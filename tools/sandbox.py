"""E2B sandbox tool layer for the Drafter's code-fix loop.

Owns the lifecycle of one ephemeral E2B sandbox per Drafter run: fetching the
target repo at a resolved commit, gating network egress through three phases
(GitHub-tarball-hosts-only -> package-registries-only -> locked), running the
agent's install/edit/test tool calls against it, and recording every
(diff, test-result) attempt as a `SandboxAttempt` for `DrafterSubgraph` to
consume. Mirrors `tools/mcp_clients.py`'s composition-root pattern
(`sandbox_toolset` == `researcher_toolset`) but diverges on eagerness: no E2B
or GitHub I/O happens until a tool is actually called (see `ensure_ready`).
"""

import asyncio
import contextlib
import functools
import inspect
import shlex
import time
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Concatenate, Literal, ParamSpec

import structlog
from e2b import (
    ALL_TRAFFIC,
    AsyncSandbox,
    CommandExitException,
    CommandResult,
    FileType,
    SandboxNetworkOpts,
    SandboxNetworkUpdate,
)
from github import Github
from langchain_core.tools import BaseTool, StructuredTool

from config.settings import Settings
from graph.schemas import SandboxAttempt, SandboxResult
from tools.mcp_clients import clamp_tool_output

log = structlog.get_logger(__name__)

_P = ParamSpec("_P")

MAX_SANDBOX_FIX_ATTEMPTS = 6

# Unlike fix_attempt, baseline/repro have no natural cap on "productive"
# retries (a model can legitimately need a couple of tries to find the right
# invocation) -- but with no cap at all, a baseline that's failing for a
# structural reason (a missing test dependency, not a bad test-command
# invocation) can absorb the entire tool-call budget on cosmetic invocation
# variants that were never going to work, leaving zero calls for the fix
# itself. These caps exist to force the model back to install_dependencies
# (via the ERROR text below) well before that happens.
MAX_SANDBOX_BASELINE_ATTEMPTS = 3
MAX_SANDBOX_REPRO_ATTEMPTS = 3

# Where the repo tarball is extracted inside the sandbox. Fixed rather than
# configurable: it's an implementation detail of this module, never exposed
# to the agent (tool paths are relative and resolved against it internally).
_REPO_DIR = "/home/user/repo"

# Phase 1 (ensure_ready steps 1-4): only GitHub's own API + tarball-download
# host, enough to resolve a ref and fetch the archive.
_GITHUB_TARBALL_HOSTS = ["api.github.com", "codeload.github.com"]

# Phase 2 (ensure_ready step 5): package registries only, so
# install_dependencies can run but nothing else can reach the network.
_PACKAGE_REGISTRY_HOSTS = [
    "pypi.org",
    "files.pythonhosted.org",
    "registry.npmjs.org",
    "registry.yarnpkg.com",
]

# install_dependencies refuses anything whose first token isn't one of these
# (or `python -m pip`) -- the install window is the only time the sandbox has
# any egress at all, so arbitrary commands are refused there.
_RECOGNIZED_INSTALLERS = {"pip", "uv", "npm", "yarn", "pnpm", "bun"}

# Default window size when read_file gets a start_line but no end_line.
# Sized so a typical source file (~50-80 chars/line) stays comfortably under
# drafter_file_read_max_chars's default of 16_000 -- the hard char clamp
# still applies on top regardless, this just avoids requiring both
# start_line and end_line for the common "give me from here on" case.
_DEFAULT_READ_WINDOW_LINES = 300

# search_file caps how many matches it describes in one call -- an
# over-broad pattern (e.g. a common word) shouldn't return an unbounded wall
# of text; the model is told to narrow the pattern instead.
_MAX_SEARCH_MATCHES = 20


def _tail_clamp(text: str, max_chars: int) -> str:
    """Like `clamp_tool_output`'s clamp, but keeps the *tail* of `text`
    rather than the head. Test-runner and installer output puts the useful
    part -- the FAILURES/traceback section, the final pass/fail summary
    line, pip/npm's error block -- at the end of stdout+stderr, not the
    start, so head-cropping it (as the generic byte-oriented
    `clamp_tool_output` does) throws away exactly the part a caller needs to
    diagnose a failure."""
    if len(text) <= max_chars:
        return text
    omitted = len(text) - max_chars
    return f"...[truncated, {omitted} earlier characters]\n{text[-max_chars:]}"


def _is_recognized_installer(command: str) -> bool:
    try:
        tokens = shlex.split(command)
    except ValueError:
        return False
    if not tokens:
        return False
    if tokens[0] in _RECOGNIZED_INSTALLERS:
        return True
    return tokens[0] == "python" and tokens[1:3] == ["-m", "pip"]


class SandboxSetupError(Exception):
    """Raised by `ensure_ready()` when the sandbox can't be created or the
    repo can't be fetched (E2B API error, private/inaccessible repo, GitHub
    rate limit). Every public tool method catches this (and generic E2B SDK
    exceptions) -- never raises out to the caller."""


