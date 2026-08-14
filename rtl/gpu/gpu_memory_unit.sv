// GPU memory unit: bridges the compute unit VLD/VST interface and the
// memory_coalescer.  Stalls the compute pipeline (stall_o) from the first
// cycle a request is latched until the coalescer signals done.
//
// stall_o is registered (depends only on busy_q, not req_i) to avoid a
// combinational path back through the compute unit's mem_busy logic.
// The first cycle of a request (coal_start pulse) the pipeline is not yet
// stalled; that is safe because the compute unit's pipe_stall causes the
// result to be captured from rdata_o only when stall_o drops, not one
// cycle earlier.

module gpu_memory_unit
    import gpu_pkg::*;
#(
    parameter logic GPU_ENABLE_COALESCE = 1'b0
)(
    input  logic clk,
    input  logic rst_n,

    // -----------------------------------------------------------------------
    // Compute unit interface (matches gpu_compute_unit port names)
    // -----------------------------------------------------------------------
    input  logic                          req_i,
    input  logic                          we_i,
    input  logic [N_LANES-1:0][31:0]      addr_i,
    input  logic [N_LANES-1:0][31:0]      wdata_i,
    input  logic [N_LANES-1:0]            lane_mask_i,

    output logic                          stall_o,
    output logic [N_LANES-1:0][31:0]      rdata_o,
    output logic                          rvalid_o,   // coincides with stall_o falling

    // -----------------------------------------------------------------------
    // AXI4 master — pass-through to memory_coalescer
    // -----------------------------------------------------------------------
    output logic [31:0]  m_araddr_o,
    output logic         m_arvalid_o,
    input  logic         m_arready_i,
    input  logic [31:0]  m_rdata_i,
    input  logic [1:0]   m_rresp_i,
    input  logic         m_rvalid_i,
    output logic         m_rready_o,
    output logic [31:0]  m_awaddr_o,
    output logic         m_awvalid_o,
    input  logic         m_awready_i,
    output logic [31:0]  m_wdata_o,
    output logic [3:0]   m_wstrb_o,
    output logic         m_wvalid_o,
    input  logic         m_wready_i,
    input  logic [1:0]   m_bresp_i,
    input  logic         m_bvalid_i,
    output logic         m_bready_o
);

    logic coal_start, coal_done;
    logic busy_q;
    logic [N_LANES-1:0][31:0] coal_rdata;

    // Start coalescer on the first active cycle of each request
    assign coal_start = req_i && !busy_q;
    // Stall is registered — zero combinational fan-back into compute unit
    assign stall_o    = busy_q;
    assign rdata_o    = coal_rdata;
    assign rvalid_o   = coal_done;

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n)          busy_q <= 1'b0;
        else if (coal_start) busy_q <= 1'b1;
        else if (coal_done)  busy_q <= 1'b0;
    end

    memory_coalescer #(
        .GPU_ENABLE_COALESCE (GPU_ENABLE_COALESCE)
    ) u_coal (
        .clk         (clk),
        .rst_n       (rst_n),
        .start_i     (coal_start),
        .we_i        (we_i),
        .addr_i      (addr_i),
        .wdata_i     (wdata_i),
        .mask_i      (lane_mask_i),
        .done_o      (coal_done),
        .rdata_o     (coal_rdata),
        .m_araddr_o  (m_araddr_o),
        .m_arvalid_o (m_arvalid_o),
        .m_arready_i (m_arready_i),
        .m_rdata_i   (m_rdata_i),
        .m_rresp_i   (m_rresp_i),
        .m_rvalid_i  (m_rvalid_i),
        .m_rready_o  (m_rready_o),
        .m_awaddr_o  (m_awaddr_o),
        .m_awvalid_o (m_awvalid_o),
        .m_awready_i (m_awready_i),
        .m_wdata_o   (m_wdata_o),
        .m_wstrb_o   (m_wstrb_o),
        .m_wvalid_o  (m_wvalid_o),
        .m_wready_i  (m_wready_i),
        .m_bresp_i   (m_bresp_i),
        .m_bvalid_i  (m_bvalid_i),
        .m_bready_o  (m_bready_o)
    );

endmodule

