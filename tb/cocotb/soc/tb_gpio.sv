// tb_gpio.sv
// Phase 6a — standalone cocotb test wrapper for gpio_controller (rtl/periph/gpio_controller.sv,
// bead claude_verilog_test-ckc).
//
// Directly instantiates gpio_controller with true top-level input ports for clk/rst_n and the
// whole APB4 slave face, plus a true top-level gpio_in_i input the BFM/test can drive directly
// (no RTL assign feeds it — no multiple-driver conflict), and re-exports gpio_out_o/gpio_oe_o/
// irq_o as top-level outputs so tests can sample them every cycle. Same standalone pattern as
// tb_pmu.sv / tb_pll_apb_regs.sv.
//
// Register map under test (gpio_controller.sv, ADDR_W=12) — see the DUT header for the full
// per-register behavioural contract (sync/edge latency, sticky-vs-live IRQ_STAT, etc.):
//   0x000  GPIO_DATA_IN   [RO]  live synchronised pin levels (HW-written)
//   0x004  GPIO_DATA_OUT  [RW]  output-drive value per pin
//   0x008  GPIO_DIR       [RW]  1 = pin driven as output, 0 = input
//   0x00C  GPIO_IRQ_EN    [RW]  1 = pin's IRQ event masked into irq_o
//   0x010  GPIO_IRQ_TYPE  [RW]  0 = level-sensitive, 1 = edge-sensitive
//   0x014  GPIO_IRQ_POL   [RW]  0 = active-low/falling, 1 = active-high/rising
//   0x018  GPIO_IRQ_STAT  [RO]  per-pin pending (HW-written)
//   0x01C  GPIO_IRQ_CLR   [W1C] APB-write-snoop clear (edge pins only); always reads 0
//
// Clock/reset naming: clk/rst_n map straight through (gpio_controller uses clk/rst_n directly,
// not pclk/presetn — unlike pmu/apb4_register_bank).
//
// Lint target: verilator -Wall -Wno-IMPORTSTAR 0 errors 0 warnings.

`default_nettype none

module tb_gpio #(
    parameter int unsigned ADDR_W = 12,  // 4 KB slot -- matches gpio_controller.sv
    parameter int unsigned N_PINS = 32   // number of implemented GPIO pins (<= 32)
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

    // -- GPIO pin triplet -----------------------------------------------------
    output logic [N_PINS-1:0] gpio_out_o,
    output logic [N_PINS-1:0] gpio_oe_o,
    input  logic [N_PINS-1:0] gpio_in_i,

    // -- Interrupt output -------------------------------------------------------
    output logic irq_o
);

    gpio_controller #(
        .ADDR_W(ADDR_W),
        .N_PINS(N_PINS)
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

        // GPIO pins
        .gpio_out_o(gpio_out_o),
        .gpio_oe_o (gpio_oe_o),
        .gpio_in_i (gpio_in_i),

        // Interrupt
        .irq_o(irq_o)
    );

endmodule : tb_gpio

`default_nettype wire
