#!/usr/bin/env python3
"""Source-idiom checker for struct-member selects (bead ainf) - BLOCKING, zero allowed sites.

Rule (docs/development/CODING_GUIDELINES.md, 1.3): never take a bit, part or element select
directly on a struct member, read or write.  Copy the member to a named signal first and select
from that: `logic [W-1:0] w; assign w = s.m;` then `w[hi:lo]`.

Why (docs/SYNLIG_STRUCT_SELECT_AINF.md): the Synlig frontend mis-elaborates
  D1  s.m[hi:lo] / s.m[i]  when the struct TYPE has exactly two members declared with a packed range
  D2  y.m[hi:lo] = v       (LHS part-select of a struct member), for any struct type
  D3  s.m[i]               when m is a multi-dim packed array member (read as ONE BIT)
and the damage can be fully silent (no warning, no x).  sv2v is unaffected.  The defect depends on
the struct type, which silently changes when a member is added, so the rule is unconditional
rather than per-type: a clean tree stays clean whatever the typedefs do.

This checker is a tripwire on the SOURCE idiom; it does not elaborate anything.  It scans every
rtl/**/*.sv for `<expr>.member[...]` and exits 1 on ANY hit.  There is no baseline of allowed sites:
tools/verif/struct_member_select_baseline.txt must stay empty (the checker fails if it is not).
Two-ranged-member struct types (the D1-hot types) are listed with -v for information only.

usage: check_struct_member_select.py [--root DIR] [--baseline FILE] [-v]
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

IDENT = r"[A-Za-z_][A-Za-z0-9_]*"
# base[idx]*.member(.member)*  followed by a bracket select
SITE_RE = re.compile(rf"({IDENT}(?:\[[^\]]*\])*(?:\.{IDENT})+)\s*\[")
LHS_RE = re.compile(
    rf"^\s*(?:assign\s+)?({IDENT}(?:\[[^\]]*\])*(?:\.{IDENT})+)\s*\[[^\]]*\]\s*(?:<=|=(?!=))"
)
TYPEDEF_RE = re.compile(
    r"typedef\s+struct\s*(?:packed)?\s*(?:signed|unsigned)?\s*\{(.*?)\}\s*(\w+)\s*;", re.S
)
RANGED_RE = re.compile(r"^\s*(?:logic|bit|reg)\s*(?:signed\s+|unsigned\s+)?\[[^\]]+\]")


def strip_comments(text: str) -> str:
    """Blank out block and line comments, keeping line numbers."""
    text = re.sub(r"/\*.*?\*/", lambda m: "\n" * m.group(0).count("\n"), text, flags=re.S)
    return re.sub(r"//[^\n]*", "", text)


def ranged_member_count(body: str) -> int:
    """Count struct members declared with an explicit packed range."""
    count = 0
    for decl in body.split(";"):
        if RANGED_RE.match(decl):
            count += 1
    return count


def scan_file(path: Path, root: Path) -> tuple:
    """Scan one file; return (sites, lhs sites, hot type keys)."""
    rel = path.relative_to(root).as_posix()
    text = strip_comments(path.read_text(encoding="utf-8", errors="replace"))
    sites, lhs, hot = [], [], []
    for m in TYPEDEF_RE.finditer(text):
        if ranged_member_count(m.group(1)) == 2:
            hot.append(f"hot-type|{rel}|{m.group(2)}")
    for lineno, line in enumerate(text.splitlines(), 1):
        norm = " ".join(line.split())
        for sm in SITE_RE.finditer(line):
            sites.append((f"site|{rel}|{sm.group(1)}", lineno, norm))
        lm = LHS_RE.match(line)
        if lm:
            lhs.append((f"lhs|{rel}|{lm.group(1)}", lineno, norm))
    return sites, lhs, hot


def collect(root: Path) -> tuple:
    """Scan every rtl/*.sv under root; return (sites, lhs sites, hot types)."""
    sites, lhs, hot = [], [], []
    for path in sorted((root / "rtl").rglob("*.sv")):
        s, lh, h = scan_file(path, root)
        sites += s
        lhs += lh
        hot += [(k, 0, "") for k in h]
    return sites, lhs, hot


def main(argv: list | None = None) -> int:
    """Run the checker; return 0 if clean, 1 on any site or a non-empty baseline."""
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--root", default=".", help="repository root (default: cwd)")
    ap.add_argument("--baseline", default=None, help="baseline file (must contain no entries)")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)
    root = Path(args.root).resolve()
    base_path = (
        Path(args.baseline)
        if args.baseline
        else root / "tools/verif/struct_member_select_baseline.txt"
    )

    sites, lhs, hot = collect(root)
    waived = []
    if base_path.exists():
        waived = [
            ln.strip()
            for ln in base_path.read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.startswith("#")
        ]
    for key, ln, txt in sites:
        print(f"SITE {key}  (line {ln}) {txt}")
    if args.verbose:
        for key, _, _ in hot:
            print(f"INFO {key} (two ranged members; D1-hot if a member select ever appears)")
        print(f"{len(sites)} select sites ({len(lhs)} on an assignment LHS), {len(hot)} R=2 types")
    rc = 0
    if sites:
        print(
            f"FAIL: {len(sites)} select(s) taken directly on a struct member. Synlig "
            "mis-elaborates these (docs/SYNLIG_STRUCT_SELECT_AINF.md): copy the member to a "
            "named signal first and select from that.",
            file=sys.stderr,
        )
        rc = 1
    if waived:
        print(
            f"FAIL: {base_path} lists {len(waived)} allowed site(s); the baseline must stay empty "
            "(rewrite the site instead of waiving it).",
            file=sys.stderr,
        )
        rc = 1
    return rc


if __name__ == "__main__":
    sys.exit(main())
