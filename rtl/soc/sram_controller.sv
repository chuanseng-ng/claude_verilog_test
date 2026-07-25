// sram_controller.sv
// Phase 5 (M6) — AXI4-slave SRAM controller (main memory model).
//
// GH #104 Sky130 SoC Stage-2: the default backing store is still a flat
// behavioral word array (used for FreePDK45/ASAP7 PD flows and all cocotb
// regressions that don't opt in to `SRAM_SKY130`) — but the flat array
// synthesizes to ~32K flip-flops plus a huge combinational 1024:1 read mux,
// which OOMs/fails-timing on the Sky130 SoC flow. When compiled with
// `+define+SRAM_SKY130` (mirrors the existing `ifdef SRAM_SKY130` convention
// in rtl/mem/rv32i_dcache.sv / rv32i_icache.sv), the backing store is instead
// a real sky130_sram_4kbyte_1rw1r_32x1024_8 OpenRAM hard macro (1024 words x
// 32 bits = 4 KB, matching MEM_WORDS=1024). The external AXI4 interface and
// memory-map behaviour are unchanged in both cases — soc_top instantiates
// this module identically either way.
//
// Design:
//   * Two independent single-outstanding FSMs (write, read) — matches the
//     depth-1 AXI4 master BFM and the M3 crossbar's per-slave lock.
//   * INCR and FIXED bursts supported; WRAP / out-of-range -> SLVERR response.
//   * WSTRB byte enables honoured on writes.  BID/RID echo AWID/ARID.
//   * Default (flat array): reads are combinational, registered index —
//     RDATA is valid the cycle RVALID is asserted (0 extra latency).
//   * SRAM_SKY130 (hard macro): writes go to the macro's port 0 (RW, used
//     write-only here); reads go to the macro's port 1 (dedicated read-only
//     port). The macro's dout1 is NEGEDGE-launched (addr1/csb1 presented in
//     cycle N are captured at the posedge ending cycle N, then read at the
//     negedge mid-cycle N+1) so dout1 is only stable for a posedge-sampling
//     AXI consumer starting cycle N+2 -- TWO cycles after the address is
//     presented, not one (GH #104 fr_null_20260724_051800_00). The read FSM
//     issues the macro address, waits one extra cycle for the negedge write
//     to land (`rd_pend_q`), then exposes the beat through a 2-entry output
//     skid buffer. Once primed, back-to-back burst beats still stream at 1
//     beat/cycle (a new address is issued whenever the buffer is guaranteed
//     a free slot for it once it lands); the extra buffer slot absorbs a
//     beat that lands while AXI backpressure holds the head slot, so no
//     beat is ever dropped, duplicated, or exposed before its data is
//     genuinely valid. Burst *start* latency is 3 cycles (R_IDLE->R_BUSY,
//     1 cycle to land in the macro, 1 cycle to land in the buffer) versus
//     the flat array's immediate first beat; sustained throughput is
//     unaffected.
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
    //
    // Under `SRAM_SKY130` this MUST be 1024 (4 KB) to match the OpenRAM hard
    // macro geometry — see the elaboration-time check below.
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

`ifdef SRAM_SKY130
    // The OpenRAM macro is fixed at 1024 words x 32 bits (10-bit address).
    // Guard against a silent depth mismatch if MEM_WORDS is ever overridden
    // (e.g. an experiment/L2-bench parameter sweep) while SRAM_SKY130 is
    // defined for the same build.
    if (MEM_WORDS != 1024) begin : g_mem_words_check
        // Elaboration system task (IEEE 1800-2017 §20.11): $fatal used
        // directly inside a generate scope -- NOT wrapped in an `initial`
        // block -- is evaluated at ELABORATION time, not simulation time.
        // The previous `initial $error(...)` form only ever fired if the
        // design was actually simulated, so `verilator --lint-only`
        // elaboration (which never runs simulation) silently let a wrong
        // MEM_WORDS through and truncate onto the macro's 10-bit
        // addr0/addr1. This form fails the build immediately, under lint
        // and synthesis elaboration alike, before a single clock is run.
        $fatal(1, "sram_controller: SRAM_SKY130 requires MEM_WORDS=1024 (4 KB) to match the sky130_sram_4kbyte_1rw1r_32x1024_8 macro geometry; got MEM_WORDS=%0d", MEM_WORDS);
    end
`else
    logic [DW-1:0] mem [0:MEM_WORDS-1];
