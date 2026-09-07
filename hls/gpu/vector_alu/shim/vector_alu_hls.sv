// vector_alu_hls.sv
// GH #119 — hand-written RTL vs Bambu HLS core PPA/QoR comparison shim.
//
// Purpose:
//   Adapts the port names/widths of the Bambu-generated `vector_alu` HLS
//   core (/nobackup/hls/out/vector_alu/vector_alu.v) to the hand-written
//   RTL interface defined in rtl/gpu/vector_alu.sv, so that BOTH
//   implementations can be driven by the exact same, unmodified cocotb
//   testbench (tb/cocotb/gpu/test_vector_alu.py). This module's data port
//   list (names/directions/widths) is byte-identical to the hand-written
//   RTL's (module name aside); four extra ports (clk, rst_n, start_i,
//   done_o) are added on top because the reference block is purely
//   combinational while the HLS core is a clocked, start/done-handshaked
//   datapath. The testbench detects the HLS arm via `hasattr(dut, "clk")`.
//
//   This shim is combinational wiring ONLY — no registers, no FSM, no
//   logic beyond zero-extension/truncation of ports. Shim area is reported
//   as a separate line in the PPA comparison and must stay zero-register.
//
// Width adaptation:
//   The reference block's `opcode_i` is the 7-bit `gpu_opcode_t` enum,
//   `funct3_i`/`funct7_i` are 3-bit/7-bit, `imm_i` is 12 bits, and
//   `active_mask_i` is N_LANES(8) bits; the HLS core widens every one of
//   its 21 data inputs to [31:0] (Bambu's default scalar-port width) —
//   each is zero-extended at the instance port map (see the `imm_i` note
//   below for why zero-extension, not sign-extension, is the correct
//   match here). `rs1_i`/`rs2_i` are already 32 bits/lane and connect
//   directly, sliced from the packed [N_LANES-1:0][REG_WIDTH-1:0] arrays.
//   The reference block's `result_o` is 32 bits/lane (direct connect);
//   `branch_taken_o` is 1 bit/lane, while the HLS core drives all 8
//   `branch_taken_N` outputs as [31:0] — each is captured in a same-width
//   internal wire and truncated to bit 0 via a continuous assign (still
//   wire-only: no registers, no always blocks).
//
// `imm_i` convention (the one real judgement call in this shim):
//   The reference port `imm_i` is `logic [11:0]`, commented "sign-extended
//   by caller" — which a 12-bit port cannot literally hold, so the actual
//   value this shim ever receives is a raw 12-bit field (bits 31:12 are
//   not represented, i.e. implicitly zero from the core's point of view).
//   hls/gpu/vector_alu/ASSUMPTIONS.md item 1 records that the C source's
//   `imm` handling is `SIGN_EXTEND_12`, applied *idempotently* to the
//   core's 32-bit `imm` input:
//     #define SIGN_EXTEND_12(v) (((v) & 0x800u) ? ((v) | 0xFFFFF000u) \
//                                                : ((v) & 0xFFFu))
//   and proves (by construction, and verified natively in that document)
//   that this expression reproduces the correct sign-extended value for
//   BOTH of the two candidate input conventions: a raw 12-bit field
//   (bits 31:12 == 0) or an already sign-extended 32-bit value (bits
//   31:11 all copies of bit 11). Since this shim's own input is
//   necessarily the first case — a 12-bit port has no bits 31:12 to be
//   anything other than zero — the correct instance-port value is the
//   **zero-extension** of imm_i, `{20'd0, imm_i}`: that is exactly the
//   "raw 12-bit field" input the ASSUMPTIONS.md proof covers, and the
//   core's own SIGN_EXTEND_12 logic performs the sign-extension the
//   reference's port comment promises. Sign-extending here in the shim
//   as well would be redundant (idempotent) but would incorrectly imply
//   the shim performs the sign-extension, when that responsibility is
//   inside the HLS core by the C author's design. Zero-extension is the
//   direct, evidence-backed match.
//
// Coding rules:
//   * No #delays, no initial blocks, no real types
//   * Wire-only: zero registers, zero always blocks
//   * No `default_nettype` directive (Spyglass IND, CODING_GUIDELINES.md §1.3)
//
// Lint target: verilator -Wall -Wno-DECLFILENAME 0 errors 0 warnings on
//              this file (the wrapped HLS core is machine-generated and is
//              linted/waived separately — see GH #119).

module vector_alu_hls
    import gpu_pkg::*;
