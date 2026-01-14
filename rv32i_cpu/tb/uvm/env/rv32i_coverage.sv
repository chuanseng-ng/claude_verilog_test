//-----------------------------------------------------------------------------
// RV32I Coverage Collector
// Functional coverage for RV32I CPU verification
//-----------------------------------------------------------------------------

class rv32i_coverage extends uvm_subscriber #(axi4lite_seq_item);

    `uvm_component_utils(rv32i_coverage)

    //-------------------------------------------------------------------------
    // Instruction Fields for Coverage
    //-------------------------------------------------------------------------
    logic [6:0]  opcode;
    logic [4:0]  rd, rs1, rs2;
    logic [2:0]  funct3;
    logic [6:0]  funct7;
    logic [31:0] instr;

    //-------------------------------------------------------------------------
    // Coverage Groups
    //-------------------------------------------------------------------------

    // Opcode coverage
    covergroup cg_opcode;
        option.per_instance = 1;
        option.name = "opcode_cov";

        cp_opcode: coverpoint opcode {
            bins op_load    = {7'b0000011};
            bins op_store   = {7'b0100011};
            bins op_branch  = {7'b1100011};
            bins op_jalr    = {7'b1100111};
            bins op_jal     = {7'b1101111};
            bins op_op_imm  = {7'b0010011};
            bins op_op      = {7'b0110011};
            bins op_lui     = {7'b0110111};
            bins op_auipc   = {7'b0010111};
            bins op_system  = {7'b1110011};
            illegal_bins other = default;
        }
    endgroup

    // ALU R-type operations
    covergroup cg_alu_r;
        option.per_instance = 1;
        option.name = "alu_r_cov";

        cp_funct3: coverpoint funct3 iff (opcode == 7'b0110011) {
            bins add_sub = {3'b000};
            bins sll     = {3'b001};
            bins slt     = {3'b010};
            bins sltu    = {3'b011};
            bins xor_op  = {3'b100};
            bins srl_sra = {3'b101};
            bins or_op   = {3'b110};
            bins and_op  = {3'b111};
        }

        cp_add_sub: coverpoint funct7[5] iff (opcode == 7'b0110011 && funct3 == 3'b000) {
            bins add = {1'b0};
            bins sub = {1'b1};
        }

        cp_srl_sra: coverpoint funct7[5] iff (opcode == 7'b0110011 && funct3 == 3'b101) {
            bins srl = {1'b0};
            bins sra = {1'b1};
        }

        // Register coverage
        cp_rd: coverpoint rd iff (opcode == 7'b0110011) {
            bins zero = {0};
            bins low  = {[1:7]};
            bins mid  = {[8:15]};
            bins high = {[16:31]};
        }

        cp_rs1: coverpoint rs1 iff (opcode == 7'b0110011) {
            bins zero = {0};
            bins low  = {[1:7]};
            bins mid  = {[8:15]};
            bins high = {[16:31]};
        }

        cp_rs2: coverpoint rs2 iff (opcode == 7'b0110011) {
            bins zero = {0};
            bins low  = {[1:7]};
            bins mid  = {[8:15]};
            bins high = {[16:31]};
        }
    endgroup

    // ALU I-type operations
    covergroup cg_alu_i;
        option.per_instance = 1;
        option.name = "alu_i_cov";

        cp_funct3: coverpoint funct3 iff (opcode == 7'b0010011) {
            bins addi  = {3'b000};
            bins slli  = {3'b001};
            bins slti  = {3'b010};
            bins sltiu = {3'b011};
            bins xori  = {3'b100};
            bins sri   = {3'b101};  // SRLI/SRAI
            bins ori   = {3'b110};
            bins andi  = {3'b111};
        }

        cp_srli_srai: coverpoint funct7[5] iff (opcode == 7'b0010011 && funct3 == 3'b101) {
            bins srli = {1'b0};
            bins srai = {1'b1};
        }
    endgroup

    // Load operations
    covergroup cg_load;
        option.per_instance = 1;
        option.name = "load_cov";

        cp_funct3: coverpoint funct3 iff (opcode == 7'b0000011) {
            bins lb  = {3'b000};
            bins lh  = {3'b001};
            bins lw  = {3'b010};
            bins lbu = {3'b100};
            bins lhu = {3'b101};
        }
    endgroup

    // Store operations
    covergroup cg_store;
        option.per_instance = 1;
        option.name = "store_cov";

        cp_funct3: coverpoint funct3 iff (opcode == 7'b0100011) {
            bins sb = {3'b000};
            bins sh = {3'b001};
            bins sw = {3'b010};
        }
    endgroup

    // Branch operations
    covergroup cg_branch;
        option.per_instance = 1;
        option.name = "branch_cov";

        cp_funct3: coverpoint funct3 iff (opcode == 7'b1100011) {
            bins beq  = {3'b000};
            bins bne  = {3'b001};
            bins blt  = {3'b100};
            bins bge  = {3'b101};
            bins bltu = {3'b110};
            bins bgeu = {3'b111};
        }
    endgroup

    // Memory address alignment
    covergroup cg_mem_align;
        option.per_instance = 1;
        option.name = "mem_align_cov";

        cp_addr_align: coverpoint instr[1:0] {
            bins aligned   = {2'b00};
            bins byte_1    = {2'b01};
            bins half      = {2'b10};
            bins byte_3    = {2'b11};
        }
    endgroup

    //-------------------------------------------------------------------------
    // Constructor
    //-------------------------------------------------------------------------
    function new(string name, uvm_component parent);
        super.new(name, parent);
        cg_opcode   = new();
        cg_alu_r    = new();
        cg_alu_i    = new();
        cg_load     = new();
        cg_store    = new();
        cg_branch   = new();
        cg_mem_align = new();
    endfunction

    //-------------------------------------------------------------------------
    // Write Function (called for each AXI read = instruction fetch)
    //-------------------------------------------------------------------------
    function void write(axi4lite_seq_item t);
        // Only process instruction fetches (from code region)
        // Assuming code region is lower addresses
        if (t.addr < 32'h0000_1000) begin
            instr   = t.data;
            opcode  = instr[6:0];
            rd      = instr[11:7];
            funct3  = instr[14:12];
            rs1     = instr[19:15];
            rs2     = instr[24:20];
            funct7  = instr[31:25];

            // Sample coverage
            cg_opcode.sample();
            cg_alu_r.sample();
            cg_alu_i.sample();
            cg_load.sample();
            cg_store.sample();
            cg_branch.sample();
        end else begin
            // Data access - sample alignment
            instr[1:0] = t.addr[1:0];
            cg_mem_align.sample();
        end
    endfunction

    //-------------------------------------------------------------------------
    // Report Coverage
    //-------------------------------------------------------------------------
    function void report_phase(uvm_phase phase);
        string report;
        super.report_phase(phase);

        report = "\n";
        report = {report, "========================================\n"};
        report = {report, "        COVERAGE SUMMARY\n"};
        report = {report, "========================================\n"};
        report = {report, $sformatf("  Opcode:      %0.1f%%\n", cg_opcode.get_coverage())};
        report = {report, $sformatf("  ALU R-type:  %0.1f%%\n", cg_alu_r.get_coverage())};
        report = {report, $sformatf("  ALU I-type:  %0.1f%%\n", cg_alu_i.get_coverage())};
        report = {report, $sformatf("  Load:        %0.1f%%\n", cg_load.get_coverage())};
        report = {report, $sformatf("  Store:       %0.1f%%\n", cg_store.get_coverage())};
        report = {report, $sformatf("  Branch:      %0.1f%%\n", cg_branch.get_coverage())};
        report = {report, $sformatf("  Mem Align:   %0.1f%%\n", cg_mem_align.get_coverage())};
        report = {report, "========================================\n"};

        `uvm_info("COVERAGE", report, UVM_LOW)
    endfunction

endclass
