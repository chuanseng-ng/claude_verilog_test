// rv32i_clock_gate.sv
// Glitch-free integrated clock gate for SRAM clk0 power reduction.
//
// Synthesis (__pnr__ defined by LibreLane Yosys steps): directly instantiates
// ICGx1_ASAP7_75t_R from the ASAP7 RVT SEQ liberty.  Pins: CLK (source
// clock), ENA (active-high enable, latched on low phase), SE (scan/test
// enable, = test_en), GCLK (gated output).
//
// DFT (bead claude_verilog_test-j41m.2, docs/design/DFT_ARCHITECTURE.md sec.4
// item 5): test_en forces the gate open.  In test mode every flop behind the
// gate must see the (test) clock whatever the functional enable says, or it
// is unreachable by scan and un-capturable by ATPG.  The behavioural arm
// latches (en | test_en) on the clock-low phase, i.e. the OR is in front of
// the latch exactly as in a library ICG with a scan-enable pin, so test_en
// inherits the same glitch-free guarantee as en.  test_en is quasi-static
// (a test-mode level, never toggled while the clock is running); tie it to
// 1'b0 where the gated clock feeds no scannable flop (SRAM-macro clocks).
//
// Simulation / lint (__pnr__ not defined): behavioral latch-AND model that is
// cycle-accurate and glitch-free.  Verilator LATCH warning suppressed here.

// Sky130 SoC clock roots (bead claude_verilog_test-j41m.4, Sky130 re-harden RUN_2026-10-16_04-53-49):
// `USE_SKY130_CLKCELLS` (pnr/Makefile SKY130_SOC_SV2V_DEFINES only) selects, for an instance that sets
// HARD_ROOT, a hand-instantiated library gate instead of the behavioural latch + AND:
//   sky130_fd_sc_hd__sdlclkp_4  integrated clock gate, scan-enable pin (GATE | SCE latched while CLK is low,
//                               exactly the (en | test_en) structure below)  ->  icg_gclk
//   sky130_fd_sc_hd__buf_16     root buffer, driving the net CTS owns (plain buf, not clkbuf: see CTS-0105 below)
// Why: synthesis mapped the behavioural AND to an and2_2 (max_capacitance 0.19 pF at ss) and CTS then hung
// ~0.68 pF of root wire on it (the register-tree root buffer is placed at the sink centroid, ~4 mm from the
// gate), failing CVT.MaxCapViolations at 8 corners. repair_design skips clock nets, so nothing else can fix
// it; the driver has to be right from synthesis on. buf_16 has a 5.0 pF Liberty max_capacitance at ss (clkbuf_16: 1.017 pF
// at ss, 1.53 pF at tt). It is a plain buffer, NOT a clkbuf_16, on purpose: clkbuf_16 is in CTS_CLK_BUFFERS, so TritonCTS
// sees it as an existing clock buffer and skips the net ("CTS-0105: Net cpu_gated_clk already has clock buffer ...
// Skipping...", RUN_2026-10-17_08-53-43: no clock tree built, setup WNS -130 ns). A gate whose output feeds no CTS tree (HARD_ROOT = 0) keeps the behavioural
// arm, so an unloaded gate (u_gpu_cg on the Sky130 SoC, whose GPU is a tie-off) still optimises away.
// The instance names u_icg / u_root_buf are stable on purpose: pnr/sky130/soc/config*.json lists them in
// RSZ_DONT_TOUCH_RX, and the netlist checks grep for them.

/* verilator lint_off UNOPTFLAT */
module rv32i_clock_gate #(
    // 1 = this gate is a clock root that CTS builds a tree on (only honoured under USE_SKY130_CLKCELLS).
    parameter bit HARD_ROOT = 1'b0
) (
    input  logic en,
    input  logic test_en,
    input  logic clk,
    output logic gclk
);
`ifdef FPGA_BUFGCE
    // FPGA prototype (bead hlrm.2): Xilinx 7-series global clock buffer with clock enable. CE is latched while the
    // input clock is low (same glitch-free contract as the ICG / latch+AND arms), O is a dedicated global-clock
    // tree. The board build feeds `clk` from the same MMCM output as the ungated BUFG (see fpga/nexys_video/),
    // so gated and ungated domains stay matched. Simulation / lint use the stub in rtl/fpga/sim/BUFGCE.v.
    BUFGCE u_bufgce (.I(clk), .CE(en | test_en), .O(gclk));
`elsif USE_ICG_CELL
    // USE_ICG_CELL is in VERILOG_DEFINES (Yosys) but not LINTER_DEFINES (Verilator).
    ICGx1_ASAP7_75t_R u_icg (.CLK(clk), .ENA(en), .SE(test_en), .GCLK(gclk));
`else
`ifdef USE_SKY130_CLKCELLS
    localparam bit LIB_CELLS = 1'b1;
`else
    localparam bit LIB_CELLS = 1'b0;
`endif
    localparam bit CELLS = HARD_ROOT && LIB_CELLS;
    if (CELLS) begin : g_cell
`ifdef USE_SKY130_CLKCELLS
        logic icg_gclk;
        sky130_fd_sc_hd__sdlclkp_4 u_icg      (.CLK(clk), .GATE(en), .SCE(test_en), .GCLK(icg_gclk));
        sky130_fd_sc_hd__buf_16    u_root_buf (.A(icg_gclk), .X(gclk));
`endif
    end else begin : g_beh
        logic en_latch;
        /* verilator lint_off LATCH */
        always_latch if (!clk) en_latch = en | test_en;
        /* verilator lint_on LATCH */
        assign gclk = clk & en_latch;
    end
`endif
endmodule
/* verilator lint_on UNOPTFLAT */
