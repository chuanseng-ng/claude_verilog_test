#!/usr/bin/env python3
"""name_flops_openroad.py <in.nl.v> <out.nl.v>
Yosys/OpenROAD name every flop instance anonymously (`_54171_`) but keep the name of its Q net (`\\u_core.fwd_b_ex1c_r `).  Conformal then has no name to
map on and falls back to function-based mapping of all ~6.7 k key points, which did not finish in >20 min.  This script renames each sky130_fd_sc_hd__df* instance
to `<Q net name>_reg` -- a cosmetic edit of the INSTANCE token only: no pin connection, cell type or net is touched (the script re-parses the output and asserts the
(cell type, pin->net) multiset is identical, and that every new instance name is unique).  A wrong name can only make mapping fall back to function; the compare
still decides equivalence."""
import re, sys
src, dst = sys.argv[1:3]
t = open(src).read()
pat = re.compile(r"^([ \t]*)(sky130_fd_sc_hd__df\w+)[ \t]+(\S+)[ \t]*\((.*?)\);\n", re.S | re.M)
used, n = set(), 0
def esc(s):
    s = s.strip()
    base = s[1:] if s.startswith("\\") else s
    return base
def repl(m):
    global n
    ind, cell, inst, body = m.groups()
    q = re.search(r"\.Q\(([^()]*?)\)", body)
    qn = esc(q.group(1)) if q else inst
    new = qn + "_reg"
    assert new not in used, ("duplicate", new)
    used.add(new); n += 1
    nm = "\\" + new + " " if re.search(r"[^A-Za-z0-9_$]", new) else new
    return "%s%s %s (%s);\n" % (ind, cell, nm, body)
out = pat.sub(repl, t)
def sig(s):
    return sorted((m.group(2), tuple(sorted((a, b.strip()) for a, b in re.findall(r"\.(\w+)\(([^()]*?)\)", m.group(4))))) for m in pat.finditer(s))
a = [(c, p) for c, p in sig(t)]; b = [(c, p) for c, p in sig(out)]
assert a == b, "connectivity changed"
open(dst, "w").write(out)
print("renamed %d flop instances (unique), connectivity multiset identical" % n)
