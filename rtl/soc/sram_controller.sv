// sram_controller.sv
// Phase 5 (M6) — Behavioral AXI4-slave SRAM controller (main memory model).
//
// Burst-capable AXI4 slave backing main memory (soc_addr_map_pkg::SRAM range).
// Behavioral only: a flat word array, no DRAM bank/refresh/timing logic.  The
// real DRAM controller is a Phase 6+ stretch goal.
//
// Design:
//   * Two independent single-outstanding FSMs (write, read) — matches the
//     depth-1 AXI4 master BFM and the M3 crossbar's per-slave lock.
//   * INCR and FIXED bursts supported; WRAP / out-of-range -> SLVERR response.
//   * WSTRB byte enables honoured on writes.  BID/RID echo AWID/ARID.
//   * Reads are combinational from the array (behavioral memory), registered
//     index — RDATA is valid the cycle RVALID is asserted.
//
// Ports are the slave-side mirror of the crossbar's `s1_*` (SRAM) port group
// in tb_axi4_crossbar.sv; all widths come from axi_pkg.  Flat per-channel
// signals (no SV interfaces) per the Phase 5 RTL convention.

module sram_controller
    import axi_pkg::*;
    import soc_addr_map_pkg::*;
#(
    parameter int unsigned AW        = axi_pkg::AXI_ADDR_WIDTH,
    parameter int unsigned DW        = axi_pkg::AXI_DATA_WIDTH,
    parameter int unsigned SW        = axi_pkg::AXI_STRB_WIDTH,
    parameter int unsigned IW        = axi_pkg::AXI_ID_WIDTH,
    parameter int unsigned LENW      = axi_pkg::AXI_LEN_WIDTH,
    // Behavioral backing-store depth in 32-bit words (power of two).  The SRAM
    // address window is huge (256 MB); the model only realises the low MEM_WORDS
    // words and aliases the address by masking to the index width.
    parameter int unsigned MEM_WORDS = 4096
) (
    input  logic clk,
    input  logic rst_n,

    // ── Write address channel ────────────────────────────────────────────────
    input  logic [IW-1:0]   s_awid,
    input  logic [AW-1:0]   s_awaddr,
    input  logic [LENW-1:0] s_awlen,
    input  logic [2:0]      s_awsize,
    input  logic [1:0]      s_awburst,
    input  logic            s_awvalid,
    output logic            s_awready,

    // ── Write data channel ───────────────────────────────────────────────────
    input  logic [DW-1:0]   s_wdata,
    input  logic [SW-1:0]   s_wstrb,
    input  logic            s_wlast,
    input  logic            s_wvalid,
    output logic            s_wready,

    // ── Write response channel ───────────────────────────────────────────────
    output logic [IW-1:0]   s_bid,
    output logic [1:0]      s_bresp,
    output logic            s_bvalid,
    input  logic            s_bready,

    // ── Read address channel ─────────────────────────────────────────────────
    input  logic [IW-1:0]   s_arid,
    input  logic [AW-1:0]   s_araddr,
    input  logic [LENW-1:0] s_arlen,
    input  logic [2:0]      s_arsize,
    input  logic [1:0]      s_arburst,
    input  logic            s_arvalid,
    output logic            s_arready,

    // ── Read data channel ────────────────────────────────────────────────────
    output logic [IW-1:0]   s_rid,
    output logic [DW-1:0]   s_rdata,
    output logic [1:0]      s_rresp,
    output logic            s_rlast,
    output logic            s_rvalid,
    input  logic            s_rready
);

    // ── Local geometry ───────────────────────────────────────────────────────
    localparam int unsigned IDX_W    = $clog2(MEM_WORDS);
    localparam int unsigned ADDR_LSB = 2;  // 4-byte word addressing

    logic [DW-1:0] mem [0:MEM_WORDS-1];

    // Word index (masked into the realised backing store) from a byte address.
    function automatic logic [IDX_W-1:0] word_index(input logic [AW-1:0] addr);
        /* verilator lint_off UNUSEDSIGNAL */
        logic [AW-1:0] off;
        /* verilator lint_on  UNUSEDSIGNAL */
        off = addr - SRAM_BASE;
        return off[ADDR_LSB +: IDX_W];
    endfunction

    // In-range check against the SRAM window.
    function automatic logic in_range(input logic [AW-1:0] addr);
        return (addr >= SRAM_BASE) && (addr <= SRAM_LIMIT);
    endfunction

    // Last-beat byte address for a burst.  For INCR, the final beat starts at
    // base + len*4 (AxSIZE fixed at 4 B in this SoC).  For FIXED/WRAP the
    // address does not advance past the start beat — use base so the caller's
    // in_range(last) check is identical to in_range(base).
    // Note: WRAP is already rejected by the burst-type check; returning base
    // here is conservative but correct.
    function automatic logic [AW-1:0] last_addr(
        input logic [AW-1:0]   base,
        input logic [LENW-1:0] len,
        input logic [1:0]      burst
    );
        if (burst == AXI_BURST_INCR)
            return base + (AW'(len) << 2);
        else
            return base;
    endfunction

    // ── Write FSM ────────────────────────────────────────────────────────────
    typedef enum logic [1:0] {W_IDLE, W_DATA, W_RESP} wstate_e;
    wstate_e          wstate;
    logic [IDX_W-1:0] w_idx;
    logic [IW-1:0]    bid_q;
    logic             w_err;
    logic             w_incr;

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            wstate <= W_IDLE;
            w_err  <= 1'b0;
            w_incr <= 1'b0;
        end else begin
            unique case (wstate)
                W_IDLE: begin
                    if (s_awvalid) begin
                        w_idx  <= word_index(s_awaddr);
                        bid_q  <= s_awid;
                        w_err  <= ~in_range(s_awaddr)
                                  || ~in_range(last_addr(s_awaddr, s_awlen, s_awburst))
                                  || (s_awburst == AXI_BURST_WRAP);
                        w_incr <= (s_awburst == AXI_BURST_INCR);
                        wstate <= W_DATA;
                    end
                end
                W_DATA: begin
                    if (s_wvalid) begin
                        if (!w_err) begin
                            for (int b = 0; b < SW; b++) begin
                                if (s_wstrb[b]) begin
                                    mem[w_idx][b*8 +: 8] <= s_wdata[b*8 +: 8];
                                end
                            end
                            if (w_incr) begin
                                w_idx <= w_idx + 1'b1;
                            end
                        end
                        if (s_wlast) begin
                            wstate <= W_RESP;
                        end
                    end
                end
                W_RESP: begin
                    if (s_bready) begin
                        wstate <= W_IDLE;
                    end
                end
                default: wstate <= W_IDLE;
            endcase
        end
    end

    assign s_awready = (wstate == W_IDLE);
    assign s_wready  = (wstate == W_DATA);
    assign s_bvalid  = (wstate == W_RESP);
    assign s_bid     = bid_q;
    assign s_bresp   = w_err ? AXI_RESP_SLVERR : AXI_RESP_OKAY;

    // ── Read FSM ─────────────────────────────────────────────────────────────
    typedef enum logic [0:0] {R_IDLE, R_DATA} rstate_e;
    rstate_e          rstate;
    logic [IDX_W-1:0] r_idx;
    logic [LENW-1:0]  r_cnt;
    logic [IW-1:0]    rid_q;
    logic             r_err;
    logic             r_incr;

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            rstate <= R_IDLE;
            r_err  <= 1'b0;
            r_incr <= 1'b0;
        end else begin
            unique case (rstate)
                R_IDLE: begin
                    if (s_arvalid) begin
                        r_idx  <= word_index(s_araddr);
                        r_cnt  <= s_arlen;
                        rid_q  <= s_arid;
                        r_err  <= ~in_range(s_araddr)
                                  || ~in_range(last_addr(s_araddr, s_arlen, s_arburst))
                                  || (s_arburst == AXI_BURST_WRAP);
                        r_incr <= (s_arburst == AXI_BURST_INCR);
                        rstate <= R_DATA;
                    end
                end
                R_DATA: begin
                    if (s_rready) begin
                        if (r_cnt == '0) begin
                            rstate <= R_IDLE;
                        end else begin
                            if (r_incr) begin
                                r_idx <= r_idx + 1'b1;
                            end
                            r_cnt <= r_cnt - 1'b1;
                        end
                    end
                end
                default: rstate <= R_IDLE;
            endcase
        end
    end

    assign s_arready = (rstate == R_IDLE);
    assign s_rvalid  = (rstate == R_DATA);
    assign s_rdata   = mem[r_idx];
    assign s_rid     = rid_q;
    assign s_rresp   = r_err ? AXI_RESP_SLVERR : AXI_RESP_OKAY;
    assign s_rlast   = (r_cnt == '0);

    // ── Unused inputs ────────────────────────────────────────────────────────
    // AxSIZE is fixed at 4 B for this 32-bit SoC; AWLEN is implied by WLAST on
    // the write path.  Sink them to keep Verilator -Wall clean.
    logic _unused_ok;
    assign _unused_ok = &{1'b0, s_awsize, s_arsize};

endmodule
