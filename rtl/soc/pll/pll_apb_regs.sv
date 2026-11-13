// pll_apb_regs - APB4 configuration slave for the PLL clock generator.
//
// Function: The module wraps apb4_register_bank. CONTROL is at 0x00: bit 0 pll_enable, bits 7:4 div_n, bits 9:8 post_div_sel.
//   STATUS is at 0x04: bit 0 locked mirrors pll_locked_i. The register at 0x08 reads 0 and ignores writes.
//   div_n = 0 selects N=13. post_div_sel 0, 1 and 2 select /1, /2 and /4.
//   The outputs are pll_enable_o, feedback_div_o and post_div_sel_o.
// Parameters: ADDR_W.
// Clocks and resets: clk_i is pclk. rst_n_i is presetn. It is active low and synchronous.
// Caller rules:
//   - pll_enable resets to 1 and is read-only. Firmware cannot clear it. The PLL is always enabled.
//   - The module has no `timescale directive and no `default_nettype directive.
// Doc: ds:mod:pll-apb-regs, cr:mod:pll-apb-regs

module pll_apb_regs #(
    parameter int unsigned ADDR_W = 12  // local byte address width (4 KB slot)
) (
    input logic clk_i,
    input logic rst_n_i,

    // ── APB4 slave port ─────────────────────────────────────────────────────
    // pclk = clk_i, presetn = rst_n_i (mapped inside module)
    input  logic              psel,
    input  logic              penable,
    input  logic              pwrite,
    input  logic [ADDR_W-1:0] paddr,
    input  logic [      31:0] pwdata,
    input  logic [       3:0] pstrb,
    output logic [      31:0] prdata,
    output logic              pready,
    output logic              pslverr,

    // ── PLL configuration outputs ────────────────────────────────────────────
    output logic       pll_enable_o,    // 1 = PLL active (de-asserts PLL reset)
    output logic [3:0] feedback_div_o,  // div_n[3:0] from CONTROL[7:4]
    output logic [1:0] post_div_sel_o,  // post_div_sel from CONTROL[9:8]

    // ── PLL status input ─────────────────────────────────────────────────────
    input logic pll_locked_i  // from pll_clkgen locked_o
);

    // ── Register file: 3 words ──────────────────────────────────────────────
    // Index 0: CONTROL  (RW: bits [9:0] writable, rest RO-zero)
    // Index 1: STATUS   (RO: bit[0] driven by HW)
    // Index 2: RSVD     (RO: zero)

    localparam int unsigned N_REGS = 3;

    // pll_enable (CONTROL bit 0) is not in WMASK. Firmware cannot clear it.
    localparam logic [31:0] WMASK[N_REGS] = '{
        32'h0000_03F0,  // CONTROL: bits [9:8],[7:4] writable; bit[0] non-clearable (GH #89)
        32'h0000_0000,  // STATUS:  RO
        32'h0000_0000  // RSVD:    RO
    };

    localparam logic [31:0] RESET_VAL[N_REGS] = '{
        32'h0000_0001,  // CONTROL: pll_enable=1 (default ON so SoC self-locks
                        //   at reset without firmware intervention).
                        //   div_n=0 (→N=13 default), post_div_sel=0 (→/1).
                        // bit[0] is excluded from WMASK. Firmware cannot clear pll_enable.
        32'h0000_0000,  // STATUS:  cleared
        32'h0000_0000  // RSVD
    };

    logic [31:0] regs_out[N_REGS];
    logic        hw_wen  [N_REGS];
    logic [31:0] hw_wdata[N_REGS];

    apb4_register_bank #(
        .N_REGS   (N_REGS),
        .ADDR_W   (ADDR_W),
        .RESET_VAL(RESET_VAL),
        .WMASK    (WMASK)
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
    assign hw_wen[0]      = 1'b0;
    assign hw_wdata[0]    = '0;
    // reg 1 (STATUS): locked bit driven by PLL
    assign hw_wen[1]      = 1'b1;
    assign hw_wdata[1]    = {31'b0, pll_locked_i};
    // reg 2 (RSVD): no HW write
    assign hw_wen[2]      = 1'b0;
    assign hw_wdata[2]    = '0;

    // ── Extract PLL config from CONTROL register ────────────────────────────
    // CONTROL[0]   = pll_enable
    // CONTROL[7:4] = div_n (feedback_div)
    // CONTROL[9:8] = post_div_sel
    assign pll_enable_o   = regs_out[0][0];
    assign feedback_div_o = regs_out[0][7:4];
    assign post_div_sel_o = regs_out[0][9:8];

endmodule : pll_apb_regs
