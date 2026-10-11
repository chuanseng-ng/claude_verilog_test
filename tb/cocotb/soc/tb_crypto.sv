// tb_crypto.sv
// Phase 6b -- standalone cocotb test wrapper for crypto_accel (rtl/periph/crypto_accel.sv, with
// its sub-cores rtl/periph/aes128_core.sv and rtl/periph/sha256_core.sv; bead
// claude_verilog_test-f7vs.10).
//
// STRICT TDD: the DUT does not exist when this wrapper is written (test_crypto.py is the RED half
// of the cycle). Every port and parameter name below is taken from the frozen microarchitecture
// contract for the peripheral, not invented.
//
// FOUR DUTs, ONE WRAPPER. crypto_accel has three compile-time parameters whose behaviour a single
// simulation build cannot show: SBOX_PARALLEL (11 vs 41 cycles per AES block -- the pre-documented
// Gate A area fallback, which must be BIT-IDENTICAL), EN_AES = 0 and EN_SHA = 0 (a mode whose core
// is compiled out must complete hang-free on the 2-cycle zero-length path). Rather than three more
// Makefile targets and three more sim builds, this wrapper instantiates one DUT per configuration
// side by side, each with its own flat APB4 face distinguished by a name prefix; the cocotb
// suite drives each through APB4Master(dut, prefix, ...). clk and rst_n are shared, so a reset
// resets all four. There is no interaction between the instances.
//
//   prefix       instance   configuration
//   (none)       u_dut      the defaults: ADDR_W = 12, EN_AES = EN_SHA = 1, SBOX_PARALLEL = 16
//   v4_          u_dut_v4   SBOX_PARALLEL = 4  (the 4-S-box fallback; EN_AES = EN_SHA = 1)
//   noaes_       u_dut_na   EN_AES = 0         (SHA-only build)
//   nosha_       u_dut_ns   EN_SHA = 0         (AES-only build)
//
// NO PARAMETERS ARE EXPOSED, on purpose. A -G override of the primary instance that makes it
// identical to one of the fixed variants (say -GEN_AES=0) puts two identically-parameterised
// crypto_accel instances in one elaboration, and Verilator then reports a spurious VARHIDDEN on
// crypto_accel's local strb_expand function -- a wrapper artefact that a single instance does not
// show. The elaboration-guard checks in test_crypto.py therefore lint a throwaway SINGLE-instance
// top (generated at test time) instead of overriding this one.
//
// Because the three fixed-configuration instances are always elaborated, every ordinary
// `make crypto_lint` / `make crypto` also proves that EN_AES = 0, EN_SHA = 0 and SBOX_PARALLEL = 4
// each elaborate and lint clean.
//
// crypto_accel has NO asynchronous input (clk / rst_n / APB4 only; irq_o is an output), so there is
// no CDC and no synchroniser in this wrapper or in the file list.
//
// Register map under test (crypto_accel.sv, ADDR_W = 12, N_REGS = 32) -- the full contract is in
// test_crypto.py's docstring:
//   0x000  CRYPTO_CTRL      [RW]  [1:0] mode, [3] IRQ enable, [4] SHA_CONT; [2] start is W1P
//   0x004  CRYPTO_STATUS    [RO]  [0] busy, [1] done, [2] key_valid, [3] key_write_rejected
//   0x008-0x014  KEY0-3     [WO]  shadow-registered; always reads 0
//   0x018-0x024  IV0-3      [RW]  CTR counter block
//   0x028-0x034  DIN0-3     [WO]  4-word aperture onto one shift register
//   0x038-0x044  DOUT0-3    [RO]  AES output block
//   0x048-0x064  DIGEST0-7  [RO]  SHA-256 digest / chaining value
//   0x068  CRYPTO_IRQ_STAT  [RO]  sticky done
//   0x06C  CRYPTO_IRQ_CLR   [WO]  W1C: [0] done, [1] key_write_rejected
//   0x070-0x07C  reserved
//
// Lint target: verilator -Wall -Wno-IMPORTSTAR -Wno-SYNCASYNCNET 0 errors 0 warnings.

