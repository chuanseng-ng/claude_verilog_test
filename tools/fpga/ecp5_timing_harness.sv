// ecp5_timing_harness.sv -- TIMING HARNESS, NOT SoC RTL (bead hlrm, FPGA Stage 0 ECP5 lower bound).
//
// Purpose: let nextpnr-ecp5 place and route the CPU-only soc_top on an LFE5U-85F-6BG381C with NO board pins.
// soc_top has 292 port bits (103 in, 189 out, 4 of the inputs are clocks); CABGA381 has 205 user IO, so the
// bare core cannot be pinned at all. This wrapper keeps the core byte-for-byte unchanged and replaces the pad
// interface by two thin shells, all clocked by clk_i:
//
//   * inputs : the 99 non-clock inputs come out of ONE serial shift register fed by a single pin `din`.
//              Every soc_top input bit is therefore driven by a real flop (no constant propagation can delete
//              logic behind a tied-off input), at the cost of 99 FFs.
//   * outputs: the 189 output bits are registered (189 FFs), folded 16:1 into 12 parity flops, then folded again
//              into the single pin `dout`. Every output bit that is not a constant stays observable, so yosys
//              keeps its whole cone, at the cost of ~200 FFs and ~70 LUT4 (depth <= 2 LUT levels per stage, far
//              below the core's own critical path, so it cannot set fmax).
//
// What this CUTS (and so what the resulting number does NOT cover): every pad-level path. No input-to-register or
// register-to-output path of the real top level is timed, no IO standard / pin / bank constraint exists, and the
// shells add ~300 FFs (about 2 % of the design) that are not in the real SoC. The four clock inputs
// (clk_i, cpu_clk_i, scan_clk_i, tck_i) stay real pins. Paths from the cpu_clk_i domain into the clk_i output
// shell (and clk_i shell -> cpu_clk_i domain) are real cross-domain paths in this netlist; nextpnr reports them
// separately from the per-clock fmax.
//
// Not synthesis input for any ASIC flow. Used only by tools/fpga/stage0_pnr_ecp5.sh.
module ecp5_timing_harness (
    input  logic clk_i,
    input  logic cpu_clk_i,
    input  logic scan_clk_i,
    input  logic tck_i,
    input  logic din,
    output logic dout
);
  localparam int unsigned NI = 99;
  localparam int unsigned NO = 189;
  localparam int unsigned NG = 12;  // 12 x 16 = 192 >= 189

  logic [NI-1:0] in_sr;
  always_ff @(posedge clk_i) in_sr <= {in_sr[NI-2:0], din};

  logic [NO-1:0] soc_out;

  // Input bit order below MUST mirror the soc_top port order; the output concatenation does the same. Only the
  // widths matter for timing (each bit is an independent flop), but keep them honest so the netlist is the core's.
  soc_top u_soc (
      .clk_i        (clk_i),
      .rst_n_i      (in_sr[0]),
      .cpu_clk_i    (cpu_clk_i),
      .cpu_rst_n_i  (in_sr[1]),
      .apb_paddr_i  (in_sr[13:2]),
      .apb_psel_i   (in_sr[14]),
      .apb_penable_i(in_sr[15]),
      .apb_pwrite_i (in_sr[16]),
      .apb_pwdata_i (in_sr[48:17]),
      .apb_prdata_o (soc_out[31:0]),
      .apb_pready_o (soc_out[32]),
      .apb_pslverr_o(soc_out[33]),
      .uart_tx_o    (soc_out[34]),
      .uart_rx_i    (in_sr[49]),
      .spi_sclk_o   (soc_out[35]),
      .spi_mosi_o   (soc_out[36]),
      .spi_miso_i   (in_sr[50]),
      .spi_cs_n_o   (soc_out[37]),
      .gpio_out_o   (soc_out[69:38]),
      .gpio_oe_o    (soc_out[101:70]),
      .gpio_in_i    (in_sr[82:51]),
      .pwm_o        (soc_out[105:102]),
      .wdt_rst_req_o(soc_out[106]),
      .i2c_scl_o    (soc_out[107]),
      .i2c_scl_oe_o (soc_out[108]),
      .i2c_scl_i    (in_sr[83]),
      .i2c_sda_o    (soc_out[109]),
      .i2c_sda_oe_o (soc_out[110]),
      .i2c_sda_i    (in_sr[84]),
      .commit_valid_o(soc_out[111]),
      .commit_pc_o  (soc_out[143:112]),
      .commit_insn_o(soc_out[175:144]),
      .gpu_irq_o    (soc_out[176]),
      .pll_locked_o (soc_out[177]),
      .cpu_pll_locked_o(soc_out[178]),
      .scan_mode_i  (in_sr[85]),
      .scan_en_i    (in_sr[86]),
      .scan_rst_ni  (in_sr[87]),
      .scan_clk_i   (scan_clk_i),
      .scan_in_i    (in_sr[95:88]),
      .scan_out_o   (soc_out[186:179]),
      .tck_i        (tck_i),
      .tms_i        (in_sr[96]),
      .tdi_i        (in_sr[97]),
      .trst_ni      (in_sr[98]),
      .tdo_o        (soc_out[187]),
      .tdo_oe_o     (soc_out[188])
  );

  logic [NO-1:0] out_q;
  logic [NG-1:0] grp_q;
  logic [(NG*16)-1:0] out_pad;
  always_comb begin
    out_pad = '0;
    out_pad[NO-1:0] = out_q;
  end

  always_ff @(posedge clk_i) begin
    out_q <= soc_out;
    for (int g = 0; g < NG; g++) grp_q[g] <= ^out_pad[g*16+:16];
    dout <= ^grp_q;
  end
endmodule
