// RV32I ALU - Arithmetic Logic Unit for RISC-V RV32I processor
module rv32i_alu
    import rv32i_pkg::*;
(
    input  logic [XLEN-1:0]  operand_a,
    input  logic [XLEN-1:0]  operand_b,
    input  alu_op_e          alu_op,

    output logic [XLEN-1:0]  result,
    output logic             zero,       // Result is zero
    output logic             negative,   // Result is negative (MSB)
    output logic             carry,      // Carry/borrow out
    output logic             overflow    // Signed overflow
);

    // Internal signals
    logic [XLEN:0]   add_result;
    logic [XLEN:0]   sub_result;
    logic [XLEN-1:0] shift_amount;

    // Limit shift amount to 5 bits for 32-bit operations
    assign shift_amount = {27'b0, operand_b[4:0]};

    // Addition and subtraction with carry
    assign add_result = {1'b0, operand_a} + {1'b0, operand_b};
    assign sub_result = {1'b0, operand_a} - {1'b0, operand_b};

    // Main ALU operation
    always_comb begin
        result   = '0;
        carry    = 1'b0;
        overflow = 1'b0;

        case (alu_op)
            ALU_OP_ADD: begin
                result   = add_result[XLEN-1:0];
                carry    = add_result[XLEN];
                // Overflow: both operands same sign, result different sign
                overflow = (operand_a[XLEN-1] == operand_b[XLEN-1]) &&
                           (result[XLEN-1] != operand_a[XLEN-1]);
            end

            ALU_OP_SUB: begin
                result   = sub_result[XLEN-1:0];
                carry    = sub_result[XLEN];  // Borrow
                // Overflow: operands different sign, result sign matches subtrahend
                overflow = (operand_a[XLEN-1] != operand_b[XLEN-1]) &&
                           (result[XLEN-1] == operand_b[XLEN-1]);
            end

            ALU_OP_SLL: begin
                result = operand_a << shift_amount[4:0];
            end

            ALU_OP_SLT: begin
                // Signed comparison
                result = {{(XLEN-1){1'b0}}, $signed(operand_a) < $signed(operand_b)};
            end

            ALU_OP_SLTU: begin
                // Unsigned comparison
                result = {{(XLEN-1){1'b0}}, operand_a < operand_b};
            end

            ALU_OP_XOR: begin
                result = operand_a ^ operand_b;
            end

            ALU_OP_SRL: begin
                result = operand_a >> shift_amount[4:0];
            end

            ALU_OP_SRA: begin
                result = $signed(operand_a) >>> shift_amount[4:0];
            end

            ALU_OP_OR: begin
                result = operand_a | operand_b;
            end

            ALU_OP_AND: begin
                result = operand_a & operand_b;
            end

            ALU_OP_PASS_B: begin
                result = operand_b;
            end

            default: begin
                result = '0;
            end
        endcase
    end

    // Status flags
    assign zero     = (result == '0);
    assign negative = result[XLEN-1];

endmodule