`endif

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
`ifndef SRAM_SKY130
                        if (!w_err) begin
                            for (int b = 0; b < SW; b++) begin
                                if (s_wstrb[b]) begin
                                    mem[w_idx][b*8 +: 8] <= s_wdata[b*8 +: 8];
                                end
                            end
                        end
`endif
                        if (!w_err && w_incr) begin
                            w_idx <= w_idx + 1'b1;
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

`ifdef SRAM_SKY130
    // ── SRAM macro — port 0 (RW, write-only in this controller) ─────────────
    // Committed the same cycle the write FSM accepts a beat: csb0 active-low,
    // gated on an actual (non-error) write so an out-of-range burst never
    // touches the macro (matches the flat-array `if (!w_err)` guard it
    // replaces). web0 is tied 0 (always "write" when selected) since port 0
    // is never used to read in this design.
    logic w_mem_write;
    assign w_mem_write = (wstate == W_DATA) && s_wvalid && !w_err;

    logic             mem_csb0;
    logic [3:0]       mem_wmask0;
    logic [IDX_W-1:0] mem_addr0;
    logic [DW-1:0]    mem_din0;
    logic [DW-1:0]    mem_dout0_unused;

    assign mem_csb0   = ~w_mem_write;
    assign mem_wmask0 = s_wstrb;
    assign mem_addr0  = w_idx;
    assign mem_din0   = s_wdata;
`endif

    // ── Read FSM ─────────────────────────────────────────────────────────────
`ifndef SRAM_SKY130
    // ---- Default: flat behavioral array, combinational read (0-cycle
    // additional latency beyond the R_IDLE->R_DATA state transition already
    // present here). ----
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

