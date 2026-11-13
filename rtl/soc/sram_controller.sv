// sram_controller - AXI4 slave SRAM controller, the main memory model.
//
// Function: The module has two independent single-outstanding FSMs, one for writes and one for reads.
//   It supports INCR and FIXED bursts. WRAP and out-of-range addresses give SLVERR. WSTRB byte enables are honoured.
//   BID and RID echo AWID and ARID. The AXI4 interface is the same for all storage variants (default, SRAM_SKY130, FPGA).
//   Default: a flat word array of MEM_WORDS words. Reads are registered. A burst starts after 2 cycles
//   and a primed burst streams 1 beat per cycle. A write word lands in mem 2 cycles after its W handshake.
//   BVALID waits in W_DRAIN until the last beat has landed.
//   SRAM_SKY130: a hard macro. Writes use port 0. Reads use port 1 and a 2-entry output skid buffer.
//   A burst starts after 3 cycles.
// Parameters: AW, DW, SW, IW, LENW and MEM_WORDS. SRAM_SKY130 requires MEM_WORDS=1024.
// Clocks and resets: clk is the clock. rst_n is the reset.
// Caller rules:
//   - A master that must read new data after a write must wait for B before it issues AR.
//   - A read of a word whose write is still in the pipeline returns the old value. The module has no forwarding.
//   - The ports mirror the crossbar s1_* port group. All widths come from axi_pkg.
// Doc: ds:mod:sram-controller, tm:mod:sram-controller, cr:mod:sram-controller

// hlrm (FPGA Stage 0): the SRAM_SKY130 FSM arm (single write port + dedicated registered-read port, 2-entry skid
// buffer, no flat word array) is the right shape for an FPGA block RAM too. SRAM_CTRL_2P selects that FSM arm;
// it is local to this file (undefined at the end) so it can never leak into another module's `ifdef.
// With FPGA undefined it is defined exactly when SRAM_SKY130 is, so every pre-existing elaboration is unchanged.
`ifdef SRAM_SKY130
`define SRAM_CTRL_2P
`elsif FPGA
`define SRAM_CTRL_2P
`endif

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
    input  logic            s_rready,

    // ── MBIST (DFT Stage 4, Doc: tm:ch:dft-architecture:16-stage-4-specification-beads-j41m14-mbist-j41m10-control-word-crossing): collar select/bus in, macro read data out.
    //    Active only in the SRAM_SKY130 arm; every other arm ignores the inputs and drives 0.
    input  logic            mb_en_i,
    input  logic            mb_ce_i,
    input  logic            mb_we_i,
    input  logic [3:0]      mb_wmask_i,
    input  logic [9:0]      mb_addr_i,
    input  logic [31:0]     mb_din_i,
    output logic [31:0]     mb_dout0_o,
    output logic [31:0]     mb_dout1_o
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
        // The $fatal runs at elaboration, outside an `initial` block. A wrong MEM_WORDS fails lint as well as simulation.
        $fatal(1, "sram_controller: SRAM_SKY130 requires MEM_WORDS=1024 (4 KB) to match the sky130_sram_4kbyte_1rw1r_32x1024_8 macro geometry; got MEM_WORDS=%0d", MEM_WORDS);
    end
`elsif FPGA
    // hlrm: backing store is the fpga_sdp_ram_be instance at the bottom of this file (inferred block RAM).
    // MEM_WORDS must be a power of two so the word index is a plain bit slice of the byte address.
    if ((MEM_WORDS & (MEM_WORDS - 1)) != 0) begin : g_mem_words_pow2_check
        $fatal(1, "sram_controller: FPGA arm requires MEM_WORDS to be a power of two; got MEM_WORDS=%0d", MEM_WORDS);
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
    // W_DRAIN holds BVALID until the write pipeline has landed the last beat. The SRAM_SKY130 branch never enters W_DRAIN.
    typedef enum logic [1:0] {W_IDLE, W_DATA, W_DRAIN, W_RESP} wstate_e;
    wstate_e          wstate;
