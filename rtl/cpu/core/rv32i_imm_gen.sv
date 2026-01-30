// rv32i_imm_gen.sv
// RV32I Immediate Generator
// Extracts and sign-extends immediate values from instruction encoding
//
// Specification: RISC-V ISA Manual, Volume I, Chapter 2
// Supports all 6 RV32I immediate formats: I, S, B, U, J, R

module rv32i_imm_gen (
  // Instruction input
  /* verilator lint_off UNUSEDSIGNAL */
  input  logic [31:0] instruction,  // Lower bits [6:0] are opcode, not used in immediate generation
  /* verilator lint_on UNUSEDSIGNAL */

  // Immediate format selection
  input  logic [2:0]  imm_fmt,

  // Generated immediate output
  output logic [31:0] immediate
);

  // Immediate format encodings
  localparam [2:0] FMT_I = 3'b000;  // I-type (ALU-immediate, loads)
  localparam [2:0] FMT_S = 3'b001;  // S-type (stores)
  localparam [2:0] FMT_B = 3'b010;  // B-type (branches)
  localparam [2:0] FMT_U = 3'b011;  // U-type (LUI, AUIPC)
  localparam [2:0] FMT_J = 3'b100;  // J-type (JAL)
  localparam [2:0] FMT_R = 3'b101;  // R-type (no immediate)

  // Combinational logic for immediate generation
  always_comb begin
    case (imm_fmt)
      // I-type: imm[11:0] = instruction[31:20]
      // Sign-extend to 32 bits
      FMT_I: begin
        immediate = {{20{instruction[31]}}, instruction[31:20]};
      end

      // S-type: imm[11:5] = instruction[31:25], imm[4:0] = instruction[11:7]
      // Sign-extend to 32 bits
      FMT_S: begin
        immediate = {{20{instruction[31]}}, instruction[31:25], instruction[11:7]};
      end

      // B-type: imm[12|10:5|4:1|11] from instruction, imm[0] = 0
      // Sign-extend to 32 bits
      FMT_B: begin
        immediate = {{19{instruction[31]}},
                     instruction[31],    // imm[12]
                     instruction[7],     // imm[11]
                     instruction[30:25], // imm[10:5]
                     instruction[11:8],  // imm[4:1]
                     1'b0};              // imm[0] = 0 (2-byte aligned)
      end

      // U-type: imm[31:12] = instruction[31:12], imm[11:0] = 0
      // No sign extension needed (upper 20 bits are the immediate)
      FMT_U: begin
        immediate = {instruction[31:12], 12'h0};
      end

      // J-type: imm[20|10:1|11|19:12] from instruction, imm[0] = 0
      // Sign-extend to 32 bits
      FMT_J: begin
        immediate = {{11{instruction[31]}},
                     instruction[31],    // imm[20]
                     instruction[19:12], // imm[19:12]
                     instruction[20],    // imm[11]
                     instruction[30:21], // imm[10:1]
                     1'b0};              // imm[0] = 0 (2-byte aligned)
      end

      // R-type: No immediate
      FMT_R: begin
        immediate = 32'h0;
      end

      // Default case to avoid latches
      default: begin
        immediate = 32'h0;
      end
    endcase
  end

endmodule
