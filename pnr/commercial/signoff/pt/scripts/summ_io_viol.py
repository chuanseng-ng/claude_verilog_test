#!/usr/bin/env python3
"""summ_io_viol.py <run_dir>... -- reduce diag_io_viol.tcl's io_viol.tsv to io_viol_summary.tsv (kind, type, violators, skew_limited, worst_matched_slack).
skew_limited = violators with slack_matched >= 0 (the violation disappears when clk_io is aligned to the macro register's own clock arrival).
in2out paths have no macro register: counted as violators, never skew_limited.  r2r rows are ignored (not I/O)."""
import collections
import os
import sys

for d in sys.argv[1:]:
    f = os.path.join(d, "io_viol.tsv")
    n = collections.Counter(); ok = collections.Counter(); worst = {}
    for line in open(f).read().splitlines()[1:]:
        kind, tp, sp, ep, sl, ra, io, m = line.split("\t")
        if kind == "r2r":
            continue
        k = (kind, tp)
        n[k] += 1
        if m != "NA":
            mv = float(m)
            ok[k] += mv >= 0
            worst[k] = min(worst.get(k, mv), mv)
    with open(os.path.join(d, "io_viol_summary.tsv"), "w") as o:
        o.write("kind\ttype\tviolators\tskew_limited\tworst_matched_slack\n")
        for k in sorted(n):
            o.write(f"{k[0]}\t{k[1]}\t{n[k]}\t{ok[k]}\t{worst.get(k, 'NA')}\n")
