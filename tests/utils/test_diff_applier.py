"""These tests run the real `git` binary (present in dev/CI/deploy per
AGENTS.md) rather than faking it -- for a class whose entire job is
orchestrating git subprocess calls, a fake would only prove the fake
matches our own assumptions about git's behavior, not that it's correct.
Test diffs are generated via git itself (`_git_diff_between`), not
hand-written unified-diff text, so they're guaranteed well-formed."""

import subprocess
from collections.abc import Mapping
from pathlib import Path
from shutil import which
from uuid import uuid4

import pytest

from utils.diff_applier import AppliedFile, DiffApplier, DiffApplyError


def _require_git() -> str:
    resolved = which("git")
    if resolved is None:
        raise RuntimeError("git executable required to run these tests")
    return resolved


_GIT: str = _require_git()


def _apply(diff: str, base_files: Mapping[str, str | None]) -> list[AppliedFile]:
    return DiffApplier().apply(diff, base_files)


def _run(args: list[str], *, cwd: Path) -> subprocess.CompletedProcess[bytes]:
    # Binary capture, decoded manually where needed: subprocess's `text=True`
    # applies universal-newline translation to captured stdout, which would
    # silently collapse a CRLF file's "\r\n" line endings to "\n" before the
    # diff/status text ever reaches our assertions.
    return subprocess.run(  # noqa: S603 -- resolved git path, test-authored fixed args
        [_GIT, *args], cwd=cwd, check=True, capture_output=True
    )


def _stdout(result: subprocess.CompletedProcess[bytes]) -> str:
    return result.stdout.decode("utf-8")


def _git_diff_between(
    before: Mapping[str, str | None],
    after: Mapping[str, str | None],
    tmp_path: Path,
    *,
    detect_renames: bool = False,
) -> str:
    repo = tmp_path / f"gen-{uuid4().hex}"
    repo.mkdir()
    _run(["init", "-q"], cwd=repo)
    _run(["config", "user.name", "test"], cwd=repo)
    _run(["config", "user.email", "test@example.com"], cwd=repo)

    for path, content in before.items():
        if content is None:
            continue
        full = repo / path
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(content)
    _run(["add", "-A"], cwd=repo)
    _run(["commit", "--allow-empty", "-q", "-m", "before"], cwd=repo)

    # A path present in `before` but absent from `after` is a deletion (not
    # merely "unspecified, so leave it alone") -- this is what makes the
    # rename fixture work: `old.py` in `before` only + `new.py` in `after`
    # only becomes a delete+add pair, which `-M` then detects as a rename.
    for path in before:
        if path not in after and (repo / path).exists():
            (repo / path).unlink()
    for path, content in after.items():
        full = repo / path
        if content is None:
            if full.exists():
                full.unlink()
        else:
            full.parent.mkdir(parents=True, exist_ok=True)
            full.write_text(content)
    _run(["add", "-A"], cwd=repo)

    diff_args = ["diff", "--cached", "--no-color"]
    if detect_renames:
        diff_args.append("-M")
    return _stdout(_run(diff_args, cwd=repo))


def _write_crlf(repo: Path, path: str, lines: list[str]) -> None:
    (repo / path).write_bytes(b"\r\n".join(line.encode() for line in lines) + b"\r\n")


def test_apply_modify_single_hunk(tmp_path: Path) -> None:
    before = {"foo.py": "line1\nline2\nline3\n"}
    after = {"foo.py": "line1\nline2-changed\nline3\n"}
    diff = _git_diff_between(before, after, tmp_path)

    applied = _apply(diff, before)

    assert applied == [AppliedFile(path="foo.py", content=after["foo.py"])]


def test_apply_modify_multiple_hunks(tmp_path: Path) -> None:
    before_lines = [f"line{i}" for i in range(1, 21)]
    after_lines = list(before_lines)
    after_lines[0] = "line1-CHANGED"
    after_lines[-1] = "line20-CHANGED"
    before = {"f.txt": "\n".join(before_lines) + "\n"}
    after = {"f.txt": "\n".join(after_lines) + "\n"}
    diff = _git_diff_between(before, after, tmp_path)
    assert diff.count("@@") == 4  # 2 hunks, each with an opening "@@ ... @@"

    applied = _apply(diff, before)

    assert applied == [AppliedFile(path="f.txt", content=after["f.txt"])]


def test_apply_add_new_file(tmp_path: Path) -> None:
    before: dict[str, str | None] = {}
    after = {"new_file.py": "print('hello')\n"}
    diff = _git_diff_between(before, after, tmp_path)

    applied = _apply(diff, {"new_file.py": None})

    assert applied == [AppliedFile(path="new_file.py", content=after["new_file.py"])]


def test_apply_delete_file(tmp_path: Path) -> None:
    before = {"gone.py": "content\n"}
    after: dict[str, str | None] = {"gone.py": None}
    diff = _git_diff_between(before, after, tmp_path)

    applied = _apply(diff, before)

    assert applied == [AppliedFile(path="gone.py", content=None)]


def test_apply_rename_surfaces_as_delete_and_add(tmp_path: Path) -> None:
    before = {"old.py": "line1\nline2\nline3\nline4\nline5\n"}
    after = {"new.py": "line1\nline2-changed\nline3\nline4\nline5\n"}
    diff = _git_diff_between(before, after, tmp_path, detect_renames=True)
    assert "rename from" in diff

    applied = _apply(diff, before)

    assert AppliedFile(path="old.py", content=None) in applied
    assert AppliedFile(path="new.py", content=after["new.py"]) in applied
    assert len(applied) == 2


