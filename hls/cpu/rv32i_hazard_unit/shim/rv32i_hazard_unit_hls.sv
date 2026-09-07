// rv32i_hazard_unit_hls.sv
// GH #119 — hand-written RTL vs Bambu HLS core PPA/QoR comparison shim.
//
// Purpose:
//   Adapts the port names/widths of the Bambu-generated `rv32i_hazard_unit`
//   HLS core (/nobackup/hls/out/rv32i_hazard_unit/rv32i_hazard_unit.v) to
//   the hand-written RTL interface defined in
//   rtl/cpu/core/rv32i_hazard_unit.sv, so that BOTH implementations can be
//   driven by the exact same, unmodified cocotb testbench
//   (tb/cocotb/cpu/test_hazard_unit.py). This module's data port list
//   (names/directions/widths) is byte-identical to the hand-written RTL's
//   (module name aside); four extra ports (clk, rst_n, start_i, done_o)
//   are added on top because the reference block is purely combinational
//   while the HLS core is a clocked, start/done-handshaked datapath. The
//   testbench detects the HLS arm via `hasattr(dut, "clk")`.
//
//   This shim is combinational wiring ONLY — no registers, no FSM, no
//   logic beyond zero-extension/truncation of ports. Shim area is reported
//   as a separate line in the PPA comparison and must stay zero-register.
//
// Width adaptation:
//   The reference block's 26 inputs are 5-bit (*_rd_addr / *_rs1_addr /
//   *_rs2_addr) or 1-bit (everything else); the HLS core widens every one
//   of its 26 inputs to [31:0] (Bambu's default scalar-port width) — each
//   is zero-extended at the instance port map.
//   The reference block's 28 outputs are 2-bit (fwd_a_sel, fwd_b_sel,
//   fwd_store_sel, fwd_a_sel_pre, fwd_b_sel_pre) or 1-bit (everything
//   else); the HLS core drives all 28 as [31:0] — each is captured in a
//   same-width internal wire and truncated to the reference's low bits via
//   a continuous assign (still wire-only: no registers, no always blocks).
//
// Coding rules:
//   * No #delays, no initial blocks, no real types
//   * Wire-only: zero registers, zero always blocks
//   * No `default_nettype` directive (Spyglass IND, CODING_GUIDELINES.md §1.3)
//
// Lint target: verilator -Wall -Wno-DECLFILENAME 0 errors 0 warnings on
//              this file (the wrapped HLS core is machine-generated and is
//              linted/waived separately — see GH #119).