class SandboxHandle:
    """Owns the lazy E2B sandbox for one Drafter run.

    Every public method acquires `self._lock` (an `asyncio.Lock`) for its
    whole body, including reads -- the sandbox is a single sequential
    resource, and this avoids a parallel tool-call batch racing a write
    against a diff snapshot. `ensure_ready()` acquires the same lock itself
    and delegates to `_ensure_ready_locked()`; every other method calls
    `_ensure_ready_locked()` directly (never the public `ensure_ready()`)
    since it's already holding the lock by the time it gets there --
    `asyncio.Lock` isn't reentrant, so re-acquiring it from inside itself
    would deadlock.

    Contract shared by every public tool method (read_file/write_file/
    edit_file/list_files/install_dependencies/run_tests): never raises.
    `SandboxSetupError` and any E2B SDK exception are caught internally,
    logged as a structured warning (`sandbox_tool_error`: tool, error), and
    turned into a returned "ERROR: ..." string.

    `repo_full_name`/`ref` are per-run values, supplied by the composition
    root from `state["issue"].repo_full_name` -- never fixed at graph-build
    time.
    """

    def __init__(
        self, *, settings: Settings, github_client: Github, repo_full_name: str, ref: str | None
    ) -> None:
        self._settings = settings
        self._github_client = github_client
        self._repo_full_name = repo_full_name
        self._ref = ref

        self._lock = asyncio.Lock()
        self._sandbox: AsyncSandbox | None = None
        self._network_locked = False
        self._billed_seconds = 0.0
        self._install_attempted = False
        self._last_call: tuple[str, tuple[object, ...]] | None = None

        self.base_commit_sha: str | None = None
        self.base_ref: str | None = None
        self.attempts: list[SandboxAttempt] = []

    def _resolve_path(self, path: str) -> str:
        return path if path.startswith("/") else f"{_REPO_DIR}/{path}"

    def _require_sandbox(self) -> AsyncSandbox:
        if self._sandbox is None:
            # Only reachable if a caller bypasses ensure_ready(), which no
            # public method does -- defensive, not expected in practice.
            raise SandboxSetupError("sandbox accessed before ensure_ready() succeeded")
        return self._sandbox

    async def _resolve_ref_and_tarball_url(self) -> tuple[str, str, str]:
        """Resolves `self._ref` (or the repo's default branch, if unset) to
        a real commit SHA and a signed tarball download URL, via PyGithub.

        PyGithub is a synchronous/blocking client (built on `requests`), so
        this whole round trip runs off the event loop via `asyncio.to_thread`
        rather than blocking it directly inside an async method.
        """

        def _resolve() -> tuple[str, str, str]:
            repo = self._github_client.get_repo(self._repo_full_name)
            resolved_ref = self._ref if self._ref is not None else repo.default_branch
            sha = repo.get_commit(resolved_ref).sha
            tarball_url = repo.get_archive_link("tarball", sha)
            return resolved_ref, sha, tarball_url

        return await asyncio.to_thread(_resolve)

    async def _ensure_ready_locked(self) -> None:
        """Create-on-first-use. Assumes `self._lock` is already held by the
        caller. Idempotent -- only does real work once."""
        if self._sandbox is not None:
            return
        if self._settings.e2b_api_key is None:
            raise SandboxSetupError("E2B_API_KEY is not configured")

        sandbox: AsyncSandbox | None = None
        try:
            # Phase 1: GitHub hosts only, so this sandbox can do nothing but
            # fetch the repo before any package installs or agent content
            # exist. Restriction is skipped entirely when
            # e2b_restrict_network is False (local-debugging escape hatch);
            # the network is still locked unconditionally later, in
            # _lock_network -- that boundary protects against agent-authored
            # content phoning home and isn't part of the debugging opt-out.
            network: SandboxNetworkOpts | None = None
            if self._settings.e2b_restrict_network:
                network = SandboxNetworkOpts(
                    allow_out=list(_GITHUB_TARBALL_HOSTS), deny_out=[ALL_TRAFFIC]
                )

            sandbox = await AsyncSandbox.create(
                timeout=int(self._settings.e2b_sandbox_session_timeout_seconds),
                api_key=self._settings.e2b_api_key.get_secret_value(),
                network=network,
            )

            resolved_ref, sha, tarball_url = await self._resolve_ref_and_tarball_url()

            setup_timeout = int(self._settings.e2b_install_timeout_seconds)
            # Never `git clone` -- fetch+extract the tarball at the resolved
            # SHA instead, then synthesize a local git history so `git diff`
            # has a baseline (GitHub tarballs ship with no .git).
            await sandbox.commands.run(f"mkdir -p {_REPO_DIR}", timeout=setup_timeout)
            await sandbox.commands.run(
                f'curl -fsSL "{tarball_url}" | tar -xz -C {_REPO_DIR} --strip-components=1',
                timeout=setup_timeout,
            )
            await sandbox.commands.run(
                "git init -q && git add -A && "
                "git -c user.email=sandbox@triage-bot.local -c user.name=triage-bot "
                "commit -q -m 'sandbox baseline' --allow-empty",
                cwd=_REPO_DIR,
                timeout=setup_timeout,
            )

            # Phase 2: package registries only, so install_dependencies can
            # run next but nothing else can reach the network.
            if self._settings.e2b_restrict_network:
                await sandbox.update_network(
                    SandboxNetworkUpdate(
                        allow_out=list(_PACKAGE_REGISTRY_HOSTS), deny_out=[ALL_TRAFFIC]
                    )
                )

            self._sandbox = sandbox
            # The *real* GitHub SHA the tarball was fetched at -- NOT the
            # synthetic local commit's SHA from the `git init` step above.
            self.base_commit_sha = sha
            self.base_ref = resolved_ref
        except Exception as exc:
            # Don't leak a sandbox that was created but failed a later setup
            # step (tarball fetch, git init, network transition).
            if sandbox is not None and self._sandbox is None:
                with contextlib.suppress(Exception):
                    await sandbox.kill()
            log.warning(
                "sandbox_setup_failed",
                repo=self._repo_full_name,
                ref=self._ref,
                error=str(exc),
            )
            raise SandboxSetupError(
                f"failed to set up sandbox for {self._repo_full_name}@{self._ref}: {exc}"
            ) from exc

    async def ensure_ready(self) -> None:
        """Public entry point: acquires the lock, then does the (idempotent)
        real setup work. Safe under concurrent callers."""
        async with self._lock:
            await self._ensure_ready_locked()

    async def _lock_network(self) -> None:
        """One-way, permanent: `update_network(allow_internet_access=False)`,
        or a no-op if already locked. Assumes `self._lock` is held."""
        if self._network_locked:
            return
        sandbox = self._require_sandbox()
        await sandbox.update_network(SandboxNetworkUpdate(allow_internet_access=False))
        self._network_locked = True

    async def _run_command(
        self, command: str, *, timeout_seconds: int, cwd: str | None = None
    ) -> CommandResult:
        """Runs `command` and always returns a `CommandResult`, even on a
        non-zero exit code -- unlike the E2B SDK's default of raising
        `CommandExitException` in that case. A failing install or test
        command is an expected, meaningful outcome here (e.g. "tests
        failed"), not a sandbox-level error; genuine SDK/transport
        exceptions still propagate to the caller unchanged.

        Named `timeout_seconds`, not `timeout` -- ruff's ASYNC109 flags an
        async function with a bare `timeout` parameter as if it were
        implementing its own cancellation logic (suggesting
        `asyncio.timeout` instead); this just forwards the value to the E2B
        SDK's own `commands.run(timeout=...)`, so that rule doesn't apply."""
        sandbox = self._require_sandbox()
        try:
            return await sandbox.commands.run(command, timeout=timeout_seconds, cwd=cwd)
        except CommandExitException as exc:
            return CommandResult(
                stdout=exc.stdout, stderr=exc.stderr, exit_code=exc.exit_code, error=exc.error
            )

    def _has_passing_baseline(self) -> bool:
        return any(a.kind == "baseline" and a.result.passed for a in self.attempts)

    def _attempt_count(self, kind: str) -> int:
        return sum(1 for a in self.attempts if a.kind == kind)

    def _bounded_timeout_seconds(self, configured_timeout: float) -> int:
        """Caps a per-call timeout at whatever's left of the run's
        billed-seconds budget, so a single slow command can no longer run
        for the full `configured_timeout` once the budget is nearly
        exhausted -- without this, a call starting with e.g. 1s of
        remaining budget could still run for the full
        e2b_install_timeout_seconds (300s) before the next gate check
        fires. Floors at 1 second (never 0, which some execution backends
        treat as "no timeout" rather than "immediate timeout") -- every
        caller already refuses the call outright when `self._billed_seconds
        >= e2b_max_billed_seconds_per_run`, so this is only reached with a
        strictly positive remaining budget, potentially under a second.
        """
        remaining_budget = self._settings.e2b_max_billed_seconds_per_run - self._billed_seconds
        return max(1, int(min(configured_timeout, remaining_budget)))

    @staticmethod
    def _repeat_guarded(
        fn: Callable[Concatenate[SandboxHandle, _P], Awaitable[str]],
    ) -> Callable[Concatenate[SandboxHandle, _P], Awaitable[str]]:
        """Decorator for the read-only tool methods (list_files/read_file/
        search_file). Refuses an exact repeat of the call immediately before
        it -- these tools are deterministic (their own descriptions already
        say so), so an immediate repeat can't surface anything new and only
        wastes a tool-call slot out of the Drafter's budget (the failure
        mode this closes: a model looping on the same read_file range
        indefinitely). Binds arguments against the function's own signature
        (not the raw positional/keyword args a caller happened to use) so
        the same logical call always produces the same key regardless of
        calling style.

        Compares against a single most-recent-call slot (`self._last_call`),
        not a running history of every call made this run: a full-history
        blacklist would permanently refuse a *later*, legitimate re-fetch of
        the same arguments -- e.g. once ContextEditingMiddleware clears an
        old tool result, its placeholder text explicitly tells the model to
        "call this tool again if you need the original data"
        (see `graph/nodes/agent_subgraph.py`'s `context_edit_placeholder`).
        `self._last_call` is shared with every other public tool method --
        write_file/edit_file/install_dependencies/run_tests each reset it to
        `None` at the top of their own body (undecorated) -- so adjacency is
        measured against the true previous tool call, not just the most
        recent read-only one (e.g. read_file -> edit_file -> the same
        read_file again must NOT be flagged as a repeat).

        The check-and-record step is done under `self._lock` (briefly
        acquired and released, not held across the call into `fn`) to keep
        it race-free against a concurrent tool-call batch, consistent with
        this class's existing concurrency contract -- then released before
        calling `fn`, which acquires the same (non-reentrant) lock itself
        for its own body.
        """
        signature = inspect.signature(fn)

        @functools.wraps(fn)
        async def wrapper(self: SandboxHandle, *args: _P.args, **kwargs: _P.kwargs) -> str:
            bound = signature.bind(self, *args, **kwargs)
            bound.apply_defaults()
            call_args = dict(bound.arguments)
            del call_args["self"]
            key = (fn.__name__, tuple(call_args.items()))
            async with self._lock:
                is_repeat = self._last_call == key
                self._last_call = key
            if is_repeat:
                log.info("sandbox_repeat_call_refused", tool=fn.__name__, **call_args)
                return (
                    f"ERROR: {fn.__name__} was just called with these exact "
                    "arguments -- repeating it immediately can't reveal anything "
                    "new (these tools are deterministic). Change the arguments, "
                    "or move on to the next step, instead of repeating this "
                    "exact call."
                )
            return await fn(self, *args, **kwargs)

        return wrapper

    @_repeat_guarded
    async def read_file(
        self, path: str, start_line: int | None = None, end_line: int | None = None
    ) -> str:
        """`start_line`/`end_line` (1-indexed, both optional) let the model
        read a specific window of a large file instead of always the head --
        without them, `arrow/arrow.py`-sized files (65KB, well over the
        16,000-char default clamp) can never have their tail seen at all,
        no matter how many times read_file is called. Self-clamps via
        `self._settings.drafter_file_read_max_chars`, the same pattern
        `install_dependencies`/`run_tests` already use for their own output
        budgets -- so `build_sandbox_tools` no longer needs to wrap this
        tool in the generic `clamp_tool_output`."""
        log.info("sandbox_read_file", path=path, start_line=start_line, end_line=end_line)
        async with self._lock:
            try:
                await self._ensure_ready_locked()
                sandbox = self._require_sandbox()
                text = await sandbox.files.read(self._resolve_path(path))
                return self._slice_and_clamp_lines(text, start_line=start_line, end_line=end_line)
            except Exception as exc:
                log.warning("sandbox_tool_error", tool="read_file", error=str(exc))
                return f"ERROR: {exc}{await self._list_parent_for_error(path)}"

    def _slice_and_clamp_lines(
        self, text: str, *, start_line: int | None, end_line: int | None
    ) -> str:
        """Shared by `read_file`'s whole-file default and explicit-range
        requests -- always reports total line count in its truncation
        notice (never just an opaque char count) so the model knows how far
        it can page, per the "tool calls are deterministic" Global
        Constraint in `prompts/drafter.py`: repeating the same call can
        never reveal more, but a different `start_line`/`end_line` can."""
        lines = text.splitlines()
        total_lines = len(lines)

        if start_line is None and end_line is None:
            first_line, last_line = 1, total_lines
        else:
            first_line = start_line if start_line is not None else 1
            if first_line < 1:
                return "ERROR: start_line must be >= 1"
            if first_line > total_lines:
                return f"ERROR: file has only {total_lines} lines"
            last_line = (
                end_line if end_line is not None else first_line + _DEFAULT_READ_WINDOW_LINES - 1
            )
            if last_line < first_line:
                return "ERROR: end_line must be >= start_line"
            last_line = min(last_line, total_lines)

        content = "\n".join(lines[first_line - 1 : last_line])

        max_chars = self._settings.drafter_file_read_max_chars
        char_truncated = len(content) > max_chars
        if char_truncated:
            content = content[:max_chars]

        if last_line < total_lines or char_truncated:
            content += (
                f"\n...[truncated: showing lines {first_line}-{last_line} of "
                f"{total_lines} total. Use start_line/end_line to read further, or "
                "search_file to jump to something specific.]"
            )
        return content

    @_repeat_guarded
    async def search_file(self, path: str, pattern: str, context_lines: int = 3) -> str:
        """Literal substring search, deliberately not regex -- a
        model-chosen (or content-influenced, via prompt injection from file
        contents) regex pattern would be a ReDoS vector for no real benefit
        over substring matching when looking for a function/snippet name.
        Complements `read_file`'s line range for the case evidence gives no
        line number at all (`Evidence.reference` is a free-form string per
        its own field description, not guaranteed to carry one)."""
        log.info("sandbox_search_file", path=path, pattern=pattern)
        async with self._lock:
            try:
                if not pattern:
                    return "ERROR: pattern must not be empty"
                await self._ensure_ready_locked()
                sandbox = self._require_sandbox()
                text = await sandbox.files.read(self._resolve_path(path))
                return self._format_search_result(
                    text, path=path, pattern=pattern, context_lines=context_lines
                )
            except Exception as exc:
                log.warning("sandbox_tool_error", tool="search_file", error=str(exc))
                return f"ERROR: {exc}{await self._list_parent_for_error(path)}"

    def _format_search_result(
        self, text: str, *, path: str, pattern: str, context_lines: int
    ) -> str:
        lines = text.splitlines()
        matches = [i for i, line in enumerate(lines) if pattern in line]
        if not matches:
            return f"No matches for {pattern!r} in {path}"

        shown = matches[:_MAX_SEARCH_MATCHES]
        blocks: list[str] = []
        for idx in shown:
            start = max(0, idx - context_lines)
            end = min(len(lines), idx + context_lines + 1)
            blocks.append("\n".join(f"line {i + 1}: {lines[i]}" for i in range(start, end)))
        content = "\n--\n".join(blocks)

        if len(matches) > _MAX_SEARCH_MATCHES:
            omitted_matches = len(matches) - _MAX_SEARCH_MATCHES
            content += f"\n...[{omitted_matches} further matches omitted, narrow your pattern]"

        max_chars = self._settings.drafter_file_read_max_chars
        if len(content) > max_chars:
            omitted = len(content) - max_chars
            content = f"{content[:max_chars]}\n...[truncated, {omitted} more characters]"
        return content

    async def _list_parent_for_error(self, path: str) -> str:
        """Best-effort: appended to a failed `read_file`'s error so the model
        can self-correct (find the real path) without spending a separate
        `list_files` round trip on a path it already knows is wrong. Never
        raises -- any failure here just falls back to the plain error
        string. Calls `sandbox.files.list()` directly rather than the public
        `list_files()` method: the caller (`read_file`) already holds
        `self._lock`, and `asyncio.Lock` isn't reentrant."""
        log.info("sandbox_list_parent_for_error", path=path)
        try:
            sandbox = self._require_sandbox()
            parent = self._resolve_path(path).rsplit("/", 1)[0] or "/"
            entries = await sandbox.files.list(parent)
            names = "\n".join(
                f"{entry.path}/" if entry.type == FileType.DIR else entry.path for entry in entries
            )
            return f"\nContents of {parent}:\n{names}" if names else f"\n{parent} is empty"
        except Exception:
            return ""

    async def write_file(self, path: str, content: str) -> str:
        log.info("sandbox_write_file", path=path, content=content)
        async with self._lock:
            try:
                # Invalidates the read-only tools' repeat-guard adjacency
                # (see _repeat_guarded): a mutation happened, so a
                # subsequent read_file/search_file/list_files call that
                # repeats an earlier one is no longer a back-to-back
                # no-op and must not be refused.
                self._last_call = None
                await self._ensure_ready_locked()
                sandbox = self._require_sandbox()
                await self._lock_network()
                # e2b's Filesystem.write signature carries an unparameterized
                # `IO[Unknown]` in its `data` union, which makes the awaited
                # return type only partially known to pyright regardless of
                # the (fully-str) arguments actually passed here -- a stub
                # completeness gap in the third-party library, not a type
                # error in this call.
                await sandbox.files.write(  # pyright: ignore[reportUnknownMemberType]
                    self._resolve_path(path), content
                )
                return f"wrote {path}"
            except Exception as exc:
                log.warning("sandbox_tool_error", tool="write_file", error=str(exc))
                return f"ERROR: {exc}"

    async def edit_file(self, path: str, find: str, replace: str) -> str:
        log.info("sandbox_edit_file", path=path, find=find, replace=replace)
        async with self._lock:
            try:
                # See the comment in write_file() above.
                self._last_call = None
                await self._ensure_ready_locked()
                sandbox = self._require_sandbox()
                await self._lock_network()
                resolved_path = self._resolve_path(path)
                text = await sandbox.files.read(resolved_path)
                occurrences = text.count(find)
                if occurrences == 0:
                    return f"ERROR: no match for the given text in {path}"
                if occurrences > 1:
                    return (
                        f"ERROR: {occurrences} matches for the given text in {path}; "
                        "must match exactly once"
                    )
                # See the comment on the write() call in write_file() above.
                await sandbox.files.write(  # pyright: ignore[reportUnknownMemberType]
                    resolved_path, text.replace(find, replace, 1)
                )
                return f"edited {path}"
            except Exception as exc:
                log.warning("sandbox_tool_error", tool="edit_file", error=str(exc))
                return f"ERROR: {exc}"

    @_repeat_guarded
    async def list_files(self, path: str = ".") -> str:
        log.info("sandbox_list_files", path=path)
        async with self._lock:
            try:
                await self._ensure_ready_locked()
                sandbox = self._require_sandbox()
                entries = await sandbox.files.list(self._resolve_path(path))
                if not entries:
                    return "(empty)"
                return "\n".join(
                    f"{entry.path}/" if entry.type == FileType.DIR else entry.path
                    for entry in entries
                )
            except Exception as exc:
                log.warning("sandbox_tool_error", tool="list_files", error=str(exc))
                return f"ERROR: {exc}"

    async def install_dependencies(self, command: str) -> str:
        async with self._lock:
            try:
                # See the comment in write_file() above.
                self._last_call = None
                await self._ensure_ready_locked()
                self._require_sandbox()
                if self._network_locked:
                    log.info(
                        "sandbox_tool_result",
                        tool="install_dependencies",
                        command=command,
                        passed=False,
                        reason="network_locked",
                    )
                    return (
                        "ERROR: sandbox network is locked; dependencies can no longer be installed"
                    )
                if not _is_recognized_installer(command):
                    log.info(
                        "sandbox_tool_result",
                        tool="install_dependencies",
                        command=command,
                        passed=False,
                        reason="unrecognized_installer",
                    )
                    return f"ERROR: unrecognized installer command: {command!r}"
                if self._billed_seconds >= self._settings.e2b_max_billed_seconds_per_run:
                    log.info(
                        "sandbox_tool_result",
                        tool="install_dependencies",
                        command=command,
                        passed=False,
                        reason="billed_seconds_exhausted",
                    )
                    return "ERROR: sandbox billed-seconds budget exhausted"

                # Marked as soon as a real install command is genuinely
                # dispatched -- regardless of its exit code -- so run_tests
                # can tell "the agent tried and it's still failing" apart
                # from "the agent skipped straight to run_tests" (see
                # run_tests's own baseline-without-install gate below).
                self._install_attempted = True

                start = time.monotonic()
                result = await self._run_command(
                    command,
                    timeout_seconds=self._bounded_timeout_seconds(
                        self._settings.e2b_install_timeout_seconds
                    ),
                    cwd=_REPO_DIR,
                )
                combined = f"{result.stdout}{result.stderr}"

                self._billed_seconds += time.monotonic() - start

                passed = result.exit_code == 0
                status = "INSTALLED" if passed else "INSTALL_FAILED"
                budget = (
                    self._settings.drafter_test_log_success_max_chars
                    if passed
                    else self._settings.drafter_test_log_failure_max_chars
                )
                log.info(
                    "sandbox_tool_result",
                    tool="install_dependencies",
                    command=command,
                    exit_code=result.exit_code,
                    # result=combined,
                    duration_seconds=time.monotonic() - start,
                    passed=passed,
                )
                return f"{status}: {command}\n{_tail_clamp(combined, budget)}"
            except Exception as exc:
                log.warning("sandbox_tool_error", tool="install_dependencies", error=str(exc))
                return f"ERROR: {exc}"

    async def run_tests(
        self, *, kind: Literal["baseline", "repro", "fix_attempt"], test_command: str
    ) -> str:
        async with self._lock:
            try:
                # See the comment in write_file() above.
                self._last_call = None
                await self._ensure_ready_locked()
                self._require_sandbox()
                # A "baseline" run exercises only the pristine, as-fetched
                # repo -- no agent-authored content exists in the sandbox
                # yet (write_file/edit_file always lock the network
                # unconditionally, before writing anything, so if either had
                # already run this call would find the network already
                # locked regardless of `kind`). That makes it safe to run
                # baseline during the install-phase (registry-only) network,
                # which some test runners need: tox/nox provision their own
                # per-env dependencies as part of the *first* invocation of a
                # given environment, rather than during a separate install
                # step, and would otherwise fail to reach the registry once
                # the network is locked. Every other kind runs strictly
                # after an edit has already locked the network -- this call
                # is a no-op in that case, not a widened window.
                if kind != "baseline":
                    await self._lock_network()

                # A first baseline attempt is always allowed without a prior
                # install_dependencies call (see the network-gating comment
                # above -- tox/nox self-provision on first invocation). But
                # once that first attempt has failed with nothing installed,
                # a further baseline attempt is refused outright rather than
                # just hinted at: a hint is something the model can read and
                # ignore on retry -- exactly the failure mode this gate
                # exists to close. This never fires once any baseline
                # attempt has passed, so a tox/nox repo that already went
                # green is never blocked from anything.
                def _refuse(reason: str, message: str) -> str:
                    log.info(
                        "sandbox_tool_result",
                        tool="run_tests",
                        kind=kind,
                        test_command=test_command,
                        passed=False,
                        reason=reason,
                    )
                    return message

                if (
                    kind == "baseline"
                    and not self._has_passing_baseline()
                    and self._attempt_count("baseline") >= 1
                    and not self._install_attempted
                ):
                    return _refuse(
                        "baseline_retry_without_install",
                        "ERROR: the previous baseline attempt failed and "
                        "install_dependencies has not been called yet this run -- call "
                        "install_dependencies before retrying run_tests, rather than "
                        "repeating the same test command.",
                    )
                if (
                    kind == "baseline"
                    and self._attempt_count("baseline") >= MAX_SANDBOX_BASELINE_ATTEMPTS
                ):
                    return _refuse(
                        "baseline_attempt_cap",
                        f"ERROR: baseline attempt limit ({MAX_SANDBOX_BASELINE_ATTEMPTS}) reached.",
                    )
                if kind in ("repro", "fix_attempt") and not self._has_passing_baseline():
                    return _refuse(
                        "no_passing_baseline", 'ERROR: no passing "baseline" run recorded yet'
                    )
                if kind == "repro" and self._attempt_count("repro") >= MAX_SANDBOX_REPRO_ATTEMPTS:
                    return _refuse(
                        "repro_attempt_cap",
                        f"ERROR: repro attempt limit ({MAX_SANDBOX_REPRO_ATTEMPTS}) reached",
                    )
                if kind == "fix_attempt" and self._attempt_count("repro") == 0:
                    return _refuse(
                        "fix_attempt_without_repro",
                        'ERROR: no "repro" run recorded yet -- run_tests(kind="repro") against '
                        "a test that captures this issue (write one first if none exists) "
                        "before attempting a fix, so there is something concrete to verify the "
                        "fix against.",
                    )
                if (
                    kind == "fix_attempt"
                    and self._attempt_count("fix_attempt") >= MAX_SANDBOX_FIX_ATTEMPTS
                ):
                    return _refuse(
                        "fix_attempt_cap",
                        f"ERROR: fix attempt limit ({MAX_SANDBOX_FIX_ATTEMPTS}) reached",
                    )
                if self._billed_seconds >= self._settings.e2b_max_billed_seconds_per_run:
                    return _refuse(
                        "billed_seconds_exhausted", "ERROR: sandbox billed-seconds budget exhausted"
                    )

                # Snapshot the diff *before* running the test command so a
                # pass/fail is never separated from the exact diff that
                # produced it. Stage everything first: plain `git diff`
                # compares the working tree against the index and never
                # shows untracked files at all, so a brand-new file the
                # agent just wrote (write_file) would otherwise be
                # permanently invisible here -- `git add -A` (respecting
                # .gitignore) plus `--cached` diffs against the one-time
                # baseline commit from ensure_ready(), covering new files
                # exactly like modified ones.
                await self._run_command("git add -A", timeout_seconds=60, cwd=_REPO_DIR)
                diff_result = await self._run_command(
                    "git diff --cached", timeout_seconds=60, cwd=_REPO_DIR
                )
                changed_files_result = await self._run_command(
                    "git diff --cached --name-only", timeout_seconds=60, cwd=_REPO_DIR
                )
                changed_files = [line for line in changed_files_result.stdout.splitlines() if line]

                # A fix_attempt whose diff exactly matches one that already
                # passed can't produce a different result -- refusing it here
                # (before the real test command runs) is what actually saves
                # the E2B billed-seconds a repeat call would otherwise waste,
                # not just a wasted tool-call slot. Deliberately compares
                # against the diff, not just "any passing fix_attempt exists":
                # a genuinely new edit made after an earlier pass must still
                # be verified.
                if (
                    kind == "fix_attempt"
                    and self.last_passing_fix_attempt is not None
                    and diff_result.stdout == self.last_passing_fix_attempt.diff
                ):
                    return _refuse(
                        "fix_attempt_diff_already_passed",
                        "ERROR: a fix_attempt with this exact diff already passed "
                        f"(attempt {self.last_passing_fix_attempt.attempt_number}) -- "
                        "re-running an unchanged diff cannot produce a different result. "
                        "Propose the code_fix action now instead of calling run_tests again.",
                    )

                start = time.monotonic()
                test_result = await self._run_command(
                    test_command,
                    timeout_seconds=self._bounded_timeout_seconds(
                        self._settings.e2b_test_command_timeout_seconds
                    ),
                    cwd=_REPO_DIR,
                )
                duration = time.monotonic() - start
                self._billed_seconds += duration

                passed = test_result.exit_code == 0
                logs = f"{test_result.stdout}{test_result.stderr}"
                attempt = SandboxAttempt(
                    kind=kind,
                    attempt_number=len(self.attempts) + 1,
                    diff=diff_result.stdout,
                    changed_files=changed_files,
                    result=SandboxResult(
                        passed=passed,
                        logs=logs,
                        test_command=test_command,
                        duration_seconds=duration,
                    ),
                    recorded_at=datetime.now(UTC),
                )
                self.attempts.append(attempt)
                log.info(
                    "sandbox_attempt_recorded",
                    kind=kind,
                    test_command=test_command,
                    attempt_number=attempt.attempt_number,
                    changed_files=changed_files,
                    diff_length=len(attempt.diff),
                    logs_length=len(logs),
                    # logs=logs,
                    duration_seconds=duration,
                    passed=passed,
                    cumulative_billed_seconds=self._billed_seconds,
                    cumulative_cost_usd=self.estimated_cost_usd,
                )
                status = "PASSED" if passed else "FAILED"
                budget = (
                    self._settings.drafter_test_log_success_max_chars
                    if passed
                    else self._settings.drafter_test_log_failure_max_chars
                )
                result_text = f"{status}: {test_command}\n{_tail_clamp(logs, budget)}"
                if kind == "baseline" and not passed and not self._install_attempted:
                    # First failure, install never attempted: warn now, on
                    # this attempt -- the *next* baseline attempt without an
                    # install call in between is hard-refused (see the gate
                    # above), so this is the model's one chance to notice
                    # before that happens.
                    result_text += (
                        "\n\nNote: install_dependencies has not been called yet this "
                        "run. If this failure looks like a missing dependency (e.g. a "
                        "module/import/command-not-found error), call "
                        "install_dependencies before retrying."
                    )
                if kind == "repro" and passed:
                    # Advisory, not a hard refusal -- unlike the fix_attempt
                    # gate above, a passing repro isn't always wrong (the
                    # issue may already be fixed), so this shouldn't block
                    # the workflow, only prompt the model to reconsider.
                    result_text += (
                        "\n\nWarning: this repro run PASSED. Per the workflow, a repro "
                        "is expected to FAIL, capturing the bug -- a passing repro means "
                        "the bug wasn't actually reproduced. Reconsider before editing: "
                        "find or write a test that actually fails first."
                    )
                return result_text
            except Exception as exc:
                log.warning("sandbox_tool_error", tool="run_tests", error=str(exc))
                return f"ERROR: {exc}"

    @property
    def install_attempted(self) -> bool:
        """Whether `install_dependencies` has actually dispatched a real
        install command at least once this run, regardless of pass/fail.
        Used by `run_tests`'s own baseline-without-install gate, and
        threaded into `format_failed_fix_comment` so a "no fix attempted"
        comment can tell a genuine pre-existing repo failure apart from the
        agent's own sandbox-setup miss."""
        return self._install_attempted

    @property
    def last_passing_fix_attempt(self) -> SandboxAttempt | None:
        """Scans `self.attempts` in reverse for the last entry with
        kind=="fix_attempt", result.passed=True, and a non-empty diff. A
        passing baseline/repro attempt never counts, even if it's the most
        recent entry."""
        for attempt in reversed(self.attempts):
            if attempt.kind == "fix_attempt" and attempt.result.passed and attempt.diff:
                return attempt
        return None

    @property
    def estimated_cost_usd(self) -> float:
        """Observability only -- feeds `RunMeta.estimated_cost_usd`, never
        used to gate anything (the real gate is billed-seconds vs.
        `e2b_max_billed_seconds_per_run`, checked directly in run_tests/
        install_dependencies)."""
        return self._billed_seconds * self._settings.e2b_cost_per_second_usd

    async def aclose(self) -> None:
        """Kills the E2B sandbox if `ensure_ready()` ever actually created
        one; no-op otherwise (the common case for Drafter runs that never
        touch the sandbox at all)."""
        async with self._lock:
            if self._sandbox is not None:
                with contextlib.suppress(Exception):
                    await self._sandbox.kill()
                self._sandbox = None