`default_nettype none

module tb_crypto (
    input  logic clk,
    input  logic rst_n,

    // DFT scan mode (bead j41m.2) -- main instance only; the other three are tied 0. 0 = functional.
    input  logic scan_mode_i,

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

    // -- u_dut_v4: SBOX_PARALLEL = 4 ----------------------------------------
    input  logic        v4_psel,
    input  logic        v4_penable,
    input  logic        v4_pwrite,
    input  logic [11:0] v4_paddr,
    input  logic [31:0] v4_pwdata,
    input  logic [3:0]  v4_pstrb,
    output logic [31:0] v4_prdata,
    output logic        v4_pready,
    output logic        v4_pslverr,
    output logic        v4_irq_o,

    // -- u_dut_na: EN_AES = 0 -------------------------------------------------
    input  logic        noaes_psel,
    input  logic        noaes_penable,
    input  logic        noaes_pwrite,
    input  logic [11:0] noaes_paddr,
    input  logic [31:0] noaes_pwdata,
    input  logic [3:0]  noaes_pstrb,
    output logic [31:0] noaes_prdata,
    output logic        noaes_pready,
    output logic        noaes_pslverr,
    output logic        noaes_irq_o,

    // -- u_dut_ns: EN_SHA = 0 -------------------------------------------------
    input  logic        nosha_psel,
    input  logic        nosha_penable,
    input  logic        nosha_pwrite,
    input  logic [11:0] nosha_paddr,
    input  logic [31:0] nosha_pwdata,
    input  logic [3:0]  nosha_pstrb,
    output logic [31:0] nosha_prdata,
    output logic        nosha_pready,
    output logic        nosha_pslverr,
    output logic        nosha_irq_o
);

    crypto_accel #(
        .ADDR_W       (12),
        .EN_AES       (1'b1),
        .EN_SHA       (1'b1),
        .SBOX_PARALLEL(16)
    ) u_dut (
        .clk    (clk),
        .rst_n  (rst_n),
        .scan_mode_i (scan_mode_i),
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

    crypto_accel #(
        .ADDR_W       (12),
        .EN_AES       (1'b1),
        .EN_SHA       (1'b1),
        .SBOX_PARALLEL(4)
    ) u_dut_v4 (
        .clk    (clk),
        .rst_n  (rst_n),
        .scan_mode_i (1'b0),
        .psel   (v4_psel),
        .penable(v4_penable),
        .pwrite (v4_pwrite),
        .paddr  (v4_paddr),
        .pwdata (v4_pwdata),
        .pstrb  (v4_pstrb),
        .prdata (v4_prdata),
        .pready (v4_pready),
        .pslverr(v4_pslverr),
        .irq_o  (v4_irq_o)
    );

    crypto_accel #(
        .ADDR_W       (12),
        .EN_AES       (1'b0),
        .EN_SHA       (1'b1),
        .SBOX_PARALLEL(16)
    ) u_dut_na (
        .clk    (clk),
        .rst_n  (rst_n),
        .scan_mode_i (1'b0),
        .psel   (noaes_psel),
        .penable(noaes_penable),
        .pwrite (noaes_pwrite),
        .paddr  (noaes_paddr),
        .pwdata (noaes_pwdata),
        .pstrb  (noaes_pstrb),
        .prdata (noaes_prdata),
        .pready (noaes_pready),
        .pslverr(noaes_pslverr),
        .irq_o  (noaes_irq_o)
    );

    crypto_accel #(
        .ADDR_W       (12),
        .EN_AES       (1'b1),
        .EN_SHA       (1'b0),
        .SBOX_PARALLEL(16)
    ) u_dut_ns (
        .clk    (clk),
        .rst_n  (rst_n),
        .scan_mode_i (1'b0),
        .psel   (nosha_psel),
        .penable(nosha_penable),
        .pwrite (nosha_pwrite),
        .paddr  (nosha_paddr),
        .pwdata (nosha_pwdata),
        .pstrb  (nosha_pstrb),
        .prdata (nosha_prdata),
        .pready (nosha_pready),
        .pslverr(nosha_pslverr),
        .irq_o  (nosha_irq_o)
    );

endmodule : tb_crypto

`default_nettype wire
