#!/usr/bin/env python3
"""Fail if a branch's .beads/issues.jsonl would reopen a bead that main has closed.

Why this exists (bead 78ld)
---------------------------
The Dolt DB is the authoritative bead store; ``.beads/issues.jsonl`` is a
derived export that every commit regenerates. beads' post-checkout and
post-merge hooks run ``bd import`` on whatever jsonl the new HEAD carries, and
that import overwrites DB rows wholesale. Checking out a branch (or a stale
local main) whose jsonl is older than the DB therefore silently reverts closed
beads to open and drops notes added after the last commit -- and because every
later commit re-exports the DB, the branch then carries the regression into its
PR. Observed six times by 2026-10-06; see bead 78ld for three repros.

Layer 2 of the hazard, the merge itself, is fixed by the b1o merge driver
(tools/setup/beads_merge_driver.sh). Layer 1, the checkout import, is guarded
locally by tools/setup/beads_checkout_guard.py. This script is the backstop
that a local setup can never be: it runs in CI on every PR, so an unguarded
clone still cannot land a resurrected bead.

What it checks
--------------
For every bead that is ``closed`` on the base (main) and present with a
non-closed status on the head, it reports a violation -- unless:

  * the head row is identical to the merge-base row: the PR never touched it,
    so a 3-way merge keeps main's closed row. (This is a branch cut before the
    closure; harmless, and flagging it would fire on most long-lived PRs.)
  * the head row carries the reopen marker ``beads-reopen-ok`` (any case) in its
    notes or in a comment. That is the escape hatch for a deliberate reopen,
    e.g. ``bd update <id> --append-notes "beads-reopen-ok: fix reverted in #N"``.

In CI the job checks out GitHub's PR merge commit, so ``--base-ref HEAD^1
--head-ref HEAD`` compares "main after this PR" against "main now", and the
merge-base is the base itself.

Usage
-----
    python3 tools/setup/check_beads_reopen.py                     # HEAD vs origin/main
    python3 tools/setup/check_beads_reopen.py --base-ref HEAD^1 --head-ref HEAD
    python3 tools/setup/check_beads_reopen.py --base-file a.jsonl --head-file b.jsonl

Exit codes: 0 = clean, 1 = at least one unmarked reopen, 2 = input error.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

CLOSED = "closed"
REOPEN_MARKER = "beads-reopen-ok"
JSONL_PATH = ".beads/issues.jsonl"

Row = dict[str, object]
Rows = dict[str, Row]


@dataclass(frozen=True)
class Reopen:
    """One bead closed on the base and non-closed on the head."""

    bead_id: str
    base_status: str
    head_status: str
    title: str


def parse_jsonl(text: str, source: str) -> Rows:
    """Parse a beads export into ``{id: row}``. Non-issue records are skipped.

    Raises ValueError naming ``source:line`` on malformed input: a gate that
    silently skipped a garbled line could report clean on exactly the row that
    matters.
    """
    rows: Rows = {}
    for lineno, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{source}:{lineno}: not valid JSON ({exc.msg})") from exc
        if not isinstance(obj, dict):
            raise ValueError(f"{source}:{lineno}: expected a JSON object")
        if obj.get("_type", "issue") != "issue":
            continue
        bead_id = obj.get("id")
        if not isinstance(bead_id, str) or not bead_id:
            raise ValueError(f"{source}:{lineno}: row has no string 'id'")
        rows[bead_id] = obj
    return rows


def has_reopen_marker(row: Row) -> bool:
    """True when the row's notes or any comment text carries REOPEN_MARKER."""
    texts = [str(row.get("notes") or "")]
    comments = row.get("comments")
    if isinstance(comments, list):
        texts.extend(str(c.get("text", "")) for c in comments if isinstance(c, dict))
    return any(REOPEN_MARKER in t.lower() for t in texts)


