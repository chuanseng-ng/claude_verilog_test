// rv32i_dcache.sv
// Phase 3 — Data Cache (D$)
//
// Configuration (parameterised by DCACHE_WAYS from rv32i_cache_pkg):
//
//   DCACHE_WAYS = 1 (default, direct-mapped):
//     4 KB, 256 sets × 1 way × 16 B, write-back + write-allocate.
//     Behaviour is BIT-IDENTICAL to the pre-M10b baseline.  All existing
//     tests/regression/synthesis/PD flows are unaffected.
//
//   DCACHE_WAYS = 2 (Phase 5 M10b experiment):
//     4 KB, 128 sets × 2 ways × 16 B, write-back + write-allocate.
//     Same total capacity; conflict-miss component is the experiment target.
//     Replacement: per-set 1-bit true-LRU (lru_array[set] = MRU way index,
//     i.e. the way accessed last).  On miss: fill an invalid way first (any
//     way); else evict the LRU way (lru_array[set] XOR 1).
//     LRU updated on every access (hit and fill).
//
// Address decomposition:
//   WAYS=1: tag[31:12] | index[11:4] | offset[3:0]  — 20 | 8 | 4 bits
//   WAYS=2: tag[31:11] | index[10:4] | offset[3:0]  — 21 | 7 | 4 bits
//
// ── SRAM macros (selected at compile time via `SRAM_SKY130 define) ──────────
//   Default (FreePDK45):
//     Per way: 1× sram_1rw_256x32_freepdk45 (tag),
//              4× sram_1rw_256x32_freepdk45 (data, one per word column)
//     WAYS=2 instantiates 2× the above set.  The SRAM depth is always 256
//     rows; for WAYS=2 only 128 rows are used (index is 7 bits).
//   `ifdef SRAM_SKY130 (Sky130):
//     sky130_sram_1kbyte_1rw1r_32x256_8 per way (same depth/width).
//
// ── Valid, dirty, and LRU bits ───────────────────────────────────────────────
//   valid_array[way][set], dirty_array[way][set]: register arrays
//     (in-cycle access, bulk reset, 1-cycle maintenance scan).
//   lru_array[set] (WAYS=2 only): 1-bit register, = index of MRU way.
//     lru_array[set]==0 → way 0 is MRU → evict way 1 on miss.
//     lru_array[set]==1 → way 1 is MRU → evict way 0 on miss.
//     Updated on hit (set to hit_way) and on fill (set to filled_way).
//     For WAYS=1 lru_array is not instantiated (zero width, no logic).
//
// ── Timing model — SRAM has 1-cycle read latency (6/7-state FSM) ────────────
//   CS_IDLE       : dc_valid_i → issue SRAM read (all ways, all 5 SRAMs), stall=1
//   CS_SRAM_LATCH : SRAM read in flight; capture dout into tag_dout_r/data_dout_r
//   CS_HIT_PENDING: tag compare (WAYS=1: hit_comb; WAYS=2: hit_comb[way]);
//                   register results into hit_q / hit_way_q
//   CS_TAG_CHECK  : hit_q valid
//                   read  hit → stall=0, dc_rdata_o from data_dout_r[hit_way_q][latch_word]
//                   write hit → SRAM byte-masked write via hit_bank_q / hit_way_q, stall=0
//                   miss → CS_WRITEBACK (dirty victim) or CS_REFILL (clean/invalid victim)
//   CS_WRITEBACK  : send wb_buf_q[0..3] to AXI burst, → CS_REFILL
//   CS_REFILL     : fetch 4 words from AXI, write to SRAM (write-allocate), → CS_DONE
//   CS_DONE       : dc_rdata_o from refill_buf_q[latch_word], stall=0, → CS_IDLE
//
// ── Hit-path critical path note (Phase 5 M10b) ──────────────────────────────
//   WAYS=2 adds a 2:1 mux on the hit-data output (select word from the
//   winning way's data_dout_r array).  The selector (hit_way_q, registered
//   in CS_HIT_PENDING) adds one MUX level after the existing data_dout_r[][]
//   fanout.  The ASAP7 critical path was previously the tag-comparator fanout
//   (fixed by hit_bank_q duplication).  For WAYS=2 the new critical path is
//   expected to be: tag_dout_r[w][TAG_BITS_D-1:0] → comparator → hit_comb[w]
//   → register hit_q/hit_way_q (CS_HIT_PENDING) → data mux select (CS_TAG_CHECK).
//   This adds ~1 MUX level vs. the WAYS=1 path.  Timing closure at ASAP7
//   (~571 MHz SoC governed) is anticipated but not yet characterized; flag for
//   PD agent when this experiment proceeds to synthesis.

