// GPU top: AXI4-Lite control slave + instruction-fetch AXI4-Lite master +
// data AXI4 master.  Wires gpu_command_queue, warp_scheduler,
// gpu_compute_unit, gpu_memory_unit, and shared_memory.
//
// AXI4-Lite slave register map (12-bit byte offset within 4 KiB):
//   0x000 GPU_CTRL      [0]=launch W1S  [1]=reset W1S  [2]=irq_enable
//   0x004 GPU_STATUS    [0]=idle [1]=done [2]=error  (RO)
//   0x008 GPU_KERNEL_PC
//   0x00C GPU_GRID_X    [15:0]
//   0x010 GPU_GRID_Y    [15:0]
//   0x014 GPU_GRID_Z    [15:0]
//   0x018 GPU_BLOCK_X   [9:0]
//   0x01C GPU_BLOCK_Y   [9:0]
//   0x020 GPU_BLOCK_Z   [9:0]
//   0x024 GPU_ARG_PTR
//   0x028 GPU_IRQ_CLR   [0]=W1C
//   0x030–0x06C GPU_PERFCNT[0..15]  (RO)
`default_nettype none

module gpu_top
    import gpu_pkg::*;
#(
    /* verilator lint_off UNUSEDPARAM */
    parameter logic GPU_ENABLE_COALESCE = 1'b0
    /* verilator lint_on UNUSEDPARAM */
)(
    input  logic clk,
    input  logic rst_n,

    // -------------------------------------------------------------------
    // AXI4-Lite slave — CPU control (12-bit byte offset within 4 KiB)
    // -------------------------------------------------------------------
    input  logic [11:0] s_axil_awaddr,
    input  logic        s_axil_awvalid,
    output logic        s_axil_awready,
    input  logic [31:0] s_axil_wdata,
    /* verilator lint_off UNUSEDSIGNAL */
    input  logic [3:0]  s_axil_wstrb,
    /* verilator lint_on UNUSEDSIGNAL */
    input  logic        s_axil_wvalid,
    output logic        s_axil_wready,
    output logic [1:0]  s_axil_bresp,
    output logic        s_axil_bvalid,
    input  logic        s_axil_bready,
    input  logic [11:0] s_axil_araddr,
    input  logic        s_axil_arvalid,
    output logic        s_axil_arready,
    output logic [31:0] s_axil_rdata,
    output logic [1:0]  s_axil_rresp,
    output logic        s_axil_rvalid,
    input  logic        s_axil_rready,

    // -------------------------------------------------------------------
    // AXI4-Lite master — instruction fetch (pass-through from compute unit)
    // -------------------------------------------------------------------
    output logic [31:0] m_axil_if_araddr,
    output logic        m_axil_if_arvalid,
    input  logic        m_axil_if_arready,
    input  logic [31:0] m_axil_if_rdata,
    input  logic [1:0]  m_axil_if_rresp,
    input  logic        m_axil_if_rvalid,
    output logic        m_axil_if_rready,

    // -------------------------------------------------------------------
    // AXI4 master — data memory (pass-through from memory_coalescer)
    // -------------------------------------------------------------------
    output logic [31:0] m_axi_araddr,
    output logic        m_axi_arvalid,
    input  logic        m_axi_arready,
    input  logic [31:0] m_axi_rdata,
    /* verilator lint_off UNUSEDSIGNAL */
    input  logic [1:0]  m_axi_rresp,
    /* verilator lint_on UNUSEDSIGNAL */
    input  logic        m_axi_rvalid,
    output logic        m_axi_rready,
    output logic [31:0] m_axi_awaddr,
    output logic        m_axi_awvalid,
    input  logic        m_axi_awready,
    output logic [31:0] m_axi_wdata,
    output logic [3:0]  m_axi_wstrb,
    output logic        m_axi_wvalid,
    input  logic        m_axi_wready,
    /* verilator lint_off UNUSEDSIGNAL */
    input  logic [1:0]  m_axi_bresp,
    /* verilator lint_on UNUSEDSIGNAL */
    input  logic        m_axi_bvalid,
    output logic        m_axi_bready,

    // -------------------------------------------------------------------
    // IRQ
    // -------------------------------------------------------------------
    output logic        gpu_irq_o
);

    // -------------------------------------------------------------------
    // AXI4-Lite slave write channel
    // -------------------------------------------------------------------
    logic        aw_cap_q;
    logic [11:0] aw_addr_q;
    logic        bvalid_q;

    // Writable control registers
    logic [31:0] r_kernel_pc_q;
    logic [15:0] r_grid_x_q, r_grid_y_q, r_grid_z_q;
    logic [9:0]  r_block_x_q, r_block_y_q, r_block_z_q;
    logic [31:0] r_arg_ptr_q;
    logic        r_irq_en_q;

    // One-cycle command pulses from write decode
    logic ctrl_launch_q, ctrl_reset_q, irq_clr_q;

    assign s_axil_awready = ~aw_cap_q;
    assign s_axil_wready  = aw_cap_q;
    assign s_axil_bresp   = 2'b00;
    assign s_axil_bvalid  = bvalid_q;

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            aw_cap_q       <= 1'b0;
            aw_addr_q      <= '0;
            bvalid_q       <= 1'b0;
            ctrl_launch_q  <= 1'b0;
            ctrl_reset_q   <= 1'b0;
            irq_clr_q      <= 1'b0;
            r_kernel_pc_q  <= '0;
            r_grid_x_q     <= '0; r_grid_y_q <= '0; r_grid_z_q <= '0;
            r_block_x_q    <= '0; r_block_y_q <= '0; r_block_z_q <= '0;
            r_arg_ptr_q    <= '0;
            r_irq_en_q     <= 1'b0;
        end else begin
            ctrl_launch_q  <= 1'b0;
            ctrl_reset_q   <= 1'b0;
            irq_clr_q      <= 1'b0;
            if (s_axil_awvalid && ~aw_cap_q) begin
                aw_cap_q  <= 1'b1;
                aw_addr_q <= s_axil_awaddr;
            end
            if (aw_cap_q && s_axil_wvalid) begin
                aw_cap_q <= 1'b0;
                bvalid_q <= 1'b1;
                case (aw_addr_q)
                    12'h000: begin
                        if (s_axil_wdata[0]) ctrl_launch_q <= 1'b1;
                        if (s_axil_wdata[1]) ctrl_reset_q  <= 1'b1;
                        r_irq_en_q <= s_axil_wdata[2];
                    end
                    12'h008: r_kernel_pc_q <= s_axil_wdata;
                    12'h00C: r_grid_x_q    <= s_axil_wdata[15:0];
                    12'h010: r_grid_y_q    <= s_axil_wdata[15:0];
                    12'h014: r_grid_z_q    <= s_axil_wdata[15:0];
                    12'h018: r_block_x_q   <= s_axil_wdata[9:0];
                    12'h01C: r_block_y_q   <= s_axil_wdata[9:0];
                    12'h020: r_block_z_q   <= s_axil_wdata[9:0];
                    12'h024: r_arg_ptr_q   <= s_axil_wdata;
                    12'h028: irq_clr_q     <= s_axil_wdata[0];
                    default: ;
                endcase
            end
            if (bvalid_q && s_axil_bready) bvalid_q <= 1'b0;
        end
    end

    // -------------------------------------------------------------------
    // AXI4-Lite slave read channel
    // -------------------------------------------------------------------
    logic        ar_cap_q;
    logic [11:0] ar_addr_q;

    assign s_axil_arready = ~ar_cap_q;
    assign s_axil_rvalid  = ar_cap_q;
    assign s_axil_rresp   = 2'b00;

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            ar_cap_q  <= 1'b0;
            ar_addr_q <= '0;
        end else begin
            if (s_axil_arvalid && ~ar_cap_q) begin
                ar_cap_q  <= 1'b1;
                ar_addr_q <= s_axil_araddr;
            end
            if (ar_cap_q && s_axil_rready) ar_cap_q <= 1'b0;
        end
    end

    // -------------------------------------------------------------------
    // GPU FSM + IRQ latch + performance counters
    // -------------------------------------------------------------------
    gpu_state_t  state_q;
    logic        irq_latch_q;
    logic [31:0] perf_cnt_q [16];

    // Command queue outputs
    logic        cq_desc_valid;
    /* verilator lint_off UNUSEDSIGNAL */
    kernel_desc_t cq_desc;  // grid_x/y/z, block_y/z, arg_ptr unused in Phase 4
    /* verilator lint_on UNUSEDSIGNAL */
    logic        cq_irq_en;          // pass-through of r_irq_en_q

    // Warp scheduler outputs
    logic                     sched_issue;
    logic [WARP_W-1:0]        sched_warp_id;
    logic [31:0]              sched_warp_pc;
    logic [N_LANES-1:0]       sched_warp_mask;
    logic                     sched_kernel_done;
    logic [DIV_STACK_DEPTH-1:0] sched_div_depth;
    div_entry_t               sched_div_top;

    // Compute unit outputs
    logic                     cu_pipe_stall;
    logic                     cu_retire;
    logic [WARP_W-1:0]        cu_retire_id;
    logic [31:0]              cu_retire_pc;
    logic [N_LANES-1:0]       cu_retire_mask;
    logic                     cu_done;
    logic [WARP_W-1:0]        cu_done_id;
    logic                     cu_div_push;
    logic [WARP_W-1:0]        cu_div_push_warp;
    div_entry_t               cu_div_push_entry;
    logic                     cu_div_pop;
    logic [WARP_W-1:0]        cu_div_pop_warp;
    logic [31:0]              cu_div_pop_pc;
    logic [N_LANES-1:0]       cu_div_pop_mask;
    logic                     cu_gpu_error;

    // Compute unit → memory unit
    logic                     cu_mem_req, cu_mem_we;
    logic [N_LANES-1:0][31:0] cu_mem_addr, cu_mem_wdata;
    logic [N_LANES-1:0]       cu_mem_lane_mask;
    logic                     mu_stall;
    logic [N_LANES-1:0][31:0] mu_rdata;
    logic                     mu_rvalid;
    logic [WARP_W-1:0]        cu_exec_warp_id;

    // Compute unit → shared memory
    logic                              cu_shmem_req, cu_shmem_we;
    logic [N_LANES-1:0][SHMEM_W-1:0]  cu_shmem_addr;
    logic [N_LANES-1:0][31:0]         cu_shmem_wdata;
    logic [N_LANES-1:0]               cu_shmem_mask;
    logic                              sm_stall;
    logic [N_LANES-1:0][31:0]         sm_rdata;
    logic                              sm_rvalid;

    // sched_launch: 1-cycle pulse when IDLE and descriptor ready
    logic sched_launch;
    assign sched_launch = (state_q == GPS_IDLE) && cq_desc_valid;

    // n_warps: ceil(block_x / N_LANES), capped at N_WARPS-1
    logic [WARP_W-1:0] n_warps_w;
    logic [9:0]        n_warps_raw;
    assign n_warps_raw = {3'b0, cq_desc.block_x[9:3]} + {9'b0, |cq_desc.block_x[2:0]};
    assign n_warps_w   = |n_warps_raw[9:WARP_W] ? WARP_W'(N_WARPS-1) : n_warps_raw[WARP_W-1:0];

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state_q     <= GPS_IDLE;
            irq_latch_q <= 1'b0;
        end else begin
            case (state_q)
                GPS_IDLE:
                    if (sched_launch) state_q <= GPS_RUNNING;
                GPS_RUNNING:
                    if      (cu_gpu_error)        state_q <= GPS_ERROR;
                    else if (sched_kernel_done)   state_q <= GPS_DONE;
                GPS_DONE:
                    if (ctrl_reset_q || ctrl_launch_q) state_q <= GPS_IDLE;
                GPS_ERROR:
                    if (ctrl_reset_q) state_q <= GPS_IDLE;
                default: state_q <= GPS_IDLE;
            endcase
            if ((state_q == GPS_RUNNING) && sched_kernel_done) irq_latch_q <= 1'b1;
            if (irq_clr_q || ctrl_reset_q || sched_launch)     irq_latch_q <= 1'b0;
        end
    end

    assign gpu_irq_o = irq_latch_q && cq_irq_en;

    // -------------------------------------------------------------------
    // Performance counters (reset on new kernel launch)
    // -------------------------------------------------------------------
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            for (int i = 0; i < 16; i++) perf_cnt_q[i] <= '0;
        end else if (sched_launch) begin
            for (int i = 0; i < 16; i++) perf_cnt_q[i] <= '0;
        end else begin
            if (state_q == GPS_RUNNING)                           perf_cnt_q[0] <= perf_cnt_q[0] + 1;
            if (cu_retire)                                         perf_cnt_q[1] <= perf_cnt_q[1] + 1;
            if (sched_issue)                                       perf_cnt_q[2] <= perf_cnt_q[2] + 1;
            if (cu_div_push)                                       perf_cnt_q[3] <= perf_cnt_q[3] + 1;
            if ((m_axi_arvalid && m_axi_arready) ||
                (m_axi_awvalid && m_axi_awready))                 perf_cnt_q[5] <= perf_cnt_q[5] + 1;
        end
    end

    // -------------------------------------------------------------------
    // Read data mux
    // -------------------------------------------------------------------
    always_comb begin
        s_axil_rdata = 32'h0;
        case (ar_addr_q)
            12'h000: s_axil_rdata = {29'h0, r_irq_en_q, 2'b00};
            12'h004: s_axil_rdata = {29'h0,
                                      (state_q == GPS_ERROR),
                                      (state_q == GPS_DONE),
                                      (state_q == GPS_IDLE)};
            12'h008: s_axil_rdata = r_kernel_pc_q;
            12'h00C: s_axil_rdata = {16'h0, r_grid_x_q};
            12'h010: s_axil_rdata = {16'h0, r_grid_y_q};
            12'h014: s_axil_rdata = {16'h0, r_grid_z_q};
            12'h018: s_axil_rdata = {22'h0, r_block_x_q};
            12'h01C: s_axil_rdata = {22'h0, r_block_y_q};
            12'h020: s_axil_rdata = {22'h0, r_block_z_q};
            12'h024: s_axil_rdata = r_arg_ptr_q;
            12'h028: s_axil_rdata = {31'h0, irq_latch_q};
            12'h030: s_axil_rdata = perf_cnt_q[0];
            12'h034: s_axil_rdata = perf_cnt_q[1];
            12'h038: s_axil_rdata = perf_cnt_q[2];
            12'h03C: s_axil_rdata = perf_cnt_q[3];
            12'h040: s_axil_rdata = perf_cnt_q[4];
            12'h044: s_axil_rdata = perf_cnt_q[5];
            12'h048: s_axil_rdata = perf_cnt_q[6];
            12'h04C: s_axil_rdata = perf_cnt_q[7];
            12'h050: s_axil_rdata = perf_cnt_q[8];
            12'h054: s_axil_rdata = perf_cnt_q[9];
            12'h058: s_axil_rdata = perf_cnt_q[10];
            12'h05C: s_axil_rdata = perf_cnt_q[11];
            12'h060: s_axil_rdata = perf_cnt_q[12];
            12'h064: s_axil_rdata = perf_cnt_q[13];
            12'h068: s_axil_rdata = perf_cnt_q[14];
            12'h06C: s_axil_rdata = perf_cnt_q[15];
            default: s_axil_rdata = 32'h0;
        endcase
    end

    // -------------------------------------------------------------------
    // Shared memory active/we drive
    // -------------------------------------------------------------------
    logic [N_LANES-1:0] sm_active, sm_we;
    assign sm_active = cu_shmem_mask & {N_LANES{cu_shmem_req}};
    assign sm_we     = {N_LANES{cu_shmem_we}} & cu_shmem_mask & {N_LANES{cu_shmem_req}};

    // -------------------------------------------------------------------
    // gpu_command_queue
    // -------------------------------------------------------------------
    gpu_command_queue u_cq (
        .clk         (clk),
        .rst_n       (rst_n),
        .launch_i    (ctrl_launch_q),
        .kernel_pc_i (r_kernel_pc_q),
        .grid_x_i    (r_grid_x_q),
        .grid_y_i    (r_grid_y_q),
        .grid_z_i    (r_grid_z_q),
        .block_x_i   (r_block_x_q),
        .block_y_i   (r_block_y_q),
        .block_z_i   (r_block_z_q),
        .arg_ptr_i   (r_arg_ptr_q),
        .irq_enable_i(r_irq_en_q),
        /* verilator lint_off PINCONNECTEMPTY */
        .busy_o      (),                // gpu_top uses state_q for arbitration
        /* verilator lint_on PINCONNECTEMPTY */
        .desc_valid_o(cq_desc_valid),
        .desc_o      (cq_desc),
        .desc_ack_i  (sched_launch),
        .irq_enable_o(cq_irq_en)
    );

    // -------------------------------------------------------------------
    // warp_scheduler
    // -------------------------------------------------------------------
    warp_scheduler u_sched (
        .clk              (clk),
        .rst_n            (rst_n),
        .launch_i         (sched_launch),
        .kernel_pc_i      (cq_desc.kernel_pc),
        .init_mask_i      ({N_LANES{1'b1}}),
        .n_warps_active_i (n_warps_w),
        .warp_issue_o     (sched_issue),
        .warp_id_o        (sched_warp_id),
        .warp_pc_o        (sched_warp_pc),
        .warp_mask_o      (sched_warp_mask),
        .pipe_stall_i     (cu_pipe_stall),
        .warp_retire_i    (cu_retire),
        .warp_retire_id_i (cu_retire_id),
        .warp_next_pc_i   (cu_retire_pc),
        .warp_next_mask_i (cu_retire_mask),
        .warp_done_i      (cu_done),
        .warp_done_id_i   (cu_done_id),
        .div_push_i       (cu_div_push),
        .div_push_warp_i  (cu_div_push_warp),
        .div_push_entry_i (cu_div_push_entry),
        .div_pop_i        (cu_div_pop),
        .div_pop_warp_i   (cu_div_pop_warp),
        .div_pop_pc_i     (cu_div_pop_pc),
        .div_pop_mask_i   (cu_div_pop_mask),
        .exec_warp_id_i   (cu_exec_warp_id),
        .div_stack_depth_o(sched_div_depth),
        .div_stack_top_o  (sched_div_top),
        .gpu_error_i      (cu_gpu_error),
        .kernel_done_o    (sched_kernel_done)
    );

    // -------------------------------------------------------------------
    // gpu_compute_unit
    // -------------------------------------------------------------------
    gpu_compute_unit u_cu (
        .clk              (clk),
        .rst_n            (rst_n),
        .warp_issue_i     (sched_issue),
        .warp_id_i        (sched_warp_id),
        .warp_pc_i        (sched_warp_pc),
        .warp_mask_i      (sched_warp_mask),
        .pipe_stall_o     (cu_pipe_stall),
        .warp_retire_o    (cu_retire),
        .warp_retire_id_o (cu_retire_id),
        .warp_next_pc_o   (cu_retire_pc),
        .warp_next_mask_o (cu_retire_mask),
        .warp_done_o      (cu_done),
        .warp_done_id_o   (cu_done_id),
        .div_push_o       (cu_div_push),
        .div_push_warp_o  (cu_div_push_warp),
        .div_push_entry_o (cu_div_push_entry),
        .div_pop_o        (cu_div_pop),
        .div_pop_warp_o   (cu_div_pop_warp),
        .div_pop_pc_o     (cu_div_pop_pc),
        .div_pop_mask_o   (cu_div_pop_mask),
        .exec_warp_id_o   (cu_exec_warp_id),
        .gpu_error_o      (cu_gpu_error),
        .if_araddr_o      (m_axil_if_araddr),
        .if_arvalid_o     (m_axil_if_arvalid),
        .if_arready_i     (m_axil_if_arready),
        .if_rdata_i       (m_axil_if_rdata),
        .if_rresp_i       (m_axil_if_rresp),
        .if_rvalid_i      (m_axil_if_rvalid),
        .if_rready_o      (m_axil_if_rready),
        .mem_req_o        (cu_mem_req),
        .mem_we_o         (cu_mem_we),
        .mem_addr_o       (cu_mem_addr),
        .mem_wdata_o      (cu_mem_wdata),
        .mem_lane_mask_o  (cu_mem_lane_mask),
        .mem_stall_i      (mu_stall),
        .mem_rdata_i      (mu_rdata),
        .mem_rvalid_i     (mu_rvalid),
        .shmem_req_o      (cu_shmem_req),
        .shmem_we_o       (cu_shmem_we),
        .shmem_addr_o     (cu_shmem_addr),
        .shmem_wdata_o    (cu_shmem_wdata),
        .shmem_lane_mask_o(cu_shmem_mask),
        .shmem_stall_i    (sm_stall),
        .shmem_rdata_i    (sm_rdata),
        .shmem_rvalid_i   (sm_rvalid),
        .div_stack_depth_i(sched_div_depth),
        .div_stack_top_i  (sched_div_top)
    );

    // -------------------------------------------------------------------
    // gpu_memory_unit
    // -------------------------------------------------------------------
    gpu_memory_unit #(
        .GPU_ENABLE_COALESCE (GPU_ENABLE_COALESCE)
    ) u_mu (
        .clk          (clk),
        .rst_n        (rst_n),
        .req_i        (cu_mem_req),
        .we_i         (cu_mem_we),
        .addr_i       (cu_mem_addr),
        .wdata_i      (cu_mem_wdata),
        .lane_mask_i  (cu_mem_lane_mask),
        .stall_o      (mu_stall),
        .rdata_o      (mu_rdata),
        .rvalid_o     (mu_rvalid),
        .m_araddr_o   (m_axi_araddr),
        .m_arvalid_o  (m_axi_arvalid),
        .m_arready_i  (m_axi_arready),
        .m_rdata_i    (m_axi_rdata),
        .m_rresp_i    (m_axi_rresp),
        .m_rvalid_i   (m_axi_rvalid),
        .m_rready_o   (m_axi_rready),
        .m_awaddr_o   (m_axi_awaddr),
        .m_awvalid_o  (m_axi_awvalid),
        .m_awready_i  (m_axi_awready),
        .m_wdata_o    (m_axi_wdata),
        .m_wstrb_o    (m_axi_wstrb),
        .m_wvalid_o   (m_axi_wvalid),
        .m_wready_i   (m_axi_wready),
        .m_bresp_i    (m_axi_bresp),
        .m_bvalid_i   (m_axi_bvalid),
        .m_bready_o   (m_axi_bready)
    );

    // -------------------------------------------------------------------
    // shared_memory
    // -------------------------------------------------------------------
    shared_memory u_sm (
        .clk          (clk),
        .rst_n        (rst_n),
        .sh_addr_i    (cu_shmem_addr),
        .sh_we_i      (sm_we),
        .sh_wdata_i   (cu_shmem_wdata),
        .sh_active_i  (sm_active),
        .sh_rdata_o   (sm_rdata),
        .sh_stall_o   (sm_stall),
        .sh_rvalid_o  (sm_rvalid)
    );

endmodule

`default_nettype wire
