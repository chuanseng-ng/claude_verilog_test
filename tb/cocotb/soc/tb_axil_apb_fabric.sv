// tb_axil_apb_fabric.sv
// Bead claude_verilog_test-8riq (GH #216 coverage gap) -- cocotb wrapper for the real SoC control
// fabric chain, with a scripted AXI-Lite slave and a scripted APB slave hanging off it so a test can
// stall every channel and inject every error response:
//
//   cocotb master (m_axil_*)
//        |
//   axi_lite_interconnect  (N_SLAVES = 2, single master, depth-1)
//        |-- ring slot 0  EXT AXI-Lite slave, 0x2000_1000..0x2000_1FFF -> ports x_axil_*  (cocotb-driven)
//        '-- ring slot 1  axil_to_apb bridge, 0x2000_2000..0x2000_7FFF
//                |
//             apb_interconnect (N_SLAVES = 3)
//                |-- apb slot 0  apb4_register_bank,  0x2000_2000..0x2000_2FFF
//                |-- apb slot 1  apb4_register_bank,  0x2000_3000..0x2000_3FFF
//                '-- apb slot 2  EXT APB slave,       0x2000_4000..0x2000_4FFF -> ports xp_*   (cocotb-driven)
//                   0x2000_5000..0x2000_7FFF is inside the bridge window but claimed by NO apb slave
//                   (the reserved-slot case: apb_interconnect answers pslverr_o=1).
//
// Ring addresses below 0x2000_1000 or above 0x2000_7FFF are unmapped at the ring level -> DECERR.
//
// This is the same module chain soc_bus builds (axi_lite_interconnect -> axil_to_apb ->
// apb_interconnect), so what is checked here is the real propagation path of SLVERR (APB pslverr ->
// axil_to_apb bresp/rresp -> ring response mux -> master) and DECERR (ring decode miss), not a stub.
//
// The two register banks are 8 registers each, ADDR_W = 12 (the low 12 bits of the absolute APB
// address), every register fully SW-writable.

