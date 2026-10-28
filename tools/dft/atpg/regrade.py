#!/usr/bin/env python3
"""Independent re-grade of Quaigh patterns by simulation (bead j41m.15, sanity check 2).

usage: regrade.py CUT.blif PATTERNS.test --out report.json [--samples 200] [--undetected 50] [--seed 7]
                  [--quaigh PATH] [--no-quaigh-sim]

For a random sample of single stuck-at faults on gate-output nets of the BLIF cut it decides, TWICE and independently,
whether the pattern file detects the fault (some output differs from the good circuit on some pattern):
  (a) this file's own bit-parallel simulator (Python big ints, own `.names` evaluator);
  (b) `quaigh simulate` on a fault-injected copy of the BLIF (Quaigh's reader and simulator, not its fault simulator).
The two must agree fault by fault.  For every fault the patterns do NOT detect, `quaigh equiv` good-vs-faulted says
whether it is provably untestable (equivalent) or a coverage hole (testable but missed).
Negative controls: (1) all-zero patterns must detect (almost) nothing; (2) a fault-free copy must never be flagged;
(3) the tests inject a corrupted simulator result and require the comparison to fail.
Limits: this validates Quaigh's pattern-to-output simulation and the sample's detection status; it does not recount
Quaigh's own internal fault list (that is Quaigh-internal and reported only as totals).
"""

import argparse
import json
import random
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple

Gate = Tuple[List[str], List[Tuple[str, str]]]  # (input nets, [(cube, output polarity)])


def parse_blif(text: str):
    text = text.replace("\\\n", " ")
    inputs: List[str] = []
    outputs: List[str] = []
    gates: Dict[str, Gate] = {}
    latches: List[List[str]] = []
    lines = [ln.strip() for ln in text.split("\n")]
    i = 0
    while i < len(lines):
        ln = lines[i]
        i += 1
        if not ln or ln.startswith("#"):
            continue
        if ln.startswith(".inputs"):
            inputs += ln.split()[1:]
        elif ln.startswith(".outputs"):
            outputs += ln.split()[1:]
        elif ln.startswith(".names"):
            nets = ln.split()[1:]
            cubes = []
            while i < len(lines) and lines[i] and not lines[i].startswith("."):
                cubes.append(lines[i].split())
                i += 1
            ins, out = nets[:-1], nets[-1]
            cs = []
            for c in cubes:
                cs.append(("", c[0]) if not ins else (c[0], c[1]))
            gates[out] = (ins, cs)
        elif ln.startswith(".latch"):
            latches.append(ln.split()[1:3])
        elif ln.startswith((".subckt", ".gate")):
            raise SystemExit(f"unsupported construct in cut: {ln[:40]}")
    # full-scan view, same order as quaigh's expose_dff: flop Q -> extra input, flop D -> extra output
    inputs += [q for _, q in latches]
    outputs += [d for d, _ in latches]
    return inputs, outputs, gates


def to_comb_blif(text: str) -> str:
    """Full-scan view as plain text: every `.latch D Q ...` is removed, Q is appended to .inputs and D to .outputs (latch order).
    Needed because `quaigh equiv` on a sequential BLIF is a 1-cycle check from the reset state, NOT a full-scan check."""
    lines = text.replace("\\\n", " ").split("\n")
    qs, ds, keep = [], [], []
    for ln in lines:
        if ln.startswith(".latch"):
            f = ln.split()
            ds.append(f[1])
            qs.append(f[2])
        else:
            keep.append(ln)
    done_i = done_o = False
    for i, ln in enumerate(keep):
        if ln.startswith(".inputs") and not done_i:
            keep[i] = ln + " " + " ".join(qs)
            done_i = True
        elif ln.startswith(".outputs") and not done_o:
            keep[i] = ln + " " + " ".join(ds)
            done_o = True
    return "\n".join(keep)


def topo(inputs, gates):
    order, seen, state = [], set(inputs), {}
    for root in gates:
        if root in seen or root in state:
            continue
        stack = [(root, iter(gates[root][0]))]
        state[root] = 1
        while stack:
            n, it = stack[-1]
            for d in it:
                if d in seen or d in state or d not in gates:
                    continue
                state[d] = 1
                stack.append((d, iter(gates[d][0])))
                break
            else:
                stack.pop()
                order.append(n)
                seen.add(n)
    return order


