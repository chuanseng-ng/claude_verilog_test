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
//   * Default (flat array): reads are REGISTERED (bead ydw, 2026-09-17) —
//     `mem[r_idx]` (a 1024:1 read mux) feeds a single head register
//     (r_data_q/r_valid_q/r_last_q) and nothing else, so the crossbar/
//     consumer segment downstream of s_rdata never sees the mux. Burst-start
//     latency is 2 cycles (was 1 / "0 extra"): only the FIRST beat costs the
//     extra cycle — once primed, continuous RREADY still sustains 1
//     beat/cycle. See the read FSM comment below (sram_controller.sv read
//     FSM, `ifndef SRAM_SKY130` branch) for the full timing diagram and the
//     read-after-write hazard analysis.
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
//     the flat array's 2-cycle registered first beat; sustained throughput
//     is unaffected either way.
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

`ifndef SRAM_SKY130
    // bead rvb (fan-out fix, Path A / RVB_FANOUT_FIX_PROPOSAL.md §A.2 option
    // A2): one-hot decode of a word index, registered by the caller during
    // the address phase (see word_sel_q below) instead of being re-decoded
    // combinationally from s_wvalid every cycle.
    function automatic logic [MEM_WORDS-1:0] word_onehot(input logic [IDX_W-1:0] idx);
        logic [MEM_WORDS-1:0] oh;
        oh      = '0;
        oh[idx] = 1'b1;
        return oh;
    endfunction
`endif

    // ── Write FSM ────────────────────────────────────────────────────────────
    typedef enum logic [1:0] {W_IDLE, W_DATA, W_RESP} wstate_e;
    wstate_e          wstate;
`ifdef SRAM_SKY130
    logic [IDX_W-1:0] w_idx;
`else
    // bead rvb (fan-out fix, Path A): registered one-hot word-select,
    // replacing the indexed `mem[w_idx][...]` assignment that used to
    // synthesize a per-storage-bit compare gated directly by s_wvalid (an
    // ~MEM_WORDS*DW-wide, ~18.5k-endpoint fan-out cone off s_wvalid on the
    // ASAP7 deferred_flatten netlist — see docs/design/RVB_FANOUT_FIX_PROPOSAL.md
    // §A.1). word_sel_q is decoded once during the address phase (W_IDLE,
    // a cycle that already exists ahead of W_DATA) and reused unchanged
    // across a burst's byte lanes; s_wvalid then only needs to reach the
    // MEM_WORDS word_we AND2 gates below (see w_commit/word_we), not every
    // individual storage bit. Zero added write latency: the decode reuses
    // an address-phase cycle that already existed before this fix.
    logic [MEM_WORDS-1:0] word_sel_q;
`endif
    logic [IW-1:0]    bid_q;
    logic             w_err;
    logic             w_incr;

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            wstate <= W_IDLE;
            w_err  <= 1'b0;
            w_incr <= 1'b0;
`ifndef SRAM_SKY130
            word_sel_q <= '0;
`endif
        end else begin
            unique case (wstate)
                W_IDLE: begin
                    if (s_awvalid) begin
`ifdef SRAM_SKY130
                        w_idx  <= word_index(s_awaddr);
`else
                        word_sel_q <= word_onehot(word_index(s_awaddr));
`endif
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
`ifdef SRAM_SKY130
                            w_idx <= w_idx + 1'b1;
`else
                            // Index +1 mod MEM_WORDS == a 1-position rotate
                            // of the one-hot select vector (MEM_WORDS is
                            // required to be a power of two, see the
                            // MEM_WORDS parameter comment above).
                            word_sel_q <= {word_sel_q[MEM_WORDS-2:0], word_sel_q[MEM_WORDS-1]};
`endif
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

`ifndef SRAM_SKY130
    // bead rvb (fan-out fix, Path A): the actual mem[] write, moved out of
    // the FSM always_ff above and re-expressed as MEM_WORDS explicit,
    // independently-timed word_we[i]-gated always_ff blocks. w_commit fans
    // out to MEM_WORDS AND2 gates (word_we) instead of directly reaching
    // every one of the MEM_WORDS*DW storage bits, giving CTS/resizer
    // MEM_WORDS separately-timed branches instead of one shared tree.
    // w_err/wstrb/wlast semantics are unchanged from the original indexed
    // assignment (`mem[w_idx][b*8+:8] <= s_wdata[b*8+:8] if s_wstrb[b] &&
    // !w_err`, gated by s_wvalid while wstate==W_DATA).
    logic w_commit;
    assign w_commit = (wstate == W_DATA) && s_wvalid && !w_err;

    logic [MEM_WORDS-1:0] word_we;
    assign word_we = word_sel_q & {MEM_WORDS{w_commit}};

    for (genvar gw = 0; gw < MEM_WORDS; gw++) begin : g_mem_word_we
        always_ff @(posedge clk) begin
            if (word_we[gw]) begin
                for (int b = 0; b < SW; b++) begin
                    if (s_wstrb[b]) begin
                        mem[gw][b*8 +: 8] <= s_wdata[b*8 +: 8];
                    end
                end
            end
        end
    end
