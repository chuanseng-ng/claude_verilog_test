// tb_axil_to_apb.sv
// Phase 5 (APB migration PR-1) — cocotb test wrapper for axil_to_apb bridge.
//
// Instantiates axil_to_apb (AXI4-Lite slave -> APB4 master) back-to-back with
// apb4_register_bank so the entire write/read data path can be verified through
// one simple top-level:
//
//   AXI4LiteMaster BFM  ->  axil_to_apb  ->  apb4_register_bank
//
// The AXI4-Lite port uses the "s_axil_" prefix that AXI4LiteMaster BFM expects.
// The APB4 bus is internal; the register bank's regs_o and pslverr are exposed
// so tests can inject pslverr from outside to exercise SLVERR propagation.
//
// To enable pslverr injection the bridge's pslverr input is driven by the
// external port pslverr_force: when force_slverr=1 the register bank's pready
// output is overridden to 1 and pslverr to 1 (single-cycle injection).
//
// Register layout (N_REGS = 8, identical to tb_apb4_register_bank):
//   reg0..reg5 : fully SW-writable
//   reg6       : SW read-only, HW-writable
//   reg7       : low-byte writable only (WMASK 0x000000FF)

`default_nettype none

module tb_axil_to_apb #(
    parameter int unsigned ADDR_W = 32,
    parameter int unsigned DW     = 32,
    parameter int unsigned SW     = 4,
    parameter int unsigned N_REGS = 8
) (
    input  logic clk,
    input  logic rst_n,

    // ── AXI4-Lite slave port (driven by AXI4LiteMaster BFM) ──────────────────
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

    // ── SLVERR injection control ──────────────────────────────────────────────
    // When force_slverr=1 the register bank is bypassed: the bridge sees
    // pready=1 and pslverr=1, allowing test_pslverr_propagation.
    input  logic force_slverr,

    // ── Hardware status injection -> register index 6 ─────────────────────────
    input  logic              hw_status_wen,
    input  logic [31:0]       hw_status_wdata
);

    // ── Internal APB4 bus wires ───────────────────────────────────────────────
    logic              apb_psel;
    logic              apb_penable;
    logic              apb_pwrite;
    logic [ADDR_W-1:0] apb_paddr;
    logic [DW-1:0]     apb_pwdata;
    logic [SW-1:0]     apb_pstrb;
    logic [DW-1:0]     bank_prdata;   // prdata from the register bank
    logic              apb_pready_bank;
    logic              apb_pslverr_bank;

    // Mux: when force_slverr=1 override pready/pslverr seen by the bridge.
    logic apb_pready;
    logic apb_pslverr;
    assign apb_pready  = force_slverr ? 1'b1 : apb_pready_bank;
    assign apb_pslverr = force_slverr ? 1'b1 : apb_pslverr_bank;
    // prdata: bridge always samples the bank's real output (0 when forced is fine)

    // ── axil_to_apb bridge ────────────────────────────────────────────────────
    axil_to_apb #(
        .ADDR_W (ADDR_W),
        .DW     (DW),
        .SW     (SW)
    ) u_bridge (
        .clk           (clk),
        .rst_n         (rst_n),
        // AXI-Lite slave
        .s_axil_awaddr (s_axil_awaddr),
        .s_axil_awprot (s_axil_awprot),
        .s_axil_awvalid(s_axil_awvalid),
        .s_axil_awready(s_axil_awready),
        .s_axil_wdata  (s_axil_wdata),
        .s_axil_wstrb  (s_axil_wstrb),
        .s_axil_wvalid (s_axil_wvalid),
        .s_axil_wready (s_axil_wready),
        .s_axil_bresp  (s_axil_bresp),
        .s_axil_bvalid (s_axil_bvalid),
        .s_axil_bready (s_axil_bready),
        .s_axil_araddr (s_axil_araddr),
        .s_axil_arprot (s_axil_arprot),
        .s_axil_arvalid(s_axil_arvalid),
        .s_axil_arready(s_axil_arready),
        .s_axil_rdata  (s_axil_rdata),
        .s_axil_rresp  (s_axil_rresp),
        .s_axil_rvalid (s_axil_rvalid),
        .s_axil_rready (s_axil_rready),
        // APB4 master
        .psel          (apb_psel),
        .penable       (apb_penable),
        .pwrite        (apb_pwrite),
        .paddr         (apb_paddr),
        .pwdata        (apb_pwdata),
        .pstrb         (apb_pstrb),
        .prdata        (bank_prdata),   // read from bank; 0 when force_slverr (safe)
        .pready        (apb_pready),
        .pslverr       (apb_pslverr)
    );

    // ── apb4_register_bank slave ──────────────────────────────────────────────
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
    logic [31:0] regs_o [N_REGS];
    /* verilator lint_on  UNUSEDSIGNAL */

    apb4_register_bank #(
        .N_REGS    (N_REGS),
        .ADDR_W    (ADDR_W),
        .DW        (DW),
        .SW        (SW),
        .RESET_VAL (RV),
        .WMASK     (WM)
    ) u_bank (
        .pclk      (clk),
        .presetn   (rst_n),
        .psel      (apb_psel),
        .penable   (apb_penable),
        .pwrite    (apb_pwrite),
        .paddr     (apb_paddr[ADDR_W-1:0]),
        .pwdata    (apb_pwdata),
        .pstrb     (apb_pstrb),
        .prdata    (bank_prdata),
        .pready    (apb_pready_bank),
        .pslverr   (apb_pslverr_bank),
        .regs_o    (regs_o),
        .hw_wen_i  (hw_wen),
        .hw_wdata_i(hw_wdata)
    );

endmodule : tb_axil_to_apb

`default_nettype wire
