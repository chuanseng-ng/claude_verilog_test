#!/usr/bin/env python3
"""Render ``stuck_bits_formal.py`` results as coverage-waiver lines (bead xkw5).

Reads the JSON lines ``stuck_bits_formal.py`` printed (``--proof FILE``, repeatable) and writes one
``coverage_waivers.txt`` entry per (module, signal): the regex lists exactly the proven bits, in both
toggle directions, and the justification cites the proof and, for register-bank words, the register
and its documented mask from ``tb/cocotb/soc/reg_maps.py`` (transcribed from the module headers,
not from the RTL).  A proven bit that lies INSIDE a documented writable mask is not waived: it
would mean the register cannot be written the way the documentation says, which is a finding, so it
is printed on stderr and left in the report.

The tool prints to stdout and never edits the waiver file.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tb" / "cocotb" / "soc"))
import reg_maps  # noqa: E402  pylint: disable=wrong-import-position

BIT_RE = re.compile(r"^([A-Za-z_][\w$.]*)((?:\[\d+\])*)$")
MODULE_MAP = {
    "timer": "timer",
    "uart_controller": "uart",
    "spi_controller": "spi",
    "gpio_controller": "gpio",
    "pwm_controller": "pwm",
    "watchdog_timer": "wdt",
    "trng": "trng",
    "i2c_controller": "i2c",
    "pmu": "pmu",
    "pll_apb_regs": "pll",
    "npu_top": "npu",
}
REG_ARRAYS = {"regs_o", "regs", "regs_out"}
PROOF = (
    "PROVEN stuck after the first reset for every input sequence (unbounded SymbiYosys/ABC-PDR proof, "
    "tools/verif/stuck_bits_formal.py: reset assumed in cycles 0-1, all inputs free, bit equals its "
    "cycle-2 value for ever after)"
)


def ranges(nums: list[int]) -> str:
    """'3-5, 9' style text for a sorted list of ints."""
    out, i = [], 0
    nums = sorted(nums)
    while i < len(nums):
        j = i
        while j + 1 < len(nums) and nums[j + 1] == nums[j] + 1:
            j += 1
        out.append(str(nums[i]) if i == j else f"{nums[i]}-{nums[j]}")
        i = j + 1
    return ", ".join(out)


def regex_for(sig: str, by_elem: dict[tuple, list[int]]) -> str:
    """Anchored regex over '<sig>[e..][bit]:<from>-><to>' for exactly the given bits."""
    groups: dict[tuple, list[tuple]] = defaultdict(list)
    for elem, bits in by_elem.items():
        groups[tuple(sorted(bits))].append(elem)
    alts = []
    for bits, elems in sorted(groups.items()):
        bit_alt = "|".join(str(b) for b in bits)
        if elems == [()]:
            alts.append(f"\\[(?:{bit_alt})\\]")
            continue
        n_idx = len(elems[0])
        cols = []
        for i in range(n_idx):
            cols.append("|".join(sorted({str(e[i]) for e in elems}, key=int)))
        # element tuples that are not a full product would over-match: split them
        prod = 1
        for i in range(n_idx):
            prod *= len({e[i] for e in elems})
        if prod != len(elems):
            for e in sorted(elems):
                idx = "".join(f"\\[{x}\\]" for x in e)
                alts.append(f"{idx}\\[(?:{bit_alt})\\]")
            continue
        idx = "".join(f"\\[(?:{c})\\]" for c in cols)
        alts.append(f"{idx}\\[(?:{bit_alt})\\]")
    return f"^{re.escape(sig)}(?:{'|'.join(alts)}):"


def describe(module: str, sig: str, by_elem: dict[tuple, list[int]]) -> tuple[str, list[str]]:
    """Reason text for a signal's proven bits and any proven bit inside a documented mask."""
    notes: list[str] = []
    bank = reg_maps.BANKS.get(MODULE_MAP.get(module, ""), (None, 0))[0]
    parts = []
    for elem in sorted(by_elem):
        bits = sorted(by_elem[elem])
        if sig in REG_ARRAYS and len(elem) == 1 and bank is not None and elem[0] < len(bank):
            reg = bank[elem[0]]
            inside = [b for b in bits if (reg.wmask >> b) & 1]
            if inside:
                notes.append(f"{module} {sig}[{elem[0]}] bits {inside} are inside {reg.name}'s mask")
                by_elem[elem] = [b for b in bits if b not in inside]
                bits = by_elem[elem]
                if not bits:
                    continue
            parts.append(
                f"word {elem[0]} ({reg.name}, documented WMASK {reg.wmask:#x}, reset {reg.reset:#x}) "
                f"bit(s) {ranges(bits)}"
            )
        elif sig in REG_ARRAYS and len(elem) == 1:
            parts.append(f"word {elem[0]} bit(s) {ranges(bits)}")
        elif len(elem) == 0:
            parts.append(f"bit(s) {ranges(bits)}")
        else:
            parts.append(f"element {list(elem)} bit(s) {ranges(bits)}")
    if sig in REG_ARRAYS:
        why = (
            "the register bits are reserved / read-only / write-only fields: not in the documented "
            "write mask and never written by the module, so they keep their reset value"
        )
    elif sig == "prdata":
        why = "no register of the bank can drive these read-data bits (all words have them reserved)"
    else:
        why = "a signal derived only from register bits that are themselves proven stuck"
    return f"{'; '.join(parts)}: {why}", notes


def render(proofs: list[Path]) -> int:
    """Print the waiver lines; returns the number of notes (findings) raised."""
    findings = 0
    for path in proofs:
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            res = json.loads(line)
            module = res["module"]
            sigs: dict[str, dict[tuple, list[int]]] = defaultdict(lambda: defaultdict(list))
            for bit in res["proven"]:
                match = BIT_RE.match(bit)
                if not match:
                    continue
                idx = [int(x) for x in re.findall(r"\[(\d+)\]", match.group(2))]
                sigs[match.group(1)][tuple(idx[:-1])].append(idx[-1])
            for sig in sorted(sigs):
                by_elem = dict(sigs[sig])
                text, notes = describe(module, sig, by_elem)
                for note in notes:
                    print(f"FINDING: {note}", file=sys.stderr)
                    findings += 1
                by_elem = {e: b for e, b in by_elem.items() if b}
                if not by_elem:
                    continue
                n_pts = 2 * sum(len(b) for b in by_elem.values())
                print(
                    f"{module} | toggle | {regex_for(sig, by_elem)} | b | "
                    f"{PROOF}; {text}; {n_pts} points"
                )
    return findings


def main(argv: list[str]) -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", maxsplit=1)[0])
    parser.add_argument("--proof", action="append", required=True, type=Path)
    args = parser.parse_args(argv)
    render(args.proof)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
