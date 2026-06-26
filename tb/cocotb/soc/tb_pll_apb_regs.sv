// tb_pll_apb_regs.sv
// Phase 7 (APB migration PR-6) — standalone cocotb test wrapper for pll_apb_regs.
//
// Directly instantiates pll_apb_regs with exposed APB4 slave ports that the
// APB4Master BFM drives.  pll_locked_i is exposed as an input so the testbench
// can inject the locked signal and verify STATUS[0] mirrors it correctly.
//
// This standalone approach follows the same pattern as tb_apb4_register_bank.sv
// and the prior tb_pll_axil_regs.sv: the BFM drives true top-level input ports,
// not nets driven by any RTL assign, so there is no multiple-driver conflict.
//
// Register map under test (pll_apb_regs.sv):
//   0x000  CONTROL [RW]  bit[0]=pll_enable, [7:4]=div_n, [9:8]=post_div_sel
//   0x004  STATUS  [RO]  bit[0]=locked (mirrors pll_locked_i)
//   0x008  RSVD    [RO]  reads 0, writes ignored
//
// Clock/reset naming:
//   clk   → pclk   inside pll_apb_regs (mapped via clk_i)
//   rst_n → presetn inside pll_apb_regs (mapped via rst_n_i)
//
// Lint target: verilator -Wall -Wno-IMPORTSTAR 0 errors 0 warnings.

`default_nettype none

module tb_pll_apb_regs #(
    parameter int unsigned ADDR_W = 12   // 4 KB slot — matches pll_apb_regs
) (
    input  logic clk,
    input  logic rst_n,

    // ── APB4 slave port (BFM-facing, flat APB4 names) ──────────────────────
    input  logic              psel,
    input  logic              penable,
    input  logic              pwrite,
    input  logic [ADDR_W-1:0] paddr,
    input  logic [31:0]       pwdata,
    input  logic [3:0]        pstrb,
    output logic [31:0]       prdata,
    output logic              pready,
    output logic              pslverr,

    // ── PLL status injection ─────────────────────────────────────────────────
    input  logic pll_locked_i,      // drives STATUS[0] via hw_wen path

    // ── PLL config observability ─────────────────────────────────────────────
    output logic       pll_enable_o,
    output logic [3:0] feedback_div_o,
    output logic [1:0] post_div_sel_o
);

    pll_apb_regs #(
        .ADDR_W (ADDR_W)
    ) u_dut (
        .clk_i         (clk),
        .rst_n_i       (rst_n),
        // APB4 slave
        .psel          (psel),
        .penable       (penable),
        .pwrite        (pwrite),
        .paddr         (paddr),
        .pwdata        (pwdata),
        .pstrb         (pstrb),
        .prdata        (prdata),
        .pready        (pready),
        .pslverr       (pslverr),
        // PLL signals
        .pll_enable_o  (pll_enable_o),
        .feedback_div_o(feedback_div_o),
        .post_div_sel_o(post_div_sel_o),
        .pll_locked_i  (pll_locked_i)
    );

endmodule : tb_pll_apb_regs

`default_nettype wire
