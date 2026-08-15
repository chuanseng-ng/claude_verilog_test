// GPU command queue: 1-deep descriptor FIFO between AXI4-Lite register bank
// (in gpu_top) and the warp_scheduler.
//
// On launch_i pulse: latch the kernel descriptor and assert desc_valid_o.
// New launches while busy_o are silently dropped (gpu_top guards with idle check).
// On desc_ack_i: clear valid so a new descriptor can be accepted.

module gpu_command_queue
    import gpu_pkg::*;
(
    input  logic           clk,
    input  logic           rst_n,

    // -----------------------------------------------------------------------
    // Write side: from AXI4-Lite register bank in gpu_top
    // -----------------------------------------------------------------------
    input  logic           launch_i,       // W1S pulse — latch descriptor below
    input  logic [31:0]    kernel_pc_i,
    input  logic [15:0]    grid_x_i,
    input  logic [15:0]    grid_y_i,
    input  logic [15:0]    grid_z_i,
    input  logic [9:0]     block_x_i,
    input  logic [9:0]     block_y_i,
    input  logic [9:0]     block_z_i,
    input  logic [31:0]    arg_ptr_i,
    input  logic           irq_enable_i,   // GPU_CTRL[2] — registered in gpu_top

    // -----------------------------------------------------------------------
    // Status
    // -----------------------------------------------------------------------
    output logic           busy_o,         // 1 while descriptor pending

    // -----------------------------------------------------------------------
    // Read side: to warp_scheduler
    // -----------------------------------------------------------------------
    output logic           desc_valid_o,
    output kernel_desc_t   desc_o,
    input  logic           desc_ack_i,     // warp_scheduler accepted descriptor

    // -----------------------------------------------------------------------
    // IRQ enable forwarded to gpu_top IRQ logic
    // -----------------------------------------------------------------------
    output logic           irq_enable_o
);

    logic        valid_q;
    kernel_desc_t desc_q;

    assign desc_valid_o = valid_q;
    assign desc_o       = desc_q;
    assign busy_o       = valid_q;
    assign irq_enable_o = irq_enable_i;   // persistent CTRL bit — no latching needed

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            valid_q <= 1'b0;
            desc_q  <= '0;
        end else begin
            if (desc_ack_i)
                valid_q <= 1'b0;
            if (launch_i && !valid_q) begin
                valid_q          <= 1'b1;
                desc_q.kernel_pc <= kernel_pc_i;
                desc_q.grid_x    <= grid_x_i;
                desc_q.grid_y    <= grid_y_i;
                desc_q.grid_z    <= grid_z_i;
                desc_q.block_x   <= block_x_i;
                desc_q.block_y   <= block_y_i;
                desc_q.block_z   <= block_z_i;
                desc_q.arg_ptr   <= arg_ptr_i;
            end
        end
    end

endmodule