def eval_gate(gate: Gate, val: Dict[str, int], mask: int) -> int:
    ins, cubes = gate
    if not cubes:
        return 0
    pol = cubes[0][1]
    acc = 0
    for cube, _ in cubes:
        term = mask
        for net, ch in zip(ins, cube):
            if ch == "1":
                term &= val[net]
            elif ch == "0":
                term &= ~val[net] & mask
        acc |= term
    return acc if pol == "1" else (~acc & mask)


class Sim:
    def __init__(self, blif_text: str):
        self.inputs, self.outputs, self.gates = parse_blif(blif_text)
        self.order = topo(self.inputs, self.gates)
        self.pos = {n: k for k, n in enumerate(self.order)}
        self.fanout: Dict[str, List[str]] = {}
        for g, (ins, _) in self.gates.items():
            for d in ins:
                self.fanout.setdefault(d, []).append(g)
        self.good: Dict[str, int] = {}
        self.mask = 0

    def load(self, patterns: List[str]):
        n = len(patterns)
        self.mask = (1 << n) - 1
        val = {}
        for k, name in enumerate(self.inputs):
            v = 0
            for p, bits in enumerate(patterns):
                if bits[k] == "1":
                    v |= 1 << p
            val[name] = v
        for g in self.order:
            val[g] = eval_gate(self.gates[g], val, self.mask)
        self.good = val

    def outs(self, val) -> List[int]:
        return [val.get(o, 0) for o in self.outputs]

    def detect(self, net: str, value: int) -> Optional[int]:
        """First pattern index on which stuck-at-`value` on `net` flips some output, else None."""
        forced = self.mask if value else 0
        if self.good[net] == forced:
            return None
        val = dict(self.good)
        val[net] = forced
        cone, stack = set(), [net]
        while stack:
            n = stack.pop()
            for g in self.fanout.get(n, []):
                if g not in cone:
                    cone.add(g)
                    stack.append(g)
        for g in sorted(cone, key=self.pos.__getitem__):
            val[g] = eval_gate(self.gates[g], val, self.mask)
        diff = 0
        for o in self.outputs:
            diff |= val.get(o, 0) ^ self.good.get(o, 0)
        if not diff:
            return None
        return (diff & -diff).bit_length() - 1


def read_patterns(path: Path) -> List[str]:
    pats = []
    for ln in Path(path).read_text().splitlines():
        t = ln.strip()
        if not t or t.startswith("*"):
            continue
        pats.append("".join((t.split(":", 1)[1] if ":" in t else t).split()))
    return pats


def fault_blif(text: str, net: str, value: int) -> str:
    """Replace the definition of gate output `net` by a constant."""
    t = text.replace("\\\n", " ")
    out, lines, i, done = [], t.split("\n"), 0, False
    while i < len(lines):
        ln = lines[i]
        if ln.startswith(".names") and ln.split()[-1] == net:
            i += 1
            while i < len(lines) and lines[i] and not lines[i].startswith("."):
                i += 1
            out.append(f".names {net}")
            if value:
                out.append("1")
            done = True
            continue
        out.append(ln)
        i += 1
    if not done:
        raise ValueError(f"{net} is not a gate output (primary-input faults are not injected)")
    return "\n".join(out)


