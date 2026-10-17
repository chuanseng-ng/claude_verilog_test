// soc_mbist.sv
// DFT Stage 4 (beads claude_verilog_test-j41m.14 / j41m.10, GH #244): SoC-level MBIST integration.
// Specification: docs/design/DFT_ARCHITECTURE.md section 16.
//
// Contains, for the CORE domain (core_clk: sram_controller + NPU weight memory): the control-word crossing
// (mbist_xing), the mbist_ctrl and the status return (mbist_status_sync). The collars stay in the memory
// wrappers; this module drives them through ONE broadcast bus and reads the macro outputs.
//
// CPU domain (CPU_PRESENT = 1): the control-word crossing into cpu_core_clk and the status return only. The
// CPU-domain controller and the ten cache collars live INSIDE the CPU hard macro (section 16.7), so this
// module exports the holding-register outputs (cpu_run_o / cpu_cfg_o / cpu_ctl_rst_n_o) and takes the macro's
// status block (cpu_status_i). With CPU_PRESENT = 0 (the shipped value, until the CPU macro is re-hardened)
// nothing CPU-side exists: the CPU status block reads 0 and cpu_present reads 0.
//
// Lint target: verilator -Wall -Wno-IMPORTSTAR 0 errors 0 warnings.

module soc_mbist #(
    parameter bit                  CPU_PRESENT = 1'b0,
    parameter int unsigned         N_MEM       = 2,
    parameter int unsigned         AW          = 10,
    parameter logic [N_MEM-1:0]    P1_MASK     = '0
) (
    // ── TAP side (TCK domain) ────────────────────────────────────────────────
    input  logic         tck_i,
    input  logic         rst_tck_n_i,
    input  logic [28:0]  mbist_ctl_i,        // MBIST_CTRL update register
    input  logic         mbist_wr_i,         // write strobe
    output logic         mbist_wr_ready_o,
    output logic [138:0] mbist_status_o,     // {cpu block, core block, cpu_present}

    // ── Shared test controls ─────────────────────────────────────────────────
    input  logic         trst_ni,
    input  logic         scan_mode_i,
    input  logic         scan_rst_ni,

    // ── Core domain ──────────────────────────────────────────────────────────
    input  logic                 core_clk_i,
    input  logic                 core_rst_n_i,
    output logic                 bist_en_o,
    output logic                 b_ce_o,
    output logic                 b_we_o,
    output logic [3:0]           b_wmask_o,
    output logic [AW-1:0]        b_addr_o,
    output logic [31:0]          b_din_o,
    input  logic [N_MEM*32-1:0]  dout0_i,
    input  logic [N_MEM*32-1:0]  dout1_i,

    // ── CPU domain (CPU_PRESENT = 1; unused otherwise) ───────────────────────
    input  logic         cpu_clk_i,
    input  logic         cpu_rst_n_i,
    output logic         cpu_run_o,
    output logic [25:0]  cpu_cfg_o,
    output logic         cpu_ctl_rst_n_o,
    input  logic [68:0]  cpu_status_i
);

    // ── Core domain ──────────────────────────────────────────────────────────
    logic        core_wr_ready_w;
    logic        core_run_w;
    logic [25:0] core_cfg_w;
    logic        core_ctl_rst_n_w;
    logic [68:0] core_status_w;
    logic [68:0] core_status_tck_w;

    mbist_xing #(
        .CTL_W   (29),
        .DOM_BIT (27)
    ) u_xing_core (
        .tck_i       (tck_i),
        .rst_tck_n_i (rst_tck_n_i),
        .wr_valid_i  (mbist_wr_i),
        .wr_data_i   (mbist_ctl_i),
        .wr_ready_o  (core_wr_ready_w),
        .clk_dst_i   (core_clk_i),
        .dst_rst_n_i (core_rst_n_i),
        .trst_ni     (trst_ni),
        .scan_mode_i (scan_mode_i),
        .scan_rst_ni (scan_rst_ni),
        .rst_n_o     (core_ctl_rst_n_w),
        .run_o       (core_run_w),
        .cfg_o       (core_cfg_w)
    );

    mbist_ctrl #(
        .N_MEM   (N_MEM),
        .AW      (AW),
        .RD_LAT  (2),
        .P1_MASK (P1_MASK)
    ) u_ctrl_core (
        .clk_i     (core_clk_i),
        .rst_n_i   (core_ctl_rst_n_w),
        .run_i     (core_run_w),
        .cfg_i     (core_cfg_w),
        .bist_en_o (bist_en_o),
        .b_ce_o    (b_ce_o),
        .b_we_o    (b_we_o),
        .b_wmask_o (b_wmask_o),
        .b_addr_o  (b_addr_o),
        .b_din_o   (b_din_o),
        .dout0_i   (dout0_i),
        .dout1_i   (dout1_i),
        .status_o  (core_status_w)
    );

    mbist_status_sync #(
        .ST_W (69)
    ) u_stsync_core (
        .tck_i        (tck_i),
        .rst_tck_n_i  (rst_tck_n_i),
        .status_i     (core_status_w),
        .status_tck_o (core_status_tck_w)
    );

    // ── CPU domain ───────────────────────────────────────────────────────────
    logic        cpu_wr_ready_w;
    logic [68:0] cpu_status_tck_w;

    if (CPU_PRESENT) begin : g_cpu
        mbist_xing #(
            .CTL_W   (29),
            .DOM_BIT (28)
        ) u_xing_cpu (
            .tck_i       (tck_i),
            .rst_tck_n_i (rst_tck_n_i),
            .wr_valid_i  (mbist_wr_i),
            .wr_data_i   (mbist_ctl_i),
            .wr_ready_o  (cpu_wr_ready_w),
            .clk_dst_i   (cpu_clk_i),
            .dst_rst_n_i (cpu_rst_n_i),
            .trst_ni     (trst_ni),
            .scan_mode_i (scan_mode_i),
            .scan_rst_ni (scan_rst_ni),
            .rst_n_o     (cpu_ctl_rst_n_o),
            .run_o       (cpu_run_o),
            .cfg_o       (cpu_cfg_o)
        );

        mbist_status_sync #(
            .ST_W (69)
        ) u_stsync_cpu (
            .tck_i        (tck_i),
            .rst_tck_n_i  (rst_tck_n_i),
            .status_i     (cpu_status_i),
            .status_tck_o (cpu_status_tck_w)
        );
    end else begin : g_nocpu
        assign cpu_wr_ready_w   = 1'b1;
        assign cpu_status_tck_w = 69'd0;
        assign cpu_ctl_rst_n_o  = 1'b0;
        assign cpu_run_o        = 1'b0;
        assign cpu_cfg_o        = 26'd0;
        /* verilator lint_off UNUSEDSIGNAL */
        logic unused_cpu_w;
        assign unused_cpu_w = &{1'b0, cpu_clk_i, cpu_rst_n_i, cpu_status_i};
        /* verilator lint_on  UNUSEDSIGNAL */
    end

    assign mbist_wr_ready_o = core_wr_ready_w & cpu_wr_ready_w;
    assign mbist_status_o   = {cpu_status_tck_w, core_status_tck_w, CPU_PRESENT};

endmodule : soc_mbist
