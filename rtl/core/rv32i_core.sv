// RV32I Core - Integrates all core components (fetch, decode, execute, writeback)
module rv32i_core
    import rv32i_pkg::*;
(
    input  logic             clk,
    input  logic             rst_n,

    // Memory interface (directly exposed, AXI wrapper is external)
    output logic [XLEN-1:0]  mem_addr,
    output logic [XLEN-1:0]  mem_wdata,
    output logic [3:0]       mem_wstrb,
    input  logic [XLEN-1:0]  mem_rdata,
    output logic             mem_req,
    output logic             mem_we,
    input  logic             mem_ready,
    input  logic             mem_valid,

    // Debug interface
    input  logic             dbg_halt_req,
    input  logic             dbg_resume_req,
    input  logic             dbg_step_req,
    input  logic             dbg_pc_we,
    input  logic [XLEN-1:0]  dbg_pc_wdata,
    output logic [XLEN-1:0]  dbg_pc_rdata,
    output logic [ILEN-1:0]  dbg_instr,
    output logic             dbg_halted,
    output halt_cause_e      dbg_halt_cause,

    // Debug register file access
    input  logic [REG_ADDR_WIDTH-1:0] dbg_reg_addr,
    input  logic [XLEN-1:0]           dbg_reg_wdata,
    input  logic                      dbg_reg_we,
    output logic [XLEN-1:0]           dbg_reg_rdata,

    // Breakpoint inputs
    input  logic             bp_hit
);

    // =========================================================================
    // Internal signals
    // =========================================================================

    // Program Counter
    logic [XLEN-1:0] pc_q, pc_d;
    logic [XLEN-1:0] pc_plus4;

    // Instruction register
    logic [ILEN-1:0] instr_q, instr_d;

    // Decoded signals
    logic [REG_ADDR_WIDTH-1:0] rs1_addr, rs2_addr, rd_addr;
    logic [6:0]                opcode;
    logic [2:0]                funct3;
    logic [6:0]                funct7;
    ctrl_signals_t             ctrl;
    logic                      illegal_instr;

    // Register file signals
    logic [XLEN-1:0] rs1_data, rs2_data;
    logic [XLEN-1:0] rd_data;
    logic            rd_we;

    // Immediate
    logic [XLEN-1:0] imm;

    // ALU signals
    logic [XLEN-1:0] alu_operand_a, alu_operand_b;
    logic [XLEN-1:0] alu_result;
    logic            alu_zero, alu_negative, alu_carry, alu_overflow;

    // Control signals
    cpu_state_e      cpu_state;
    logic            pc_we;
    logic            pc_sel_branch, pc_sel_jump;
    logic            instr_valid;
    logic            stall;
    logic            halted;
    halt_cause_e     halt_cause;
    logic            ctrl_mem_req, ctrl_mem_we;

    // Memory access signals
    logic [XLEN-1:0] load_data;
    logic            is_fetch;

    // =========================================================================
    // Program Counter
    // =========================================================================
    assign pc_plus4 = pc_q + 32'd4;

    // PC next value logic
    always_comb begin
        pc_d = pc_q;

        if (dbg_pc_we && halted) begin
            // Debug write to PC (only when halted)
            pc_d = dbg_pc_wdata;
        end else if (pc_we) begin
            if (pc_sel_jump) begin
                // JAL/JALR: PC = ALU result (with bit 0 cleared for JALR)
                pc_d = {alu_result[XLEN-1:1], 1'b0};
            end else if (pc_sel_branch) begin
                // Branch: PC = PC + imm
                pc_d = pc_q + imm;
            end else begin
                // Default: PC = PC + 4
                pc_d = pc_plus4;
            end
        end
    end

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            pc_q <= 32'h0000_0000;  // Reset vector
        end else begin
            pc_q <= pc_d;
        end
    end

    // =========================================================================
    // Instruction Register
    // =========================================================================
    assign is_fetch = (cpu_state == CPU_FETCH);

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            instr_q <= 32'h0000_0013;  // NOP (ADDI x0, x0, 0)
        end else if (is_fetch && mem_valid) begin
            instr_q <= mem_rdata;
        end
    end

    // =========================================================================
    // Decoder
    // =========================================================================
    rv32i_decode u_decode (
        .instr         (instr_q),
        .rs1_addr      (rs1_addr),
        .rs2_addr      (rs2_addr),
        .rd_addr       (rd_addr),
        .opcode        (opcode),
        .funct3        (funct3),
        .funct7        (funct7),
        .ctrl          (ctrl),
        .illegal_instr (illegal_instr)
    );

    // =========================================================================
    // Immediate Generator
    // =========================================================================
    rv32i_imm_gen u_imm_gen (
        .instr    (instr_q),
        .imm_type (ctrl.imm_type),
        .imm      (imm)
    );

    // =========================================================================
    // Register File
    // =========================================================================

    // Write enable (only during writeback phase and when not stalled)
    assign rd_we = ctrl.reg_write && (cpu_state == CPU_WRITEBACK);

    rv32i_regfile u_regfile (
        .clk       (clk),
        .rst_n     (rst_n),
        .rs1_addr  (rs1_addr),
        .rs1_data  (rs1_data),
        .rs2_addr  (rs2_addr),
        .rs2_data  (rs2_data),
        .rd_addr   (rd_addr),
        .rd_data   (rd_data),
        .rd_we     (rd_we),
        .dbg_addr  (dbg_reg_addr),
        .dbg_wdata (dbg_reg_wdata),
        .dbg_we    (dbg_reg_we && halted),  // Debug write only when halted
        .dbg_rdata (dbg_reg_rdata)
    );

    // =========================================================================
    // ALU Operand Selection
    // =========================================================================
    always_comb begin
        // Operand A selection
        case (ctrl.alu_src_a)
            ALU_SRC_REG:  alu_operand_a = rs1_data;
            ALU_SRC_PC:   alu_operand_a = pc_q;
            ALU_SRC_ZERO: alu_operand_a = '0;
            default:      alu_operand_a = rs1_data;
        endcase

        // Operand B selection
        case (ctrl.alu_src_b)
            ALU_SRC_REG:  alu_operand_b = rs2_data;
            ALU_SRC_IMM:  alu_operand_b = imm;
            ALU_SRC_ZERO: alu_operand_b = '0;
            default:      alu_operand_b = rs2_data;
        endcase
    end

    // =========================================================================
    // ALU
    // =========================================================================
    rv32i_alu u_alu (
        .operand_a (alu_operand_a),
        .operand_b (alu_operand_b),
        .alu_op    (ctrl.alu_op),
        .result    (alu_result),
        .zero      (alu_zero),
        .negative  (alu_negative),
        .carry     (alu_carry),
        .overflow  (alu_overflow)
    );

    // =========================================================================
    // Control Unit
    // =========================================================================
    rv32i_control u_control (
        .clk            (clk),
        .rst_n          (rst_n),
        .instr          (instr_q),
        .ctrl           (ctrl),
        .illegal_instr  (illegal_instr),
        .alu_zero       (alu_zero),
        .alu_negative   (alu_negative),
        .alu_result     (alu_result),
        .mem_ready      (mem_ready),
        .mem_valid      (mem_valid),
        .dbg_halt_req   (dbg_halt_req),
        .dbg_resume_req (dbg_resume_req),
        .dbg_step_req   (dbg_step_req),
        .bp_hit         (bp_hit),
        .cpu_state      (cpu_state),
        .pc_we          (pc_we),
        .pc_sel_branch  (pc_sel_branch),
        .pc_sel_jump    (pc_sel_jump),
        .instr_valid    (instr_valid),
        .stall          (stall),
        .halted         (halted),
        .halt_cause     (halt_cause),
        .mem_req        (ctrl_mem_req),
        .mem_we         (ctrl_mem_we)
    );

    // =========================================================================
    // Load Data Processing
    // =========================================================================
    always_comb begin
        load_data = mem_rdata;

        // Extract and sign/zero extend based on load type
        case (ctrl.funct3)
            LD_LB: begin
                case (alu_result[1:0])
                    2'b00: load_data = {{24{mem_rdata[7]}},  mem_rdata[7:0]};
                    2'b01: load_data = {{24{mem_rdata[15]}}, mem_rdata[15:8]};
                    2'b10: load_data = {{24{mem_rdata[23]}}, mem_rdata[23:16]};
                    2'b11: load_data = {{24{mem_rdata[31]}}, mem_rdata[31:24]};
                endcase
            end
            LD_LH: begin
                case (alu_result[1])
                    1'b0: load_data = {{16{mem_rdata[15]}}, mem_rdata[15:0]};
                    1'b1: load_data = {{16{mem_rdata[31]}}, mem_rdata[31:16]};
                endcase
            end
            LD_LW: begin
                load_data = mem_rdata;
            end
            LD_LBU: begin
                case (alu_result[1:0])
                    2'b00: load_data = {24'b0, mem_rdata[7:0]};
                    2'b01: load_data = {24'b0, mem_rdata[15:8]};
                    2'b10: load_data = {24'b0, mem_rdata[23:16]};
                    2'b11: load_data = {24'b0, mem_rdata[31:24]};
                endcase
            end
            LD_LHU: begin
                case (alu_result[1])
                    1'b0: load_data = {16'b0, mem_rdata[15:0]};
                    1'b1: load_data = {16'b0, mem_rdata[31:16]};
                endcase
            end
            default: load_data = mem_rdata;
        endcase
    end

    // =========================================================================
    // Writeback Data Selection
    // =========================================================================
    always_comb begin
        case (ctrl.wb_src)
            WB_SRC_ALU: rd_data = alu_result;
            WB_SRC_MEM: rd_data = load_data;
            WB_SRC_PC4: rd_data = pc_plus4;
            WB_SRC_IMM: rd_data = imm;
            default:    rd_data = alu_result;
        endcase
    end

    // =========================================================================
    // Memory Interface
    // =========================================================================

    // Memory address: PC for fetch, ALU result for load/store
    assign mem_addr = is_fetch ? pc_q : {alu_result[XLEN-1:2], 2'b00};

    // Write data (aligned based on address and size)
    always_comb begin
        mem_wdata = rs2_data;
        mem_wstrb = 4'b0000;

        if (ctrl.mem_write) begin
            case (ctrl.funct3)
                ST_SB: begin
                    case (alu_result[1:0])
                        2'b00: begin mem_wdata = {24'b0, rs2_data[7:0]};       mem_wstrb = 4'b0001; end
                        2'b01: begin mem_wdata = {16'b0, rs2_data[7:0], 8'b0}; mem_wstrb = 4'b0010; end
                        2'b10: begin mem_wdata = {8'b0, rs2_data[7:0], 16'b0}; mem_wstrb = 4'b0100; end
                        2'b11: begin mem_wdata = {rs2_data[7:0], 24'b0};       mem_wstrb = 4'b1000; end
                    endcase
                end
                ST_SH: begin
                    case (alu_result[1])
                        1'b0: begin mem_wdata = {16'b0, rs2_data[15:0]};       mem_wstrb = 4'b0011; end
                        1'b1: begin mem_wdata = {rs2_data[15:0], 16'b0};       mem_wstrb = 4'b1100; end
                    endcase
                end
                ST_SW: begin
                    mem_wdata = rs2_data;
                    mem_wstrb = 4'b1111;
                end
                default: begin
                    mem_wdata = rs2_data;
                    mem_wstrb = 4'b1111;
                end
            endcase
        end
    end

    // Memory request and write enable
    assign mem_req = ctrl_mem_req;
    assign mem_we  = ctrl_mem_we;

    // =========================================================================
    // Debug Interface Outputs
    // =========================================================================
    assign dbg_pc_rdata   = pc_q;
    assign dbg_instr      = instr_q;
    assign dbg_halted     = halted;
    assign dbg_halt_cause = halt_cause;

endmodule
