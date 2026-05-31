// tb_axi_lite_interconnect.sv
// Phase 5 (M3) — cocotb test wrapper for axi_lite_interconnect.
//
// Instantiates the 6-slave control interconnect with the real peripheral
// address map (soc_periph_map_pkg) and attaches six axi_lite_register_bank
// instances as the slaves.  This exercises BOTH new modules together: the BFM
// drives the CPU-side "m_axil_" master port; routing, isolation, DECERR and
// backpressure are observed end-to-end through real register banks.
//
// Slave map (soc_periph_map_pkg):
//   s0 GPU   0x2000_1000   s1 UART  0x2000_2000   s2 SPI 0x2000_3000
//   s3 Timer 0x2000_4000   s4 DMA   0x2000_5000   s5 IRQ 0x2000_6000
//   unmapped gap (e.g. 0x2000_0000 / 0x2000_7000) -> DECERR

module tb_axi_lite_interconnect #(
    parameter int unsigned AW     = axi_pkg::AXI_ADDR_WIDTH,
    parameter int unsigned DW     = axi_pkg::AXI_DATA_WIDTH,
    parameter int unsigned SW     = axi_pkg::AXI_STRB_WIDTH,
    parameter int unsigned N_REGS = 8,
    parameter int unsigned BANK_AW = 12
) (
    input  logic clk,
    input  logic rst_n,

    // ── CPU-side master port (BFM prefix "m_axil_") ──────────────────────────
    input  logic [AW-1:0] m_axil_awaddr,
    input  logic [2:0]    m_axil_awprot,
    input  logic          m_axil_awvalid,
    output logic          m_axil_awready,
    input  logic [DW-1:0] m_axil_wdata,
    input  logic [SW-1:0] m_axil_wstrb,
    input  logic          m_axil_wvalid,
    output logic          m_axil_wready,
    output logic [1:0]    m_axil_bresp,
    output logic          m_axil_bvalid,
    input  logic          m_axil_bready,
    input  logic [AW-1:0] m_axil_araddr,
    input  logic [2:0]    m_axil_arprot,
    input  logic          m_axil_arvalid,
    output logic          m_axil_arready,
    output logic [DW-1:0] m_axil_rdata,
    output logic [1:0]    m_axil_rresp,
    output logic          m_axil_rvalid,
    input  logic          m_axil_rready
);

    import soc_periph_map_pkg::*;

    localparam int unsigned NS = AXIL_N_SLAVES;   // 6

    // Interconnect <-> slave array buses.
    logic [AW-1:0] s_awaddr  [NS]; logic [2:0] s_awprot [NS];
    logic          s_awvalid [NS]; logic       s_awready[NS];
    logic [DW-1:0] s_wdata   [NS]; logic [SW-1:0] s_wstrb [NS];
    logic          s_wvalid  [NS]; logic       s_wready [NS];
    logic [1:0]    s_bresp   [NS]; logic       s_bvalid [NS]; logic s_bready[NS];
    logic [AW-1:0] s_araddr  [NS]; logic [2:0] s_arprot [NS];
    logic          s_arvalid [NS]; logic       s_arready[NS];
    logic [DW-1:0] s_rdata   [NS]; logic [1:0] s_rresp  [NS];
    logic          s_rvalid  [NS]; logic       s_rready [NS];

    axi_lite_interconnect #(
        .N_SLAVES  (NS),
        .SLV_BASE  (AXIL_SLV_BASE),
        .SLV_LIMIT (AXIL_SLV_LIMIT)
    ) u_axil_ic (
        .clk(clk), .rst_n(rst_n),
        .m_axil_awaddr(m_axil_awaddr), .m_axil_awprot(m_axil_awprot),
        .m_axil_awvalid(m_axil_awvalid), .m_axil_awready(m_axil_awready),
        .m_axil_wdata(m_axil_wdata), .m_axil_wstrb(m_axil_wstrb),
        .m_axil_wvalid(m_axil_wvalid), .m_axil_wready(m_axil_wready),
        .m_axil_bresp(m_axil_bresp), .m_axil_bvalid(m_axil_bvalid),
        .m_axil_bready(m_axil_bready),
        .m_axil_araddr(m_axil_araddr), .m_axil_arprot(m_axil_arprot),
        .m_axil_arvalid(m_axil_arvalid), .m_axil_arready(m_axil_arready),
        .m_axil_rdata(m_axil_rdata), .m_axil_rresp(m_axil_rresp),
        .m_axil_rvalid(m_axil_rvalid), .m_axil_rready(m_axil_rready),
        .s_axil_awaddr(s_awaddr), .s_axil_awprot(s_awprot),
        .s_axil_awvalid(s_awvalid), .s_axil_awready(s_awready),
        .s_axil_wdata(s_wdata), .s_axil_wstrb(s_wstrb),
        .s_axil_wvalid(s_wvalid), .s_axil_wready(s_wready),
        .s_axil_bresp(s_bresp), .s_axil_bvalid(s_bvalid), .s_axil_bready(s_bready),
        .s_axil_araddr(s_araddr), .s_axil_arprot(s_arprot),
        .s_axil_arvalid(s_arvalid), .s_axil_arready(s_arready),
        .s_axil_rdata(s_rdata), .s_axil_rresp(s_rresp),
        .s_axil_rvalid(s_rvalid), .s_axil_rready(s_rready)
    );

    // No hardware-side status injection in the interconnect testbench.
    logic        hw_wen_z   [N_REGS];
    logic [31:0] hw_wdata_z [N_REGS];
    always_comb begin
        for (int unsigned i = 0; i < N_REGS; i++) begin
            hw_wen_z  [i] = 1'b0;
            hw_wdata_z[i] = 32'b0;
        end
    end

    // Six register-bank slaves; each takes the low BANK_AW bits of the routed
    // 32-bit address.
    genvar gs;
    generate
    for (gs = 0; gs < NS; gs++) begin : g_bank
        /* verilator lint_off UNUSEDSIGNAL */
        logic [31:0] regs_o [N_REGS];
        /* verilator lint_on  UNUSEDSIGNAL */
        axi_lite_register_bank #(
            .N_REGS (N_REGS),
            .ADDR_W (BANK_AW)
        ) u_bank (
            .clk(clk), .rst_n(rst_n),
            .s_axil_awaddr (s_awaddr[gs][BANK_AW-1:0]),
            .s_axil_awprot (s_awprot[gs]),
            .s_axil_awvalid(s_awvalid[gs]), .s_axil_awready(s_awready[gs]),
            .s_axil_wdata  (s_wdata[gs]),   .s_axil_wstrb (s_wstrb[gs]),
            .s_axil_wvalid (s_wvalid[gs]),  .s_axil_wready(s_wready[gs]),
            .s_axil_bresp  (s_bresp[gs]),   .s_axil_bvalid(s_bvalid[gs]),
            .s_axil_bready (s_bready[gs]),
            .s_axil_araddr (s_araddr[gs][BANK_AW-1:0]),
            .s_axil_arprot (s_arprot[gs]),
            .s_axil_arvalid(s_arvalid[gs]), .s_axil_arready(s_arready[gs]),
            .s_axil_rdata  (s_rdata[gs]),   .s_axil_rresp (s_rresp[gs]),
            .s_axil_rvalid (s_rvalid[gs]),  .s_axil_rready(s_rready[gs]),
            .regs_o(regs_o), .hw_wen_i(hw_wen_z), .hw_wdata_i(hw_wdata_z)
        );
    end
    endgenerate

endmodule : tb_axi_lite_interconnect
