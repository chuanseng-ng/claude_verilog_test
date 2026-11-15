#!/usr/bin/env python3 -I
"""export_b3.py [run_dir] [out_dir] -- copy the final views of the OpenROAD B3 LibreLane run into pnr/commercial/runs/openroad_b3 (same file set as runs/openroad of B2).
The flow exits 2 (deferred nom_tt hold error) so LibreLane writes no final/ dir; the views are taken from the last step's state_out.json (as B2)."""
import csv, json, shutil, sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
run = Path(sys.argv[1]) if len(sys.argv) > 1 else REPO / "pnr/sky130/cpu/runs/b3_openroad"
out = Path(sys.argv[2]) if len(sys.argv) > 2 else REPO / "pnr/commercial/runs/openroad_b3"
steps = sorted(p for p in run.iterdir() if p.is_dir() and (p / "state_out.json").is_file() and p.name[:2].isdigit())
last = steps[-1]
s = json.load(open(last / "state_out.json"))
out.mkdir(parents=True, exist_ok=True)
for key, name in (("nl", "rv32i_cpu_top.nl.v"), ("pnl", "rv32i_cpu_top.pnl.v"), ("def", "rv32i_cpu_top.def"), ("lef", "rv32i_cpu_top.lef"),
                  ("gds", "rv32i_cpu_top.gds"), ("klayout_gds", "rv32i_cpu_top.klayout.gds"), ("sdc", "rv32i_cpu_top.sdc")):
    shutil.copy2(s[key], out / name)
for k, v in s["spef"].items():
    shutil.copy2(v, out / f"rv32i_cpu_top.{k[:3]}.spef")
m = s["metrics"]
json.dump(m, open(out / "metrics.json", "w"), indent=2)
with open(out / "metrics.csv", "w", newline="") as f:
    w = csv.writer(f)
    for k, v in m.items():
        w.writerow([k, v])
(out / "RUN_INFO.txt").write_text(
    f"b3_openroad\nrun_dir: {run}  (gitignored)\nconfig:  {REPO}/pnr/sky130/cpu/config_b3.json (CLI: -j 2; flow CVTClassicB3 = Classic + CVT.InsertDout0Buffers after detailed placement)\n"
    f"flow:    LibreLane 3562a8d (2.4.13-2-g3562a8d) + pnr/librelane_patches/librelane_live_state_2026-09-26.diff + plugin pnr/sky130/cpu/plugin_b3, in container ghcr.io/librelane/librelane:2.4.13 (OpenROAD edf00dff)\n"
    f"last step: {last.name}\n")
print("exported", last.name, "->", out)
