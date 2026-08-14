// rv32i_alu.sv
// RV32I Arithmetic Logic Unit — shared-adder design
//
// Implements all 10 RV32I ALU operations.
// ADD/SUB/SLT/SLTU share one 33-bit adder, eliminating the redundant parallel
// carry chains that were the binding setup-critical path (EX1a, Run 38 -3.89 ps).
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

  // Shared add/subtract datapath for ADD, SUB, SLT, SLTU.
  // do_sub=1 → invert operand_b and add 1 (two's-complement negation):
  //   sum = a + ~b + 1 = a - b
  // sum[32] is carry-out; ~sum[32] is the unsigned borrow (a < b unsigned).
  // SLT signed: if operand signs differ, a[31] is the sign of the result;
  //   if equal, sum[31] (the difference MSB) is the sign of (a−b).
  logic        do_sub;
  logic [32:0] sum;
  logic        slt_result;

  assign do_sub    = (alu_op == ALU_SUB)  ||
                     (alu_op == ALU_SLT)  ||
                     (alu_op == ALU_SLTU);
  assign sum       = {1'b0, operand_a}
                   + {1'b0, operand_b ^ {32{do_sub}}}
                   + {32'b0, do_sub};
  assign slt_result = (operand_a[31] ^ operand_b[31]) ? operand_a[31] : sum[31];

  // Result mux
  always_comb begin
    case (alu_op)
      ALU_ADD:  result = sum[31:0];
      ALU_SUB:  result = sum[31:0];
      ALU_SLL:  result = operand_a << shamt;
      ALU_SLT:  result = {31'b0, slt_result};
      ALU_SLTU: result = {31'b0, ~sum[32]};
      ALU_XOR:  result = operand_a ^ operand_b;
      ALU_SRL:  result = operand_a >> shamt;
      // Spyglass SignedUnsignedExpr-ML: waived (lint/spyglass/waivers.awl) —
      // arithmetic right shift is functionally required to be signed (RV32I SRA).
      ALU_SRA:  result = $signed(operand_a) >>> shamt;
      ALU_OR:   result = operand_a | operand_b;
      ALU_AND:  result = operand_a & operand_b;
      /* verilator coverage_off */
      default:  result = 32'h0;
      /* verilator coverage_on */
    endcase
  end

endmodule
