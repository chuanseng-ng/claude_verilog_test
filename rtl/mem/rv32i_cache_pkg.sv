// rv32i_cache_pkg.sv
// Phase 3 Cache System Package
//
// Defines shared parameters and types for I-cache and D-cache.
//
// Cache configuration (from MEMORY_MAP.md):
//   - Size:         4 KB each (I$ and D$)
//   - Organization: Direct-mapped
//   - Line size:    16 bytes (4 words)
//   - Sets:         256
//   - Address:      tag[31:12] | index[11:4] | byte_offset[3:0]

package rv32i_cache_pkg;

    // =========================================================================
    // Cache geometry
    // =========================================================================
    localparam int CACHE_SIZE_BYTES = 4096;              // 4 KB
    localparam int LINE_SIZE_BYTES  = 16;                // 16 bytes per line
    localparam int LINE_WORDS       = LINE_SIZE_BYTES / 4; // 4 words per line
    localparam int N_SETS           = CACHE_SIZE_BYTES / LINE_SIZE_BYTES; // 256

    // Address field widths
    localparam int OFFSET_BITS = $clog2(LINE_SIZE_BYTES); // 4 bits [3:0]
    localparam int INDEX_BITS  = $clog2(N_SETS);          // 8 bits [11:4]
    localparam int TAG_BITS    = 32 - INDEX_BITS - OFFSET_BITS; // 20 bits [31:12]

    // AXI4-Lite refill: one transaction per word, N_BEATS per line
    localparam int REFILL_BEATS = LINE_WORDS; // 4 AXI transactions per miss

    // =========================================================================
    // Cache FSM state encoding
    // Extended to 3 bits to accommodate synchronous-SRAM pipeline stages.
    // CS_HIT_PENDING added (Run 15 timing fix): one extra register stage between
    // CS_SRAM_LATCH and CS_TAG_CHECK so hit_comb is registered before it fans
    // out to the data SRAM mux network (~821 loads → registered hit_q/hit_bank_q).
    // =========================================================================
    typedef enum logic [3:0] {
        CS_IDLE          = 4'b0000,  // Idle: issue SRAM read on new request
        CS_SRAM_LATCH    = 4'b0101,  // Latch: capture negedge SRAM dout into pipeline regs
        CS_HIT_PENDING   = 4'b0110,  // Hit pipeline: register hit_comb before fanout
        CS_TAG_CHECK     = 4'b0001,  // Tag check: hit_q valid, act on hit or miss
        CS_REFILL        = 4'b0010,  // Refill: fetch words from AXI and write to SRAM
        CS_WRITEBACK     = 4'b0011,  // Writeback: flush dirty line to AXI (D$ only)
        CS_DONE          = 4'b0100,  // Done: output data from refill buffer, release stall
        // ── Phase 5 uncached MMIO bypass states (D$ only) ─────────────────────
        CS_UNCACHED_RD   = 4'b0111,  // Uncached read: single-beat AR → R, bypass cache
        CS_UNCACHED_WR   = 4'b1000,  // Uncached write: single-beat AW/W → B, bypass cache
        // ── Phase 5 D-cache maintenance states (D$ only) ──────────────────────
        CS_FLUSH_SCAN    = 4'b1001,  // Flush-all: walk 256 lines, write back dirty ones
        CS_INVAL_SCAN    = 4'b1010   // Inval-all: walk 256 lines, clear valid+dirty bits
    } cache_state_t;

    // =========================================================================
    // D-cache maintenance CSR addresses (Phase 5)
    // Keep in sync with rv32i_csr_file.sv and rv32i_pipeline_id.sv.
    // =========================================================================
    localparam logic [11:0] DCACHE_FLUSH_CSR = 12'h7C0; // write-only, triggers flush-all
    localparam logic [11:0] DCACHE_INVAL_CSR = 12'h7C1; // write-only, triggers inval-all

endpackage