`ifdef SRAM_CTRL_2P
    logic [IDX_W-1:0] w_idx;
`else
    // w_idx is the binary word index.
    logic [IDX_W-1:0] w_idx;
    logic             drain_cnt;  // W_DRAIN: 1 => one more full cycle to wait
`endif
    logic [IW-1:0]    bid_q;
    logic             w_err;
    logic             w_incr;

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            wstate <= W_IDLE;
            w_err  <= 1'b0;
            w_incr <= 1'b0;
`ifndef SRAM_CTRL_2P
            drain_cnt <= 1'b0;
`endif
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
                        if (!w_err && w_incr) begin
                            w_idx <= w_idx + 1'b1;
                        end
                        if (s_wlast) begin
`ifdef SRAM_CTRL_2P
                            wstate <= W_RESP;
`else
                            // BVALID must not assert until the last beat has landed in mem.
                            // The pipeline takes 2 clock edges past this
                            // accept edge to land the word, so W_DRAIN must
                            // hold for 2 cycles before W_RESP is entered.
                            wstate    <= W_DRAIN;
                            drain_cnt <= 1'b1;
`endif
                        end
                    end
                end
`ifndef SRAM_CTRL_2P
                W_DRAIN: begin
                    if (drain_cnt == 1'b0) begin
                        wstate <= W_RESP;
                    end else begin
                        drain_cnt <= 1'b0;
                    end
                end
`endif
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

