"""Unit tests for tools/setup/check_beads_reopen.py (bead 78ld).

The property under test: a PR must never carry a ``.beads/issues.jsonl`` row
that would move a bead closed on main back to a non-closed status, unless the
reopen is explicitly marked. The checker must also *not* fire on rows the PR
never touched -- a branch cut before a closure carries the stale row, but a
3-way merge keeps main's closed row, so flagging it would be a false positive.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
_SPEC = importlib.util.spec_from_file_location(
    "check_beads_reopen", REPO_ROOT / "tools" / "setup" / "check_beads_reopen.py"
)
assert _SPEC and _SPEC.loader
cbr = importlib.util.module_from_spec(_SPEC)
sys.modules["check_beads_reopen"] = cbr
_SPEC.loader.exec_module(cbr)


def _row(bead_id: str, status: str, **extra: object) -> dict[str, object]:
    row: dict[str, object] = {"_type": "issue", "id": bead_id, "title": f"t-{bead_id}"}
    row["status"] = status
    row.update(extra)
    return row


def _jsonl(*rows: dict[str, object]) -> str:
    return "".join(json.dumps(r) + "\n" for r in rows)


# ---------------------------------------------------------------- parsing


def test_parse_jsonl_keys_rows_by_id() -> None:
    """Parse jsonl keys rows by id."""
    rows = cbr.parse_jsonl(_jsonl(_row("a", "open"), _row("b", "closed")), "x")
    assert set(rows) == {"a", "b"}
    assert rows["b"]["status"] == "closed"


def test_parse_jsonl_skips_blank_lines() -> None:
    """Parse jsonl skips blank lines."""
    rows = cbr.parse_jsonl("\n" + _jsonl(_row("a", "open")) + "\n\n", "x")
    assert list(rows) == ["a"]


def test_parse_jsonl_rejects_garbage_with_source_and_line() -> None:
    """Parse jsonl rejects garbage with source and line."""
    with pytest.raises(ValueError, match=r"src:2"):
        cbr.parse_jsonl(_jsonl(_row("a", "open")) + "{not json\n", "src")


def test_parse_jsonl_rejects_row_without_id() -> None:
    """Parse jsonl rejects row without id."""
    with pytest.raises(ValueError, match="id"):
        cbr.parse_jsonl('{"status": "open"}\n', "src")


def test_parse_jsonl_ignores_non_issue_records() -> None:
    """Parse jsonl ignores non issue records."""
    text = _jsonl(_row("a", "open"), {"_type": "memory", "key": "k", "value": "v"})
    assert list(cbr.parse_jsonl(text, "x")) == ["a"]


# ---------------------------------------------------------------- marker


def test_marker_line_in_notes_is_counted_case_insensitively() -> None:
    """A line starting `beads-reopen-ok:` counts, in any case."""
    assert cbr.count_reopen_markers(_row("a", "open", notes="x\nBEADS-REOPEN-OK: regressed")) == 1


def test_marker_line_in_a_comment_is_counted() -> None:
    """A comment starting with the marker counts."""
    row = _row("a", "open", comments=[{"text": "beads-reopen-ok: fix reverted"}])
    assert cbr.count_reopen_markers(row) == 1


def test_marker_mentioned_in_prose_is_not_counted() -> None:
    """Regression 2026-10-06: 78ld's own notes DESCRIBED the escape hatch.

    "escape hatch 'beads-reopen-ok' in notes/comments" sat mid-line in the
    bead's notes, matched the old substring test, and exempted the bead from
    the guard -- so a checkout silently reopened it.
    """
    row = _row("a", "open", notes="CI gate; escape hatch 'beads-reopen-ok' in notes/comments.")
    assert cbr.count_reopen_markers(row) == 0


def test_no_marker() -> None:
    """No marker."""
    assert cbr.count_reopen_markers(_row("a", "open", notes="reopen it please")) == 0


def test_marker_already_on_base_is_not_new() -> None:
    """An old marker line carried over from the base does not license a new reopen."""
    base = _row("a", "closed", notes="beads-reopen-ok: an older reopen")
    head = _row("a", "open", notes="beads-reopen-ok: an older reopen")
    assert not cbr.has_new_reopen_marker(base, head)


def test_marker_added_on_head_is_new() -> None:
    """A marker line the head added on top of the base's notes is new."""
    base = _row("a", "closed", notes="history")
    head = _row("a", "open", notes="history\nbeads-reopen-ok: fix reverted in #300")
    assert cbr.has_new_reopen_marker(base, head)