`endif

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
    // ---- Default: flat behavioral array, REGISTERED read (bead ydw). ----
    //
    // claude_verilog_test-ydw: the previous `assign s_rdata = mem[r_idx]`
    // was a *live combinational* 1024:1 read mux — MEM_WORDS storage-flop
    // outputs into a DW-wide mux, straight out to s_rdata and on into
    // u_bus.u_xbar / the consuming master. On the ASAP7 SoC post-GRT STA
    // this was the dominant worst-path class: u_sram's mem[] storage flop
    // -> ~1050 ps of buffer/wire spread -> ~900 ps of mux -> s_rdata ->
    // crossbar -> u_dma.D, worst slack -1144.52 ps, 23% of all setup
    // violators. Fix: register the mux's output directly, one cycle after
    // the address is issued, so nothing downstream of s_rdata ever sees the
    // mux — only a flip-flop.
    //
    // Select-path note: `r_idx` (the mux select) is a plain register, set
    // once on AR-accept and incremented in place by the sequential block
    // below. The select is never a live `rready ? r_idx+1 : r_idx`
    // combinational expression in front of the 1024:1 mux — r_idx already
    // *is* next-address-or-current, decided a cycle earlier, so the mux's
    // only fan-in beyond mem[] is that one register.
    //
    // Timing (R_IDLE -> R_BUSY, then steady-state streaming):
    //   R_IDLE : wait for ARVALID; on accept, latch idx/cnt/id/err/incr,
    //            set r_active, move to R_BUSY. No mem[] read is issued this
    //            cycle (mirrors the R_IDLE->R_BUSY latency the SRAM_SKY130
    //            branch already pays for its own, unrelated, reason).
    //   R_BUSY : `r_issue_now` reads mem[r_idx] into the head register
    //            (r_data_q/r_last_q/r_valid_q, exposed directly as
    //            s_rdata/s_rlast/s_rvalid) whenever the head has room, or is
    //            about to: `r_active && (!r_valid_q || s_rready)`.
    //              - Head empty (!r_valid_q): fetch immediately.
    //              - Head full but consumed this cycle (RVALID && RREADY):
    //                the just-fetched word replaces the outgoing one on the
    //                very next edge — no bubble, so continuous RREADY
    //                sustains 1 beat/cycle indefinitely once primed.
    //              - Head full, RVALID && !RREADY (backpressure): r_issue_now
    //                is low, no new mem[] read happens, and r_data_q/
    //                r_last_q/r_valid_q simply hold — RDATA/RLAST/RVALID
    //                stay stable under backpressure and no beat is ever
    //                skipped or duplicated.
    //            Returns to R_IDLE once every beat has been fetched
    //            (!r_active) and the head has drained (!r_valid_q, or it
    //            drains this very cycle).
    //
    // Latency: burst-start latency is 2 cycles (R_IDLE->R_BUSY, then one
    // cycle for the registered mem[] read to land in the head) versus the
    // previous 1-cycle / "0 extra latency" combinational design — a +1-cycle
    // cost on the FIRST beat only. Sustained throughput, INCR vs FIXED
    // addressing, SLVERR (r_err) behaviour, and MEM_WORDS wraparound (still
    // the same `r_idx + 1'b1`, unaffected by the power-of-two width) are all
    // unchanged from the previous design.
    //
    // Read-after-write hazard analysis: while the head is held across a
    // multi-cycle stall (RVALID && !RREADY), a write landing at the same
    // word address that is already sitting in r_data_q is NOT reflected —
    // the head keeps presenting the pre-write snapshot for the rest of the
    // stall. The previous combinational design re-read mem[] live every
    // cycle and so *could* pick up such a write mid-stall. This is a change
    // within an already-unspecified corner, not a new class of bug:
    // axi4_crossbar.sv gives each slave independent, depth-1-outstanding
    // write and read engines (axi4_crossbar.sv:9) and explicitly does NOT
    // interlock a concurrent AR against an in-flight AW to the same slave —
    // "A master that requires read-after-write ordering to the same slave
    // must wait for B before AR" (axi4_crossbar.sv:22-27). So no fabric
    // interlock rules this race out, but AXI4 itself defines no ordering
    // here either way, and this SoC's coherency model is entirely
    // software-managed (CLAUDE.md: the CPU explicitly flushes/invalidates
    // its D-cache around GPU launches; no master is expected to write and
    // read the same live address without an intervening BRESP). No RTL
    // bypass is added for it: a same-address forwarding compare would have
    // to index the MEM_WORDS-wide one-hot write-select vector (word_sel_q)
    // by the held read index, reintroducing exactly the class of wide
    // indexed mux this fix removes. If a future master needs a hardware-
    // guaranteed same-cycle RAW bypass to this SRAM, prefer a narrow one-hot
    // AND/OR-reduce compare (`|(word_sel_q & word_onehot(r_held_idx_q))`)
    // over a binary index compare.
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
    // see the Timing note above.
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
