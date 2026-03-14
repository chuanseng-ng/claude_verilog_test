// rv32i_pipeline_pkg.sv
// RV32I 5-Stage Pipeline Register Type Definitions (Phase 2)
//
// Defines the four pipeline register structs that connect the five stages.
// All registers reset/flush to NOP values (valid=0).

package rv32i_pipeline_pkg;

    // =========================================================================
    // IF/ID Pipeline Register
    // Captures the fetched instruction and its PC.
    // Reset/flush value: valid=0, instruction=NOP (ADDI x0,x0,0 = 0x00000013)
    // =========================================================================
    typedef struct packed {
        logic [31:0] pc;           // PC of fetched instruction
        logic [31:0] instruction;  // Fetched instruction word
        logic        valid;        // 1 = instruction is valid (0 = bubble)
    } if_id_reg_t;

    // =========================================================================
    // ID/EX Pipeline Register
    // Captures all decode outputs and register-read results.
    // Reset/flush value: all control signals 0, valid=0.
    // =========================================================================
    typedef struct packed {
        logic [31:0] pc;           // Instruction PC
        logic [31:0] instruction;  // Instruction word (for commit_insn_o)
        logic [31:0] rs1_data;     // Register file rs1 read result
        logic [31:0] rs2_data;     // Register file rs2 read result
        logic [31:0] immediate;    // Sign-extended immediate
        logic [4:0]  rs1_addr;     // rs1 address (forwarding detection)
        logic [4:0]  rs2_addr;     // rs2 address (forwarding detection)
        logic [4:0]  rd_addr;      // Destination register
        logic [3:0]  alu_op;       // ALU operation
        logic [1:0]  alu_src_a;    // ALU A mux: 00=rs1, 01=PC, 10=zero
        logic        alu_src_b;    // ALU B mux: 0=rs2, 1=imm
        logic        reg_wr_en;    // Register write enable
        logic        mem_rd;       // Load operation
        logic        mem_wr;       // Store operation
        logic [2:0]  mem_size;     // 000=byte, 001=half, 010=word
        logic        mem_unsigned; // Unsigned load
        logic        branch;       // Branch instruction
        logic [2:0]  branch_op;    // Branch comparison type (funct3)
        logic        jump;         // JAL or JALR
        logic        jalr;         // JALR (register-relative jump)
        logic        csr_access;   // CSR read/write instruction
        logic [11:0] csr_addr;     // 12-bit CSR address
        logic [2:0]  csr_op;       // CSR operation (funct3)
        logic        ebreak;       // EBREAK instruction
        logic        mret;         // MRET instruction
        logic        fence_i;     // FENCE.I instruction (I-cache invalidate)
        logic        illegal;      // Illegal instruction
        logic        valid;        // Stage valid
    } id_ex_reg_t;

    // =========================================================================
    // EX/MEM Pipeline Register
    // Captures ALU result, branch decision, store data, and CSR write value.
    // =========================================================================
    typedef struct packed {
        logic [31:0] pc;           // Instruction PC
        logic [31:0] instruction;  // Instruction word (for commit_insn_o)
        logic [31:0] alu_result;   // ALU output (address for loads/stores)
        logic [31:0] rs2_data;     // Store data (after forwarding)
        logic [31:0] csr_rdata;    // CSR read data (pre-write, for rd)
        logic [4:0]  rd_addr;      // Destination register
        logic        reg_wr_en;    // Register write enable
        logic        mem_rd;       // Load operation
        logic        mem_wr;       // Store operation
        logic [2:0]  mem_size;     // Memory access size
        logic        mem_unsigned; // Unsigned load
        logic        csr_access;   // CSR instruction
        logic [11:0] csr_addr;     // CSR address
        logic [31:0] csr_wdata;    // Value written to CSR this cycle
        logic        jump;         // Jump instruction (for WB PC+4 mux)
        logic        jalr;         // JALR
        logic        pc_redirect;  // 1 = pipeline must flush and redirect PC
        logic [31:0] pc_target;    // Redirect target address
        logic        trap_valid;   // Trap/interrupt taken this instruction
        logic [31:0] trap_cause;   // Full 32-bit mcause value
        logic        valid;        // Stage valid
    } ex_mem_reg_t;

    // =========================================================================
    // MEM/WB Pipeline Register
    // Captures memory read data for WB mux and final writeback.
    // =========================================================================
    typedef struct packed {
        logic [31:0] pc;           // Instruction PC
        logic [31:0] instruction;  // Instruction word (for commit_insn_o)
        logic [31:0] alu_result;   // ALU result (non-load writeback)
        logic [31:0] mem_rdata;    // Loaded and byte-extracted data
        logic [31:0] csr_rdata;    // CSR read data (for writeback to rd)
        logic [4:0]  rd_addr;      // Destination register
        logic        reg_wr_en;    // Register write enable
        logic        mem_rd;       // Was this a load
        logic        csr_access;   // CSR instruction (selects csr_rdata for WB)
        logic        jump;         // JAL/JALR (selects PC+4 for WB)
        logic        trap_valid;   // Trap taken this cycle
        logic [31:0] trap_cause;   // mcause value
        logic        valid;        // Stage valid
    } mem_wb_reg_t;

    // =========================================================================
    // Flush (NOP bubble) values
    // =========================================================================
    function automatic if_id_reg_t if_id_nop();
        if_id_nop = '{pc: '0, instruction: 32'h0000_0013, valid: 1'b0};
    endfunction

    function automatic id_ex_reg_t id_ex_nop();
        id_ex_nop = '{default: '0};
    endfunction

    function automatic ex_mem_reg_t ex_mem_nop();
        ex_mem_nop = '{default: '0};
    endfunction

    function automatic mem_wb_reg_t mem_wb_nop();
        mem_wb_nop = '{default: '0};
    endfunction

endpackage
