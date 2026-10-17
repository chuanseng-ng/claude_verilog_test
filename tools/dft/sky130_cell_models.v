// Models for check_scan_clk_rst.py on the Sky130 SoC netlist (pnr/sky130/soc/soc_top_sv2v.v), which hand-instantiates
// three library cells on its clock roots (bead j41m.4, +define+USE_SKY130_CLKCELLS) and carries only empty
// (* blackbox *) stubs of them (pnr/sky130/soc/sky130_clkcells_stub.v). Analysis only: never part of any synthesis or
// simulation file list. Read BEFORE the netlist, so these definitions win over the deferred blackbox stubs.
//
//   sky130_fd_sc_hd__sdlclkp_4  library integrated clock gate. The latch is transparent while CLK is low and its D input is
//                               GATE | SCE, exactly the structure rv32i_clock_gate's behavioural arm builds, so the checker
//                               can see that the enable cone contains the scan-mode term (SCE = test_en).
//   sky130_fd_sc_hd__mux2_4     the dft_clk_mux 2:1 mux (X = S ? A1 : A0); scan mode selects the test clock.
//   sky130_fd_sc_hd__buf_16     root buffer (plain buffer, not a clkbuf: CTS-0105, see rv32i_clock_gate.sv).
module sky130_fd_sc_hd__sdlclkp_4 (
    input  CLK,
    input  GATE,
    input  SCE,
    output GCLK
);
  reg en_l;
  always @* if (!CLK) en_l = GATE | SCE;
  assign GCLK = CLK & en_l;
endmodule

module sky130_fd_sc_hd__mux2_4 (
    input  A0,
    input  A1,
    input  S,
    output X
);
  assign X = S ? A1 : A0;
endmodule

module sky130_fd_sc_hd__buf_16 (
    input  A,
    output X
);
  assign X = A;
endmodule