`default_nettype none

import rv32i_cache_pkg::*;
import axi_pkg::*;
import soc_addr_map_pkg::MMIO_BASE;

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
    output logic        dc_miss_o,    // 1-cycle pulse: CS_TAG_CHECK miss → CS_REFILL/CS_WRITEBACK

    // ── D-cache maintenance triggers (Phase 5) — from rv32i_csr_file ─────────
    input  logic        dc_flush_i,       // 1-cycle pulse: flush-all dirty lines to AXI
    input  logic        dc_inval_i,       // 1-cycle pulse: invalidate all lines
    output logic        dc_maint_done_o,  // 1-cycle pulse: maintenance operation complete

    // ── AXI4 read channel (refill) ───────────────────────────────────────────
    output logic [31:0]                axi_araddr_o,
    output logic [AXI_LEN_WIDTH-1:0]  axi_arlen_o,
    output logic [AXI_SIZE_WIDTH-1:0] axi_arsize_o,
    output logic [1:0]                axi_arburst_o,
    output logic                      axi_arvalid_o,
    input  logic                      axi_arready_i,

    input  logic [31:0] axi_rdata_i,
    input  logic [1:0]  axi_rresp_i,
    input  logic        axi_rvalid_i,
    input  logic        axi_rlast_i,
    output logic        axi_rready_o,

    // ── AXI4 write channel (writeback) ───────────────────────────────────────
    output logic [31:0]                axi_awaddr_o,
    output logic [AXI_LEN_WIDTH-1:0]  axi_awlen_o,
    output logic [AXI_SIZE_WIDTH-1:0] axi_awsize_o,
    output logic [1:0]                axi_awburst_o,
    output logic                      axi_awvalid_o,
    input  logic                      axi_awready_i,

    output logic [31:0] axi_wdata_o,
    output logic [3:0]  axi_wstrb_o,
    output logic        axi_wlast_o,
    output logic        axi_wvalid_o,
    input  logic        axi_wready_i,

    input  logic        axi_bvalid_i,
    input  logic [1:0]  axi_bresp_i,
    output logic        axi_bready_o
);

    // =========================================================================
    // Local geometry — derived from package parameters
    // =========================================================================
    // N_SETS_D  : number of sets  (256 for WAYS=1, 128 for WAYS=2)
    // INDEX_BITS_D : index width  (  8 for WAYS=1,   7 for WAYS=2)
    // TAG_BITS_D   : tag width    ( 20 for WAYS=1,  21 for WAYS=2)
    // These are localparams so Verilator sees them as elaboration-time constants.
    localparam int WAYS_L        = DCACHE_WAYS;   // local alias for brevity
    localparam int N_SETS_L      = N_SETS_D;
    localparam int INDEX_BITS_L  = INDEX_BITS_D;
    localparam int TAG_BITS_L    = TAG_BITS_D;

    // Terminal values for maintenance scan loops — explicit width to avoid
    // WIDTHEXPAND warnings when compared with INDEX_BITS_L-bit or 1-bit signals.
    // LAST_SET : index of the last set (N_SETS_L-1), INDEX_BITS_L bits wide.
    // LAST_WAY : index of the last way (WAYS_L-1),   1 bit wide.
    localparam logic [7:0]  LAST_SET_8 = 8'(N_SETS_L - 1);  // fits in 8b (128 or 256)
    localparam logic        LAST_WAY   = (WAYS_L > 1) ? 1'b1 : 1'b0;

    // =========================================================================
    // Valid, dirty, and LRU bit arrays
    // =========================================================================
    // valid_array[way][set] and dirty_array[way][set]:
    //   Indexed [way][set] so the scan loops below are clean.
    //   For WAYS=1 the outer dimension is [0:0] — same bit, same access pattern.
    logic valid_array [0:WAYS_L-1][0:N_SETS_L-1];
    logic dirty_array [0:WAYS_L-1][0:N_SETS_L-1];

    // lru_array[set]: 1-bit MRU-way pointer (only meaningful for WAYS=2).
    //   lru_array[s] = w means way w was accessed most recently in set s.
    //   Eviction target = lru_array[s] ^ 1'b1  (the other way).
    //   For WAYS=1: declared as [0:0][0:0] (1 bit, never written) — Verilator
    //   sees it as a 1-element array; the code never reads it when WAYS_L==1.
    logic lru_array [0:N_SETS_L-1];

    // =========================================================================
    // Tag SRAM instances — one per way
    // Each SRAM is 256 deep × 32 wide regardless of WAYS (depth rows are used:
    // 256 for WAYS=1, 128 for WAYS=2; upper rows simply stay unaccessed).
    // =========================================================================
    logic        tag_csb0  [0:WAYS_L-1];
    logic        tag_web0  [0:WAYS_L-1];
    logic [7:0]  tag_addr0 [0:WAYS_L-1];
    logic [31:0] tag_din0  [0:WAYS_L-1];
    logic [31:0] tag_dout0 [0:WAYS_L-1];

    genvar gway;
    generate
        for (gway = 0; gway < WAYS_L; gway++) begin : gen_tag_sram
`ifdef SRAM_SKY130
            sky130_sram_1kbyte_1rw1r_32x256_8 u_tag_sram (
                .clk0   (clk),
                .csb0   (tag_csb0[gway]),
                .web0   (tag_web0[gway]),
                .wmask0 (4'b1111),
                .addr0  (tag_addr0[gway]),
                .din0   (tag_din0[gway]),
                .dout0  (tag_dout0[gway]),
                .clk1   (clk),
                .csb1   (1'b1),
                .addr1  (8'b0),
                .dout1  ()
            );
`elsif SRAM_ASAP7
            logic tag_gclk;
            rv32i_clock_gate u_tag_cg (
                .en  (!tag_csb0[gway]),
                .clk (clk),
                .gclk(tag_gclk)
            );
            sram_1rw_256x32_asap7 u_tag_sram (
                .clk0   (tag_gclk),
                .csb0   (tag_csb0[gway]),
                .web0   (tag_web0[gway]),
                .addr0  (tag_addr0[gway]),
                .din0   (tag_din0[gway]),
                .dout0  (tag_dout0[gway])
            );
`else
            sram_1rw_256x32_freepdk45 u_tag_sram (
                .clk0   (clk),
                .csb0   (tag_csb0[gway]),
                .web0   (tag_web0[gway]),
                .addr0  (tag_addr0[gway]),
                .din0   (tag_din0[gway]),
                .dout0  (tag_dout0[gway])
            );
`endif
        end
    endgenerate

    // =========================================================================
    // Data SRAM instances — LINE_WORDS per way (4 word-columns × WAYS)
    // =========================================================================
    logic        data_csb0  [0:WAYS_L-1][0:LINE_WORDS-1];
    logic        data_web0  [0:WAYS_L-1][0:LINE_WORDS-1];
    logic [7:0]  data_addr0 [0:WAYS_L-1][0:LINE_WORDS-1];
    logic [31:0] data_din0  [0:WAYS_L-1][0:LINE_WORDS-1];
    logic [31:0] data_dout0 [0:WAYS_L-1][0:LINE_WORDS-1];

    genvar gw2, gw;
    generate
        for (gw2 = 0; gw2 < WAYS_L; gw2++) begin : gen_data_sram_way
            for (gw = 0; gw < LINE_WORDS; gw++) begin : gen_data_sram_word
`ifdef SRAM_SKY130
                sky130_sram_1kbyte_1rw1r_32x256_8 u_data_sram (
                    .clk0   (clk),
                    .csb0   (data_csb0[gw2][gw]),
                    .web0   (data_web0[gw2][gw]),
                    .wmask0 (4'b1111),
                    .addr0  (data_addr0[gw2][gw]),
                    .din0   (data_din0[gw2][gw]),
                    .dout0  (data_dout0[gw2][gw]),
                    .clk1   (clk),
                    .csb1   (1'b1),
                    .addr1  (8'b0),
                    .dout1  ()
                );
`elsif SRAM_ASAP7
                logic data_gclk;
                rv32i_clock_gate u_data_cg (
                    .en  (!data_csb0[gw2][gw]),
                    .clk (clk),
                    .gclk(data_gclk)
                );
                sram_1rw_256x32_asap7 u_data_sram (
                    .clk0   (data_gclk),
                    .csb0   (data_csb0[gw2][gw]),
                    .web0   (data_web0[gw2][gw]),
                    .addr0  (data_addr0[gw2][gw]),
                    .din0   (data_din0[gw2][gw]),
                    .dout0  (data_dout0[gw2][gw])
                );
`else
                sram_1rw_256x32_freepdk45 u_data_sram (
                    .clk0   (clk),
                    .csb0   (data_csb0[gw2][gw]),
                    .web0   (data_web0[gw2][gw]),
                    .addr0  (data_addr0[gw2][gw]),
                    .din0   (data_din0[gw2][gw]),
                    .dout0  (data_dout0[gw2][gw])
                );
`endif
            end
        end
    endgenerate

    // =========================================================================
    // FSM state and pipeline registers
    // =========================================================================
    cache_state_t state_q;

    // Latched access address and control (registered when entering CS_SRAM_LATCH)
    logic [31:0]            dc_addr_q;
    logic                   dc_we_q;
    logic [31:0]            dc_wdata_q;
    logic [3:0]             dc_wstrb_q;

    // Address field aliases from latched address
    // INDEX_BITS_L and TAG_BITS_L are elaboration-time constants so the
    // bit-select widths are legal in all contexts.
    logic [TAG_BITS_L-1:0]   latch_tag;
    logic [INDEX_BITS_L-1:0] latch_index;
    logic [1:0]               latch_word;

    assign latch_tag   = dc_addr_q[31 : 32-TAG_BITS_L];
    assign latch_index = dc_addr_q[31-TAG_BITS_L : OFFSET_BITS];
    assign latch_word  = dc_addr_q[3:2];

    // Combinational address index from live input (for CS_IDLE SRAM read)
    logic [INDEX_BITS_L-1:0] addr_index;
    assign addr_index = dc_addr_i[31-TAG_BITS_L : OFFSET_BITS];

    // Writeback buffer: holds the full dirty line captured in CS_TAG_CHECK
    logic [LINE_WORDS-1:0][31:0] wb_buf_q;
    logic [TAG_BITS_L-1:0]       wb_tag_q;
    logic [INDEX_BITS_L-1:0]     wb_index_q;

    // Refill buffer and write-miss flag
    logic [LINE_WORDS-1:0][31:0] refill_buf_q;
    logic                         is_write_q;

    // AXI word counter (refill and writeback)
    logic [1:0]  axi_word_q;
    logic        ar_pending_q;
    logic        aw_done_q;
    logic        w_done_q;

    // ── Phase 5: uncached MMIO bypass registers ───────────────────────────────
    logic [31:0] uncached_rdata_q;

    // ── Phase 5: maintenance scan registers ──────────────────────────────────
    // maint_idx_q walks 0..N_SETS_L-1 (7 or 8 bits wide).
    // For WAYS=2 it is 7 bits (128 sets); for WAYS=1 it is 8 bits (256 sets).
    // Declared as 8 bits always; upper bits simply stay 0 for WAYS=2.
    logic [7:0]  maint_idx_q;
    // maint_way_q: which way is currently being written back in CS_FLUSH_SCAN
    // (WAYS=1: always 0; WAYS=2: 0 or 1, iterates across all ways per set).
    logic        maint_way_q;
    logic        flush_mode_q;
    logic        maint_done_q;
    logic        flush_pending_q;
    logic        inval_pending_q;

    // ── SRAM output pipeline registers ───────────────────────────────────────
    // tag_dout_r[way], data_dout_r[way][word]: captured at CS_SRAM_LATCH
    logic [31:0] tag_dout_r  [0:WAYS_L-1];
    logic [31:0] data_dout_r [0:WAYS_L-1][0:LINE_WORDS-1];

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            for (int wr = 0; wr < WAYS_L; wr++) begin
                tag_dout_r[wr] <= '0;
                for (int i = 0; i < LINE_WORDS; i++) data_dout_r[wr][i] <= '0;
            end
        end else if (state_q == CS_SRAM_LATCH) begin
            for (int wr = 0; wr < WAYS_L; wr++) begin
                tag_dout_r[wr] <= tag_dout0[wr];
                for (int i = 0; i < LINE_WORDS; i++) data_dout_r[wr][i] <= data_dout0[wr][i];
            end
        end
    end

    // Writeback base address (reconstructed from evicted tag + index)
    logic [31:0] wb_addr_base;
    assign wb_addr_base = {wb_tag_q, wb_index_q, {OFFSET_BITS{1'b0}}};

    // Refill base address
    logic [31:0] refill_base;
    assign refill_base = {dc_addr_q[31:OFFSET_BITS], {OFFSET_BITS{1'b0}}};

    // =========================================================================
    // Hit detection — pipelined (Run 15 timing fix, extended for WAYS=2)
    //
    // CS_HIT_PENDING: parallel tag compare across all ways.
    //   hit_comb[w] = valid_array[w][latch_index] && (tag_dout_r[w][TAG_BITS_L-1:0] == latch_tag)
    //
    // CS_TAG_CHECK: registered results.
    //   hit_q      = OR of hit_comb[] — overall hit indicator
    //   hit_way_q  = index of the hitting way (0 when WAYS=1; 0 or 1 for WAYS=2)
    //                For WAYS=2: if both ways somehow hit (tag collision, impossible
    //                in correct operation), way 0 takes priority.
    //
    // hit_bank_q[way][word]: per-way, per-bank registered copies of hit_comb[way].
    //   Used for write-hit SRAM control to reduce fanout (identical to WAYS=1
    //   where there is only one set of banks).
    //
    // WAYS=2 hit-path critical path:
    //   tag_dout_r[w][] → XOR comparator → hit_comb[w]
    //   → register (CS_HIT_PENDING) → hit_way_q → data_dout_r[hit_way_q][latch_word]
    //   This adds one 2:1 MUX level vs. the WAYS=1 path (see file header note).
    // =========================================================================
    logic hit_comb [0:WAYS_L-1];

    genvar ghw;
    generate
        for (ghw = 0; ghw < WAYS_L; ghw++) begin : g_hit_comb
            assign hit_comb[ghw] =
                valid_array[ghw][latch_index] &&
                (tag_dout_r[ghw][TAG_BITS_L-1:0] == latch_tag);
        end
    endgenerate

    // Overall hit and hitting-way registers
    logic        hit_q;
    logic        hit_way_q;  // 0 for WAYS=1 (unused); 0 or 1 for WAYS=2

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            hit_q     <= 1'b0;
            hit_way_q <= 1'b0;
        end else if (state_q == CS_HIT_PENDING) begin
            // OR-reduce across ways for overall hit.
            // |{hit_comb} does not reduce unpacked arrays in Verilator 5.x;
            // use an explicit loop so the generated C++ sees scalar ORs.
            begin
                logic any_hit;
                any_hit = 1'b0;
                for (int hi = 0; hi < WAYS_L; hi++)
                    any_hit = any_hit | hit_comb[hi];
                hit_q <= any_hit;
            end
            // Priority encode: way 0 wins ties (not expected in correct operation)
            if (WAYS_L == 1) begin
                hit_way_q <= 1'b0;
            end else begin
                // WAYS=2: way 0 has priority
                hit_way_q <= (hit_comb[0]) ? 1'b0 : 1'b1;
            end
        end else if (state_q == CS_TAG_CHECK) begin
            hit_q     <= 1'b0;
            hit_way_q <= 1'b0;
        end
    end

    // Per-way, per-bank registered copies — fanout reduction on write-hit control
    // hit_bank_q[way][bank]: registered copy of hit_comb[way].
    (* keep = 1 *) logic hit_bank_q [0:WAYS_L-1][0:LINE_WORDS-1];
    genvar ghb, ghbw;
    generate
        for (ghbw = 0; ghbw < WAYS_L; ghbw++) begin : g_hit_bank_way
            for (ghb = 0; ghb < LINE_WORDS; ghb++) begin : g_hit_bank_word
                always_ff @(posedge clk) begin
                    if (!rst_n)
                        hit_bank_q[ghbw][ghb] <= 1'b0;
                    else if (state_q == CS_HIT_PENDING)
                        hit_bank_q[ghbw][ghb] <= hit_comb[ghbw];
                    else if (state_q == CS_TAG_CHECK)
                        hit_bank_q[ghbw][ghb] <= 1'b0;
                end
            end
        end
    endgenerate

    // =========================================================================
    // Victim-way selection (WAYS=2 replacement policy)
    //
    // On a miss in CS_TAG_CHECK:
    //   1. If any way in latch_index is invalid → fill that way (invalid-first).
    //   2. Else → fill the LRU way (lru_array[latch_index] XOR 1).
    //
    // victim_way_q: registered in CS_TAG_CHECK, consumed by CS_WRITEBACK and
    //   CS_REFILL to write the correct SRAM way and update valid/dirty/LRU.
    // =========================================================================
    logic victim_way_q;

    // Need writeback: victim line is valid, dirty, and a different tag exists.
    // Computed purely combinationally from tag_dout_r / valid_array / dirty_array
    // so it is ready in CS_TAG_CHECK (same cycle hit_q is consumed).
    //
    // For WAYS=2: we compute the candidate victim inline (invalid-first, then LRU)
    // so that need_writeback does not depend on the registered victim_way_q (which
    // is also set this cycle in CS_TAG_CHECK — a circular dependency that would
    // create a combinational loop or incorrect behaviour due to scheduling order).
    logic need_writeback;
    logic cand_vw;           // combinational candidate victim way (before registration)

    // WAY1_IDX: index of way-1 clamped to 0 when WAYS_L=1 to avoid out-of-range
    // array accesses that Verilator checks even inside dead `if (WAYS_L>1)` branches.
    localparam int WAY1_IDX = (WAYS_L > 1) ? 1 : 0;

    always_comb begin
        // Default: way 0 is the only candidate victim for WAYS=1
        cand_vw = 1'b0;
        if (WAYS_L > 1) begin
            if (!valid_array[0][latch_index])
                cand_vw = 1'b0;
            else if (!valid_array[WAY1_IDX][latch_index])
                cand_vw = 1'b1;
            else
                cand_vw = lru_array[latch_index] ^ 1'b1;
        end
        need_writeback = valid_array[cand_vw][latch_index] &&
                         dirty_array[cand_vw][latch_index] &&
                         (tag_dout_r[cand_vw][TAG_BITS_L-1:0] != latch_tag);
    end

    // Registered victim way (set in CS_TAG_CHECK when miss detected).
    // Simply register cand_vw computed combinationally above.
    always_ff @(posedge clk) begin
        if (!rst_n) begin
            victim_way_q <= 1'b0;
        end else if (state_q == CS_TAG_CHECK && !hit_q) begin
            victim_way_q <= cand_vw;
        end
    end

    // =========================================================================
    // Stall output
    // =========================================================================
    assign dc_stall_o =
        (state_q == CS_IDLE        && dc_valid_i) ||
        (state_q == CS_SRAM_LATCH)                ||
        (state_q == CS_HIT_PENDING)               ||
        (state_q == CS_TAG_CHECK   && !hit_q)     ||
        (state_q == CS_WRITEBACK)                 ||
        (state_q == CS_REFILL)                    ||
        (state_q == CS_UNCACHED_RD)               ||
        (state_q == CS_UNCACHED_WR)               ||
        (state_q == CS_FLUSH_SCAN)                ||
        (state_q == CS_INVAL_SCAN);

    // =========================================================================
    // Miss strobe output (Phase 5 M7 — performance counter event)
    // =========================================================================
    assign dc_miss_o = (state_q == CS_TAG_CHECK) && !hit_q;

    // =========================================================================
    // Maintenance done strobe (Phase 5)
    // =========================================================================
    assign dc_maint_done_o = maint_done_q;

    // =========================================================================
    // Read data output
    // =========================================================================
    always_comb begin
        case (state_q)
            CS_TAG_CHECK:   dc_rdata_o = data_dout_r[hit_way_q][latch_word]; // read hit
            CS_DONE:        dc_rdata_o = refill_buf_q[latch_word];            // read-miss refilled
            CS_UNCACHED_RD: dc_rdata_o = uncached_rdata_q;                    // uncached (captured R)
            default:        dc_rdata_o = 32'b0;
        endcase
    end

    // =========================================================================
    // AXI read control — muxed between burst refill and uncached single-beat
    // =========================================================================
    always_comb begin
        if (state_q == CS_UNCACHED_RD) begin
            axi_araddr_o  = {dc_addr_q[31:2], 2'b00};
            axi_arlen_o   = 8'd0;
            axi_arsize_o  = axi_pkg::AXI_SIZE_4B;
            axi_arburst_o = axi_pkg::AXI_BURST_INCR;
            axi_arvalid_o = !ar_pending_q;
        end else begin
            axi_araddr_o  = {refill_base[31:OFFSET_BITS], {OFFSET_BITS{1'b0}}};
            axi_arlen_o   = axi_pkg::AXI_LEN_LINE;
            axi_arsize_o  = axi_pkg::AXI_SIZE_4B;
            axi_arburst_o = axi_pkg::AXI_BURST_INCR;
            axi_arvalid_o = (state_q == CS_REFILL) && !ar_pending_q;
        end
    end
    assign axi_rready_o = 1'b1;

    // =========================================================================
    // AXI write control — muxed between burst writeback and uncached single-beat
    // =========================================================================
    always_comb begin
        if (state_q == CS_UNCACHED_WR) begin
            axi_awaddr_o  = {dc_addr_q[31:2], 2'b00};
            axi_awlen_o   = 8'd0;
            axi_awsize_o  = axi_pkg::AXI_SIZE_4B;
            axi_awburst_o = axi_pkg::AXI_BURST_INCR;
            axi_awvalid_o = !aw_done_q;
            axi_wdata_o   = dc_wdata_q;
            axi_wstrb_o   = dc_wstrb_q;
            axi_wlast_o   = !w_done_q;
            axi_wvalid_o  = !w_done_q;
        end else begin
            axi_awaddr_o  = {wb_addr_base[31:OFFSET_BITS], {OFFSET_BITS{1'b0}}};
            axi_awlen_o   = axi_pkg::AXI_LEN_LINE;
            axi_awsize_o  = axi_pkg::AXI_SIZE_4B;
            axi_awburst_o = axi_pkg::AXI_BURST_INCR;
            axi_awvalid_o = (state_q == CS_WRITEBACK) && !aw_done_q;
            axi_wdata_o   = wb_buf_q[axi_word_q];
            axi_wstrb_o   = 4'b1111;
            axi_wlast_o   = (state_q == CS_WRITEBACK) && (axi_word_q == 2'd3);
            axi_wvalid_o  = (state_q == CS_WRITEBACK) && !w_done_q;
        end
    end
    assign axi_bready_o = 1'b1;

    // =========================================================================
    // Write-hit byte merge: merge cached data with CPU write data
    // =========================================================================
    logic [31:0] merged_hit_word;
    assign merged_hit_word[7:0]   = dc_wstrb_q[0] ? dc_wdata_q[7:0]   : data_dout_r[hit_way_q][latch_word][7:0];
    assign merged_hit_word[15:8]  = dc_wstrb_q[1] ? dc_wdata_q[15:8]  : data_dout_r[hit_way_q][latch_word][15:8];
    assign merged_hit_word[23:16] = dc_wstrb_q[2] ? dc_wdata_q[23:16] : data_dout_r[hit_way_q][latch_word][23:16];
    assign merged_hit_word[31:24] = dc_wstrb_q[3] ? dc_wdata_q[31:24] : data_dout_r[hit_way_q][latch_word][31:24];

    // Write-miss byte merge: merge AXI refill data with CPU write data
    logic [31:0] merged_refill_word;
    assign merged_refill_word[7:0]   = dc_wstrb_q[0] ? dc_wdata_q[7:0]   : axi_rdata_i[7:0];
    assign merged_refill_word[15:8]  = dc_wstrb_q[1] ? dc_wdata_q[15:8]  : axi_rdata_i[15:8];
    assign merged_refill_word[23:16] = dc_wstrb_q[2] ? dc_wdata_q[23:16] : axi_rdata_i[23:16];
    assign merged_refill_word[31:24] = dc_wstrb_q[3] ? dc_wdata_q[31:24] : axi_rdata_i[31:24];

    // =========================================================================
    // SRAM combinational control — Tag SRAMs (one per way)
    // =========================================================================
    always_comb begin
        for (int tw = 0; tw < WAYS_L; tw++) begin
            tag_csb0[tw]  = 1'b1;
            tag_web0[tw]  = 1'b1;
            tag_addr0[tw] = 8'b0;
            tag_din0[tw]  = 32'b0;
        end

        case (state_q)
            CS_IDLE: begin
                // Read all way tag SRAMs simultaneously (only for cacheable addresses)
                if (dc_valid_i && !(dc_addr_i >= MMIO_BASE)) begin
                    for (int tw = 0; tw < WAYS_L; tw++) begin
                        tag_csb0[tw]  = 1'b0;
                        tag_web0[tw]  = 1'b1;
                        tag_addr0[tw] = 8'(addr_index);  // upper bits are 0 for WAYS=2
                    end
                end
            end

            CS_REFILL: begin
                // Write new tag to the victim way on last burst beat (RLAST)
                if (ar_pending_q && axi_rvalid_i && axi_rlast_i) begin
                    tag_csb0[victim_way_q]  = 1'b0;
                    tag_web0[victim_way_q]  = 1'b0;
                    tag_addr0[victim_way_q] = 8'(latch_index);
                    tag_din0[victim_way_q]  = {{(32-TAG_BITS_L){1'b0}}, latch_tag};
                end
            end

            // CS_FLUSH_SCAN: read all way tag SRAMs at maint_idx_q so tag_dout_r
            // is valid after CS_SRAM_LATCH.  Only read the specific way being
            // flushed (maint_way_q).
            CS_FLUSH_SCAN: begin
                if (dirty_array[maint_way_q][maint_idx_q[INDEX_BITS_L-1:0]] &&
                    valid_array[maint_way_q][maint_idx_q[INDEX_BITS_L-1:0]]) begin
                    tag_csb0[maint_way_q]  = 1'b0;
                    tag_web0[maint_way_q]  = 1'b1;
                    tag_addr0[maint_way_q] = 8'(maint_idx_q);
                end
            end

            default: ;
        endcase
    end

    // =========================================================================
    // SRAM combinational control — Data SRAMs (LINE_WORDS per way)
    // =========================================================================
    always_comb begin
        for (int dw2 = 0; dw2 < WAYS_L; dw2++) begin
            for (int dw = 0; dw < LINE_WORDS; dw++) begin
                data_csb0[dw2][dw]  = 1'b1;
                data_web0[dw2][dw]  = 1'b1;
                data_addr0[dw2][dw] = 8'b0;
                data_din0[dw2][dw]  = 32'b0;
            end
        end

        case (state_q)
            CS_IDLE: begin
                // Read all word-column SRAMs for all ways simultaneously
                if (dc_valid_i && !(dc_addr_i >= MMIO_BASE)) begin
                    for (int dw2 = 0; dw2 < WAYS_L; dw2++) begin
                        for (int dw = 0; dw < LINE_WORDS; dw++) begin
                            data_csb0[dw2][dw]  = 1'b0;
                            data_web0[dw2][dw]  = 1'b1;
                            data_addr0[dw2][dw] = 8'(addr_index);
                        end
                    end
                end
            end

            CS_TAG_CHECK: begin
                // Write hit: byte-masked write to the hitting way's word column.
                // hit_bank_q[hit_way_q][latch_word] is the registered copy of
                // hit_comb[hit_way_q] — per-way, per-bank for fanout reduction.
                if (hit_bank_q[hit_way_q][latch_word] && dc_we_q) begin
                    data_csb0[hit_way_q][latch_word]  = 1'b0;
                    data_web0[hit_way_q][latch_word]  = 1'b0;
                    data_addr0[hit_way_q][latch_word] = 8'(latch_index);
                    data_din0[hit_way_q][latch_word]  = merged_hit_word;
                end
            end

            CS_REFILL: begin
                // Write each arriving word to the victim way's SRAM column.
                if (ar_pending_q && axi_rvalid_i) begin
                    data_csb0[victim_way_q][axi_word_q]  = 1'b0;
                    data_web0[victim_way_q][axi_word_q]  = 1'b0;
                    data_addr0[victim_way_q][axi_word_q] = 8'(latch_index);
                    data_din0[victim_way_q][axi_word_q]  =
                        (is_write_q && (axi_word_q == latch_word))
                        ? merged_refill_word
                        : axi_rdata_i;
                end
            end

            // CS_FLUSH_SCAN: read the maint_way_q data SRAMs at maint_idx_q
            CS_FLUSH_SCAN: begin
                if (dirty_array[maint_way_q][maint_idx_q[INDEX_BITS_L-1:0]] &&
                    valid_array[maint_way_q][maint_idx_q[INDEX_BITS_L-1:0]]) begin
                    for (int dw = 0; dw < LINE_WORDS; dw++) begin
                        data_csb0[maint_way_q][dw]  = 1'b0;
                        data_web0[maint_way_q][dw]  = 1'b1;
                        data_addr0[maint_way_q][dw] = 8'(maint_idx_q);
                    end
                end
            end

            default: ;
        endcase
    end

    // =========================================================================
    // FSM — sequential logic
    //
    // Flush/inval scan termination for WAYS=2:
    //   The scan walks maint_idx_q over 0..N_SETS_L-1.  For WAYS=2, after
    //   completing all sets for maint_way_q=0, maint_way_q is incremented to 1
    //   and maint_idx_q resets to 0 to scan way 1.  Scan is complete when
    //   maint_way_q==WAYS_L-1 and maint_idx_q==N_SETS_L-1.
    //   For WAYS=1, maint_way_q stays 0 and maint_idx_q walks 0..255 exactly
    //   as before — no change to the WAYS=1 termination condition.
    // =========================================================================
    always_ff @(posedge clk) begin
        if (!rst_n) begin
            state_q           <= CS_IDLE;
            dc_addr_q         <= '0;
            dc_we_q           <= 1'b0;
            dc_wdata_q        <= '0;
            dc_wstrb_q        <= '0;
            axi_word_q        <= 2'b00;
            ar_pending_q      <= 1'b0;
            aw_done_q         <= 1'b0;
            w_done_q          <= 1'b0;
            wb_buf_q          <= '0;
            wb_tag_q          <= '0;
            wb_index_q        <= '0;
            refill_buf_q      <= '0;
            is_write_q        <= 1'b0;
            uncached_rdata_q  <= '0;
            maint_idx_q       <= 8'h00;
            maint_way_q       <= 1'b0;
            flush_mode_q      <= 1'b0;
            maint_done_q      <= 1'b0;
            flush_pending_q   <= 1'b0;
            inval_pending_q   <= 1'b0;
            victim_way_q      <= 1'b0;
        end else begin
            maint_done_q <= 1'b0;  // default: clear done pulse every cycle

            // Latch maintenance requests that arrive while the cache is busy.
            if (dc_flush_i && state_q != CS_IDLE) flush_pending_q <= 1'b1;
            if (dc_inval_i && state_q != CS_IDLE && !flush_pending_q) inval_pending_q <= 1'b1;

            case (state_q)
                // -----------------------------------------------------------------
                CS_IDLE: begin
                    if (dc_valid_i) begin
                        // CPU access takes priority; latch concurrent maintenance pulse.
                        if (dc_flush_i) flush_pending_q <= 1'b1;
                        else if (dc_inval_i && !flush_pending_q) inval_pending_q <= 1'b1;
                        dc_addr_q  <= dc_addr_i;
                        dc_we_q    <= dc_we_i;
                        dc_wdata_q <= dc_wdata_i;
                        dc_wstrb_q <= dc_wstrb_i;
                        if (dc_addr_i >= MMIO_BASE) begin
                            axi_word_q   <= 2'b00;
                            ar_pending_q <= 1'b0;
                            aw_done_q    <= 1'b0;
                            w_done_q     <= 1'b0;
                            if (dc_we_i)
                                state_q <= CS_UNCACHED_WR;
                            else
                                state_q <= CS_UNCACHED_RD;
                        end else begin
                            state_q <= CS_SRAM_LATCH;
                        end
                    end else begin
                        // No CPU access; consume pending or live maintenance request.
                        if (flush_pending_q || dc_flush_i) begin
                            flush_pending_q <= 1'b0;
                            flush_mode_q    <= 1'b1;
                            maint_idx_q     <= 8'h00;
                            maint_way_q     <= 1'b0;
                            axi_word_q      <= 2'b00;
                            aw_done_q       <= 1'b0;
                            w_done_q        <= 1'b0;
                            state_q         <= CS_FLUSH_SCAN;
                        end else if (inval_pending_q || dc_inval_i) begin
                            inval_pending_q <= 1'b0;
                            maint_idx_q     <= 8'h00;
                            maint_way_q     <= 1'b0;
                            state_q         <= CS_INVAL_SCAN;
                        end
                    end
                end

                // -----------------------------------------------------------------
                CS_SRAM_LATCH: begin
                    state_q <= CS_HIT_PENDING;
                end

                // -----------------------------------------------------------------
                CS_HIT_PENDING: begin
                    // hit_comb[] → hit_q / hit_way_q / hit_bank_q[] captured this cycle.
                    if (flush_mode_q) begin
                        // Flush path: data_dout_r valid; load wb_buf and hand off.
                        for (int wbw = 0; wbw < LINE_WORDS; wbw++) begin
                            wb_buf_q[wbw] <= data_dout_r[maint_way_q][wbw];
                        end
                        wb_tag_q <= tag_dout_r[maint_way_q][TAG_BITS_L-1:0];
                        // wb_index_q already latched in CS_FLUSH_SCAN
                        state_q  <= CS_WRITEBACK;
                    end else begin
                        state_q <= CS_TAG_CHECK;
                    end
                end

                // -----------------------------------------------------------------
                CS_TAG_CHECK: begin
                    if (hit_q) begin
                        // Hit: data available. Write hit SRAM issued combinationally.
                        // LRU update: mark this way as MRU.
                        if (WAYS_L > 1) begin
                            lru_array[latch_index] <= hit_way_q;
                        end
                        state_q <= CS_IDLE;
                    end else begin
                        // Miss: set up for writeback or refill.
                        axi_word_q   <= 2'b00;
                        ar_pending_q <= 1'b0;
                        aw_done_q    <= 1'b0;
                        w_done_q     <= 1'b0;
                        is_write_q   <= dc_we_q;
                        // victim_way_q is set by separate always_ff above.

                        if (need_writeback) begin
                            // Capture dirty line from the victim way's SRAM dout.
                            for (int wbw = 0; wbw < LINE_WORDS; wbw++) begin
                                wb_buf_q[wbw] <= data_dout_r[victim_way_q][wbw];
                            end
                            wb_tag_q     <= tag_dout_r[victim_way_q][TAG_BITS_L-1:0];
                            wb_index_q   <= latch_index;
                            flush_mode_q <= 1'b0;
                            state_q      <= CS_WRITEBACK;
                        end else begin
                            state_q <= CS_REFILL;
                        end
                    end
                end

                // -----------------------------------------------------------------
                // CS_WRITEBACK — AXI4 burst writeback
                CS_WRITEBACK: begin
                    if (!aw_done_q && axi_awready_i)
                        aw_done_q <= 1'b1;
                    if (!w_done_q && axi_wvalid_o && axi_wready_i) begin
                        if (axi_word_q == 2'd3) begin
                            w_done_q <= 1'b1;
                        end else begin
                            axi_word_q <= axi_word_q + 1'b1;
                        end
                    end
                    if (axi_bvalid_i && (axi_bresp_i == 2'b00)) begin
                        aw_done_q  <= 1'b0;
                        w_done_q   <= 1'b0;
                        axi_word_q <= 2'b00;
                        if (flush_mode_q) begin
                            // Maintenance writeback: check if scan is complete.
                            // Termination: maint_way_q == LAST_WAY and
                            //              wb_index_q  == LAST_SET
                            if ((wb_index_q == LAST_SET_8[INDEX_BITS_L-1:0]) &&
                                (maint_way_q == LAST_WAY)) begin
                                maint_done_q <= 1'b1;
                                maint_idx_q  <= 8'h00;
                                maint_way_q  <= 1'b0;
                                flush_mode_q <= 1'b0;
                                state_q      <= CS_IDLE;
                            end else if (wb_index_q == LAST_SET_8[INDEX_BITS_L-1:0]) begin
                                // End of this way; move to next way
                                maint_way_q  <= maint_way_q + 1'b1;
                                maint_idx_q  <= 8'h00;
                                state_q      <= CS_FLUSH_SCAN;
                            end else begin
                                maint_idx_q[INDEX_BITS_L-1:0] <= wb_index_q + 1'b1;
                                state_q     <= CS_FLUSH_SCAN;
                            end
                        end else begin
                            state_q <= CS_REFILL;
                        end
                    end else if (axi_bvalid_i && (axi_bresp_i != 2'b00)) begin
                        state_q    <= CS_IDLE;
                        aw_done_q  <= 1'b0;
                        w_done_q   <= 1'b0;
                        axi_word_q <= 2'b00;
                    end
                end

                // -----------------------------------------------------------------
                // CS_REFILL — AXI4 burst refill (4 beats)
                CS_REFILL: begin
                    if (!ar_pending_q) begin
                        if (axi_arready_i)
                            ar_pending_q <= 1'b1;
                    end else begin
                        if (axi_rvalid_i && (axi_rresp_i == 2'b00)) begin
                            refill_buf_q[axi_word_q] <=
                                (is_write_q && (axi_word_q == latch_word))
                                ? merged_refill_word
                                : axi_rdata_i;
                            if (axi_rlast_i) begin
                                state_q      <= CS_DONE;
                                ar_pending_q <= 1'b0;
                                axi_word_q   <= 2'b00;
                                // LRU update: mark victim way as MRU (it was just filled)
                                if (WAYS_L > 1) begin
                                    lru_array[latch_index] <= victim_way_q;
                                end
                            end else begin
                                if (axi_word_q != 2'd3)
                                    axi_word_q <= axi_word_q + 1'b1;
                            end
                        end else if (axi_rvalid_i && (axi_rresp_i != 2'b00)) begin
                            state_q      <= CS_IDLE;
                            ar_pending_q <= 1'b0;
                            axi_word_q   <= 2'b00;
                        end
                    end
                end

                // -----------------------------------------------------------------
                CS_DONE: begin
                    state_q <= CS_IDLE;
                end

                // -----------------------------------------------------------------
                // CS_UNCACHED_RD — single-beat AXI read bypass (MMIO address)
                CS_UNCACHED_RD: begin
                    if (!ar_pending_q) begin
                        if (axi_arready_i)
                            ar_pending_q <= 1'b1;
                    end else begin
                        if (axi_rvalid_i) begin
                            ar_pending_q <= 1'b0;
                            state_q      <= CS_DONE;
                            if (axi_rresp_i == 2'b00) begin
                                uncached_rdata_q         <= axi_rdata_i;
                                refill_buf_q[latch_word] <= axi_rdata_i;
                            end else begin
                                uncached_rdata_q         <= 32'h0;
                                refill_buf_q[latch_word] <= 32'h0;
                            end
                        end
                    end
                end

                // -----------------------------------------------------------------
                // CS_UNCACHED_WR — single-beat AXI write bypass (MMIO address)
                CS_UNCACHED_WR: begin
                    if (!aw_done_q && axi_awready_i)
                        aw_done_q <= 1'b1;
                    if (!w_done_q && axi_wvalid_o && axi_wready_i)
                        w_done_q <= 1'b1;
                    if (axi_bvalid_i) begin
                        aw_done_q <= 1'b0;
                        w_done_q  <= 1'b0;
                        state_q   <= CS_DONE;
                    end
                end

                // -----------------------------------------------------------------
                // CS_FLUSH_SCAN — walk all N_SETS_L sets × WAYS_L ways
                // Outer loop: maint_way_q (0..WAYS_L-1)
                // Inner loop: maint_idx_q (0..N_SETS_L-1)
                //
                // For each (way, set): if dirty && valid, read SRAM and go to
                // CS_WRITEBACK (via CS_SRAM_LATCH → CS_HIT_PENDING, flush_mode_q=1).
                // After writeback the B-response handler above advances maint_idx_q
                // and maint_way_q and returns here.
                //
                // Termination guarantee: the scan terminates in exactly
                //   WAYS_L × N_SETS_L cycles (1 per clean/invalid entry)
                //   + (# dirty lines) × writeback time.
                // The CSRRW flush-pulse re-fire gotcha (Jun-16 root cause) is
                // prevented by the flush_pending_q / dc_flush_i latch in CS_IDLE:
                // the FSM only enters CS_FLUSH_SCAN from CS_IDLE, never from within
                // the scan itself, and flush_pending_q is cleared at entry.
                CS_FLUSH_SCAN: begin
                    if (dirty_array[maint_way_q][maint_idx_q[INDEX_BITS_L-1:0]] &&
                        valid_array[maint_way_q][maint_idx_q[INDEX_BITS_L-1:0]]) begin
                        // Dirty line: SRAM read issued combinationally; pipeline through
                        // CS_SRAM_LATCH → CS_HIT_PENDING (flush_mode_q=1) → CS_WRITEBACK.
                        axi_word_q   <= 2'b00;
                        aw_done_q    <= 1'b0;
                        w_done_q     <= 1'b0;
                        wb_index_q   <= maint_idx_q[INDEX_BITS_L-1:0];
                        state_q      <= CS_SRAM_LATCH;
                    end else begin
                        // Clean or invalid: advance scan pointer.
                        if ((maint_idx_q[INDEX_BITS_L-1:0] == LAST_SET_8[INDEX_BITS_L-1:0]) &&
                            (maint_way_q == LAST_WAY)) begin
                            // All sets × all ways walked: scan complete
                            maint_done_q <= 1'b1;
                            maint_idx_q  <= 8'h00;
                            maint_way_q  <= 1'b0;
                            flush_mode_q <= 1'b0;
                            state_q      <= CS_IDLE;
                        end else if (maint_idx_q[INDEX_BITS_L-1:0] == LAST_SET_8[INDEX_BITS_L-1:0]) begin
                            // End of this way's sets: advance to next way
                            maint_way_q <= maint_way_q + 1'b1;
                            maint_idx_q <= 8'h00;
                            // remain in CS_FLUSH_SCAN
                        end else begin
                            maint_idx_q[INDEX_BITS_L-1:0] <=
                                maint_idx_q[INDEX_BITS_L-1:0] + 1'b1;
                            // remain in CS_FLUSH_SCAN
                        end
                    end
                end

                // -----------------------------------------------------------------
                // CS_INVAL_SCAN — clear valid+dirty for all sets × ways (no AXI)
                // For WAYS=2: outer loop maint_way_q, inner loop maint_idx_q.
                // valid/dirty writes handled in the valid/dirty always_ff below.
                CS_INVAL_SCAN: begin
                    if ((maint_idx_q[INDEX_BITS_L-1:0] == LAST_SET_8[INDEX_BITS_L-1:0]) &&
                        (maint_way_q == LAST_WAY)) begin
                        maint_done_q <= 1'b1;
                        maint_idx_q  <= 8'h00;
                        maint_way_q  <= 1'b0;
                        state_q      <= CS_IDLE;
                    end else if (maint_idx_q[INDEX_BITS_L-1:0] == LAST_SET_8[INDEX_BITS_L-1:0]) begin
                        maint_way_q <= maint_way_q + 1'b1;
                        maint_idx_q <= 8'h00;
                        // remain in CS_INVAL_SCAN
                    end else begin
                        maint_idx_q[INDEX_BITS_L-1:0] <=
                            maint_idx_q[INDEX_BITS_L-1:0] + 1'b1;
                    end
                end

                default: state_q <= CS_IDLE;
            endcase
        end
    end

    // =========================================================================
    // Valid, dirty, and LRU arrays — sequential
    // =========================================================================
    /* verilator lint_off BLKSEQ */
    always_ff @(posedge clk) begin
        if (!rst_n) begin
            for (int vw = 0; vw < WAYS_L; vw++) begin
                for (int vs = 0; vs < N_SETS_L; vs++) begin
                    valid_array[vw][vs] = 1'b0;
                    dirty_array[vw][vs] = 1'b0;
                end
            end
            for (int ls = 0; ls < N_SETS_L; ls++) begin
                lru_array[ls] = 1'b0;
            end
        end else begin
            // Write hit: set dirty for the hitting way
            if (state_q == CS_TAG_CHECK && hit_q && dc_we_q)
                dirty_array[hit_way_q][latch_index] <= 1'b1;

            // Writeback complete: clear dirty (flush keeps valid; miss evicts both)
            if (state_q == CS_WRITEBACK && axi_bvalid_i) begin
                dirty_array[flush_mode_q ? maint_way_q : victim_way_q][wb_index_q] <= 1'b0;
                if (!flush_mode_q)
                    valid_array[victim_way_q][wb_index_q] <= 1'b0;
            end

            // Refill complete: mark victim way valid; dirty iff write-miss
            if (state_q == CS_REFILL && ar_pending_q && axi_rvalid_i && axi_rlast_i) begin
                valid_array[victim_way_q][latch_index] <= 1'b1;
                dirty_array[victim_way_q][latch_index] <= is_write_q;
            end

            // CS_INVAL_SCAN: clear valid+dirty for current (way, set)
            if (state_q == CS_INVAL_SCAN) begin
                valid_array[maint_way_q][maint_idx_q[INDEX_BITS_L-1:0]] <= 1'b0;
                dirty_array[maint_way_q][maint_idx_q[INDEX_BITS_L-1:0]] <= 1'b0;
            end
        end
    end
    /* verilator lint_on BLKSEQ */

    // =========================================================================
    // Suppress unused-signal warnings
    // axi_rresp_i and axi_bresp_i are used in FSM resp checks above.
    // =========================================================================
    /* verilator lint_off UNUSEDSIGNAL */
    // (no currently-unused signals)
    /* verilator lint_on  UNUSEDSIGNAL */

endmodule

`default_nettype wire
