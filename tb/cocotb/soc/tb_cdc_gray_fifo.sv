// tb_cdc_gray_fifo.sv
// Bead claude_verilog_test-3snb -- standalone testbench wrapper for cdc_gray_fifo's
// DEPTH=2 variant, with DEPTH=4 as the control.
//
// Two DUT instances share the two clocks and the two (per-domain) resets but have
// independent data/valid/ready faces:
//   u_d2  DEPTH=2  the new minimal multi-bit pointer-synchroniser variant
//   u_d4  DEPTH=4  control -- the smallest depth the module supported before 3snb
//
// Gray-crossing monitors
// ----------------------
// The one property that makes a multi-bit pointer crossing safe is that the bus
// handed to the synchroniser changes by AT MOST ONE BIT per source-clock edge. A
// simulator without per-bit skew cannot show a binary-pointer crossing failing, so
// the property is checked structurally instead: each monitor samples the d_i of
// the two pointer synchronisers (hierarchical reference) every source-clock edge
// and latches a sticky flag if more than one bit moved between consecutive edges.
//   *_gray_viol_o   sticky, cleared only by mon_rst_n_i (NOT by the DUT resets, so a
//                   violation cannot be hidden by a later DUT reset).
// Edges at which the source domain is in reset, or was in reset on the previous
// edge, are skipped: asserting reset legitimately drives the pointer to zero in one
// step.
//
// Not claimed: this does not model metastability or per-bit skew, only the
// invariant that makes skew harmless.

