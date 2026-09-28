// tb_pwm.sv
// Phase 6a-2 -- standalone cocotb test wrapper for pwm_controller (rtl/periph/pwm_controller.sv,
// bead claude_verilog_test-f7vs.6). pwm_controller DOES NOT EXIST YET as of this wrapper's
// authorship -- this is step 2 of the mandated TDD order (docs/PHASE6_IP_EXPANSION_PLAN.md
// Sec.9: "the verification orchestrator runs before the RTL orchestrator"). This file, and the
// `pwm`/`pwm_lint` Makefile targets built on it, are EXPECTED TO FAIL TO ELABORATE until
// rtl/periph/pwm_controller.sv is written to match the contract documented here and in
// test_pwm.py.
//
// Directly instantiates pwm_controller with true top-level input ports for clk/rst_n and the
// whole APB4 slave face, and re-exports pwm_o/irq_o as top-level outputs so tests can sample them
// every cycle. Same standalone pattern as tb_gpio.sv / tb_pmu.sv. Unlike tb_gpio.sv, PWM has NO
// async input pins at all (push-pull output only, per docs/PHASE6_IP_EXPANSION_PLAN.md Sec.7
// "6a-2 -- PWM": "no oe, no async input and no CDC at all").
//
// Register map under test (pwm_controller.sv, ADDR_W=12) -- see test_pwm.py's module docstring
// for the full per-register behavioural contract (shared-period/per-channel-duty semantics,
// polarity, IRQ sticky/W1C, and this suite's own defined corner-case decisions for duty==0,
// duty>=period, and period==0):
//   0x000  PWM_CTRL      [RW]   [3:0] per-channel enable, [7:4] per-channel output polarity
//   0x004  PWM_PERIOD    [RW]   [15:0] shared period, in prescaled ticks
//   0x008  PWM_PRESCALE  [RW]   [15:0] core_clk divider; one tick = (PRESCALE+1) clocks
//   0x00C  PWM_DUTY01    [RW]   [15:0] ch0 duty, [31:16] ch1 duty
//   0x010  PWM_DUTY23    [RW]   [15:0] ch2 duty, [31:16] ch3 duty
//   0x014  PWM_IRQ_EN    [RW]   [3:0] per-channel period-wrap IRQ enable (masks irq_o only)
//   0x018  PWM_IRQ_STAT  [RO]   [3:0] sticky per-channel period-wrap
//   0x01C  PWM_IRQ_CLR   [WO]   W1C against PWM_IRQ_STAT; always reads 0
//
// Clock/reset naming: clk/rst_n map straight through (pwm_controller uses clk/rst_n directly,
// not pclk/presetn -- matching gpio_controller's convention, not apb4_register_bank's own).
//
// Lint target: verilator -Wall -Wno-IMPORTSTAR 0 errors 0 warnings (once the DUT exists).

`default_nettype none

module tb_pwm #(
    parameter int unsigned ADDR_W = 12,  // 4 KB slot -- matches pwm_controller.sv
    parameter int unsigned N_CH   = 4    // number of PWM channels (1 <= N_CH <= 8)
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

    // -- PWM channel outputs (push-pull; no oe, no async input, no CDC) --------
    output logic [N_CH-1:0] pwm_o,

    // -- Interrupt output -------------------------------------------------------
    output logic irq_o
);

    pwm_controller #(
        .ADDR_W(ADDR_W),
        .N_CH  (N_CH)
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

        // PWM channels
        .pwm_o(pwm_o),

        // Interrupt
        .irq_o(irq_o)
    );

endmodule : tb_pwm

`default_nettype wire
