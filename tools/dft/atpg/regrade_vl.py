#!/usr/bin/env python3
"""Verilator + Yosys re-grade of Quaigh patterns (bead j41m.15): the check that shares NOTHING with Quaigh or with regrade.py's simulator.

usage: regrade_vl.py CUT.blif PATTERNS.test --faults faults.json --out report.json [--yosys PATH] [--verilator-cmd 'nix develop ...']

Inputs: the cut BLIF, the Quaigh pattern file, and a fault list (JSON list of {"net", "value"}; regrade.py --dump-faults writes
one, with its own simulator's verdict).  Method:
  1. text step (trivial, covered by tests): `.latch D Q` -> Q is an extra input and D an extra output (full scan, same order Quaigh uses);
     every fault site gets a select input: net = sel ? stuck_value : original driver.  One model carries ALL sampled faults.
  2. Yosys `read_blif` + `write_verilog` turn the BLIF into Verilog (Yosys, not our parser, defines what each .names means).
  3. Verilator compiles it once; a C++ bench applies every pattern with no fault selected (good outputs) and then with each fault
     selected; a fault is detected on a pattern when any output differs.
  4. For the faults the patterns do not detect, Yosys' own SAT solver (`miter -equiv` + `sat -prove`) decides whether the fault is untestable
     (proof of equivalence good vs faulted) or a coverage hole.  A different solver from Quaigh's Kissat.
The result is compared fault by fault with the verdict in the fault list.
"""

import argparse
import json
import re
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Dict, List, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
from regrade import fault_blif, parse_blif, read_patterns, to_comb_blif  # noqa: E402

DEFAULT_YOSYS = "/nobackup/claude_sim_build/j41m15/bin/yosys"
DEFAULT_VL_SHELL = "nix develop " + str(Path(__file__).resolve().parents[3]) + " --command bash -c {cmd}"


def esc(n: str) -> str:
    return "\\" + n + " "


def multi_fault_blif(ctext: str, faults: List[Tuple[str, int]]) -> Tuple[str, List[int]]:
    """Insert one select input per fault. Returns (blif, indices of the faults actually inserted); a second fault on an already
    faulted net is skipped (the caller reports it)."""
    lines = ctext.replace("\\\n", " ").split("\n")
    used, kept = set(), []
    extra_blocks, sels = [], []
    for k, (net, v) in enumerate(faults):
        if net in used:
            continue
        for i, ln in enumerate(lines):
            if ln.startswith(".names") and ln.split()[-1] == net:
                f = ln.split()
                f[-1] = f"{net}__g{k}"
                lines[i] = " ".join(f)
                break
        else:
            raise ValueError(f"{net} is not a gate output")
        used.add(net)
        kept.append(k)
        sels.append(f"fsel_{k}")
        if v == 0:
            extra_blocks += [f".names {net}__g{k} fsel_{k} {net}", "10 1"]
        else:
            extra_blocks += [f".names {net}__g{k} fsel_{k} {net}", "1- 1", "-1 1"]
    for i, ln in enumerate(lines):
        if ln.startswith(".inputs"):
            lines[i] = ln + " " + " ".join(sels)
            break
    end = [i for i, ln in enumerate(lines) if ln.startswith(".end")]
    at = end[0] if end else len(lines)
    lines[at:at] = extra_blocks
    return "\n".join(lines), kept


TB = r"""
#include "Vvl_top.h"
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <string>
#include <vector>
// Verilator uses scalar types for ports of up to 64 bits and VlWide<N> above: treat both as arrays of 32-bit words.
template <class W> static uint32_t* words(W& w) { if constexpr (std::is_integral<W>::value) return reinterpret_cast<uint32_t*>(&w); else return w.data(); }
template <class W> static void setbit(W& w, int k, int v) { uint32_t* p = words(w); if (v) p[k >> 5] |= (1u << (k & 31)); else p[k >> 5] &= ~(1u << (k & 31)); }
template <class W> static void clr(W& w) { uint32_t* p = words(w); for (size_t i = 0; i < sizeof(w) / 4; i++) p[i] = 0; }
int main(int argc, char** argv) {
  std::ifstream pf(argv[1]);
  int NI = atoi(argv[2]), NF = atoi(argv[3]), NO = atoi(argv[4]);
  std::vector<std::string> pats; std::string ln;
  while (std::getline(pf, ln)) { if (ln.empty()) continue; pats.push_back(ln); }
  Vvl_top top;
  std::vector<int> first(NF, -1);
  int nw = (NO + 31) / 32;
  for (size_t p = 0; p < pats.size(); p++) {
    const std::string& b = pats[p];
    clr(top.pin);
    for (int k = 0; k < NI; k++) setbit(top.pin, k, b[k] == '1');
    clr(top.fsel);
    top.eval();
    std::vector<uint32_t> good(words(top.pout), words(top.pout) + nw);
    for (int f = 0; f < NF; f++) {
      if (first[f] >= 0) continue;
      setbit(top.fsel, f, 1); top.eval();
      bool d = false;
      for (int w = 0; w < nw; w++) if (words(top.pout)[w] != good[w]) d = true;
      if (d) first[f] = (int)p;
      setbit(top.fsel, f, 0);
    }
  }
  for (int f = 0; f < NF; f++) printf("%d\n", first[f]);
  return 0;
}
"""


