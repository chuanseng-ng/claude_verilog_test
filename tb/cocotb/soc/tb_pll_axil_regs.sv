// tb_pll_axil_regs.sv
// Phase 7 (M-c) — standalone cocotb test wrapper for pll_axil_regs.
//
// Directly instantiates pll_axil_regs with exposed AXI4-Lite slave ports
// using the flat "s_axil_" prefix the AXI4LiteMaster BFM expects.
// Also exposes pll_locked_i as an input so the testbench can inject the
// locked signal and verify STATUS[0] mirrors it correctly.
//
// This standalone approach mirrors the pattern used for timer, UART, SPI,
// DMA, and IRQ controller (each have a standalone tb_*.sv wrapper).  It
// avoids the "BFM drives bridge-output nets" structural conflict that occurs
// when the BFM targets periph_axil_* inside the full SoC testbench
// (tb_soc_pll.sv): those signals are continuously driven by axi4_to_axilite
// assigns and cannot be overridden by cocotb value-writes in Verilator.
//
// Register map under test (pll_axil_regs.sv):
//   0x000  CONTROL [RW]  bit[0]=pll_enable, [7:4]=div_n, [9:8]=post_div_sel
//   0x004  STATUS  [RO]  bit[0]=locked (mirrors pll_locked_i)
//   0x008  RSVD    [RO]  reads 0, writes ignored
//
// Lint target: verilator -Wall -Wno-IMPORTSTAR 0 errors 0 warnings.

`default_nettype none

module tb_pll_axil_regs #(
    parameter int unsigned ADDR_W = 12   // 4 KB slot — matches pll_axil_regs
) (
    input  logic clk,
    input  logic rst_n,

    // ── AXI4-Lite slave port (BFM-facing, flat "s_axil_" prefix) ─────────────
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

    // ── PLL status injection ──────────────────────────────────────────────────
    input  logic pll_locked_i,      // drives STATUS[0] via hw_wen path

    // ── PLL config observability ──────────────────────────────────────────────
    output logic       pll_enable_o,
    output logic [3:0] feedback_div_o,
    output logic [1:0] post_div_sel_o
);

    pll_axil_regs #(
        .ADDR_W (ADDR_W)
    ) u_dut (
        .clk_i          (clk),
        .rst_n_i        (rst_n),
        // AXI4-Lite slave
        .s_axil_awaddr  (s_axil_awaddr),
        .s_axil_awprot  (s_axil_awprot),
        .s_axil_awvalid (s_axil_awvalid),
        .s_axil_awready (s_axil_awready),
        .s_axil_wdata   (s_axil_wdata),
        .s_axil_wstrb   (s_axil_wstrb),
        .s_axil_wvalid  (s_axil_wvalid),
        .s_axil_wready  (s_axil_wready),
        .s_axil_bresp   (s_axil_bresp),
        .s_axil_bvalid  (s_axil_bvalid),
        .s_axil_bready  (s_axil_bready),
        .s_axil_araddr  (s_axil_araddr),
        .s_axil_arprot  (s_axil_arprot),
        .s_axil_arvalid (s_axil_arvalid),
        .s_axil_arready (s_axil_arready),
        .s_axil_rdata   (s_axil_rdata),
        .s_axil_rresp   (s_axil_rresp),
        .s_axil_rvalid  (s_axil_rvalid),
        .s_axil_rready  (s_axil_rready),
        // PLL signals
        .pll_enable_o   (pll_enable_o),
        .feedback_div_o (feedback_div_o),
        .post_div_sel_o (post_div_sel_o),
        .pll_locked_i   (pll_locked_i)
    );

endmodule : tb_pll_axil_regs

`default_nettype wire
