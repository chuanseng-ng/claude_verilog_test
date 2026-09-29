// tb_wdt.sv
// Phase 6a-3 -- standalone cocotb test wrapper for watchdog_timer (rtl/periph/watchdog_timer.sv,
// bead claude_verilog_test-f7vs.7). watchdog_timer DOES NOT EXIST YET as of this wrapper's
// authorship -- this is step 2 of the mandated TDD order (docs/PHASE6_IP_EXPANSION_PLAN.md
// Sec.9: "the verification orchestrator runs before the RTL orchestrator"). This file, and the
// `wdt`/`wdt_lint` Makefile targets built on it, are EXPECTED TO FAIL TO ELABORATE until
// rtl/periph/watchdog_timer.sv is written to match the contract documented here and in
// test_wdt.py.
//
// Directly instantiates watchdog_timer with true top-level input ports for clk/rst_n and the
// whole APB4 slave face, and re-exports irq_o and wdt_rst_req_o as top-level outputs so tests can
// sample them every cycle. Same standalone pattern as tb_pwm.sv / tb_gpio.sv. The WDT has NO
// async input pins at all and therefore no CDC of its own (docs/PHASE6_IP_EXPANSION_PLAN.md
// Sec.7 "6a-3 -- WDT"): the only clock domain is core_clk (== clk here).
//
// Register map under test (watchdog_timer.sv, ADDR_W=12, N_REGS=8) -- see test_wdt.py's module
// docstring for the full behavioural contract (counter/prescaler timing, magic-value feed,
// window mode, bark/bite, level-held irq_o / wdt_rst_req_o, and this suite's own decisions on
// RELOAD==0, RELOAD-write timing and COUNT read side effects):
//   0x000  WDT_CTRL      [RW]   [0] enable, [1] RST_EN (reset value 0), [2] window mode enable
//   0x004  WDT_RELOAD    [RW]   counter reload value, in prescaled ticks
//   0x008  WDT_COUNT     [RO]   live counter value
//   0x00C  WDT_WINDOW    [RW]   closed-window threshold; 0 disables the window check
//   0x010  WDT_FEED      [WO]   write 0x5A5A_C0DE to feed; any other value rejected; reads 0
//   0x014  WDT_PRESCALE  [RW]   [15:0] core_clk divider; one tick = (PRESCALE+1) clocks
//   0x018  WDT_STATUS    [RO]   [0] bark, [1] bite, [2] window violation -- all sticky
//   0x01C  WDT_IRQ_CLR   [WO]   W1C against WDT_STATUS; reads 0
//
// wdt_rst_req_o is the standalone level-held bite request. WDT_CTRL.RST_EN does NOT gate it at
// this boundary: RST_EN only arms the SoC-level cpu_domain_rst_n AND-in, a soc_top integration
// concern that is invisible here (test_wdt_rst_en_does_not_gate_wdt_rst_req pins that down).
//
// Clock/reset naming: clk/rst_n map straight through (watchdog_timer uses clk/rst_n directly,
// not pclk/presetn -- matching gpio_controller / pwm_controller).
//
// Lint target: verilator -Wall -Wno-IMPORTSTAR 0 errors 0 warnings (once the DUT exists).

`default_nettype none

module tb_wdt #(
    parameter int unsigned ADDR_W = 12  // 4 KB slot -- matches watchdog_timer.sv
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

    // -- Interrupt and reset-request outputs (both level-held, never pulses) -----
    output logic irq_o,
    output logic wdt_rst_req_o
);

    watchdog_timer #(
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

        // Outputs
        .irq_o        (irq_o),
        .wdt_rst_req_o(wdt_rst_req_o)
    );

endmodule : tb_wdt

`default_nettype wire
