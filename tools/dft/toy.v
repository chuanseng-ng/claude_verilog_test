module toy(input clka, input clkb, input rst_n, input d, output qa, output qb, output qn, output ql);
  wire a0, a1, b0, b1, n0, l0, gclk;
  // two clock domains
  sky130_fd_sc_hd__dfrtp_1 fa0 (.CLK(clka), .D(d), .RESET_B(rst_n), .Q(a0));
  sky130_fd_sc_hd__dfxtp_1 fa1 (.CLK(clka), .D(a0), .Q(a1));
  sky130_fd_sc_hd__dfxtp_1 fb0 (.CLK(clkb), .D(a1), .Q(b0));
  sky130_fd_sc_hd__dfxtp_1 fb1 (.CLK(clkb), .D(b0), .Q(b1));
  // negedge flop (dfrtn is the neg-edge cell)
  sky130_fd_sc_hd__dfrtn_1 fn0 (.CLK_N(clka), .D(a1), .RESET_B(rst_n), .Q(n0));
  // latch
  sky130_fd_sc_hd__dlxtp_1 l1 (.GATE(clkb), .D(b1), .Q(l0));
  // clock gate (no test enable) then a gated flop
  sky130_fd_sc_hd__dlclkp_1 cg (.CLK(clka), .GATE(b1), .GCLK(gclk));
  wire g0;
  sky130_fd_sc_hd__dfxtp_1 fg0 (.CLK(gclk), .D(n0), .Q(g0));
  assign qa = a1; assign qb = g0; assign qn = n0; assign ql = l0;
endmodule
