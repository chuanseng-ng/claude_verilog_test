// rv32i_dcache.sv
// Phase 3 — Data Cache (D$)
//
// Configuration: 4 KB, direct-mapped, 16-byte lines, write-back + write-allocate
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
// Valid bits  (256b) and dirty bits (256b) are kept as register arrays:
//   - valid_array: needed for 1-cycle bulk reset and in-cycle hit detection
//   - dirty_array: needed for writeback decision in CS_TAG_CHECK
//
// Timing model — SRAM has 1-cycle read latency:
//   CS_IDLE     : dc_valid_i → issue SRAM read (all 5 SRAMs), stall=1
//   CS_TAG_CHECK: SRAM output available
//                 read  hit → stall=0, dc_rdata_o from data SRAM dout
//                 write hit → issue SRAM byte-masked write, stall=0, dirty←1
//                 miss, clean victim → → CS_REFILL
//                 miss, dirty victim → capture dirty line from data SRAM dout
//                                      into wb_buf_q, → CS_WRITEBACK
//   CS_WRITEBACK: send wb_buf_q[0..3] to AXI word-by-word, → CS_REFILL
//   CS_REFILL   : fetch 4 words from AXI, write to SRAM (with write-allocate
//                 byte merge for write-miss), update valid/tag, → CS_DONE
//   CS_DONE     : dc_rdata_o from refill_buf_q (read-miss), stall=0, → CS_IDLE
//                 (write-miss: dc_rdata_o unused, stall=0 releases store)


import rv32i_cache_pkg::*;

