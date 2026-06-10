// rv32i_icache.sv
// Phase 3 — Instruction Cache (I$)
//
// Configuration: 4 KB, direct-mapped, 16-byte lines, write-through (read-only)
//
// SRAM macros used (selected at compile time via `SRAM_SKY130 define):
//   Default (FreePDK45):
//     - 1× sram_1rw_256x32_freepdk45  (tag array,  bits [19:0] = 20-bit tag)
//     - 4× sram_1rw_256x32_freepdk45  (data array, one per word column)
//   `ifdef SRAM_SKY130 (Sky130):
//     - 1× sky130_sram_1kbyte_1rw1r_32x256_8  (tag array)
//     - 4× sky130_sram_1kbyte_1rw1r_32x256_8  (data array)
//     wmask0=4'b1111 (full-word writes; byte masking done via R-M-W in cache logic)
//     Port 1 (read-only) is tied off (csb1=1) — unused in this design.
//
// Valid bits are kept in a 256-bit register array to support 1-cycle FENCE.I
// bulk-invalidation (the SRAM cannot do a bulk write).
//
// Timing model — SRAM has 1-cycle read latency (registered inputs):
//   CS_IDLE     : ic_valid_i asserted → issue SRAM read, stall=1
//   CS_TAG_CHECK: SRAM output available → check hit/miss
//                 hit  → stall=0, ic_rdata_o from SRAM dout, → CS_IDLE
//                 miss → stall=1, → CS_REFILL
//   CS_REFILL   : fetch 4 words from AXI, write each word to SRAM as it arrives
//                 last word → → CS_DONE
//   CS_DONE     : ic_rdata_o from refill_buf_q, stall=0, → CS_IDLE
//
// CPU-side interface (from IF stage):
//   - Present ic_addr_i + ic_valid_i each cycle
//   - Cache returns ic_rdata_o with ic_stall_o=0 on the cycle data is valid
//   - ic_stall_o=1 while waiting for SRAM read or line refill
//
// FENCE.I:
//   - Assert ic_invalidate_i for 1 cycle to clear all valid bits (register array)
//   - Next access will miss and refill from memory


import rv32i_cache_pkg::*;
import axi_pkg::*;

module rv32i_icache (
    input  logic        clk,
    input  logic        rst_n,

    // ── CPU-side interface (from IF stage) ────────────────────────────────────
    input  logic [31:0] ic_addr_i,        // Fetch address
    input  logic        ic_valid_i,       // Fetch request valid
    output logic [31:0] ic_rdata_o,       // Instruction word
    output logic        ic_stall_o,       // 1 = stall the pipeline
    output logic        ic_miss_o,        // 1-cycle pulse: CS_TAG_CHECK miss → CS_REFILL

    // ── FENCE.I invalidation ──────────────────────────────────────────────────
    input  logic        ic_invalidate_i,  // Invalidate all lines (1-cycle pulse)

    // ── AXI4 read-only (to cache arbiter) ────────────────────────────────────
    output logic [31:0]                    axi_araddr_o,
    output logic [AXI_LEN_WIDTH-1:0]      axi_arlen_o,
    output logic [AXI_SIZE_WIDTH-1:0]     axi_arsize_o,
    output logic [1:0]                    axi_arburst_o,
    output logic                          axi_arvalid_o,
    input  logic                          axi_arready_i,

    input  logic [31:0] axi_rdata_i,
    input  logic [1:0]  axi_rresp_i,
    input  logic        axi_rvalid_i,
    input  logic        axi_rlast_i,
    output logic        axi_rready_o
);

    // =========================================================================
    // Valid bits — register array (supports 1-cycle bulk clear for FENCE.I)
    // =========================================================================
    logic valid_array [0:N_SETS-1];   // 256 flip-flops — negligible area

    // =========================================================================
    // Tag SRAM instance (1× 32×256, bits [TAG_BITS-1:0] = 20-bit tag)
    // =========================================================================
    logic        tag_csb0, tag_web0;
    logic [7:0]  tag_addr0;
    logic [31:0] tag_din0, tag_dout0;

