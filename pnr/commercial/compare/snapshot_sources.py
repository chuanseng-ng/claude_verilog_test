#!/usr/bin/env python3
"""Copy the small machine-readable result files that live only in gitignored run
directories into a committed snapshot, so every number in comparison.json can be
traced to a file in git.

Run once on the host that holds the run directories (it starts no EDA tool):

    python3 -I pnr/commercial/compare/snapshot_sources.py

Writes ``pnr/commercial/compare/snapshot/`` plus ``snapshot/MANIFEST.tsv``
(snapshot path, origin path, sha256 of the origin, bytes).  Two files are derived,
not copied, and say so in the manifest: the OpenROAD cell census (counted from the
post-route netlist) and the OpenROAD per-step runtime table (from LibreLane's
per-step ``runtime.txt``).  The cell-area table is read from the PDK LEF.

LEC evidence of the b6 arms is copied into the existing per-tool report convention
(``signoff/lec/{conformal,formality}/reports/<tag>/``), the same way earlier steps
committed theirs.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
COM = REPO / "pnr/commercial"
SNAP = COM / "compare/snapshot"

PT_DIRS = {"base": "runs", "iolat": "runs_iolat", "own": "runs_own"}
PT_ARMS = [
    "openroad",
    "icc2b6",
    "innovusb6",
    "icc2",
    "icc2b5i",
    "icc2b5m",
    "innovusb5h",
    "innovusb5j",
    "innovusb5k",
]
CORNERS = [f"{rc}_{lib}" for rc in ("nom", "min", "max") for lib in ("tt", "ss", "ff")]
PDK_LEF_DIR = Path(
    os.environ.get(
        "SKY130_HD_LEF_DIR",
        str(
            Path.home() / "pdk/ciel/sky130/versions/0fe599b2afb6708d281543108caf8310912f54af"
            "/sky130A/libs.ref/sky130_fd_sc_hd/lef"
        ),
    )
)
SRAM_LEF = COM / "pdk/sky130/build"  # searched for the SRAM LEF below

manifest: list[tuple[str, str, str, int]] = []


def sha(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def rel(p: Path) -> str:
    return str(p.resolve().relative_to(REPO))


def copy(src: Path, dst: Path, required: bool = True) -> None:
    if not src.is_file():
        if required:
            sys.exit(f"missing source {src}")
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dst)
    manifest.append((rel(dst), rel(src), sha(src), src.stat().st_size))


def derived(dst: Path, origin: str, text: str) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(text)
    manifest.append((rel(dst), origin, "derived", len(text.encode())))


def pt() -> None:
    for var, d in PT_DIRS.items():
        for arm in PT_ARMS:
            for c in CORNERS:
                src = COM / "signoff/pt" / d / f"{arm}_{c}"
                if not (src / "metrics.tsv").is_file():
                    continue
                dst = SNAP / "pt" / var / f"{arm}_{c}"
                for f in ("metrics.tsv", "inputs.txt", "global_timing.txt"):
                    copy(src / f, dst / f)
                if c == "nom_tt":
                    copy(src / "power_B.txt", dst / "power_B.txt", required=False)
                    copy(src / "time.txt", dst / "time.txt", required=False)
                    if var == "base":
                        copy(src / "constraint_drv.txt", dst / "constraint_drv.txt", required=False)


def openroad() -> None:
    src = COM / "runs/openroad"
    dst = SNAP / "openroad"
    copy(src / "metrics.json", dst / "metrics.json")
    copy(src / "RUN_INFO.txt", dst / "RUN_INFO.txt")
    nl = src / "rv32i_cpu_top.nl.v"
    cnt: Counter[str] = Counter()
    pat = re.compile(r"^\s*(sky130_[A-Za-z0-9_]+)\s+\S+\s*\(")
    with open(nl) as f:
        for line in f:
            m = pat.match(line)
            if m:
                cnt[m.group(1)] += 1
    derived(
        dst / "cellcount.txt",
        f"{rel(nl)} sha256={sha(nl)} (instance count per master)",
        "".join(f"{k} {v}\n" for k, v in sorted(cnt.items())),
    )
    run = REPO / "pnr/sky130/cpu/runs/b2_openroad"
    rows = []
    for step in sorted(p for p in run.iterdir() if p.is_dir() and (p / "runtime.txt").is_file()):
        rows.append(f"{step.name}\t{(step / 'runtime.txt').read_text().strip()}\n")
    derived(
        dst / "step_runtime.tsv",
        f"{rel(run)}/*/runtime.txt (LibreLane per-step runtime)",
        "step\truntime_hms\n" + "".join(rows),
    )


def icc2() -> None:
    run = COM / "impl/icc2/runs/b6_icc2"
    dst = SNAP / "icc2_b6"
    for f in (
        "final_qor.txt",
        "final_utilization.txt",
        "final_cellcount.txt",
        "final_check_routes.txt",
        "final_check_lvs.txt",
        "final_power.txt",
    ):
        copy(run / "reports" / f, dst / f)
    for t in sorted((run / "logs").glob("*.time")):
        copy(t, dst / "stage_time" / t.name)
    # the ICC2 b6 own SDC used by the judge (md5 44ce62ce...): commit next to the other own SDCs
    copy(run / "out/rv32i_cpu_top.func_tt.sdc", COM / "constraints/sky130_cpu_icc2_b6_own_pt.sdc")


def innovus() -> None:
    run = COM / "impl/innovus/runs/b6_innovus"
    dst = SNAP / "innovus_b6"
    for f in ("final_area.txt", "final_route_summary.txt", "final_antenna.txt"):
        copy(run / "reports" / f, dst / f)
    for t in sorted((run / "logs").glob("*.time")):
        copy(t, dst / "stage_time" / t.name)


def lec() -> None:
    cr = COM / "signoff/lec/conformal"
    for d in sorted((cr / "runs").glob("b4m_*")):
        if d.is_dir() and (d / "lec.log").is_file():
            copy(d / "lec.log", cr / "reports" / d.name / "lec_log.txt")
            copy(d / "time.txt", cr / "reports" / d.name / "time.txt", required=False)
    fr = COM / "signoff/lec/formality"
    tags = sorted(
        p.name
        for p in (fr / "runs").iterdir()
        if p.is_dir() and (p.name.startswith("b6_") or p.name == "b4a2_dc_v2_vs_rtl")
    )
    for t in tags:
        d = fr / "runs" / t
        if not (d / "fm.log").is_file():
            continue
        copy(d / "fm.log", fr / "reports" / t / "fm_log.txt")
        for f in (
            "time.txt",
            "failing_points.txt",
            "aborted_points.txt",
            "unverified_points.txt",
            "svf_operations.txt",
            "unmatched_points.txt",
            "black_boxes.txt",
        ):
            copy(d / f, fr / "reports" / t / f, required=False)


def cell_area() -> None:
    lefs = [PDK_LEF_DIR / "sky130_fd_sc_hd.lef", PDK_LEF_DIR / "sky130_ef_sc_hd.lef"]
    sram = sorted(REPO.glob("pnr/sky130/**/sky130_sram_1kbyte_1rw1r_32x256_8.lef"))
    lefs += sram[:1]
    rows, origin = {}, []
    for lef in lefs:
        cur = None
        for line in open(lef):
            m = re.match(r"\s*MACRO\s+(\S+)", line)
            if m:
                cur = m.group(1)
                continue
            m = re.match(r"\s*SIZE\s+([\d.]+)\s+BY\s+([\d.]+)", line)
            if m and cur:
                rows[cur] = (float(m.group(1)), float(m.group(2)))
                cur = None
        origin.append(f"{lef} sha256={sha(lef)}")
    derived(
        SNAP / "cell_area.tsv",
        "; ".join(origin) + " (MACRO SIZE w x h)",
        "cell\tw_um\th_um\tarea_um2\n"
        + "".join(f"{k}\t{w}\t{h}\t{w * h:.6f}\n" for k, (w, h) in sorted(rows.items())),
    )


def main() -> None:
    if SNAP.exists():
        shutil.rmtree(SNAP)
    pt()
    openroad()
    icc2()
    innovus()
    lec()
    cell_area()
    (SNAP / "MANIFEST.tsv").write_text(
        "snapshot\torigin\torigin_sha256\tbytes\n"
        + "".join("\t".join(map(str, r)) + "\n" for r in manifest)
    )
    print(f"{len(manifest)} files -> {rel(SNAP)}")


if __name__ == "__main__":
    main()