def build_sandbox_tools(handle: SandboxHandle, *, file_read_max_chars: int) -> list[BaseTool]:
    """7 `StructuredTool`s as closures over `handle`: read_file, write_file,
    edit_file, list_files, install_dependencies, run_tests, search_file --
    each a thin async wrapper calling the matching `SandboxHandle` method
    and returning its string result. `read_file`/`search_file` are now
    line/match-count-aware self-clamped inside `SandboxHandle` itself (see
    `_slice_and_clamp_lines`/`_format_search_result`), the same pattern
    `install_dependencies`/`run_tests` already use via `_tail_clamp` --
    wrapping them again here in the generic, line-unaware `clamp_tool_output`
    would produce two stacked truncation notices. `list_files` output is
    still clamped to `file_read_max_chars` via `clamp_tool_output` (reused
    from `tools/mcp_clients.py`), a plain head-crop. `write_file`/`edit_file`
    return short, fixed-shape status strings, not raw file/log content, so
    they're left unclamped too."""

    async def read_file(
        path: str, start_line: int | None = None, end_line: int | None = None
    ) -> str:
        return await handle.read_file(path, start_line=start_line, end_line=end_line)

    async def write_file(path: str, content: str) -> str:
        return await handle.write_file(path, content)

    async def edit_file(path: str, find: str, replace: str) -> str:
        return await handle.edit_file(path, find, replace)

    async def list_files(path: str = ".") -> str:
        return await handle.list_files(path)

    async def install_dependencies(command: str) -> str:
        return await handle.install_dependencies(command)

    async def run_tests(
        kind: Literal["baseline", "repro", "fix_attempt"], test_command: str
    ) -> str:
        return await handle.run_tests(kind=kind, test_command=test_command)

    async def search_file(path: str, pattern: str, context_lines: int = 3) -> str:
        return await handle.search_file(path, pattern, context_lines=context_lines)

    read_file_tool = StructuredTool.from_function(
        coroutine=read_file,
        name="read_file",
        description=(
            "Read a file's contents from the sandboxed repository checkout. Calling "
            "it again with the same arguments always returns the same content -- "
            "pass start_line (and optionally end_line, both 1-indexed) to read a "
            "different range of a large file instead of retrying the same call."
        ),
    )
    search_file_tool = StructuredTool.from_function(
        coroutine=search_file,
        name="search_file",
        description=(
            "Search a file in the sandboxed repository checkout for a literal "
            "substring, returning matching line numbers with surrounding context. "
            "Use this to locate a function or snippet by name when you don't "
            "already know its line number."
        ),
    )
    write_file_tool = StructuredTool.from_function(
        coroutine=write_file,
        name="write_file",
        description=(
            "Overwrite a file's contents in the sandbox. Permanently disables the "
            "sandbox's network access from this point on."
        ),
    )
    edit_file_tool = StructuredTool.from_function(
        coroutine=edit_file,
        name="edit_file",
        description=(
            "Replace an exact, uniquely-matching snippet of text in a file. Fails if "
            "the snippet doesn't match exactly once. Permanently disables the "
            "sandbox's network access from this point on."
        ),
    )
    list_files_tool = StructuredTool.from_function(
        coroutine=list_files,
        name="list_files",
        description="List files and directories under a path in the sandboxed repository checkout.",
    )
    install_dependencies_tool = StructuredTool.from_function(
        coroutine=install_dependencies,
        name="install_dependencies",
        description="Run the repository's dependency-install command inside the sandbox.",
    )
    run_tests_tool = StructuredTool.from_function(
        coroutine=run_tests,
        name="run_tests",
        description="Run the repository's test command inside the sandbox and record the result.",
    )

    return [
        read_file_tool,
        write_file_tool,
        edit_file_tool,
        clamp_tool_output(list_files_tool, max_chars=file_read_max_chars),
        install_dependencies_tool,
        run_tests_tool,
        search_file_tool,
    ]


