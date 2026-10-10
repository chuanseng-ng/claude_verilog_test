# ruff: noqa: E501
"""Mechanical site table for the Synlig struct-member select defects (bead ainf).

usage: sitetable.py [repo-root]
Parses every `typedef struct` in rtl/, counts ranged members R, resolves the struct type of the base
of every `<base>.m...[sel]` select (heuristic name->type map from declarations), classifies read/write,
and prints the predicted outcome per docs/SYNLIG_STRUCT_SELECT_AINF.md.
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from check_struct_member_select import (  # noqa: E402
    IDENT,
    LHS_RE,
    RANGED_RE,
    SITE_RE,
    TYPEDEF_RE,
    strip_comments,
)


def parse_types(root: Path) -> dict:
    types: dict = {}
    for p in sorted((root / "rtl").rglob("*.sv")):
        txt = strip_comments(p.read_text(encoding="utf-8", errors="replace"))
        for m in TYPEDEF_RE.finditer(txt):
            members = {}
            r = 0
            for decl in m.group(1).split(";"):
                decl = decl.strip()
                if not decl:
                    continue
                name = re.findall(IDENT, decl)[-1]
                mtype = None if re.match(r"(logic|bit|reg)\b", decl) else decl.split()[0]
                ranged = bool(RANGED_RE.match(decl))
                r += ranged
                members[name] = (mtype, ranged)
            types[m.group(2)] = {"file": p.relative_to(root).as_posix(), "R": r, "members": members}
    return types


def var_types(root: Path, types: dict) -> dict:
    out: dict = {}
    pat = re.compile(
        rf"\b(?:\w+::)?({'|'.join(map(re.escape, types))})\s+(?:(?:input|output|ref)\s+)?({IDENT})"
    )
    for p in sorted((root / "rtl").rglob("*.sv")):
        txt = strip_comments(p.read_text(encoding="utf-8", errors="replace"))
        for m in pat.finditer(txt):
            out[m.group(2)] = m.group(1)
    return out


def predict(rtype: dict, write: bool, bitsel: bool) -> str:
    r = rtype["R"]
    if write:
        return "SILENTLY WRONG (D2)" if not bitsel else ("correct" if r != 2 else "WRONG (D1+D2)")
    return "D1 HOT: wrong" if r == 2 else "correct"


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    types = parse_types(root)
    vtypes = var_types(root, types)
    print("== struct types (R = members declared with a packed range)")
    for n, t in sorted(types.items()):
        flag = (
            "  <-- R=2: D1 HOT"
            if t["R"] == 2
            else ("  (one edit from R=2)" if t["R"] in (1, 3) else "")
        )
        print(f"{n:22s} R={t['R']:2d} members={len(t['members']):2d} {t['file']}{flag}")
    print("== member select sites")
    print("file:line | expr | base var | type | R | rw | prediction")
    for p in sorted((root / "rtl").rglob("*.sv")):
        rel = p.relative_to(root).as_posix()
        txt = strip_comments(p.read_text(encoding="utf-8", errors="replace"))
        for ln, line in enumerate(txt.splitlines(), 1):
            lhs = LHS_RE.match(line)
            for sm in SITE_RE.finditer(line):
                expr = sm.group(1)
                base = re.match(IDENT, expr).group(0)
                t = vtypes.get(base)
                if t is None:
                    print(f"{rel}:{ln} | {expr} | {base} | UNRESOLVED | - | - | check by hand")
                    continue
                # follow nested struct-typed members to the struct that owns the selected member
                owner = types[t]
                for mem in re.findall(rf"\.({IDENT})", expr)[:-1]:
                    nt = owner["members"].get(mem, (None, False))[0]
                    if nt in types:
                        owner = types[nt]
                write = bool(lhs) and lhs.group(1) == expr
                bit = ":" not in line[sm.end() : line.find("]", sm.end())]
                print(
                    f"{rel}:{ln} | {expr} | {base} | {t} | {owner['R']} | "
                    f"{'W' if write else 'R'} | {predict(owner, write, bit)}"
                )
    return 0


if __name__ == "__main__":
    sys.exit(main())
