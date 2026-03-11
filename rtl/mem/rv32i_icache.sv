// rv32i_icache.sv
// Phase 3 — Instruction Cache (I$)
//
// Configuration: 4 KB, direct-mapped, 16-byte lines, write-through (read-only)
//
// CPU-side interface (from IF stage):
//   - Present ic_addr_i + ic_valid_i each cycle
//   - Cache returns ic_rdata_o same cycle on hit (ic_stall_o=0)
//   - On miss: ic_stall_o=1 while REFILL FSM fetches 4 words from AXI4-Lite
//
// Memory-side interface (to cache arbiter):
//   - AXI4-Lite read-only (AR + R channels only)
//   - 4 single-word AXI transactions per cache-line refill
//
// FENCE.I support:
//   - Assert ic_invalidate_i for 1 cycle to clear all valid bits
//   - Next access to any address will miss and refill from memory

import rv32i_cache_pkg::*;

module rv32i_icache (
    input  logic        clk,
    input  logic        rst_n,

    // ── CPU-side interface (from IF stage) ────────────────────────────────────
    input  logic [31:0] ic_addr_i,        // Fetch address
    input  logic        ic_valid_i,       // Fetch request valid
    output logic [31:0] ic_rdata_o,       // Instruction word (valid when !ic_stall_o)
    output logic        ic_stall_o,       // 1 = miss/busy — stall the pipeline

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
    // Cache arrays (behavioral SRAM model — synthesized as SRAM macros)
    // =========================================================================
    logic [TAG_BITS-1:0]            tag_array  [0:N_SETS-1];
    logic [LINE_WORDS-1:0][31:0]    data_array [0:N_SETS-1];
    logic                           valid_array[0:N_SETS-1];

    // =========================================================================
    // Address field extraction
    // =========================================================================
    logic [TAG_BITS-1:0]   addr_tag;
    logic [INDEX_BITS-1:0] addr_index;
    logic [1:0]            addr_word;   // Which word within the line [3:2]

    assign addr_tag   = ic_addr_i[31:12];
    assign addr_index = ic_addr_i[11:4];
    assign addr_word  = ic_addr_i[3:2];

    // =========================================================================
    // Hit detection (combinational — 1 cycle)
    // =========================================================================
    logic hit;
    assign hit = valid_array[addr_index] && (tag_array[addr_index] == addr_tag);

    // =========================================================================
    // FSM state and refill registers
    // =========================================================================
    cache_state_t        state_q;
    logic [31:0]         refill_line_addr_q; // Base address of line being refilled (16-byte aligned)
    logic [1:0]          refill_word_q;      // Current word in refill sequence (0-3)
    logic                ar_pending_q;       // AR accepted, waiting for R response

    // Refill word buffer (accumulates the 4 words before committing to cache)
    logic [LINE_WORDS-1:0][31:0] refill_buf_q;

    // =========================================================================
    // AXI control (read address channel)
    // =========================================================================
    // AR address: base of refill line + current word offset
    assign axi_araddr_o  = {refill_line_addr_q[31:4], refill_word_q, 2'b00};
    // Issue AR when in REFILL and not waiting for R response
    assign axi_arvalid_o = (state_q == CS_REFILL) && !ar_pending_q;
    // Always accept R responses
    assign axi_rready_o  = 1'b1;

    // Convenience: last word of refill just arrived
    logic refill_last_word;
    assign refill_last_word = ar_pending_q && axi_rvalid_i && (refill_word_q == 2'd3);

    // =========================================================================
    // Stall output
    // Stall when: valid request AND (miss detected OR refill in progress)
    // =========================================================================
    assign ic_stall_o = ic_valid_i && ((state_q != CS_IDLE) || !hit);

    // =========================================================================
    // Data output (combinational from cache arrays)
    // =========================================================================
    assign ic_rdata_o = data_array[addr_index][addr_word];

    // =========================================================================
    // FSM — sequential logic
    // =========================================================================
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state_q           <= CS_IDLE;
            refill_line_addr_q <= '0;
            refill_word_q     <= 2'b00;
            ar_pending_q      <= 1'b0;
            refill_buf_q      <= '0;
        end else begin
            case (state_q)
                // -----------------------------------------------------------------
                CS_IDLE: begin
                    // Start refill on miss (and not currently invalidating)
                    if (ic_valid_i && !hit && !ic_invalidate_i) begin
                        state_q            <= CS_REFILL;
                        refill_line_addr_q <= {ic_addr_i[31:4], 4'b0000}; // align to 16
                        refill_word_q      <= 2'b00;
                        ar_pending_q       <= 1'b0;
                    end
                end
                // -----------------------------------------------------------------
                CS_REFILL: begin
                    // Issue AR for current word
                    if (!ar_pending_q) begin
                        if (axi_arready_i) begin
                            ar_pending_q <= 1'b1; // AR accepted
                        end
                    end else begin
                        // Waiting for R response
                        if (axi_rvalid_i) begin
                            refill_buf_q[refill_word_q] <= axi_rdata_i;
                            ar_pending_q <= 1'b0;
                            if (refill_word_q == 2'd3) begin
                                // All 4 words received — commit to cache and return to IDLE
                                state_q <= CS_IDLE;
                            end else begin
                                refill_word_q <= refill_word_q + 1'b1;
                            end
                        end
                    end
                end
                // -----------------------------------------------------------------
                default: state_q <= CS_IDLE;
            endcase
        end
    end

    // =========================================================================
    // Cache array writes (synchronous)
    // Priority: reset/invalidate > refill commit
    // =========================================================================
    always_ff @(posedge clk) begin
        if (!rst_n || ic_invalidate_i) begin
            // Reset or FENCE.I: invalidate all lines
            for (int j = 0; j < N_SETS; j++) begin
                valid_array[j] <= 1'b0;
            end
        end else if (refill_last_word) begin
            // Refill complete: commit line to cache
            // (refill_last_word fires when the 4th word arrives)
            tag_array  [refill_line_addr_q[11:4]] <= refill_line_addr_q[31:12];
            valid_array[refill_line_addr_q[11:4]] <= 1'b1;
            // Words 0-2 are already in refill_buf_q; word 3 just arrived
            data_array [refill_line_addr_q[11:4]][0] <= refill_buf_q[0];
            data_array [refill_line_addr_q[11:4]][1] <= refill_buf_q[1];
            data_array [refill_line_addr_q[11:4]][2] <= refill_buf_q[2];
            data_array [refill_line_addr_q[11:4]][3] <= axi_rdata_i; // last word
        end
    end

    // Suppress unused signal warning for AXI rresp (not checked; simplified model)
    /* verilator lint_off UNUSEDSIGNAL */
    logic _unused_rresp = |axi_rresp_i;
    /* verilator lint_on UNUSEDSIGNAL */

endmodule
