// Minimal free-running testbench for a bounded GLS functional check of the
// rv32i_cpu_top hard macro (bead claude_verilog_test-b0t part B, coordinator
// extension request 2026-09-18). Unlike the vector_alu_hls check
// (tools/verif/gls/run_hls_seq_check.py), which used yosys `sim -r
// <stimulus.fst>` to replay a precomputed OPEN-LOOP waveform, the CPU macro
// has a fully reactive AXI4 instruction-fetch interface (variable-length
// bursts, ready/valid handshaking) that cannot be captured as a fixed
// replay file without already knowing the DUT's own cycle-accurate timing
// -- circular for a correctness check. Instead this file is read ALONGSIDE
// the DUT (gate netlist OR RTL) as ordinary Verilog and driven with yosys
// `sim -clock clk -n <N>` (no `-r`), i.e. a normal free-running simulation
// where this module's own always blocks are the stimulus generator. This
// sidesteps `sim -r`'s wire-matching-pass wall entirely (that pass is
// specific to `-r`'s file-based replay matching, not to `sim` in general).
//
// The AXI read slave below is a generic, burst-length-agnostic single-
// outstanding-transaction BFM: it accepts any arlen/arsize/arburst the DUT
// issues and serves consecutive words from a small ROM, so it does not
// encode any assumption about the DUT's actual cache-line burst size.
//
// Program (see tools/verif/gls/gen_cpu_check_rom.py for the encoder):
//   0x00: ADDI x1, x0, 5      -> x1 = 5
//   0x04: ADDI x2, x0, 7      -> x2 = 7
//   0x08: ADD  x3, x1, x2     -> x3 = 12   (reads x1, x2)
//   0x0c: ADD  x4, x3, x0     -> x4 = 12   (reads x3 -- exercises forwarding)
//   0x10: SW   x4, 0(x0)      -> mem[0] = 12 -- THE observable: this is a
//                                 clean, well-understood AXI write, unlike
//                                 the undocumented debug_rs1_data_o/
//                                 debug_rs2_data_o outputs (found empirically
//                                 to NOT be commit-aligned -- they read 0 at
//                                 every commit in this program, including
//                                 ADD x3,x1,x2's, so they are some other
//                                 pipeline stage's snapshot, not usable as a
//                                 commit-time operand probe without further
//                                 reverse engineering this macro's internal
//                                 debug bus, which is out of scope here).
//                                 axi_awaddr_o/axi_wdata_o directly show
//                                 whether the ALU/forwarding datapath
//                                 actually produced 12.
//   0x14: JAL  x0, 0          -> self-loop, parks PC once the program has
//                                 retired
// ROM is padded with more JAL x0,0 (0x0000006f) so any incidental
// speculative/prefetch reads past the program never see X.

