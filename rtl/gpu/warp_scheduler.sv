// Warp scheduler: tracks N_WARPS warp states and selects the next warp
// to issue to gpu_compute_unit using round-robin.
//
// State per warp: pc[31:0], active_mask[N_LANES-1:0], busy (in-flight),
// done (VRET + empty stack), and a per-warp divergence stack.
//
// Round-robin: starting from rr_ptr, scan forward to find the first warp
// that is neither busy nor done. Issue it and advance rr_ptr.
// When all warps are done: assert kernel_done_o.

module warp_scheduler
    import gpu_pkg::*;
#(
    parameter int N_WARPS_P = N_WARPS
)(
    input  logic                    clk,
    input  logic                    rst_n,

    // -----------------------------------------------------------------------
    // Kernel launch from gpu_command_queue
    // -----------------------------------------------------------------------
    input  logic                    launch_i,         // pulse: load descriptor below
    input  logic [31:0]             kernel_pc_i,      // entry-point PC for all warps
    input  logic [N_LANES-1:0]      init_mask_i,      // initial active mask (all lanes)
    input  logic [WARP_W-1:0]       n_warps_active_i, // number of warps in this block

    // -----------------------------------------------------------------------
    // Issue port to gpu_compute_unit
    // -----------------------------------------------------------------------
    output logic                    warp_issue_o,
    output logic [WARP_W-1:0]       warp_id_o,
    output logic [31:0]             warp_pc_o,
    output logic [N_LANES-1:0]      warp_mask_o,
    input  logic                    pipe_stall_i,     // compute unit busy

    // -----------------------------------------------------------------------
    // Retirement feedback from gpu_compute_unit WB stage
    // -----------------------------------------------------------------------
    // Normal instruction retired (ALU, MEMORY, converging branch, VJMP, VSYNC)
    input  logic                    warp_retire_i,
    input  logic [WARP_W-1:0]       warp_retire_id_i,
    input  logic [31:0]             warp_next_pc_i,
    input  logic [N_LANES-1:0]      warp_next_mask_i,

    // VRET with empty divergence stack → warp truly done
    input  logic                    warp_done_i,
    input  logic [WARP_W-1:0]       warp_done_id_i,

    // Divergent branch: push false-path entry onto the warp's stack
    input  logic                    div_push_i,
    input  logic [WARP_W-1:0]       div_push_warp_i,
    input  div_entry_t              div_push_entry_i,

    // VRET with non-empty stack: pop and resume false path
    input  logic                    div_pop_i,
    input  logic [WARP_W-1:0]       div_pop_warp_i,
    input  logic [31:0]             div_pop_pc_i,
    input  logic [N_LANES-1:0]      div_pop_mask_i,

    // -----------------------------------------------------------------------
    // Divergence stack state exposed to gpu_compute_unit for its EX stage
    // -----------------------------------------------------------------------
    input  logic [WARP_W-1:0]           exec_warp_id_i,    // warp currently in EX stage
    output logic [DIV_STACK_DEPTH-1:0]  div_stack_depth_o, // depth of executing warp's stack
    output div_entry_t                   div_stack_top_o,   // top of executing warp's stack

    // -----------------------------------------------------------------------
    // GPU error (stack overflow) — reserved: future halting logic
    // -----------------------------------------------------------------------
    /* verilator lint_off UNUSEDSIGNAL */
    input  logic                    gpu_error_i,
    /* verilator lint_on UNUSEDSIGNAL */

    // -----------------------------------------------------------------------
    // Kernel completion
    // -----------------------------------------------------------------------
    output logic                    kernel_done_o
);

    // -----------------------------------------------------------------------
    // Per-warp state
    // -----------------------------------------------------------------------
    logic [31:0]             warp_pc    [N_WARPS_P-1:0];
    logic [N_LANES-1:0]      warp_mask  [N_WARPS_P-1:0];
    logic                    warp_busy  [N_WARPS_P-1:0];
    logic                    warp_done  [N_WARPS_P-1:0];

    // Per-warp divergence stack
    // depth is represented with (DIV_STACK_DEPTH) bits (values 0 to DIV_STACK_DEPTH)
    logic [DIV_STACK_DEPTH-1:0]               div_depth [N_WARPS_P-1:0];
    div_entry_t [DIV_STACK_DEPTH-1:0]         div_stack [N_WARPS_P-1:0];

    // -----------------------------------------------------------------------
    // Round-robin pointer
    // -----------------------------------------------------------------------
    logic [WARP_W-1:0] rr_ptr;

    // Number of warps in the active block (set on launch)
    logic [WARP_W-1:0] n_warps_q;

    // -----------------------------------------------------------------------
    // Round-robin warp selection — find next non-busy, non-done warp
    // -----------------------------------------------------------------------
    logic [WARP_W-1:0] next_warp;
    logic              found;

    always_comb begin
        next_warp = rr_ptr;
        found     = 1'b0;
        for (int i = 0; i < N_WARPS; i++) begin
            logic [WARP_W-1:0] cand_i;
            cand_i = WARP_W'((int'(rr_ptr) + i) % N_WARPS);
            if (!found && (cand_i < n_warps_q) &&
                !warp_busy[cand_i] && !warp_done[cand_i]) begin
                next_warp = cand_i;
                found     = 1'b1;
            end
        end
    end

    // -----------------------------------------------------------------------
    // Issue logic
    // -----------------------------------------------------------------------
    assign warp_issue_o = found && !pipe_stall_i && (n_warps_q != '0);
    assign warp_id_o    = next_warp;
    assign warp_pc_o    = warp_pc  [next_warp];
    assign warp_mask_o  = warp_mask[next_warp];

    // Divergence stack state for the warp currently in the EX stage.
    // Must use exec_warp_id_i (the warp whose VRET/branch is executing), NOT
    // next_warp (which is whatever round-robin selects next — often wrong for
    // single-warp kernels where next_warp wraps to an invalid index).
    assign div_stack_depth_o = div_depth[exec_warp_id_i];
    assign div_stack_top_o   = (div_depth[exec_warp_id_i] != '0) ?
                                div_stack[exec_warp_id_i][div_depth[exec_warp_id_i] - 1'b1] :
                                '0;

    // -----------------------------------------------------------------------
    // State update sequencer
    // -----------------------------------------------------------------------
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            rr_ptr    <= '0;
            n_warps_q <= '0;
            for (int w = 0; w < N_WARPS; w++) begin
                warp_pc  [w] <= '0;
                warp_mask[w] <= '0;
                warp_busy[w] <= 1'b0;
                warp_done[w] <= 1'b0;
                div_depth[w] <= '0;
            end
        end else begin

            // ---------------------------------------------------------------
            // Kernel launch: initialise all warps
            // ---------------------------------------------------------------
            if (launch_i) begin
                n_warps_q <= n_warps_active_i;
                rr_ptr    <= '0;
                for (int w = 0; w < N_WARPS; w++) begin
                    warp_pc  [w] <= kernel_pc_i;
                    warp_mask[w] <= init_mask_i;
                    warp_busy[w] <= 1'b0;
                    warp_done[w] <= 1'b0;
                    div_depth[w] <= '0;
                end
            end

            // ---------------------------------------------------------------
            // Issue: mark selected warp as busy, advance rr_ptr
            // ---------------------------------------------------------------
            if (warp_issue_o) begin
                warp_busy[next_warp] <= 1'b1;
                rr_ptr               <= WARP_W'((int'(next_warp) + 1) % N_WARPS);
            end

            // ---------------------------------------------------------------
            // Normal retirement: update PC and mask, mark warp ready
            // ---------------------------------------------------------------
            if (warp_retire_i) begin
                warp_pc  [warp_retire_id_i] <= warp_next_pc_i;
                warp_mask[warp_retire_id_i] <= warp_next_mask_i;
                warp_busy[warp_retire_id_i] <= 1'b0;
            end

            // ---------------------------------------------------------------
            // Warp done (VRET + empty stack)
            // ---------------------------------------------------------------
            if (warp_done_i) begin
                warp_busy[warp_done_id_i] <= 1'b0;
                warp_done[warp_done_id_i] <= 1'b1;
            end

            // ---------------------------------------------------------------
            // Divergence push: stack entry for false path
            // ---------------------------------------------------------------
            if (div_push_i) begin
                div_stack[div_push_warp_i][div_depth[div_push_warp_i]] <= div_push_entry_i;
                div_depth[div_push_warp_i] <= div_depth[div_push_warp_i] + 1'b1;
                // PC+mask update comes via warp_retire_i (fired simultaneously)
            end

            // ---------------------------------------------------------------
            // Divergence pop: resume false path
            // ---------------------------------------------------------------
            if (div_pop_i) begin
                warp_pc  [div_pop_warp_i] <= div_pop_pc_i;
                warp_mask[div_pop_warp_i] <= div_pop_mask_i;
                warp_busy[div_pop_warp_i] <= 1'b0;
                div_depth[div_pop_warp_i] <= div_depth[div_pop_warp_i] - 1'b1;
            end

        end
    end

    // -----------------------------------------------------------------------
    // Kernel done: all active warps have completed
    // -----------------------------------------------------------------------
    logic all_done;
    always_comb begin
        all_done = (n_warps_q != '0);
        for (int w = 0; w < N_WARPS; w++) begin
            if (WARP_W'(unsigned'(w)) < WARP_W'(unsigned'(n_warps_q)) && !warp_done[w])
                all_done = 1'b0;
        end
    end

    assign kernel_done_o = all_done;

endmodule

