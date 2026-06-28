// pll_apb_regs.sv
// Phase 7 (APB migration PR-6) — APB4 configuration slave for the PLL clock generator.
//
// Converted from pll_axil_regs.sv (AXI4-Lite) to APB4 bus protocol.
// The register map, field decode, and HW-write path are unchanged.
//
// Register map (byte offset, 32-bit words):
//
//   0x00  CONTROL  [RW]
//           [0]    pll_enable   — set-only/RO-1 (non-clearable; GH #89 anti-brick):
//                                 PLL is always enabled; firmware cannot hold PLL in reset
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
// The module is a structural wrapper around apb4_register_bank.sv so all
// APB4 protocol machinery (SETUP/ACCESS phases, pready, pslverr) is reused.
//
// Output ports drive the PLL wrapper (unchanged from pll_axil_regs):
//   pll_enable_o   — always 1 at runtime (WMASK bit[0]=0; non-clearable; GH #89)
//   feedback_div_o — div_n field from CONTROL[7:4]
//   post_div_sel_o — post_div_sel field from CONTROL[9:8]
//   pll_locked_i   — status input from pll_clkgen locked_o
//
// APB4 clock/reset mapping:
//   pclk    = clk_i   (reference clock; register block runs at ref clock)
//   presetn = rst_n_i (active-low synchronous reset)
//
// Coding rules:
//   * No logic — structural instantiation + assign only
//   * Always-on domain (clk_i): config bus runs at ref clock
//   * No `timescale directive
//   * `default_nettype none
//
// Lint target: verilator -Wall -Wno-IMPORTSTAR 0 errors 0 warnings.

`default_nettype none

module pll_apb_regs #(
    parameter int unsigned ADDR_W = 12   // local byte address width (4 KB slot)
) (
    input  logic clk_i,
    input  logic rst_n_i,

    // ── APB4 slave port ─────────────────────────────────────────────────────
    // pclk = clk_i, presetn = rst_n_i (mapped inside module)
    input  logic              psel,
    input  logic              penable,
    input  logic              pwrite,
    input  logic [ADDR_W-1:0] paddr,
    input  logic [31:0]       pwdata,
    input  logic [3:0]        pstrb,
    output logic [31:0]       prdata,
    output logic              pready,
    output logic              pslverr,

    // ── PLL configuration outputs ────────────────────────────────────────────
    output logic       pll_enable_o,    // 1 = PLL active (de-asserts PLL reset)
    output logic [3:0] feedback_div_o,  // div_n[3:0] from CONTROL[7:4]
    output logic [1:0] post_div_sel_o,  // post_div_sel from CONTROL[9:8]

    // ── PLL status input ─────────────────────────────────────────────────────
    input  logic       pll_locked_i     // from pll_clkgen locked_o
);

    // ── Register file: 3 words ──────────────────────────────────────────────
    // Index 0: CONTROL  (RW: bits [9:0] writable, rest RO-zero)
    // Index 1: STATUS   (RO: bit[0] driven by HW)
    // Index 2: RSVD     (RO: zero)

    localparam int unsigned N_REGS = 3;

    // Per-register SW-writable bit masks
    // CONTROL: bits [9:8] post_div_sel, [7:4] div_n writable.
    // bit[0] pll_enable is NOT in WMASK — non-clearable by design (GH #89 anti-brick):
    // apb4_register_bank leaves bit[0] at its reset value (1) on every write, so
    // firmware can never hold the PLL in reset and deadlock the SoC.
    localparam logic [31:0] WMASK [N_REGS] = '{
        32'h0000_03F0,   // CONTROL: bits [9:8],[7:4] writable; bit[0] non-clearable (GH #89)
        32'h0000_0000,   // STATUS:  RO
        32'h0000_0000    // RSVD:    RO
    };

    localparam logic [31:0] RESET_VAL [N_REGS] = '{
        32'h0000_0001,   // CONTROL: pll_enable=1 (default ON so SoC self-locks
                         //   at reset without firmware intervention).
                         //   div_n=0 (→N=13 default), post_div_sel=0 (→/1).
                         //   bit[0] excluded from WMASK (GH #89): firmware
                         //   cannot clear pll_enable — self-brick path unreachable.
        32'h0000_0000,   // STATUS:  cleared
        32'h0000_0000    // RSVD
    };

    logic [31:0] regs_out [N_REGS];
    logic        hw_wen   [N_REGS];
    logic [31:0] hw_wdata [N_REGS];

    apb4_register_bank #(
        .N_REGS    (N_REGS),
        .ADDR_W    (ADDR_W),
        .RESET_VAL (RESET_VAL),
        .WMASK     (WMASK)
    ) u_regbank (
        .pclk      (clk_i),
        .presetn   (rst_n_i),
        // APB4 slave
        .psel      (psel),
        .penable   (penable),
        .pwrite    (pwrite),
        .paddr     (paddr),
        .pwdata    (pwdata),
        .pstrb     (pstrb),
        .prdata    (prdata),
        .pready    (pready),
        .pslverr   (pslverr),
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

endmodule : pll_apb_regs

`default_nettype wire