`ifdef SRAM_SKY130
    sky130_sram_1kbyte_1rw1r_32x256_8 u_tag_sram (
        .clk0   (clk),
        .csb0   (tag_csb0),
        .web0   (tag_web0),
        .wmask0 (4'b1111),
        .addr0  (tag_addr0),
        .din0   (tag_din0),
        .dout0  (tag_dout0),
        .clk1   (clk),
        .csb1   (1'b1),
        .addr1  (8'b0),
        .dout1  ()
    );
`elsif SRAM_ASAP7
    logic tag_gclk;
    rv32i_clock_gate u_tag_cg (.en(!tag_csb0), .clk(clk), .gclk(tag_gclk));
    sram_1rw_256x32_asap7 u_tag_sram (
        .clk0   (tag_gclk),
        .csb0   (tag_csb0),
        .web0   (tag_web0),
        .addr0  (tag_addr0),
        .din0   (tag_din0),
        .dout0  (tag_dout0)
    );
`else
    sram_1rw_256x32_freepdk45 u_tag_sram (
        .clk0   (clk),
        .csb0   (tag_csb0),
        .web0   (tag_web0),
        .addr0  (tag_addr0),
        .din0   (tag_din0),
        .dout0  (tag_dout0)
    );
`endif

    // =========================================================================
    // Data SRAM instances (4× 32×256, one per word column in a cache line)
    // =========================================================================
    logic        data_csb0   [0:LINE_WORDS-1];
    logic        data_web0   [0:LINE_WORDS-1];
    logic [7:0]  data_addr0  [0:LINE_WORDS-1];
    logic [31:0] data_din0   [0:LINE_WORDS-1];
    logic [31:0] data_dout0  [0:LINE_WORDS-1];

    genvar gw;
    generate
        for (gw = 0; gw < LINE_WORDS; gw++) begin : gen_data_sram
`ifdef SRAM_SKY130
            sky130_sram_1kbyte_1rw1r_32x256_8 u_data_sram (
                .clk0   (clk),
                .csb0   (data_csb0[gw]),
                .web0   (data_web0[gw]),
                .wmask0 (4'b1111),
                .addr0  (data_addr0[gw]),
                .din0   (data_din0[gw]),
                .dout0  (data_dout0[gw]),
                .clk1   (clk),
                .csb1   (1'b1),
                .addr1  (8'b0),
                .dout1  ()
            );
`elsif SRAM_ASAP7
            logic data_gclk;
            rv32i_clock_gate u_data_cg (.en(!data_csb0[gw]), .clk(clk), .gclk(data_gclk));
            sram_1rw_256x32_asap7 u_data_sram (
                .clk0   (data_gclk),
                .csb0   (data_csb0[gw]),
                .web0   (data_web0[gw]),
                .addr0  (data_addr0[gw]),
                .din0   (data_din0[gw]),
                .dout0  (data_dout0[gw])
            );
