// tb_mbist_soc_slice.sv
// DFT Stage 4 (beads claude_verilog_test-j41m.14 / j41m.10): the SoC-level MBIST integration on the REAL
// wrappers. Same wiring as soc_top (dft_ctrl -> soc_mbist -> sram_controller + npu_top), simulated with
// +define+SRAM_SKY130 so both wrappers instantiate their mem_collar and the Sky130 macro (here the
// fault-injecting stand-in with the real macro's name). sram_controller is driven over AXI4 by the BFM
// (prefix s_), the TAP over JTAG; the NPU's APB side is idle.
module tb_mbist_soc_slice (
    input  logic clk,
    input  logic rst_n,

    // sram_controller slave port (AXI4 BFM, prefix s)
    input  logic [3:0]  s_awid,
    input  logic [31:0] s_awaddr,
    input  logic [7:0]  s_awlen,
    input  logic [2:0]  s_awsize,
    input  logic [1:0]  s_awburst,
    input  logic        s_awvalid,
    output logic        s_awready,
    input  logic [31:0] s_wdata,
    input  logic [3:0]  s_wstrb,
    input  logic        s_wlast,
    input  logic        s_wvalid,
    output logic        s_wready,
    output logic [3:0]  s_bid,
    output logic [1:0]  s_bresp,
    output logic        s_bvalid,
    input  logic        s_bready,
    input  logic [3:0]  s_arid,
    input  logic [31:0] s_araddr,
    input  logic [7:0]  s_arlen,
    input  logic [2:0]  s_arsize,
    input  logic [1:0]  s_arburst,
    input  logic        s_arvalid,
    output logic        s_arready,
    output logic [3:0]  s_rid,
    output logic [31:0] s_rdata,
    output logic [1:0]  s_rresp,
    output logic        s_rlast,
    output logic        s_rvalid,
    input  logic        s_rready,

    // JTAG
    input  logic tck_i,
    input  logic tms_i,
    input  logic tdi_i,
    input  logic trst_ni,
    input  logic scan_clk_i,
    output logic tdo_o,
    output logic tdo_oe_o,

    output logic bist_en_o
);

    logic [28:0]  mbist_ctl;
    logic         mbist_wr;
    logic         mbist_rst_tck_n;
    logic         mbist_wr_ready;
    logic [138:0] mbist_status;
    logic         dft_scan_mode;
    logic         dft_scan_rst_n;
    /* verilator lint_off UNUSEDSIGNAL */
    logic         dft_scan_en;
    logic         dft_test_en;
    logic         dft_test_clk;
    logic         unused_force;
    /* verilator lint_on  UNUSEDSIGNAL */

    dft_ctrl u_dft_ctrl (
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
        .mbist_force_o     (unused_force),
        .mbist_rst_tck_n_o (mbist_rst_tck_n),
        .mbist_wr_ready_i  (mbist_wr_ready),
        .mbist_status_i    (mbist_status)
    );

    logic         mb_en;
    logic         mb_ce;
    logic         mb_we;
    logic [3:0]   mb_wmask;
    logic [9:0]   mb_addr;
    logic [31:0]  mb_din;
    logic [31:0]  mb_sram_dout0;
    logic [31:0]  mb_sram_dout1;
    logic [31:0]  mb_npu_dout0;
    /* verilator lint_off UNUSEDSIGNAL */
    logic         cpu_run;
    logic [25:0]  cpu_cfg;
    logic         cpu_ctl_rst_n;
    /* verilator lint_on  UNUSEDSIGNAL */

    soc_mbist #(
        .CPU_PRESENT (1'b0),
        .N_MEM       (2),
        .AW          (10),
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
        .core_clk_i       (clk),
        .core_rst_n_i     (rst_n),
        .bist_en_o        (mb_en),
        .b_ce_o           (mb_ce),
        .b_we_o           (mb_we),
        .b_wmask_o        (mb_wmask),
        .b_addr_o         (mb_addr),
        .b_din_o          (mb_din),
        .dout0_i          ({mb_npu_dout0, mb_sram_dout0}),
        .dout1_i          ({32'd0, mb_sram_dout1}),
        .cpu_clk_i        (clk),
        .cpu_rst_n_i      (rst_n),
        .cpu_run_o        (cpu_run),
        .cpu_cfg_o        (cpu_cfg),
        .cpu_ctl_rst_n_o  (cpu_ctl_rst_n),
        .cpu_status_i     (69'd0)
    );

    assign bist_en_o = mb_en;

    sram_controller #(
        .MEM_WORDS (1024)
    ) u_sram (
        .clk(clk), .rst_n(rst_n),
        .s_awid(s_awid), .s_awaddr(s_awaddr), .s_awlen(s_awlen), .s_awsize(s_awsize), .s_awburst(s_awburst),
        .s_awvalid(s_awvalid), .s_awready(s_awready),
        .s_wdata(s_wdata), .s_wstrb(s_wstrb), .s_wlast(s_wlast), .s_wvalid(s_wvalid), .s_wready(s_wready),
        .s_bid(s_bid), .s_bresp(s_bresp), .s_bvalid(s_bvalid), .s_bready(s_bready),
        .s_arid(s_arid), .s_araddr(s_araddr), .s_arlen(s_arlen), .s_arsize(s_arsize), .s_arburst(s_arburst),
        .s_arvalid(s_arvalid), .s_arready(s_arready),
        .s_rid(s_rid), .s_rdata(s_rdata), .s_rresp(s_rresp), .s_rlast(s_rlast), .s_rvalid(s_rvalid),
        .s_rready(s_rready),
        .mb_en_i(mb_en), .mb_ce_i(mb_ce), .mb_we_i(mb_we), .mb_wmask_i(mb_wmask), .mb_addr_i(mb_addr),
        .mb_din_i(mb_din), .mb_dout0_o(mb_sram_dout0), .mb_dout1_o(mb_sram_dout1)
    );

    // NPU: APB idle; only its weight-memory collar matters here.
    /* verilator lint_off UNUSEDSIGNAL */
    logic [31:0] npu_prdata;
    logic        npu_pready;
    logic        npu_pslverr;
    logic        npu_irq;
    /* verilator lint_on  UNUSEDSIGNAL */

    npu_top #(
        .ADDR_W (12)
    ) u_npu (
        .clk(clk), .rst_n(rst_n),
        .psel(1'b0), .penable(1'b0), .pwrite(1'b0), .paddr(12'd0), .pwdata(32'd0), .pstrb(4'd0),
        .prdata(npu_prdata), .pready(npu_pready), .pslverr(npu_pslverr), .irq_o(npu_irq),
        .mb_en_i(mb_en), .mb_ce_i(mb_ce), .mb_we_i(mb_we), .mb_wmask_i(mb_wmask), .mb_addr_i(mb_addr),
        .mb_din_i(mb_din), .mb_dout0_o(mb_npu_dout0)
    );

endmodule : tb_mbist_soc_slice
