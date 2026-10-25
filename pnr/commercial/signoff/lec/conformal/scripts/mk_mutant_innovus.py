#!/usr/bin/env python3
"""mk_mutant_innovus.py <in.nl.v> <out.nl.v> <mode>  -- B4d negative-control mutants of the Innovus netlist (mirrors B4c mk_mutant_icc2.py).
  fwdb_inv : inverter on the D pin of flop \\u_core/fwd_b_ex1c_r_reg (dud4 forwarding-select flop class); D net \\u_core/n_13109
  swap     : swap pins A1 and B1 of a211o_1 \\u_core/g419910 = (A1&A2)|B1|C1, the driver of the D net of ex1a_ex1b_reg_q_reg[alu_result][5]
Exactly one edit; asserts each anchor occurs exactly once.  Gate names (gNNNNNN) are not stable across tool runs: re-anchor on a new netlist."""
import re, sys
src, dst, mode = sys.argv[1:4]
t = open(src).read()
if mode == "fwdb_inv":
    old = "   sky130_fd_sc_hd__dfxtp_1 \\u_core/fwd_b_ex1c_r_reg  (\n\t.CLK(\\u_core/CTS_89 ),\n\t.D(\\u_core/n_13109 ),"
    new = ("   wire mut_n ;\n   sky130_fd_sc_hd__inv_1 mut_inv ( .A(\\u_core/n_13109 ), .Y(mut_n) );\n"
           "   sky130_fd_sc_hd__dfxtp_1 \\u_core/fwd_b_ex1c_r_reg  (\n\t.CLK(\\u_core/CTS_89 ),\n\t.D(mut_n),")
elif mode == "swap":
    old = ("   sky130_fd_sc_hd__a211o_1 \\u_core/g419910  (\n\t.A1(\\u_core/FE_OFN18145_n_265 ),\n\t.A2(\\u_core/n_4125 ),\n"
           "\t.B1(\\u_core/n_8722 ),\n\t.C1(\\u_core/n_10171 ),\n\t.X(\\u_core/n_10596 ));")
    new = ("   sky130_fd_sc_hd__a211o_1 \\u_core/g419910  (\n\t.A1(\\u_core/n_8722 ),\n\t.A2(\\u_core/n_4125 ),\n"
           "\t.B1(\\u_core/FE_OFN18145_n_265 ),\n\t.C1(\\u_core/n_10171 ),\n\t.X(\\u_core/n_10596 ));")
else:
    raise SystemExit("bad mode")
assert t.count(old) == 1, (mode, t.count(old))
open(dst, "w").write(t.replace(old, new))
print("mutant written:", dst, mode)
