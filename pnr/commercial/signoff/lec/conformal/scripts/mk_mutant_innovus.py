#!/usr/bin/env python3
"""mk_mutant_innovus.py <in.nl.v> <out.nl.v> <mode>  -- negative-control mutants of an Innovus netlist (B4d, parameterised for B4e).
  fwdb_inv : inverter on the D pin of flop \\u_core/fwd_b_ex1c_r_reg (dud4 forwarding-select flop class)
  swap     : swap the A1 and B1 connections of a211o_1 \\u_core/g419910 = (A1&A2)|B1|C1, the driver of the D net of ex1a_ex1b_reg_q_reg[alu_result][5]
The anchors are instance NAMES (flop names are stable; g419910 survived b5b -> b5c) but the connected nets are read from the file, so the mutant
follows net renames between runs (b5b had A1=FE_OFN18145_n_265, b5c has A1=n_265).  The script also checks, from the file, that the swapped gate's X net
is the D net of the alu_result[5] flop.  Exactly one edit; asserts each anchor occurs exactly once."""
import re, sys
src, dst, mode = sys.argv[1:4]
t = open(src).read()
if mode == "fwdb_inv":
    pat = re.compile(r"(   sky130_fd_sc_hd__dfxtp_\d \\u_core/fwd_b_ex1c_r_reg  \(\n\t\.CLK\([^\n]*\n\t\.D\()(\S+) (\),)")
    assert len(pat.findall(t)) == 1
    m = pat.search(t)
    new = ("   wire mut_n ;\n   sky130_fd_sc_hd__inv_1 mut_inv ( .A(%s ), .Y(mut_n) );\n" % m.group(2)) + m.group(1) + "mut_n" + m.group(3)
    t = t[:m.start()] + new + t[m.end():]
elif mode == "swap":
    gp = re.compile(r"   sky130_fd_sc_hd__a211o_1 \\u_core/g419910  \(\n\t\.A1\((\S+) \),\n\t\.A2\((\S+) \),\n\t\.B1\((\S+) \),\n\t\.C1\((\S+) \),\n\t\.X\((\S+) \)\);")
    assert len(gp.findall(t)) == 1
    m = gp.search(t)
    a1, a2, b1, c1, x = m.groups()
    fp = re.compile(r"\\u_core/ex1a_ex1b_reg_q_reg\[alu_result\]\[5\]  \(\n\t\.CLK\([^\n]*\n\t\.D\(" + re.escape(x) + r" \)")
    assert len(fp.findall(t)) == 1, "g419910 no longer drives alu_result[5]"
    new = m.group(0).replace(".A1(%s )" % a1, ".A1(@@ )").replace(".B1(%s )" % b1, ".B1(%s )" % a1).replace(".A1(@@ )", ".A1(%s )" % b1)
    assert new != m.group(0)
    t = t[:m.start()] + new + t[m.end():]
else:
    raise SystemExit("bad mode")
open(dst, "w").write(t)
print("mutant written:", dst, mode)