module rv32i_dcache (
    input  logic        clk,
    input  logic        rst_n,

    // ── CPU-side interface (from MEM stage) ───────────────────────────────────
    input  logic [31:0] dc_addr_i,
    input  logic        dc_valid_i,
    input  logic        dc_we_i,
    input  logic [31:0] dc_wdata_i,
    input  logic [3:0]  dc_wstrb_i,
    output logic [31:0] dc_rdata_o,
    output logic        dc_stall_o,

    // ── AXI4-Lite read channel (refill) ──────────────────────────────────────
    output logic [31:0] axi_araddr_o,
    output logic        axi_arvalid_o,
    input  logic        axi_arready_i,

    input  logic [31:0] axi_rdata_i,
    input  logic [1:0]  axi_rresp_i,
    input  logic        axi_rvalid_i,
    output logic        axi_rready_o,

    // ── AXI4-Lite write channel (writeback) ──────────────────────────────────
    output logic [31:0] axi_awaddr_o,
    output logic        axi_awvalid_o,
    input  logic        axi_awready_i,

    output logic [31:0] axi_wdata_o,
    output logic [3:0]  axi_wstrb_o,
    output logic        axi_wvalid_o,
    input  logic        axi_wready_i,

    input  logic        axi_bvalid_i,
    input  logic [1:0]  axi_bresp_i,
    output logic        axi_bready_o
);

    // =========================================================================
    // Valid and dirty bits — register arrays (in-cycle access, bulk reset)
    // =========================================================================
    logic valid_array [0:N_SETS-1];
    logic dirty_array [0:N_SETS-1];

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
    // Data SRAM instances (4× 32×256, one per word column)
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

    // Latched access address and control (registered when entering CS_TAG_CHECK)
    logic [31:0]           dc_addr_q;
    logic                  dc_we_q;
    logic [31:0]           dc_wdata_q;
    logic [3:0]            dc_wstrb_q;

    logic [TAG_BITS-1:0]   latch_tag;
    logic [INDEX_BITS-1:0] latch_index;
    logic [1:0]            latch_word;

    // Writeback buffer: holds the full dirty line captured in CS_TAG_CHECK
    logic [LINE_WORDS-1:0][31:0] wb_buf_q;
    logic [TAG_BITS-1:0]         wb_tag_q;
    logic [INDEX_BITS-1:0]       wb_index_q;

    // Refill buffer and write-miss flag
    logic [LINE_WORDS-1:0][31:0] refill_buf_q;
    logic                        is_write_q;

    // AXI word counter (refill and writeback)
    logic [1:0]  axi_word_q;
    logic        ar_pending_q;
    logic        aw_done_q;
    logic        w_done_q;

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
    // Combinational: address fields from live input
    // =========================================================================
    logic [INDEX_BITS-1:0] addr_index;
    assign addr_index = dc_addr_i[11:4];

    // =========================================================================
    // Latched address field aliases
    // =========================================================================
    assign latch_tag   = dc_addr_q[31:12];
    assign latch_index = dc_addr_q[11:4];
    assign latch_word  = dc_addr_q[3:2];

    // =========================================================================
    // Writeback base address (reconstructed from evicted tag + index)
    // =========================================================================
    logic [31:0] wb_addr_base;
    assign wb_addr_base = {wb_tag_q, wb_index_q, 4'b0000};

    // Refill base address
    logic [31:0] refill_base;
    assign refill_base = {dc_addr_q[31:4], 4'b0000};

    // =========================================================================
    // Hit detection (combinational in CS_TAG_CHECK)
    // =========================================================================
    logic hit;
    assign hit = (state_q == CS_TAG_CHECK) &&
                 valid_array[latch_index] &&
                 (tag_dout_r[TAG_BITS-1:0] == latch_tag);

    // Need writeback: victim line is valid, dirty, and different tag
    logic need_writeback;
    assign need_writeback = valid_array[latch_index] &&
                            dirty_array[latch_index] &&
                            (tag_dout_r[TAG_BITS-1:0] != latch_tag);

    // =========================================================================
    // Stall output
    // =========================================================================
    assign dc_stall_o =
        (state_q == CS_IDLE       && dc_valid_i) ||   // Initiating SRAM read
        (state_q == CS_SRAM_LATCH)               ||   // Waiting for pipeline reg
        (state_q == CS_TAG_CHECK  && !hit)        ||   // Miss or still checking
        (state_q == CS_WRITEBACK)                ||   // Writing back dirty line
        (state_q == CS_REFILL);                        // Refilling
    // CS_TAG_CHECK + hit: stall=0
    // CS_DONE: stall=0

    // =========================================================================
    // Read data output
    // =========================================================================
    always_comb begin
        case (state_q)
            CS_TAG_CHECK: dc_rdata_o = data_dout_r[latch_word];  // read hit
            CS_DONE:      dc_rdata_o = refill_buf_q[latch_word]; // read-miss refilled
            default:      dc_rdata_o = 32'b0;
        endcase
    end

    // =========================================================================
    // AXI read control (refill)
    // =========================================================================
    assign axi_araddr_o  = {refill_base[31:4], axi_word_q, 2'b00};
    assign axi_arvalid_o = (state_q == CS_REFILL) && !ar_pending_q;
    assign axi_rready_o  = 1'b1;

    // =========================================================================
    // AXI write control (writeback)
    // =========================================================================
    assign axi_awaddr_o  = {wb_addr_base[31:4], axi_word_q, 2'b00};
    assign axi_awvalid_o = (state_q == CS_WRITEBACK) && !aw_done_q;
    assign axi_wdata_o   = wb_buf_q[axi_word_q];
    assign axi_wstrb_o   = 4'b1111;
    assign axi_wvalid_o  = (state_q == CS_WRITEBACK) && !w_done_q;
    assign axi_bready_o  = 1'b1;

    // =========================================================================
    // Write-hit byte merge: merge cached data with CPU write data
    // FreePDK45 SRAM has no byte write-mask; use pre-read data_dout_r + wstrb.
    // =========================================================================
    logic [31:0] merged_hit_word;
    assign merged_hit_word[7:0]   = dc_wstrb_q[0] ? dc_wdata_q[7:0]   : data_dout_r[latch_word][7:0];
    assign merged_hit_word[15:8]  = dc_wstrb_q[1] ? dc_wdata_q[15:8]  : data_dout_r[latch_word][15:8];
    assign merged_hit_word[23:16] = dc_wstrb_q[2] ? dc_wdata_q[23:16] : data_dout_r[latch_word][23:16];
    assign merged_hit_word[31:24] = dc_wstrb_q[3] ? dc_wdata_q[31:24] : data_dout_r[latch_word][31:24];

    // Write-miss byte merge: merge AXI refill data with CPU write data
    // Used when writing the miss word during CS_REFILL for a write-miss.
    // =========================================================================
    logic [31:0] merged_refill_word;
    assign merged_refill_word[7:0]   = dc_wstrb_q[0] ? dc_wdata_q[7:0]   : axi_rdata_i[7:0];
    assign merged_refill_word[15:8]  = dc_wstrb_q[1] ? dc_wdata_q[15:8]  : axi_rdata_i[15:8];
    assign merged_refill_word[23:16] = dc_wstrb_q[2] ? dc_wdata_q[23:16] : axi_rdata_i[23:16];
    assign merged_refill_word[31:24] = dc_wstrb_q[3] ? dc_wdata_q[31:24] : axi_rdata_i[31:24];

    // =========================================================================
    // SRAM combinational control — Tag SRAM
    // =========================================================================
    always_comb begin
        tag_csb0  = 1'b1;
        tag_web0  = 1'b1;
        tag_addr0 = 8'b0;
        tag_din0  = 32'b0;

        case (state_q)
            CS_IDLE: begin
                if (dc_valid_i) begin
                    tag_csb0  = 1'b0;
                    tag_web0  = 1'b1;   // read
                    tag_addr0 = addr_index;
                end
            end

            CS_TAG_CHECK: begin
                // Write hit: update tag (no tag change, but issue as write anyway
                // to keep csb=1 by default — actually tag doesn't change on write hit,
                // only dirty bit changes, so no tag SRAM write needed here)
                ;
            end

            CS_REFILL: begin
                // Write tag when last word arrives
                if (ar_pending_q && axi_rvalid_i && (axi_word_q == 2'd3)) begin
                    tag_csb0  = 1'b0;
                    tag_web0  = 1'b0;
                    tag_addr0 = latch_index;
                    tag_din0   = {12'b0, latch_tag};   // new tag in [19:0]
                end
            end

            default: ;
        endcase
    end

    // =========================================================================
    // SRAM combinational control — Data SRAMs
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
                // Read all 4 word SRAMs simultaneously
                if (dc_valid_i) begin
                    for (int w = 0; w < LINE_WORDS; w++) begin
                        data_csb0[w]  = 1'b0;
                        data_web0[w]  = 1'b1;   // read
                        data_addr0[w] = addr_index;
                    end
                end
            end

            CS_TAG_CHECK: begin
                // Write hit: byte-masked write to the specific word column
                if (hit && dc_we_q) begin
                    data_csb0[latch_word]  = 1'b0;
                    data_web0[latch_word]  = 1'b0;   // write (full merged word, no wmask)
                    data_addr0[latch_word] = latch_index;
                    data_din0[latch_word]  = merged_hit_word;
                end
            end

            CS_REFILL: begin
                // Write each arriving word to its SRAM column.
                // For write-miss: merge CPU write bytes into the miss word.
                if (ar_pending_q && axi_rvalid_i) begin
                    data_csb0[axi_word_q]  = 1'b0;
                    data_web0[axi_word_q]  = 1'b0;   // write
                    data_addr0[axi_word_q] = latch_index;
                    data_din0[axi_word_q]   = (is_write_q && (axi_word_q == latch_word))
                                              ? merged_refill_word
                                              : axi_rdata_i;
                end
            end

            default: ;
        endcase
    end

    // =========================================================================
    // FSM — sequential logic
    // =========================================================================
    always_ff @(posedge clk) begin
        if (!rst_n) begin
            state_q      <= CS_IDLE;
            dc_addr_q    <= '0;
            dc_we_q      <= 1'b0;
            dc_wdata_q   <= '0;
            dc_wstrb_q   <= '0;
            axi_word_q   <= 2'b00;
            ar_pending_q <= 1'b0;
            aw_done_q    <= 1'b0;
            w_done_q     <= 1'b0;
            wb_buf_q     <= '0;
            wb_tag_q     <= '0;
            wb_index_q   <= '0;
            refill_buf_q <= '0;
            is_write_q   <= 1'b0;
        end else begin
            case (state_q)
                // -----------------------------------------------------------------
                CS_IDLE: begin
                    if (dc_valid_i) begin
                        // Latch access parameters, issue SRAM read (combinationally above)
                        dc_addr_q  <= dc_addr_i;
                        dc_we_q    <= dc_we_i;
                        dc_wdata_q <= dc_wdata_i;
                        dc_wstrb_q <= dc_wstrb_i;
                        state_q    <= CS_SRAM_LATCH;
                    end
                end

                // -----------------------------------------------------------------
                CS_SRAM_LATCH: begin
                    // tag_dout_r / data_dout_r captured in always_ff above.
                    // No FENCE.I in D-cache; unconditional transition.
                    state_q <= CS_TAG_CHECK;
                end

                // -----------------------------------------------------------------
                CS_TAG_CHECK: begin
                    if (hit) begin
                        // Hit: read data available from SRAM dout.
                        // Write hit: SRAM byte-masked write issued combinationally.
                        // Dirty bit update handled in valid/dirty always_ff below.
                        state_q <= CS_IDLE;
                    end else begin
                        // Miss
                        axi_word_q   <= 2'b00;
                        ar_pending_q <= 1'b0;
                        aw_done_q    <= 1'b0;
                        w_done_q     <= 1'b0;
                        is_write_q   <= dc_we_q;

                        if (need_writeback) begin
                            // Capture all 4 words of the dirty line from SRAM dout
                            // (all 4 data SRAMs were read simultaneously in CS_IDLE)
                            wb_buf_q[0] <= data_dout_r[0];
                            wb_buf_q[1] <= data_dout_r[1];
                            wb_buf_q[2] <= data_dout_r[2];
                            wb_buf_q[3] <= data_dout_r[3];
                            wb_tag_q    <= tag_dout_r[TAG_BITS-1:0];
                            wb_index_q  <= latch_index;
                            state_q     <= CS_WRITEBACK;
                        end else begin
                            state_q <= CS_REFILL;
                        end
                    end
                end

                // -----------------------------------------------------------------
                CS_WRITEBACK: begin
                    // AW channel
                    if (!aw_done_q && axi_awready_i)
                        aw_done_q <= 1'b1;
                    // W channel
                    if (!w_done_q && axi_wready_i)
                        w_done_q <= 1'b1;
                    // B channel: advance word counter only on OKAY response
                    if (axi_bvalid_i && (axi_bresp_i == 2'b00)) begin
                        aw_done_q <= 1'b0;
                        w_done_q  <= 1'b0;
                        if (axi_word_q == 2'd3) begin
                            state_q    <= CS_REFILL;
                            axi_word_q <= 2'b00;
                        end else begin
                            axi_word_q <= axi_word_q + 1'b1;
                        end
                    end else if (axi_bvalid_i && (axi_bresp_i != 2'b00)) begin
                        // AXI error: abort writeback, return to IDLE
                        state_q    <= CS_IDLE;
                        aw_done_q  <= 1'b0;
                        w_done_q   <= 1'b0;
                        axi_word_q <= 2'b00;
                    end
                end

                // -----------------------------------------------------------------
                CS_REFILL: begin
                    if (!ar_pending_q) begin
                        if (axi_arready_i)
                            ar_pending_q <= 1'b1;
                    end else begin
                        if (axi_rvalid_i && (axi_rresp_i == 2'b00)) begin
                            refill_buf_q[axi_word_q] <= (is_write_q && (axi_word_q == latch_word))
                                                        ? merged_refill_word
                                                        : axi_rdata_i;
                            ar_pending_q <= 1'b0;
                            if (axi_word_q == 2'd3) begin
                                state_q <= CS_DONE;
                            end else begin
                                axi_word_q <= axi_word_q + 1'b1;
                            end
                        end else if (axi_rvalid_i && (axi_rresp_i != 2'b00)) begin
                            // AXI error: discard bad data, return to IDLE
                            state_q      <= CS_IDLE;
                            ar_pending_q <= 1'b0;
                            axi_word_q   <= 2'b00;
                        end
                    end
                end

                // -----------------------------------------------------------------
                CS_DONE: begin
                    // dc_rdata_o = refill_buf_q[latch_word] (combinational above)
                    // stall=0, pipeline advances
                    state_q <= CS_IDLE;
                end

                default: state_q <= CS_IDLE;
            endcase
        end
    end

    // =========================================================================
    // Valid and dirty arrays — sequential
    // =========================================================================
    always_ff @(posedge clk) begin
        if (!rst_n) begin
            for (int j = 0; j < N_SETS; j++) begin
                valid_array[j] = 1'b0;
                dirty_array[j] = 1'b0;
            end
        end else begin
            // Write hit: set dirty
            if (state_q == CS_TAG_CHECK && hit && dc_we_q)
                dirty_array[latch_index] <= 1'b1;

            // Writeback complete: invalidate the evicted line
            if (state_q == CS_WRITEBACK && axi_bvalid_i && (axi_word_q == 2'd3)) begin
                dirty_array[wb_index_q] <= 1'b0;
                valid_array[wb_index_q] <= 1'b0;
            end

            // Refill complete: mark line valid, clear dirty (or set dirty for write-miss)
            if (state_q == CS_REFILL && ar_pending_q && axi_rvalid_i && (axi_word_q == 2'd3)) begin
                valid_array[latch_index] <= 1'b1;
                dirty_array[latch_index] <= is_write_q;
            end
        end
    end

    // Suppress unused warnings
    /* verilator lint_off UNUSEDSIGNAL */
    // axi_rresp_i and axi_bresp_i are now used in FSM RESP checks above.
    /* verilator lint_on UNUSEDSIGNAL */

endmodule
