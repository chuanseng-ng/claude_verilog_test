// GPU compute unit: 4-stage FETCH → DECODE → EXECUTE → WRITEBACK pipeline.
//
// One warp issues per cycle. The warp_scheduler presents (warp_id, pc,
// active_mask) on the FETCH input. The pipeline stalls on memory ops and
// VSYNC; VRET signals warp completion back to the scheduler.
//
// Divergence stack (per warp, DIV_STACK_DEPTH entries):
//   On a divergent branch the true-path mask is set and (return_pc,
//   false-path mask) is pushed. On VRET with a non-empty stack the
//   false path is popped and re-issued; on VRET with an empty stack
//   the warp is marked done. Stack overflow sets gpu_error_o.
//
// Memory ops (VLD/VST) stall the pipeline via mem_stall_i from
// gpu_memory_unit. Instruction fetch stalls via axi_r* handshake.
//
// NOTE: Human review required before merge (divergence algorithm,
//       memory stall interaction, reconverge logic).
`default_nettype none

module gpu_compute_unit
    import gpu_pkg::*;
(
    input  logic                        clk,
    input  logic                        rst_n,

    // -----------------------------------------------------------------------
    // Warp scheduler interface
    // -----------------------------------------------------------------------
    input  logic                        warp_issue_i,
    input  logic [WARP_W-1:0]          warp_id_i,
    input  logic [31:0]                 warp_pc_i,
    input  logic [N_LANES-1:0]         warp_mask_i,

    output logic                        pipe_stall_o,

    // Warp retirement — PC + mask update for scheduler after each instruction
    output logic                        warp_retire_o,
    output logic [WARP_W-1:0]          warp_retire_id_o,
    output logic [31:0]                 warp_next_pc_o,
    output logic [N_LANES-1:0]         warp_next_mask_o,

    // Completion signals
    output logic                        warp_done_o,
    output logic [WARP_W-1:0]          warp_done_id_o,

    // Divergence push (branch with split mask)
    output logic                        div_push_o,
    output logic [WARP_W-1:0]          div_push_warp_o,
    output div_entry_t                  div_push_entry_o,

    // Divergence pop / reconverge (false-path re-issue after VRET)
    output logic                        div_pop_o,
    output logic [WARP_W-1:0]          div_pop_warp_o,
    output logic [31:0]                 div_pop_pc_o,
    output logic [N_LANES-1:0]         div_pop_mask_o,

    // Currently-executing warp ID (for scheduler div-stack lookup)
    output logic [WARP_W-1:0]          exec_warp_id_o,

    // Error output (stack overflow)
    output logic                        gpu_error_o,

    // -----------------------------------------------------------------------
    // AXI4-Lite master — instruction fetch (read-only)
    // -----------------------------------------------------------------------
    output logic [31:0]                 if_araddr_o,
    output logic                        if_arvalid_o,
    input  logic                        if_arready_i,
    input  logic [31:0]                 if_rdata_i,
    /* verilator lint_off UNUSEDSIGNAL */
    input  logic [1:0]                  if_rresp_i,     // reserved: AXI error check
    /* verilator lint_on UNUSEDSIGNAL */
    input  logic                        if_rvalid_i,
    output logic                        if_rready_o,

    // -----------------------------------------------------------------------
    // Memory unit interface (VLD / VST)
    // -----------------------------------------------------------------------
    output logic                        mem_req_o,
    output logic                        mem_we_o,
    output logic [N_LANES-1:0][31:0]   mem_addr_o,
    output logic [N_LANES-1:0][31:0]   mem_wdata_o,
    output logic [N_LANES-1:0]         mem_lane_mask_o,
    input  logic                        mem_stall_i,
    input  logic [N_LANES-1:0][31:0]   mem_rdata_i,
    input  logic                        mem_rvalid_i,

    // -----------------------------------------------------------------------
    // Shared memory interface (separate path, no AXI)
    // -----------------------------------------------------------------------
    output logic                        shmem_req_o,
    output logic                        shmem_we_o,
    output logic [N_LANES-1:0][SHMEM_W-1:0] shmem_addr_o,
    output logic [N_LANES-1:0][31:0]   shmem_wdata_o,
    output logic [N_LANES-1:0]         shmem_lane_mask_o,
    input  logic                        shmem_stall_i,
    input  logic [N_LANES-1:0][31:0]   shmem_rdata_i,
    input  logic                        shmem_rvalid_i,

    // -----------------------------------------------------------------------
    // Per-warp divergence stack state (held externally in warp_scheduler)
    // -----------------------------------------------------------------------
    input  logic [DIV_STACK_DEPTH-1:0] div_stack_depth_i,
    input  div_entry_t                  div_stack_top_i
);

    // -----------------------------------------------------------------------
    // Pipeline registers (FETCH → DECODE → EXECUTE → WRITEBACK)
    // -----------------------------------------------------------------------

    // IF/ID pipeline register
    typedef struct packed {
        logic        valid;
        logic [WARP_W-1:0] warp_id;
        logic [31:0] pc;
        logic [31:0] instr;
        logic [N_LANES-1:0] active_mask;
    } if_id_t;

    // ID/EX pipeline register
    typedef struct packed {
        logic        valid;
        logic [WARP_W-1:0] warp_id;
        logic [31:0] pc;
        logic [N_LANES-1:0] active_mask;
        gpu_opcode_t opcode;
        instr_class_t iclass;
        logic [4:0]  rd;
        logic [11:0] imm;
        logic [N_LANES-1:0][31:0] rs1_data;
        logic [N_LANES-1:0][31:0] rs2_data;
        logic [31:0] branch_target;   // pc + sign_extend(imm)
        logic [31:0] jump_target;     // pc + sign_extend(imm) (same encoding for Phase 4)
    } id_ex_t;

    // EX/WB pipeline register
    typedef struct packed {
        logic        valid;
        logic [WARP_W-1:0] warp_id;
        logic [N_LANES-1:0] active_mask;
        logic [4:0]  rd;
        logic [N_LANES-1:0][31:0] result;
        logic        wr_en;
        logic        warp_done;
        logic        div_pop;
        logic        div_push;
        div_entry_t  div_entry;
        logic [31:0] next_pc;         // resolved next PC for this warp
        logic [N_LANES-1:0] next_mask; // resolved next active mask
    } ex_wb_t;

    if_id_t if_id_q;
    id_ex_t id_ex_q;
    ex_wb_t ex_wb_q;

    // -----------------------------------------------------------------------
    // Stall logic
    // -----------------------------------------------------------------------
    logic fetch_stall;
    logic mem_busy;
    logic pipe_stall;

    // instr_rdy_q: latches rvalid across mem-stall cycles so we don't
    // deadlock when rvalid pulses once but pipe_stall prevents advance.
    logic instr_rdy_q;
    logic instr_avail;

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n)           instr_rdy_q <= 1'b0;
        else if (if_rvalid_i) instr_rdy_q <= 1'b1;
        else if (!pipe_stall) instr_rdy_q <= 1'b0;
    end

    // instr_rdy_q is set one cycle after rvalid — pipeline advances only when
    // if_id_q.instr already holds the captured instruction (removes combinational
    // AXI rdata→decode timing path; same-cycle bypass was the critical-path limiter).
    assign instr_avail  = instr_rdy_q;
    assign fetch_stall  = if_id_q.valid && !instr_avail;
    // mem_busy: stall while the coalescer is in-flight (mem_stall_i high).
    // Do NOT gate on id_ex_q.iclass: when VST is in EX/WB and the next
    // instruction (e.g. VRET) is already in EX, id_ex_q.iclass is no longer
    // IC_MEMORY, so the old check would drop mem_busy one cycle early — letting
    // VRET fire warp_done before the write completes (lane-4 write-miss bug).
    assign mem_busy     = mem_stall_i;
    // shmem_rvalid_i holds the pipe one extra cycle so a VLDS parked in WB is
    // not advanced the same cycle its read data becomes valid. shared_memory
    // drops sh_stall_o (=|pending_q) the cycle pending clears, but rdata_q is
    // only valid that cycle and sh_rvalid_o pulses then — without this term the
    // WB-advance would overwrite ex_wb_q before the captured result is written
    // back (mirrors the VLD capture-then-advance ordering of gpu_memory_unit).
    assign pipe_stall   = fetch_stall || mem_busy || shmem_stall_i || shmem_rvalid_i;
    assign pipe_stall_o = pipe_stall || if_id_q.valid;

    // -----------------------------------------------------------------------
    // Register file wires
    // -----------------------------------------------------------------------
    logic [WARP_W-1:0]          rf_rda_warp, rf_rdb_warp;
    logic [REG_W-1:0]           rf_rda_reg,  rf_rdb_reg;
    logic [N_LANES-1:0][31:0]   rf_rda_data, rf_rdb_data;

    logic [WARP_W-1:0]          rf_wr_warp;
    logic [REG_W-1:0]           rf_wr_reg;
    logic                        rf_wr_en;
    logic [N_LANES-1:0]         rf_wr_mask;
    logic [N_LANES-1:0][31:0]   rf_wr_data;

    vector_register_file u_regfile (
        .clk          (clk),
        .rst_n        (rst_n),
        .rda_warp_i   (rf_rda_warp),
        .rda_reg_i    (rf_rda_reg),
        .rda_data_o   (rf_rda_data),
        .rdb_warp_i   (rf_rdb_warp),
        .rdb_reg_i    (rf_rdb_reg),
        .rdb_data_o   (rf_rdb_data),
        .wr_en_i      (rf_wr_en),
        .wr_mask_i    (rf_wr_mask),
        .wr_warp_i    (rf_wr_warp),
        .wr_reg_i     (rf_wr_reg),
        .wr_data_i    (rf_wr_data)
    );

    // -----------------------------------------------------------------------
    // FETCH stage
    // -----------------------------------------------------------------------
    assign if_araddr_o  = warp_pc_i;
    assign if_arvalid_o = warp_issue_i && !pipe_stall_o;
    assign if_rready_o  = 1'b1;

    // Single always_ff for if_id_q — instruction word captured separately from control fields.
    // rdata can arrive while the stage is stalled; new warp issue sets the other fields.
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            if_id_q <= '0;
        end else begin
            if (if_rvalid_i && if_rready_o)
                if_id_q.instr <= if_rdata_i;
            if (!pipe_stall) begin
                if (warp_issue_i && if_arready_i) begin
                    if_id_q.valid       <= 1'b1;
                    if_id_q.warp_id     <= warp_id_i;
                    if_id_q.pc          <= warp_pc_i;
                    if_id_q.active_mask <= warp_mask_i;
                end else begin
                    if_id_q.valid <= 1'b0;
                end
            end
        end
    end

    // -----------------------------------------------------------------------
    // DECODE stage — combinational
    // -----------------------------------------------------------------------
    logic [6:0]  dec_opcode;
    logic [4:0]  dec_rd, dec_rs1, dec_rs2;
    logic [11:0] dec_imm;
    instr_class_t dec_class;
    gpu_opcode_t  dec_op;

    /* verilator lint_off UNUSEDSIGNAL */
    logic [31:0] dec_instr;  // funct3 bits[14:12] reserved for future sub-opcode use
    /* verilator lint_on UNUSEDSIGNAL */
    // Always read the registered instruction. instr_avail (instr_rdy_q) ensures
    // the pipeline only advances after if_id_q.instr has been captured from rdata.
    assign dec_instr  = if_id_q.instr;

    assign dec_opcode = dec_instr[6:0];
    assign dec_rd     = dec_instr[11:7];
    assign dec_rs1    = dec_instr[19:15];
    assign dec_rs2    = dec_instr[24:20];
    assign dec_imm    = dec_instr[31:20];
    assign dec_op     = gpu_opcode_t'(dec_opcode);

    always_comb begin
        dec_class = IC_INVALID;
        unique case (dec_op)
            VADD, VSUB, VMUL, VAND, VOR, VXOR,
            VSLL, VSRL, VSRA,
            VADDI, VANDI, VORI, VXORI: dec_class = IC_ALU;
            VLD, VST:                   dec_class = IC_MEMORY;
            VLDS, VSTS:                 dec_class = IC_SHMEM;
            VBEQ, VBNE, VBLT, VBGE:    dec_class = IC_BRANCH;
            VJMP:                       dec_class = IC_VJMP;
            VRET:                       dec_class = IC_VRET;
            VMOV_TID_X, VMOV_TID_Y, VMOV_TID_Z,
            VMOV_BID_X, VMOV_BID_Y, VMOV_BID_Z: dec_class = IC_SPECIAL;
            VSYNC:                      dec_class = IC_VSYNC;
            default:                    dec_class = IC_INVALID;
        endcase
    end

    // Register file read address wiring
    assign rf_rda_warp = if_id_q.warp_id;
    assign rf_rda_reg  = dec_rs1;
    assign rf_rdb_warp = if_id_q.warp_id;
    assign rf_rdb_reg  = dec_rs2;

    logic [31:0] dec_branch_target, dec_jump_target;
    assign dec_branch_target = if_id_q.pc + {{20{dec_imm[11]}}, dec_imm};
    assign dec_jump_target   = if_id_q.pc + {{20{dec_imm[11]}}, dec_imm};

    // ID → EX register
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            id_ex_q <= '0;
        end else if (!pipe_stall) begin
            if (if_id_q.valid && instr_avail) begin
                id_ex_q.valid         <= 1'b1;
                id_ex_q.warp_id       <= if_id_q.warp_id;
                id_ex_q.pc            <= if_id_q.pc;
                id_ex_q.active_mask   <= if_id_q.active_mask;
                id_ex_q.opcode        <= dec_op;
                id_ex_q.iclass        <= dec_class;
                id_ex_q.rd            <= dec_rd;
                id_ex_q.imm           <= dec_imm;
                id_ex_q.rs1_data      <= rf_rda_data;
                id_ex_q.rs2_data      <= rf_rdb_data;
                id_ex_q.branch_target <= dec_branch_target;
                id_ex_q.jump_target   <= dec_jump_target;
            end else begin
                id_ex_q.valid <= 1'b0;
            end
        end
    end

    // -----------------------------------------------------------------------
    // EXECUTE stage
    // -----------------------------------------------------------------------
    logic [N_LANES-1:0][31:0] alu_result;
    logic [N_LANES-1:0]       branch_taken;

    vector_alu u_alu (
        .opcode_i      (id_ex_q.opcode),
        .funct3_i      (3'b0),
        .funct7_i      (7'b0),
        .rs1_i         (id_ex_q.rs1_data),
        .rs2_i         (id_ex_q.rs2_data),
        .imm_i         (id_ex_q.imm),
        .active_mask_i (id_ex_q.active_mask),
        .result_o      (alu_result),
        .branch_taken_o(branch_taken)
    );

    // VMOV: tid/bid per-lane values
    logic [N_LANES-1:0][31:0] special_result;
    always_comb begin
        special_result = '0;
        for (int l = 0; l < N_LANES; l++) begin
            case (id_ex_q.opcode)
                VMOV_TID_X: special_result[l] = 32'(l);
                VMOV_BID_X: special_result[l] = 32'(unsigned'(id_ex_q.warp_id));
                default:    special_result[l] = '0;
            endcase
        end
    end

    // Divergence detection: branch where some lanes take and others don't
    logic [N_LANES-1:0] mask_taken, mask_not_taken;
    logic               is_divergent;
    always_comb begin
        mask_taken     = id_ex_q.active_mask & branch_taken;
        mask_not_taken = id_ex_q.active_mask & ~branch_taken;
        is_divergent   = (mask_taken != '0) && (mask_not_taken != '0);
    end

    // Memory interface — address generation for VLD/VST (global) and VLDS/VSTS (shared)
    logic is_mem_op, is_shmem_op;
    assign is_mem_op   = id_ex_q.valid && (id_ex_q.iclass == IC_MEMORY);
    assign is_shmem_op = id_ex_q.valid && (id_ex_q.iclass == IC_SHMEM);

    always_comb begin
        logic [31:0] shmem_byte_addr;
        // Global memory path (VLD/VST) — mutually exclusive with shared path
        mem_req_o       = is_mem_op && !mem_busy;
        mem_we_o        = (id_ex_q.opcode == VST);
        mem_lane_mask_o = id_ex_q.active_mask;
        for (int l = 0; l < N_LANES; l++) begin
            mem_addr_o[l]  = id_ex_q.rs1_data[l] + {{20{id_ex_q.imm[11]}}, id_ex_q.imm};
            mem_wdata_o[l] = id_ex_q.rs2_data[l];
        end
        // Shared memory path (VLDS/VSTS) — mutually exclusive with global path
        shmem_req_o       = is_shmem_op && !shmem_stall_i;
        shmem_we_o        = (id_ex_q.opcode == VSTS);
        shmem_lane_mask_o = id_ex_q.active_mask;
        shmem_byte_addr   = '0;
        for (int l = 0; l < N_LANES; l++) begin
            shmem_byte_addr  = id_ex_q.rs1_data[l] + {{20{id_ex_q.imm[11]}}, id_ex_q.imm};
            shmem_addr_o[l]  = shmem_byte_addr[SHMEM_W-1:0];
            shmem_wdata_o[l] = id_ex_q.rs2_data[l];
        end
    end

    // EX → WB register
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            ex_wb_q     <= '0;
            gpu_error_o <= 1'b0;
        end else begin
            // VLD result arrives while pipe_stall=1 (memory still busy); capture
            // it here so that WB sees correct data when the stall clears next cycle.
            if (mem_rvalid_i && ex_wb_q.valid && ex_wb_q.wr_en)
                ex_wb_q.result <= mem_rdata_i;
            // VLDS result: shared memory rvalid pulse — capture read data into WB result.
            if (shmem_rvalid_i && ex_wb_q.valid && ex_wb_q.wr_en)
                ex_wb_q.result <= shmem_rdata_i;

            if (!pipe_stall) begin
            ex_wb_q.valid       <= id_ex_q.valid;
            ex_wb_q.warp_id     <= id_ex_q.warp_id;
            ex_wb_q.active_mask <= id_ex_q.active_mask;
            ex_wb_q.rd          <= id_ex_q.rd;
            ex_wb_q.wr_en       <= 1'b0;
            ex_wb_q.warp_done   <= 1'b0;
            ex_wb_q.div_pop     <= 1'b0;
            ex_wb_q.div_push    <= 1'b0;
            ex_wb_q.div_entry   <= '0;
            ex_wb_q.result      <= '0;
            ex_wb_q.next_pc     <= id_ex_q.pc + 32'd4;      // default: sequential advance
            ex_wb_q.next_mask   <= id_ex_q.active_mask;     // default: mask unchanged

            if (id_ex_q.valid) begin
                unique case (id_ex_q.iclass)
                    IC_ALU: begin
                        ex_wb_q.result <= alu_result;
                        ex_wb_q.wr_en  <= 1'b1;
                    end

                    IC_SPECIAL: begin
                        ex_wb_q.result <= special_result;
                        ex_wb_q.wr_en  <= 1'b1;
                    end

                    IC_MEMORY: begin
                        // VLD: result from memory unit (captured once mem_stall_i drops)
                        ex_wb_q.wr_en  <= (id_ex_q.opcode == VLD);
                        ex_wb_q.result <= mem_rdata_i;
                    end

                    IC_SHMEM: begin
                        // VLDS: result from shared memory (captured via shmem_rvalid_i pulse)
                        // VSTS: no writeback
                        ex_wb_q.wr_en  <= (id_ex_q.opcode == VLDS);
                        ex_wb_q.result <= shmem_rdata_i;
                    end

                    IC_BRANCH: begin
                        if (is_divergent) begin
                            if (div_stack_depth_i == DIV_STACK_DEPTH[DIV_STACK_DEPTH-1:0]) begin
                                gpu_error_o <= 1'b1; // stack overflow
                            end else begin
                                ex_wb_q.div_push              <= 1'b1;
                                ex_wb_q.div_entry.return_pc   <= id_ex_q.pc + 32'd4;
                                ex_wb_q.div_entry.return_mask <= mask_not_taken;
                                ex_wb_q.active_mask           <= mask_taken;
                                ex_wb_q.next_pc               <= id_ex_q.branch_target;
                                ex_wb_q.next_mask             <= mask_taken;
                            end
                        end else begin
                            // Converging: all lanes agree — taken or not taken
                            ex_wb_q.next_pc <= (mask_taken != '0) ?
                                               id_ex_q.branch_target : id_ex_q.pc + 32'd4;
                        end
                    end

                    IC_VJMP: begin
                        ex_wb_q.next_pc <= id_ex_q.jump_target;
                    end

                    IC_VRET: begin
                        if (div_stack_depth_i != '0) begin
                            ex_wb_q.div_pop <= 1'b1;
                        end else begin
                            ex_wb_q.warp_done <= 1'b1;
                        end
                    end

                    IC_VSYNC: begin
                        // Intra-warp VSYNC: Phase 4 passes immediately (single CU)
                    end

                    default: ; // IC_INVALID
                endcase
            end
        end
        end // else
    end

    // -----------------------------------------------------------------------
    // WRITEBACK stage
    // -----------------------------------------------------------------------
    assign rf_wr_en   = ex_wb_q.valid && ex_wb_q.wr_en;
    assign rf_wr_warp = ex_wb_q.warp_id;
    assign rf_wr_reg  = ex_wb_q.rd;
    assign rf_wr_mask = ex_wb_q.active_mask;
    assign rf_wr_data = ex_wb_q.result;

    // Retirement events must be SINGLE-CYCLE pulses, fired only when the WB
    // instruction actually advances out of the stage (!pipe_stall). Without the
    // !pipe_stall gate, an instruction parked in WB during a memory stall holds
    // warp_retire_o high for the whole stall, repeatedly clearing warp_busy in
    // the scheduler — which lets the next instruction (e.g. VRET) be issued
    // twice and fire warp_done prematurely (divergence lane-4 store dropped).
    logic wb_retire;
    assign wb_retire = ex_wb_q.valid && !pipe_stall;

    // Normal instruction retirement: update scheduler with new PC and mask.
    // warp_done and div_pop are handled by their own dedicated outputs below.
    assign warp_retire_o      = wb_retire && !ex_wb_q.warp_done && !ex_wb_q.div_pop;
    assign warp_retire_id_o   = ex_wb_q.warp_id;
    assign warp_next_pc_o     = ex_wb_q.next_pc;
    assign warp_next_mask_o   = ex_wb_q.next_mask;

    assign warp_done_o    = wb_retire && ex_wb_q.warp_done;
    assign warp_done_id_o = ex_wb_q.warp_id;

    assign div_push_o       = wb_retire && ex_wb_q.div_push;
    assign div_push_warp_o  = ex_wb_q.warp_id;
    assign div_push_entry_o = ex_wb_q.div_entry;

    assign div_pop_o      = wb_retire && ex_wb_q.div_pop;
    assign div_pop_warp_o = ex_wb_q.warp_id;
    assign div_pop_pc_o   = div_stack_top_i.return_pc;
    assign div_pop_mask_o = div_stack_top_i.return_mask;

    assign exec_warp_id_o = id_ex_q.warp_id;

endmodule

`default_nettype wire
