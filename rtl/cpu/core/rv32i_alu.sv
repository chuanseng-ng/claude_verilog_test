// rv32i_alu.sv
// RV32I Arithmetic Logic Unit
// Implements all 10 RV32I ALU operations
//
// Specification: RISC-V ISA Manual, Volume I
// - ADD, SUB
// - AND, OR, XOR
// - SLL, SRL, SRA (shift operations)
// - SLT, SLTU (comparison operations)
//
// Notes:
// - Shift amount uses only lower 5 bits of operand_b[4:0]
// - SRA preserves sign bit (arithmetic right shift)
// - All operations wrap (no saturation)
// - SLT uses signed comparison, SLTU uses unsigned comparison

module rv32i_alu (
  // Operands
  input  logic [31:0] operand_a,
  input  logic [31:0] operand_b,

  // ALU operation selection
  input  logic [3:0]  alu_op,

  // Result
  output logic [31:0] result
);

  // ALU operation encodings
  localparam [3:0] ALU_ADD  = 4'b0000;
  localparam [3:0] ALU_SUB  = 4'b0001;
  localparam [3:0] ALU_SLL  = 4'b0010;
  localparam [3:0] ALU_SLT  = 4'b0011;
  localparam [3:0] ALU_SLTU = 4'b0100;
  localparam [3:0] ALU_XOR  = 4'b0101;
  localparam [3:0] ALU_SRL  = 4'b0110;
  localparam [3:0] ALU_SRA  = 4'b0111;
  localparam [3:0] ALU_OR   = 4'b1000;
  localparam [3:0] ALU_AND  = 4'b1001;

  // Shift amount (only lower 5 bits used per RV32I spec)
  logic [4:0] shamt;
  assign shamt = operand_b[4:0];

  // Combinational ALU logic
  always_comb begin
    case (alu_op)
      // ADD: operand_a + operand_b
      ALU_ADD: begin
        result = operand_a + operand_b;
      end

      // SUB: operand_a - operand_b
      ALU_SUB: begin
        result = operand_a - operand_b;
      end

      // SLL: Shift left logical
      // Shift operand_a left by shamt positions
      ALU_SLL: begin
        result = operand_a << shamt;
      end

      // SLT: Set less than (signed)
      // result = 1 if operand_a < operand_b (signed), else 0
      ALU_SLT: begin
        result = ($signed(operand_a) < $signed(operand_b)) ? 32'h1 : 32'h0;
      end

      // SLTU: Set less than unsigned
      // result = 1 if operand_a < operand_b (unsigned), else 0
      ALU_SLTU: begin
        result = (operand_a < operand_b) ? 32'h1 : 32'h0;
      end

      // XOR: Bitwise exclusive OR
      ALU_XOR: begin
        result = operand_a ^ operand_b;
      end

      // SRL: Shift right logical
      // Shift operand_a right by shamt positions (zero-fill)
      ALU_SRL: begin
        result = operand_a >> shamt;
      end

      // SRA: Shift right arithmetic
      // Shift operand_a right by shamt positions (sign-extend)
      ALU_SRA: begin
        result = $signed(operand_a) >>> shamt;
      end

      // OR: Bitwise OR
      ALU_OR: begin
        result = operand_a | operand_b;
      end

      // AND: Bitwise AND
      ALU_AND: begin
        result = operand_a & operand_b;
      end

      // Default case to avoid latches
      default: begin
        result = 32'h0;
      end
    endcase
  end

endmodule