`else
    // ---- SRAM_SKY130: hard macro, port 1 (dedicated read-only port). ----
    //
    // GH #104 fix (fr_null_20260724_051800_00): the macro's dout1 is
    // NEGEDGE-launched (see sim/sky130_sram_4kbyte_1rw1r_32x1024_8.sv):
    // addr1/csb1 presented during cycle N are captured by the macro's own
    // input register at the posedge ENDING cycle N, and the read is
    // performed at the NEGEDGE mid-cycle N+1 -- so dout1 only becomes
    // stable/sampleable from a posedge-sampling consumer's point of view
    // starting cycle N+2, i.e. TWO clock edges after the address is
    // presented, not one. The previous version of this FSM exposed
    // s_rvalid/s_rdata one cycle too early (cycle N+1), reading dout1
    // before its negedge write for that address had even happened --
    // reading stale data and silently dropping the true final beat.
    //
    // Fix: an extra one-cycle pipeline stage (`rd_pend_q`) plus a 2-entry
    // output skid buffer (`buf_v_q`/`buf_last_q`/`buf_data_q`) so the beat
    // is only exposed to AXI once dout1 is genuinely valid, WITHOUT losing
    // sustained beat-per-cycle throughput or dropping/duplicating beats
    // under R-channel backpressure:
    //
    // R_IDLE : wait for ARVALID; on accept, latch idx/cnt/id/err/incr and
    //          move to R_BUSY (address not issued this same cycle).
    // R_BUSY : `r_issue_now` presents one new macro read address per cycle
    //          (mem_csb1/mem_addr1) whenever the output buffer has a free
    //          slot to receive it once it lands.
    //          `rd_pend_q` is registered from `r_issue_now` -- it is 1
    //          during the cycle the macro's negedge write for that address
    //          actually happens (i.e. exactly the cycle after issue), which
    //          is also exactly the cycle mem_dout1 becomes the fresh,
    //          correct value for that address.
    //          The freshly-landed word is captured (`mem_dout1` sampled)
    //          into whichever buffer slot is free that same cycle -- slot 0
    //          (the AXI-facing head: s_rvalid/s_rdata/s_rlast) if free,
    //          else slot 1 (a one-beat overflow reserve for when AXI is
    //          applying backpressure on slot 0). `r_issue_now` only fires
    //          when a landing beat is guaranteed a free slot one cycle
    //          later (`buf_has_room`, i.e. slot 1 will be empty), so a
    //          third, unbufferable beat can never be issued -- this throttle
    //          is the only thing that ever stalls issuing; once primed,
    //          continuous RREADY sustains 1 beat/cycle indefinitely (slot 1
    //          is never touched in the no-backpressure steady state).
    //          Returns to R_IDLE once the whole pipeline -- issue (r_active),
    //          in-flight (rd_pend_q), and both buffer slots -- has drained.
    typedef enum logic [0:0] {R_IDLE, R_BUSY} rstate_e;
    rstate_e          rstate;
    logic [IDX_W-1:0] r_idx;       // next address to issue to the macro
    logic [LENW-1:0]  r_cnt;       // beats remaining to ISSUE (arlen down to 0)
    logic             r_active;    // 1 from AR-accept until the final beat's
                                    // address has been issued
    logic [IW-1:0]    rid_q;
    logic             r_err;
    logic             r_incr;

    // ---- Stage 1: in-flight marker (macro's negedge write for this
    // address is happening THIS cycle -- unstoppable once issued). ----
    logic             rd_pend_q;
    logic             rd_pend_last_q;

    // ---- Stage 2: 2-entry output skid buffer (slot 0 = AXI-facing head).
    logic          buf_v_q    [0:1];
    logic          buf_last_q [0:1];
    logic [DW-1:0] buf_data_q [0:1];

    logic             mem_csb1;
    logic [IDX_W-1:0] mem_addr1;
    logic [DW-1:0]    mem_dout1;

    logic head_fire;              // slot 0 consumed this cycle
    assign head_fire = buf_v_q[0] && s_rready;

    // Next-state of the 2-entry buffer: drain slot 0 (shifting slot 1 down)
    // if consumed this cycle, then place a landing beat (if any) into
    // whichever slot is free after that drain.
    logic          next_buf_v0, next_buf_v1;
    logic          next_buf_last0, next_buf_last1;
    logic [DW-1:0] next_buf_data0, next_buf_data1;

    always_comb begin
        next_buf_v0    = buf_v_q[0];
        next_buf_last0 = buf_last_q[0];
        next_buf_data0 = buf_data_q[0];
        next_buf_v1    = buf_v_q[1];
        next_buf_last1 = buf_last_q[1];
        next_buf_data1 = buf_data_q[1];

        if (head_fire) begin
            next_buf_v0    = buf_v_q[1];
            next_buf_last0 = buf_last_q[1];
            next_buf_data0 = buf_data_q[1];
            next_buf_v1    = 1'b0;
        end

        if (rd_pend_q) begin
            if (!next_buf_v0) begin
                next_buf_v0    = 1'b1;
                next_buf_last0 = rd_pend_last_q;
                next_buf_data0 = mem_dout1;
            end else begin
                next_buf_v1    = 1'b1;
                next_buf_last1 = rd_pend_last_q;
                next_buf_data1 = mem_dout1;
            end
        end
    end

    // A new address may be issued now only if a beat landing from it (one
    // cycle later) is guaranteed a free slot -- i.e. slot 1 will be empty
    // after this cycle's own drain/fill settle.
    logic buf_has_room;
    assign buf_has_room = !next_buf_v1;

    logic r_issue_now;
    assign r_issue_now = r_active && buf_has_room;

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            rstate         <= R_IDLE;
            r_active       <= 1'b0;
            r_err          <= 1'b0;
            r_incr         <= 1'b0;
            rd_pend_q      <= 1'b0;
            rd_pend_last_q <= 1'b0;
        end else begin
            rd_pend_q <= r_issue_now;
            if (r_issue_now) begin
                rd_pend_last_q <= (r_cnt == '0);
            end

            unique case (rstate)
                R_IDLE: begin
                    if (s_arvalid) begin
                        r_idx    <= word_index(s_araddr);
                        r_cnt    <= s_arlen;
                        rid_q    <= s_arid;
                        r_err    <= ~in_range(s_araddr)
                                    || ~in_range(last_addr(s_araddr, s_arlen, s_arburst))
                                    || (s_arburst == AXI_BURST_WRAP);
                        r_incr   <= (s_arburst == AXI_BURST_INCR);
                        r_active <= 1'b1;
                        rstate   <= R_BUSY;
                    end
                end
                R_BUSY: begin
                    if (r_issue_now) begin
                        if (r_cnt == '0) begin
                            r_active <= 1'b0;
                        end else begin
                            r_cnt <= r_cnt - 1'b1;
                            if (r_incr) begin
                                r_idx <= r_idx + 1'b1;
                            end
                        end
                    end
                    // Return to IDLE only once nothing remains anywhere in
                    // the pipeline: no more beats to issue, none in flight,
                    // and both buffer slots drained.
                    if (!r_active && !rd_pend_q && !buf_v_q[0] && !buf_v_q[1]) begin
                        rstate <= R_IDLE;
                    end
                end
                default: rstate <= R_IDLE;
            endcase
        end
    end

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            buf_v_q[0] <= 1'b0;
            buf_v_q[1] <= 1'b0;
        end else begin
            buf_v_q[0]    <= next_buf_v0;
            buf_last_q[0] <= next_buf_last0;
            buf_data_q[0] <= next_buf_data0;
            buf_v_q[1]    <= next_buf_v1;
            buf_last_q[1] <= next_buf_last1;
            buf_data_q[1] <= next_buf_data1;
        end
    end

    // Macro port 1 (read-only): select whenever this cycle issues a new
    // address (see r_issue_now above).
    assign mem_csb1  = ~(rstate == R_BUSY && r_issue_now);
    assign mem_addr1 = r_idx;

    assign s_arready = (rstate == R_IDLE);
    assign s_rvalid  = buf_v_q[0];
    assign s_rdata   = buf_data_q[0];
    assign s_rid     = rid_q;
    assign s_rresp   = r_err ? AXI_RESP_SLVERR : AXI_RESP_OKAY;
    assign s_rlast   = buf_last_q[0];
`endif

