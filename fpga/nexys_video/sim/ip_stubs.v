// ip_stubs.v -- black-box stand-ins for the build-time Vivado IP, FOR LINT ONLY (bead hlrm.2).
// Never put this file in a Vivado file list: it would shadow the generated IP modules.
// Port lists mirror what fpga/nexys_video/ip.tcl generates (jtag_axi AXI4-Lite master; one ILA).
module jtag_axi_0 (
    input  wire        aclk,
    input  wire        aresetn,
    output wire [31:0] m_axi_awaddr,
    output wire [2:0]  m_axi_awprot,
    output wire        m_axi_awvalid,
    input  wire        m_axi_awready,
    output wire [31:0] m_axi_wdata,
    output wire [3:0]  m_axi_wstrb,
    output wire        m_axi_wvalid,
    input  wire        m_axi_wready,
    input  wire [1:0]  m_axi_bresp,
    input  wire        m_axi_bvalid,
    output wire        m_axi_bready,
    output wire [31:0] m_axi_araddr,
    output wire [2:0]  m_axi_arprot,
    output wire        m_axi_arvalid,
    input  wire        m_axi_arready,
    input  wire [31:0] m_axi_rdata,
    input  wire [1:0]  m_axi_rresp,
    input  wire        m_axi_rvalid,
    output wire        m_axi_rready
);
endmodule

module ila_0 (
    input wire        clk,
    input wire [23:0] probe0,
    input wire [31:0] probe1,
    input wire [31:0] probe2,
    input wire [31:0] probe3,
    input wire [31:0] probe4
);
endmodule

// ---- unisim primitives used by nexys_video_top.sv, minimal lint stand-ins (ports as in UG953) ----
module IBUF (input wire I, output wire O); assign O = I; endmodule
module OBUF (input wire I, output wire O); assign O = I; endmodule
module BUFG (input wire I, output wire O); assign O = I; endmodule
module IOBUF (inout wire IO, input wire I, input wire T, output wire O);
    assign IO = T ? 1'bz : I;
    assign O  = IO;
endmodule
module MMCME2_BASE #(
    parameter BANDWIDTH = "OPTIMIZED", parameter real CLKIN1_PERIOD = 0.0, parameter integer DIVCLK_DIVIDE = 1,
    parameter real CLKFBOUT_MULT_F = 5.0, parameter real CLKOUT0_DIVIDE_F = 1.0, parameter integer CLKOUT1_DIVIDE = 1,
    parameter STARTUP_WAIT = "FALSE"
) (
    input  wire CLKIN1, input wire CLKFBIN, output wire CLKFBOUT, output wire CLKFBOUTB,
    output wire CLKOUT0, output wire CLKOUT0B, output wire CLKOUT1, output wire CLKOUT1B,
    output wire CLKOUT2, output wire CLKOUT2B, output wire CLKOUT3, output wire CLKOUT3B,
    output wire CLKOUT4, output wire CLKOUT5, output wire CLKOUT6,
    output wire LOCKED, input wire PWRDWN, input wire RST
);
    assign {CLKFBOUT, CLKFBOUTB, CLKOUT0, CLKOUT0B, CLKOUT1, CLKOUT1B, CLKOUT2, CLKOUT2B, CLKOUT3, CLKOUT3B} = {10{CLKIN1}};
    assign {CLKOUT4, CLKOUT5, CLKOUT6} = {3{CLKIN1}};
    assign LOCKED = ~RST;
endmodule
