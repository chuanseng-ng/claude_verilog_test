#!/usr/bin/env python3
"""mk_mutant.py <in.nl.v> <out.nl.v> <mode>  -- negative-control mutants of the FINAL Genus netlist (B4b).
Adapted from ../formality/scripts/mk_mutant.py (B4a, DC instance names); re-anchored to the Genus names.
  fwdb_inv : insert an inverter on the D pin of flop fwd_b_ex1c_r_reg (the dud4 forwarding-select flop class; Genus kept the name)
  swap     : swap pins A_N and C of and3b_1 g371542 = and(!fwd_b_sel_r[0], n_13445, fwd_b_sel_r[1]) in the operand-B forwarding
             select decode (n_13445 = nor(fwd_b_ex1b2_r, fwd_b_ex1c_r)); selection code 10 now decodes as 01.
Exactly one edit is made; the script fails if the anchor text is not found exactly once.  Genus gate names (gNNNNNN) are not stable
across Genus runs: re-anchor if the netlist is regenerated (flop names are stable)."""
import sys
src, dst, mode = sys.argv[1:4]
t = open(src).read()
if mode == "fwdb_inv":
    old = "  sky130_fd_sc_hd__dfxtp_1 fwd_b_ex1c_r_reg(.CLK (clk), .D (n_13109),\n       .Q (fwd_b_ex1c_r));"
    new = ("  wire mut_n;\n  sky130_fd_sc_hd__inv_1 mut_inv (.A (n_13109), .Y (mut_n));\n"
           "  sky130_fd_sc_hd__dfxtp_1 fwd_b_ex1c_r_reg(.CLK (clk), .D (mut_n),\n       .Q (fwd_b_ex1c_r));")
elif mode == "swap":
    old = ("  sky130_fd_sc_hd__and3b_1 g371542(.A_N (fwd_b_sel_r[0]), .B (n_13445),\n"
           "       .C (fwd_b_sel_r[1]), .X (n_13535));")
    new = ("  sky130_fd_sc_hd__and3b_1 g371542(.A_N (fwd_b_sel_r[1]), .B (n_13445),\n"
           "       .C (fwd_b_sel_r[0]), .X (n_13535));")
else:
    raise SystemExit("bad mode")
assert t.count(old) == 1, (mode, t.count(old))
open(dst, "w").write(t.replace(old, new))
print("mutant written:", dst, mode)
