// tb_mbist_cpu_macro.sv
// DFT Stage 4 (bead claude_verilog_test-c54a, DFT_ARCHITECTURE.md 16.7): the REAL CPU hard-macro MBIST path.
//
//   dft_ctrl (jtag_tap) --MBIST_CTRL/STATUS--> soc_mbist (CPU_PRESENT = 1: cpu_core_clk control-word crossing,
//       status return) --mbist_run_i / mbist_cfg_i--> rv32i_cpu_top --mbist_status_o--> soc_mbist
//   rv32i_cpu_top is built with +define+SRAM_SKY130: its mbist_ctrl (N_MEM = 10, AW = 8, reset-free) drives the ten
//   mem_collar instances of the I$ / D$ in front of ten fault-injecting stand-ins that carry the real
//   sky130_sram_1kbyte_1rw1r_32x256_8 module name (sram_fi_core).
//
// The macro clock is cpu_gated_clk: clk_i through an rv32i_clock_gate whose enable is the PMU stand-in
// pmu_clk_en_i OR the TAP-launched mbist_force (soc_top: cpu_cg_en), so the suite can prove that an MBIST run
// opens a PMU-closed gate. The core-domain controller is not built (soc_mbist N_MEM = 1, memory data tied 0, never
// selected: dom_core = 0). The AXI master is parked (every ready/valid input 0): the CPU idles after its first
// fetch request, which is all this bench needs; CPU function with the collars in the loop is proven separately
// (tools/verif/gls/sky130 RTL arm vs the pre-change RTL).
module tb_mbist_cpu_macro (
    input  logic tck_i,
    input  logic tms_i,
    input  logic tdi_i,
    input  logic trst_ni,
    input  logic scan_clk_i,   // idle low
    output logic tdo_o,
    output logic tdo_oe_o,

    input  logic clk_i,        // ungated CPU clock (cpu_core_clk)
    input  logic rst_n_i,      // CPU-domain reset (cpu_domain_rst_n)
    input  logic pmu_clk_en_i, // stand-in for cpu_gated_clk_en
    input  logic pmu_rst_n_i,  // stand-in for the PMU-driven part of cpu_domain_rst_n (macro reset only; the MBIST holding register is NOT reset by it)
    output logic gclk_o,       // the macro's clk_i
    output logic mbist_force_o,
    output logic bist_en_o,    // the macro controller's collar select (hierarchical alias)
    output logic arvalid_o     // the parked CPU still asks for a fetch: proves the macro is alive
);

    logic [28:0]  mbist_ctl;
    logic         mbist_wr;
    logic         mbist_rst_tck_n;
    logic         mbist_wr_ready;
    logic [138:0] mbist_status;
    logic         dft_scan_mode;
    logic         dft_scan_en;
    logic         dft_scan_rst_n;
    logic         dft_test_en;
    logic         dft_test_clk;

    dft_ctrl u_dft (
        .scan_mode_i       (1'b0),
        .scan_en_i         (1'b0),
        .scan_rst_ni       (1'b1),
        .scan_clk_i        (scan_clk_i),
        .tck_i             (tck_i),
        .tms_i             (tms_i),
        .tdi_i             (tdi_i),
        .trst_ni           (trst_ni),
        .tdo_o             (tdo_o),
        .tdo_oe_o          (tdo_oe_o),
        .scan_mode_o       (dft_scan_mode),
        .scan_en_o         (dft_scan_en),
        .scan_rst_no       (dft_scan_rst_n),
        .test_en_o         (dft_test_en),
        .test_clk_o        (dft_test_clk),
        .mbist_ctl_o       (mbist_ctl),
        .mbist_wr_o        (mbist_wr),
        .mbist_force_o     (mbist_force_o),
        .mbist_rst_tck_n_o (mbist_rst_tck_n),
        .mbist_wr_ready_i  (mbist_wr_ready),
        .mbist_status_i    (mbist_status)
    );

    logic        cpu_run;
    logic [25:0] cpu_cfg;
    logic [68:0] cpu_status;
    /* verilator lint_off UNUSEDSIGNAL */
    logic        cpu_ctl_rst_n;
    logic        core_bist_en;
    logic        core_ce;
    logic        core_we;
    logic [3:0]  core_wmask;
    logic [1:0]  core_addr;
    logic [31:0] core_din;
    /* verilator lint_on  UNUSEDSIGNAL */

    soc_mbist #(
        .CPU_PRESENT (1'b1),
        .N_MEM       (1),
        .AW          (2),
        .P1_MASK     (1'b0)
    ) u_mbist (
        .tck_i            (tck_i),
        .rst_tck_n_i      (mbist_rst_tck_n),
        .mbist_ctl_i      (mbist_ctl),
        .mbist_wr_i       (mbist_wr),
        .mbist_wr_ready_o (mbist_wr_ready),
        .mbist_status_o   (mbist_status),
        .trst_ni          (trst_ni),
        .scan_mode_i      (dft_scan_mode),
        .scan_rst_ni      (dft_scan_rst_n),
        .core_clk_i       (clk_i),
        .core_rst_n_i     (rst_n_i),
        .bist_en_o        (core_bist_en),
        .b_ce_o           (core_ce),
        .b_we_o           (core_we),
        .b_wmask_o        (core_wmask),
        .b_addr_o         (core_addr),
        .b_din_o          (core_din),
        .dout0_i          (32'd0),
        .dout1_i          (32'd0),
        .cpu_clk_i        (clk_i),
        .cpu_rst_n_i      (rst_n_i),
        .cpu_run_o        (cpu_run),
        .cpu_cfg_o        (cpu_cfg),
        .cpu_ctl_rst_n_o  (cpu_ctl_rst_n),
        .cpu_status_i     (cpu_status)
    );

    // CPU clock gate: PMU enable OR the TAP-launched MBIST force (soc_top cpu_cg_en), test_en as in soc_top.
    logic cg_en;
    assign cg_en = pmu_clk_en_i | mbist_force_o | cpu_status[0] | cpu_status[1];  // soc_top: cpu_mbist_busy

    rv32i_clock_gate #(.HARD_ROOT(1'b0)) u_cpu_cg (
        .en      (cg_en),
        .test_en (dft_test_en),
        .clk     (clk_i),
        .gclk    (gclk_o)
    );

    /* verilator lint_off UNUSEDSIGNAL */
    logic [31:0] axi_awaddr, axi_wdata, axi_araddr, commit_pc, commit_insn, dbg_rs1, dbg_rs2, apb_prdata;
    logic [7:0]  axi_awlen, axi_arlen;
    logic [2:0]  axi_awsize, axi_arsize;
    logic [1:0]  axi_awburst, axi_arburst;
    logic [3:0]  axi_wstrb, trap_cause, dbg_state;
    logic        axi_awvalid, axi_wlast, axi_wvalid, axi_bready, axi_rready;
    logic        apb_pready, apb_pslverr, commit_valid, trap_taken;
    logic        dbg_br, dbg_tbj, dbg_pcsrc, dbg_ebreak;
    logic [1:0]  scan_out;
    /* verilator lint_on  UNUSEDSIGNAL */

    logic macro_rst_n;
    assign macro_rst_n = rst_n_i & pmu_rst_n_i;   // soc_top: cpu_domain_rst_n

    rv32i_cpu_top #(
        .RESET_PC (32'h0000_1000)
    ) u_cpu (
        .clk_i                    (gclk_o),
        .rst_n_i                  (macro_rst_n),
        .axi_awaddr_o             (axi_awaddr),
        .axi_awlen_o              (axi_awlen),
        .axi_awsize_o             (axi_awsize),
        .axi_awburst_o            (axi_awburst),
        .axi_awvalid_o            (axi_awvalid),
        .axi_awready_i            (1'b0),
        .axi_wdata_o              (axi_wdata),
        .axi_wstrb_o              (axi_wstrb),
        .axi_wlast_o              (axi_wlast),
        .axi_wvalid_o             (axi_wvalid),
        .axi_wready_i             (1'b0),
        .axi_bresp_i              (2'b00),
        .axi_bvalid_i             (1'b0),
        .axi_bready_o             (axi_bready),
        .axi_araddr_o             (axi_araddr),
        .axi_arlen_o              (axi_arlen),
        .axi_arsize_o             (axi_arsize),
        .axi_arburst_o            (axi_arburst),
        .axi_arvalid_o            (arvalid_o),
        .axi_arready_i            (1'b0),
        .axi_rdata_i              (32'd0),
        .axi_rresp_i              (2'b00),
        .axi_rvalid_i             (1'b0),
        .axi_rlast_i              (1'b0),
        .axi_rready_o             (axi_rready),
        .apb_paddr_i              (12'd0),
        .apb_psel_i               (1'b0),
        .apb_penable_i            (1'b0),
        .apb_pwrite_i             (1'b0),
        .apb_pwdata_i             (32'd0),
        .apb_prdata_o             (apb_prdata),
        .apb_pready_o             (apb_pready),
        .apb_pslverr_o            (apb_pslverr),
        .commit_valid_o           (commit_valid),
        .commit_pc_o              (commit_pc),
        .commit_insn_o            (commit_insn),
        .trap_taken_o             (trap_taken),
        .trap_cause_o             (trap_cause),
        .debug_rs1_data_o         (dbg_rs1),
        .debug_rs2_data_o         (dbg_rs2),
        .debug_branch_taken_o     (dbg_br),
        .debug_take_branch_jump_o (dbg_tbj),
        .debug_pc_src_o           (dbg_pcsrc),
        .debug_state_o            (dbg_state),
        .debug_ebreak_o           (dbg_ebreak),
        .ext_irq_i                (1'b0),
        .timer_irq_i              (1'b0),
        .scan_mode_i              (dft_scan_mode),
        .scan_en_i                (dft_scan_en),
        .scan_in_i                (2'b00),
        .scan_out_o               (scan_out),
        .mbist_run_i              (cpu_run),
        .mbist_cfg_i              (cpu_cfg),
        .mbist_status_o           (cpu_status)
    );

    assign bist_en_o = u_cpu.mb_en_w;

endmodule : tb_mbist_cpu_macro
