#!/usr/bin/env python3
"""Pin-coordinate lock for a hard macro (bead lu09).

A macro re-harden that merely appends a pin must not move the existing ones: the SoC routes to the
committed LEF pin positions, and LibreLane's ``Odb.CustomIOPlacement`` re-spaces a whole edge when its
pin count changes (j41m.4 / PR #287: 6 appended N-edge pins moved all 95 existing ones, up to 214 um).

The lock is a *template DEF* derived from the committed LEF and handed to LibreLane as ``FP_DEF_TEMPLATE``
(``FP_TEMPLATE_MATCH_MODE: strict``). ``Odb.ApplyDEFTemplate`` runs after ``Odb.CustomIOPlacement``,
overwrites every pin shape with the template's, and in strict mode exits ``EX_DATAERR`` when the design and
the template pin sets differ in either direction. A new pin therefore cannot be added without a template
edit, and this script checks that edit against the committed LEF. LibreLane itself does NOT check that two
template pins overlap, so ``check`` does.

Subcommands
-----------
gen   LEF OUT.def              Derive the template DEF from a macro LEF (signal pins only, no power).
check --lef LEF --def DEF      Exit 1 if the template omits, or moves, any signal pin of the committed LEF,
                               or if two template pins on one layer overlap / sit closer than --min-space.
                               Template pins absent from the LEF are "pending" (reported, not an error):
                               that is the state of a PR that adds a pin before the re-harden.
      [--new-lef NEW.lef]      Also exit 1 if a fresh harden's LEF (or a LEF-like dump from
                               ``odb_pins_to_lef.py``) moved or dropped any pin of LEF. Added pins are
      [--odb-lef ODB.lef]      reported, never an error.

Stdlib only.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lef_pin_diff import parse_pins  # noqa: E402  (sibling script, shares one LEF parser)

DBU_PER_UM = 1000  # sky130A; LEF carries 3 decimals so this is exact
Rect = tuple[str, int, int, int, int]  # layer, llx, lly, urx, ury in DBU


def _dbu(v: float) -> int:
    return int(round(v * DBU_PER_UM))


def macro_info(lef: Path) -> tuple[str, float, float, dict[str, str]]:
    """Return (macro name, width um, height um, {signal pin: DIRECTION}) for a LEF."""
    text = lef.read_text(encoding="utf-8", errors="replace")
    m = re.search(r"^MACRO\s+(\S+)", text, re.M)
    s = re.search(r"^\s*SIZE\s+([\d.]+)\s+BY\s+([\d.]+)", text, re.M)
    if not m or not s:
        raise SystemExit(f"{lef}: no MACRO/SIZE found")
    dirs: dict[str, str] = {}
    for pm in re.finditer(r"^\s*PIN\s+(\S+)(.*?)^\s*END\s+\1(?!\S)", text, re.M | re.S):
        body = pm.group(2)
        use = re.search(r"USE\s+(\w+)", body)
        if use and use.group(1) in ("POWER", "GROUND"):
            continue
        d = re.search(r"DIRECTION\s+(INPUT|OUTPUT|INOUT)", body)
        dirs[pm.group(1)] = d.group(1) if d else "INOUT"
    return m.group(1), float(s.group(1)), float(s.group(2)), dirs


def lef_rects(lef: Path) -> dict[str, list[Rect]]:
    """{pin: sorted [(layer, llx, lly, urx, ury) in DBU]} for every pin of a LEF."""
    pins, _ = parse_pins(str(lef), None)
    return {
        p: sorted((ly, _dbu(a), _dbu(b), _dbu(c), _dbu(d)) for ly, a, b, c, d in r)
        for p, r in pins.items()
    }


def gen_def(lef: Path) -> str:
    """Deterministic template DEF text for the signal pins of ``lef`` (sorted by pin name)."""
    name, w, h, dirs = macro_info(lef)
    rects = lef_rects(lef)
    sig = sorted(dirs)
    out = [
        "VERSION 5.8 ;",
        'DIVIDERCHAR "/" ;',
        'BUSBITCHARS "[]" ;',
        f"DESIGN {name} ;",
        f"UNITS DISTANCE MICRONS {DBU_PER_UM} ;",
        f"DIEAREA ( 0 0 ) ( {_dbu(w)} {_dbu(h)} ) ;",
        f"PINS {len(sig)} ;",
    ]
    for p in sig:
        if p not in rects:
            raise SystemExit(f"{lef}: signal pin {p} has no RECT geometry")
        shape = "".join(f" + LAYER {ly} ( {a} {b} ) ( {c} {d} )" for ly, a, b, c, d in rects[p])
        out.append(
            f"- {p} + NET {p} + DIRECTION {dirs[p]} + USE SIGNAL{shape} + PLACED ( 0 0 ) N ;"
        )
    out += ["END PINS", f"NETS {len(sig)} ;"]
    out += [f"- {p} ( PIN {p} ) ;" for p in sig]
    out += ["END NETS", "END DESIGN", ""]
    return "\n".join(out)


def parse_def_pins(path: Path) -> dict[str, list[Rect]]:
    """Absolute DBU rects of every pin in a DEF PINS section (orientation N only)."""
    text = path.read_text(encoding="utf-8")
    sec = re.search(r"^PINS\s+\d+\s*;(.*?)^END PINS", text, re.M | re.S)
    if not sec:
        raise SystemExit(f"{path}: no PINS section")
    pins: dict[str, list[Rect]] = {}
    for stmt in re.split(r";\s*\n", sec.group(1)):
        m = re.match(r"\s*-\s+(\S+)\s", stmt)
        if not m:
            continue
        ox, oy = 0, 0
        pl = re.search(r"\+\s+(?:PLACED|FIXED)\s+\(\s*(-?\d+)\s+(-?\d+)\s*\)\s+(\S+)", stmt)
        if pl:
            ox, oy = int(pl.group(1)), int(pl.group(2))
            if pl.group(3) != "N":
                raise SystemExit(
                    f"{path}: pin {m.group(1)} has orientation {pl.group(3)}; only N is supported"
                )
        rs = [
            (ly, ox + int(a), oy + int(b), ox + int(c), oy + int(d))
            for ly, a, b, c, d in re.findall(
                r"\+\s+LAYER\s+(\S+)\s+\(\s*(-?\d+)\s+(-?\d+)\s*\)\s+\(\s*(-?\d+)\s+(-?\d+)\s*\)",
                stmt,
            )
        ]
        if rs:
            pins[m.group(1)] = sorted(rs)
    return pins


def collisions(pins: dict[str, list[Rect]], min_space_dbu: int) -> list[str]:
    """Pairs of different pins whose same-layer rects overlap or are closer than ``min_space_dbu``."""
    by_layer: dict[str, list[tuple[int, int, int, int, str]]] = {}
    for p, rs in pins.items():
        for ly, a, b, c, d in rs:
            by_layer.setdefault(ly, []).append((a, b, c, d, p))
    out: list[str] = []
    for ly, items in by_layer.items():
        items.sort()
        for i, (a, b, c, d, p) in enumerate(items):
            for a2, b2, c2, d2, p2 in items[i + 1 :]:
                if a2 >= c + min_space_dbu:
                    break  # sorted by llx: nothing further right can touch this rect
                gap_x = max(a2 - c, a - c2)
                gap_y = max(b2 - d, b - d2)
                if p != p2 and max(gap_x, gap_y) < min_space_dbu:
                    out.append(f"{ly}: {p} {(a, b, c, d)} vs {p2} {(a2, b2, c2, d2)}")
    return sorted(out)


def compare(old: Path, new: Path, label: str) -> tuple[list[str], list[str], list[str]]:
    """(moved, removed, added) pin names of ``new`` relative to ``old``, exact coordinates."""
    sig_old = set(macro_info(old)[3])  # signal pins only: an ODB dump has no power pins
    a = {p: r for p, r in lef_rects(old).items() if p in sig_old}
    b = {p: r for p, r in lef_rects(new).items() if p not in ("VPWR", "VGND")}
    common = set(a) & set(b)
    moved = sorted(p for p in common if a[p] != b[p])
    removed = sorted(set(a) - set(b))
    added = sorted(set(b) - set(a))
    print(
        f"[pin-lock] {label}: {len(a)} locked pins, {len(common) - len(moved)} identical, "
        f"{len(moved)} MOVED, {len(removed)} REMOVED, {len(added)} added"
    )
    for p in moved[:20]:
        print(f"[pin-lock]   moved {p}: {a[p]} -> {b[p]}")
    for p in removed[:20]:
        print(f"[pin-lock]   removed {p}")
    for p in added:
        print(f"[pin-lock]   added {p} (not locked)")
    return moved, removed, added


def cmd_check(args: argparse.Namespace) -> int:
    lef, deff = Path(args.lef), Path(args.def_file)
    _, _, _, dirs = macro_info(lef)
    locked = {p: r for p, r in lef_rects(lef).items() if p in dirs}
    tpl = parse_def_pins(deff)
    bad = 0
    missing = sorted(set(locked) - set(tpl))
    moved = sorted(p for p in set(locked) & set(tpl) if locked[p] != tpl[p])
    pending = sorted(set(tpl) - set(locked))
    print(
        f"[pin-lock] template {deff.name}: {len(tpl)} pins; {len(locked)} locked by {lef.name}: "
        f"{len(locked) - len(missing) - len(moved)} identical, {len(moved)} MOVED, {len(missing)} MISSING, "
        f"{len(pending)} pending (in template, not yet in LEF)"
    )
    for p in moved[:20]:
        print(f"[pin-lock]   template moved {p}: LEF {locked[p]} -> template {tpl[p]}")
    for p in missing[:20]:
        print(f"[pin-lock]   template missing {p}")
    for p in pending:
        print(f"[pin-lock]   pending {p}: {tpl[p]}")
    if moved or missing:
        bad += 1
        print("[pin-lock] FAIL: template does not reproduce the committed LEF pin coordinates")
    hits = collisions(tpl, _dbu(args.min_space))
    for h in hits[:20]:
        print(f"[pin-lock]   collision {h}")
    if hits:
        bad += 1
        print(
            f"[pin-lock] FAIL: {len(hits)} template pin pair(s) overlap or violate {args.min_space} um spacing"
        )
    for new in [x for x in (args.new_lef, args.odb_lef) if x]:
        mv, rm, _ = compare(lef, Path(new), str(new))
        if mv or rm:
            bad += 1
            print(f"[pin-lock] FAIL: {new} moved/removed locked pins")
    if not bad:
        print("[pin-lock] OK")
    return 1 if bad else 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("gen", help="write the template DEF derived from a LEF")
    g.add_argument("lef")
    g.add_argument("out")
    c = sub.add_parser(
        "check", help="fail if the template drops/moves a locked pin or pins collide"
    )
    c.add_argument("--lef", required=True)
    c.add_argument("--def", dest="def_file", required=True)
    c.add_argument("--new-lef")
    c.add_argument("--odb-lef")
    c.add_argument(
        "--min-space",
        type=float,
        default=0.14,
        help="min same-layer pin spacing in um (met2/met3 = 0.14)",
    )
    a = ap.parse_args()
    if a.cmd == "gen":
        Path(a.out).write_text(gen_def(Path(a.lef)), encoding="utf-8")
        print(f"[pin-lock] wrote {a.out}")
        return 0
    return cmd_check(a)


if __name__ == "__main__":
    sys.exit(main())
