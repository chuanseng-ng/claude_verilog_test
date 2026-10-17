// nexys_video_dbg.sv -- FPGA-only debug access for the Nexys Video prototype (bead hlrm.2, decision #3).
//
//   host (Vivado hw_manager, Tcl "create_hw_axi_txn") --JTAG--> jtag_axi_0 (AXI4-Lite master, 32/32)
//        --> axil_to_apb (repo RTL, reused unchanged) --> soc_top APB3 debug port (12-bit address)
//   + one ILA (ila_0, 75 MHz CPU clock).
//
// The two vendor IP modules (jtag_axi_0, ila_0) are NOT checked in: build.tcl creates them with
// create_ip/set_property (fpga/nexys_video/ip.tcl). Lint uses fpga/nexys_video/sim/ip_stubs.v.
//
// The APB debug port reaches the CPU debug registers (halt/step/GPR/PC) through apb_cdc_bridge inside soc_top; it is NOT
// a view of the peripheral map. Peripheral and memory access from the host needs the CPU (UART bootloader, hlrm.2 #4).
module nexys_video_dbg (
    input  logic        clk_sys_i,
    input  logic        rst_sys_n_i,
    input  logic        clk_cpu_i,

    output logic [11:0] apb_paddr_o,
    output logic        apb_psel_o,
    output logic        apb_penable_o,
    output logic        apb_pwrite_o,
    output logic [31:0] apb_pwdata_o,
    input  logic [31:0] apb_prdata_i,
    input  logic        apb_pready_i,
    input  logic        apb_pslverr_i,

    // observed-only signals for the ILAs
    input  logic        uart_tx_i,
    input  logic        uart_rx_i,
    input  logic        gpu_irq_i,
    input  logic        wdt_rst_req_i,
    input  logic        pll_locked_i,
    input  logic        cpu_pll_locked_i,
    input  logic        commit_valid_i,
    input  logic [31:0] commit_pc_i,
    input  logic [31:0] commit_insn_i
);
    // ---- JTAG-to-AXI master (AXI4-Lite)
    logic [31:0] awaddr, araddr, wdata, rdata;
    logic [2:0]  awprot, arprot;
    logic [3:0]  wstrb;
    logic [1:0]  bresp, rresp;
    logic        awvalid, awready, wvalid, wready, bvalid, bready, arvalid, arready, rvalid, rready;

    jtag_axi_0 u_jtag_axi (
        .aclk          (clk_sys_i),
        .aresetn       (rst_sys_n_i),
        .m_axi_awaddr  (awaddr),
        .m_axi_awprot  (awprot),
        .m_axi_awvalid (awvalid),
        .m_axi_awready (awready),
        .m_axi_wdata   (wdata),
        .m_axi_wstrb   (wstrb),
        .m_axi_wvalid  (wvalid),
        .m_axi_wready  (wready),
        .m_axi_bresp   (bresp),
        .m_axi_bvalid  (bvalid),
        .m_axi_bready  (bready),
        .m_axi_araddr  (araddr),
        .m_axi_arprot  (arprot),
        .m_axi_arvalid (arvalid),
        .m_axi_arready (arready),
        .m_axi_rdata   (rdata),
        .m_axi_rresp   (rresp),
        .m_axi_rvalid  (rvalid),
        .m_axi_rready  (rready)
    );

    // ---- AXI-Lite -> APB shim (rtl/soc/axil_to_apb.sv, unchanged)
    logic [31:0] paddr_full;
    logic [3:0]  pstrb_unused;
    /* verilator lint_off UNUSEDSIGNAL */
    logic [19:0] paddr_hi_unused;
    /* verilator lint_on UNUSEDSIGNAL */
    axil_to_apb #(.ADDR_W(32), .DW(32), .SW(4)) u_axil2apb (
        .clk            (clk_sys_i),
        .rst_n          (rst_sys_n_i),
        .s_axil_awaddr  (awaddr),
        .s_axil_awprot  (awprot),
        .s_axil_awvalid (awvalid),
        .s_axil_awready (awready),
        .s_axil_wdata   (wdata),
        .s_axil_wstrb   (wstrb),
        .s_axil_wvalid  (wvalid),
        .s_axil_wready  (wready),
        .s_axil_bresp   (bresp),
        .s_axil_bvalid  (bvalid),
        .s_axil_bready  (bready),
        .s_axil_araddr  (araddr),
        .s_axil_arprot  (arprot),
        .s_axil_arvalid (arvalid),
        .s_axil_arready (arready),
        .s_axil_rdata   (rdata),
        .s_axil_rresp   (rresp),
        .s_axil_rvalid  (rvalid),
        .s_axil_rready  (rready),
        .psel           (apb_psel_o),
        .penable        (apb_penable_o),
        .pwrite         (apb_pwrite_o),
        .paddr          (paddr_full),
        .pwdata         (apb_pwdata_o),
        .pstrb          (pstrb_unused),
        .prdata         (apb_prdata_i),
        .pready         (apb_pready_i),
        .pslverr        (apb_pslverr_i)
    );
    assign apb_paddr_o     = paddr_full[11:0];
    assign paddr_hi_unused = paddr_full[31:12];

    // ---- ILA: ONE core only. The free Vivado licence (BASIC) rejects a design with more than one ILA
    // ([Chipscope 16-620]; and at most 5 probes). It runs on the 75 MHz CPU clock, which samples the 50 MHz system-domain signals
    // (APB debug bus, UART, flags) without loss. The clocks are outputs of one MMCM, so the sys -> cpu probe paths are
    // related-clock paths; probe widths are fixed in ip.tcl, keep the two in step.
    // BASIC licence also caps an ILA at 5 probes ([Chipscope 16-620]), so the narrow signals share probe0.
    ila_0 u_ila (
        .clk     (clk_cpu_i),
        .probe0  ({apb_paddr_o,                                        // [23:12]
                   apb_psel_o, apb_penable_o, apb_pwrite_o, apb_pready_i, apb_pslverr_i, uart_tx_i, uart_rx_i,
                   gpu_irq_i, wdt_rst_req_i, pll_locked_i, cpu_pll_locked_i,   // [11:1]
                   commit_valid_i}),                                   // [0]
        .probe1  (apb_pwdata_o),                // [31:0]
        .probe2  (apb_prdata_i),                // [31:0]
        .probe3  (commit_pc_i),                 // [31:0]
        .probe4  (commit_insn_i)                // [31:0]
    );
endmodule
