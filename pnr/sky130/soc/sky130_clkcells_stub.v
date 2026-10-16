// sky130_clkcells_stub.v
// Black-box stubs for the three sky130_fd_sc_hd library cells that the Sky130 SoC instantiates by hand on its
// clock roots (bead claude_verilog_test-j41m.4; selected by +define+USE_SKY130_CLKCELLS, see
// rtl/mem/rv32i_clock_gate.sv and rtl/soc/dft/dft_clk_mux.sv). They are in SKY130_SOC_SV_FILES so that
//   * Verilator (LibreLane Verilator.Lint, which reads only soc_top_sv2v.v and the macro blackboxes, not the
//     standard-cell models) and the yosys elaboration gate (tools/verif/synth_gate) find a definition;
//   * sv2v carries them into soc_top_sv2v.v as (* blackbox *) modules, exactly like the SRAM and CPU stubs.
// Yosys.Synthesis loads the standard-cell Liberty as -lib cells BEFORE it reads soc_top_sv2v.v, and a module that
// already exists wins over the deferred `$abstract` one, so synthesis binds these instances to the real
// library cells (the stub is never synthesised). Same mechanism as the SRAM and CPU macro stubs.
// Power pins are deliberately absent (the flow connects VPWR/VGND/VPB/VNB through the PDN, as for every other
// standard cell in the netlist).
// Pin names and functions from sky130_fd_sc_hd__tt_025C_1v80.lib:
//   sdlclkp_4  GCLK = CLK & latch_(CLK low)(GATE | SCE)           (clock_gating_integrated_cell latch_posedge_precontrol)
//   mux2_4     X = S ? A1 : A0
//   clkbuf_16  X = A

(* blackbox *)
module sky130_fd_sc_hd__sdlclkp_4 (
    input  CLK,
    input  GATE,
    input  SCE,
    output GCLK
);
endmodule

(* blackbox *)
module sky130_fd_sc_hd__mux2_4 (
    input  A0,
    input  A1,
    input  S,
    output X
);
endmodule

(* blackbox *)
module sky130_fd_sc_hd__clkbuf_16 (
    input  A,
    output X
);
endmodule
