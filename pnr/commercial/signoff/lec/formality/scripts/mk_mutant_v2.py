#!/usr/bin/env python3
"""mk_mutant_v2.py <in.nl.v> <out.nl.v> <mode>  -- negative-control mutants for the syn-v2 (MCMM) DC netlist, which is flat
(`u_core_*` names) and has different U-numbers than v1, so the anchors of mk_mutant.py do not apply.  Anchors are FOUND, then edited
exactly once; the script prints what it chose and fails if nothing suitable exists.
  fwdb_inv : inverter on the D pin of the forwarding-select flop *fwd_b_ex1c_r_reg (the dud4 flop class)
  swap     : swap A2<->B2 of an a22oi_1 with one data input on an ex1b_ex2_reg_q bus and the other on ex1c_comb
             (operand-forwarding mux cone, same class as v1's U1801 swap); requires A1!=B1 and A2!=B2 so the function really changes"""
import sys, re
src, dst, mode = sys.argv[1:4]
t = open(src).read()
inst = re.compile(r"  (sky130_fd_sc_hd__\w+) (\S+) \((.*?)\);", re.S)
if mode == "fwdb_inv":
    m = [x for x in inst.finditer(t) if re.search(r"fwd_b_ex1c_r_reg$", x.group(2))]
    assert len(m) == 1, len(m)
    x = m[0]
    d = re.search(r"\.D\(([^)]*)\)", x.group(3)).group(1).strip()
    new = x.group(0).replace(".D(%s)" % d, ".D(mut_n)", 1)
    new = "  wire mut_n;\n  sky130_fd_sc_hd__inv_1 mut_inv ( .A(%s), .Y(mut_n) );\n" % d + new
    t = t[:x.start()] + new + t[x.end():]
    print("fwdb_inv: flop", x.group(2), "D net", d)
elif mode == "swap":
    cands = []
    for x in inst.finditer(t):
        if x.group(1) != "sky130_fd_sc_hd__a22oi_1": continue
        p = {k: v.strip() for k, v in re.findall(r"\.(\w+)\(([^)]*)\)", x.group(3))}
        # forwarding-mux cone, like v1's U1801: an input is a pipeline-register / bypass bus of the EX stages
        if p["A1"] != p["B1"] and p["A2"] != p["B2"] and any("ex1b_ex2_reg_q" in p[k] for k in ("A2", "B2")) and any("ex1c_comb" in p[k] for k in ("A2", "B2")):
            cands.append((x, p))
    assert cands, "no a22oi_1 drives an alu_result flop D"
    x, p = cands[0]
    new = x.group(0).replace(".A2(%s)" % p["A2"], ".A2(@@B2@@)", 1).replace(".B2(%s)" % p["B2"], ".B2(%s)" % p["A2"], 1).replace("@@B2@@", p["B2"])
    assert new != x.group(0)
    t = t[:x.start()] + new + t[x.end():]
    print("swap: inst", x.group(2), "pins", p)
else:
    raise SystemExit("bad mode")
open(dst, "w").write(t)
print("mutant written:", dst, mode)
