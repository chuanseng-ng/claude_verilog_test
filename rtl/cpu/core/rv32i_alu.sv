// rv32i_alu - RV32I arithmetic logic unit with a shared adder.
//
// Function: Combinational. result is computed from operand_a, operand_b and alu_op.
//   ALU_ADD 4'b0000, ALU_SUB 4'b0001, ALU_SLL 4'b0010, ALU_SLT 4'b0011, ALU_SLTU 4'b0100,
//   ALU_XOR 4'b0101, ALU_SRL 4'b0110, ALU_SRA 4'b0111, ALU_OR 4'b1000, ALU_AND 4'b1001.
//   ADD, SUB, SLT and SLTU share one 33-bit adder.
//   Shifts use only operand_b[4:0]. SRA preserves the sign bit. All operations wrap. There is no saturation.
//   SLT uses signed comparison and SLTU uses unsigned comparison.
//   An alu_op above 4'b1001 gives result = 0.
// Parameters: none.
// Clocks and resets: none. The module is purely combinational.
// Caller rules:
//   - Drive alu_op with one of the ten encodings above. Any other value gives result = 0.
// Doc: ds:mod:rv32i-alu, tm:mod:rv32i-alu

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
