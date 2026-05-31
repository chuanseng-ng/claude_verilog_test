// tb_axi_lite_register_bank.sv
// Phase 5 (M3) — cocotb test wrapper for axi_lite_register_bank.
//
// Exposes one register bank's AXI4-Lite slave port with the flat "s_axil_"
// prefix the AXI4LiteMaster BFM expects, plus a single HW-status injection pair
// wired to register index 6 (a read-only/status register) so the testbench can
// verify the hardware write path bypasses WMASK.
//
// Register layout (N_REGS = 8):
//   reg0..reg5 : fully SW-writable  (WMASK = 0xFFFFFFFF)
//   reg6       : SW read-only/status (WMASK = 0x00000000), HW-writable
//   reg7       : low-byte writable   (WMASK = 0x000000FF)

module tb_axi_lite_register_bank #(
    parameter int unsigned ADDR_W = 12,
    parameter int unsigned DW     = axi_pkg::AXI_DATA_WIDTH,
    parameter int unsigned SW     = axi_pkg::AXI_STRB_WIDTH,
    parameter int unsigned N_REGS = 8
) (
    input  logic clk,
    input  logic rst_n,

    input  logic [ADDR_W-1:0] s_axil_awaddr,
    input  logic [2:0]        s_axil_awprot,
    input  logic              s_axil_awvalid,
    output logic              s_axil_awready,
    input  logic [DW-1:0]     s_axil_wdata,
    input  logic [SW-1:0]     s_axil_wstrb,
    input  logic              s_axil_wvalid,
    output logic              s_axil_wready,
    output logic [1:0]        s_axil_bresp,
    output logic              s_axil_bvalid,
    input  logic              s_axil_bready,
    input  logic [ADDR_W-1:0] s_axil_araddr,
    input  logic [2:0]        s_axil_arprot,
    input  logic              s_axil_arvalid,
    output logic              s_axil_arready,
    output logic [DW-1:0]     s_axil_rdata,
    output logic [1:0]        s_axil_rresp,
    output logic              s_axil_rvalid,
    input  logic              s_axil_rready,

    // Hardware status injection -> register index 6.
    input  logic              hw_status_wen,
    input  logic [31:0]       hw_status_wdata
);

    localparam logic [31:0] WM [N_REGS] = '{
        32'hFFFF_FFFF, 32'hFFFF_FFFF, 32'hFFFF_FFFF, 32'hFFFF_FFFF,
        32'hFFFF_FFFF, 32'hFFFF_FFFF, 32'h0000_0000, 32'h0000_00FF};
    localparam logic [31:0] RV [N_REGS] = '{default: '0};

    logic        hw_wen   [N_REGS];
    logic [31:0] hw_wdata [N_REGS];
    always_comb begin
        for (int unsigned i = 0; i < N_REGS; i++) begin
            hw_wen  [i] = 1'b0;
            hw_wdata[i] = 32'b0;
        end
        hw_wen  [6] = hw_status_wen;
        hw_wdata[6] = hw_status_wdata;
    end

    /* verilator lint_off UNUSEDSIGNAL */
    logic [31:0] regs_o [N_REGS];   // exposed by DUT; not checked via this port
    /* verilator lint_on  UNUSEDSIGNAL */

    axi_lite_register_bank #(
        .N_REGS    (N_REGS),
        .ADDR_W    (ADDR_W),
        .DW        (DW),
        .SW        (SW),
        .RESET_VAL (RV),
        .WMASK     (WM)
    ) u_bank (
        .clk(clk), .rst_n(rst_n),
        .s_axil_awaddr(s_axil_awaddr), .s_axil_awprot(s_axil_awprot),
        .s_axil_awvalid(s_axil_awvalid), .s_axil_awready(s_axil_awready),
        .s_axil_wdata(s_axil_wdata), .s_axil_wstrb(s_axil_wstrb),
        .s_axil_wvalid(s_axil_wvalid), .s_axil_wready(s_axil_wready),
        .s_axil_bresp(s_axil_bresp), .s_axil_bvalid(s_axil_bvalid),
        .s_axil_bready(s_axil_bready),
        .s_axil_araddr(s_axil_araddr), .s_axil_arprot(s_axil_arprot),
        .s_axil_arvalid(s_axil_arvalid), .s_axil_arready(s_axil_arready),
        .s_axil_rdata(s_axil_rdata), .s_axil_rresp(s_axil_rresp),
        .s_axil_rvalid(s_axil_rvalid), .s_axil_rready(s_axil_rready),
        .regs_o(regs_o), .hw_wen_i(hw_wen), .hw_wdata_i(hw_wdata)
    );

endmodule : tb_axi_lite_register_bank
