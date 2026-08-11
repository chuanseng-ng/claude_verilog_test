#!/usr/bin/env python3
"""Generate a LibreLane FP_PIN_ORDER_CFG file from a macro LEF.

Reads a hard-macro LEF's ``PIN`` records, classifies each signal pin by
which boundary edge its first ``RECT`` touches, sorts each edge low->high
along the edge, and emits the ``#N``/``#E``/``#S``/``#W`` sectioned file
that ``librelane/scripts/odbpy/ioplace_parser/parse.py`` expects for
``FP_PIN_ORDER_CFG``.

Classification rule (applied in this order against the first RECT of each
pin's PORT):
    y1 == 0          -> S (south / bottom edge)
    y2 == SIZE_Y      -> N (north / top edge)
    x1 == 0          -> W (west / left edge)
    otherwise         -> E (east / right edge)

POWER and GROUND pins are excluded -- LibreLane's io_place step filters
those bterms itself, and pinning them here would be redundant.

The along-edge sort key is the first RECT's leading coordinate on the
free axis: x1 for N/S pins, y1 for E/W pins.

Entries are anchored regexes in the LibreLane parser, so literal ``[``
and ``]`` bus-index characters are backslash-escaped on output.

No comment lines are ever emitted (not even at the top of the file):
any line beginning with ``#`` that is not one of the four direction
markers is parsed by LibreLane as a pin identifier, and the step fails
with "identifier/regex '#' requires a direction to be set first".
Explanatory prose belongs in an adjacent README, not in this file.

Usage:
    gen_pin_order.py <macro.lef> [-o OUTPUT]

With no ``-o``, the pin-order file is written to stdout.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass

_SIZE_RE = re.compile(r"^\s*SIZE\s+([0-9.eE+-]+)\s+BY\s+([0-9.eE+-]+)\s*;")
_PIN_RE = re.compile(r"^\s*PIN\s+(\S+)\s*$")
_END_PIN_RE = re.compile(r"^\s*END\s+(\S+)\s*$")
_USE_RE = re.compile(r"^\s*USE\s+(\S+)\s*;")
_RECT_RE = re.compile(
    r"^\s*RECT\s+([0-9.eE+-]+)\s+([0-9.eE+-]+)\s+([0-9.eE+-]+)\s+([0-9.eE+-]+)\s*;"
)

_DIRECTIONS = ("N", "E", "S", "W")


@dataclass(frozen=True)
class Pin:
    name: str
    side: str
    sort_key: float


def _escape_pin_name(name: str) -> str:
    return name.replace("[", r"\[").replace("]", r"\]")


def _classify_side(x1: float, y1: float, x2: float, y2: float, size_y: float) -> str:
    del x2  # unused: classification only needs x1/y1 plus y2 vs size_y
    if y1 == 0:
        return "S"
    if y2 == size_y:
        return "N"
    if x1 == 0:
        return "W"
    return "E"


def parse_lef(lef_path: str) -> list[Pin]:
    """Parse a macro LEF and return the classified, sorted signal pins."""
    size_x: float | None = None
    size_y: float | None = None
    pins: list[Pin] = []

    with open(lef_path, encoding="utf-8") as handle:
        lines = handle.readlines()

    # Locate SIZE (assumes a single MACRO per file, as produced by LibreLane).
    for line in lines:
        match = _SIZE_RE.match(line)
        if match:
            size_x = float(match.group(1))
            size_y = float(match.group(2))
            break
    if size_x is None or size_y is None:
        raise ValueError(f"no 'SIZE x BY y ;' line found in {lef_path}")

    i = 0
    n = len(lines)
    while i < n:
        pin_match = _PIN_RE.match(lines[i])
        if not pin_match:
            i += 1
            continue

        pin_name = pin_match.group(1)
        use = None
        first_rect: tuple[float, float, float, float] | None = None

        j = i + 1
        while j < n:
            end_match = _END_PIN_RE.match(lines[j])
            if end_match and end_match.group(1) == pin_name:
                break
            use_match = _USE_RE.match(lines[j])
            if use_match and use is None:
                use = use_match.group(1)
            if first_rect is None:
                rect_match = _RECT_RE.match(lines[j])
                if rect_match:
                    first_rect = tuple(float(g) for g in rect_match.groups())
            j += 1

        if use not in ("POWER", "GROUND"):
            if first_rect is None:
                raise ValueError(
                    f"pin '{pin_name}' in {lef_path} has no RECT in its PORT"
                )
            x1, y1, x2, y2 = first_rect
            side = _classify_side(x1, y1, x2, y2, size_y)
            sort_key = x1 if side in ("N", "S") else y1
            pins.append(Pin(name=pin_name, side=side, sort_key=sort_key))

        i = j + 1

    return pins


def render_pin_order(pins: list[Pin]) -> str:
    by_side: dict[str, list[Pin]] = {d: [] for d in _DIRECTIONS}
    for pin in pins:
        by_side[pin.side].append(pin)

    lines: list[str] = []
    for direction in _DIRECTIONS:
        side_pins = sorted(by_side[direction], key=lambda p: p.sort_key)
        lines.append(f"#{direction}")
        for pin in side_pins:
            lines.append(_escape_pin_name(pin.name))
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("lef", help="path to the macro LEF file")
    parser.add_argument(
        "-o",
        "--output",
        default=None,
        help="output path for the FP_PIN_ORDER_CFG file (default: stdout)",
    )
    args = parser.parse_args(argv)

    pins = parse_lef(args.lef)
    text = render_pin_order(pins)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as handle:
            handle.write(text)
    else:
        sys.stdout.write(text)

    return 0


if __name__ == "__main__":
    sys.exit(main())
