// pll_axil_regs.sv
// Phase 7 (M-c) — AXI-Lite configuration slave for the PLL clock generator.
//
// Register map (byte offset, 32-bit words):
//
//   0x00  CONTROL  [RW]
//           [0]    pll_enable   — 1: assert rst_n to PLL; 0: hold PLL in reset
//           [7:4]  div_n[3:0]  — feedback divider ratio (4'h0 → N=13 default)
//           [9:8]  post_div_sel — post-divider: 2'b00→/1, 2'b01→/2, 2'b10→/4
//           [31:10] reserved (RO 0)
//
//   0x04  STATUS   [RO]
//           [0]    locked      — mirrors pll_locked_i (RO; HW-driven)
//           [31:1] reserved (RO 0)
//
//   0x08  RSVD     [RO]  — reads 0, writes ignored
//
// The module is a structural wrapper around axi_lite_register_bank.sv so all
// AXI-Lite protocol machinery (capture, BVALID/RVALID FSMs) is reused.
//
// Output ports drive the PLL wrapper:
//   pll_enable_o   — gate for PLL rst_n (0 = PLL in reset)
//   feedback_div_o — div_n field from CONTROL
//   post_div_sel_o — post_div_sel field from CONTROL
//   pll_locked_i   — status input from pll_clkgen locked_o
//
// Coding rules:
//   * No logic — structural instantiation + assign only
//   * Always-on domain (AXI-Lite clk_i): config bus runs at ref/core clock
//   * No `timescale directive
//   * `default_nettype none
//
// Lint target: verilator -Wall -Wno-IMPORTSTAR 0 errors 0 warnings.

`default_nettype none

module pll_axil_regs #(
    parameter int unsigned ADDR_W = 12   // local byte address width (4 KB slot)
) (
    input  logic clk_i,
    input  logic rst_n_i,

    // ── AXI4-Lite slave port ────────────────────────────────────────────────
    input  logic [ADDR_W-1:0] s_axil_awaddr,
    input  logic [2:0]        s_axil_awprot,
    input  logic              s_axil_awvalid,
    output logic              s_axil_awready,
    input  logic [31:0]       s_axil_wdata,
    input  logic [3:0]        s_axil_wstrb,
    input  logic              s_axil_wvalid,
    output logic              s_axil_wready,
    output logic [1:0]        s_axil_bresp,
    output logic              s_axil_bvalid,
    input  logic              s_axil_bready,
    input  logic [ADDR_W-1:0] s_axil_araddr,
    input  logic [2:0]        s_axil_arprot,
    input  logic              s_axil_arvalid,
    output logic              s_axil_arready,
    output logic [31:0]       s_axil_rdata,
    output logic [1:0]        s_axil_rresp,
    output logic              s_axil_rvalid,
    input  logic              s_axil_rready,

    // ── PLL configuration outputs ───────────────────────────────────────────
    output logic       pll_enable_o,    // 1 = PLL active (de-asserts PLL reset)
    output logic [3:0] feedback_div_o,  // div_n[3:0] from CONTROL[7:4]
    output logic [1:0] post_div_sel_o,  // post_div_sel from CONTROL[9:8]

    // ── PLL status input ────────────────────────────────────────────────────
    input  logic       pll_locked_i     // from pll_clkgen locked_o
);

    // ── Register file: 3 words ──────────────────────────────────────────────
    // Index 0: CONTROL  (RW: bits [9:0] writable, rest RO-zero)
    // Index 1: STATUS   (RO: bit[0] driven by HW)
    // Index 2: RSVD     (RO: zero)

    localparam int unsigned N_REGS = 3;

    // Per-register SW-writable bit masks
    // CONTROL: bits [9:8] post_div_sel, [7:4] div_n, [0] pll_enable
    localparam logic [31:0] WMASK [N_REGS] = '{
        32'h0000_03F1,   // CONTROL: bits [9:8],[7:4],[0] writable
        32'h0000_0000,   // STATUS:  RO
        32'h0000_0000    // RSVD:    RO
    };

    localparam logic [31:0] RESET_VAL [N_REGS] = '{
        32'h0000_0000,   // CONTROL: PLL disabled, div_n=0 (→13 default), /1
        32'h0000_0000,   // STATUS:  cleared
        32'h0000_0000    // RSVD
    };

    logic [31:0] regs_out [N_REGS];
    logic        hw_wen   [N_REGS];
    logic [31:0] hw_wdata [N_REGS];

    axi_lite_register_bank #(
        .N_REGS    (N_REGS),
        .ADDR_W    (ADDR_W),
        .RESET_VAL (RESET_VAL),
        .WMASK     (WMASK)
    ) u_regbank (
        .clk           (clk_i),
        .rst_n         (rst_n_i),
        // AXI-Lite slave
        .s_axil_awaddr (s_axil_awaddr),
        .s_axil_awprot (s_axil_awprot),
        .s_axil_awvalid(s_axil_awvalid),
        .s_axil_awready(s_axil_awready),
        .s_axil_wdata  (s_axil_wdata),
        .s_axil_wstrb  (s_axil_wstrb),
        .s_axil_wvalid (s_axil_wvalid),
        .s_axil_wready (s_axil_wready),
        .s_axil_bresp  (s_axil_bresp),
        .s_axil_bvalid (s_axil_bvalid),
        .s_axil_bready (s_axil_bready),
        .s_axil_araddr (s_axil_araddr),
        .s_axil_arprot (s_axil_arprot),
        .s_axil_arvalid(s_axil_arvalid),
        .s_axil_arready(s_axil_arready),
        .s_axil_rdata  (s_axil_rdata),
        .s_axil_rresp  (s_axil_rresp),
        .s_axil_rvalid (s_axil_rvalid),
        .s_axil_rready (s_axil_rready),
        // HW side
        .regs_o    (regs_out),
        .hw_wen_i  (hw_wen),
        .hw_wdata_i(hw_wdata)
    );

    // ── HW write: push locked status into STATUS reg each cycle ────────────
    // reg 0 (CONTROL): no HW write
    assign hw_wen  [0] = 1'b0;
    assign hw_wdata[0] = '0;
    // reg 1 (STATUS): locked bit driven by PLL
    assign hw_wen  [1] = 1'b1;
    assign hw_wdata[1] = {31'b0, pll_locked_i};
    // reg 2 (RSVD): no HW write
    assign hw_wen  [2] = 1'b0;
    assign hw_wdata[2] = '0;

    // ── Extract PLL config from CONTROL register ────────────────────────────
    // CONTROL[0]   = pll_enable
    // CONTROL[7:4] = div_n (feedback_div)
    // CONTROL[9:8] = post_div_sel
    assign pll_enable_o   = regs_out[0][0];
    assign feedback_div_o = regs_out[0][7:4];
    assign post_div_sel_o = regs_out[0][9:8];

endmodule : pll_axil_regs

`default_nettype wire
