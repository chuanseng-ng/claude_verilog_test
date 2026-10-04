// tb_npu.sv
// Phase 6c -- standalone cocotb test wrapper for npu_top (rtl/npu/npu_top.sv, with its sub-modules
// rtl/npu/npu_mac_array.sv and rtl/npu/npu_weight_mem.sv; bead claude_verilog_test-f7vs.11).
//
// STRICT TDD: the DUT does not exist when this wrapper is written (test_npu.py is the RED half of
// the cycle). Every port and parameter name below is taken from the frozen interface contract in
// docs/PHASE6_IP_EXPANSION_PLAN.md Sec.7 "6c -- NPU", not invented.
//
// TWO DUTs, ONE WRAPPER. npu_top has a compile-time parameter, EN_NPU, whose behaviour a single
// simulation build cannot show: EN_NPU = 0 must constant-fold the block away yet still terminate
// its APB face cleanly (pready = 1, prdata = 0, pslverr = 0, irq_o = 0) or the bus would hang.
// Rather than a second Makefile target and sim build, this wrapper instantiates one DUT per
// configuration side by side, each with its own flat APB4 face distinguished by a name prefix;
// the cocotb suite drives each through APB4Master(dut, prefix, ...). clk and rst_n are shared, so
// a reset resets both. There is no interaction between the instances.
//
//   prefix   instance   configuration
//   (none)   u_dut      the defaults: ADDR_W = 12, WEIGHT_WORDS = 1024, GRID = 4, EN_NPU = 1
//   off_     u_dut_off  EN_NPU = 0  (the SoC tie-off arm; every output must be inert)
//
// NO PARAMETERS ARE EXPOSED, on purpose (same reasoning as tb_crypto.sv). A -G override of the
// primary instance that makes it identical to the fixed variant (say -GEN_NPU=0) would put two
// identically-parameterised npu_top instances in one elaboration, which Verilator can answer with
// a spurious VARHIDDEN on a module-local function -- a wrapper artefact a single instance does not
// show. The elaboration-guard check in test_npu.py therefore lints a throwaway SINGLE-instance top
// (generated at test time) instead of overriding this one.
//
// Because the EN_NPU = 0 instance is always elaborated, every ordinary `make npu_lint` / `make npu`
// also proves that the disabled arm elaborates and lints clean.
//
// npu_top has NO asynchronous input (clk / rst_n / APB4 only; irq_o is an output), so there is no
// CDC and no synchroniser in this wrapper or in the file list.
//
// Register map under test (npu_top.sv, ADDR_W = 12, N_REGS = 16) -- the full contract, including
// the decisions the plan left open, is in test_npu.py's docstring:
//   0x00  CTRL      [RW]  [0] RELU_EN, [3] IRQ_EN; [2] START is W1P and reads 0
//   0x04  STATUS    [RO]  [0] busy [1] done [2] ain_full [3] ain_empty [4] aout_valid
//                         [5] aout_full [6] cfg_rejected (sticky)
//   0x08  WADDR     [RW]  [9:0] weight-SRAM word address; auto-increments on every WDATA write
//   0x0C  WDATA     [WO]  4 packed INT8 weights -> SRAM[WADDR]; reads 0
//   0x10  TILEBASE  [RW]  [9:0] first weight word of the next inference
//   0x14  KLEN      [RW]  [5:0] number of 4-element chunks
//   0x18  SCALE     [RW]  [15:0] requantise multiplier, [20:16] right shift
//   0x1C  AIN       [WO]  4 packed INT8 activations -> AIN FIFO; reads 0
//   0x20  AOUT      [RO]  head of the AOUT FIFO (4 packed INT8 results); a READ POPS
//   0x24  IRQ_STAT  [RO]  [0] sticky done
//   0x28  IRQ_CLR   [WO]  W1C: [0] clears done, [1] clears cfg_rejected
//   0x2C-0x3C reserved (read 0, writes dropped)
//
// Lint target: verilator -Wall -Wno-IMPORTSTAR -Wno-SYNCASYNCNET -Wno-DECLFILENAME, 0 errors
// 0 warnings (DECLFILENAME is disabled only for the pre-existing sim SRAM model's file name).

`default_nettype none

module tb_npu (
    input  logic clk,
    input  logic rst_n,

    // -- u_dut: APB4 slave port (BFM-facing, flat APB4 names) ---------------
    input  logic              psel,
    input  logic              penable,
    input  logic              pwrite,
    input  logic [11:0]       paddr,
    input  logic [31:0]       pwdata,
    input  logic [3:0]        pstrb,
    output logic [31:0]       prdata,
    output logic              pready,
    output logic              pslverr,
    output logic              irq_o,

    // -- u_dut_off: EN_NPU = 0 ------------------------------------------------
    input  logic        off_psel,
    input  logic        off_penable,
    input  logic        off_pwrite,
    input  logic [11:0] off_paddr,
    input  logic [31:0] off_pwdata,
    input  logic [3:0]  off_pstrb,
    output logic [31:0] off_prdata,
    output logic        off_pready,
    output logic        off_pslverr,
    output logic        off_irq_o
);

    npu_top #(
        .ADDR_W      (12),
        .WEIGHT_WORDS(1024),
        .GRID        (4),
        .EN_NPU      (1'b1)
    ) u_dut (
        .clk    (clk),
        .rst_n  (rst_n),
        .psel   (psel),
        .penable(penable),
        .pwrite (pwrite),
        .paddr  (paddr),
        .pwdata (pwdata),
        .pstrb  (pstrb),
        .prdata (prdata),
        .pready (pready),
        .pslverr(pslverr),
        .irq_o  (irq_o)
    );

    npu_top #(
        .ADDR_W      (12),
        .WEIGHT_WORDS(1024),
        .GRID        (4),
        .EN_NPU      (1'b0)
    ) u_dut_off (
        .clk    (clk),
        .rst_n  (rst_n),
        .psel   (off_psel),
        .penable(off_penable),
        .pwrite (off_pwrite),
        .paddr  (off_paddr),
        .pwdata (off_pwdata),
        .pstrb  (off_pstrb),
        .prdata (off_prdata),
        .pready (off_pready),
        .pslverr(off_pslverr),
        .irq_o  (off_irq_o)
    );

endmodule : tb_npu

`default_nettype wire
