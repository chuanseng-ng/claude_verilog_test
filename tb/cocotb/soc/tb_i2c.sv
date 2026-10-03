// tb_i2c.sv
// Phase 6a-5 -- standalone cocotb test wrapper for i2c_controller (rtl/periph/i2c_controller.sv,
// bead claude_verilog_test-f7vs.9).
//
// Directly instantiates i2c_controller with true top-level input ports for clk/rst_n, the whole
// APB4 slave face, and BOTH sensed pad levels (i2c_scl_i / i2c_sda_i), and re-exports the
// open-drain triplet outputs and irq_o so tests can sample them every cycle. Same standalone
// pattern as tb_gpio.sv / tb_trng.sv.
//
// THE WIRED-AND IS NOT HERE. The DUT's pad-ring contract is "oe = 1 drives the line LOW, oe = 0
// releases it, an external pull-up makes a released line high, nothing on-chip drives a line
// high". The physical bus (master AND every slave AND the pull-up) is therefore modelled in the
// cocotb BFM, tb/cocotb/bfm/i2c_slave.py, which computes
//     sda_bus = (i2c_sda_oe_o ? i2c_sda_o : 1) & slave_drive
// every clock and drives the result into i2c_sda_i (same for SCL). Keeping it out of this wrapper
// means the wrapper cannot mask a polarity bug: i2c_sda_i is a plain unconnected input here.
//
// Register map under test (i2c_controller.sv, ADDR_W=12, N_REGS=12) -- see the DUT header for the
// full contract and test_i2c.py's docstring for the behaviours this suite pins:
//   0x000  I2C_CTRL      [RW]  [0] EN, [1] LOOPBACK, [11:8] RX_THR
//   0x004  I2C_STATUS    [RO]  [0] busy, [1] txn_active, [2] nack, [3] arb_lost, [4] timeout,
//                              [5] SCL level, [6] SDA level
//   0x008  I2C_CLKDIV    [RW]  [15:0], reset 0x00FF, clamped to CLKDIV_MIN in hardware
//   0x00C  I2C_ADDR      [RW]  [6:0] address, [7] R/W
//   0x010  I2C_TX_DATA   [WO]  push (write-snoop)
//   0x014  I2C_RX_DATA   [RO]  pop (read-snoop)
//   0x018  I2C_CMD       [WO]  snoop pulse
//   0x01C  I2C_FIFO_STAT [RO]  levels / full / empty
//   0x020  I2C_TIMEOUT   [RW]  [15:0] ticks, reset 0xFFFF, 0 disables
//   0x024  I2C_IRQ_EN    [RW]  [4:0]
//   0x028  I2C_IRQ_STAT  [RO]  [3:0] sticky, [4] live rx-threshold
//   0x02C  I2C_IRQ_CLR   [WO]  W1C against IRQ_STAT[3:0]
//
// CLKDIV_MIN is passed through so test_i2c.py can prove, with a separate lint-only elaboration,
// that the DUT's g_clkdiv_min_check guard refuses an unsafe override. The default (3) is the
// DUT's own default; the simulation build never overrides it.
//
// Lint target: verilator -Wall -Wno-IMPORTSTAR 0 errors 0 warnings.

`default_nettype none

module tb_i2c #(
    parameter int unsigned ADDR_W     = 12,  // 4 KB slot -- matches i2c_controller.sv
    parameter int unsigned CLKDIV_MIN = 3    // DUT default; overridden only by the guard test
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

    // -- I2C pad triplets (open-drain; *_o is dead, *_oe_o is the real control) --
    output logic i2c_scl_o,
    output logic i2c_scl_oe_o,
    input  logic i2c_scl_i,
    output logic i2c_sda_o,
    output logic i2c_sda_oe_o,
    input  logic i2c_sda_i,

    // -- Interrupt output (level-held, never a pulse) ------------------------
    output logic irq_o
);

    i2c_controller #(
        .ADDR_W    (ADDR_W),
        .CLKDIV_MIN(CLKDIV_MIN)
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

        // I2C pads
        .i2c_scl_o   (i2c_scl_o),
        .i2c_scl_oe_o(i2c_scl_oe_o),
        .i2c_scl_i   (i2c_scl_i),
        .i2c_sda_o   (i2c_sda_o),
        .i2c_sda_oe_o(i2c_sda_oe_o),
        .i2c_sda_i   (i2c_sda_i),

        // Interrupt
        .irq_o(irq_o)
    );

endmodule : tb_i2c

`default_nettype wire
