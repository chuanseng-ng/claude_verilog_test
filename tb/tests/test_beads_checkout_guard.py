"""Unit tests for tools/setup/beads_checkout_guard.py (bead 78ld).

beads' post-checkout / post-merge hook runs ``bd import`` on whatever
``.beads/issues.jsonl`` the new HEAD carries, overwriting the authoritative
Dolt DB wholesale. Measured in a scratch repo (bd 1.0.4): a stale file moves a
closed bead back to open, erases notes added after the last commit, and moves
``updated_at`` *backwards*. The guard diffs a DB export taken before the hook
against one taken after, and re-imports the pre-hook rows of every bead the
import regressed. These tests pin the regression rules and the restore path.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
_SETUP = REPO_ROOT / "tools" / "setup"
sys.path.insert(0, str(_SETUP))
_SPEC = importlib.util.spec_from_file_location(
    "beads_checkout_guard", _SETUP / "beads_checkout_guard.py"
)
assert _SPEC and _SPEC.loader
guard = importlib.util.module_from_spec(_SPEC)
sys.modules["beads_checkout_guard"] = guard
_SPEC.loader.exec_module(guard)

T0 = "2026-10-06T10:00:00Z"
T1 = "2026-10-06T11:00:00Z"


def _row(bead_id: str, status: str = "open", **extra: object) -> dict[str, object]:
    row: dict[str, object] = {"_type": "issue", "id": bead_id, "title": f"t-{bead_id}"}
    row["status"] = status
    row["updated_at"] = T1
    row.update(extra)
    return row


# ---------------------------------------------------------------- rules


def test_identical_exports_have_no_regressions() -> None:
    """Identical exports have no regressions."""
    rows = {"a": _row("a", "closed"), "b": _row("b")}
    assert not guard.find_regressions(rows, {k: dict(v) for k, v in rows.items()})


def test_closed_to_open_is_a_regression() -> None:
    """Closed to open is a regression."""
    before = {"a": _row("a", "closed")}
    after = {"a": _row("a", "in_progress")}
    (reg,) = guard.find_regressions(before, after)
    assert reg.bead_id == "a"
    assert any("closed -> in_progress" in r for r in reg.reasons)


def test_notes_shrinking_is_a_regression() -> None:
    """Notes shrinking is a regression."""
    before = {"a": _row("a", notes="first\nsecond added after the commit")}
    after = {"a": _row("a", notes="first")}
    (reg,) = guard.find_regressions(before, after)
    assert any("notes" in r for r in reg.reasons)


def test_notes_erased_entirely_is_a_regression() -> None:
    """Notes erased entirely is a regression."""
    (reg,) = guard.find_regressions({"a": _row("a", notes="x")}, {"a": _row("a")})
    assert any("notes" in r for r in reg.reasons)


def test_comments_dropping_is_a_regression() -> None:
    """Comments dropping is a regression."""
    before = {"a": _row("a", comments=[{"id": 1}, {"id": 2}], comment_count=2)}
    after = {"a": _row("a", comments=[{"id": 1}], comment_count=1)}
    (reg,) = guard.find_regressions(before, after)
    assert any("comments" in r for r in reg.reasons)


def test_updated_at_moving_backwards_is_a_regression() -> None:
    """Catches any field the import reverted, e.g. a description edit."""
    before = {"a": _row("a", description="new", updated_at=T1)}
    after = {"a": _row("a", description="old", updated_at=T0)}
    (reg,) = guard.find_regressions(before, after)
    assert any("updated_at" in r for r in reg.reasons)


def test_newer_incoming_row_is_accepted() -> None:
    """A genuinely newer row (e.g. from another machine) must pass through."""
    before = {"a": _row("a", "open", updated_at=T0)}
    after = {"a": _row("a", "closed", updated_at=T1, notes="closed elsewhere")}
    assert not guard.find_regressions(before, after)


def test_new_bead_from_import_is_accepted() -> None:
    """New bead from import is accepted."""
    assert not guard.find_regressions({}, {"n": _row("n")})


def test_bead_missing_after_is_not_restored() -> None:
    """bd import is an upsert and cannot delete; nothing to restore."""
    assert not guard.find_regressions({"a": _row("a")}, {})


def test_reopen_marker_never_exempts_a_regression() -> None:
    """Regression 2026-10-06 (78ld itself): the guard must ignore the CI marker.

    78ld's notes described the escape hatch ("escape hatch 'beads-reopen-ok' in
    notes/comments"). The old guard exempted any row whose notes contained the
    marker, so a post-checkout import silently moved 78ld closed -> in_progress
    (Dolt commit 22:10:21, inside the guard's window) and the guard stayed
    quiet. A file-driven reopen is never deliberate in a single-DB setup; the
    escape hatch for the guard is BEADS_CHECKOUT_GUARD=off.
    """
    notes = "FIX: CI gate, escape hatch 'beads-reopen-ok' in notes/comments."
    before = {"a": _row("a", "closed", updated_at=T1, notes=notes)}
    after = {"a": _row("a", "in_progress", updated_at=T0, notes=notes)}
    (reg,) = guard.find_regressions(before, after)
    assert any("closed -> in_progress" in r for r in reg.reasons)


def test_even_a_line_anchored_marker_does_not_exempt_the_guard() -> None:
    """Marker semantics belong to the CI gate only."""
    before = {"a": _row("a", "closed", updated_at=T0)}
    after = {"a": _row("a", "open", updated_at=T1, notes="beads-reopen-ok: reverted")}
    (reg,) = guard.find_regressions(before, after)
    assert any("closed -> open" in r for r in reg.reasons)


def test_regressions_sorted_and_carry_title() -> None:
    """Regressions sorted and carry title."""
    before = {k: _row(k, "closed") for k in ("b", "a")}
    after = {k: _row(k, "open") for k in ("b", "a")}
    regs = guard.find_regressions(before, after)
    assert [r.bead_id for r in regs] == ["a", "b"]
    assert regs[0].title == "t-a"


def test_restore_rows_are_the_pre_hook_rows_only() -> None:
    """Restore rows are the pre hook rows only."""
    before = {"a": _row("a", "closed"), "b": _row("b", "open")}
    after = {"a": _row("a", "open"), "b": _row("b", "open")}
    regs = guard.find_regressions(before, after)
    rows = guard.restore_rows(before, regs)
    assert rows == [before["a"]]


# ---------------------------------------------------------------- CLI


def _write(path: Path, rows: dict[str, dict[str, object]]) -> Path:
    path.write_text("".join(json.dumps(r) + "\n" for r in rows.values()), encoding="utf-8")
    return path


class _FakeBd:  # pylint: disable=too-few-public-methods
    """Records `bd import <file>` invocations instead of touching a real DB."""

    def __init__(self, returncode: int = 0) -> None:
        self.calls: list[list[str]] = []
        self.imported: list[str] = []
        self.returncode = returncode

    def __call__(self, argv: list[str]) -> int:
        self.calls.append(argv)
        self.imported.append(Path(argv[-1]).read_text(encoding="utf-8"))
        return self.returncode


def _args(tmp_path: Path, before: dict, after: dict, *extra: str) -> list[str]:
    b = _write(tmp_path / "before.jsonl", before)
    a = _write(tmp_path / "after.jsonl", after)
    return ["--before", str(b), "--after", str(a), "--hook", "post-checkout", *extra]


def test_main_clean_is_silent_and_does_not_import(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Main clean is silent and does not import."""
    fake = _FakeBd()
    rows = {"a": _row("a", "closed")}
    assert guard.main(_args(tmp_path, rows, rows), run_bd=fake) == 0
    assert not fake.calls
    assert capsys.readouterr().err == ""


def test_main_restore_mode_reimports_only_regressed_rows(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Main restore mode reimports only regressed rows."""
    fake = _FakeBd()
    before = {"a": _row("a", "closed", close_reason="done"), "b": _row("b")}
    after = {"a": _row("a", "open"), "b": _row("b")}
    assert guard.main(_args(tmp_path, before, after), run_bd=fake) == 0
    assert len(fake.calls) == 1 and fake.calls[0][:2] == ["bd", "import"]
    imported = [json.loads(line) for line in fake.imported[0].splitlines()]
    assert imported == [before["a"]]
    err = capsys.readouterr().err
    assert "a" in err and "RESTORED" in err


def test_main_warn_mode_does_not_import_but_prints_recovery_command(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Main warn mode does not import but prints recovery command."""
    fake = _FakeBd()
    before = {"a": _row("a", "closed")}
    after = {"a": _row("a", "open")}
    assert guard.main(_args(tmp_path, before, after, "--mode", "warn"), run_bd=fake) == 0
    assert not fake.calls
    err = capsys.readouterr().err
    assert "bd import" in err and "restore" in err


def test_main_failed_import_is_loud_but_never_blocks(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Main failed import is loud but never blocks."""
    fake = _FakeBd(returncode=1)
    before = {"a": _row("a", "closed")}
    after = {"a": _row("a", "open")}
    assert guard.main(_args(tmp_path, before, after), run_bd=fake) == 0
    err = capsys.readouterr().err
    assert "FAILED" in err and "bd import" in err


def test_main_unreadable_snapshot_never_blocks(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Main unreadable snapshot never blocks."""
    argv = ["--before", str(tmp_path / "missing"), "--after", str(tmp_path / "missing2")]
    assert guard.main(argv, run_bd=_FakeBd()) == 0
    assert "could not" in capsys.readouterr().err