`default_nettype none

module tb_axil_apb_fabric #(
    parameter int unsigned AW = 32,
    parameter int unsigned DW = 32,
    parameter int unsigned SW = 4
) (
    input  logic clk,
    input  logic rst_n,

    // ── Master port (cocotb) ─────────────────────────────────────────────────
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
    input  logic          m_axil_rready,

    // ── Ring slot 0: EXT AXI-Lite slave, named from the SLAVE's point of view ───
    output logic [AW-1:0] x_axil_awaddr,
    output logic          x_axil_awvalid,
    input  logic          x_axil_awready,
    output logic [DW-1:0] x_axil_wdata,
    output logic [SW-1:0] x_axil_wstrb,
    output logic          x_axil_wvalid,
    input  logic          x_axil_wready,
    input  logic [1:0]    x_axil_bresp,
    input  logic          x_axil_bvalid,
    output logic          x_axil_bready,
    output logic [AW-1:0] x_axil_araddr,
    output logic          x_axil_arvalid,
    input  logic          x_axil_arready,
    input  logic [DW-1:0] x_axil_rdata,
    input  logic [1:0]    x_axil_rresp,
    input  logic          x_axil_rvalid,
    output logic          x_axil_rready,

    // ── APB slot 2: EXT APB slave (observed outputs, driven responses) ─────────
    output logic          xp_psel,
    output logic          xp_penable,
    output logic          xp_pwrite,
    output logic [AW-1:0] xp_paddr,
    output logic [DW-1:0] xp_pwdata,
    output logic [SW-1:0] xp_pstrb,
    input  logic [DW-1:0] xp_prdata,
    input  logic          xp_pready,
    input  logic          xp_pslverr,

    // ── Bridge-side APB master signals, for per-slave routing checks ───────────
    output logic [2:0]    apb_psel_o
);

    localparam int unsigned NS_RING = 2;
    localparam int unsigned NS_APB  = 3;

    localparam logic [NS_RING-1:0][AW-1:0] RING_BASE  = {32'h2000_2000, 32'h2000_1000};
    localparam logic [NS_RING-1:0][AW-1:0] RING_LIMIT = {32'h2000_7FFF, 32'h2000_1FFF};

    // ── Ring <-> slave buses (packed 2D, as axi_lite_interconnect requires) ──────
    logic [NS_RING-1:0][AW-1:0] s_awaddr;  logic [NS_RING-1:0][2:0]  s_awprot;
    logic [NS_RING-1:0]         s_awvalid; logic [NS_RING-1:0]       s_awready;
    logic [NS_RING-1:0][DW-1:0] s_wdata;   logic [NS_RING-1:0][SW-1:0] s_wstrb;
    logic [NS_RING-1:0]         s_wvalid;  logic [NS_RING-1:0]       s_wready;
    logic [NS_RING-1:0][1:0]    s_bresp;   logic [NS_RING-1:0]       s_bvalid;
    logic [NS_RING-1:0]         s_bready;
    logic [NS_RING-1:0][AW-1:0] s_araddr;  logic [NS_RING-1:0][2:0]  s_arprot;
    logic [NS_RING-1:0]         s_arvalid; logic [NS_RING-1:0]       s_arready;
    logic [NS_RING-1:0][DW-1:0] s_rdata;   logic [NS_RING-1:0][1:0]  s_rresp;
    logic [NS_RING-1:0]         s_rvalid;  logic [NS_RING-1:0]       s_rready;

    axi_lite_interconnect #(
        .N_SLAVES  (NS_RING),
        .SLV_BASE  (RING_BASE),
        .SLV_LIMIT (RING_LIMIT)
    ) u_ring (
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

    // ── Ring slot 0 -> EXT ports ────────────────────────────────────────────────
    assign x_axil_awaddr  = s_awaddr[0];
    assign x_axil_awvalid = s_awvalid[0];
    assign s_awready[0]   = x_axil_awready;
    assign x_axil_wdata   = s_wdata[0];
    assign x_axil_wstrb   = s_wstrb[0];
    assign x_axil_wvalid  = s_wvalid[0];
    assign s_wready[0]    = x_axil_wready;
    assign s_bresp[0]     = x_axil_bresp;
    assign s_bvalid[0]    = x_axil_bvalid;
    assign x_axil_bready  = s_bready[0];
    assign x_axil_araddr  = s_araddr[0];
    assign x_axil_arvalid = s_arvalid[0];
    assign s_arready[0]   = x_axil_arready;
    assign s_rdata[0]     = x_axil_rdata;
    assign s_rresp[0]     = x_axil_rresp;
    assign s_rvalid[0]    = x_axil_rvalid;
    assign x_axil_rready  = s_rready[0];

    // AxPROT is not decoded anywhere (waived in coverage_waivers.txt); the unused slot-0 sinks are
    // kept so -Wall does not flag the packed-array bits.
    /* verilator lint_off UNUSEDSIGNAL */
    logic unused_ring;
    assign unused_ring = &{1'b0, s_awprot, s_arprot};
    /* verilator lint_on  UNUSEDSIGNAL */

    // ── Ring slot 1 -> axil_to_apb -> apb_interconnect ─────────────────────────────
    logic              b_psel, b_penable, b_pwrite;
    logic [AW-1:0]     b_paddr;
    logic [DW-1:0]     b_pwdata, b_prdata;
    logic [SW-1:0]     b_pstrb;
    logic              b_pready, b_pslverr;

    axil_to_apb #(.ADDR_W(AW), .DW(DW), .SW(SW)) u_bridge (
        .clk(clk), .rst_n(rst_n),
        .s_axil_awaddr (s_awaddr[1]), .s_axil_awprot(s_awprot[1]),
        .s_axil_awvalid(s_awvalid[1]), .s_axil_awready(s_awready[1]),
        .s_axil_wdata  (s_wdata[1]),   .s_axil_wstrb (s_wstrb[1]),
        .s_axil_wvalid (s_wvalid[1]),  .s_axil_wready(s_wready[1]),
        .s_axil_bresp  (s_bresp[1]),   .s_axil_bvalid(s_bvalid[1]),
        .s_axil_bready (s_bready[1]),
        .s_axil_araddr (s_araddr[1]),  .s_axil_arprot(s_arprot[1]),
        .s_axil_arvalid(s_arvalid[1]), .s_axil_arready(s_arready[1]),
        .s_axil_rdata  (s_rdata[1]),   .s_axil_rresp (s_rresp[1]),
        .s_axil_rvalid (s_rvalid[1]),  .s_axil_rready(s_rready[1]),
        .psel(b_psel), .penable(b_penable), .pwrite(b_pwrite), .paddr(b_paddr),
        .pwdata(b_pwdata), .pstrb(b_pstrb),
        .prdata(b_prdata), .pready(b_pready), .pslverr(b_pslverr)
    );

    typedef logic [AW-1:0] apb_addr_arr_t [NS_APB];
    localparam apb_addr_arr_t APB_BASE  = '{32'h2000_2000, 32'h2000_3000, 32'h2000_4000};
    localparam apb_addr_arr_t APB_LIMIT = '{32'h2000_2FFF, 32'h2000_3FFF, 32'h2000_4FFF};

    logic              p_psel    [NS_APB];
    logic              p_penable [NS_APB];
    logic              p_pwrite  [NS_APB];
    logic [AW-1:0]     p_paddr   [NS_APB];
    logic [DW-1:0]     p_pwdata  [NS_APB];
    logic [SW-1:0]     p_pstrb   [NS_APB];
    logic [DW-1:0]     p_prdata  [NS_APB];
    logic              p_pready  [NS_APB];
    logic              p_pslverr [NS_APB];

    apb_interconnect #(
        .N_SLAVES(NS_APB), .ADDR_W(AW), .DW(DW), .SW(SW),
        .SLV_BASE(APB_BASE), .SLV_LIMIT(APB_LIMIT)
    ) u_apb_ic (
        .psel_i(b_psel), .penable_i(b_penable), .pwrite_i(b_pwrite), .paddr_i(b_paddr),
        .pwdata_i(b_pwdata), .pstrb_i(b_pstrb),
        .prdata_o(b_prdata), .pready_o(b_pready), .pslverr_o(b_pslverr),
        .psel_o(p_psel), .penable_o(p_penable), .pwrite_o(p_pwrite), .paddr_o(p_paddr),
        .pwdata_o(p_pwdata), .pstrb_o(p_pstrb),
        .prdata_i(p_prdata), .pready_i(p_pready), .pslverr_i(p_pslverr)
    );

    assign apb_psel_o = {p_psel[2], p_psel[1], p_psel[0]};

    // ── APB slots 0 and 1: real register banks ────────────────────────────────────
    genvar gb;
    generate
        for (gb = 0; gb < 2; gb++) begin : g_bank
            /* verilator lint_off UNUSEDSIGNAL */
            logic [31:0] regs_o [8];
            /* verilator lint_on  UNUSEDSIGNAL */
            logic        hw_wen   [8];
            logic [31:0] hw_wdata [8];
            always_comb begin
                for (int unsigned i = 0; i < 8; i++) begin
                    hw_wen[i]   = 1'b0;
                    hw_wdata[i] = 32'b0;
                end
            end
            apb4_register_bank #(.N_REGS(8), .ADDR_W(12)) u_bank (
                .pclk(clk), .presetn(rst_n),
                .psel(p_psel[gb]), .penable(p_penable[gb]), .pwrite(p_pwrite[gb]),
                .paddr(p_paddr[gb][11:0]), .pwdata(p_pwdata[gb]), .pstrb(p_pstrb[gb]),
                .prdata(p_prdata[gb]), .pready(p_pready[gb]), .pslverr(p_pslverr[gb]),
                .regs_o(regs_o), .hw_wen_i(hw_wen), .hw_wdata_i(hw_wdata)
            );
        end
    endgenerate

    // ── APB slot 2: EXT ports ─────────────────────────────────────────────────────
    assign xp_psel    = p_psel[2];
    assign xp_penable = p_penable[2];
    assign xp_pwrite  = p_pwrite[2];
    assign xp_paddr   = p_paddr[2];
    assign xp_pwdata  = p_pwdata[2];
    assign xp_pstrb   = p_pstrb[2];
    assign p_prdata[2]  = xp_prdata;
    assign p_pready[2]  = xp_pready;
    assign p_pslverr[2] = xp_pslverr;

endmodule : tb_axil_apb_fabric

`default_nettype wire