@asynccontextmanager
async def sandbox_toolset(
    settings: Settings, github_client: Github, repo_full_name: str, ref: str | None = None
) -> AsyncGenerator[tuple[list[BaseTool], SandboxHandle | None]]:
    """Composition-root context manager, mirrors `tools/mcp_clients.py`'s
    `researcher_toolset` pattern but diverges on eagerness: no I/O happens in
    this function's own body -- constructing `SandboxHandle` is a cheap
    no-op (all E2B/PyGithub I/O is inside `ensure_ready()`, called lazily by
    the tool methods on first real use). Yields `(tools, handle)` -- unlike
    `researcher_toolset`, the caller (`DrafterSubgraph.finalize()`) needs the
    handle's recorded attempts directly, not just the tools. Yields
    `(tools=[], handle=None)` when `settings.e2b_api_key` is unset, matching
    the `GITHUB_TOKEN`/`TAVILY_API_KEY` graceful-degradation precedent
    elsewhere in this codebase. `finally: await handle.aclose()` (skipped
    when `handle` is `None`) guarantees the sandbox is never leaked even if
    the caller raises."""
    if settings.e2b_api_key is None:
        log.warning("sandbox_tool_unavailable", reason="E2B_API_KEY not set")
        yield [], None
        return

    handle = SandboxHandle(
        settings=settings, github_client=github_client, repo_full_name=repo_full_name, ref=ref
    )
    try:
        tools = build_sandbox_tools(
            handle, file_read_max_chars=settings.drafter_file_read_max_chars
        )
        yield tools, handle
    finally:
        await handle.aclose()
