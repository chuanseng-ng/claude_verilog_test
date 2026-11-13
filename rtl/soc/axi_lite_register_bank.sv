// axi_lite_register_bank - AXI4-Lite slave with N_REGS 32-bit registers.
//
// Function: The bank has one AXI4-Lite slave port. It allows one outstanding write and one outstanding read.
//   The module captures AW and W independently and commits them together.
//   Software writes obey WMASK and wstrb. Only masked bits change. WMASK=0 makes a register read-only to software.
//   Hardware writes use hw_wen_i and hw_wdata_i. They bypass WMASK. regs_o shows the current values.
// Parameters: N_REGS, ADDR_W, DW, SW, RESET_VAL and WMASK.
// Clocks and resets: clk is the clock. rst_n is the reset.
// Caller rules:
//   - On a same-cycle software and hardware write, software wins inside WMASK and hardware wins outside it.
//     A register with WMASK=0 is owned by hardware.
//   - A write outside the range completes with OKAY and is dropped. A read outside the range returns 0.
// Doc: ds:mod:axi-lite-register-bank, cr:mod:axi-lite-register-bank

module axi_lite_register_bank #(
    parameter int unsigned N_REGS = 16,
    parameter int unsigned ADDR_W = 12,                       // local byte address
    parameter int unsigned DW     = axi_pkg::AXI_DATA_WIDTH,
    parameter int unsigned SW     = axi_pkg::AXI_STRB_WIDTH,
    parameter logic [31:0] RESET_VAL [N_REGS] = '{default: '0},
    // Per-register writable-bit mask (1 = SW-writable).  Default: all writable.
    parameter logic [31:0] WMASK    [N_REGS] = '{default: '1}
) (
    input  logic clk,
    input  logic rst_n,

    // ══ AXI4-Lite slave port ══════════════════════════════════════════════════
    // Write address (byte offset bits [1:0] unused: word-aligned register file)
    /* verilator lint_off UNUSEDSIGNAL */
    input  logic [ADDR_W-1:0] s_axil_awaddr,
    input  logic [2:0]        s_axil_awprot,
    /* verilator lint_on  UNUSEDSIGNAL */
    input  logic              s_axil_awvalid,
    output logic              s_axil_awready,
    // Write data
    input  logic [DW-1:0]     s_axil_wdata,
    input  logic [SW-1:0]     s_axil_wstrb,
    input  logic              s_axil_wvalid,
    output logic              s_axil_wready,
    // Write response
    output logic [1:0]        s_axil_bresp,
    output logic              s_axil_bvalid,
    input  logic              s_axil_bready,
    // Read address (byte offset bits [1:0] unused: word-aligned register file)
    /* verilator lint_off UNUSEDSIGNAL */
    input  logic [ADDR_W-1:0] s_axil_araddr,
    input  logic [2:0]        s_axil_arprot,
    /* verilator lint_on  UNUSEDSIGNAL */
    input  logic              s_axil_arvalid,
    output logic              s_axil_arready,
    // Read data
    output logic [DW-1:0]     s_axil_rdata,
    output logic [1:0]        s_axil_rresp,
    output logic              s_axil_rvalid,
    input  logic              s_axil_rready,

    // ══ Hardware side ═════════════════════════════════════════════════════════
    output logic [31:0] regs_o    [N_REGS],   // current register values
    input  logic        hw_wen_i  [N_REGS],   // hardware write enable (per reg)
    input  logic [31:0] hw_wdata_i[N_REGS]    // hardware write data (bypasses WMASK)
);

    import axi_pkg::*;

    // Static checks: module storage is fixed at 32-bit words with 4-byte
    // strobes (simulation only — $fatal is non-synthesizable).