`ifndef SRAM_CTRL_2P
    // Write pipeline: stage 1 registers the W beat, stage 2 holds per-group registers, stage 3 writes mem.
    // A word lands in mem 2 cycles after its W handshake. WREADY does not depend on the pipeline.
    // BVALID waits in W_DRAIN until the last beat has landed.
    // Error bursts write nothing. BRESP is SLVERR.
    localparam int unsigned GROUP_WORDS = 32;
    localparam int unsigned NGROUPS     = MEM_WORDS / GROUP_WORDS;
    localparam int unsigned LOCAL_W     = $clog2(GROUP_WORDS);
    localparam int unsigned GROUP_SEL_W = IDX_W - LOCAL_W;

    if (((MEM_WORDS % GROUP_WORDS) != 0) || (MEM_WORDS <= GROUP_WORDS)) begin : g_group_words_check
        // Elaboration-time check (see the SRAM_SKY130 MEM_WORDS guard above
        // for why a bare $fatal in a generate scope, not wrapped in
        // `initial`, is used here). MEM_WORDS must be an exact, strictly
        // larger multiple of GROUP_WORDS: NGROUPS==1 (MEM_WORDS==GROUP_WORDS)
        // would make GROUP_SEL_W a zero-width type (idx1_q[IDX_W-1:LOCAL_W]
        // with IDX_W==LOCAL_W), which is not legal SystemVerilog.
        $fatal(1, "sram_controller: MEM_WORDS=%0d must be an exact multiple of, and strictly greater than, GROUP_WORDS=%0d for the rvb write-pipeline grouping", MEM_WORDS, GROUP_WORDS);
    end

    // Local one-hot decode of a beat's word index within its GROUP_WORDS
    // group — narrow (GROUP_WORDS wide, not MEM_WORDS wide), shared
    // (broadcast, not replicated) across all NGROUPS stage-2 group blocks.
    function automatic logic [GROUP_WORDS-1:0] word_onehot_local(input logic [LOCAL_W-1:0] idx);
        logic [GROUP_WORDS-1:0] oh;
        oh      = '0;
        oh[idx] = 1'b1;
        return oh;
    endfunction

    // ---- Stage 1: input register slice. ----
    logic             wr_valid1_q;  // 1-cycle pulse: a real (non-error) write beat was captured last cycle
    logic [DW-1:0]    wdata1_q;
    logic [SW-1:0]    wstrb1_q;
    logic [IDX_W-1:0] idx1_q;

    logic beat_accept;
    assign beat_accept = (wstate == W_DATA) && s_wvalid;

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            wr_valid1_q <= 1'b0;
        end else begin
            wr_valid1_q <= beat_accept && !w_err;
            if (beat_accept) begin
                wdata1_q <= s_wdata;
                wstrb1_q <= s_wstrb;
                idx1_q   <= w_idx;
            end
        end
    end

    // ---- Stage 2: per-group local registers. ----
    logic [GROUP_SEL_W-1:0] grp1_sel;
    logic [LOCAL_W-1:0]     local1_idx;
    assign grp1_sel   = idx1_q[IDX_W-1:LOCAL_W];
    assign local1_idx = idx1_q[LOCAL_W-1:0];

    logic [GROUP_WORDS-1:0] local1_onehot;
    assign local1_onehot = word_onehot_local(local1_idx);

    logic [SW-1:0] grp_we_q    [NGROUPS][GROUP_WORDS];
    logic [DW-1:0] grp_wdata_q [NGROUPS];

    for (genvar gk = 0; gk < NGROUPS; gk++) begin : g_stage2_group
        logic grp_sel_k;
        assign grp_sel_k = wr_valid1_q && (grp1_sel == GROUP_SEL_W'(gk));

        always_ff @(posedge clk) begin
            if (!rst_n) begin
                for (int gw = 0; gw < GROUP_WORDS; gw++) begin
                    grp_we_q[gk][gw] <= '0;
                end
                grp_wdata_q[gk] <= '0;
            end else if (grp_sel_k) begin
                for (int gw = 0; gw < GROUP_WORDS; gw++) begin
                    grp_we_q[gk][gw] <= local1_onehot[gw] ? wstrb1_q : '0;
                end
                grp_wdata_q[gk] <= wdata1_q;
            end else begin
                for (int gw = 0; gw < GROUP_WORDS; gw++) begin
                    grp_we_q[gk][gw] <= '0;
                end
                // grp_wdata_q[gk] deliberately NOT assigned in this branch
                // (holds its previous value), see tm:mod:sram-controller:
                // this self-hold is what keeps this register's
                // D-input structurally distinct from every other group's.
            end
        end
    end

    // ---- Stage 3: mem[] write — one always_ff per word, gated only by its
    // own group's registered, already-qualified write-enable. ----
    for (genvar wk = 0; wk < NGROUPS; wk++) begin : g_stage3_group
        for (genvar ww = 0; ww < GROUP_WORDS; ww++) begin : g_stage3_word
            localparam int unsigned GIDX = wk * GROUP_WORDS + ww;
            always_ff @(posedge clk) begin
                for (int b = 0; b < SW; b++) begin
                    if (grp_we_q[wk][ww][b]) begin
                        mem[GIDX][b*8 +: 8] <= grp_wdata_q[wk][b*8 +: 8];
                    end
                end
            end
        end
    end
`endif

