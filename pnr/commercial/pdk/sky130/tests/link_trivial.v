// Trivial netlist for commercial-tool link/load checks (part 2a): one hd flop + one SRAM macro.
// Non-ANSI port style on purpose: PrimeTime's netlist reader rejects ANSI-C headers (SVR-4).
module link_trivial (clk, d, csb0, web0, csb1, wmask0, addr0, addr1, din0, q, dout0, dout1);
  input         clk, d, csb0, web0, csb1;
  input  [3:0]  wmask0;
  input  [7:0]  addr0, addr1;
  input  [31:0] din0;
  output        q;
  output [31:0] dout0, dout1;
  sky130_fd_sc_hd__dfxtp_1 u_ff (.CLK(clk), .D(d), .Q(q));
  sky130_sram_1kbyte_1rw1r_32x256_8 u_sram (
    .clk0(clk), .csb0(csb0), .web0(web0), .wmask0(wmask0), .addr0(addr0), .din0(din0), .dout0(dout0),
    .clk1(clk), .csb1(csb1), .addr1(addr1), .dout1(dout1));
endmodule
