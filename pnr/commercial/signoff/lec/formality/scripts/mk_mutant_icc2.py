#!/usr/bin/env python3
"""mk_mutant_icc2.py <in.nl.v> <out.nl.v> <mode>  -- negative-control mutants of the ICC2 netlist (B4c).
  fwdb_inv : inverter inserted on the D pin of flop \\u_core/fwd_b_ex1c_r_reg (dud4 forwarding-select flop class)
  swap     : swap pins A1 and C1 of o221ai_1 \\u_core/U2793, the driver of the D net of ex1a_ex1b alu_result[5]
Exactly one edit; asserts the anchor occurs exactly once."""
import sys, re
src, dst, mode = sys.argv[1:4]
t = open(src).read()
if mode == "fwdb_inv":
    pat = re.compile(r"(sky130_fd_sc_hd__dfxtp_\d \\u_core/fwd_b_ex1c_r_reg \( \.D \( )(\S+)( \))")
    assert len(pat.findall(t)) == 1
    m = pat.search(t)
    dnet = m.group(2)
    new = ("wire mut_n ;\nsky130_fd_sc_hd__inv_1 mut_inv ( .A ( %s ) , .Y ( mut_n ) ) ;\n" % dnet) + m.group(1) + "mut_n" + m.group(3)
    t = t[:m.start()] + new + t[m.end():]
elif mode == "swap":
    pat = re.compile(r"(sky130_fd_sc_hd__o221ai_1 \\u_core/U2793 \(.*?\) ;)", re.S)
    ms = pat.findall(t)
    assert len(ms) == 1
    old = ms[0]
    a1 = re.search(r"\.A1 \( (\S+) \)", old).group(1)
    c1 = re.search(r"\.C1 \( (\S+) \)", old).group(1)
    new = old.replace(".A1 ( %s )" % a1, ".A1 ( @@ )").replace(".C1 ( %s )" % c1, ".C1 ( %s )" % a1).replace(".A1 ( @@ )", ".A1 ( %s )" % c1)
    assert new != old
    t = t.replace(old, new)
else:
    raise SystemExit("bad mode")
open(dst, "w").write(t)
print("mutant written:", dst, mode)
