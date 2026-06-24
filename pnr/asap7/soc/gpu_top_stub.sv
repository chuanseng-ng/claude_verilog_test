// gpu_top_stub.sv
// Blackbox stub for the gpu_top hard macro at SoC-top synthesis.
// Yosys treats (* blackbox *) modules as externally-defined cells; the port
// interface is preserved for netlist connectivity but no logic is synthesised.
// The real implementation is in pnr/asap7/soc/macro/gpu_top.nl.v.gz
// (gate-level netlist from the GPU block-level signoff run).

`timescale 1ns/1ps

(* blackbox *)
module gpu_top #(
    parameter logic GPU_ENABLE_COALESCE = 1'b0
) (
    input  logic        clk,
    input  logic        rst_n,

    // AXI4-Lite slave — CPU control
    input  logic [11:0] s_axil_awaddr,
    input  logic        s_axil_awvalid,
    output logic        s_axil_awready,
    input  logic [31:0] s_axil_wdata,
    input  logic [3:0]  s_axil_wstrb,
    input  logic        s_axil_wvalid,
    output logic        s_axil_wready,
    output logic [1:0]  s_axil_bresp,
    output logic        s_axil_bvalid,
    input  logic        s_axil_bready,
    input  logic [11:0] s_axil_araddr,
    input  logic        s_axil_arvalid,
    output logic        s_axil_arready,
    output logic [31:0] s_axil_rdata,
    output logic [1:0]  s_axil_rresp,
    output logic        s_axil_rvalid,
    input  logic        s_axil_rready,

    // AXI4-Lite master — instruction fetch
    output logic [31:0] m_axil_if_araddr,
    output logic        m_axil_if_arvalid,
    input  logic        m_axil_if_arready,
    input  logic [31:0] m_axil_if_rdata,
    input  logic [1:0]  m_axil_if_rresp,
    input  logic        m_axil_if_rvalid,
    output logic        m_axil_if_rready,

    // AXI4 master — data memory
    output logic [31:0] m_axi_araddr,
    output logic        m_axi_arvalid,
    input  logic        m_axi_arready,
    input  logic [31:0] m_axi_rdata,
    input  logic [1:0]  m_axi_rresp,
    input  logic        m_axi_rvalid,
    output logic        m_axi_rready,
    output logic [31:0] m_axi_awaddr,
    output logic        m_axi_awvalid,
    input  logic        m_axi_awready,
    output logic [31:0] m_axi_wdata,
    output logic [3:0]  m_axi_wstrb,
    output logic        m_axi_wvalid,
    input  logic        m_axi_wready,
    input  logic [1:0]  m_axi_bresp,
    input  logic        m_axi_bvalid,
    output logic        m_axi_bready,

    // IRQ
    output logic        gpu_irq_o
);
endmodule
