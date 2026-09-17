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
//   * Default (flat array), WRITES: bead rvb Path A residual fix
//     (2026-09-17) — a 2-stage registered, group-distributed write pipeline
//     (stage 1 input register -> stage 2 per-group registers -> stage 3
//     mem[] write; see the `ifndef SRAM_SKY130` block after the write-FSM
//     channel assigns for the full design). A word lands in mem[] at the
//     clock edge ending 2 cycles after its W handshake; WREADY still
//     asserts every cycle in W_DATA (no throughput loss, 1 beat/cycle
//     sustained). BVALID is held off (new W_DRAIN FSM state) until the
//     burst's last beat has actually landed, so a master that waits for B
//     before issuing a same-address AR always reads the new data — see the
//     read FSM's read-after-write hazard analysis below for masters that
//     do NOT wait for B.
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

    // ── Write FSM ────────────────────────────────────────────────────────────
    // bead rvb Path A residual fix (2026-09-17): W_DRAIN is a new state used
    // only by the flat-array (`ifndef SRAM_SKY130`) branch below, to hold off
    // BVALID until the write pipeline (see the stage 1/2/3 block after the
    // channel assigns) has actually landed the burst's last beat in mem[].
    // The SRAM_SKY130 branch never transitions into W_DRAIN — its W_DATA
    // case arm still goes straight to W_RESP, unchanged. Adding this state
    // shifts W_RESP's synthesized encoding but not its behavior; wstate_e
    // stays a 2-bit type (4 states now instead of 3), identical simulated/
    // synthesized functional behavior for the SRAM_SKY130 branch either way.
    typedef enum logic [1:0] {W_IDLE, W_DATA, W_DRAIN, W_RESP} wstate_e;
    wstate_e          wstate;
`ifdef SRAM_SKY130
    logic [IDX_W-1:0] w_idx;
`else
    // bead rvb: binary word index (unlike the ifdef branch above, this is a
    // separate declaration so the SRAM_SKY130 branch's own w_idx text is
    // untouched). The MEM_WORDS-wide one-hot `word_sel_q` register from the
    // first rvb iteration (2026-09-16) is removed here — it was still a
    // same-cycle function of s_wvalid gating a MEM_WORDS-wide AND array
    // directly off the address-phase decode, and post-route measurement
    // (RUN_2026-09-17_09-01-42) showed the fan-out cone through mem[] was
    // still the #1 setup-violator class (16,400 violators, worst -1050 ps).
    // See the stage 1/2/3 write pipeline below for the actual fix.
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
`ifndef SRAM_SKY130
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
`ifdef SRAM_SKY130
                            wstate <= W_RESP;
`else
                            // bead rvb: BVALID must not assert until this
                            // beat (the burst's last) has landed in mem[] —
                            // see the write-pipeline latency note below.
                            // The pipeline takes 2 clock edges past this
                            // accept edge to land the word, so W_DRAIN must
                            // hold for 2 cycles before W_RESP is entered.
                            wstate    <= W_DRAIN;
                            drain_cnt <= 1'b1;
`endif
                        end
                    end
                end