`ifdef SRAM_CTRL_2P
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
`ifndef SRAM_CTRL_2P
    // Default: flat behavioural array with a registered read. r_idx is a plain register, so no combinational select drives the read mux.
    // R_IDLE accepts AR. R_BUSY reads mem[r_idx] into the head register when the head has room.
    // Backpressure holds the head. Continuous RREADY gives 1 beat per cycle after a 2-cycle start.
    // A read of a word whose write is still in the pipeline returns the old value. There is no forwarding.
    // A master that waits for B before it issues AR reads the new data.
    typedef enum logic [0:0] {R_IDLE, R_BUSY} rstate_e;
    rstate_e          rstate;
    logic [IDX_W-1:0] r_idx;    // next address to fetch from mem[]
    logic [LENW-1:0]  r_cnt;    // beats remaining to fetch (arlen down to 0)
    logic             r_active; // 1 from AR-accept until the final beat has
                                 // been fetched
    logic [IW-1:0]    rid_q;
    logic             r_err;
    logic             r_incr;

    // ---- Head register: one prefetched beat, exposed directly to AXI. ----
    logic             r_valid_q;
    logic             r_last_q;
    logic [DW-1:0]    r_data_q;

    // Fetch a new word into the head whenever the head is empty, or is being
    // drained this very cycle (guaranteeing it room for the incoming word) —
    // See ds:mod:sram-controller.
    logic r_issue_now;
    assign r_issue_now = r_active && (!r_valid_q || s_rready);

    // The head is (or is about to become) empty this cycle — used only to
    // decide the R_BUSY -> R_IDLE transition, never on the mux/select path.
    logic r_head_clearing;
    assign r_head_clearing = !r_valid_q || s_rready;

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            rstate    <= R_IDLE;
            r_active  <= 1'b0;
            r_err     <= 1'b0;
            r_incr    <= 1'b0;
            r_valid_q <= 1'b0;
            r_last_q  <= 1'b0;
            r_data_q  <= '0;
        end else begin
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
                        // The 1024:1 read mux — its only consumer is this
                        // one register.
                        r_data_q  <= mem[r_idx];
                        r_last_q  <= (r_cnt == '0);
                        r_valid_q <= 1'b1;
                        if (r_cnt == '0) begin
                            r_active <= 1'b0;
                        end else begin
                            r_cnt <= r_cnt - 1'b1;
                            if (r_incr) begin
                                r_idx <= r_idx + 1'b1;
                            end
                        end
                    end else if (s_rready) begin
                        // Head consumed with nothing to replace it -> empty.
                        r_valid_q <= 1'b0;
                    end
                    if (!r_active && r_head_clearing) begin
                        rstate <= R_IDLE;
                    end
                end
                default: rstate <= R_IDLE;
            endcase
        end
    end

    assign s_arready = (rstate == R_IDLE);
    assign s_rvalid  = r_valid_q;
    assign s_rdata   = r_data_q;
    assign s_rid     = rid_q;
    assign s_rresp   = r_err ? AXI_RESP_SLVERR : AXI_RESP_OKAY;
    assign s_rlast   = r_last_q;

`else
    // ---- SRAM_SKY130: hard macro, port 1 (dedicated read-only port). ----
    //
    // The macro launches read data on the falling edge. rd_pend_q adds a cycle and a 2-entry skid buffer exposes the beat.
    // r_issue_now issues one address per cycle while the buffer has room.
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
    // Port 0 is the write port. Port 1 is the read port. USE_POWER_PINS is not defined here. mem_collar sits between the controller and the macro.
    logic             mb_csb0_m;
    logic             mb_web0_m;
    logic [3:0]       mb_wmask0_m;
    logic [9:0]       mb_addr0_m;
    logic [31:0]      mb_din0_m;
    logic             mb_csb1_m;
    logic [9:0]       mb_addr1_m;
    /* verilator lint_off UNUSEDSIGNAL */
    logic             mb_cmp_f0_unused;   // LOCAL_CMP = 0: the collar compare is not built, strobes are constant 0
    logic             mb_cmp_f1_unused;
    /* verilator lint_on  UNUSEDSIGNAL */

    mem_collar #(
        .AW     (10),
        .HAS_P1 (1'b1)
    ) u_mbist_collar (
        .bist_en_i  (mb_en_i),
        .b_ce_i     (mb_ce_i),
        .b_we_i     (mb_we_i),
        .b_wmask_i  (mb_wmask_i),
        .b_addr_i   (mb_addr_i),
        .b_din_i    (mb_din_i),
        .csb0_f_i   (mem_csb0),
        .web0_f_i   (1'b0),
        .wmask0_f_i (mem_wmask0),
        .addr0_f_i  (mem_addr0),
        .din0_f_i   (mem_din0),
        .csb1_f_i   (mem_csb1),
        .addr1_f_i  (mem_addr1),
        .clk_i       (clk),
        .x_rd_i      (1'b0),
        .x_xm_i      (4'b0),
        .x_bg_i      (3'b0),
        .dout0_i     (32'd0),
        .dout1_i     (32'd0),
        .cmp_fail0_o (mb_cmp_f0_unused),
        .cmp_fail1_o (mb_cmp_f1_unused),
        .csb0_m_o   (mb_csb0_m),
        .web0_m_o   (mb_web0_m),
        .wmask0_m_o (mb_wmask0_m),
        .addr0_m_o  (mb_addr0_m),
        .din0_m_o   (mb_din0_m),
        .csb1_m_o   (mb_csb1_m),
        .addr1_m_o  (mb_addr1_m)
    );

    sky130_sram_4kbyte_1rw1r_32x1024_8 u_sram_macro (
        .clk0   (clk),
        .csb0   (mb_csb0_m),
        .web0   (mb_web0_m),
        .wmask0 (mb_wmask0_m),
        .addr0  (mb_addr0_m),
        .din0   (mb_din0_m),
        .dout0  (mem_dout0_unused),
        .clk1   (clk),
        .csb1   (mb_csb1_m),
        .addr1  (mb_addr1_m),
        .dout1  (mem_dout1)
    );

    // dout0 (port 0 read data) is never consumed functionally — port 0 is write-only here. It is read by
    // the MBIST controller (and so is dout1, which is also the functional read path).
    assign mb_dout0_o = mem_dout0_unused;
    assign mb_dout1_o = mem_dout1;
`elsif FPGA
    // ── FPGA: inferred block RAM (hlrm) ──────────────────────────────────────
    // Same two-port contract as the Sky130 macro arm above: write port = the write FSM (byte-enabled, committed
    // the cycle the beat is accepted), read port = the read FSM's dedicated port with ONE registered-read cycle.
    // The Sky130 macro launches dout1 on the negedge after the address edge and the FSM samples it at the next
    // posedge; a registered-output block RAM presents the same data over the same cycle, so the skid-buffer
    // timing above holds unchanged (rd_pend_q is high exactly when mem_dout1 is the fresh word).
    // w_mem_write / mem_csb0 / mem_wmask0 / mem_addr0 / mem_din0 / mem_dout0_unused are declared and driven by
    // the shared SRAM_CTRL_2P block above (identical write-side qualification to the Sky130 macro arm).
    logic [SW-1:0]    mem_we;
    assign mem_we = mem_csb0 ? '0 : mem_wmask0;

    fpga_sdp_ram_be #(.WORDS(MEM_WORDS)) u_fpga_mem (
        .clk    (clk),
        .we_i   (mem_we),
        .waddr_i(mem_addr0),
        .wdata_i(mem_din0),
        .re_i   (~mem_csb1),
        .raddr_i(mem_addr1),
        .rdata_o(mem_dout1)
    );

    // No port-0 read in this controller; the shared block's dout0 placeholder is never driven in this arm.
    assign mem_dout0_unused = '0;
    logic _unused_dout0;
    assign _unused_dout0 = &{1'b0, mem_dout0_unused};
`endif

`ifndef SRAM_SKY130
    // No Sky130 macro in this arm (flat array / FPGA block RAM): the MBIST collar does not exist here.
    assign mb_dout0_o = 32'd0;
    assign mb_dout1_o = 32'd0;
    logic _unused_mb;
    assign _unused_mb = &{1'b0, mb_en_i, mb_ce_i, mb_we_i, mb_wmask_i, mb_addr_i, mb_din_i};
`endif

    // ── Unused inputs ────────────────────────────────────────────────────────
    // AxSIZE is fixed at 4 B for this 32-bit SoC; AWLEN is implied by WLAST on
    // the write path.  Sink them to keep Verilator -Wall clean.
    logic _unused_ok;
    assign _unused_ok = &{1'b0, s_awsize, s_arsize};

endmodule

`undef SRAM_CTRL_2P