(
    input  logic clk,
    input  logic rst_n,

    // -----------------------------------------------------------------------
    // HLS start/done handshake — not present on the combinational reference.
    // -----------------------------------------------------------------------
    input  logic start_i,
    output logic done_o,

    input  gpu_opcode_t                       opcode_i,
    input  logic [2:0]                        funct3_i,
    input  logic [6:0]                        funct7_i,

    input  logic [N_LANES-1:0][REG_WIDTH-1:0] rs1_i,
    input  logic [N_LANES-1:0][REG_WIDTH-1:0] rs2_i,
    input  logic [11:0]                       imm_i,      // sign-extended by caller

    input  logic [N_LANES-1:0]               active_mask_i,

    output logic [N_LANES-1:0][REG_WIDTH-1:0] result_o,
    output logic [N_LANES-1:0]               branch_taken_o
);

  // ---------------------------------------------------------------------
  // 32-bit capture wires for every HLS core branch_taken_N output,
  // truncated below to the reference block's 1-bit-per-lane width. The
  // upper 31 bits are intentionally discarded — waive the resulting
  // unused-bits warnings rather than trusting the reader to infer intent
  // from silence.
  // ---------------------------------------------------------------------
  /* verilator lint_off UNUSEDSIGNAL */
  logic [31:0] branch_taken_0_w;
  logic [31:0] branch_taken_1_w;
  logic [31:0] branch_taken_2_w;
  logic [31:0] branch_taken_3_w;
  logic [31:0] branch_taken_4_w;
  logic [31:0] branch_taken_5_w;
  logic [31:0] branch_taken_6_w;
  logic [31:0] branch_taken_7_w;
  /* verilator lint_on UNUSEDSIGNAL */

  // Truncate each 32-bit core output down to the reference port width.
  assign branch_taken_o[0] = branch_taken_0_w[0];
  assign branch_taken_o[1] = branch_taken_1_w[0];
  assign branch_taken_o[2] = branch_taken_2_w[0];
  assign branch_taken_o[3] = branch_taken_3_w[0];
  assign branch_taken_o[4] = branch_taken_4_w[0];
  assign branch_taken_o[5] = branch_taken_5_w[0];
  assign branch_taken_o[6] = branch_taken_6_w[0];
  assign branch_taken_o[7] = branch_taken_7_w[0];

  // ---------------------------------------------------------------------
  // Bambu HLS core instance — plain-Verilog, machine-generated.
  // ---------------------------------------------------------------------
  vector_alu u_core (
      .clock (clk),
      .reset (rst_n),  // both async active-low — direct, no inversion

      .start_port (start_i),
      .done_port  (done_o),

      // Data inputs — zero-extended from the reference's narrower widths
      // up to the core's [31:0] scalar ports.
      .opcode       ({25'd0, opcode_i}),
      .funct3       ({29'd0, funct3_i}),
      .funct7       ({25'd0, funct7_i}),

      .rs1_0 (rs1_i[0]), .rs1_1 (rs1_i[1]), .rs1_2 (rs1_i[2]), .rs1_3 (rs1_i[3]),
      .rs1_4 (rs1_i[4]), .rs1_5 (rs1_i[5]), .rs1_6 (rs1_i[6]), .rs1_7 (rs1_i[7]),

      .rs2_0 (rs2_i[0]), .rs2_1 (rs2_i[1]), .rs2_2 (rs2_i[2]), .rs2_3 (rs2_i[3]),
      .rs2_4 (rs2_i[4]), .rs2_5 (rs2_i[5]), .rs2_6 (rs2_i[6]), .rs2_7 (rs2_i[7]),

      // Zero-extend the 12-bit raw immediate field — see the `imm_i`
      // convention note above.
      .imm          ({20'd0, imm_i}),
      .active_mask  ({24'd0, active_mask_i}),

      // Data outputs — result_N is already 32 bits/lane, direct connect.
      .result_0 (result_o[0]), .result_1 (result_o[1]),
      .result_2 (result_o[2]), .result_3 (result_o[3]),
      .result_4 (result_o[4]), .result_5 (result_o[5]),
      .result_6 (result_o[6]), .result_7 (result_o[7]),

      // branch_taken_N captured full-width, truncated above.
      .branch_taken_0 (branch_taken_0_w), .branch_taken_1 (branch_taken_1_w),
      .branch_taken_2 (branch_taken_2_w), .branch_taken_3 (branch_taken_3_w),
      .branch_taken_4 (branch_taken_4_w), .branch_taken_5 (branch_taken_5_w),
      .branch_taken_6 (branch_taken_6_w), .branch_taken_7 (branch_taken_7_w)
  );

endmodule
