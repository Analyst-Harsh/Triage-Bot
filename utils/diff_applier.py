import os
import subprocess
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from shutil import which
from typing import Final

DEFAULT_GIT_TIMEOUT_SECONDS: Final[float] = 30.0

_BOT_AUTHOR_NAME = "triage-bot"
_BOT_AUTHOR_EMAIL = "triage-bot@users.noreply.github.com"


class DiffApplyError(Exception):
    """Raised when staging, applying, or reading back a unified diff fails
    -- the only exception type `DiffApplier.apply` ever raises; a bare
    `subprocess`/`OSError` never escapes this module."""


@dataclass(frozen=True)
class AppliedFile:
    """One file's post-apply state. `content=None` means the file was
    deleted by the diff. Internal to the `utils`/`GitHubClient` boundary --
    never persisted, never crosses a trust boundary itself."""

    path: str
    content: str | None


def _git_executable() -> str:
    resolved = which("git")
    if resolved is None:
        raise DiffApplyError("git executable not found on PATH")
    return resolved


def _git_env() -> dict[str, str]:
    """Isolates every git invocation from the host's global/system
    gitconfig (e.g. `core.hooksPath` running an arbitrary script on
    commit, or `commit.gpgsign` blocking on a passphrase prompt) --
    behavior must depend only on this module's own `-c` flags and the
    ephemeral repo's local config, never on ambient machine state."""
    return {**os.environ, "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_SYSTEM": "/dev/null"}


def _validate_relative_path(path: str) -> str:
    parsed = PurePosixPath(path)
    if parsed.is_absolute() or ".." in parsed.parts:
        raise DiffApplyError(f"refusing unsafe path from diff: {path!r}")
    return path


def _write_base_file(workdir: Path, path: str, content: str) -> None:
    validated = _validate_relative_path(path)
    full_path = workdir / validated
    full_path.parent.mkdir(parents=True, exist_ok=True)
    full_path.write_text(content, encoding="utf-8")


def _read_applied_file(workdir: Path, path: str) -> str:
    validated = _validate_relative_path(path)
    full_path = workdir / validated
    try:
        raw = full_path.read_bytes()
    except OSError as exc:
        raise DiffApplyError(f"failed to read {path!r} after applying diff: {exc}") from exc
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise DiffApplyError(f"{path!r} is not valid UTF-8 after applying diff") from exc


def _collect_applied_files(workdir: Path, status_output: str) -> list[AppliedFile]:
    """Parses `git status --porcelain=v1 -z` output (already `git add -A`
    staged, so the index status column carries the real change; the
    worktree column is always blank). Renames appear as a status token
    followed by an extra NUL-terminated original-path field -- verified
    empirically against git 2.50, not merely assumed from docs."""
    tokens = status_output.split("\0")
    applied: list[AppliedFile] = []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        index += 1
        if not token:
            continue
        if len(token) < 4:
            raise DiffApplyError(f"unexpected git status entry: {token!r}")

        status_code, path = token[0], token[3:]

        if status_code == "R":
            if index >= len(tokens):
                raise DiffApplyError("rename entry missing original path")
            old_path = tokens[index]
            index += 1
            applied.append(AppliedFile(path=_validate_relative_path(old_path), content=None))
            applied.append(
                AppliedFile(
                    path=_validate_relative_path(path),
                    content=_read_applied_file(workdir, path),
                )
            )
        elif status_code == "D":
            applied.append(AppliedFile(path=_validate_relative_path(path), content=None))
        elif status_code in ("A", "M"):
            applied.append(
                AppliedFile(
                    path=_validate_relative_path(path),
                    content=_read_applied_file(workdir, path),
                )
            )
        else:
            raise DiffApplyError(f"unsupported git status code {status_code!r} for {path!r}")

    return applied


class DiffApplier:
    """Applies a unified diff strictly against known base file contents,
    using the real `git` binary in an ephemeral, isolated repository.

    `git apply` is strict by default (exact context, no fuzzy matching,
    refuses paths escaping the working tree) -- this class adds no
    patch-application logic of its own, only staging/subprocess/
    failure-mapping orchestration around it. Applying a diff is a data
    transformation on text, not execution of the diff's own content, so
    this never runs anything the diff's author supplied.
    """

    def __init__(self, *, timeout_seconds: float = DEFAULT_GIT_TIMEOUT_SECONDS) -> None:
        self._timeout_seconds = timeout_seconds

    def apply(self, diff: str, base_files: Mapping[str, str | None]) -> list[AppliedFile]:
        """Applies `diff` against `base_files` (path -> content, or `None`
        for a path the diff itself adds) and returns the resulting state of
        every file the diff touched.

        Raises `DiffApplyError` -- never a bare `subprocess`/`OSError` --
        on any failure, with git's own stderr describing exactly which
        hunk didn't apply.
        """
        if not diff.strip():
            raise DiffApplyError("refusing to apply an empty diff")

        with tempfile.TemporaryDirectory(prefix="triage-bot-diff-") as tmp:
            tmp_path = Path(tmp)
            # The patch file lives outside `workdir` so it never shows up in
            # `git status`/`git add -A` inside the repo it's being applied to.
            workdir = tmp_path / "workdir"
            workdir.mkdir()
            patch_path = tmp_path / "change.patch"
            patch_path.write_text(diff, encoding="utf-8")

            self._run_git_checked(["init", "-q"], cwd=workdir)
            self._run_git_checked(["config", "user.name", _BOT_AUTHOR_NAME], cwd=workdir)
            self._run_git_checked(["config", "user.email", _BOT_AUTHOR_EMAIL], cwd=workdir)

            for path, content in base_files.items():
                if content is not None:
                    _write_base_file(workdir, path, content)

            self._run_git_checked(["add", "-A"], cwd=workdir)
            # --allow-empty: a diff that only adds new files has nothing to
            # commit yet at this point.
            self._run_git_checked(["commit", "--allow-empty", "-q", "-m", "base"], cwd=workdir)

            check_result = self._run_git(["apply", "--check", str(patch_path)], cwd=workdir)
            if check_result.returncode != 0:
                raise DiffApplyError(f"diff failed to apply: {check_result.stderr.strip()}")
            self._run_git_checked(["apply", str(patch_path)], cwd=workdir)

            self._run_git_checked(["add", "-A"], cwd=workdir)
            status = self._run_git_checked(["status", "--porcelain=v1", "-z"], cwd=workdir)

            return _collect_applied_files(workdir, status.stdout)

    def _run_git(self, args: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
        git = _git_executable()
        try:
            return subprocess.run(  # noqa: S603 -- fixed argv (git + our own flags), no shell
                [git, *args],
                cwd=cwd,
                env=_git_env(),
                capture_output=True,
                text=True,
                timeout=self._timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise DiffApplyError(
                f"git {' '.join(args)} timed out after {self._timeout_seconds}s"
            ) from exc

    def _run_git_checked(self, args: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
        result = self._run_git(args, cwd=cwd)
        if result.returncode != 0:
            raise DiffApplyError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
        return result
