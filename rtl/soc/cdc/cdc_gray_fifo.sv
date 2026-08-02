// cdc_gray_fifo.sv
// GH #91 — Generic dual-clock gray-pointer FIFO, ready/valid on both faces.
//
// Cummings SNUG-2002 "Simulation and Synthesis Techniques for Asynchronous
// FIFO Design" style-1 dual-clock FIFO: binary read/write pointers are kept
// locally in each domain, converted to gray code, and only the REGISTERED
// gray pointer crosses the clock boundary — through exactly one
// cdc_2ff_sync instance per direction. The full/empty flags are each
// computed from a comparison between the local combinational next-state
// gray pointer and the ALREADY-SYNCHRONISED remote gray pointer, then
// registered. This costs one extra cycle of pointer latency but is what
// makes the flag timing-closeable (both compare operands are stable for a
// full local clock period before the flag registers).
//
// Params:
//   WIDTH       — payload width in bits.
//   DEPTH       — FIFO depth in entries. MUST be a power of two and >= 4.
//                 Power-of-two is required by the gray-code wrap arithmetic.
//                 DEPTH must be >= 4 (not 2): at DEPTH=2, PTR_W=$clog2(2)+1=2
//                 and the full-flag address slice rd_gray_sync_w[PTR_W-3:0]
//                 degenerates to [-1:0], which is not a legal bit range —
//                 DEPTH=2 is therefore illegal, not merely impractical.
//   SYNC_STAGES — stage count passed to both internal cdc_2ff_sync gray
//                 pointer synchronisers (>= 2 required; see cdc_2ff_sync.sv).
//
// !!! mem_q is a genuine ASYNCHRONOUS DATA PATH !!!
// Storage is a flop array (`logic [WIDTH-1:0] mem_q [DEPTH]`), written on
// wr_clk_i, read COMBINATIONALLY at rd_bin_q on rd_clk_i — with no reset of
// its own. This is safe ONLY because a written entry cannot become visible
// to the read side (rd_valid_o) until the write pointer's gray code has
// propagated through SYNC_STAGES receiving flops in u_wr_ptr_to_rd and been
// compared into empty_q. Nothing in RTL or simulation constrains the mem_q
// write-clk -> read-domain-combinational-read timing path structurally.
// GH #94 MUST add `set_max_delay -datapath_only` (bounded to <= one
// receiving clock period) on:
//   (1) this mem_q write-to-read-domain-combinational-read path, and
//   (2) both registered gray-pointer crossings (u_wr_ptr_to_rd, u_rd_ptr_to_wr).
//
// No combinational path crosses the clock boundary anywhere else in this
// module — both wr_ready_o and rd_valid_o are driven locally from flags that
// are themselves computed from already-synchronised inputs (wr_ready_o is
// additionally qualified by its own domain's wr_rst_n_i, a same-domain
// input, not a cross-domain path — see the reset-gating note above
// full_q/empty_q's derivation below).
//
// Reset: asynchronous assert, synchronous deassert, active-low per domain
// (docs/development/CODING_GUIDELINES.md §1.4). wr_rst_n_i / rd_rst_n_i are
// expected to already be domain-synchronised at the call site (see
// async_axi_fifo.sv, which drives them from cdc_reset_sync outputs sharing a
// common `s_rst_n_i & m_rst_n_i` root).
//
// Lint target: verilator -Wall -Wno-IMPORTSTAR 0 errors 0 warnings.

