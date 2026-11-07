#!/usr/bin/env python3
"""correlate.py <ref.tsv> <test.tsv> [label]  -- StarRC (test) vs OpenRCX (ref), per net, ratio = test/ref.

Gate population: nets present in both with ref total C > 1 fF.  Prints a markdown row block.
Metrics: median, p5, p95 of the ratio, Pearson r (linear and log-log), count outside +-10 %, totals.
"""
import sys, numpy as np

def load(p):
    d = {}
    with open(p) as f:
        next(f)
        for l in f:
            n, c, g, cc, r, k = l.rstrip("\n").split("\t")
            d[n] = (float(c), float(g), float(cc), float(r), int(k))
    return d

def stat(label, a, b):
    ratio = b / a
    med = np.median(ratio); p5, p95 = np.percentile(ratio, [5, 95])
    r_lin = np.corrcoef(a, b)[0, 1]
    r_log = np.corrcoef(np.log(a), np.log(b))[0, 1]
    out = int(np.sum((ratio < 0.9) | (ratio > 1.1)))
    return "| %s | %d | %.3f | %.3f | %.3f | %.4f | %.4f | %d (%.1f %%) |" % (
        label, len(a), med, p5, p95, r_lin, r_log, out, 100.0 * out / len(a))

ref = load(sys.argv[1]); tst = load(sys.argv[2]); lab = sys.argv[3] if len(sys.argv) > 3 else ""
common = [n for n in ref if n in tst]
print("nets ref=%d test=%d common=%d only_ref=%d only_test=%d" % (
    len(ref), len(tst), len(common), len(ref) - len(common), len(tst) - len(common)))
sel = [n for n in common if ref[n][0] > 1.0]
print("gate population (ref total C > 1 fF): %d nets" % len(sel))
C0 = np.array([ref[n][0] for n in sel]); C1 = np.array([tst[n][0] for n in sel])
G0 = np.array([ref[n][1] for n in sel]); G1 = np.array([tst[n][1] for n in sel])
R0 = np.array([ref[n][3] for n in sel]); R1 = np.array([tst[n][3] for n in sel])
print("| quantity (%s) | nets | median | p5 | p95 | r (lin) | r (log-log) | outside +-10 %% |" % lab)
print("|---|---|---|---|---|---|---|---|")
print(stat("total C", C0, C1))
print(stat("ground C", G0, G1))
m = (R0 > 0) & (R1 > 0)
print(stat("total R (nets with R>0 both)", R0[m], R1[m]))
S0 = np.array([ref[n][2] / ref[n][0] for n in sel]); S1 = np.array([tst[n][2] / tst[n][0] for n in sel])
print("coupling share per net (cc/total), nets with ref C > 1 fF: median ref %.3f test %.3f (diff %+.1f points), p25/p75 ref %.3f/%.3f test %.3f/%.3f" % (
    np.median(S0), np.median(S1), 100 * (np.median(S1) - np.median(S0)), *np.percentile(S0, [25, 75]), *np.percentile(S1, [25, 75])))
tc0 = sum(v[0] for v in ref.values()); tc1 = sum(v[0] for v in tst.values())
tg0 = sum(v[1] for v in ref.values()); tg1 = sum(v[1] for v in tst.values())
cc0 = sum(v[2] for v in ref.values()) / 2; cc1 = sum(v[2] for v in tst.values()) / 2
tr0 = sum(v[3] for v in ref.values()); tr1 = sum(v[3] for v in tst.values())
print("total design (all nets): C ref %.1f pF, test %.1f pF, ratio %.3f | ground C %.1f vs %.1f pF (%.3f) | "
      "coupling C %.1f vs %.1f pF (%.3f) | sum R %.3g vs %.3g ohm (%.3f)" % (
      tc0 / 1e3, tc1 / 1e3, tc1 / tc0, tg0 / 1e3, tg1 / 1e3, tg1 / tg0, cc0 / 1e3, cc1 / 1e3, cc1 / cc0 if cc0 else 0,
      tr0, tr1, tr1 / tr0))
print("coupling fraction of total C: ref %.3f test %.3f" % (2 * cc0 / tc0, 2 * cc1 / tc1))