def find_reopened(
    base: Rows, head: Rows, merge_base: Rows | None = None
) -> tuple[list[Reopen], list[Reopen]]:
    """Return ``(violations, allowed)``, each sorted by bead id.

    ``allowed`` holds reopens that carry the marker, so the caller can still
    report them. A row identical to its merge-base row is skipped entirely.
    """
    violations: list[Reopen] = []
    allowed: list[Reopen] = []
    for bead_id in sorted(base):
        base_status = str(base[bead_id].get("status", ""))
        head_row = head.get(bead_id)
        if base_status != CLOSED or head_row is None:
            continue
        head_status = str(head_row.get("status", ""))
        if head_status == CLOSED:
            continue
        if merge_base is not None and merge_base.get(bead_id) == head_row:
            continue
        hit = Reopen(bead_id, base_status, head_status, str(head_row.get("title", "")))
        (allowed if has_reopen_marker(head_row) else violations).append(hit)
    return violations, allowed


# ---------------------------------------------------------------- input


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=False
    )


def _rows_at_ref(repo: Path, ref: str, path: str) -> Rows:
    """Rows of ``path`` at ``ref``; a ref without the file yields no rows."""
    if _git(repo, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}").returncode != 0:
        raise ValueError(f"not a commit: {ref!r}")
    shown = _git(repo, "show", f"{ref}:{path}")
    if shown.returncode != 0:
        return {}
    return parse_jsonl(shown.stdout, f"{ref}:{path}")


def _rows_from_file(path: str) -> Rows:
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"cannot read {path}: {exc.strerror}") from exc
    return parse_jsonl(text, path)


def _load(args: argparse.Namespace) -> tuple[Rows, Rows, Rows | None]:
    repo = Path(args.repo)
    base = (
        _rows_from_file(args.base_file)
        if args.base_file
        else _rows_at_ref(repo, args.base_ref, args.path)
    )
    if args.head_file:
        head = _rows_from_file(args.head_file)
    elif args.head_ref:
        head = _rows_at_ref(repo, args.head_ref, args.path)
    else:
        head = _rows_from_file(str(repo / args.path))

    merge_base: Rows | None = None
    if args.merge_base_file:
        merge_base = _rows_from_file(args.merge_base_file)
    elif not args.base_file and not args.head_file:
        mb = _git(repo, "merge-base", args.base_ref, args.head_ref or "HEAD")
        if mb.returncode == 0:
            merge_base = _rows_at_ref(repo, mb.stdout.strip(), args.path)
        else:
            print("note: no merge-base found (shallow clone?); comparing base and head only")
    return base, head, merge_base


# ---------------------------------------------------------------- CLI


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    p.add_argument("--repo", default=".", help="git repository (default: cwd)")
    p.add_argument("--path", default=JSONL_PATH, help=f"export path (default: {JSONL_PATH})")
    p.add_argument("--base-ref", default="origin/main", help="base ref (default: origin/main)")
    p.add_argument("--head-ref", default="", help="head ref (default: the working-tree file)")
    p.add_argument("--base-file", default="", help="read the base export from a file")
    p.add_argument("--head-file", default="", help="read the head export from a file")
    p.add_argument("--merge-base-file", default="", help="read the merge-base export from a file")
    return p


def main(argv: list[str] | None = None) -> int:
    """Entry point; see the module docstring for exit codes."""
    args = _build_parser().parse_args(argv)
    try:
        base, head, merge_base = _load(args)
    except ValueError as exc:
        print(f"ERROR: {exc}")
        return 2

    violations, allowed = find_reopened(base, head, merge_base)
    for r in allowed:
        print(f"allowed (marked {REOPEN_MARKER}): {r.bead_id} {r.base_status} -> {r.head_status}")
    if not violations:
        print(f"OK: no bead closed on the base is reopened ({len(base)} base rows checked)")
        return 0

    print(f"FAIL: {len(violations)} bead(s) closed on the base would be reopened:")
    for r in violations:
        print(f"  {r.bead_id}: {r.base_status} -> {r.head_status}  ({r.title})")
    print(
        "\nThis is the bead-78ld hazard: a checkout imported an older issues.jsonl into\n"
        "the Dolt DB and later commits exported the reverted state. To fix, re-close\n"
        "each bead (bd close <id> --reason ...) and commit the export. If the reopen\n"
        f"is deliberate, add a note containing '{REOPEN_MARKER}', e.g.\n"
        f'  bd update <id> --append-notes "{REOPEN_MARKER}: <why>"\n'
        "See the Beads section of CLAUDE.md."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
