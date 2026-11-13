// cdc_gray_fifo - dual-clock gray-pointer FIFO with ready/valid on both faces.
//
// Function: Each side keeps a binary pointer in its own clock domain. Only the registered gray pointer crosses.
//   It crosses through one cdc_sync instance per direction. The flags full_q and empty_q are registered.
//   Storage is a flop array. mem_q is written on wr_clk_i. It is read in the rd_clk_i domain without a reset.
//   wr_ready_o and rd_valid_o come from local flags. No other combinational path crosses the clocks.
// Parameters:
//   WIDTH        Payload width in bits.
//   DEPTH        Number of entries. It must be a power of two and at least 2.
//   SYNC_STAGES  Stages of both pointer synchronisers. It must be at least 2.
// Clocks and resets: wr_clk_i and rd_clk_i are the two clocks. wr_rst_n_i and rd_rst_n_i are active low.
//   Each asserts asynchronously and deasserts synchronously. Each is expected to be already synchronised to its own clock.
//   While wr_rst_n_i is low, wr_ready_o is low.
// Caller rules:
//   - mem_q is an asynchronous data path. STA must set set_max_delay -datapath_only on the mem_q read path.
//     The bound is at most one receiving clock period.
//   - STA must set the same constraint on both gray-pointer crossings, u_wr_ptr_to_rd and u_rd_ptr_to_wr.
// Doc: ds:mod:cdc-gray-fifo, tm:mod:cdc-gray-fifo

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

    // DEPTH must be a power of two and at least 2. The $fatal runs at elaboration, outside an `initial` block.
    if ((DEPTH < 2) || ((DEPTH & (DEPTH - 1)) != 0)) begin : g_depth_check
        $fatal(1, "cdc_gray_fifo: DEPTH (%0d) must be a power of two and >= 2", DEPTH);
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
    // one cdc_sync instance. Binary pointers and the combinational
    // *_gray_d next-state values never cross the clock boundary.
    logic [PTR_W-1:0] wr_gray_sync_r;   // wr_gray_q synchronised into the READ domain
    logic [PTR_W-1:0] rd_gray_sync_w;   // rd_gray_q synchronised into the WRITE domain

    cdc_sync #(
        .WIDTH  (PTR_W),
        .STAGES (SYNC_STAGES)
    ) u_wr_ptr_to_rd (
        .clk_i   (rd_clk_i),
        .rst_n_i (rd_rst_n_i),
        .d_i     (wr_gray_q),
        .q_o     (wr_gray_sync_r)
    );

    cdc_sync #(
        .WIDTH  (PTR_W),
        .STAGES (SYNC_STAGES)
    ) u_rd_ptr_to_wr (
        .clk_i   (wr_clk_i),
        .rst_n_i (wr_rst_n_i),
        .d_i     (rd_gray_q),
        .q_o     (rd_gray_sync_w)
    );

    // ── Full / empty flags ────────────────────────────────────────────────────
    // Registered comparisons (see ds:mod:cdc-gray-fifo for why this is one cycle "behind"
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

    // Gray value the next write pointer must equal for the FIFO to be full
    // (see tm:mod:cdc-gray-fifo). Only the compare operand is
    // generate-selected, so the flop below is identical for every DEPTH.
    logic [PTR_W-1:0] full_cmp_w;

    if (DEPTH == 2) begin : g_full_cmp_d2
        // 2-bit gray pointer: "invert the top two bits" is the whole pointer.
        assign full_cmp_w = ~rd_gray_sync_w;
    end else begin : g_full_cmp_dge4
        // DEPTH >= 4 (PTR_W >= 3): original expression, unchanged.
        assign full_cmp_w = {~rd_gray_sync_w[PTR_W-1:PTR_W-2], rd_gray_sync_w[PTR_W-3:0]};
    end

    always_ff @(posedge wr_clk_i or negedge wr_rst_n_i) begin
        if (!wr_rst_n_i) begin
            full_q <= 1'b0;
        end else begin
            full_q <= (wr_gray_d == full_cmp_w);
        end
    end

    // wr_ready_o also requires wr_rst_n_i. The reset value of full_q is 0, so !full_q alone would accept a beat during reset.
    assign rd_valid_o = !empty_q;
    assign wr_ready_o = wr_rst_n_i && !full_q;

    // ── Storage ───────────────────────────────────────────────────────────────
    // Flop-array memory, combinational read at rd_bin_q, no reset — see the
    // mem_q asynchronous-data-path warning. See ds:mod:cdc-gray-fifo.
    logic [WIDTH-1:0] mem_q [DEPTH];

    always_ff @(posedge wr_clk_i) begin
        if (wr_en) begin
            mem_q[wr_bin_q[ADDR_W-1:0]] <= wr_data_i;
        end
    end

    assign rd_data_o = mem_q[rd_bin_q[ADDR_W-1:0]];

endmodule : cdc_gray_fifo
