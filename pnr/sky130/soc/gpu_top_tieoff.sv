// gpu_top_tieoff.sv
// Synthesisable tie-off stub for gpu_top in the Sky130 SoC Stage 2 flow.
//
// The GPU is NOT instantiated as a hard macro in Stage 2.  This module
// matches the EXACT port interface expected by soc_top.sv but drives all
// outputs to safe idle / zero values.  Yosys will propagate the constants
// and synthesise this to nearly zero standard cells.
//
// Key difference from the ASAP7 gpu_top_stub.sv: that file uses
// (* blackbox *) for macro blackboxing; this file is fully synthesisable so
// that sv2v + Yosys produces a real (trivial) gate-level result.

`default_nettype none

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

    // AXI4-Lite master — instruction fetch (read-only)
    output logic [31:0] m_axil_if_araddr,
    output logic        m_axil_if_arvalid,
    input  logic        m_axil_if_arready,
    input  logic [31:0] m_axil_if_rdata,
    input  logic [1:0]  m_axil_if_rresp,
    input  logic        m_axil_if_rvalid,
    output logic        m_axil_if_rready,

    // AXI4 data master — GPU DRAM access
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

    // Suppress unused input warnings (synthesis will discard undriven fanout)
    /* verilator lint_off UNUSEDSIGNAL */
    logic _unused;
    assign _unused = GPU_ENABLE_COALESCE ^ clk ^ rst_n
                   ^ s_axil_awvalid ^ |s_axil_awaddr
                   ^ |s_axil_wdata ^ |s_axil_wstrb ^ s_axil_wvalid
                   ^ s_axil_bready
                   ^ s_axil_arvalid ^ |s_axil_araddr ^ s_axil_rready
                   ^ m_axil_if_arready ^ |m_axil_if_rdata ^ |m_axil_if_rresp
                   ^ m_axil_if_rvalid
                   ^ m_axi_arready ^ |m_axi_rdata ^ |m_axi_rresp ^ m_axi_rvalid
                   ^ m_axi_awready ^ m_axi_wready ^ |m_axi_bresp ^ m_axi_bvalid;
    /* verilator lint_on UNUSEDSIGNAL */

    // AXI4-Lite slave: stall all transactions (slave not present)
    assign s_axil_awready = 1'b0;
    assign s_axil_wready  = 1'b0;
    assign s_axil_bresp   = 2'b00;
    assign s_axil_bvalid  = 1'b0;
    assign s_axil_arready = 1'b0;
    assign s_axil_rdata   = 32'h0;
    assign s_axil_rresp   = 2'b00;
    assign s_axil_rvalid  = 1'b0;

    // AXI4-Lite master: never issue requests
    assign m_axil_if_araddr  = 32'h0;
    assign m_axil_if_arvalid = 1'b0;
    assign m_axil_if_rready  = 1'b0;

    // AXI4 data master: never issue requests
    assign m_axi_araddr  = 32'h0;
    assign m_axi_arvalid = 1'b0;
    assign m_axi_rready  = 1'b0;
    assign m_axi_awaddr  = 32'h0;
    assign m_axi_awvalid = 1'b0;
    assign m_axi_wdata   = 32'h0;
    assign m_axi_wstrb   = 4'h0;
    assign m_axi_wvalid  = 1'b0;
    assign m_axi_bready  = 1'b0;

    // No interrupt
    assign gpu_irq_o = 1'b0;

endmodule : gpu_top

`default_nettype wire
