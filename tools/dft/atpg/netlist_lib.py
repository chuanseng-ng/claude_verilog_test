"""Tiny structural-Verilog reader for the OpenROAD / Yosys gate netlists of the Sky130 SoC (bead j41m.15).

Not a Verilog parser: it understands exactly the layout the flow writes (one instance per statement, named pin
connections, escaped identifiers).  Same approach as tools/dft/check_scan_chains.py.
"""

import re
from pathlib import Path
from typing import Dict, Iterator, NamedTuple

CELL_RE = re.compile(r"\n\s*(sky130_fd_sc_hd__\w+|sky130_ef_sc_hd__\w+|rv32i_cpu_top|sky130_sram_\w+)\s+(\\?\S+)\s*\((.*?)\);", re.S)
PIN_RE = re.compile(r"\.(\w+)\(([^()]*)\)")
FLOP_TYPE_RE = re.compile(r"sky130_fd_sc_hd__(sdf|df|edf|sedf)\w*")
SCAN_FLOP_RE = re.compile(r"sky130_fd_sc_hd__s(df|edf)\w*")
FILLER_RE = re.compile(r"sky130_(fd|ef)_sc_hd__(fill|decap|tapvpwrvgnd|diode)\w*")
BUF_RE = re.compile(r"sky130_fd_sc_hd__(buf|clkbuf|dlygate\w*|dlymetal\w*|clkdlybuf\w*)_")
INV_RE = re.compile(r"sky130_fd_sc_hd__(inv|clkinv\w*)_")


class Cell(NamedTuple):
    typ: str
    inst: str
    pins: Dict[str, str]


def norm(name: str) -> str:
    """Escaped-identifier cleanup: `\\a.b[0] ` -> `a.b[0]`."""
    return name.strip().replace("\\", "").replace(" ", "")


def iter_cells(text: str) -> Iterator[Cell]:
    for typ, inst, body in CELL_RE.findall(text):
        yield Cell(typ, norm(inst), {p: norm(n) for p, n in PIN_RE.findall(body)})


def read_cells(path) -> Dict[str, Cell]:
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    return {c.inst: c for c in iter_cells(text)}
