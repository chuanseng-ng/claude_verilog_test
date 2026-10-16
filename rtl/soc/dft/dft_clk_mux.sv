// dft_clk_mux.sv
// DFT Stage 1a (bead claude_verilog_test-j41m.2, GH #244).
//
// Test-clock bypass for one clock root: in scan mode the clock is the tester's
// test clock, otherwise the functional clock, so that every flop below the
// root is clocked from a port during test (docs/design/DFT_ARCHITECTURE.md
// sec.9.3). A module of its own, rather than an inline `?:`, so that
//   * every test-clock mux in the design has one greppable name, and the Stage 2
//     insertion step and the clock/reset controllability check can find them;
//   * CTS and STA see a single, deliberately placed cell per root.
//
// Plain 2:1 mux, deliberately NOT a glitch-free (enable-before-switch)
// switcher. sel_i is quasi-static: it is set while neither clock is running
// and not toggled while either one is, which is how the ATE or the Stage 1b TAP
// uses scan_mode. A synchronised glitch-free switch needs a clock in each source
// domain to retire the old selection and deadlocks when the functional clock is
// stopped; it belongs with the TAP (bead j41m.3), where the select is generated.
//
// Functional mode (sel_i = 0): clk_o === func_clk_i, no logic other than the mux.
//
// Sky130 SoC clock roots (bead claude_verilog_test-j41m.4, RUN_2026-10-16_04-53-49): under
// `USE_SKY130_CLKCELLS` (pnr/Makefile SKY130_SOC_SV2V_DEFINES only) every instance is a clock root that CTS
// builds a tree on (core_clk 17784 sinks, cpu_core_clk 174), so the mux is hand-instantiated:
//   sky130_fd_sc_hd__mux2_4     the 2:1 mux, same function as the `?:` below (A0 = func, A1 = scan, S = sel)
//   sky130_fd_sc_hd__clkbuf_16  root buffer driving the CTS-owned net
// Synthesis had mapped the mux to an a21bo_2 (0.18 pF at ss) that then carried ~0.30 pF of root wire and failed
// CVT.MaxCapViolations on core_clk at 4 tt/ss corners; repair_design skips clock nets, so the driver must be
// strong from synthesis on (clkbuf_16: 1.017 pF at ss). Instance names u_mux / u_root_buf are stable: they are
// listed in RSZ_DONT_TOUCH_RX in pnr/sky130/soc/config*.json. Functional mode is unchanged: clk_o follows
// func_clk_i through the mux and the buffer, with no other logic.
//
// Lint target: verilator -Wall -Wno-IMPORTSTAR 0 errors 0 warnings.

module dft_clk_mux (
    input  logic func_clk_i,
    input  logic scan_clk_i,
    input  logic sel_i,        // 1 = scan/test mode: use scan_clk_i
    output logic clk_o
);

`ifdef USE_SKY130_CLKCELLS
    logic mux_clk;
    sky130_fd_sc_hd__mux2_4    u_mux      (.A0(func_clk_i), .A1(scan_clk_i), .S(sel_i), .X(mux_clk));
    sky130_fd_sc_hd__clkbuf_16 u_root_buf (.A(mux_clk), .X(clk_o));
`else
    assign clk_o = sel_i ? scan_clk_i : func_clk_i;
`endif

endmodule : dft_clk_mux
