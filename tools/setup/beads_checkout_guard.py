#!/usr/bin/env python3
"""Undo what beads' checkout/merge import did to beads the DB already had newer.

Why this exists (bead 78ld)
---------------------------
beads 1.0.4's post-checkout hook (on a branch switch) and post-merge hook run
``bd import .beads/issues.jsonl``. That import is an upsert that lets the file
win wholesale. When the checked-out file is older than the Dolt DB -- a stale
local main, or a branch cut before a closure -- it silently:

  * moves a closed bead back to open / in_progress,
  * erases notes added after the last commit,
  * rewinds ``updated_at`` (so any other field edit is reverted too).

All three were reproduced in a scratch repo on 2026-10-06. bd has only an
all-or-nothing knob (``import.auto``) and no "never regress" import mode, so
the guard wraps the hook instead (tools/setup/beads_hook_wrapper.sh):

  1. ``bd export`` the DB to a backup              (before the beads hook)
  2. run the beads hook unchanged                   (its import happens here)
  3. ``bd export`` again and call this script with both snapshots.

This script finds every bead the import regressed and re-imports *that bead's
pre-hook row* -- verified to restore it exactly, ``updated_at`` included. Rows
the import legitimately advanced (newer ``updated_at``) or created are left
alone, so issues arriving from elsewhere still enter the DB.

A regression is any of: status closed -> non-closed; notes shorter; fewer
comments; ``updated_at`` earlier than before. There is deliberately NO
per-bead exemption here. The first version honoured the CI gate's
``beads-reopen-ok`` marker as a substring of the notes. 78ld's own notes
*described* that escape hatch, so on 2026-10-06 a post-checkout import moved
78ld closed -> in_progress (Dolt commit 22:10:21, inside the guard's window)
and the guard stayed silent. With a single authoritative DB, an import that
reopens a bead is never the deliberate path; a deliberate reopen is ``bd
update``. To let a file-driven reopen through, use BEADS_CHECKOUT_GUARD=off.

Modes (``BEADS_CHECKOUT_GUARD`` in the wrapper, ``--mode`` here):
  restore (default) re-import the pre-hook rows and say so loudly
  warn              print the regressions and the exact recovery command only
  off               (wrapper only) skip the guard entirely

Never blocks a checkout: every path exits 0. A guard that could wedge
``git checkout`` would get uninstalled, which is worse than a loud warning.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_beads_reopen import (  # noqa: E402
    CLOSED,
    Row,
    Rows,
    parse_jsonl,
)

BANNER = "=" * 72


@dataclass(frozen=True)
class Regression:
    """One bead whose DB row the import moved backwards."""

    bead_id: str
    title: str
    reasons: tuple[str, ...]


def _timestamp(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _comment_count(row: Row) -> int:
    comments = row.get("comments")
    listed = len(comments) if isinstance(comments, list) else 0
    counted = row.get("comment_count")
    return max(listed, counted if isinstance(counted, int) else 0)


def _reasons(before: Row, after: Row) -> list[str]:
    reasons: list[str] = []
    b_status, a_status = str(before.get("status", "")), str(after.get("status", ""))
    if b_status == CLOSED and a_status != CLOSED:
        reasons.append(f"status {b_status} -> {a_status}")
    b_notes, a_notes = str(before.get("notes") or ""), str(after.get("notes") or "")
    if len(a_notes) < len(b_notes):
        reasons.append(f"notes shrank {len(b_notes)} -> {len(a_notes)} chars")
    b_cc, a_cc = _comment_count(before), _comment_count(after)
    if a_cc < b_cc:
        reasons.append(f"comments dropped {b_cc} -> {a_cc}")
    b_ts, a_ts = _timestamp(before.get("updated_at")), _timestamp(after.get("updated_at"))
    if b_ts and a_ts and a_ts < b_ts:
        reasons.append(
            f"updated_at moved backwards {before['updated_at']} -> {after['updated_at']}"
        )
    return reasons


def find_regressions(before: Rows, after: Rows) -> list[Regression]:
    """Beads present in both snapshots whose post-hook row is older; sorted by id."""
    found: list[Regression] = []
    for bead_id in sorted(before.keys() & after.keys()):
        reasons = _reasons(before[bead_id], after[bead_id])
        if reasons:
            title = str(before[bead_id].get("title", ""))
            found.append(Regression(bead_id, title, tuple(reasons)))
    return found


def restore_rows(before: Rows, regressions: list[Regression]) -> list[Row]:
    """The pre-hook rows to re-import, in regression order."""
    return [before[r.bead_id] for r in regressions]


def _default_run_bd(argv: list[str]) -> int:
    proc = subprocess.run(argv, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        sys.stderr.write(proc.stdout + proc.stderr)
    return proc.returncode


def _report(hook: str, regressions: list[Regression], restore_file: Path, status: str) -> None:
    err = sys.stderr
    print(BANNER, file=err)
    print(f"beads checkout guard (bead 78ld): '{hook}' import regressed", file=err)
    print(f"{len(regressions)} bead(s) the DB already had newer:", file=err)
    for r in regressions:
        print(f"  {r.bead_id}  {r.title[:60]}", file=err)
        for reason in r.reasons:
            print(f"      - {reason}", file=err)
    print(status, file=err)
    print(f"Pre-hook rows: {restore_file}", file=err)
    print(BANNER, file=err)


def main(argv: list[str] | None = None, run_bd: Callable[[list[str]], int] | None = None) -> int:
    """Entry point. Always returns 0 -- see the module docstring."""
    p = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    p.add_argument("--before", required=True, help="bd export taken before the beads hook")
    p.add_argument("--after", required=True, help="bd export taken after the beads hook")
    p.add_argument("--hook", default="post-checkout", help="hook name, for messages")
    p.add_argument("--mode", choices=("restore", "warn"), default="restore")
    p.add_argument("--bd", default="bd", help="bd executable")
    args = p.parse_args(argv)
    runner = run_bd or _default_run_bd

    try:
        before = parse_jsonl(Path(args.before).read_text(encoding="utf-8"), args.before)
        after = parse_jsonl(Path(args.after).read_text(encoding="utf-8"), args.after)
    except (OSError, ValueError) as exc:
        print(
            f"beads checkout guard: could not read snapshots ({exc}); not checked", file=sys.stderr
        )
        return 0

    regressions = find_regressions(before, after)
    if not regressions:
        return 0

    restore_file = Path(args.before).with_suffix(".restore.jsonl")
    restore_file.write_text(
        "".join(
            json.dumps(row, ensure_ascii=False) + "\n" for row in restore_rows(before, regressions)
        ),
        encoding="utf-8",
    )
    recover = f"{args.bd} import {restore_file}"
    if args.mode == "warn":
        status = f"NOT restored (warn mode). To restore them, run:\n  {recover}"
    elif runner([args.bd, "import", str(restore_file)]) == 0:
        status = "RESTORED: the pre-hook rows were re-imported; the DB is back as it was."
    else:
        status = f"Restore FAILED. Recover by hand with:\n  {recover}"
    _report(args.hook, regressions, restore_file, status)
    return 0


if __name__ == "__main__":
    sys.exit(main())
