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
    // =========================================================================
    typedef enum logic [1:0] {
        CS_IDLE      = 2'b00,  // Idle: check hit/miss each cycle
        CS_REFILL    = 2'b01,  // Refill: fetch words from AXI (both caches)
        CS_WRITEBACK = 2'b10,  // Writeback: flush dirty line to AXI (D$ only)
        CS_RESERVED  = 2'b11   // Unused
    } cache_state_t;

endpackage