`ifndef __pnr__
    initial begin
        if (DW != 32) $fatal(1, "axi_lite_register_bank requires DW == 32");
        if (SW != 4)  $fatal(1, "axi_lite_register_bank requires SW == 4");
    end
`endif

    logic [31:0] regs [N_REGS];
    assign regs_o = regs;

    // Word index from byte address (32-bit words).  WORDW spans the whole 4 KB
    // slot; IDXW is the narrow index into the N_REGS array (range-checked first).
    localparam int unsigned WORDW = ADDR_W - 2;
    localparam int unsigned IDXW  = (N_REGS > 1) ? $clog2(N_REGS) : 1;

    // ── Write channel ─────────────────────────────────────────────────────────
    typedef enum logic [0:0] { WR_IDLE, WR_RESP } wr_e;
    wr_e               wr_state;
    logic              aw_captured, w_captured;
    logic [WORDW-1:0]  waddr_word;
    logic [DW-1:0]     wdata_q;
    logic [SW-1:0]     wstrb_q;

    assign s_axil_awready = (wr_state == WR_IDLE) && !aw_captured;
    assign s_axil_wready  = (wr_state == WR_IDLE) && !w_captured;
    assign s_axil_bvalid  = (wr_state == WR_RESP);
    assign s_axil_bresp   = AXI_RESP_OKAY;

    // Commit pulse: both halves of the write are in hand this cycle.
    logic aw_now, w_now, wr_commit;
    assign aw_now    = s_axil_awvalid && s_axil_awready;
    assign w_now     = s_axil_wvalid  && s_axil_wready;
    assign wr_commit = (wr_state == WR_IDLE) &&
                       (aw_captured || aw_now) && (w_captured || w_now);

    logic [WORDW-1:0] commit_word;
    assign commit_word = aw_now ? s_axil_awaddr[ADDR_W-1:2] : waddr_word;

    // Effective SW write mask = byte-strobe expanded AND per-register WMASK.
    function automatic logic [31:0] strb_expand(input logic [SW-1:0] strb);
        for (int unsigned b = 0; b < SW; b++)
            strb_expand[8*b +: 8] = strb[b] ? 8'hFF : 8'h00;
    endfunction

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            wr_state    <= WR_IDLE;
            aw_captured <= 1'b0;
            w_captured  <= 1'b0;
            waddr_word  <= '0;
            wdata_q     <= '0;
            wstrb_q     <= '0;
            for (int unsigned r = 0; r < N_REGS; r++) regs[r] <= RESET_VAL[r];
        end else begin
            // Hardware status writes (bypass WMASK).
            for (int unsigned r = 0; r < N_REGS; r++)
                if (hw_wen_i[r]) regs[r] <= hw_wdata_i[r];

            unique case (wr_state)
                WR_IDLE: begin
                    if (aw_now) begin
                        aw_captured <= 1'b1;
                        waddr_word  <= s_axil_awaddr[ADDR_W-1:2];
                    end
                    if (w_now) begin
                        w_captured <= 1'b1;
                        wdata_q    <= s_axil_wdata;
                        wstrb_q    <= s_axil_wstrb;
                    end
                    if (wr_commit) begin
                        // SW commit obeys WMASK & wstrb; in-range only.
                        // Use this cycle's data if it just arrived, else latched.
                        // Zero-extend commit_word to 32 bits before the N_REGS compare.
                        if ({{(32-WORDW){1'b0}}, commit_word} < N_REGS) begin
                            automatic logic [IDXW-1:0] ci = commit_word[IDXW-1:0];
                            automatic logic [DW-1:0]   wd =
                                w_now ? s_axil_wdata : wdata_q;
                            automatic logic [SW-1:0]   ws =
                                w_now ? s_axil_wstrb : wstrb_q;
                            automatic logic [31:0]     m  =
                                WMASK[ci] & strb_expand(ws);
                            // SW owns the WMASK bits. HW owns the rest. Fold the same-cycle HW write into base.
                            automatic logic [31:0]     base =
                                hw_wen_i[ci] ? hw_wdata_i[ci] : regs[ci];
                            regs[ci] <= (base & ~m) | (wd & m);
                        end
                        wr_state    <= WR_RESP;
                        aw_captured <= 1'b0;
                        w_captured  <= 1'b0;
                    end
                end
                WR_RESP: if (s_axil_bready) wr_state <= WR_IDLE;
                default: wr_state <= WR_IDLE;
            endcase
        end
    end

    // ── Read channel ──────────────────────────────────────────────────────────
    typedef enum logic [0:0] { RD_IDLE, RD_RESP } rd_e;
    rd_e           rd_state;
    logic [DW-1:0] rdata_q;

    assign s_axil_arready = (rd_state == RD_IDLE);
    assign s_axil_rvalid  = (rd_state == RD_RESP);
    assign s_axil_rresp   = AXI_RESP_OKAY;
    assign s_axil_rdata   = rdata_q;

    logic [WORDW-1:0] araddr_word;
    assign araddr_word = s_axil_araddr[ADDR_W-1:2];

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            rd_state <= RD_IDLE;
            rdata_q  <= '0;
        end else begin
            unique case (rd_state)
                RD_IDLE: if (s_axil_arvalid && s_axil_arready) begin
                    // Zero-extend araddr_word to 32 bits before the N_REGS compare.
                    rdata_q  <= ({{(32-WORDW){1'b0}}, araddr_word} < N_REGS)
                                ? regs[araddr_word[IDXW-1:0]] : '0;
                    rd_state <= RD_RESP;
                end
                RD_RESP: if (s_axil_rready) rd_state <= RD_IDLE;
                default: rd_state <= RD_IDLE;
            endcase
        end
    end

endmodule : axi_lite_register_bank
