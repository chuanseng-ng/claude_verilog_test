// tb_apb4_register_bank.sv
// Phase 5 (APB migration PR-1) — cocotb test wrapper for apb4_register_bank.
//
// Mirrors tb_axi_lite_register_bank.sv exactly in register layout and
// HW-injection wiring so test_apb4_register_bank.py can confirm byte-for-byte
// behavioral equivalence with the AXI-Lite bank.
//
// Register layout (N_REGS = 8):
//   reg0..reg5 : fully SW-writable  (WMASK = 0xFFFFFFFF)
//   reg6 @0x18 : SW read-only/status (WMASK = 0x00000000), HW-writable
//   reg7 @0x1C : low-byte writable only (WMASK = 0x000000FF)
//
// APB4 ports are exposed flat (psel/penable/pwrite/paddr/pwdata/pstrb/
// prdata/pready/pslverr) — the APB4Master BFM drives them directly.
// Hardware injection port: hw_status_wen / hw_status_wdata -> reg6.

`default_nettype none

module tb_apb4_register_bank #(
    parameter int unsigned ADDR_W = 12,
    parameter int unsigned DW     = 32,
    parameter int unsigned SW     = 4,
    parameter int unsigned N_REGS = 8
) (
    input  logic pclk,
    input  logic presetn,

    // APB4 slave port (flat — driven by APB4Master BFM)
    input  logic              psel,
    input  logic              penable,
    input  logic              pwrite,
    input  logic [ADDR_W-1:0] paddr,
    input  logic [DW-1:0]     pwdata,
    input  logic [SW-1:0]     pstrb,
    output logic [DW-1:0]     prdata,
    output logic              pready,
    output logic              pslverr,

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
    logic [31:0] regs_o [N_REGS];   // not checked via this port in unit tests
    /* verilator lint_on  UNUSEDSIGNAL */

    apb4_register_bank #(
        .N_REGS    (N_REGS),
        .ADDR_W    (ADDR_W),
        .DW        (DW),
        .SW        (SW),
        .RESET_VAL (RV),
        .WMASK     (WM)
    ) u_bank (
        .pclk      (pclk),
        .presetn   (presetn),
        .psel      (psel),
        .penable   (penable),
        .pwrite    (pwrite),
        .paddr     (paddr),
        .pwdata    (pwdata),
        .pstrb     (pstrb),
        .prdata    (prdata),
        .pready    (pready),
        .pslverr   (pslverr),
        .regs_o    (regs_o),
        .hw_wen_i  (hw_wen),
        .hw_wdata_i(hw_wdata)
    );

endmodule : tb_apb4_register_bank

`default_nettype wire