# ---------------------------------------------------------------- core rule


def test_closed_on_base_open_on_head_is_flagged() -> None:
    """Closed on base open on head is flagged."""
    base = {"a": _row("a", "closed")}
    head = {"a": _row("a", "in_progress")}
    bad, allowed = cbr.find_reopened(base, head)
    assert [r.bead_id for r in bad] == ["a"]
    assert bad[0].base_status == "closed" and bad[0].head_status == "in_progress"
    assert not allowed


def test_still_closed_is_clean() -> None:
    """Still closed is clean."""
    bad, _ = cbr.find_reopened({"a": _row("a", "closed")}, {"a": _row("a", "closed")})
    assert not bad


def test_open_on_base_is_not_this_checks_business() -> None:
    """Open on base is not this checks business."""
    bad, _ = cbr.find_reopened({"a": _row("a", "open")}, {"a": _row("a", "closed")})
    assert not bad


def test_bead_absent_from_head_is_not_a_reopen() -> None:
    """Bead absent from head is not a reopen."""
    bad, _ = cbr.find_reopened({"a": _row("a", "closed")}, {})
    assert not bad


def test_new_bead_on_head_is_clean() -> None:
    """New bead on head is clean."""
    bad, _ = cbr.find_reopened({}, {"n": _row("n", "open")})
    assert not bad


def test_marked_reopen_is_allowed_not_flagged() -> None:
    """Marked reopen is allowed not flagged."""
    base = {"a": _row("a", "closed")}
    head = {"a": _row("a", "open", notes="beads-reopen-ok: fix was reverted in #300")}
    bad, allowed = cbr.find_reopened(base, head)
    assert not bad
    assert [r.bead_id for r in allowed] == ["a"]


def test_reopen_of_bead_whose_notes_mention_the_marker_is_flagged() -> None:
    """The 78ld shape: notes discuss the marker, the reopen is accidental."""
    notes = "escape hatch 'beads-reopen-ok' in notes/comments"
    base = {"a": _row("a", "closed", notes=notes)}
    head = {"a": _row("a", "in_progress", notes=notes)}
    bad, allowed = cbr.find_reopened(base, head)
    assert [r.bead_id for r in bad] == ["a"]
    assert not allowed


def test_row_untouched_since_merge_base_is_not_flagged() -> None:
    """Branch cut before the closure: stale row, but 3-way merge keeps main's."""
    stale = _row("a", "in_progress", updated_at="2026-10-01T00:00:00Z")
    base = {"a": _row("a", "closed", updated_at="2026-10-02T00:00:00Z")}
    bad, _ = cbr.find_reopened(base, {"a": dict(stale)}, merge_base={"a": dict(stale)})
    assert not bad


def test_row_changed_since_merge_base_is_flagged() -> None:
    """The PR rewrote the row, so the merge would carry the reopen into main."""
    merge_base = {"a": _row("a", "closed")}
    base = {"a": _row("a", "closed")}
    head = {"a": _row("a", "in_progress")}
    bad, _ = cbr.find_reopened(base, head, merge_base=merge_base)
    assert [r.bead_id for r in bad] == ["a"]


def test_results_are_sorted_by_id() -> None:
    """Results are sorted by id."""
    base = {k: _row(k, "closed") for k in ("c", "a", "b")}
    head = {k: _row(k, "open") for k in ("c", "a", "b")}
    bad, _ = cbr.find_reopened(base, head)
    assert [r.bead_id for r in bad] == ["a", "b", "c"]


# ---------------------------------------------------------------- CLI (files)


def _write(path: Path, *rows: dict[str, object]) -> Path:
    path.write_text(_jsonl(*rows), encoding="utf-8")
    return path


def test_main_exit_0_when_clean(tmp_path: Path) -> None:
    """Main exit 0 when clean."""
    base = _write(tmp_path / "base.jsonl", _row("a", "closed"))
    head = _write(tmp_path / "head.jsonl", _row("a", "closed"))
    assert cbr.main(["--base-file", str(base), "--head-file", str(head)]) == 0