def yosys_sat_equiv(yosys: str, good: Path, faulted: Path, tmp: Path) -> bool:
    """True when Yosys proves good == faulted for all inputs (the fault is untestable)."""
    g = tmp / "gold.blif"
    f = tmp / "gate.blif"
    g.write_text(re.sub(r"^\.model .*$", ".model gold", good.read_text(), flags=re.M))
    f.write_text(re.sub(r"^\.model .*$", ".model gate", faulted.read_text(), flags=re.M))
    ys = tmp / "eq.ys"
    ys.write_text(f"read_blif {g}\nread_blif {f}\nmiter -equiv -flatten -make_outputs gold gate miter\n"
                  "hierarchy -top miter\nflatten\nopt\nopt\nopt\nsat -verify -prove trigger 0 miter\n")
    r = subprocess.run([yosys, "-q", "-l", str(tmp / "eq.log"), str(ys)], capture_output=True, text=True)
    return r.returncode == 0 and "SUCCESS" in (tmp / "eq.log").read_text()


def run(blif: Path, patterns: Path, faults: List[dict], yosys: str, vl_shell: str, tmp: Path,
        sat_undetected: int = 60) -> dict:
    ctext = to_comb_blif(Path(blif).read_text())
    ins, outs, _ = parse_blif(ctext)
    fl = [(f["net"], int(f["value"])) for f in faults]
    mtext, kept = multi_fault_blif(ctext, fl)
    ins2, outs2, _ = parse_blif(mtext)
    model = re.search(r"^\.model (\S+)", mtext, re.M).group(1)
    # an exposed flop Q that is also a primary output is both an input and an output of the BLIF: keep it as an input in the
    # Verilog model and wire the output bit to it in the wrapper
    in_set = set(ins2)
    ytext = "\n".join(
        (".outputs " + " ".join(n for n in ln.split()[1:] if n not in in_set)) if ln.startswith(".outputs") else ln
        for ln in mtext.split("\n"))
    (tmp / "m.blif").write_text(ytext)
    (tmp / "y.ys").write_text(f"read_blif {tmp}/m.blif\nwrite_verilog -noattr {tmp}/dut.v\n")
    subprocess.run([yosys, "-q", str(tmp / "y.ys")], check=True, capture_output=True)
    ni, nf, no = len(ins), len(kept), len(outs2)
    w = [f"module vl_top(input [{max(ni, 1) - 1}:0] pin, input [{max(nf, 1) - 1}:0] fsel, output [{no - 1}:0] pout);",
         f"  {model} u("]
    conn = [f".{esc(n)}(pin[{k}])" for k, n in enumerate(ins)] + [f".{esc('fsel_%d' % k)}(fsel[{j}])" for j, k in enumerate(kept)]
    pos = {n: k for k, n in enumerate(ins)}
    uniq = []
    for n in outs2:
        if n not in pos and n not in uniq:
            uniq.append(n)  # a net listed twice in .outputs (Quaigh counts both) is one wire here
    conn += [f".{esc(n)}(w[{u}])" for u, n in enumerate(uniq)]
    assigns = []
    for k, n in enumerate(outs2):
        # an exposed flop Q that is also a primary output is an input of the model: wire the output bit to it
        assigns.append(f"  assign pout[{k}] = {'pin[%d]' % pos[n] if n in pos else 'w[%d]' % uniq.index(n)};")
    w.insert(1, f"  wire [{max(len(uniq), 1) - 1}:0] w;")
    w.append(",\n    ".join(conn) + ");\n" + "\n".join(assigns) + "\nendmodule\n")
    (tmp / "vl_top.v").write_text("\n".join(w))
    (tmp / "tb.cpp").write_text(TB)
    pats = [p for p in read_patterns(patterns)]
    (tmp / "pats.txt").write_text("\n".join(pats) + "\n")
    (tmp / "zeros.txt").write_text("0" * ni + "\n")
    inner = (f"cd {tmp} && verilator --cc --exe --build -O2 -Wno-fatal -Wno-lint -Wno-style --top-module vl_top "
             f"-CFLAGS -O1 vl_top.v dut.v tb.cpp -o vsim >verilator.log 2>&1 && ./obj_dir/vsim pats.txt {ni} {nf} {no} && echo --- && "
             f"./obj_dir/vsim zeros.txt {ni} {nf} {no}")
    r = subprocess.run(vl_shell.format(cmd=shlex.quote(inner)), shell=True, capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(f"verilator step failed: {r.stderr[-500:]} {(tmp / 'verilator.log').read_text()[-800:] if (tmp / 'verilator.log').exists() else ''}")
    real_out, zero_out = r.stdout.split("---")
    first = [int(x) for x in real_out.split()]
    zero_first = [int(x) for x in zero_out.split()]
    if len(first) != nf:
        raise SystemExit(f"bench returned {len(first)} verdicts for {nf} faults")
    verdict = {kept[j]: first[j] for j in range(nf)}
    rep = {"patterns": len(pats), "faults_in_model": nf, "faults_skipped_same_net": len(fl) - nf,
           "disagreements": [], "detected": 0, "undetected": 0, "undetected_proven_untestable_yosys_sat": 0,
           "undetected_testable_hole": 0, "undetected_proof_skipped": 0}
    n_sat = 0
    for k, f in enumerate(faults):
        if k not in verdict:
            continue
        det = verdict[k] >= 0
        rep["detected" if det else "undetected"] += 1
        if "own_sim_detects" in f and f["own_sim_detects"] != det:
            rep["disagreements"].append({"net": f["net"], "value": f["value"], "own_sim": f["own_sim_detects"], "verilator": det})
        if not det:
            if n_sat >= sat_undetected:
                rep["undetected_proof_skipped"] += 1
                continue
            n_sat += 1
            fb = tmp / "faulted.blif"
            fb.write_text(fault_blif(ctext, f["net"], int(f["value"])))
            gb = tmp / "good.blif"
            gb.write_text(ctext)
            if yosys_sat_equiv(yosys, gb, fb, tmp):
                rep["undetected_proven_untestable_yosys_sat"] += 1
            else:
                rep["undetected_testable_hole"] += 1
                rep.setdefault("holes", []).append({"net": f["net"], "value": f["value"]})
    # negative control: one all-zero pattern must detect clearly fewer of the same faults than the Quaigh pattern set
    rep["control_all_zero"] = {"detected_by_quaigh_patterns": sum(v >= 0 for v in first),
                               "detected_by_all_zero_pattern": sum(v >= 0 for v in zero_first)}
    rep["control_all_zero"]["ok"] = (rep["control_all_zero"]["detected_by_all_zero_pattern"]
                                     < rep["control_all_zero"]["detected_by_quaigh_patterns"])
    rep["ok"] = not rep["disagreements"] and rep["control_all_zero"]["ok"]
    return rep


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("blif")
    ap.add_argument("patterns")
    ap.add_argument("--faults", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--yosys", default=DEFAULT_YOSYS)
    ap.add_argument("--vl-shell", default=DEFAULT_VL_SHELL,
                    help="shell command that runs {cmd} inside an environment with verilator and a C++ compiler")
    ap.add_argument("--sat-undetected", type=int, default=60)
    a = ap.parse_args(argv)
    faults = json.loads(Path(a.faults).read_text())
    with tempfile.TemporaryDirectory(dir="/nobackup/claude_sim_build/j41m15") as td:
        rep = run(Path(a.blif), Path(a.patterns), faults, a.yosys, a.vl_shell, Path(td), a.sat_undetected)
    Path(a.out).write_text(json.dumps(rep, indent=1))
    print(json.dumps({k: v for k, v in rep.items() if k != "disagreements"}), "disagreements:", len(rep["disagreements"]))
    return 0 if rep["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