def test_apply_preserves_missing_trailing_newline(tmp_path: Path) -> None:
    before = {"noeof.txt": "line1\nnoeof"}
    after = {"noeof.txt": "line1\nnoeof-changed"}
    diff = _git_diff_between(before, after, tmp_path)
    assert "\\ No newline at end of file" in diff

    applied = _apply(diff, before)

    assert applied == [AppliedFile(path="noeof.txt", content=after["noeof.txt"])]


def test_apply_multi_file_diff(tmp_path: Path) -> None:
    before = {"a.py": "a-before\n", "b.py": "b-before\n"}
    after = {"a.py": "a-after\n", "b.py": "b-after\n"}
    diff = _git_diff_between(before, after, tmp_path)

    applied = _apply(diff, before)

    assert sorted(applied, key=lambda f: f.path) == [
        AppliedFile(path="a.py", content="a-after\n"),
        AppliedFile(path="b.py", content="b-after\n"),
    ]


def test_apply_crlf_content_passes_through(tmp_path: Path) -> None:
    repo = tmp_path / f"crlf-{uuid4().hex}"
    repo.mkdir()
    _run(["init", "-q"], cwd=repo)
    _run(["config", "user.name", "test"], cwd=repo)
    _run(["config", "user.email", "test@example.com"], cwd=repo)
    _run(["config", "core.autocrlf", "false"], cwd=repo)
    _write_crlf(repo, "crlf.txt", ["line1", "line2", "line3"])
    _run(["add", "-A"], cwd=repo)
    _run(["commit", "-q", "-m", "before"], cwd=repo)
    before_content = (repo / "crlf.txt").read_bytes().decode("utf-8")

    _write_crlf(repo, "crlf.txt", ["line1", "line2-changed", "line3"])
    _run(["add", "-A"], cwd=repo)
    diff = _stdout(_run(["diff", "--cached", "--no-color"], cwd=repo))

    applied = _apply(diff, {"crlf.txt": before_content})

    assert applied[0].content is not None
    assert "\r\n" in applied[0].content
    assert "line2-changed\r\n" in applied[0].content


def test_apply_raises_on_empty_diff() -> None:
    with pytest.raises(DiffApplyError, match="empty diff"):
        _apply("", {})


def test_apply_raises_on_malformed_diff() -> None:
    with pytest.raises(DiffApplyError):
        _apply("this is not a diff at all\njust text\n", {})


def test_apply_raises_on_context_mismatch(tmp_path: Path) -> None:
    """The diff was generated against one base; we hand `apply` a
    different base -- git must refuse rather than fuzzily reconcile."""
    before = {"foo.py": "line1\nline2\nline3\n"}
    after = {"foo.py": "line1\nline2-changed\nline3\n"}
    diff = _git_diff_between(before, after, tmp_path)

    wrong_base = {"foo.py": "totally-different\ncontent\nhere\n"}

    with pytest.raises(DiffApplyError):
        _apply(diff, wrong_base)


def test_apply_raises_when_diff_touches_a_path_not_in_base_files(tmp_path: Path) -> None:
    before = {"foo.py": "line1\nline2\nline3\n"}
    after = {"foo.py": "line1\nline2-changed\nline3\n"}
    diff = _git_diff_between(before, after, tmp_path)

    with pytest.raises(DiffApplyError):
        _apply(diff, {})


def test_apply_raises_on_path_escape_attempt() -> None:
    evil_diff = (
        "--- a/../../../../tmp/evil_out.txt\n"
        "+++ b/../../../../tmp/evil_out.txt\n"
        "@@ -0,0 +1 @@\n"
        "+pwned\n"
    )
    with pytest.raises(DiffApplyError):
        _apply(evil_diff, {})


def test_apply_raises_on_non_utf8_binary_result(tmp_path: Path) -> None:
    repo = tmp_path / f"binary-{uuid4().hex}"
    repo.mkdir()
    _run(["init", "-q"], cwd=repo)
    _run(["config", "user.name", "test"], cwd=repo)
    _run(["config", "user.email", "test@example.com"], cwd=repo)
    _run(["commit", "--allow-empty", "-q", "-m", "base"], cwd=repo)
    (repo / "blob.bin").write_bytes(b"\x00\xff\xfe\xfd")
    _run(["add", "-A"], cwd=repo)
    diff = _stdout(_run(["diff", "--cached", "--no-color", "--binary"], cwd=repo))
    assert "GIT binary patch" in diff

    with pytest.raises(DiffApplyError, match="UTF-8"):
        _apply(diff, {"blob.bin": None})


def test_apply_wraps_subprocess_timeout_as_diff_apply_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import subprocess as subprocess_module

    def _fake_run(*_args: object, **_kwargs: object) -> subprocess_module.CompletedProcess[str]:
        raise subprocess_module.TimeoutExpired(cmd=["git"], timeout=1)

    monkeypatch.setattr(subprocess_module, "run", _fake_run)
    with pytest.raises(DiffApplyError, match="timed out"):
        _apply("--- a/x\n+++ b/x\n@@ -1 +1 @@\n-a\n+b\n", {"x": "a\n"})


def test_apply_respects_custom_timeout_seconds() -> None:
    applier = DiffApplier(timeout_seconds=0.000001)

    with pytest.raises(DiffApplyError, match="timed out"):
        applier.apply("--- a/x\n+++ b/x\n@@ -1 +1 @@\n-a\n+b\n", {"x": "a\n"})
