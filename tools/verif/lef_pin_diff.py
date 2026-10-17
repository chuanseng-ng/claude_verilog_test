#!/usr/bin/env python3
"""Compare the PIN geometry of two LEF abstracts (bead j41m.4).

A macro re-harden that merely adds pins must not move the existing ones: the SoC routes to the
committed pin positions, and the ASAP7 run-22 lesson is that an unpinned boundary reshuffled
393 of 401 pins. This reports, for every pin present in both files, whether its (layer, rect)
set is identical, and lists pins added / removed / moved.

Usage: lef_pin_diff.py OLD.lef NEW.lef [--macro NAME] [--tol 0.0]
Exit 0 iff no common pin moved and none was removed (added pins are reported, not an error).
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict


def parse_pins(path: str, macro: str | None):
    """Return {pin: sorted [(layer, llx, lly, urx, ury), ...]} for one MACRO of a LEF file."""
    text = open(path, encoding="utf-8", errors="replace").read()
    m = re.search(r"^MACRO\s+(\S+)", text, re.M)
    name = macro or (m.group(1) if m else None)
    if name is None:
        raise SystemExit(f"{path}: no MACRO found")
    start = re.search(rf"^MACRO\s+{re.escape(name)}\b", text, re.M)
    end = re.search(rf"^END\s+{re.escape(name)}\b", text, re.M)
    if not start or not end:
        raise SystemExit(f"{path}: MACRO {name} not found")
    body = text[start.end() : end.start()]

    pins: dict[str, list] = defaultdict(list)
    for pm in re.finditer(r"^\s*PIN\s+(\S+)(.*?)^\s*END\s+\1(?!\S)", body, re.M | re.S):
        pname, pbody = pm.group(1), pm.group(2)
        layer = None
        for line in pbody.splitlines():
            line = line.strip().rstrip(";").strip()
            if line.startswith("LAYER"):
                layer = line.split()[1]
            elif line.startswith("RECT") and layer:
                x = [float(v) for v in line.split()[1:5]]
                pins[pname].append((layer, *x))
    return {k: sorted(v) for k, v in pins.items()}, name


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("old")
    ap.add_argument("new")
    ap.add_argument("--macro")
    ap.add_argument("--tol", type=float, default=0.0, help="coordinate tolerance (um)")
    a = ap.parse_args()

    old, n1 = parse_pins(a.old, a.macro)
    new, n2 = parse_pins(a.new, a.macro)
    common = sorted(set(old) & set(new))
    added = sorted(set(new) - set(old))
    removed = sorted(set(old) - set(new))

    def same(p, q):
        if len(p) != len(q):
            return False
        return all(
            x[0] == y[0] and all(abs(u - v) <= a.tol for u, v in zip(x[1:], y[1:], strict=True))
            for x, y in zip(p, q, strict=True)
        )

    moved = [p for p in common if not same(old[p], new[p])]
    print(f"macro {n1} vs {n2}: old {len(old)} pins, new {len(new)} pins")
    print(f"common {len(common)}: identical {len(common) - len(moved)}, MOVED {len(moved)}")
    print(f"added {len(added)}: {', '.join(added)}")
    print(f"removed {len(removed)}: {', '.join(removed)}")
    for p in moved[:40]:
        print(f"  moved {p}: old {old[p]} -> new {new[p]}")
    if len(moved) > 40:
        print(f"  ... {len(moved) - 40} more")
    return 0 if not moved and not removed else 1


if __name__ == "__main__":
    sys.exit(main())
