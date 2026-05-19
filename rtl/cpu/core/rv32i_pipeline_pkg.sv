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
        logic        fence_i;      // FENCE.I instruction (I-cache invalidate)
        logic        illegal;      // Illegal instruction
        logic        csr_illegal;  // CSR address not implemented (pre-computed in ID)
        logic        valid;        // Stage valid
    } id_ex_reg_t;

    // =========================================================================
    // EX/MEM Pipeline Register
    // Captures ALU result, branch decision, store data, and CSR write value.
    // =========================================================================
    typedef struct packed {
        logic [31:0] pc;           // Instruction PC
        logic [31:0] instruction;  // Instruction word (for commit_insn_o)
        logic [31:0] alu_result;         // ALU output (address for loads/stores)
        logic [31:0] mem_wdata_aligned;  // Store data, pre-aligned in EX stage
        logic [3:0]  mem_wstrb;          // Store byte strobes, pre-computed in EX stage
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
    // Trap type encoding — pre-computed in EX1a to reduce EX1b cascade depth
    // Priority (highest first): IRQ > illegal/csr_illegal > ebreak >
    //                           fence_i > mret > jalr > taken-branch > none
    // =========================================================================
    typedef enum logic [2:0] {
        TRAP_NONE    = 3'd0,
        TRAP_IRQ     = 3'd1,
        TRAP_ILLEGAL = 3'd2,
        TRAP_EBREAK  = 3'd3,
        TRAP_FENCEI  = 3'd4,
        TRAP_MRET    = 3'd5,
        TRAP_JALR    = 3'd6,
        TRAP_BRANCH  = 3'd7
    } trap_type_e;

    // =========================================================================
    // EX1a/EX1b Intermediate Wire (combinational — NOT a pipeline register)
    // Carries EX1a (ALU + branch_comp + JALR) outputs to EX1b (store-align +
    // trap-cascade).  No FF boundary here; EX2 still owns the only FF.
    // =========================================================================
    typedef struct packed {
        // EX1a computed results
        logic [31:0] alu_result;    // ALU output
        logic        branch_taken;  // Branch comparator result
        logic [31:0] fwd_store;     // Forwarded rs2 store data (for byte-align in EX1b)
        logic [31:0] csr_wd;        // CSR write data (imm or forwarded rs1)
        // Passthrough control fields from id_ex_reg_t needed by EX1b
        logic [31:0] pc;
        logic [31:0] instruction;
        logic [4:0]  rd_addr;
        logic        reg_wr_en;
        logic        mem_rd;
        logic        mem_wr;
        logic [2:0]  mem_size;
        logic        mem_unsigned;
        logic        csr_access;
        logic [11:0] csr_addr;
        logic [31:0] csr_rdata;     // CSR read data (from csr_file)
        logic        jump;
        logic        jalr;
        logic        branch;
        logic [31:0] immediate;
        logic        ebreak;
        logic        mret;
        logic        fence_i;
        logic        illegal;
        logic        csr_illegal;
        logic        valid;
        // Interrupt/trap inputs (passed through for use in EX1b trap cascade)
        logic        irq_valid_r;   // Registered IRQ valid
        logic [31:0] irq_cause;
        logic [31:0] mtvec;
        logic [31:0] mret_pc;
        // Flush indicator
        logic        flush_ex_mem;
        // rs1/rs2 addresses (for forwarding detection passthrough)
        logic [4:0]  rs1_addr;
        logic [4:0]  rs2_addr;
        // Pre-encoded trap type (computed in EX1a, consumed in EX1b as flat case-mux)
        trap_type_e  trap_type;
        // Run-19 P1: store byte-align pre-computed in EX1a to shorten EX1b cone.
        // EX1b reads these directly — removing the ~8-10 gate byte-align mux from EX1b.
        logic [31:0] pre_wdata_aligned;   // Byte/halfword/word-aligned store data
        logic [3:0]  pre_wstrb;           // Byte write strobe
        // Run-31: EX1c-decoded trap outputs (registered in ex1c_ex1b_reg_q).
        // EX1b uses these directly — eliminating the 8-way case-mux from the
        // EX1b combinational cone. Saves ~20 gate levels (NOR5/NAND5 bottleneck).
        logic        dec_trap_valid;      // trap is being taken
        logic        dec_do_redirect;     // PC redirect needed
        logic [31:0] dec_redirect_target; // redirect target PC
        logic [31:0] dec_trap_cause;      // mcause value
        logic        dec_is_irq;          // this is an interrupt (for trap_pc = squashed PC)
        logic        dec_mret;            // MRET action
        logic        dec_dbg_halt;        // EBREAK debug halt request
        logic        dec_fence_i;         // FENCE.I I-cache invalidation
    } ex1a_ex1b_t;

    // =========================================================================
    // EX1/EX2 Pipeline Register
    // Identical fields to ex_mem_reg_t — captures EX1b combinational outputs
    // at the clock edge; EX2 reads this and drives ex_mem_reg_t.
    // =========================================================================
    typedef struct packed {
        logic [31:0] pc;
        logic [31:0] instruction;
        logic [31:0] alu_result;
        logic [31:0] mem_wdata_aligned;
        logic [3:0]  mem_wstrb;
        logic [31:0] csr_rdata;
        logic [4:0]  rd_addr;
        logic        reg_wr_en;
        logic        mem_rd;
        logic        mem_wr;
        logic [2:0]  mem_size;
        logic        mem_unsigned;
        logic        csr_access;
        logic [11:0] csr_addr;
        logic [31:0] csr_wdata;
        logic        jump;
        logic        jalr;
        logic        pc_redirect;
        logic [31:0] pc_target;
        logic        trap_valid;
        logic [31:0] trap_cause;
        logic        valid;
    } ex1_ex2_reg_t;

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
        if_id_nop.pc          = 32'h0;
        if_id_nop.instruction = 32'h0000_0013; // ADDI x0,x0,0 — architectural NOP
        if_id_nop.valid       = 1'b0;
    endfunction

    function automatic id_ex_reg_t id_ex_nop();
        id_ex_nop.pc           = 32'h0;
        id_ex_nop.instruction  = 32'h0;
        id_ex_nop.rs1_data     = 32'h0;
        id_ex_nop.rs2_data     = 32'h0;
        id_ex_nop.immediate    = 32'h0;
        id_ex_nop.rs1_addr     = 5'h0;
        id_ex_nop.rs2_addr     = 5'h0;
        id_ex_nop.rd_addr      = 5'h0;
        id_ex_nop.alu_op       = 4'h0;
        id_ex_nop.alu_src_a    = 2'h0;
        id_ex_nop.alu_src_b    = 1'b0;
        id_ex_nop.reg_wr_en    = 1'b0;
        id_ex_nop.mem_rd       = 1'b0;
        id_ex_nop.mem_wr       = 1'b0;
        id_ex_nop.mem_size     = 3'h0;
        id_ex_nop.mem_unsigned = 1'b0;
        id_ex_nop.branch       = 1'b0;
        id_ex_nop.branch_op    = 3'h0;
        id_ex_nop.jump         = 1'b0;
        id_ex_nop.jalr         = 1'b0;
        id_ex_nop.csr_access   = 1'b0;
        id_ex_nop.csr_addr     = 12'h0;
        id_ex_nop.csr_op       = 3'h0;
        id_ex_nop.ebreak       = 1'b0;
        id_ex_nop.mret         = 1'b0;
        id_ex_nop.fence_i      = 1'b0;
        id_ex_nop.illegal      = 1'b0;
        id_ex_nop.csr_illegal  = 1'b0;
        id_ex_nop.valid        = 1'b0;
    endfunction

    function automatic ex_mem_reg_t ex_mem_nop();
        ex_mem_nop.pc          = 32'h0;
        ex_mem_nop.instruction = 32'h0;
        ex_mem_nop.alu_result        = 32'h0;
        ex_mem_nop.mem_wdata_aligned = 32'h0;
        ex_mem_nop.mem_wstrb         = 4'h0;
        ex_mem_nop.csr_rdata   = 32'h0;
        ex_mem_nop.rd_addr     = 5'h0;
        ex_mem_nop.reg_wr_en   = 1'b0;
        ex_mem_nop.mem_rd      = 1'b0;
        ex_mem_nop.mem_wr      = 1'b0;
        ex_mem_nop.mem_size    = 3'h0;
        ex_mem_nop.mem_unsigned= 1'b0;
        ex_mem_nop.csr_access  = 1'b0;
        ex_mem_nop.csr_addr    = 12'h0;
        ex_mem_nop.csr_wdata   = 32'h0;
        ex_mem_nop.jump        = 1'b0;
        ex_mem_nop.jalr        = 1'b0;
        ex_mem_nop.pc_redirect = 1'b0;
        ex_mem_nop.pc_target   = 32'h0;
        ex_mem_nop.trap_valid  = 1'b0;
        ex_mem_nop.trap_cause  = 32'h0;
        ex_mem_nop.valid       = 1'b0;
    endfunction

    function automatic ex1_ex2_reg_t ex1_ex2_nop();
        ex1_ex2_nop.pc                = 32'h0;
        ex1_ex2_nop.instruction       = 32'h0;
        ex1_ex2_nop.alu_result        = 32'h0;
        ex1_ex2_nop.mem_wdata_aligned = 32'h0;
        ex1_ex2_nop.mem_wstrb         = 4'h0;
        ex1_ex2_nop.csr_rdata         = 32'h0;
        ex1_ex2_nop.rd_addr           = 5'h0;
        ex1_ex2_nop.reg_wr_en         = 1'b0;
        ex1_ex2_nop.mem_rd            = 1'b0;
        ex1_ex2_nop.mem_wr            = 1'b0;
        ex1_ex2_nop.mem_size          = 3'h0;
        ex1_ex2_nop.mem_unsigned      = 1'b0;
        ex1_ex2_nop.csr_access        = 1'b0;
        ex1_ex2_nop.csr_addr          = 12'h0;
        ex1_ex2_nop.csr_wdata         = 32'h0;
        ex1_ex2_nop.jump              = 1'b0;
        ex1_ex2_nop.jalr              = 1'b0;
        ex1_ex2_nop.pc_redirect       = 1'b0;
        ex1_ex2_nop.pc_target         = 32'h0;
        ex1_ex2_nop.trap_valid        = 1'b0;
        ex1_ex2_nop.trap_cause        = 32'h0;
        ex1_ex2_nop.valid             = 1'b0;
    endfunction

    function automatic ex1a_ex1b_t ex1a_ex1b_nop();
        ex1a_ex1b_nop.alu_result    = 32'h0;
        ex1a_ex1b_nop.branch_taken  = 1'b0;
        ex1a_ex1b_nop.fwd_store     = 32'h0;
        ex1a_ex1b_nop.csr_wd        = 32'h0;
        ex1a_ex1b_nop.pc            = 32'h0;
        ex1a_ex1b_nop.instruction   = 32'h0;
        ex1a_ex1b_nop.rd_addr       = 5'h0;
        ex1a_ex1b_nop.reg_wr_en     = 1'b0;
        ex1a_ex1b_nop.mem_rd        = 1'b0;
        ex1a_ex1b_nop.mem_wr        = 1'b0;
        ex1a_ex1b_nop.mem_size      = 3'h0;
        ex1a_ex1b_nop.mem_unsigned  = 1'b0;
        ex1a_ex1b_nop.csr_access    = 1'b0;
        ex1a_ex1b_nop.csr_addr      = 12'h0;
        ex1a_ex1b_nop.csr_rdata     = 32'h0;
        ex1a_ex1b_nop.jump          = 1'b0;
        ex1a_ex1b_nop.jalr          = 1'b0;
        ex1a_ex1b_nop.branch        = 1'b0;
        ex1a_ex1b_nop.immediate     = 32'h0;
        ex1a_ex1b_nop.ebreak        = 1'b0;
        ex1a_ex1b_nop.mret          = 1'b0;
        ex1a_ex1b_nop.fence_i       = 1'b0;
        ex1a_ex1b_nop.illegal       = 1'b0;
        ex1a_ex1b_nop.csr_illegal   = 1'b0;
        ex1a_ex1b_nop.valid         = 1'b0;
        ex1a_ex1b_nop.irq_valid_r   = 1'b0;
        ex1a_ex1b_nop.irq_cause     = 32'h0;
        ex1a_ex1b_nop.mtvec         = 32'h0;
        ex1a_ex1b_nop.mret_pc       = 32'h0;
        ex1a_ex1b_nop.flush_ex_mem  = 1'b0;
        ex1a_ex1b_nop.rs1_addr      = 5'h0;
        ex1a_ex1b_nop.rs2_addr      = 5'h0;
        ex1a_ex1b_nop.trap_type         = TRAP_NONE;
        ex1a_ex1b_nop.pre_wdata_aligned = 32'h0;
        ex1a_ex1b_nop.pre_wstrb         = 4'h0;
        ex1a_ex1b_nop.dec_trap_valid      = 1'b0;
        ex1a_ex1b_nop.dec_do_redirect     = 1'b0;
        ex1a_ex1b_nop.dec_redirect_target = 32'h0;
        ex1a_ex1b_nop.dec_trap_cause      = 32'h0;
        ex1a_ex1b_nop.dec_is_irq          = 1'b0;
        ex1a_ex1b_nop.dec_mret            = 1'b0;
        ex1a_ex1b_nop.dec_dbg_halt        = 1'b0;
        ex1a_ex1b_nop.dec_fence_i         = 1'b0;
    endfunction

    function automatic mem_wb_reg_t mem_wb_nop();
        mem_wb_nop.pc          = 32'h0;
        mem_wb_nop.instruction = 32'h0;
        mem_wb_nop.alu_result  = 32'h0;
        mem_wb_nop.mem_rdata   = 32'h0;
        mem_wb_nop.csr_rdata   = 32'h0;
        mem_wb_nop.rd_addr     = 5'h0;
        mem_wb_nop.reg_wr_en   = 1'b0;
        mem_wb_nop.mem_rd      = 1'b0;
        mem_wb_nop.csr_access  = 1'b0;
        mem_wb_nop.jump        = 1'b0;
        mem_wb_nop.trap_valid  = 1'b0;
        mem_wb_nop.trap_cause  = 32'h0;
        mem_wb_nop.valid       = 1'b0;
    endfunction

endpackage