`timescale 1ns/1ps

// clk_i/rst_n_i are top-level PORTS, driven by yosys `sim -clock clk_i
// -resetn rst_n_i -rstlen <N>` -- NOT by internal `initial`/`always #delay`
// constructs. yosys's `sim` command is fundamentally a cycle-based
// simulator; a self-clocking testbench using `always #5 clk = ~clk;` /
// `#55 rst_n_i = 1;` was tried first and silently did not advance real
// simulation time at all (confirmed: only a single t=0 event was ever
// recorded for clk_i in the output VCD) -- the documented, working usage
// model is top-level clock/reset PORTS driven by `-clock`/`-resetn`.
module tb_cpu_macro_check (clk_i, rst_n_i);
  input clk_i;
  input rst_n_i;
  localparam ROM_WORDS = 64;
  reg [31:0] rom [0:ROM_WORDS-1];

  reg ext_irq_i;
  reg timer_irq_i;

  // APB debug -- unused in this check, tied off.
  reg apb_psel_i = 1'b0;
  reg apb_penable_i = 1'b0;
  reg apb_pwrite_i = 1'b0;
  reg [11:0] apb_paddr_i = 12'b0;
  reg [31:0] apb_pwdata_i = 32'b0;
  wire apb_pready_o;
  wire apb_pslverr_o;
  wire [31:0] apb_prdata_o;

  // AXI read channel (instruction/data fetch) -- driven by the BFM below.
  wire axi_arvalid_o;
  wire [31:0] axi_araddr_o;
  wire [7:0] axi_arlen_o;
  wire [2:0] axi_arsize_o;
  wire [1:0] axi_arburst_o;
  reg axi_arready_i;
  wire axi_rready_o;
  reg axi_rvalid_i;
  reg [31:0] axi_rdata_i;
  reg [1:0] axi_rresp_i;
  reg axi_rlast_i;

  // AXI write channel -- always-ready sink; this program issues no stores.
  wire axi_awvalid_o;
  wire [31:0] axi_awaddr_o;
  wire [7:0] axi_awlen_o;
  wire [2:0] axi_awsize_o;
  wire [1:0] axi_awburst_o;
  reg axi_awready_i = 1'b1;
  wire axi_wvalid_o;
  wire [31:0] axi_wdata_o;
  wire [3:0] axi_wstrb_o;
  wire axi_wlast_o;
  reg axi_wready_i = 1'b1;
  wire axi_bready_o;
  reg axi_bvalid_i = 1'b1;
  reg [1:0] axi_bresp_i = 2'b00;

  // Observability (top-level outputs -- the check target).
  wire commit_valid_o;
  wire [31:0] commit_insn_o;
  wire [31:0] commit_pc_o;
  wire [31:0] debug_rs1_data_o;
  wire [31:0] debug_rs2_data_o;
  wire [3:0] debug_state_o;
  wire trap_taken_o;
  wire [3:0] trap_cause_o;
  wire debug_branch_taken_o;
  wire debug_ebreak_o;
  wire debug_pc_src_o;
  wire debug_take_branch_jump_o;

  rv32i_cpu_top dut (
    .apb_penable_i(apb_penable_i),
    .apb_pready_o(apb_pready_o),
    .apb_psel_i(apb_psel_i),
    .apb_pslverr_o(apb_pslverr_o),
    .apb_pwrite_i(apb_pwrite_i),
    .axi_arready_i(axi_arready_i),
    .axi_arvalid_o(axi_arvalid_o),
    .axi_awready_i(axi_awready_i),
    .axi_awvalid_o(axi_awvalid_o),
    .axi_bready_o(axi_bready_o),
    .axi_bvalid_i(axi_bvalid_i),
    .axi_rlast_i(axi_rlast_i),
    .axi_rready_o(axi_rready_o),
    .axi_rvalid_i(axi_rvalid_i),
    .axi_wlast_o(axi_wlast_o),
    .axi_wready_i(axi_wready_i),
    .axi_wvalid_o(axi_wvalid_o),
    .clk_i(clk_i),
    .commit_valid_o(commit_valid_o),
    .debug_branch_taken_o(debug_branch_taken_o),
    .debug_ebreak_o(debug_ebreak_o),
    .debug_pc_src_o(debug_pc_src_o),
    .debug_take_branch_jump_o(debug_take_branch_jump_o),
    .ext_irq_i(ext_irq_i),
    .rst_n_i(rst_n_i),
    .timer_irq_i(timer_irq_i),
    .trap_taken_o(trap_taken_o),
    .apb_paddr_i(apb_paddr_i),
    .apb_prdata_o(apb_prdata_o),
    .apb_pwdata_i(apb_pwdata_i),
    .axi_araddr_o(axi_araddr_o),
    .axi_arburst_o(axi_arburst_o),
    .axi_arlen_o(axi_arlen_o),
    .axi_arsize_o(axi_arsize_o),
    .axi_awaddr_o(axi_awaddr_o),
    .axi_awburst_o(axi_awburst_o),
    .axi_awlen_o(axi_awlen_o),
    .axi_awsize_o(axi_awsize_o),
    .axi_bresp_i(axi_bresp_i),
    .axi_rdata_i(axi_rdata_i),
    .axi_rresp_i(axi_rresp_i),
    .axi_wdata_o(axi_wdata_o),
    .axi_wstrb_o(axi_wstrb_o),
    .commit_insn_o(commit_insn_o),
    .commit_pc_o(commit_pc_o),
    .debug_rs1_data_o(debug_rs1_data_o),
    .debug_rs2_data_o(debug_rs2_data_o),
    .debug_state_o(debug_state_o),
    .trap_cause_o(trap_cause_o)
  );

  initial begin
    $readmemh("rom_cpu_check.hex", rom);
    ext_irq_i = 1'b0;
    timer_irq_i = 1'b0;
  end

  // Generic single-outstanding AXI read burst slave.
  reg [1:0] ar_state; // 0=idle, 1=bursting
  reg [31:0] araddr_lat;
  reg [7:0] arlen_lat;
  reg [7:0] beat_cnt;

  always @(posedge clk_i or negedge rst_n_i) begin
    if (!rst_n_i) begin
      ar_state <= 2'd0;
      axi_rvalid_i <= 1'b0;
      beat_cnt <= 8'd0;
      araddr_lat <= 32'd0;
      arlen_lat <= 8'd0;
    end else begin
      case (ar_state)
        2'd0: begin
          axi_rvalid_i <= 1'b0;
          if (axi_arvalid_o && axi_arready_i) begin
            araddr_lat <= axi_araddr_o;
            arlen_lat <= axi_arlen_o;
            beat_cnt <= 8'd0;
            ar_state <= 2'd1;
            axi_rvalid_i <= 1'b1;
          end
        end
        2'd1: begin
          if (axi_rvalid_i && axi_rready_o) begin
            if (beat_cnt == arlen_lat) begin
              axi_rvalid_i <= 1'b0;
              ar_state <= 2'd0;
            end else begin
              beat_cnt <= beat_cnt + 8'd1;
            end
          end
        end
        default: ar_state <= 2'd0;
      endcase
    end
  end

  always @(*) begin
    axi_arready_i = (ar_state == 2'd0);
    axi_rresp_i = 2'b00;
    axi_rlast_i = (beat_cnt == arlen_lat);
    axi_rdata_i = rom[((araddr_lat[31:2] + beat_cnt)) % ROM_WORDS];
  end

  // One-shot APB debug sequencer: after the program has had plenty of time
  // to retire and park at its self-loop, (1) write DBG_CTRL[0]=1 (halt
  // request, address 0x000) -- docs/readme/DEBUG_INTERFACE.md documents
  // GPR reads alongside "debug writes only allowed when halted", and an
  // unhalted read empirically returned a value (0x30) that did not match
  // any expected register, suggesting reads are also halt-gated -- then
  // (2) read DBG_GPR[4] (address 0x010 + 4*4 = 0x020) to observe x4's final
  // architectural value directly. This is a documented interface, unlike
  // debug_rs1_data_o/debug_rs2_data_o (found empirically to not be
  // commit-aligned) and unlike the AXI write channel (never activates: the
  // D$ is write-back per docs/design/PHASE3_ARCHITECTURE_SPEC.md, so a
  // single SW does not itself generate an AXI write, only a cache-line
  // dirty mark).
  localparam HALT_START_CYC = 40;
  localparam READ_START_CYC = 80;
  localparam [11:0] DBG_CTRL_ADDR = 12'h000;
  localparam [11:0] DBG_GPR4_ADDR = 12'h020;
  reg [31:0] cyc_cnt;
  reg apb_halt_done;
  reg apb_prdata_captured_valid;
  reg [31:0] apb_prdata_captured;

  always @(posedge clk_i or negedge rst_n_i) begin
    if (!rst_n_i) begin
      cyc_cnt <= 32'd0;
      apb_psel_i <= 1'b0;
      apb_penable_i <= 1'b0;
      apb_pwrite_i <= 1'b0;
      apb_paddr_i <= 12'd0;
      apb_pwdata_i <= 32'd0;
      apb_halt_done <= 1'b0;
      apb_prdata_captured_valid <= 1'b0;
      apb_prdata_captured <= 32'd0;
    end else begin
      cyc_cnt <= cyc_cnt + 32'd1;
      if (cyc_cnt == HALT_START_CYC) begin
        apb_psel_i <= 1'b1;
        apb_penable_i <= 1'b0;
        apb_pwrite_i <= 1'b1;
        apb_paddr_i <= DBG_CTRL_ADDR;
        apb_pwdata_i <= 32'h1;
      end else if (cyc_cnt == HALT_START_CYC + 1) begin
        apb_penable_i <= 1'b1;
      end else if (apb_psel_i && apb_penable_i && apb_pwrite_i && apb_pready_o && !apb_halt_done) begin
        apb_halt_done <= 1'b1;
        apb_psel_i <= 1'b0;
        apb_penable_i <= 1'b0;
        apb_pwrite_i <= 1'b0;
      end else if (cyc_cnt == READ_START_CYC) begin
        apb_psel_i <= 1'b1;
        apb_penable_i <= 1'b0;
        apb_pwrite_i <= 1'b0;
        apb_paddr_i <= DBG_GPR4_ADDR;
      end else if (cyc_cnt == READ_START_CYC + 1) begin
        apb_penable_i <= 1'b1;
      end else if (apb_psel_i && apb_penable_i && !apb_pwrite_i && apb_pready_o && !apb_prdata_captured_valid) begin
        apb_prdata_captured <= apb_prdata_o;
        apb_prdata_captured_valid <= 1'b1;
        apb_psel_i <= 1'b0;
        apb_penable_i <= 1'b0;
      end
    end
  end

endmodule
