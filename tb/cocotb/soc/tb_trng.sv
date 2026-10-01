// tb_trng.sv
// Phase 6a-4 -- standalone cocotb test wrapper for trng (rtl/periph/trng.sv, bead
// claude_verilog_test-f7vs.8). trng DOES NOT EXIST YET as of this wrapper's authorship -- this is
// step 2 of the mandated TDD order (docs/PHASE6_IP_EXPANSION_PLAN.md Sec.9: "the verification
// orchestrator runs before the RTL orchestrator"). This file, and the `trng`/`trng_lint`
// Makefile targets built on it, are EXPECTED TO FAIL TO ELABORATE until rtl/periph/trng.sv is
// written to match the contract documented here and in test_trng.py.
//
// Directly instantiates trng with true top-level input ports for clk/rst_n and the whole APB4
// slave face, and re-exports irq_o as the only extra top-level output so tests can sample it every
// cycle. Same standalone pattern as tb_wdt.sv / tb_pwm.sv / tb_gpio.sv.
//
// The TRNG has NO top-level pins at all beyond the bus and irq_o (docs/PHASE6_IP_EXPANSION_PLAN.md
// Sec.7 "6a-4 -- TRNG"): the entropy source is swapped by `ifdef TRNG_RO_SKY130 INSIDE trng.sv,
// not by a port, so this wrapper -- and every SoC file list -- is identical for both arms. This
// wrapper deliberately does NOT define TRNG_RO_SKY130: it verifies the DEFAULT (LFSR) arm, the
// only one that is deterministic. There is no async input and therefore no CDC of its own in the
// LFSR arm; the only clock domain is core_clk (== clk here).
//
// Register map under test (trng.sv, ADDR_W=12, N_REGS=8) -- see test_trng.py's module docstring
// for the full behavioural contract (LFSR/von Neumann pipeline, FIFO, pop-on-read, health test,
// level-held irq_o, and this suite's decisions on empty reads, SEED timing and health-failure
// behaviour):
//   0x000  TRNG_CTRL     [RW]   [0] enable, [1] IRQ enable, [5:2] FIFO threshold
//   0x004  TRNG_STATUS   [RO]   [0] data ready, [1] FIFO full, [2] health_fail (sticky),
//                               [3] INSECURE (reads 1 in this build)
//   0x008  TRNG_DATA     [RO]   read pops one 32-bit word from the 4-deep FIFO (read-snoop)
//   0x00C  TRNG_SEED     [RW]   LFSR seed, sampled at the CTRL.ENABLE 0->1 edge
//   0x010  TRNG_IRQ_CLR  [WO]   W1C against STATUS.health_fail (bit 2); reads 0
//   0x014-0x01C          reserved, read 0
//
// Clock/reset naming: clk/rst_n map straight through (trng uses clk/rst_n directly, not
// pclk/presetn -- matching gpio_controller / pwm_controller / watchdog_timer).
//
// Lint target: verilator -Wall -Wno-IMPORTSTAR 0 errors 0 warnings (once the DUT exists).

`default_nettype none

module tb_trng #(
    parameter int unsigned ADDR_W = 12  // 4 KB slot -- matches trng.sv
) (
    input  logic clk,
    input  logic rst_n,

    // -- APB4 slave port (BFM-facing, flat APB4 names) ----------------------
    input  logic              psel,
    input  logic              penable,
    input  logic              pwrite,
    input  logic [ADDR_W-1:0] paddr,
    input  logic [31:0]       pwdata,
    input  logic [3:0]        pstrb,
    output logic [31:0]       prdata,
    output logic              pready,
    output logic              pslverr,

    // -- Interrupt output (level-held, never a pulse) ------------------------
    output logic irq_o
);

    trng #(
        .ADDR_W(ADDR_W)
    ) u_dut (
        .clk  (clk),
        .rst_n(rst_n),

        // APB4 slave
        .psel   (psel),
        .penable(penable),
        .pwrite (pwrite),
        .paddr  (paddr),
        .pwdata (pwdata),
        .pstrb  (pstrb),
        .prdata (prdata),
        .pready (pready),
        .pslverr(pslverr),

        // Interrupt
        .irq_o(irq_o)
    );

endmodule : tb_trng

`default_nettype wire