`else
            sram_1rw_256x32_freepdk45 u_data_sram (
                .clk0   (clk),
                .csb0   (data_csb0[gw]),
                .web0   (data_web0[gw]),
                .addr0  (data_addr0[gw]),
                .din0   (data_din0[gw]),
                .dout0  (data_dout0[gw])
            );
`endif
        end
    endgenerate

    // =========================================================================
    // FSM state and pipeline registers
    // =========================================================================
    cache_state_t state_q;

    // Latched access address (registered when entering CS_TAG_CHECK)
    logic [31:0]           ic_addr_q;
    logic [TAG_BITS-1:0]   latch_tag;
    logic [INDEX_BITS-1:0] latch_index;
    logic [1:0]            latch_word;

    // Refill control
    logic [31:0]                 refill_line_addr_q;
    logic [1:0]                  refill_word_q;
    logic                        ar_pending_q;
    logic                        cancel_ar_q;       // AR mid-handshake after cancel — hold arvalid
    logic                        cancel_wait_r_q;   // AR accepted after cancel — single-beat drain (legacy, unused in burst)
    logic                        cancel_draining;   // Burst in flight at abort — drain until RLAST
    logic [LINE_WORDS-1:0][31:0] refill_buf_q;   // Accumulates all 4 words

    // Run-19 P2: Per-bank duplicate of refill_line_addr_q.
    // refill_line_addr_q[11:4] fans to all 4 data SRAM addr0 ports in CS_REFILL,
    // creating ~530 fanout paths through the refill_word_q decode tree.
    // Each per-bank copy is loaded identically but (* keep = 1 *) prevents
    // Yosys from re-merging them, so each drives only 1 bank's addr0/din0
    // control — reducing fanout 4×. Functional behaviour is unchanged.
    (* keep = 1 *) logic [31:0] refill_addr_bank_q [0:LINE_WORDS-1];

    // SRAM output pipeline registers — capture negedge-launched dout at posedge
    logic [31:0] tag_dout_r;
    logic [31:0] data_dout_r [0:LINE_WORDS-1];

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            tag_dout_r <= '0;
            for (int i = 0; i < LINE_WORDS; i++) data_dout_r[i] <= '0;
        end else if (state_q == CS_SRAM_LATCH) begin
            tag_dout_r <= tag_dout0;
            for (int i = 0; i < LINE_WORDS; i++) data_dout_r[i] <= data_dout0[i];
        end
    end

    // =========================================================================
    // Combinational: address field extraction from live input
    // =========================================================================
    logic [INDEX_BITS-1:0] addr_index;
    assign addr_index = ic_addr_i[11:4];

    // =========================================================================
    // Address mismatch detection
    // After a branch redirect, pc_q changes while the cache may still be
    // processing the old (pre-redirect) address.  Detect this by comparing
    // the live fetch address (ic_addr_i = pc_q) against the latched address
    // (ic_addr_q) in the states that complete the previous SRAM lookup.
    // When a mismatch is detected the in-flight result is discarded and the
    // cache restarts for the new address.
    // =========================================================================
    logic addr_mismatch;
    assign addr_mismatch = ic_valid_i
                         && (ic_addr_i != ic_addr_q)
                         && (state_q == CS_SRAM_LATCH || state_q == CS_TAG_CHECK
                             || state_q == CS_REFILL);

    // =========================================================================
    // Hit detection (combinational in CS_TAG_CHECK)
    // tag_dout0[TAG_BITS-1:0] is the SRAM output from the read issued in CS_IDLE
    // =========================================================================
    logic hit;
    assign hit = (state_q == CS_TAG_CHECK) &&
                 !addr_mismatch            &&
                 valid_array[latch_index]  &&
                 (tag_dout_r[TAG_BITS-1:0] == latch_tag);

    // =========================================================================
    // Stall output
    // =========================================================================
    assign ic_stall_o =
        (state_q == CS_IDLE       &&  ic_valid_i) ||   // Initiating SRAM read
        (state_q == CS_SRAM_LATCH)                ||   // Waiting for pipeline reg
        (state_q == CS_TAG_CHECK  && !hit)         ||   // Miss detected (or mismatch)
        (state_q == CS_REFILL);                         // Refill in progress
    // CS_TAG_CHECK + hit : stall=0, ic_rdata_o from tag_dout_r/data_dout_r
    // CS_DONE            : stall=0, ic_rdata_o from refill_buf_q

    // =========================================================================
    // Miss strobe output (Phase 5 M7 — performance counter event)
    // Asserted for exactly 1 cycle: the CS_TAG_CHECK cycle where miss is detected.
    // Excludes addr_mismatch (redirect abort, not a true demand miss).
    // =========================================================================
    assign ic_miss_o = (state_q == CS_TAG_CHECK) && !hit && !addr_mismatch;

    // =========================================================================
    // Read data output
    // =========================================================================
    always_comb begin
        case (state_q)
            CS_TAG_CHECK: ic_rdata_o = data_dout_r[latch_word];
            CS_DONE:      ic_rdata_o = refill_buf_q[latch_word];
            default:      ic_rdata_o = 32'b0;
        endcase
    end

    // =========================================================================
    // AXI read control — burst mode
    //   One AR per line: address = line-base (slave auto-increments 4 B per beat).
    //   ARLEN=3 (4 beats), ARSIZE=4B, ARBURST=INCR (constant).
    //   cancel_ar_q holds arvalid after a cancel to satisfy AXI A3.2.1.
    //   cancel_draining: burst accepted at abort — drain all 4 R beats silently.
    //   TRUSTED-SLAVE ASSUMPTION: refill completion keys on rvalid && rlast and
    //   trusts the slave to deliver exactly ARLEN+1 beats (AXI4 requires this).
    //   A protocol-violating early RLAST would mark a partially-filled line
    //   valid; slave conformance is pinned by test_sram_controller.py
    //   test_rlast_position rather than defended here.
    // =========================================================================
    assign axi_araddr_o  = {refill_line_addr_q[31:4], 4'b0000};
    assign axi_arlen_o   = axi_pkg::AXI_LEN_LINE;
    assign axi_arsize_o  = axi_pkg::AXI_SIZE_4B;
    assign axi_arburst_o = axi_pkg::AXI_BURST_INCR;
    assign axi_arvalid_o = ((state_q == CS_REFILL) && !ar_pending_q && !cancel_draining) || cancel_ar_q;
    assign axi_rready_o  = 1'b1;  // Always accept R responses (drains in-flight beats)

    // =========================================================================
    // Tag SRAM write — registered commit (Run-17 P2 timing fix)
    //
    // The combinational cone from state_q (CS_REFILL one-hot bit) into
    // tag_web0/tag_din0 had 298 fanout sinks and was the second-worst ASAP7
    // critical path at -606 ps.  Inserting a 1-cycle pipeline register
    // between the commit condition and the SRAM ports breaks this cone.
    //
    // Latency impact: the tag SRAM write occurs 1 cycle after the last AXI
    // beat arrives instead of the same cycle.  The valid_array[idx] set is
    // delayed by the same 1 cycle (see valid_array always_ff below).
    // CS_REFILL transitions to CS_DONE (or CS_IDLE on mismatch) on the same
    // cycle as before — the registered write simply completes in the background
    // during CS_DONE, which is a no-stall cycle.  Correctness is preserved
    // because the CPU reads ic_rdata_o from refill_buf_q in CS_DONE, not from
    // the tag SRAM.
    // =========================================================================
    logic        tag_write_commit; // combinational commit qualifier
    logic        tag_we_q;         // registered: assert SRAM write next cycle
    logic [31:0] tag_din_q;        // registered: tag data to write
    logic [7:0]  tag_idx_q;        // registered: SRAM row index to write

    assign tag_write_commit = (state_q == CS_REFILL)
                            && ar_pending_q
                            && axi_rvalid_i
                            && axi_rlast_i
                            && !addr_mismatch
                            && ic_valid_i;

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            tag_we_q  <= 1'b0;
            tag_din_q <= 32'b0;
            tag_idx_q <= 8'b0;
        end else begin
            tag_we_q  <= tag_write_commit;
            tag_din_q <= {12'b0, refill_line_addr_q[31:12]};  // tag in [19:0]
            tag_idx_q <= refill_line_addr_q[11:4];
        end
    end

    // =========================================================================
    // SRAM combinational control — Tag SRAM (port 0)
    // =========================================================================
    always_comb begin
        tag_csb0   = 1'b1;       // default: disabled
        tag_web0   = 1'b1;       // default: read mode
        tag_addr0  = 8'b0;
        tag_din0   = 32'b0;

        case (state_q)
            CS_IDLE: begin
                // Issue tag read when a new valid fetch arrives (not FENCE.I)
                if (ic_valid_i && !ic_invalidate_i) begin
                    tag_csb0  = 1'b0;
                    tag_web0  = 1'b1;   // read
                    tag_addr0 = addr_index;
                end
            end

            default: ;
        endcase

        // Registered tag write — driven from FFs, not combinationally from
        // state_q.  Overrides the read defaults when tag_we_q is asserted.
        // This can coincide with CS_IDLE (which issues a read for a new access)
        // or CS_DONE (idle/read cycle after refill): the write takes priority
        // by overriding csb0/web0/addr0/din0.
        if (tag_we_q) begin
            tag_csb0  = 1'b0;
            tag_web0  = 1'b0;   // write
            tag_addr0 = tag_idx_q;
            tag_din0  = tag_din_q;
        end
    end

    // =========================================================================
    // Data SRAM write — registered commit (Run-22 timing fix)
    //
    // The combinational cone from state_q (CS_REFILL) + axi_rvalid_i into
    // data_csb0/web0/addr0/din0 had ~530+ fanout sinks and was the dominant
    // ASAP7 critical-path cluster after Run 21.  Inserting a 1-cycle pipeline
    // register between the commit condition and the SRAM ports breaks this cone,
    // mirroring the Run-17 P2 tag-SRAM registered-commit fix (tag_we_q above).
    //
    // Latency impact: each refill beat's data SRAM write occurs 1 cycle after
    // the AXI beat arrives.  Beat 3 fires during CS_DONE (the no-stall cycle),
    // same timing as the tag write.  Correctness is preserved because the CPU
    // reads ic_rdata_o from refill_buf_q in CS_DONE, not from the data SRAMs.
    // valid_array is gated on tag_we_q, so the line is not visible as valid
    // until the tag write commits — by then all 4 data writes have also fired.
    // =========================================================================
    logic        data_write_commit;
    logic        data_we_q;
    logic [31:0] data_din_q;
    logic [7:0]  data_idx_q;
    logic [1:0]  data_bank_q;

    assign data_write_commit = (state_q == CS_REFILL)
                             && ar_pending_q
                             && axi_rvalid_i
                             && !addr_mismatch;

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            data_we_q   <= 1'b0;
            data_din_q  <= 32'b0;
            data_idx_q  <= 8'b0;
            data_bank_q <= 2'b0;
        end else begin
            data_we_q   <= data_write_commit;
            data_din_q  <= axi_rdata_i;
            data_idx_q  <= refill_addr_bank_q[refill_word_q][11:4];
            data_bank_q <= refill_word_q;
        end
    end

    // =========================================================================
    // SRAM combinational control — Data SRAMs (port 0, all 4 instances)
    // Run-19 P2: Use per-bank duplicate refill_addr_bank_q for addr0/csb0/web0.
    // Run-22: CS_REFILL write removed from comb path — handled by data_we_q FFs.
    // =========================================================================
    always_comb begin
        for (int w = 0; w < LINE_WORDS; w++) begin
            data_csb0[w]  = 1'b1;
            data_web0[w]  = 1'b1;
            data_addr0[w] = 8'b0;
            data_din0[w]  = 32'b0;
        end

        case (state_q)
            CS_IDLE: begin
                // Issue read on all 4 word SRAMs simultaneously (same index)
                if (ic_valid_i && !ic_invalidate_i) begin
                    for (int w = 0; w < LINE_WORDS; w++) begin
                        data_csb0[w]  = 1'b0;
                        data_web0[w]  = 1'b1;  // read
                        data_addr0[w] = addr_index;
                    end
                end
            end

            default: ;
        endcase

        // Registered data write — driven from FFs, not combinationally from
        // state_q.  Overrides the read defaults when data_we_q is asserted.
        // Mirrors the tag_we_q registered-write override above.
        if (data_we_q) begin
            data_csb0[data_bank_q]  = 1'b0;
            data_web0[data_bank_q]  = 1'b0;   // write
            data_addr0[data_bank_q] = data_idx_q;
            data_din0[data_bank_q]  = data_din_q;
        end
    end

    // =========================================================================
    // FSM — sequential logic
    // =========================================================================
    always_ff @(posedge clk) begin
        if (!rst_n) begin
            state_q            <= CS_IDLE;
            ic_addr_q          <= '0;
            refill_line_addr_q <= '0;
            for (int b = 0; b < LINE_WORDS; b++) refill_addr_bank_q[b] <= '0;
            refill_word_q      <= 2'b00;
            ar_pending_q       <= 1'b0;
            cancel_ar_q        <= 1'b0;
            cancel_wait_r_q    <= 1'b0;
            cancel_draining    <= 1'b0;
            refill_buf_q       <= '0;
        end else begin
            // ----------------------------------------------------------------
            // Background drain: advance cancel-drain flags independently of
            // FSM state.
            //
            // cancel_ar_q: AR mid-handshake at abort — keep arvalid asserted
            //   until arready fires (AXI A3.2.1).  On acceptance, the slave
            //   WILL deliver a full 4-beat burst; start cancel_draining so the
            //   next refill waits until the burst completes.
            if (cancel_ar_q && axi_arready_i) begin
                cancel_ar_q     <= 1'b0;
                // Burst now in flight; drain all remaining beats.
                cancel_draining <= !(axi_rvalid_i && axi_rlast_i);
            end
            // cancel_draining: burst accepted before/at abort — drain until RLAST.
            if (cancel_draining && axi_rvalid_i && axi_rlast_i)
                cancel_draining <= 1'b0;
            // cancel_wait_r_q is unused in burst mode but kept for symmetry;
            // clear it unconditionally once any R beat arrives.
            if (cancel_wait_r_q && axi_rvalid_i)
                cancel_wait_r_q <= 1'b0;

            case (state_q)
                // -----------------------------------------------------------------
                CS_IDLE: begin
                    if (!cancel_ar_q && !cancel_wait_r_q && !cancel_draining
                            && ic_valid_i && !ic_invalidate_i) begin
                        // Issue SRAM read (combinational, above). Latch address and
                        // go to CS_SRAM_LATCH to capture SRAM output at next posedge.
                        ic_addr_q <= ic_addr_i;
                        state_q   <= CS_SRAM_LATCH;
                    end
                end

                // -----------------------------------------------------------------
                CS_SRAM_LATCH: begin
                    // tag_dout_r / data_dout_r captured in always_ff above.
                    // Abort on FENCE.I or address mismatch (branch redirect).
                    if (ic_invalidate_i || addr_mismatch)
                        state_q <= CS_IDLE;
                    else
                        state_q <= CS_TAG_CHECK;
                end

                // -----------------------------------------------------------------
                CS_TAG_CHECK: begin
                    if (addr_mismatch) begin
                        // Address changed mid-lookup (branch redirect) — discard
                        // the in-flight result and restart for the new address.
                        state_q <= CS_IDLE;
                    end else if (hit) begin
                        // Hit — data available from SRAM dout this cycle.
                        // Return to IDLE; pipeline sees stall=0 this cycle.
                        state_q <= CS_IDLE;
                    end else begin
                        // Miss — start refill
                        refill_line_addr_q <= {ic_addr_q[31:4], 4'b0000};
                        for (int b = 0; b < LINE_WORDS; b++)
                            refill_addr_bank_q[b] <= {ic_addr_q[31:4], 4'b0000};
                        refill_word_q      <= 2'b00;
                        ar_pending_q       <= 1'b0;
                        state_q            <= CS_REFILL;
                    end
                end

                // -----------------------------------------------------------------
                CS_REFILL: begin
                    // Abort on FENCE.I or cancelled request (!ic_valid_i).
                    // A cancelled request occurs when the pipeline halts (dbg_halt_req=1
                    // causes ic_valid_o=0) while a cache-line refill is still in progress.
                    // Without this abort the I-cache would fill from AXI with stale
                    // (pre-program-load) data, then serve those zeros to the CPU on resume.
                    // axi_rready_o=1'b1 drains any in-flight AXI beats without data loss.
                    if (ic_invalidate_i || !ic_valid_i) begin
                        state_q <= CS_IDLE;
                        // Determine AXI drain mode at cancel time (burst variant):
                        //   ar_pending_q=0, arready=0: AR mid-handshake — hold arvalid.
                        //     Slave will launch burst after arready; start draining then.
                        //   ar_pending_q=0, arready=1: AR accepted this cycle — burst
                        //     in flight unless RLAST also arrives now.
                        //   ar_pending_q=1, rvalid=0:  Burst beats still in flight — drain.
                        //   ar_pending_q=1, rvalid=1:  Beat arriving now; if RLAST, done.
                        cancel_ar_q     <= !ar_pending_q && !axi_arready_i;
                        cancel_draining <= ( ar_pending_q && !(axi_rvalid_i && axi_rlast_i)) ||
                                           (!ar_pending_q &&   axi_arready_i && !(axi_rvalid_i && axi_rlast_i));
                        cancel_wait_r_q <= 1'b0;
                        ar_pending_q    <= 1'b0;
                        refill_word_q   <= 2'b00;
                    end else begin
                        // Issue single AR for the full 4-beat burst
                        if (!ar_pending_q) begin
                            if (axi_arready_i)
                                ar_pending_q <= 1'b1;
                                // refill_word_q stays 0; it is the beat index
                        end else begin
                            // Collect R beats until RLAST
                            if (axi_rvalid_i) begin
                                refill_buf_q[refill_word_q] <= axi_rdata_i;
                                if (axi_rlast_i) begin
                                    // Defensive: assert refill_word_q==3 here.
                                    // Transition: commit if address still valid, else discard.
                                    state_q       <= addr_mismatch ? CS_IDLE : CS_DONE;
                                    ar_pending_q  <= 1'b0;
                                    refill_word_q <= 2'b00;
                                end else begin
                                    // Guard: never let word counter wrap past 3
                                    if (refill_word_q != 2'd3)
                                        refill_word_q <= refill_word_q + 1'b1;
                                end
                            end
                        end
                    end
                end

                // -----------------------------------------------------------------
                CS_DONE: begin
                    // ic_rdata_o comes from refill_buf_q[latch_word] this cycle.
                    // stall=0. Return to IDLE.
                    state_q <= CS_IDLE;
                end

                default: state_q <= CS_IDLE;
            endcase
        end
    end

    // =========================================================================
    // Latched address fields (derived from ic_addr_q after it is registered)
    // =========================================================================
    assign latch_tag   = ic_addr_q[31:12];
    assign latch_index = ic_addr_q[11:4];
    assign latch_word  = ic_addr_q[3:2];

    // =========================================================================
    // Valid array — sequential (register array, supports 1-cycle bulk clear)
    //
    // Run-17 P2: valid_array set is delayed by 1 cycle (uses tag_we_q, the
    // same registered signal that gates the tag SRAM write) so that the line
    // is not visible as valid until the tag SRAM write has been registered in.
    // The index to mark valid is captured in tag_idx_q on the same cycle.
    // =========================================================================
    always_ff @(posedge clk) begin
        if (!rst_n || ic_invalidate_i) begin
            // Reset or FENCE.I: invalidate all lines in one cycle
            for (int j = 0; j < N_SETS; j++)
                valid_array[j] = 1'b0;
        end else if (tag_we_q) begin
            // tag_we_q is the registered version of tag_write_commit (the last-beat
            // commit qualifier).  Marking valid here ensures the line is considered
            // valid on the same cycle the tag SRAM write is clocked in.
            valid_array[tag_idx_q] <= 1'b1;
        end
    end

    // Suppress unused signal warning for AXI rresp
    /* verilator lint_off UNUSEDSIGNAL */
    logic _unused_rresp = |axi_rresp_i;
    /* verilator lint_on UNUSEDSIGNAL */

endmodule
