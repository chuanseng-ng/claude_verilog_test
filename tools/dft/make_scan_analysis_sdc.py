#!/usr/bin/env python3
"""Analysis-only SDC for timing the scan_out_o gate path (bead j41m.17). NOT a sign-off constraint.

usage: make_scan_analysis_sdc.py OUT.sdc [REPO_SDC]

The repo SDC (pnr/sky130/soc/constraints/sky130_soc.sdc) takes scan_out_o out of timing with
``set_false_path -to [get_ports scan_out_o]`` (functional-mode constraint), so the flow STA never times the new
crypto_wipe_done -> AND2 -> scan_out_o path. This writes a COPY with that one line removed and a 0 ns output delay on
core_clk appended (the full 25 ns period). The repo SDC is not modified. Use it as STA_SDC for
pnr/scripts/sta_load_sky130_soc.tcl together with pnr/scripts/sta_scan_gate_paths_sky130_soc.tcl (STA_CMDS).
"""
import sys
from pathlib import Path

FALSE_PATH = "if {[llength [get_ports -quiet scan_out_o]] > 0} { set_false_path -to [get_ports scan_out_o] }"


def make(src_text: str) -> str:
    if src_text.count(FALSE_PATH) != 1:
        raise SystemExit("repo SDC: expected exactly one scan_out_o false-path line; it changed, update this script")
    out = src_text.replace(FALSE_PATH, "# ANALYSIS-ONLY: scan_out_o false path removed (see the constraint appended at the end)")
    out += (
        "\n# ANALYSIS-ONLY (bead j41m.17, user-approved, NOT the repo SDC): scan_out_o sampled on core_clk, 0 ns output delay\n"
        "set_output_delay 0 -clock [get_clocks core_clk] [get_ports scan_out_o]\n"
    )
    return out


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    default = Path(__file__).resolve().parents[2] / "pnr/sky130/soc/constraints/sky130_soc.sdc"
    src = Path(sys.argv[2]) if len(sys.argv) > 2 else default
    Path(sys.argv[1]).write_text(make(src.read_text()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
