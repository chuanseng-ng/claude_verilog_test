// tb_mbist_tap.sv
// DFT Stage 4 (beads claude_verilog_test-j41m.14 / j41m.10): the TAP-driven MBIST path end to end, i.e. the
// soc_top wiring without the rest of the SoC:
//
//   dft_ctrl (jtag_tap + pin leg)  --MBIST_CTRL/STATUS-->  soc_mbist (CPU_PRESENT = 1)
//      core domain: mbist_ctrl (N_CORE memories) + collars + sram_fi_core, clock clk_core_i
//      CPU  domain: the controller that will live INSIDE the CPU macro (section 16.7), instantiated here
//                   with N_CPU memories, clock clk_cpu_i, fed from soc_mbist's cpu_run/cfg/ctl_rst ports
//
// The three clocks (TCK, core, CPU) are unrelated; the suite sweeps ratios. The CPU-domain half is the
// design of the follow-up that adds the collars to the CPU hard macro; running it here proves the CPU path
// of the crossing and the status return before any re-harden.
module tb_mbist_tap #(
    parameter int unsigned N_CORE = 2,
    parameter int unsigned AW_CORE = 6,
    parameter int unsigned N_CPU = 10,
    parameter int unsigned AW_CPU = 6
) (
    input  logic tck_i,
    input  logic tms_i,
    input  logic tdi_i,
    input  logic trst_ni,
    input  logic scan_clk_i,   // idle low (a constant would make the clock-switch latch trivial)
    output logic tdo_o,
    output logic tdo_oe_o,

    input  logic clk_core_i,
    input  logic rst_core_n_i,
    input  logic clk_cpu_i,
    input  logic rst_cpu_n_i,

    output logic core_bist_en_o,
    output logic cpu_bist_en_o,
    output logic mbist_force_o,
    output logic scan_mode_o
);

    // ── TAP + shared controls ────────────────────────────────────────────────
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

    assign scan_mode_o = dft_scan_mode;
    /* verilator lint_off UNUSEDSIGNAL */
    logic unused_w;
    assign unused_w = &{1'b0, dft_scan_en, dft_test_en, dft_test_clk};
    /* verilator lint_on  UNUSEDSIGNAL */

    // ── Core domain ──────────────────────────────────────────────────────────
    logic                  c_bist_en;
    logic                  c_ce;
    logic                  c_we;
    logic [3:0]            c_wmask;
    logic [AW_CORE-1:0]    c_addr;
    logic [31:0]           c_din;
    logic [N_CORE*32-1:0]  c_dout0;
    logic [N_CORE*32-1:0]  c_dout1;

    // ── CPU domain ───────────────────────────────────────────────────────────
    logic        cpu_run;
    logic [25:0] cpu_cfg;
    logic        cpu_ctl_rst_n;
    logic [68:0] cpu_status;
    logic        p_ce;
    logic        p_we;
    logic [3:0]  p_wmask;
    logic [AW_CPU-1:0] p_addr;
    logic [31:0] p_din;
    logic [N_CPU*32-1:0] p_dout0;
    logic [N_CPU*32-1:0] p_dout1;

    soc_mbist #(
        .CPU_PRESENT (1'b1),
        .N_MEM       (N_CORE),
        .AW          (AW_CORE),
        .P1_MASK     (2'b01)
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
        .core_clk_i       (clk_core_i),
        .core_rst_n_i     (rst_core_n_i),
        .bist_en_o        (c_bist_en),
        .b_ce_o           (c_ce),
        .b_we_o           (c_we),
        .b_wmask_o        (c_wmask),
        .b_addr_o         (c_addr),
        .b_din_o          (c_din),
        .dout0_i          (c_dout0),
        .dout1_i          (c_dout1),
        .cpu_clk_i        (clk_cpu_i),
        .cpu_rst_n_i      (rst_cpu_n_i),
        .cpu_run_o        (cpu_run),
        .cpu_cfg_o        (cpu_cfg),
        .cpu_ctl_rst_n_o  (cpu_ctl_rst_n),
        .cpu_status_i     (cpu_status)
    );

    assign core_bist_en_o = c_bist_en;

    genvar gc;
    generate
        for (gc = 0; gc < N_CORE; gc++) begin : g_core
            logic          csb0_m;
            logic          web0_m;
            logic [3:0]    wmask0_m;
            logic [AW_CORE-1:0] addr0_m;
            logic [31:0]   din0_m;
            logic          csb1_m;
            logic [AW_CORE-1:0] addr1_m;

            mem_collar #(.AW(AW_CORE), .HAS_P1(gc == 0)) u_collar (
                .bist_en_i  (c_bist_en),
                .b_ce_i     (c_ce),
                .b_we_i     (c_we),
                .b_wmask_i  (c_wmask),
                .b_addr_i   (c_addr),
                .b_din_i    (c_din),
                .csb0_f_i   (1'b1),
                .web0_f_i   (1'b1),
                .wmask0_f_i (4'hF),
                .addr0_f_i  ('0),
                .din0_f_i   (32'd0),
                .csb1_f_i   (1'b1),
                .addr1_f_i  ('0),
                .csb0_m_o   (csb0_m),
                .web0_m_o   (web0_m),
                .wmask0_m_o (wmask0_m),
                .addr0_m_o  (addr0_m),
                .din0_m_o   (din0_m),
                .csb1_m_o   (csb1_m),
                .addr1_m_o  (addr1_m)
            );

            sram_fi_core #(.AW(AW_CORE)) u_mem (
                .clk0   (clk_core_i),
                .csb0   (csb0_m),
                .web0   (web0_m),
                .wmask0 (wmask0_m),
                .addr0  (addr0_m),
                .din0   (din0_m),
                .dout0  (c_dout0[gc*32 +: 32]),
                .clk1   (clk_core_i),
                .csb1   (csb1_m),
                .addr1  (addr1_m),
                .dout1  (c_dout1[gc*32 +: 32])
            );
        end
    endgenerate

    // ── The CPU-domain controller (inside the CPU macro in the follow-up) ─────
    mbist_ctrl #(
        .N_MEM   (N_CPU),
        .AW      (AW_CPU),
        .RD_LAT  (2),
        .P1_MASK ('0)
    ) u_cpu_ctrl (
        .clk_i     (clk_cpu_i),
        .rst_n_i   (cpu_ctl_rst_n),
        .run_i     (cpu_run),
        .cfg_i     (cpu_cfg),
        .bist_en_o (cpu_bist_en_o),
        .b_ce_o    (p_ce),
        .b_we_o    (p_we),
        .b_wmask_o (p_wmask),
        .b_addr_o  (p_addr),
        .b_din_o   (p_din),
        .dout0_i   (p_dout0),
        .dout1_i   (p_dout1),
        .status_o  (cpu_status)
    );

    genvar gp;
    generate
        for (gp = 0; gp < N_CPU; gp++) begin : g_cpu
            logic          csb0_m;
            logic          web0_m;
            logic [3:0]    wmask0_m;
            logic [AW_CPU-1:0] addr0_m;
            logic [31:0]   din0_m;
            logic          csb1_m;
            logic [AW_CPU-1:0] addr1_m;

            mem_collar #(.AW(AW_CPU), .HAS_P1(1'b0)) u_collar (
                .bist_en_i  (cpu_bist_en_o),
                .b_ce_i     (p_ce),
                .b_we_i     (p_we),
                .b_wmask_i  (p_wmask),
                .b_addr_i   (p_addr),
                .b_din_i    (p_din),
                .csb0_f_i   (1'b1),
                .web0_f_i   (1'b1),
                .wmask0_f_i (4'hF),
                .addr0_f_i  ('0),
                .din0_f_i   (32'd0),
                .csb1_f_i   (1'b1),
                .addr1_f_i  ('0),
                .csb0_m_o   (csb0_m),
                .web0_m_o   (web0_m),
                .wmask0_m_o (wmask0_m),
                .addr0_m_o  (addr0_m),
                .din0_m_o   (din0_m),
                .csb1_m_o   (csb1_m),
                .addr1_m_o  (addr1_m)
            );

            sram_fi_core #(.AW(AW_CPU)) u_mem (
                .clk0   (clk_cpu_i),
                .csb0   (csb0_m),
                .web0   (web0_m),
                .wmask0 (wmask0_m),
                .addr0  (addr0_m),
                .din0   (din0_m),
                .dout0  (p_dout0[gp*32 +: 32]),
                .clk1   (clk_cpu_i),
                .csb1   (csb1_m),
                .addr1  (addr1_m),
                .dout1  (p_dout1[gp*32 +: 32])
            );
        end
    endgenerate

endmodule : tb_mbist_tap
