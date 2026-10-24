#!/usr/bin/env python3
# ruff: noqa: E501
"""Replace the auto-created dft_cell_selection in the raw .tcelllib with a curated sky130_fd_sc_hd selection.
Usage: mk_tcelllib.py raw.tcelllib out.tcelllib"""
import re
import sys

P = "sky130_fd_sc_hd__"
SEL = f"""dft_cell_selection ( sky130hd ) (
  clock_buffer = {P}clkbuf_4;
  clock_inverter = {P}clkinv_2;
  clock_mux = {P}mux2_2;
  clock_and = {P}and2_2;
  clock_or = {P}or2_2;
  clock_gating_and = {P}sdlclkp_4;
  buffer = {P}buf_2;
  inverter = {P}inv_2;
  and = {P}and2_2 , {P}and3_2 , {P}and4_2;
  and = /* 1 inverting input */ {P}and2b_2 , {P}and3b_2 , {P}and4b_2;
  nand = {P}nand2_2 , {P}nand3_2 , {P}nand4_2;
  or = {P}or2_2 , {P}or3_2 , {P}or4_2;
  or = /* 1 inverting input */ {P}or2b_2 , {P}or3b_2 , {P}or4b_2;
  nor = {P}nor2_2 , {P}nor3_2 , {P}nor4_2;
  xor = {P}xor2_1 , {P}xor3_1;
  mux = {P}mux2_2 , {P}mux4_2;
  posedge_dff = {P}dfxtp_1 , {P}dfrtp_1 /*reset*/ , {P}dfstp_1 /*set*/ , {P}dfbbp_1 /*set & reset*/ ;
  negedge_dff = {P}dfrtn_1 /*reset*/ , {P}dfbbn_1 /*set & reset*/ ;
  active_high_latch = {P}dlxtp_1 , {P}dlrtp_1 /*reset*/ ;
  active_low_latch = {P}dlxtn_1 , {P}dlrtn_1 /*reset*/ ;
  posedge_scan_cell = {P}sdfxtp_1 , {P}sdfrtp_1 /*reset*/ , {P}sdfstp_1 /*set*/ , {P}sdfbbp_1 /*set & reset*/ ;
  negedge_scan_cell = {P}sdfrtn_1 /*reset*/ , {P}sdfbbn_1 /*set & reset*/ ;
) // end dft_cell_selection
"""
src = open(sys.argv[1]).read()
new, n = re.subn(r"dft_cell_selection \( \w+ \) \(.*?\) // end dft_cell_selection\n", SEL.replace("\\", "\\\\"), src, flags=re.S)
if n != 1:
    sys.exit("mk_tcelllib: expected exactly one dft_cell_selection, found %d" % n)
open(sys.argv[2], "w").write(new)
print("mk_tcelllib: curated dft_cell_selection written")
