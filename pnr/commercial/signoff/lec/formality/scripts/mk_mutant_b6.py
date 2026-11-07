#!/usr/bin/env python3
"""mk_mutant_b6.py <in.nl.v> <out.nl.v> <mode> -- negative-control mutants of the ICC2 b6 netlist (flat `u_core_*` names from the DC v2 netlist, ICC2 spaced Verilog `.D ( net )`).
Anchors are FOUND and edited exactly once (the script fails if none exists).
  fwdb_inv : inverter on the D pin of the forwarding-select flop *fwd_b_ex1c_r_reg (the dud4 flop class)
  swap     : swap A2<->B2 of an a22oi_1 (all four inputs distinct nets) whose inputs mention an ex1b_ex2 / ex1c bus (operand-forwarding mux cone) -> function really changes"""
import sys, re
src, dst, mode = sys.argv[1:4]
t = open(src).read()
inst = re.compile(r"^(sky130_fd_sc_hd__\w+) (\S+) \((.*?)\) ;", re.S | re.M)
pin = lambda body: {k: v.strip() for k, v in re.findall(r"\.(\w+)\s*\(\s*([^()]*?)\s*\)", body)}
if mode == "fwdb_inv":
    m = [x for x in inst.finditer(t) if x.group(2).endswith("fwd_b_ex1c_r_reg") and x.group(1).startswith("sky130_fd_sc_hd__df")]
    assert len(m) == 1, len(m)
    x = m[0]; d = pin(x.group(3))["D"]
    new = re.sub(r"\.D\s*\(\s*" + re.escape(d) + r"\s*\)", ".D ( mut_n )", x.group(0), count=1)
    assert new != x.group(0)
    new = "wire mut_n ;\nsky130_fd_sc_hd__inv_1 mut_inv ( .A ( %s ) , .Y ( mut_n ) ) ;\n" % d + new
    t = t[:x.start()] + new + t[x.end():]
    print("fwdb_inv: flop", x.group(2), "D net", d)
elif mode == "swap":
    cands = []
    for x in inst.finditer(t):
        if x.group(1) != "sky130_fd_sc_hd__a22oi_1": continue
        p = pin(x.group(3))
        if len({p.get("A1"), p.get("A2"), p.get("B1"), p.get("B2")}) == 4 and any(("ex1b_ex2" in v or "ex1c" in v) for v in p.values()):
            cands.append((x, p))
    assert cands, "no suitable a22oi_1"
    x, p = cands[0]
    new = re.sub(r"\.A2\s*\(\s*" + re.escape(p["A2"]) + r"\s*\)", ".A2 ( @@B2@@ )", x.group(0), count=1)
    new = re.sub(r"\.B2\s*\(\s*" + re.escape(p["B2"]) + r"\s*\)", ".B2 ( %s )" % p["A2"], new, count=1).replace("@@B2@@", p["B2"])
    assert new != x.group(0)
    t = t[:x.start()] + new + t[x.end():]
    print("swap: inst", x.group(2), "pins", p)
else:
    raise SystemExit("bad mode")
open(dst, "w").write(t)
print("mutant written:", dst, mode)