module tb_cdc_gray_fifo (
    input  logic        wr_clk_i,
    input  logic        rd_clk_i,
    input  logic        wr_rst_n_i,
    input  logic        rd_rst_n_i,
    input  logic        mon_rst_n_i,

    // ── DEPTH = 2 ────────────────────────────────────────────────────────────
    input  logic [15:0] d2_wr_data_i,
    input  logic        d2_wr_valid_i,
    output logic        d2_wr_ready_o,
    output logic [15:0] d2_rd_data_o,
    output logic        d2_rd_valid_o,
    input  logic        d2_rd_ready_i,
    output logic        d2_wr2rd_gray_viol_o,
    output logic        d2_rd2wr_gray_viol_o,

    // ── DEPTH = 4 (control) ──────────────────────────────────────────────────
    input  logic [15:0] d4_wr_data_i,
    input  logic        d4_wr_valid_i,
    output logic        d4_wr_ready_o,
    output logic [15:0] d4_rd_data_o,
    output logic        d4_rd_valid_o,
    input  logic        d4_rd_ready_i,
    output logic        d4_wr2rd_gray_viol_o,
    output logic        d4_rd2wr_gray_viol_o
);

    cdc_gray_fifo #(
        .WIDTH       (16),
        .DEPTH       (2),
        .SYNC_STAGES (2)
    ) u_d2 (
        .wr_clk_i   (wr_clk_i),
        .wr_rst_n_i (wr_rst_n_i),
        .wr_data_i  (d2_wr_data_i),
        .wr_valid_i (d2_wr_valid_i),
        .wr_ready_o (d2_wr_ready_o),
        .rd_clk_i   (rd_clk_i),
        .rd_rst_n_i (rd_rst_n_i),
        .rd_data_o  (d2_rd_data_o),
        .rd_valid_o (d2_rd_valid_o),
        .rd_ready_i (d2_rd_ready_i)
    );

    cdc_gray_fifo #(
        .WIDTH       (16),
        .DEPTH       (4),
        .SYNC_STAGES (2)
    ) u_d4 (
        .wr_clk_i   (wr_clk_i),
        .wr_rst_n_i (wr_rst_n_i),
        .wr_data_i  (d4_wr_data_i),
        .wr_valid_i (d4_wr_valid_i),
        .wr_ready_o (d4_wr_ready_o),
        .rd_clk_i   (rd_clk_i),
        .rd_rst_n_i (rd_rst_n_i),
        .rd_data_o  (d4_rd_data_o),
        .rd_valid_o (d4_rd_valid_o),
        .rd_ready_i (d4_rd_ready_i)
    );

    // ── Gray-crossing monitors ───────────────────────────────────────────────
    // d2: pointer width is $clog2(2)+1 = 2; d4: 3.
    logic [1:0] d2_w2r_cur, d2_w2r_prev;
    logic [1:0] d2_r2w_cur, d2_r2w_prev;
    logic [2:0] d4_w2r_cur, d4_w2r_prev;
    logic [2:0] d4_r2w_cur, d4_r2w_prev;
    logic       d2_w2r_ok, d2_r2w_ok, d4_w2r_ok, d4_r2w_ok;

    assign d2_w2r_cur = u_d2.u_wr_ptr_to_rd.d_i;
    assign d2_r2w_cur = u_d2.u_rd_ptr_to_wr.d_i;
    assign d4_w2r_cur = u_d4.u_wr_ptr_to_rd.d_i;
    assign d4_r2w_cur = u_d4.u_rd_ptr_to_wr.d_i;

    // "Out of reset for at least one full edge" qualifiers: cleared asynchronously by the
    // domain's own reset, set one source-clock edge after release. Using the reset only
    // asynchronously keeps the wrapper free of SYNCASYNCNET.
    always_ff @(posedge wr_clk_i or negedge wr_rst_n_i) begin
        if (!wr_rst_n_i) begin
            d2_w2r_ok <= 1'b0;
            d4_w2r_ok <= 1'b0;
        end else begin
            d2_w2r_ok <= 1'b1;
            d4_w2r_ok <= 1'b1;
        end
    end

    always_ff @(posedge rd_clk_i or negedge rd_rst_n_i) begin
        if (!rd_rst_n_i) begin
            d2_r2w_ok <= 1'b0;
            d4_r2w_ok <= 1'b0;
        end else begin
            d2_r2w_ok <= 1'b1;
            d4_r2w_ok <= 1'b1;
        end
    end

    // Write-domain-launched pointer (crosses wr -> rd), sampled on wr_clk_i.
    always_ff @(posedge wr_clk_i or negedge mon_rst_n_i) begin
        if (!mon_rst_n_i) begin
            d2_w2r_prev          <= '0;
            d4_w2r_prev          <= '0;
            d2_wr2rd_gray_viol_o <= 1'b0;
            d4_wr2rd_gray_viol_o <= 1'b0;
        end else begin
            d2_w2r_prev <= d2_w2r_cur;
            d4_w2r_prev <= d4_w2r_cur;
            if (d2_w2r_ok && ($countones(d2_w2r_cur ^ d2_w2r_prev) > 1)) begin
                d2_wr2rd_gray_viol_o <= 1'b1;
            end
            if (d4_w2r_ok && ($countones(d4_w2r_cur ^ d4_w2r_prev) > 1)) begin
                d4_wr2rd_gray_viol_o <= 1'b1;
            end
        end
    end

    // Read-domain-launched pointer (crosses rd -> wr), sampled on rd_clk_i.
    always_ff @(posedge rd_clk_i or negedge mon_rst_n_i) begin
        if (!mon_rst_n_i) begin
            d2_r2w_prev          <= '0;
            d4_r2w_prev          <= '0;
            d2_rd2wr_gray_viol_o <= 1'b0;
            d4_rd2wr_gray_viol_o <= 1'b0;
        end else begin
            d2_r2w_prev <= d2_r2w_cur;
            d4_r2w_prev <= d4_r2w_cur;
            if (d2_r2w_ok && ($countones(d2_r2w_cur ^ d2_r2w_prev) > 1)) begin
                d2_rd2wr_gray_viol_o <= 1'b1;
            end
            if (d4_r2w_ok && ($countones(d4_r2w_cur ^ d4_r2w_prev) > 1)) begin
                d4_rd2wr_gray_viol_o <= 1'b1;
            end
        end
    end

endmodule : tb_cdc_gray_fifo
