// rv32i_clock_gate - Glitch-free integrated clock gate for SRAM clk0 power reduction.
//
// Function: gclk is clk gated by an enable. The enable is latched while clk is low and is (en | test_en).
//   test_en forces the gate open. The OR sits in front of the latch, so test_en has the same glitch-free guarantee as en.
//   Arms, in the order the code tests them:
//   `FPGA_BUFGCE: a Xilinx BUFGCE with CE = en | test_en. Simulation and lint use the stub rtl/fpga/sim/BUFGCE.v.
//   `USE_ICG_CELL: ICGx1_ASAP7_75t_R (CLK, ENA = en, SE = test_en, GCLK). The define is set for Yosys, not for Verilator.
//   Neither FPGA_BUFGCE nor USE_ICG_CELL defined, HARD_ROOT = 1 and `USE_SKY130_CLKCELLS: sky130_fd_sc_hd__sdlclkp_4 (u_icg), then sky130_fd_sc_hd__buf_16 (u_root_buf).
//   Neither define set, and HARD_ROOT = 0 or no `USE_SKY130_CLKCELLS: a behavioural latch and AND, cycle-accurate and glitch-free.
// Parameters: HARD_ROOT (1 = clock root with a CTS tree; used only under `USE_SKY130_CLKCELLS; default 1'b0).
// Clocks and resets: clk is the source clock. The module has no reset.
// Caller rules:
//   - Keep test_en quasi-static: a test-mode level that never toggles while the clock runs.
//   - test_en can be tied to 1'b0 where gclk feeds no scannable flop. The cache SRAM gates (SRAM_ASAP7 arm) take the cache port test_en_i, so scan and MBIST can open them.
//   - Set HARD_ROOT = 1 for a gate that is a clock root with a CTS tree. A gate with HARD_ROOT = 0 keeps the behavioural arm.
//   - Do not rename u_icg or u_root_buf. The ASAP7 SDC files match *u_icg/GCLK. The netlist checks grep for both names.
//     pnr/sky130/soc/config*.json list only u_root_buf (the one in u_cpu_cg) in RSZ_DONT_TOUCH_RX, not u_icg.
//   - u_root_buf must be a plain buf_16, not clkbuf_16. clkbuf_16 is in CTS_CLK_BUFFERS, so TritonCTS treats the net as already buffered and builds no clock tree.
// Doc: ds:mod:rv32i-clock-gate, tm:mod:rv32i-clock-gate, cr:mod:rv32i-clock-gate, tm:ch:dft-architecture

/* verilator lint_off UNOPTFLAT */
module rv32i_clock_gate #(
    // 1 = this gate is a clock root that CTS builds a tree on (only honoured under USE_SKY130_CLKCELLS).
    parameter bit HARD_ROOT = 1'b0
) (
    // Explicit `wire` on the inputs: a testbench `default_nettype none leaks into this -y-resolved file under Xcelium (*W,NODNTW)
    input  wire logic en,
    input  wire logic test_en,
    input  wire logic clk,
    output logic gclk
);
`ifdef FPGA_BUFGCE
    // FPGA prototype: Xilinx 7-series global clock buffer with clock enable. CE is latched while the
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
