// rv32i_branch_comp.sv
// RV32I Branch Comparator
// Evaluates branch conditions for all 6 RV32I branch instructions
//
// Specification: RISC-V ISA Manual, Volume I
// - BEQ: Branch if equal
// - BNE: Branch if not equal
// - BLT: Branch if less than (signed)
// - BGE: Branch if greater than or equal (signed)
// - BLTU: Branch if less than (unsigned)
// - BGEU: Branch if greater than or equal (unsigned)

module rv32i_branch_comp (
  // Operands from register file
  input  logic [31:0] rs1_data,
  input  logic [31:0] rs2_data,

  // Branch operation type
  input  logic [2:0]  branch_op,

  // Branch taken output
  output logic        branch_taken
);

  // Branch operation encodings (funct3 from instruction)
  localparam [2:0] FUNCT3_BEQ  = 3'b000;
  localparam [2:0] FUNCT3_BNE  = 3'b001;
  localparam [2:0] FUNCT3_BLT  = 3'b100;
  localparam [2:0] FUNCT3_BGE  = 3'b101;
  localparam [2:0] FUNCT3_BLTU = 3'b110;
  localparam [2:0] FUNCT3_BGEU = 3'b111;

  // Combinational comparison logic
  always_comb begin
    case (branch_op)
      // BEQ: Branch if rs1 == rs2
      FUNCT3_BEQ: begin
        branch_taken = (rs1_data == rs2_data);
      end

      // BNE: Branch if rs1 != rs2
      FUNCT3_BNE: begin
        branch_taken = (rs1_data != rs2_data);
      end

      // BLT: Branch if rs1 < rs2 (signed comparison)
      FUNCT3_BLT: begin
        branch_taken = ($signed(rs1_data) < $signed(rs2_data));
      end

      // BGE: Branch if rs1 >= rs2 (signed comparison)
      FUNCT3_BGE: begin
        branch_taken = ($signed(rs1_data) >= $signed(rs2_data));
      end

      // BLTU: Branch if rs1 < rs2 (unsigned comparison)
      FUNCT3_BLTU: begin
        branch_taken = (rs1_data < rs2_data);
      end

      // BGEU: Branch if rs1 >= rs2 (unsigned comparison)
      FUNCT3_BGEU: begin
        branch_taken = (rs1_data >= rs2_data);
      end

      // Default: Branch not taken (for non-branch instructions)
      default: begin
        branch_taken = 1'b0;
      end
    endcase
  end

endmodule