`ifdef SRAM_SKY130
    // ── SRAM macro instantiation ─────────────────────────────────────────────
    // Port 0 (RW, write-only here) <- write FSM; Port 1 (R-only) <- read FSM.
    // USE_POWER_PINS is intentionally not defined for this build (matches the
    // existing sky130_sram_1kbyte_1rw1r_32x256_8 cache-macro convention in
    // rtl/mem/rv32i_dcache.sv / rv32i_icache.sv): vccd1/vssd1 connectivity is
    // supplied by the LEF + PDN_MACRO_CONNECTIONS at PD time, not by RTL-level
    // power ports, so no ports exist to tie off here.
    sky130_sram_4kbyte_1rw1r_32x1024_8 u_sram_macro (
        .clk0   (clk),
        .csb0   (mem_csb0),
        .web0   (1'b0),
        .wmask0 (mem_wmask0),
        .addr0  (mem_addr0),
        .din0   (mem_din0),
        .dout0  (mem_dout0_unused),
        .clk1   (clk),
        .csb1   (mem_csb1),
        .addr1  (mem_addr1),
        .dout1  (mem_dout1)
    );

    // dout0 (port 0 read data) is never consumed — port 0 is write-only here.
    logic _unused_dout0;
    assign _unused_dout0 = &{1'b0, mem_dout0_unused};
`endif

    // ── Unused inputs ────────────────────────────────────────────────────────
    // AxSIZE is fixed at 4 B for this 32-bit SoC; AWLEN is implied by WLAST on
    // the write path.  Sink them to keep Verilator -Wall clean.
    logic _unused_ok;
    assign _unused_ok = &{1'b0, s_awsize, s_arsize};

endmodule