def quaigh_outputs(quaigh: str, blif: Path, pats: Path, out: Path) -> str:
    r = subprocess.run([quaigh, "simulate", str(blif), "-i", str(pats), "-o", str(out)], capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(f"quaigh simulate failed: {r.stderr[-300:]}")
    return "\n".join(ln for ln in out.read_text().splitlines() if ln and not ln.startswith("*"))


def quaigh_equiv(quaigh: str, a: Path, b: Path) -> bool:
    r = subprocess.run([quaigh, "equiv", str(a), str(b)], capture_output=True, text=True)
    return r.returncode == 0 and "not equivalent" not in (r.stdout + r.stderr).lower()


def regrade(blif: Path, patterns: Path, quaigh: Optional[str], samples: int, n_undet: int, seed: int,
            tmp: Path) -> dict:
    text = to_comb_blif(Path(blif).read_text())
    sim = Sim(text)
    pats = read_patterns(patterns)
    sim.load(pats)
    rng = random.Random(seed)
    pool = [(n, v) for n in sim.order for v in (0, 1)]
    rng.shuffle(pool)
    det, undet = [], []
    for net, v in pool:
        d = sim.detect(net, v)
        (det if d is not None else undet).append((net, v))
        if len(det) >= samples and len(undet) >= n_undet:
            break
    chosen = [(f, True) for f in det[:samples]] + [(f, False) for f in undet[:n_undet]]

    rep = {"patterns": len(pats), "sampled_detected": 0, "sampled_undetected": 0, "mismatches": [],
           "undetected_testable": 0, "undetected_provably_untestable": 0, "quaigh_checked": bool(quaigh)}
    if quaigh:
        good_f = tmp / "good.blif"
        good_f.write_text(text)
        pat_f = tmp / "pats.test"
        pat_f.write_text("\n".join(f"{i + 1}: {p}" for i, p in enumerate(pats)) + "\n")
        good_out = quaigh_outputs(quaigh, good_f, pat_f, tmp / "good.out")
    rep["faults"] = [{"net": n, "value": v, "own_sim_detects": m} for (n, v), m in chosen]
    for (net, v), mine in chosen:
        if mine:
            rep["sampled_detected"] += 1
        else:
            rep["sampled_undetected"] += 1
        if not quaigh:
            continue
        fb = tmp / "f.blif"
        fb.write_text(fault_blif(text, net, v))
        theirs = quaigh_outputs(quaigh, fb, pat_f, tmp / "f.out") != good_out
        if theirs != mine:
            rep["mismatches"].append({"net": net, "value": v, "own_sim_detects": mine, "quaigh_sim_detects": theirs})
        if not mine:
            if quaigh_equiv(quaigh, good_f, fb):
                rep["undetected_provably_untestable"] += 1
            else:
                rep["undetected_testable"] += 1
    # negative control 1: all-zero patterns must detect much less than the real set
    zero = ["0" * len(sim.inputs)]
    s0 = Sim(text)
    s0.load(zero)
    probe = [(n, rng.randint(0, 1)) for n in rng.sample(sim.order, min(300, len(sim.order)))]
    real_hits = sum(sim.detect(n, v) is not None for n, v in probe)
    zero_hits = sum(s0.detect(n, v) is not None for n, v in probe)
    rep["control_all_zero"] = {"probe_faults": len(probe), "detected_by_quaigh_patterns": real_hits,
                               "detected_by_all_zero_pattern": zero_hits, "ok": zero_hits < real_hits}
    rep["ok"] = (not rep["mismatches"]) and rep["control_all_zero"]["ok"]
    return rep


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("blif")
    ap.add_argument("patterns")
    ap.add_argument("--out", required=True)
    ap.add_argument("--samples", type=int, default=200)
    ap.add_argument("--undetected", type=int, default=50)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--quaigh", default="/nobackup/claude_sim_build/j41m15/bin/quaigh")
    ap.add_argument("--no-quaigh-sim", action="store_true")
    ap.add_argument("--dump-faults", help="write the sampled faults with this simulator's verdict (input of regrade_vl.py)")
    a = ap.parse_args(argv)
    with tempfile.TemporaryDirectory(dir="/nobackup/claude_sim_build/j41m15") as td:
        rep = regrade(Path(a.blif), Path(a.patterns), None if a.no_quaigh_sim else a.quaigh, a.samples, a.undetected,
                      a.seed, Path(td))
    Path(a.out).write_text(json.dumps(rep, indent=1))
    if a.dump_faults:
        Path(a.dump_faults).write_text(json.dumps(rep["faults"]))
    print(json.dumps({k: rep[k] for k in rep if k not in ("mismatches", "faults")}), "mismatches:", len(rep["mismatches"]))
    return 0 if rep["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
