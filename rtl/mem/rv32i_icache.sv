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

module rv32i_icache (
    input  logic        clk,
    input  logic        rst_n,

    // ── CPU-side interface (from IF stage) ────────────────────────────────────
    input  logic [31:0] ic_addr_i,        // Fetch address
    input  logic        ic_valid_i,       // Fetch request valid
    output logic [31:0] ic_rdata_o,       // Instruction word
    output logic        ic_stall_o,       // 1 = stall the pipeline

    // ── FENCE.I invalidation ──────────────────────────────────────────────────
    input  logic        ic_invalidate_i,  // Invalidate all lines (1-cycle pulse)

    // ── AXI4-Lite read-only (to cache arbiter) ────────────────────────────────
    output logic [31:0] axi_araddr_o,
    output logic        axi_arvalid_o,
    input  logic        axi_arready_i,

    input  logic [31:0] axi_rdata_i,
    input  logic [1:0]  axi_rresp_i,
    input  logic        axi_rvalid_i,
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
    sram_1rw_256x32_asap7 u_tag_sram (
        .clk0   (clk),
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
            sram_1rw_256x32_asap7 u_data_sram (
                .clk0   (clk),
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
    logic                        cancel_wait_r_q;   // AR accepted after cancel — drain stale R beat
    logic [LINE_WORDS-1:0][31:0] refill_buf_q;   // Accumulates all 4 words

    // SRAM output pipeline registers — capture negedge-launched dout at posedge
    logic [31:0] tag_dout_r;
    logic [31:0] data_dout_r [0:LINE_WORDS-1];

    always_ff @(posedge clk or negedge rst_n) begin
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
    // AXI read control
    // =========================================================================
    assign axi_araddr_o  = {refill_line_addr_q[31:4], refill_word_q, 2'b00};
    // cancel_ar_q holds arvalid asserted after a cancel until arready fires,
    // satisfying AXI A3.2.1 (arvalid must not retract before arready).
    assign axi_arvalid_o = ((state_q == CS_REFILL) && !ar_pending_q) || cancel_ar_q;
    assign axi_rready_o  = 1'b1;  // Always accept R responses (drains in-flight beats)

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

            CS_REFILL: begin
                // Write tag on last word (when entire line is committed).
                // Guard with !addr_mismatch: if IC address changed during refill,
                // do not commit stale tag — data SRAM was already guarded the same way.
                if (ar_pending_q && axi_rvalid_i && !addr_mismatch && ic_valid_i && (refill_word_q == 2'd3)) begin
                    tag_csb0   = 1'b0;
                    tag_web0   = 1'b0;  // write
                    tag_addr0  = refill_line_addr_q[11:4];
                    tag_din0   = {12'b0, refill_line_addr_q[31:12]};  // tag in [19:0]
                end
            end

            default: ;
        endcase
    end

    // =========================================================================
    // SRAM combinational control — Data SRAMs (port 0, all 4 instances)
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

            CS_REFILL: begin
                // Write each word to its SRAM column as it arrives from AXI.
                // Suppress write for stale refills (address changed mid-flight).
                if (ar_pending_q && axi_rvalid_i && !addr_mismatch) begin
                    data_csb0[refill_word_q]  = 1'b0;
                    data_web0[refill_word_q]  = 1'b0;  // write
                    data_addr0[refill_word_q] = refill_line_addr_q[11:4];
                    data_din0[refill_word_q]   = axi_rdata_i;
                end
            end

            default: ;
        endcase
    end

    // =========================================================================
    // FSM — sequential logic
    // =========================================================================
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state_q            <= CS_IDLE;
            ic_addr_q          <= '0;
            refill_line_addr_q <= '0;
            refill_word_q      <= 2'b00;
            ar_pending_q       <= 1'b0;
            cancel_ar_q        <= 1'b0;
            cancel_wait_r_q    <= 1'b0;
            refill_buf_q       <= '0;
        end else begin
            // Background drain: advance cancel-drain flags independently of FSM state.
            // AR completes after cancel → promote to wait-for-R.
            if (cancel_ar_q && axi_arready_i) begin
                cancel_ar_q     <= 1'b0;
                cancel_wait_r_q <= !axi_rvalid_i;
            end
            // Stale R beat drains → safe to start a new refill.
            if (cancel_wait_r_q && axi_rvalid_i)
                cancel_wait_r_q <= 1'b0;

            case (state_q)
                // -----------------------------------------------------------------
                CS_IDLE: begin
                    if (!cancel_ar_q && !cancel_wait_r_q && ic_valid_i && !ic_invalidate_i) begin
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
                    // axi_rready_o=1'b1 drains any in-flight AXI beat without data loss.
                    if (ic_invalidate_i || !ic_valid_i) begin
                        state_q       <= CS_IDLE;
                        // Determine which AXI drain mode is needed at cancel time:
                        //   ar_pending_q=1, rvalid=0  → R still in flight, drain it
                        //   ar_pending_q=1, rvalid=1  → R consumed this cycle, no drain
                        //   ar_pending_q=0, arready=1 → AR just accepted, drain its R
                        //   ar_pending_q=0, arready=0 → AR mid-handshake, hold arvalid
                        cancel_ar_q     <= !ar_pending_q && !axi_arready_i;
                        cancel_wait_r_q <= ( ar_pending_q && !axi_rvalid_i) ||
                                           (!ar_pending_q &&  axi_arready_i && !axi_rvalid_i);
                        ar_pending_q  <= 1'b0;
                        refill_word_q <= 2'b00;
                    end else begin
                        // Issue AR for current word
                        if (!ar_pending_q) begin
                            if (axi_arready_i)
                                ar_pending_q <= 1'b1;
                        end else begin
                            // Waiting for R response
                            if (axi_rvalid_i) begin
                                refill_buf_q[refill_word_q] <= axi_rdata_i;
                                ar_pending_q <= 1'b0;
                                if (refill_word_q == 2'd3) begin
                                    // All 4 words received.  Only commit the line if the
                                    // address hasn't changed (stale-refill guard).
                                    state_q <= addr_mismatch ? CS_IDLE : CS_DONE;
                                end else begin
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
    // =========================================================================
    always_ff @(posedge clk) begin
        if (!rst_n || ic_invalidate_i) begin
            // Reset or FENCE.I: invalidate all lines in one cycle
            for (int j = 0; j < N_SETS; j++)
                valid_array[j] = 1'b0;
        end else if (state_q == CS_REFILL &&
                     ar_pending_q && axi_rvalid_i && !addr_mismatch && ic_valid_i && (refill_word_q == 2'd3)) begin
            // Refill complete and address still matches — mark line valid.
            // !addr_mismatch guard prevents marking valid when fetch address changed mid-refill.
            // ic_valid_i guard prevents committing when the request was cancelled (e.g. pc_redirect
            // deasserts ic_valid_o while the last AXI beat arrives — addr_mismatch cannot catch
            // this because it requires ic_valid_i to be high).
            valid_array[refill_line_addr_q[11:4]] <= 1'b1;
        end
    end

    // Suppress unused signal warning for AXI rresp
    /* verilator lint_off UNUSEDSIGNAL */
    logic _unused_rresp = |axi_rresp_i;
    /* verilator lint_on UNUSEDSIGNAL */

endmodule