`ifndef SRAM_SKY130
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

`ifndef SRAM_SKY130
    // bead rvb Path A residual fix (2026-09-17): 2-stage registered,
    // group-distributed write pipeline. Replaces the first rvb iteration's
    // word_sel_q-gated per-word always_ff (2026-09-16), which still made
    // every mem[] write-enable a same-cycle combinational function of
    // s_wvalid (via w_commit, gating a MEM_WORDS-wide AND array directly
    // off the address-phase one-hot decode) — confirmed still the #1
    // post-route setup-violator class on 26Q2 RUN_2026-09-17_09-01-42
    // (16,400 violators, worst -1050.16 ps). See
    // docs/design/RVB_FANOUT_FIX_PROPOSAL.md for the original root-cause
    // analysis this second iteration builds on.
    //
    //   Stage 1 (input register slice): registers the accepted W beat's
    //   commit/data/strobe/index. This is the ONLY register anywhere in
    //   this pipeline whose D-input is a same-cycle function of an
    //   s_w*/crossbar signal — nothing past this point is.
    //
    //   Stage 2 (per-group local registers): MEM_WORDS is split into
    //   NGROUPS contiguous groups of GROUP_WORDS words each. Each group has
    //   its OWN we/data registers, loaded ONLY when that group is the
    //   target of the stage-1 beat. grp_wdata_q[k] explicitly HOLDS
    //   (self-feedback) when group k is not selected, rather than always
    //   capturing wdata1_q — this makes every group's registers
    //   structurally distinct (a different D-input mux/compare term per
    //   group), which is what stops Yosys `opt_merge` from recognising the
    //   NGROUPS replicas as identical and collapsing them back into one
    //   high-fanout register. grp_we_q[k], by contrast, is a genuine
    //   1-cycle write-enable PULSE (explicitly driven to '0 when not
    //   selected, not held) — it must clear every cycle it isn't the
    //   target, or stage 3 would keep re-committing a stale write forever.
    //
    //   Stage 3 (mem[] write): each group's registered we/data gates only
    //   that group's own GROUP_WORDS words. The fan-out of any one stage-2
    //   register is local to one group (<= GROUP_WORDS*SW endpoints), and
    //   the fan-out of any stage-1 register is local to NGROUPS compare
    //   terms (<= MEM_WORDS/GROUP_WORDS, e.g. 128 for the default
    //   MEM_WORDS=4096) — never the whole MEM_WORDS*DW array in one hop.
    //
    // Write latency: a word lands in mem[] (updated by the always_ff below)
    // at the clock edge ending 2 cycles after its W handshake cycle — i.e.
    // handshake in cycle N, stage 1 valid in N+1, stage 2 valid in N+2 and
    // mem[] updated by the edge ending N+2, visible from N+3. WREADY
    // (`s_wready`, above) is `(wstate == W_DATA)` unconditionally — it
    // never depends on this pipeline's occupancy, so 1 beat/cycle write
    // throughput is preserved; a new beat can be captured into stage 1
    // every single cycle regardless of what stage 2/3 are doing with the
    // previous beat(s).
    //
    // B channel: BVALID must not assert before the burst's LAST beat has
    // actually landed in mem[], so a master that waits for B before issuing
    // a same-address AR (the fabric's documented ordering contract —
    // axi4_crossbar.sv:22-27 — "a master that requires read-after-write
    // ordering to the same slave must wait for B before AR") is guaranteed
    // to read the new data. W_DRAIN (see the write FSM above) holds for
    // exactly the 2 cycles needed so that wstate reaches W_RESP (BVALID=1)
    // no earlier than cycle N+3 — the SAME cycle the last beat's data
    // becomes visible in mem[], not before.
    //
    // Error bursts: wr_valid1_q is gated by `!w_err`, so stage 2/3 never
    // fire for a beat belonging to an error burst — BRESP is still SLVERR
    // (driven off w_err directly, unchanged) and nothing is ever written.
    //
    // Read-after-write window: see the read FSM's "Read-after-write hazard
    // analysis" comment below for the full analysis, now updated for this
    // 2-cycle pipeline.
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
                // (holds its previous value) — see the header comment
                // above: this self-hold is what keeps this register's
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
    // Read-after-write hazard analysis (updated 2026-09-17 for the bead rvb
    // Path A residual fix's 2-stage write pipeline — see the write FSM's
    // `ifndef SRAM_SKY130` block above for the pipeline itself):
    //
    // In-flight window: a write whose W handshake has been accepted but
    // whose 2-cycle pipeline has not yet landed it in mem[] (i.e. a read of
    // the same word issued anywhere from the handshake cycle through the
    // following 2 cycles) returns the OLD value — mem[] is a genuine flop
    // array and this read FSM has no forwarding/bypass path into the write
    // pipeline. This is the SAME accepted residual class bead ydw already
    // documented for the read side (a write landing while a stalled read
    // head holds stale data is not reflected either) — this fix widens that
    // pre-existing "no live RAW forwarding" property from 0 cycles to a
    // bounded 2-cycle window, it does not introduce a new hazard class.
    //
    // Ordering-respecting masters are safe by construction: BVALID for a
    // burst is held off (W_DRAIN) until its last beat has actually landed
    // in mem[] (see the write pipeline's B-channel note above), so any
    // master that waits for BVALID&&BREADY before issuing a same-address AR
    // is guaranteed the read returns the new data — the in-flight window
    // above is entirely contained between the W handshake and the (later)
    // BVALID, never after it.
    //
    // Masters checked this session for a same-address read issued WITHOUT
    // waiting for the preceding write's B (i.e. actually exposed to the
    // in-flight window above), all found SAFE-by-construction:
    //   - CPU D-cache (rtl/mem/rv32i_dcache.sv): CS_WRITEBACK only
    //     transitions to CS_REFILL on axi_bvalid_i && bresp==OKAY
    //     (rv32i_dcache.sv:749-751), and axi_arvalid_o is only driven from
    //     CS_REFILL (rv32i_dcache.sv:390) — no refill AR before the
    //     writeback's B is observed.
    //   - GPU memory_coalescer.sv: a single unified FSM handles one
    //     transaction (read XOR write) at a time; S_B only advances to
    //     S_DONE on m_bvalid_i (memory_coalescer.sv:192-198), and a new
    //     start_i (hence a new S_AR, memory_coalescer.sv:128) can only be
    //     issued after done_o, itself gated on S_DONE. NOT re-verified this
    //     session: whether gpu_top.sv/gpu_memory_unit.sv ever run multiple
    //     coalescer instances that could race an independent read engine
    //     against a different instance's in-flight write to the same SRAM
    //     word — only single-coalescer internal sequencing was checked.
    //   - DMA engine (rtl/periph/dma_engine.sv): single sequential FSM;
    //     S_B only advances to S_CALC/S_DESC_DONE on m_bvalid
    //     (dma_engine.sv:508-524), and S_CALC unconditionally moves to S_AR
    //     (dma_engine.sv:478-482) — no read state is reachable except
    //     through this B-gated path, including for an overlapping-address
    //     src/dst descriptor.
    //
    // No RTL bypass/forwarding path is added into the write pipeline for
    // the in-flight window itself: a same-address forwarding compare would
    // have to reach into the per-group stage-2 registers from the read
    // FSM's held index, reintroducing a comparison that spans the very
    // group boundaries this fix was designed to keep separate. If a future
    // master needs a hardware-guaranteed same-cycle (or in-flight-window)
    // RAW bypass to this SRAM, prefer comparing the read's held index
    // against `idx1_q`/`grp1_sel`+`local1_onehot` (the pipeline's own
    // already-narrow per-stage state) over reintroducing any MEM_WORDS-wide
    // structure.
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
