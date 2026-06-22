// tb_axi4_crossbar.sv
// Phase 5 (M3) — cocotb test wrapper for axi4_crossbar.
//
// The crossbar uses parameterized unpacked-array ports, which cocotb cannot
// index conveniently.  This wrapper instantiates a fixed 3-master x 2-slave
// crossbar and breaks the arrays out into flat, prefix-named scalar ports
// (m0_*, m1_*, m2_*, s0_*, s1_*) so the AXI4 master BFM and AXI4 slave model
// can attach by prefix, exactly like the existing CPU/GPU testbenches.
//
// Slave map matches soc_addr_map_pkg:
//   s0 = ROM   0x0000_1000 .. 0x0000_1FFF
//   s1 = SRAM  0x0000_2000 .. 0x0FFF_FFFF

module tb_axi4_crossbar #(
    parameter int unsigned AW   = axi_pkg::AXI_ADDR_WIDTH,
    parameter int unsigned DW   = axi_pkg::AXI_DATA_WIDTH,
    parameter int unsigned SW   = axi_pkg::AXI_STRB_WIDTH,
    parameter int unsigned IW   = axi_pkg::AXI_ID_WIDTH,
    parameter int unsigned LENW = axi_pkg::AXI_LEN_WIDTH
) (
    input logic clk,
    input logic rst_n,

    // ── Master 0 ─────────────────────────────────────────────────────────────
    input  logic [AW-1:0]   m0_awaddr,  input logic [LENW-1:0] m0_awlen,
    input  logic [2:0]      m0_awsize,  input logic [1:0]      m0_awburst,
    input  logic            m0_awvalid, output logic           m0_awready,
    input  logic [DW-1:0]   m0_wdata,   input logic [SW-1:0]   m0_wstrb,
    input  logic            m0_wlast,   input logic            m0_wvalid,
    output logic            m0_wready,
    output logic [1:0]      m0_bresp,   output logic           m0_bvalid,
    input  logic            m0_bready,
    input  logic [AW-1:0]   m0_araddr,  input logic [LENW-1:0] m0_arlen,
    input  logic [2:0]      m0_arsize,  input logic [1:0]      m0_arburst,
    input  logic            m0_arvalid, output logic           m0_arready,
    output logic [DW-1:0]   m0_rdata,   output logic [1:0]     m0_rresp,
    output logic            m0_rlast,   output logic           m0_rvalid,
    input  logic            m0_rready,

    // ── Master 1 ─────────────────────────────────────────────────────────────
    input  logic [AW-1:0]   m1_awaddr,  input logic [LENW-1:0] m1_awlen,
    input  logic [2:0]      m1_awsize,  input logic [1:0]      m1_awburst,
    input  logic            m1_awvalid, output logic           m1_awready,
    input  logic [DW-1:0]   m1_wdata,   input logic [SW-1:0]   m1_wstrb,
    input  logic            m1_wlast,   input logic            m1_wvalid,
    output logic            m1_wready,
    output logic [1:0]      m1_bresp,   output logic           m1_bvalid,
    input  logic            m1_bready,
    input  logic [AW-1:0]   m1_araddr,  input logic [LENW-1:0] m1_arlen,
    input  logic [2:0]      m1_arsize,  input logic [1:0]      m1_arburst,
    input  logic            m1_arvalid, output logic           m1_arready,
    output logic [DW-1:0]   m1_rdata,   output logic [1:0]     m1_rresp,
    output logic            m1_rlast,   output logic           m1_rvalid,
    input  logic            m1_rready,

    // ── Master 2 ─────────────────────────────────────────────────────────────
    input  logic [AW-1:0]   m2_awaddr,  input logic [LENW-1:0] m2_awlen,
    input  logic [2:0]      m2_awsize,  input logic [1:0]      m2_awburst,
    input  logic            m2_awvalid, output logic           m2_awready,
    input  logic [DW-1:0]   m2_wdata,   input logic [SW-1:0]   m2_wstrb,
    input  logic            m2_wlast,   input logic            m2_wvalid,
    output logic            m2_wready,
    output logic [1:0]      m2_bresp,   output logic           m2_bvalid,
    input  logic            m2_bready,
    input  logic [AW-1:0]   m2_araddr,  input logic [LENW-1:0] m2_arlen,
    input  logic [2:0]      m2_arsize,  input logic [1:0]      m2_arburst,
    input  logic            m2_arvalid, output logic           m2_arready,
    output logic [DW-1:0]   m2_rdata,   output logic [1:0]     m2_rresp,
    output logic            m2_rlast,   output logic           m2_rvalid,
    input  logic            m2_rready,

    // ── Slave 0 (ROM) ────────────────────────────────────────────────────────
    output logic [IW-1:0]   s0_awid,    output logic [AW-1:0]  s0_awaddr,
    output logic [LENW-1:0] s0_awlen,   output logic [2:0]     s0_awsize,
    output logic [1:0]      s0_awburst, output logic           s0_awvalid,
    input  logic            s0_awready,
    output logic [DW-1:0]   s0_wdata,   output logic [SW-1:0]  s0_wstrb,
    output logic            s0_wlast,   output logic           s0_wvalid,
    input  logic            s0_wready,
    input  logic [IW-1:0]   s0_bid,     input logic [1:0]      s0_bresp,
    input  logic            s0_bvalid,  output logic           s0_bready,
    output logic [IW-1:0]   s0_arid,    output logic [AW-1:0]  s0_araddr,
    output logic [LENW-1:0] s0_arlen,   output logic [2:0]     s0_arsize,
    output logic [1:0]      s0_arburst, output logic           s0_arvalid,
    input  logic            s0_arready,
    input  logic [IW-1:0]   s0_rid,     input logic [DW-1:0]   s0_rdata,
    input  logic [1:0]      s0_rresp,   input logic            s0_rlast,
    input  logic            s0_rvalid,  output logic           s0_rready,

    // ── Slave 1 (SRAM) ───────────────────────────────────────────────────────
    output logic [IW-1:0]   s1_awid,    output logic [AW-1:0]  s1_awaddr,
    output logic [LENW-1:0] s1_awlen,   output logic [2:0]     s1_awsize,
    output logic [1:0]      s1_awburst, output logic           s1_awvalid,
    input  logic            s1_awready,
    output logic [DW-1:0]   s1_wdata,   output logic [SW-1:0]  s1_wstrb,
    output logic            s1_wlast,   output logic           s1_wvalid,
    input  logic            s1_wready,
    input  logic [IW-1:0]   s1_bid,     input logic [1:0]      s1_bresp,
    input  logic            s1_bvalid,  output logic           s1_bready,
    output logic [IW-1:0]   s1_arid,    output logic [AW-1:0]  s1_araddr,
    output logic [LENW-1:0] s1_arlen,   output logic [2:0]     s1_arsize,
    output logic [1:0]      s1_arburst, output logic           s1_arvalid,
    input  logic            s1_arready,
    input  logic [IW-1:0]   s1_rid,     input logic [DW-1:0]   s1_rdata,
    input  logic [1:0]      s1_rresp,   input logic            s1_rlast,
    input  logic            s1_rvalid,  output logic           s1_rready
);

    import soc_addr_map_pkg::*;

    localparam int unsigned NM = 3;
    localparam int unsigned NS = 2;

    // Packed 2D buses to match axi4_crossbar packed-2D ports (Synlig/UHDM fix).
    // Bit ordering: index [0] is LSBs, [N-1] is MSBs — packed 2D [N-1:0][W-1:0].
    // Fan-in/fan-out uses explicit slice assigns; no unpacked-array aggregates.
    logic [NM-1:0][AW-1:0]   m_awaddr;  logic [NM-1:0][LENW-1:0] m_awlen;
    logic [NM-1:0][2:0]      m_awsize;  logic [NM-1:0][1:0]      m_awburst;
    logic [NM-1:0]            m_awvalid; logic [NM-1:0]            m_awready;
    logic [NM-1:0][DW-1:0]   m_wdata;   logic [NM-1:0][SW-1:0]   m_wstrb;
    logic [NM-1:0]            m_wlast;   logic [NM-1:0]            m_wvalid;
    logic [NM-1:0]            m_wready;
    logic [NM-1:0][1:0]      m_bresp;   logic [NM-1:0]            m_bvalid;
    logic [NM-1:0]            m_bready;
    logic [NM-1:0][AW-1:0]   m_araddr;  logic [NM-1:0][LENW-1:0] m_arlen;
    logic [NM-1:0][2:0]      m_arsize;  logic [NM-1:0][1:0]      m_arburst;
    logic [NM-1:0]            m_arvalid; logic [NM-1:0]            m_arready;
    logic [NM-1:0][DW-1:0]   m_rdata;   logic [NM-1:0][1:0]      m_rresp;
    logic [NM-1:0]            m_rlast;   logic [NM-1:0]            m_rvalid;
    logic [NM-1:0]            m_rready;

    logic [NS-1:0][IW-1:0]   s_awid;    logic [NS-1:0][AW-1:0]   s_awaddr;
    logic [NS-1:0][LENW-1:0] s_awlen;   logic [NS-1:0][2:0]      s_awsize;
    logic [NS-1:0][1:0]      s_awburst; logic [NS-1:0]            s_awvalid;
    logic [NS-1:0]            s_awready;
    logic [NS-1:0][DW-1:0]   s_wdata;   logic [NS-1:0][SW-1:0]   s_wstrb;
    logic [NS-1:0]            s_wlast;   logic [NS-1:0]            s_wvalid;
    logic [NS-1:0]            s_wready;
    logic [NS-1:0][IW-1:0]   s_bid;     logic [NS-1:0][1:0]      s_bresp;
    logic [NS-1:0]            s_bvalid;  logic [NS-1:0]            s_bready;
    logic [NS-1:0][IW-1:0]   s_arid;    logic [NS-1:0][AW-1:0]   s_araddr;
    logic [NS-1:0][LENW-1:0] s_arlen;   logic [NS-1:0][2:0]      s_arsize;
    logic [NS-1:0][1:0]      s_arburst; logic [NS-1:0]            s_arvalid;
    logic [NS-1:0]            s_arready;
    logic [NS-1:0][IW-1:0]   s_rid;     logic [NS-1:0][DW-1:0]   s_rdata;
    logic [NS-1:0][1:0]      s_rresp;   logic [NS-1:0]            s_rlast;
    logic [NS-1:0]            s_rvalid;  logic [NS-1:0]            s_rready;

    // ── Master fan-in (scalar -> packed slice) ────────────────────────────────
    assign m_awaddr[0]  = m0_awaddr;  assign m_awaddr[1]  = m1_awaddr;  assign m_awaddr[2]  = m2_awaddr;
    assign m_awlen[0]   = m0_awlen;   assign m_awlen[1]   = m1_awlen;   assign m_awlen[2]   = m2_awlen;
    assign m_awsize[0]  = m0_awsize;  assign m_awsize[1]  = m1_awsize;  assign m_awsize[2]  = m2_awsize;
    assign m_awburst[0] = m0_awburst; assign m_awburst[1] = m1_awburst; assign m_awburst[2] = m2_awburst;
    assign m_awvalid[0] = m0_awvalid; assign m_awvalid[1] = m1_awvalid; assign m_awvalid[2] = m2_awvalid;
    assign m_wdata[0]   = m0_wdata;   assign m_wdata[1]   = m1_wdata;   assign m_wdata[2]   = m2_wdata;
    assign m_wstrb[0]   = m0_wstrb;   assign m_wstrb[1]   = m1_wstrb;   assign m_wstrb[2]   = m2_wstrb;
    assign m_wlast[0]   = m0_wlast;   assign m_wlast[1]   = m1_wlast;   assign m_wlast[2]   = m2_wlast;
    assign m_wvalid[0]  = m0_wvalid;  assign m_wvalid[1]  = m1_wvalid;  assign m_wvalid[2]  = m2_wvalid;
    assign m_bready[0]  = m0_bready;  assign m_bready[1]  = m1_bready;  assign m_bready[2]  = m2_bready;
    assign m_araddr[0]  = m0_araddr;  assign m_araddr[1]  = m1_araddr;  assign m_araddr[2]  = m2_araddr;
    assign m_arlen[0]   = m0_arlen;   assign m_arlen[1]   = m1_arlen;   assign m_arlen[2]   = m2_arlen;
    assign m_arsize[0]  = m0_arsize;  assign m_arsize[1]  = m1_arsize;  assign m_arsize[2]  = m2_arsize;
    assign m_arburst[0] = m0_arburst; assign m_arburst[1] = m1_arburst; assign m_arburst[2] = m2_arburst;
    assign m_arvalid[0] = m0_arvalid; assign m_arvalid[1] = m1_arvalid; assign m_arvalid[2] = m2_arvalid;
    assign m_rready[0]  = m0_rready;  assign m_rready[1]  = m1_rready;  assign m_rready[2]  = m2_rready;

    // ── Master fan-out (packed slice -> scalar) ───────────────────────────────
    assign m0_awready = m_awready[0]; assign m1_awready = m_awready[1]; assign m2_awready = m_awready[2];
    assign m0_wready  = m_wready [0]; assign m1_wready  = m_wready [1]; assign m2_wready  = m_wready [2];
    assign m0_bresp   = m_bresp  [0]; assign m1_bresp   = m_bresp  [1]; assign m2_bresp   = m_bresp  [2];
    assign m0_bvalid  = m_bvalid [0]; assign m1_bvalid  = m_bvalid [1]; assign m2_bvalid  = m_bvalid [2];
    assign m0_arready = m_arready[0]; assign m1_arready = m_arready[1]; assign m2_arready = m_arready[2];
    assign m0_rdata   = m_rdata  [0]; assign m1_rdata   = m_rdata  [1]; assign m2_rdata   = m_rdata  [2];
    assign m0_rresp   = m_rresp  [0]; assign m1_rresp   = m_rresp  [1]; assign m2_rresp   = m_rresp  [2];
    assign m0_rlast   = m_rlast  [0]; assign m1_rlast   = m_rlast  [1]; assign m2_rlast   = m_rlast  [2];
    assign m0_rvalid  = m_rvalid [0]; assign m1_rvalid  = m_rvalid [1]; assign m2_rvalid  = m_rvalid [2];

    // ── Slave fan-out (packed slice -> scalar) ───────────────────────────────
    assign s0_awid=s_awid[0]; assign s0_awaddr=s_awaddr[0]; assign s0_awlen=s_awlen[0];
    assign s0_awsize=s_awsize[0]; assign s0_awburst=s_awburst[0]; assign s0_awvalid=s_awvalid[0];
    assign s0_wdata=s_wdata[0]; assign s0_wstrb=s_wstrb[0]; assign s0_wlast=s_wlast[0]; assign s0_wvalid=s_wvalid[0];
    assign s0_bready=s_bready[0];
    assign s0_arid=s_arid[0]; assign s0_araddr=s_araddr[0]; assign s0_arlen=s_arlen[0];
    assign s0_arsize=s_arsize[0]; assign s0_arburst=s_arburst[0]; assign s0_arvalid=s_arvalid[0];
    assign s0_rready=s_rready[0];

    assign s1_awid=s_awid[1]; assign s1_awaddr=s_awaddr[1]; assign s1_awlen=s_awlen[1];
    assign s1_awsize=s_awsize[1]; assign s1_awburst=s_awburst[1]; assign s1_awvalid=s_awvalid[1];
    assign s1_wdata=s_wdata[1]; assign s1_wstrb=s_wstrb[1]; assign s1_wlast=s_wlast[1]; assign s1_wvalid=s_wvalid[1];
    assign s1_bready=s_bready[1];
    assign s1_arid=s_arid[1]; assign s1_araddr=s_araddr[1]; assign s1_arlen=s_arlen[1];
    assign s1_arsize=s_arsize[1]; assign s1_arburst=s_arburst[1]; assign s1_arvalid=s_arvalid[1];
    assign s1_rready=s_rready[1];

    // ── Slave fan-in (scalar -> packed slice) ────────────────────────────────
    assign s_awready[0] = s0_awready; assign s_awready[1] = s1_awready;
    assign s_wready [0] = s0_wready;  assign s_wready [1] = s1_wready;
    assign s_bid    [0] = s0_bid;     assign s_bid    [1] = s1_bid;
    assign s_bresp  [0] = s0_bresp;   assign s_bresp  [1] = s1_bresp;
    assign s_bvalid [0] = s0_bvalid;  assign s_bvalid [1] = s1_bvalid;
    assign s_arready[0] = s0_arready; assign s_arready[1] = s1_arready;
    assign s_rid    [0] = s0_rid;     assign s_rid    [1] = s1_rid;
    assign s_rdata  [0] = s0_rdata;   assign s_rdata  [1] = s1_rdata;
    assign s_rresp  [0] = s0_rresp;   assign s_rresp  [1] = s1_rresp;
    assign s_rlast  [0] = s0_rlast;   assign s_rlast  [1] = s1_rlast;
    assign s_rvalid [0] = s0_rvalid;  assign s_rvalid [1] = s1_rvalid;

    axi4_crossbar #(
        .N_MASTERS (NM),
        .N_SLAVES  (NS),
        .SLV_BASE  (SOC_SLV_BASE),
        .SLV_LIMIT (SOC_SLV_LIMIT)
    ) u_xbar (
        .clk(clk), .rst_n(rst_n),
        .m_awaddr(m_awaddr), .m_awlen(m_awlen), .m_awsize(m_awsize),
        .m_awburst(m_awburst), .m_awvalid(m_awvalid), .m_awready(m_awready),
        .m_wdata(m_wdata), .m_wstrb(m_wstrb), .m_wlast(m_wlast),
        .m_wvalid(m_wvalid), .m_wready(m_wready),
        .m_bresp(m_bresp), .m_bvalid(m_bvalid), .m_bready(m_bready),
        .m_araddr(m_araddr), .m_arlen(m_arlen), .m_arsize(m_arsize),
        .m_arburst(m_arburst), .m_arvalid(m_arvalid), .m_arready(m_arready),
        .m_rdata(m_rdata), .m_rresp(m_rresp), .m_rlast(m_rlast),
        .m_rvalid(m_rvalid), .m_rready(m_rready),
        .s_awid(s_awid), .s_awaddr(s_awaddr), .s_awlen(s_awlen), .s_awsize(s_awsize),
        .s_awburst(s_awburst), .s_awvalid(s_awvalid), .s_awready(s_awready),
        .s_wdata(s_wdata), .s_wstrb(s_wstrb), .s_wlast(s_wlast),
        .s_wvalid(s_wvalid), .s_wready(s_wready),
        .s_bid(s_bid), .s_bresp(s_bresp), .s_bvalid(s_bvalid), .s_bready(s_bready),
        .s_arid(s_arid), .s_araddr(s_araddr), .s_arlen(s_arlen), .s_arsize(s_arsize),
        .s_arburst(s_arburst), .s_arvalid(s_arvalid), .s_arready(s_arready),
        .s_rid(s_rid), .s_rdata(s_rdata), .s_rresp(s_rresp), .s_rlast(s_rlast),
        .s_rvalid(s_rvalid), .s_rready(s_rready)
    );

endmodule : tb_axi4_crossbar
