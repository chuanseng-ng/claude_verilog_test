// tb_apb_cdc_bridge_skew.sv
// Same wrapper as tb_apb_cdc_bridge.sv, with the simulation-only settling-delay injector of cdc_sync switched on for the
// acknowledge synchroniser and the delayed reset status. Each of them can then take one s_clk_i cycle more than its
// nominal latency. Lint target: verilator -Wall -Wno-IMPORTSTAR 0 errors 0 warnings.

`default_nettype none

module tb_apb_cdc_bridge_skew #(
    parameter int unsigned ADDR_W           = 12,
    parameter int unsigned SYNC_STAGES_TO_S = 2,
    parameter int unsigned SYNC_STAGES_TO_M = 2
) (
    // ══ s_* face — source domain, APB4 SLAVE port (APB4Master attaches) ═══
    input  logic              s_clk,
    input  logic              s_rst_n,
    input  logic              s_psel,
    input  logic              s_penable,
    input  logic              s_pwrite,
    input  logic [ADDR_W-1:0] s_paddr,
    input  logic [31:0]       s_pwdata,
    input  logic [3:0]        s_pstrb,
    output logic [31:0]       s_prdata,
    output logic              s_pready,
    output logic              s_pslverr,

    // ══ m_* face — destination domain, APB4 MASTER port (local Python
    //    slave-responder coroutine drives/samples) ════════════════════════
    input  logic               m_clk,
    input  logic               m_rst_n,
    output logic               m_psel,
    output logic               m_penable,
    output logic               m_pwrite,
    output logic [ADDR_W-1:0]  m_paddr,
    output logic [31:0]        m_pwdata,
    output logic [3:0]         m_pstrb,
    input  logic [31:0]        m_prdata,
    input  logic               m_pready,
    input  logic                m_pslverr,

    // ══ Destination off level (source clock domain), driven by the test ═══
    input  logic               dest_off,

    // ══ Parameter mirrors — so the test file never hardcodes a duplicate
    //    of the RTL's own SYNC_STAGES defaults ══════════════════════════════
    output logic [31:0]        sync_stages_to_s_o,
    output logic [31:0]        sync_stages_to_m_o
);

    assign sync_stages_to_s_o = 32'(SYNC_STAGES_TO_S);
    assign sync_stages_to_m_o = 32'(SYNC_STAGES_TO_M);

    apb_cdc_bridge #(
        .ADDR_W           (ADDR_W),
        .SYNC_STAGES_TO_S (SYNC_STAGES_TO_S),
        .SYNC_STAGES_TO_M (SYNC_STAGES_TO_M)
    ) u_dut (
        // DFT scan bypass tied inert — this TB exercises functional CDC
        // behaviour only; scan-mux behaviour is covered by
        // tb_cdc_reset_sync_scan.sv.
        .dest_off_i  (dest_off),
        .scanmode_i  (1'b0),
        .scan_rst_ni (1'b1),

        .s_clk_i     (s_clk),
        .s_rst_n_i   (s_rst_n),
        .s_psel_i    (s_psel),
        .s_penable_i (s_penable),
        .s_pwrite_i  (s_pwrite),
        .s_paddr_i   (s_paddr),
        .s_pwdata_i  (s_pwdata),
        .s_pstrb_i   (s_pstrb),
        .s_prdata_o  (s_prdata),
        .s_pready_o  (s_pready),
        .s_pslverr_o (s_pslverr),

        .m_clk_i     (m_clk),
        .m_rst_n_i   (m_rst_n),
        .m_psel_o    (m_psel),
        .m_penable_o (m_penable),
        .m_pwrite_o  (m_pwrite),
        .m_paddr_o   (m_paddr),
        .m_pwdata_o  (m_pwdata),
        .m_pstrb_o   (m_pstrb),
        .m_prdata_i  (m_prdata),
        .m_pready_i  (m_pready),
        .m_pslverr_i (m_pslverr)
    );

    defparam u_dut.u_ack_sync.RAND_CDC_DELAY_EN = 1'b1;
    defparam u_dut.u_m_alive_dly_sync.RAND_CDC_DELAY_EN = 1'b1;

endmodule : tb_apb_cdc_bridge_skew

`default_nettype wire