module cdc_gray_fifo #(
    parameter int unsigned WIDTH       = 32,
    parameter int unsigned DEPTH       = 4,
    parameter int unsigned SYNC_STAGES = 2
) (
    // ── Write (source) domain ────────────────────────────────────────────────
    input  logic             wr_clk_i,
    input  logic             wr_rst_n_i,
    input  logic [WIDTH-1:0] wr_data_i,
    input  logic             wr_valid_i,
    output logic             wr_ready_o,

    // ── Read (destination) domain ────────────────────────────────────────────
    input  logic             rd_clk_i,
    input  logic             rd_rst_n_i,
    output logic [WIDTH-1:0] rd_data_o,
    output logic             rd_valid_o,
    input  logic             rd_ready_i
);

    // Elaboration-time guard: DEPTH must be a power of two and >= 4 (see
    // header). Generate-scope $fatal (not wrapped in `initial`) so it fires
    // under `verilator --lint-only` / synthesis elaboration and not only
    // under simulation — see rtl/soc/sram_controller.sv:110-126 for the
    // precedent and the reason `initial $fatal` alone is insufficient here.
    if ((DEPTH < 4) || ((DEPTH & (DEPTH - 1)) != 0)) begin : g_depth_check
        $fatal(1, "cdc_gray_fifo: DEPTH (%0d) must be a power of two and >= 4", DEPTH);
    end

    // ── Local geometry ────────────────────────────────────────────────────────
    localparam int unsigned PTR_W  = $clog2(DEPTH) + 1;  // +1 wrap bit
    localparam int unsigned ADDR_W = PTR_W - 1;

    // ── Write-domain binary + gray pointers ──────────────────────────────────
    logic [PTR_W-1:0] wr_bin_q, wr_bin_d;
    logic [PTR_W-1:0] wr_gray_q, wr_gray_d;
    logic             wr_en;

    assign wr_en     = wr_valid_i && wr_ready_o;
    assign wr_bin_d  = wr_bin_q + PTR_W'(wr_en);
    assign wr_gray_d = (wr_bin_d >> 1) ^ wr_bin_d;

    always_ff @(posedge wr_clk_i or negedge wr_rst_n_i) begin
        if (!wr_rst_n_i) begin
            wr_bin_q  <= '0;
            wr_gray_q <= '0;
        end else begin
            wr_bin_q  <= wr_bin_d;
            wr_gray_q <= wr_gray_d;
        end
    end

    // ── Read-domain binary + gray pointers ───────────────────────────────────
    logic [PTR_W-1:0] rd_bin_q, rd_bin_d;
    logic [PTR_W-1:0] rd_gray_q, rd_gray_d;
    logic             rd_en;

    assign rd_en     = rd_valid_o && rd_ready_i;
    assign rd_bin_d  = rd_bin_q + PTR_W'(rd_en);
    assign rd_gray_d = (rd_bin_d >> 1) ^ rd_bin_d;

    always_ff @(posedge rd_clk_i or negedge rd_rst_n_i) begin
        if (!rd_rst_n_i) begin
            rd_bin_q  <= '0;
            rd_gray_q <= '0;
        end else begin
            rd_bin_q  <= rd_bin_d;
            rd_gray_q <= rd_gray_d;
        end
    end

    // ── Gray-pointer CDC crossings ────────────────────────────────────────────
    // ONLY the registered gray pointer crosses domains, each through exactly
    // one cdc_2ff_sync instance. Binary pointers and the combinational
    // *_gray_d next-state values never cross the clock boundary.
    logic [PTR_W-1:0] wr_gray_sync_r;   // wr_gray_q synchronised into the READ domain
    logic [PTR_W-1:0] rd_gray_sync_w;   // rd_gray_q synchronised into the WRITE domain

    cdc_2ff_sync #(
        .WIDTH  (PTR_W),
        .STAGES (SYNC_STAGES)
    ) u_wr_ptr_to_rd (
        .clk_i   (rd_clk_i),
        .rst_n_i (rd_rst_n_i),
        .d_i     (wr_gray_q),
        .q_o     (wr_gray_sync_r)
    );

    cdc_2ff_sync #(
        .WIDTH  (PTR_W),
        .STAGES (SYNC_STAGES)
    ) u_rd_ptr_to_wr (
        .clk_i   (wr_clk_i),
        .rst_n_i (wr_rst_n_i),
        .d_i     (rd_gray_q),
        .q_o     (rd_gray_sync_w)
    );

    // ── Full / empty flags ────────────────────────────────────────────────────
    // Registered comparisons (see header for why this is one cycle "behind"
    // the raw combinational condition — that is the intended Cummings style-1
    // trade-off, not a bug).
    logic empty_q;
    logic full_q;

    always_ff @(posedge rd_clk_i or negedge rd_rst_n_i) begin
        if (!rd_rst_n_i) begin
            empty_q <= 1'b1;
        end else begin
            empty_q <= (rd_gray_d == wr_gray_sync_r);
        end
    end

    always_ff @(posedge wr_clk_i or negedge wr_rst_n_i) begin
        if (!wr_rst_n_i) begin
            full_q <= 1'b0;
        end else begin
            full_q <= (wr_gray_d == {~rd_gray_sync_w[PTR_W-1:PTR_W-2], rd_gray_sync_w[PTR_W-3:0]});
        end
    end

    // wr_ready_o is additionally gated by wr_rst_n_i itself: full_q's reset
    // value is 1'b0 ("not full"), so on its own !full_q would read 1 for the
    // entire window this domain is held in reset -- a write master could
    // then complete a handshake (wr_valid_i && wr_ready_o) whose beat is
    // silently dropped, since wr_bin_q is also held at its reset value and
    // wr_en's clocked branch never executes while !wr_rst_n_i. Gating on
    // wr_rst_n_i directly backpressures the attached master until this
    // domain's own reset has released, matching rd_valid_o's behaviour below
    // (empty_q already resets to 1'b1, so no equivalent gate is needed there
    // -- confirmed, not assumed, by inspection of the reset block above).
    assign rd_valid_o = !empty_q;
    assign wr_ready_o = wr_rst_n_i && !full_q;

    // ── Storage ───────────────────────────────────────────────────────────────
    // Flop-array memory, combinational read at rd_bin_q, no reset — see the
    // mem_q asynchronous-data-path warning in the header.
    logic [WIDTH-1:0] mem_q [DEPTH];

    always_ff @(posedge wr_clk_i) begin
        if (wr_en) begin
            mem_q[wr_bin_q[ADDR_W-1:0]] <= wr_data_i;
        end
    end

    assign rd_data_o = mem_q[rd_bin_q[ADDR_W-1:0]];

endmodule : cdc_gray_fifo
