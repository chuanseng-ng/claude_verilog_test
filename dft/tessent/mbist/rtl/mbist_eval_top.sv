// mbist_eval_top.sv -- Tessent MemoryBIST evaluation wrapper (NOT part of the SoC; evaluation only).
//
// Holds the two SoC-level users of sky130_sram_4kbyte_1rw1r_32x1024_8, instantiated unmodified from rtl/:
//   u_sram  : sram_controller  (port 0 write, port 1 = functional read path)
//   u_wmem  : npu_weight_mem   (port 0 RW, port 1 tied off inside the module)
// with one clock and one reset, exactly the clock domain (core_clk) the in-house controller serves.
// The in-house MBIST inputs of both modules (mb_*) are tied inactive, so the in-house collar is a
// pass-through here and Tessent inserts its own memory interface behind it.
//
// Why not soc_top: soc_top's core_clk reaches the macros through dft_clk_mux, whose select is driven by
// dft_ctrl flops (TAP scan_mode) that Tessent cannot constrain from a primary input (DFT_C1-1 "memory clock
// not properly sourced", see docs/design/TESSENT_MBIST_EVALUATION.md section 5).
`timescale 1ns/1ps
module mbist_eval_top (
    input  logic        clk,
    input  logic        rst_n,
    // sram_controller AXI4 slave
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
    // npu_weight_mem
    input  logic        w_wr_en,
    input  logic [9:0]  w_wr_addr,
    input  logic [31:0] w_wr_data,
    input  logic        w_rd_en,
    input  logic [9:0]  w_rd_addr,
    output logic [31:0] w_rd_data
);

    sram_controller #(.MEM_WORDS(1024)) u_sram (
        .clk(clk), .rst_n(rst_n),
        .s_awid(s_awid), .s_awaddr(s_awaddr), .s_awlen(s_awlen), .s_awsize(s_awsize),
        .s_awburst(s_awburst), .s_awvalid(s_awvalid), .s_awready(s_awready),
        .s_wdata(s_wdata), .s_wstrb(s_wstrb), .s_wlast(s_wlast), .s_wvalid(s_wvalid), .s_wready(s_wready),
        .s_bid(s_bid), .s_bresp(s_bresp), .s_bvalid(s_bvalid), .s_bready(s_bready),
        .s_arid(s_arid), .s_araddr(s_araddr), .s_arlen(s_arlen), .s_arsize(s_arsize),
        .s_arburst(s_arburst), .s_arvalid(s_arvalid), .s_arready(s_arready),
        .s_rid(s_rid), .s_rdata(s_rdata), .s_rresp(s_rresp), .s_rlast(s_rlast),
        .s_rvalid(s_rvalid), .s_rready(s_rready),
        .mb_en_i(1'b0), .mb_ce_i(1'b0), .mb_we_i(1'b0), .mb_wmask_i(4'b0),
        .mb_addr_i(10'b0), .mb_din_i(32'b0), .mb_dout0_o(), .mb_dout1_o()
    );

    npu_weight_mem #(.WEIGHT_WORDS(1024)) u_wmem (
        .clk(clk),
        .wr_en_i(w_wr_en), .wr_addr_i(w_wr_addr), .wr_data_i(w_wr_data),
        .rd_en_i(w_rd_en), .rd_addr_i(w_rd_addr), .rd_data_o(w_rd_data),
        .mb_en_i(1'b0), .mb_ce_i(1'b0), .mb_we_i(1'b0), .mb_wmask_i(4'b0),
        .mb_addr_i(10'b0), .mb_din_i(32'b0), .mb_dout0_o()
    );

endmodule