module rv32i_hazard_unit_hls (
    input  logic clk,
    input  logic rst_n,

    // -----------------------------------------------------------------------
    // HLS start/done handshake — not present on the combinational reference.
    // -----------------------------------------------------------------------
    input  logic start_i,
    output logic done_o,

    // From ID/EX register (instruction currently in EX1a)
    input  logic [4:0]  id_ex_rs1_addr,
    input  logic [4:0]  id_ex_rs2_addr,
    input  logic [4:0]  id_ex_rd_addr,
    input  logic        id_ex_mem_rd,
    input  logic        id_ex_reg_wr_en,

    // From EX1b register (ex1a_ex1b_reg — instruction in EX1c, 1 cycle behind EX1a)
    // NOTE: port names keep "ex1b_" prefix for backward compatibility with rv32i_core.sv
    input  logic [4:0]  ex1b_rd_addr,
    input  logic        ex1b_reg_wr_en,
    input  logic        ex1b_mem_rd,

    // From EX1c register (ex1c_ex1b_reg — instruction in EX1b, 2 cycles behind EX1a)
    input  logic [4:0]  ex1c_rd_addr,
    input  logic        ex1c_reg_wr_en,
    input  logic        ex1c_mem_rd,

    // From EX1b2 register (ex1b_ex2_reg_q — instruction in EX2, 3 cycles behind EX1a; Run-23)
    input  logic [4:0]  ex1b2_rd_addr,
    input  logic        ex1b2_reg_wr_en,
    input  logic        ex1b2_mem_rd,

    // From EX/MEM register (instruction completing EX2 / entering MEM)
    input  logic [4:0]  ex_mem_rd_addr,
    input  logic        ex_mem_reg_wr_en,
    input  logic        ex_mem_mem_rd,

    // From MEM/WB register (instruction currently in WB)
    input  logic [4:0]  mem_wb_rd_addr,
    input  logic        mem_wb_reg_wr_en,

    // From IF/ID register (instruction currently in ID)
    input  logic [4:0]  if_id_rs1_addr,
    input  logic [4:0]  if_id_rs2_addr,

    // Cache stall indicators
    input  logic        if_cache_stall,
    input  logic        mem_cache_stall,

    // Branch/jump/trap flush (registered from EX1b stage)
    input  logic        ex_pc_redirect,

    // Misaligned trap flush (registered from MEM stage)
    input  logic        mem_trap_redirect,

    // JAL flush (from ID stage)
    input  logic        id_jal_taken,

    // Outputs — pipeline register control
    output logic        stall_pc,
    output logic        stall_if_id,
    output logic        stall_id_ex,
    output logic        stall_ex_mem,
    output logic        stall_ex1_ex2_o,
    output logic        stall_ex1a_ex1b_o,  // EX1a→EX1c FF stall (Run 17/20)
    output logic        stall_ex1c_ex1b_o,  // EX1c→EX1b FF stall (Run 20)
    output logic        flush_if_id,
    output logic        flush_id_ex,
    output logic        flush_ex_mem,
    output logic        flush_ex1_ex2_o,
    output logic        flush_ex1a_ex1b_o,  // EX1a→EX1c FF flush (Run 17/20)
    output logic        flush_ex1c_ex1b_o,  // EX1c→EX1b FF flush (Run 20)

    // Outputs — forwarding mux selects (for instruction in EX1a)
    // Encoding: 2'b00=regfile, 2'b01=EX2, 2'b10=WB, 2'b11=EX1c (highest non-load)
    // EX1b (ex1a_ex1b_reg) tier = 2'b11 (highest; re-used for EX1c source now)
    output logic [1:0]  fwd_a_sel,
    output logic [1:0]  fwd_b_sel,
    output logic [1:0]  fwd_store_sel,

    // EX1c forwarding tier (producer just completed EX1c / in EX1b now)
    // Encoding: 1'b1 = forward from ex1c_ex1b_reg; overrides EX2 but not EX1b tier
    output logic        fwd_a_ex1c,
    output logic        fwd_b_ex1c,
    output logic        fwd_store_ex1c,

    // EX1b2 forwarding tier (producer completed EX1b / in EX1b2 register now; Run-23)
    // Encoding: 1'b1 = forward from ex1b_ex2_reg_q; priority between EX1c and EX2 tiers
    output logic        fwd_a_ex1b2,
    output logic        fwd_b_ex1b2,
    output logic        fwd_store_ex1b2,

    // Pre-decoded forwarding selects (one cycle early, registered in rv32i_core)
    // Computed using if_id_rs*_addr (consumer in ID) vs producer addresses shifted one stage earlier
    output logic [1:0]  fwd_a_sel_pre,
    output logic        fwd_a_ex1c_pre,
    output logic        fwd_a_ex1b2_pre,
    output logic [1:0]  fwd_b_sel_pre,
    output logic        fwd_b_ex1c_pre,
    output logic        fwd_b_ex1b2_pre
);

  // ---------------------------------------------------------------------
  // 32-bit capture wires for every HLS core output, truncated below to the
  // reference block's actual widths. The upper bits are intentionally
  // discarded (the reference ports are 1-bit or 2-bit) — waive the
  // resulting unused-bits warnings rather than trusting the reader to
  // infer intent from silence.
  // ---------------------------------------------------------------------
  /* verilator lint_off UNUSEDSIGNAL */
  logic [31:0] stall_pc_w;
  logic [31:0] stall_if_id_w;
  logic [31:0] stall_id_ex_w;
  logic [31:0] stall_ex_mem_w;
  logic [31:0] stall_ex1_ex2_o_w;
  logic [31:0] stall_ex1a_ex1b_o_w;
  logic [31:0] stall_ex1c_ex1b_o_w;
  logic [31:0] flush_if_id_w;
  logic [31:0] flush_id_ex_w;
  logic [31:0] flush_ex_mem_w;
  logic [31:0] flush_ex1_ex2_o_w;
  logic [31:0] flush_ex1a_ex1b_o_w;
  logic [31:0] flush_ex1c_ex1b_o_w;
  logic [31:0] fwd_a_sel_w;
  logic [31:0] fwd_b_sel_w;
  logic [31:0] fwd_store_sel_w;
  logic [31:0] fwd_a_ex1c_w;
  logic [31:0] fwd_b_ex1c_w;
  logic [31:0] fwd_store_ex1c_w;
  logic [31:0] fwd_a_ex1b2_w;
  logic [31:0] fwd_b_ex1b2_w;
  logic [31:0] fwd_store_ex1b2_w;
  logic [31:0] fwd_a_sel_pre_w;
  logic [31:0] fwd_a_ex1c_pre_w;
  logic [31:0] fwd_a_ex1b2_pre_w;
  logic [31:0] fwd_b_sel_pre_w;
  logic [31:0] fwd_b_ex1c_pre_w;
  logic [31:0] fwd_b_ex1b2_pre_w;
  /* verilator lint_on UNUSEDSIGNAL */

  // Truncate each 32-bit core output down to the reference port width.
  assign stall_pc          = stall_pc_w[0];
  assign stall_if_id       = stall_if_id_w[0];
  assign stall_id_ex       = stall_id_ex_w[0];
  assign stall_ex_mem      = stall_ex_mem_w[0];
  assign stall_ex1_ex2_o   = stall_ex1_ex2_o_w[0];
  assign stall_ex1a_ex1b_o = stall_ex1a_ex1b_o_w[0];
  assign stall_ex1c_ex1b_o = stall_ex1c_ex1b_o_w[0];
  assign flush_if_id       = flush_if_id_w[0];
  assign flush_id_ex       = flush_id_ex_w[0];
  assign flush_ex_mem      = flush_ex_mem_w[0];
  assign flush_ex1_ex2_o   = flush_ex1_ex2_o_w[0];
  assign flush_ex1a_ex1b_o = flush_ex1a_ex1b_o_w[0];
  assign flush_ex1c_ex1b_o = flush_ex1c_ex1b_o_w[0];
  assign fwd_a_sel         = fwd_a_sel_w[1:0];
  assign fwd_b_sel         = fwd_b_sel_w[1:0];
  assign fwd_store_sel     = fwd_store_sel_w[1:0];
  assign fwd_a_ex1c        = fwd_a_ex1c_w[0];
  assign fwd_b_ex1c        = fwd_b_ex1c_w[0];
  assign fwd_store_ex1c    = fwd_store_ex1c_w[0];
  assign fwd_a_ex1b2       = fwd_a_ex1b2_w[0];
  assign fwd_b_ex1b2       = fwd_b_ex1b2_w[0];
  assign fwd_store_ex1b2   = fwd_store_ex1b2_w[0];
  assign fwd_a_sel_pre     = fwd_a_sel_pre_w[1:0];
  assign fwd_a_ex1c_pre    = fwd_a_ex1c_pre_w[0];
  assign fwd_a_ex1b2_pre   = fwd_a_ex1b2_pre_w[0];
  assign fwd_b_sel_pre     = fwd_b_sel_pre_w[1:0];
  assign fwd_b_ex1c_pre    = fwd_b_ex1c_pre_w[0];
  assign fwd_b_ex1b2_pre   = fwd_b_ex1b2_pre_w[0];

  // ---------------------------------------------------------------------
  // Bambu HLS core instance — plain-Verilog, machine-generated.
  // ---------------------------------------------------------------------
  rv32i_hazard_unit u_core (
      .clock (clk),
      .reset (rst_n),  // both async active-low — direct, no inversion

      .start_port (start_i),
      .done_port  (done_o),

      // Data inputs — zero-extended from the reference's 5-bit/1-bit
      // widths up to the core's [31:0] scalar ports.
      .id_ex_rs1_addr    ({27'd0, id_ex_rs1_addr}),
      .id_ex_rs2_addr    ({27'd0, id_ex_rs2_addr}),
      .id_ex_rd_addr     ({27'd0, id_ex_rd_addr}),
      .id_ex_mem_rd      ({31'd0, id_ex_mem_rd}),
      .id_ex_reg_wr_en   ({31'd0, id_ex_reg_wr_en}),

      .ex1b_rd_addr      ({27'd0, ex1b_rd_addr}),
      .ex1b_reg_wr_en    ({31'd0, ex1b_reg_wr_en}),
      .ex1b_mem_rd       ({31'd0, ex1b_mem_rd}),

      .ex1c_rd_addr      ({27'd0, ex1c_rd_addr}),
      .ex1c_reg_wr_en    ({31'd0, ex1c_reg_wr_en}),
      .ex1c_mem_rd       ({31'd0, ex1c_mem_rd}),

      .ex1b2_rd_addr     ({27'd0, ex1b2_rd_addr}),
      .ex1b2_reg_wr_en   ({31'd0, ex1b2_reg_wr_en}),
      .ex1b2_mem_rd      ({31'd0, ex1b2_mem_rd}),

      .ex_mem_rd_addr    ({27'd0, ex_mem_rd_addr}),
      .ex_mem_reg_wr_en  ({31'd0, ex_mem_reg_wr_en}),
      .ex_mem_mem_rd     ({31'd0, ex_mem_mem_rd}),

      .mem_wb_rd_addr    ({27'd0, mem_wb_rd_addr}),
      .mem_wb_reg_wr_en  ({31'd0, mem_wb_reg_wr_en}),

      .if_id_rs1_addr    ({27'd0, if_id_rs1_addr}),
      .if_id_rs2_addr    ({27'd0, if_id_rs2_addr}),

      .if_cache_stall    ({31'd0, if_cache_stall}),
      .mem_cache_stall   ({31'd0, mem_cache_stall}),

      .ex_pc_redirect    ({31'd0, ex_pc_redirect}),
      .mem_trap_redirect ({31'd0, mem_trap_redirect}),
      .id_jal_taken      ({31'd0, id_jal_taken}),

      // Data outputs — captured full-width, truncated above.
      .stall_pc           (stall_pc_w),
      .stall_if_id        (stall_if_id_w),
      .stall_id_ex        (stall_id_ex_w),
      .stall_ex_mem       (stall_ex_mem_w),
      .stall_ex1_ex2_o    (stall_ex1_ex2_o_w),
      .stall_ex1a_ex1b_o  (stall_ex1a_ex1b_o_w),
      .stall_ex1c_ex1b_o  (stall_ex1c_ex1b_o_w),
      .flush_if_id        (flush_if_id_w),
      .flush_id_ex        (flush_id_ex_w),
      .flush_ex_mem       (flush_ex_mem_w),
      .flush_ex1_ex2_o    (flush_ex1_ex2_o_w),
      .flush_ex1a_ex1b_o  (flush_ex1a_ex1b_o_w),
      .flush_ex1c_ex1b_o  (flush_ex1c_ex1b_o_w),
      .fwd_a_sel          (fwd_a_sel_w),
      .fwd_b_sel          (fwd_b_sel_w),
      .fwd_store_sel      (fwd_store_sel_w),
      .fwd_a_ex1c         (fwd_a_ex1c_w),
      .fwd_b_ex1c         (fwd_b_ex1c_w),
      .fwd_store_ex1c     (fwd_store_ex1c_w),
      .fwd_a_ex1b2        (fwd_a_ex1b2_w),
      .fwd_b_ex1b2        (fwd_b_ex1b2_w),
      .fwd_store_ex1b2    (fwd_store_ex1b2_w),
      .fwd_a_sel_pre      (fwd_a_sel_pre_w),
      .fwd_a_ex1c_pre     (fwd_a_ex1c_pre_w),
      .fwd_a_ex1b2_pre    (fwd_a_ex1b2_pre_w),
      .fwd_b_sel_pre      (fwd_b_sel_pre_w),
      .fwd_b_ex1c_pre     (fwd_b_ex1c_pre_w),
      .fwd_b_ex1b2_pre    (fwd_b_ex1b2_pre_w)
  );

endmodule
