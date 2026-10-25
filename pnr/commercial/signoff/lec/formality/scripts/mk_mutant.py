#!/usr/bin/env python3
"""mk_mutant.py <in.nl.v> <out.nl.v> <mode>   -- negative-control netlist mutants for the B4a LEC.
  fwdb_inv : insert an inverter on the D pin of flop fwd_b_ex1c_r_reg (the dud4 forwarding-select flop class)
  swap     : swap the two DATA inputs (A2<->B2) of the a22oi_1 instance U1801 in the operand-B forwarding mux cone
Exactly one edit is made; the script fails if the anchor text is not found exactly once."""
import sys, re
src, dst, mode = sys.argv[1:4]
t = open(src).read()
if mode == "fwdb_inv":
    a = ".D(N1438), .CLK(clk), .Q(\n        fwd_b_ex1c_r) );"
    assert t.count("sky130_fd_sc_hd__dfxtp_1 fwd_b_ex1c_r_reg ( " + a) == 1
    t = t.replace("fwd_b_ex1c_r_reg ( .D(N1438)", "fwd_b_ex1c_r_reg ( .D(mut_n)")
    t = t.replace("  sky130_fd_sc_hd__dfxtp_1 fwd_b_ex1c_r_reg ( .D(mut_n)",
                  "  sky130_fd_sc_hd__inv_1 mut_inv ( .A(N1438), .Y(mut_n) );\n  sky130_fd_sc_hd__dfxtp_1 fwd_b_ex1c_r_reg ( .D(mut_n)")
    t = t.replace("module rv32i_core_00000000", "module rv32i_core_00000000", 1)
    # declare the new wire in the module that holds the flop: add right before the inverter instance
    t = t.replace("  sky130_fd_sc_hd__inv_1 mut_inv", "  wire mut_n;\n  sky130_fd_sc_hd__inv_1 mut_inv", 1)
elif mode == "swap":
    old = "sky130_fd_sc_hd__a22oi_1 U1801 ( .A1(n14522), .A2(ex1b_ex2_reg_q[152]), .B1(\n        n14527), .B2(ex1c_comb[251]), .Y(n1496) );"
    new = "sky130_fd_sc_hd__a22oi_1 U1801 ( .A1(n14522), .A2(ex1c_comb[251]), .B1(\n        n14527), .B2(ex1b_ex2_reg_q[152]), .Y(n1496) );"
    assert t.count(old) == 1
    t = t.replace(old, new)
else:
    raise SystemExit("bad mode")
open(dst, "w").write(t)
print("mutant written:", dst, mode)
