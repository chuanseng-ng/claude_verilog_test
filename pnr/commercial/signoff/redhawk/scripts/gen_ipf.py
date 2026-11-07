#!/usr/bin/env python3
"""gen_ipf.py <def> <pt_instance_power.txt> <out.ipf> -- RedHawk INSTANCE_POWER_FILE (<instance> <W>) from PrimePower, named as in the DEF (escape-free: that is how RedHawk matches them).
PT prints names without DEF escapes; match on the DEF name with backslashes removed.  Reports unmatched power (W) on both sides."""
import re, sys
defp, ptp, outp = sys.argv[1:4]
comp = {}
ins = False
with open(defp) as f:
    for line in f:
        if line.startswith("COMPONENTS"): ins = True; continue
        if line.startswith("END COMPONENTS"): break
        if ins:
            m = re.match(r"^\s*-\s+(\S+)\s+(\S+)", line)
            if m: comp[m.group(1).replace("\\", "")] = m.group(1)
tot = 0.0; miss = 0.0; nm = 0; n = 0; lines = []
with open(ptp) as f:
    for line in f:
        p = line.split()
        nme, w = p[0], float(p[1]); n += 1; tot += w
        d = comp.get(nme)
        if d is None: miss += w; nm += 1; continue
        lines.append("%s %.6e\n" % (nme, w))   # RedHawk reports/reads the escape-free name (ICC2 DEF has "\\/" inside flat names)
open(outp, "w").writelines(lines)
print("%s: PT cells %d (%.4f mW), matched %d, unmatched %d (%.4f mW); DEF components %d" % (defp.split('/')[-4], n, tot*1e3, len(lines), nm, miss*1e3, len(comp)))
