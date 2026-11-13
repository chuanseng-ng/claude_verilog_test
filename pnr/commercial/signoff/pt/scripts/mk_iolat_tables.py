#!/usr/bin/env python3
"""mk_iolat_tables.py -- build the per-view clk_io latency tables from the measured clk_i insertion latencies.

    python3 -I pnr/commercial/signoff/pt/scripts/mk_iolat_tables.py

Input : pt/runs_clklat/<arm>_<rc>_<lib>/clk_latency.tsv   (pt/scripts/measure_clk_latency.tcl, PrimeTime, StarRC SPEF, base SDC)
Output (pt/iolat_pv/, committed):
  clk_latency_measured.tsv   per arm / corner: statistics of the clk_i RISING-edge arrival at the register clock pins, as NETWORK latency
                             (arrival minus the 1.0 ns source latency of the shared SDC), ns
  iolat_pv_arm.tsv           arm <TAB> rc <TAB> lib <TAB> early <TAB> late     each arm's OWN mean network latency at that corner      (recommended)
  iolat_pv_shared.tsv        same columns; ONE value per corner (mean of the three arms' values), identical rows for every arm            (sensitivity)
Rule: early / late = mean over ALL register clock pins (flops + SRAM macros) of the min / max rise arrival of that pin.  PrimeTime reports
early == late at every pin (no derate, no OCV), so the two columns differ only in the 4th decimal; the sink-to-sink spread (skew) is NOT put
into the table: clk_io models the SoC-side registers of a balanced SoC clock tree, whose arrival equals the macro's mean insertion delay.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PT = os.path.abspath(os.path.join(HERE, ".."))
SRC = os.path.join(PT, "runs_clklat")
OUT = os.path.join(PT, "iolat_pv")
ARMS = ["openroad", "icc2b6", "innovusb6"]
# b7 arms (b6 + ECO): their OWN measured tree goes into the 'arm' table; the 'shared' table keeps the per-corner mean of the three b6-era ARMS above,
# so adding an arm never changes an existing row (the shared latency stays one value per corner, the same for every arm and for b6 vs b7).
EXTRA_ARMS = [
    a
    for a in ("icc2b7", "innovusb7", "icc2b8", "innovusb8", "icc2b9", "innovusb9", "innovusb10", "innovusb11")
    if a not in os.environ.get("IOLAT_EXCLUDE", "").split()  # IOLAT_EXCLUDE="icc2b8 innovusb8": leave arms out (e.g. while their layout is being re-run)
    # only arms whose 9 corners are ALL measured: a half-measured arm made this script fail (b7/b8 chains ran it while the other arm was still measuring)
    if all(os.path.isfile(os.path.join(PT, "runs_clklat", f"{a}_{rc}_{lib}", "clk_latency.tsv")) for rc in ("nom", "min", "max") for lib in ("tt", "ss", "ff"))
]
CORNERS = [(rc, lib) for rc in ("nom", "min", "max") for lib in ("tt", "ss", "ff")]
SOURCE_LATENCY = 1.0  # set_clock_latency -source 1.0 [get_clocks clk_i] in the shared SDC
STATS = ["min", "p05", "median", "mean", "p95", "max"]


def load(arm, rc, lib):
    d = {}
    with open(os.path.join(SRC, f"{arm}_{rc}_{lib}", "clk_latency.tsv")) as f:
        for line in f:
            k, _, v = line.rstrip("\n").partition("\t")
            d[k] = v
    return d


def main():
    os.makedirs(OUT, exist_ok=True)
    meas = {(a, rc, lib): load(a, rc, lib) for a in ARMS + EXTRA_ARMS for rc, lib in CORNERS}
    cols = ["arm", "rc", "lib", "n_regs", "n_flops", "n_sram"]
    cols += [f"all_{s}" for s in STATS]
    cols += ["flop_mean", "sram_mean", "in_capture_mean", "out_launch_mean", "skew_all_max_minus_min"]
    lines = [
        "# clk_i insertion latency at the register clock pins, RISING edge, NETWORK latency in ns (= PrimeTime arrival - 1.0 ns source latency).",
        "# Source: pt/runs_clklat/*/clk_latency.tsv (pt/scripts/measure_clk_latency.tcl). Statistics of the per-pin LATE arrival (early == late to < 0.5 ps",
        "# per pin, no derate).  all = flops + SRAM macros; in_capture = registers that capture an input-port path; out_launch = registers that launch an output-port path.",
        "\t".join(cols),
    ]
    for (a, rc, lib), d in meas.items():
        g = lambda k: float(d[k]) - SOURCE_LATENCY  # noqa: E731
        row = [a, rc, lib, d["all_rise_late_n"], d["flop_rise_late_n"], d["sram_rise_late_n"]]
        row += [f"{g('all_rise_late_' + s):.4f}" for s in STATS]
        row += [
            f"{g('flop_rise_late_mean'):.4f}",
            f"{g('sram_rise_late_mean'):.4f}",
            f"{g('in_capture_rise_late_mean'):.4f}",
            f"{g('out_launch_rise_late_mean'):.4f}",
            f"{float(d['all_rise_late_max']) - float(d['all_rise_late_min']):.4f}",
        ]
        lines.append("\t".join(map(str, row)))
    open(os.path.join(OUT, "clk_latency_measured.tsv"), "w").write("\n".join(lines) + "\n")

    hdr = [
        "# clk_io latency table for sky130_cpu_iolat_pv.sdc: arm, rc, lib, early_ns, late_ns (NETWORK latency; the SDC adds the 1.0 ns source latency).",
        "# early = mean over all register clock pins of the min rise arrival - 1.0; late = same with the max rise arrival.  Built by mk_iolat_tables.py.",
    ]
    arm_rows, sh_rows = [], []
    for rc, lib in CORNERS:
        e_l = []
        for a in ARMS:
            d = meas[(a, rc, lib)]
            e = float(d["all_rise_early_mean"]) - SOURCE_LATENCY
            l = float(d["all_rise_late_mean"]) - SOURCE_LATENCY
            arm_rows.append((a, rc, lib, e, l))
            e_l.append((e, l))
        se = sum(x[0] for x in e_l) / len(e_l)
        sl = sum(x[1] for x in e_l) / len(e_l)
        for a in ARMS + EXTRA_ARMS:
            sh_rows.append((a, rc, lib, se, sl))
        for a in EXTRA_ARMS:
            d = meas[(a, rc, lib)]
            arm_rows.append((a, rc, lib, float(d["all_rise_early_mean"]) - SOURCE_LATENCY, float(d["all_rise_late_mean"]) - SOURCE_LATENCY))
    for name, rows, note in (
        ("iolat_pv_arm.tsv", arm_rows, "# variant 'arm': each arm's own measured tree."),
        ("iolat_pv_shared.tsv", sh_rows, "# variant 'shared': per corner, the mean of the three arms' values, the same row for every arm."),
    ):
        body = [note] + [f"{a}\t{rc}\t{lib}\t{e:.4f}\t{l:.4f}" for a, rc, lib, e, l in rows]
        open(os.path.join(OUT, name), "w").write("\n".join(hdr + body) + "\n")
    print(f"wrote {OUT}: clk_latency_measured.tsv, iolat_pv_arm.tsv, iolat_pv_shared.tsv")


if __name__ == "__main__":
    sys.exit(main())