def test_main_exit_1_on_reopen_and_names_the_bead(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Main exit 1 on reopen and names the bead."""
    base = _write(tmp_path / "base.jsonl", _row("zz-1", "closed"))
    head = _write(tmp_path / "head.jsonl", _row("zz-1", "open"))
    assert cbr.main(["--base-file", str(base), "--head-file", str(head)]) == 1
    out = capsys.readouterr().out
    assert "zz-1" in out and cbr.REOPEN_MARKER in out


def test_main_exit_2_on_unparsable_input(tmp_path: Path) -> None:
    """Main exit 2 on unparsable input."""
    base = tmp_path / "base.jsonl"
    base.write_text("{oops\n", encoding="utf-8")
    head = _write(tmp_path / "head.jsonl", _row("a", "open"))
    assert cbr.main(["--base-file", str(base), "--head-file", str(head)]) == 2


def test_main_exit_2_on_missing_file(tmp_path: Path) -> None:
    """Main exit 2 on missing file."""
    head = _write(tmp_path / "head.jsonl", _row("a", "open"))
    missing = str(tmp_path / "nope.jsonl")
    assert cbr.main(["--base-file", missing, "--head-file", str(head)]) == 2


def test_main_merge_base_file_suppresses_untouched_stale_row(tmp_path: Path) -> None:
    """Main merge base file suppresses untouched stale row."""
    base = _write(tmp_path / "base.jsonl", _row("a", "closed"))
    head = _write(tmp_path / "head.jsonl", _row("a", "open"))
    mb = _write(tmp_path / "mb.jsonl", _row("a", "open"))
    argv = ["--base-file", str(base), "--head-file", str(head), "--merge-base-file", str(mb)]
    assert cbr.main(argv) == 0


# ---------------------------------------------------------------- CLI (git refs)


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


@pytest.fixture(name="repo")
def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "r"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "t@example.com")
    _git(repo, "config", "user.name", "t")
    (repo / ".beads").mkdir()
    return repo


def _commit(repo: Path, msg: str, *rows: dict[str, object]) -> None:
    _write(repo / ".beads" / "issues.jsonl", *rows)
    _git(repo, "add", ".beads/issues.jsonl")
    _git(repo, "commit", "-q", "-m", msg)


def test_refs_mode_flags_branch_that_reopens_a_closed_bead(repo: Path) -> None:
    """Refs mode flags branch that reopens a closed bead."""
    _commit(repo, "base", _row("a", "closed"))
    _git(repo, "checkout", "-q", "-b", "pr")
    _commit(repo, "reopen", _row("a", "in_progress"))
    argv = ["--repo", str(repo), "--base-ref", "main", "--head-ref", "pr"]
    assert cbr.main(argv) == 1


def test_refs_mode_ignores_stale_branch_that_never_touched_the_row(repo: Path) -> None:
    """Repro-#1 shape *without* corruption: branch cut before main closed `a`."""
    _commit(repo, "base", _row("a", "in_progress"))
    _git(repo, "checkout", "-q", "-b", "pr")
    (repo / "f.txt").write_text("x", encoding="utf-8")
    _git(repo, "add", "f.txt")
    _git(repo, "commit", "-q", "-m", "unrelated")
    _git(repo, "checkout", "-q", "main")
    _commit(repo, "close a", _row("a", "closed"))
    argv = ["--repo", str(repo), "--base-ref", "main", "--head-ref", "pr"]
    assert cbr.main(argv) == 0


def test_refs_mode_base_without_the_file_is_clean(repo: Path) -> None:
    """Refs mode base without the file is clean."""
    (repo / "f.txt").write_text("x", encoding="utf-8")
    _git(repo, "add", "f.txt")
    _git(repo, "commit", "-q", "-m", "no beads yet")
    _git(repo, "checkout", "-q", "-b", "pr")
    _commit(repo, "add", _row("a", "open"))
    argv = ["--repo", str(repo), "--base-ref", "main", "--head-ref", "pr"]
    assert cbr.main(argv) == 0


def test_refs_mode_bad_ref_is_exit_2(repo: Path) -> None:
    """Refs mode bad ref is exit 2."""
    _commit(repo, "base", _row("a", "closed"))
    argv = ["--repo", str(repo), "--base-ref", "no-such-ref", "--head-ref", "main"]
    assert cbr.main(argv) == 2
