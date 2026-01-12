// RV32I Control Unit - Generates control signals and handles branching
module rv32i_control
    import rv32i_pkg::*;
(
    input  logic             clk,
    input  logic             rst_n,

    // Instruction and decoded signals
    input  logic [ILEN-1:0]  instr,
    input  ctrl_signals_t    ctrl,
    input  logic             illegal_instr,

    // ALU flags for branch decisions
    input  logic             alu_zero,
    input  logic             alu_negative,
    input  logic [XLEN-1:0]  alu_result,

    // Memory interface status
    input  logic             mem_ready,
    input  logic             mem_valid,

    // Debug interface
    input  logic             dbg_halt_req,
    input  logic             dbg_resume_req,
    input  logic             dbg_step_req,
    input  logic             bp_hit,

    // Control outputs
    output cpu_state_e       cpu_state,
    output logic             pc_we,
    output logic             pc_sel_branch,
    output logic             pc_sel_jump,
    output logic             instr_valid,
    output logic             stall,
    output logic             halted,
    output halt_cause_e      halt_cause,

    // Memory transaction control
    output logic             mem_req,
    output logic             mem_we
);

    // State register
    cpu_state_e state_q, state_d;

    // Halt cause register
    halt_cause_e halt_cause_q, halt_cause_d;

    // Branch evaluation
    logic branch_taken;
    logic [2:0] funct3;

    assign funct3 = instr[14:12];

    // Evaluate branch condition
    always_comb begin
        branch_taken = 1'b0;

        if (ctrl.branch) begin
            case (funct3)
                BR_BEQ:  branch_taken = alu_zero;
                BR_BNE:  branch_taken = !alu_zero;
                BR_BLT:  branch_taken = alu_result[0];  // SLT result
                BR_BGE:  branch_taken = !alu_result[0]; // !SLT result
                BR_BLTU: branch_taken = alu_result[0];  // SLTU result
                BR_BGEU: branch_taken = !alu_result[0]; // !SLTU result
                default: branch_taken = 1'b0;
            endcase
        end
    end

    // Check for EBREAK instruction
    logic is_ebreak;
    assign is_ebreak = (instr[6:0] == OP_SYSTEM) &&
                       (instr[31:7] == 25'b0000000000010000000000000);

    // State machine
    always_comb begin
        state_d      = state_q;
        halt_cause_d = halt_cause_q;
        pc_we        = 1'b0;
        pc_sel_branch= 1'b0;
        pc_sel_jump  = 1'b0;
        instr_valid  = 1'b0;
        stall        = 1'b0;
        halted       = 1'b0;
        mem_req      = 1'b0;
        mem_we       = 1'b0;

        case (state_q)
            CPU_RESET: begin
                state_d = CPU_FETCH;
            end

            CPU_FETCH: begin
                // Check for halt request or breakpoint
                if (dbg_halt_req) begin
                    state_d = CPU_HALTED;
                    halt_cause_d = HALT_REQUEST;
                end else if (bp_hit) begin
                    state_d = CPU_HALTED;
                    halt_cause_d = HALT_BREAKPOINT;
                end else begin
                    // Request instruction fetch via AXI
                    mem_req = 1'b1;
                    mem_we  = 1'b0;
                    if (mem_valid) begin
                        state_d = CPU_DECODE;
                    end else begin
                        stall = 1'b1;
                    end
                end
            end

            CPU_DECODE: begin
                instr_valid = 1'b1;

                // Check for EBREAK
                if (is_ebreak) begin
                    state_d = CPU_HALTED;
                    halt_cause_d = HALT_EBREAK;
                end else begin
                    state_d = CPU_EXECUTE;
                end
            end

            CPU_EXECUTE: begin
                instr_valid = 1'b1;

                if (ctrl.mem_read || ctrl.mem_write) begin
                    // Memory operation needed
                    state_d = CPU_MEM_WAIT;
                end else begin
                    // No memory operation, go to writeback
                    state_d = CPU_WRITEBACK;
                end
            end

            CPU_MEM_WAIT: begin
                instr_valid = 1'b1;
                mem_req = 1'b1;
                mem_we  = ctrl.mem_write;

                if (mem_valid) begin
                    state_d = CPU_WRITEBACK;
                end else begin
                    stall = 1'b1;
                end
            end

            CPU_WRITEBACK: begin
                instr_valid = 1'b1;

                // Update PC
                pc_we = 1'b1;

                if (ctrl.jump) begin
                    pc_sel_jump = 1'b1;
                end else if (ctrl.branch && branch_taken) begin
                    pc_sel_branch = 1'b1;
                end
                // else: PC = PC + 4

                // Check for single-step mode
                if (dbg_step_req) begin
                    state_d = CPU_HALTED;
                    halt_cause_d = HALT_STEP;
                end else begin
                    state_d = CPU_FETCH;
                end
            end

            CPU_HALTED: begin
                halted = 1'b1;

                if (dbg_resume_req) begin
                    state_d = CPU_FETCH;
                    halt_cause_d = HALT_NONE;
                end else if (dbg_step_req) begin
                    state_d = CPU_STEP;
                end
            end

            CPU_STEP: begin
                // Execute one instruction then halt
                // Transition to fetch, step_req remains active
                state_d = CPU_FETCH;
            end

            default: begin
                state_d = CPU_RESET;
            end
        endcase
    end

    // State register
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state_q      <= CPU_RESET;
            halt_cause_q <= HALT_NONE;
        end else begin
            state_q      <= state_d;
            halt_cause_q <= halt_cause_d;
        end
    end

    // Output assignments
    assign cpu_state  = state_q;
    assign halt_cause = halt_cause_q;

endmodule
