// rv32i_dcache.sv
// Phase 3 — Data Cache (D$)
//
// Configuration: 4 KB, direct-mapped, 16-byte lines, write-back + write-allocate
//
// CPU-side interface (from MEM stage):
//   - Present dc_addr_i + dc_valid_i each cycle
//   - Read hit: dc_rdata_o valid same cycle, dc_stall_o=0
//   - Write hit: update word in-place + set dirty bit, dc_stall_o=0
//   - Miss: dc_stall_o=1; FSM performs writeback (if dirty) then refill
//
// Memory-side interface (to cache arbiter):
//   - AXI4-Lite read (AR+R) for cache line refill
//   - AXI4-Lite write (AW+W+B) for dirty line writeback
//
// Write-allocate policy:
//   - Write miss → refill line first → write to cached line
//   - Dirty eviction → writeback old line first → refill new line


import rv32i_cache_pkg::*;
module rv32i_dcache(
    input  logic        clk,
    input  logic        rst_n,

    // ── CPU-side interface (from MEM stage) ───────────────────────────────────
    input  logic [31:0] dc_addr_i,        // Memory address
    input  logic        dc_valid_i,       // Memory access valid
    input  logic        dc_we_i,          // Write enable (1=store, 0=load)
    input  logic [31:0] dc_wdata_i,       // Write data (aligned by MEM stage)
    input  logic [3:0]  dc_wstrb_i,       // Write byte strobes
    output logic [31:0] dc_rdata_o,       // Read data (valid when !dc_stall_o)
    output logic        dc_stall_o,       // 1 = miss/busy — stall pipeline

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
    // Cache arrays (behavioral SRAM model)
    // =========================================================================
    logic [TAG_BITS-1:0]            tag_array  [0:N_SETS-1];
    logic [LINE_WORDS-1:0][31:0]    data_array [0:N_SETS-1];
    logic                           valid_array[0:N_SETS-1];
    logic                           dirty_array[0:N_SETS-1];

    // =========================================================================
    // Address field extraction
    // =========================================================================
    logic [TAG_BITS-1:0]   addr_tag;
    logic [INDEX_BITS-1:0] addr_index;
    logic [1:0]            addr_word;   // Word offset within line [3:2]

    assign addr_tag   = dc_addr_i[31:12];
    assign addr_index = dc_addr_i[11:4];
    assign addr_word  = dc_addr_i[3:2];

    // =========================================================================
    // Hit detection (combinational)
    // =========================================================================
    logic hit;
    assign hit = valid_array[addr_index] && (tag_array[addr_index] == addr_tag);

    // =========================================================================
    // FSM state and control registers
    // =========================================================================
    cache_state_t        state_q;
    logic [31:0]         miss_addr_q;       // Address that caused the miss
    logic [1:0]          axi_word_q;        // Word counter for refill/writeback
    logic                ar_pending_q;      // AR issued, waiting for R
    logic                aw_done_q;         // AW handshake complete
    logic                w_done_q;          // W handshake complete
    logic                is_write_q;        // Was the missed access a write?

    // Writeback: which line to evict
    logic [INDEX_BITS-1:0] wb_index_q;     // Index of line being written back
    logic [TAG_BITS-1:0]   wb_tag_q;       // Tag of line being written back

    // Refill buffer
    logic [LINE_WORDS-1:0][31:0] refill_buf_q;

    // =========================================================================
    // Refill address: base of the new line (aligned to 16 bytes)
    // =========================================================================
    logic [31:0] refill_base;
    assign refill_base = {miss_addr_q[31:4], 4'b0000};

    // Writeback base address: reconstruct from evicted tag + index
    logic [31:0] wb_addr_base;
    assign wb_addr_base = {wb_tag_q, wb_index_q, 4'b0000};

    // =========================================================================
    // AXI control
    // =========================================================================
    // Refill (read)
    assign axi_araddr_o  = {refill_base[31:4], axi_word_q, 2'b00};
    assign axi_arvalid_o = (state_q == CS_REFILL) && !ar_pending_q;
    assign axi_rready_o  = 1'b1;

    // Writeback (write)
    assign axi_awaddr_o  = {wb_addr_base[31:4], axi_word_q, 2'b00};
    assign axi_awvalid_o = (state_q == CS_WRITEBACK) && !aw_done_q;
    assign axi_wdata_o   = data_array[wb_index_q][axi_word_q];
    assign axi_wstrb_o   = 4'b1111; // Full-word writeback
    assign axi_wvalid_o  = (state_q == CS_WRITEBACK) && !w_done_q;
    assign axi_bready_o  = 1'b1;

    // =========================================================================
    // Stall output
    // =========================================================================
    // Stall on: valid access AND (in non-idle state) OR (idle but miss)
    assign dc_stall_o = dc_valid_i && ((state_q != CS_IDLE) || !hit);

    // =========================================================================
    // Read data output (combinational from cache arrays)
    // =========================================================================
    assign dc_rdata_o = data_array[addr_index][addr_word];

    // =========================================================================
    // FSM — sequential logic
    // =========================================================================
    // Need to track whether eviction is needed (dirty line at victim index)
    logic need_writeback;
    assign need_writeback = valid_array[addr_index] && dirty_array[addr_index]
                         && (tag_array[addr_index] != addr_tag);

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state_q    <= CS_IDLE;
            miss_addr_q <= '0;
            axi_word_q  <= 2'b00;
            ar_pending_q <= 1'b0;
            aw_done_q   <= 1'b0;
            w_done_q    <= 1'b0;
            wb_index_q  <= '0;
            wb_tag_q    <= '0;
            is_write_q  <= 1'b0;
            refill_buf_q <= '0;
        end else begin
            case (state_q)
                // -----------------------------------------------------------------
                CS_IDLE: begin
                    if (dc_valid_i && !hit) begin
                        // Miss: decide whether to writeback first
                        miss_addr_q  <= dc_addr_i;
                        is_write_q   <= dc_we_i;
                        axi_word_q   <= 2'b00;
                        ar_pending_q <= 1'b0;
                        aw_done_q    <= 1'b0;
                        w_done_q     <= 1'b0;
                        if (need_writeback) begin
                            // Dirty line at victim index — write it back first
                            wb_index_q <= addr_index;
                            wb_tag_q   <= tag_array[addr_index];
                            state_q    <= CS_WRITEBACK;
                        end else begin
                            state_q <= CS_REFILL;
                        end
                    end
                end

                // -----------------------------------------------------------------
                CS_WRITEBACK: begin
                    // AW channel
                    if (!aw_done_q && axi_awready_i) begin
                        aw_done_q <= 1'b1;
                    end
                    // W channel
                    if (!w_done_q && axi_wready_i) begin
                        w_done_q <= 1'b1;
                    end
                    // B channel (response)
                    if (axi_bvalid_i && axi_bready_o) begin
                        if (axi_word_q == 2'd3) begin
                            // All 4 words written back
                            state_q   <= CS_REFILL;
                            axi_word_q <= 2'b00;
                        end else begin
                            axi_word_q <= axi_word_q + 1'b1;
                        end
                        aw_done_q <= 1'b0;
                        w_done_q  <= 1'b0;
                    end
                end

                // -----------------------------------------------------------------
                CS_REFILL: begin
                    // AR channel: issue and wait for acceptance
                    if (!ar_pending_q) begin
                        if (axi_arready_i) begin
                            ar_pending_q <= 1'b1;
                        end
                    end else begin
                        // Waiting for R
                        if (axi_rvalid_i) begin
                            refill_buf_q[axi_word_q] <= axi_rdata_i;
                            ar_pending_q <= 1'b0;
                            if (axi_word_q == 2'd3) begin
                                state_q <= CS_IDLE; // Refill done
                            end else begin
                                axi_word_q <= axi_word_q + 1'b1;
                            end
                        end
                    end
                end

                default: state_q <= CS_IDLE;
            endcase
        end
    end

    // =========================================================================
    // Cache array write logic
    // =========================================================================
    // Convenience: refill last word arriving
    logic refill_done;
    assign refill_done = (state_q == CS_REFILL) && ar_pending_q
                       && axi_rvalid_i && (axi_word_q == 2'd3);

    // Byte-merge logic for write-hit
    // Select bytes from wdata where wstrb=1, else keep cached value
    logic [31:0] merged_wdata;
    assign merged_wdata[7:0]   = dc_wstrb_i[0] ? dc_wdata_i[7:0]   : data_array[addr_index][addr_word][7:0];
    assign merged_wdata[15:8]  = dc_wstrb_i[1] ? dc_wdata_i[15:8]  : data_array[addr_index][addr_word][15:8];
    assign merged_wdata[23:16] = dc_wstrb_i[2] ? dc_wdata_i[23:16] : data_array[addr_index][addr_word][23:16];
    assign merged_wdata[31:24] = dc_wstrb_i[3] ? dc_wdata_i[31:24] : data_array[addr_index][addr_word][31:24];

    // After refill: merge for a write-miss (write-allocate)
    logic [LINE_WORDS-1:0][31:0] refill_with_write;
    logic [TAG_BITS-1:0]         miss_tag;
    logic [INDEX_BITS-1:0]       miss_index;
    logic [1:0]                  miss_word;

    assign miss_tag   = miss_addr_q[31:12];
    assign miss_index = miss_addr_q[11:4];
    assign miss_word  = miss_addr_q[3:2];

    always_comb begin
        refill_with_write = '0;
        for (int w = 0; w < LINE_WORDS; w++) begin
            if (w == int'(miss_word) && is_write_q) begin
                // Apply byte strobe mask to the written word
                refill_with_write[w][7:0]   = dc_wstrb_i[0] ? dc_wdata_i[7:0]   : (w == 3 ? axi_rdata_i[7:0]   : refill_buf_q[w][7:0]);
                refill_with_write[w][15:8]  = dc_wstrb_i[1] ? dc_wdata_i[15:8]  : (w == 3 ? axi_rdata_i[15:8]  : refill_buf_q[w][15:8]);
                refill_with_write[w][23:16] = dc_wstrb_i[2] ? dc_wdata_i[23:16] : (w == 3 ? axi_rdata_i[23:16] : refill_buf_q[w][23:16]);
                refill_with_write[w][31:24] = dc_wstrb_i[3] ? dc_wdata_i[31:24] : (w == 3 ? axi_rdata_i[31:24] : refill_buf_q[w][31:24]);
            end else if (w == 3) begin
                refill_with_write[w] = axi_rdata_i; // Last word from AXI
            end else begin
                refill_with_write[w] = refill_buf_q[w];
            end
        end
    end

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            for (int j = 0; j < N_SETS; j++) begin
                valid_array[j] = 1'b0;
                dirty_array[j] = 1'b0;
            end
        end else if (refill_done) begin
            // Commit refilled line to cache
            // For write-miss (write-allocate): the written word is merged into the line
            tag_array  [miss_index] <= miss_tag;
            valid_array[miss_index] <= 1'b1;
            dirty_array[miss_index] <= is_write_q; // Dirty if this was a write-miss
            data_array [miss_index] <= refill_with_write;
        end else if (dc_valid_i && hit && dc_we_i && (state_q == CS_IDLE)) begin
            // Write hit: update word in-place (byte-strobe merge), set dirty
            data_array [addr_index][addr_word] <= merged_wdata;
            dirty_array[addr_index]            <= 1'b1;
        end else if (state_q == CS_WRITEBACK && axi_bvalid_i && axi_bready_o
                  && axi_word_q == 2'd3) begin
            // Writeback complete: clear dirty bit (line remains valid with old tag until refill)
            dirty_array[wb_index_q] <= 1'b0;
            valid_array[wb_index_q] <= 1'b0; // Invalidate until refill completes
        end
    end

    // Suppress unused warnings
    /* verilator lint_off UNUSEDSIGNAL */
    logic _unused_rresp  = |axi_rresp_i;
    logic _unused_bresp  = |axi_bresp_i;
    /* verilator lint_on UNUSEDSIGNAL */

endmodule
