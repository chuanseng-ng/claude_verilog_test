// axi_lite_interconnect.sv
// Phase 5 (M3) — single-master x N-slave AXI4-Lite control interconnect.
//
// Routes the CPU configuration path to the peripheral control ring (GPU ctrl,
// UART, SPI, timer, DMA ctrl, IRQ ctrl).  Because the control bus has exactly
// one master (the CPU), there is no arbitration: each channel is a pure address
// demux on the way out and a response mux on the way back.  Compared with the
// data crossbar this is deliberately simpler — AXI4-Lite has no bursts, so every
// transfer is a single beat with no len/size/last.
//
// Design points (see docs/PHASE5_SOC_INTEGRATION_PLAN.md M3):
//   * Depth-1 outstanding write + depth-1 outstanding read (independent).  The
//     selected slave is latched for the life of the transaction.
//   * Unmapped address -> the interconnect itself returns a DECERR response and
//     completes the transfer (a bad config access never stalls the CPU).
//   * Parameterized SLV_BASE / SLV_LIMIT arrays keep the module reusable; the SoC
//     top-level passes soc_periph_map_pkg constants.
//
// Lint note: flat unpacked-array slave ports, single-master engine, no SVA.

module axi_lite_interconnect #(
    parameter int unsigned N_SLAVES = 6,
    parameter int unsigned AW       = axi_pkg::AXI_ADDR_WIDTH,
    parameter int unsigned DW       = axi_pkg::AXI_DATA_WIDTH,
    parameter int unsigned SW       = axi_pkg::AXI_STRB_WIDTH,
    // Per-slave address bounds (inclusive).
    parameter logic [AW-1:0] SLV_BASE  [N_SLAVES] = '{default: '0},
    parameter logic [AW-1:0] SLV_LIMIT [N_SLAVES] = '{default: '0}
) (
    input  logic clk,
    input  logic rst_n,

    // ══ Master-facing slave port (CPU config) ════════════════════════════════
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

    // ══ Slave-facing master ports (one per peripheral) ═══════════════════════
    output logic [AW-1:0] s_axil_awaddr  [N_SLAVES],
    output logic [2:0]    s_axil_awprot  [N_SLAVES],
    output logic          s_axil_awvalid [N_SLAVES],
    input  logic          s_axil_awready [N_SLAVES],
    output logic [DW-1:0] s_axil_wdata   [N_SLAVES],
    output logic [SW-1:0] s_axil_wstrb   [N_SLAVES],
    output logic          s_axil_wvalid  [N_SLAVES],
    input  logic          s_axil_wready  [N_SLAVES],
    input  logic [1:0]    s_axil_bresp   [N_SLAVES],
    input  logic          s_axil_bvalid  [N_SLAVES],
    output logic          s_axil_bready  [N_SLAVES],
    output logic [AW-1:0] s_axil_araddr  [N_SLAVES],
    output logic [2:0]    s_axil_arprot  [N_SLAVES],
    output logic          s_axil_arvalid [N_SLAVES],
    input  logic          s_axil_arready [N_SLAVES],
    input  logic [DW-1:0] s_axil_rdata   [N_SLAVES],
    input  logic [1:0]    s_axil_rresp   [N_SLAVES],
    input  logic          s_axil_rvalid  [N_SLAVES],
    output logic          s_axil_rready  [N_SLAVES]
);

    import axi_pkg::*;

    localparam int unsigned SELW = (N_SLAVES > 1) ? $clog2(N_SLAVES) : 1;

    // Address decode: slave index, or N_SLAVES when unmapped.
    function automatic int unsigned decode(input logic [AW-1:0] a);
        decode = N_SLAVES;
        for (int unsigned s = 0; s < N_SLAVES; s++) begin
            if (a >= SLV_BASE[s] && a <= SLV_LIMIT[s]) decode = s;
        end
    endfunction

    // ─────────────────────────────────────────────────────────────────────────
    // WRITE engine (single outstanding)
    // ─────────────────────────────────────────────────────────────────────────
    typedef enum logic [1:0] { W_IDLE, W_AW, W_DATA, W_RESP } wr_e;
    wr_e             wstate;
    logic [SELW-1:0] wsel;     // selected slave (valid when !w_dec)
    logic            w_dec;    // selected target is unmapped -> DECERR

    logic aw_hs, w_hs, b_hs;
    assign aw_hs = m_axil_awvalid && m_axil_awready;
    assign w_hs  = m_axil_wvalid  && m_axil_wready;
    assign b_hs  = m_axil_bvalid  && m_axil_bready;

    // Slave-side write drive + master-side write handshakes.
    always_comb begin
        for (int unsigned s = 0; s < N_SLAVES; s++) begin
            s_axil_awaddr [s] = '0;
            s_axil_awprot [s] = '0;
            s_axil_awvalid[s] = 1'b0;
            s_axil_wdata  [s] = '0;
            s_axil_wstrb  [s] = '0;
            s_axil_wvalid [s] = 1'b0;
            s_axil_bready [s] = 1'b0;
        end
        m_axil_awready = 1'b0;
        m_axil_wready  = 1'b0;
        m_axil_bvalid  = 1'b0;
        m_axil_bresp   = AXI_RESP_OKAY;

        unique case (wstate)
            W_AW: begin
                if (!w_dec) begin
                    s_axil_awaddr [wsel] = m_axil_awaddr;
                    s_axil_awprot [wsel] = m_axil_awprot;
                    s_axil_awvalid[wsel] = m_axil_awvalid;
                    m_axil_awready       = s_axil_awready[wsel];
                end else begin
                    m_axil_awready = 1'b1;   // accept and drop
                end
            end
            W_DATA: begin
                if (!w_dec) begin
                    s_axil_wdata  [wsel] = m_axil_wdata;
                    s_axil_wstrb  [wsel] = m_axil_wstrb;
                    s_axil_wvalid [wsel] = m_axil_wvalid;
                    m_axil_wready        = s_axil_wready[wsel];
                end else begin
                    m_axil_wready = 1'b1;    // sink the data beat
                end
            end
            W_RESP: begin
                if (!w_dec) begin
                    m_axil_bvalid       = s_axil_bvalid[wsel];
                    m_axil_bresp        = s_axil_bresp [wsel];
                    s_axil_bready[wsel] = m_axil_bready;
                end else begin
                    m_axil_bvalid = 1'b1;
                    m_axil_bresp  = AXI_RESP_DECERR;
                end
            end
            default: ;
        endcase
    end

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            wstate <= W_IDLE;
            wsel   <= '0;
            w_dec  <= 1'b0;
        end else begin
            unique case (wstate)
                W_IDLE: if (m_axil_awvalid) begin
                    automatic int unsigned d = decode(m_axil_awaddr);
                    if (d < N_SLAVES) begin
                        wsel  <= d[SELW-1:0];
                        w_dec <= 1'b0;
                    end else begin
                        w_dec <= 1'b1;
                    end
                    wstate <= W_AW;
                end
                W_AW:   if (aw_hs) wstate <= W_DATA;
                W_DATA: if (w_hs)  wstate <= W_RESP;
                W_RESP: if (b_hs)  wstate <= W_IDLE;
                default: wstate <= W_IDLE;
            endcase
        end
    end

    // ─────────────────────────────────────────────────────────────────────────
    // READ engine (single outstanding)
    // ─────────────────────────────────────────────────────────────────────────
    typedef enum logic [1:0] { R_IDLE, R_AR, R_DATA } rd_e;
    rd_e             rstate;
    logic [SELW-1:0] rsel;
    logic            r_dec;

    logic ar_hs, r_hs;
    assign ar_hs = m_axil_arvalid && m_axil_arready;
    assign r_hs  = m_axil_rvalid  && m_axil_rready;

    always_comb begin
        for (int unsigned s = 0; s < N_SLAVES; s++) begin
            s_axil_araddr [s] = '0;
            s_axil_arprot [s] = '0;
            s_axil_arvalid[s] = 1'b0;
            s_axil_rready [s] = 1'b0;
        end
        m_axil_arready = 1'b0;
        m_axil_rvalid  = 1'b0;
        m_axil_rdata   = '0;
        m_axil_rresp   = AXI_RESP_OKAY;

        unique case (rstate)
            R_AR: begin
                if (!r_dec) begin
                    s_axil_araddr [rsel] = m_axil_araddr;
                    s_axil_arprot [rsel] = m_axil_arprot;
                    s_axil_arvalid[rsel] = m_axil_arvalid;
                    m_axil_arready       = s_axil_arready[rsel];
                end else begin
                    m_axil_arready = 1'b1;
                end
            end
            R_DATA: begin
                if (!r_dec) begin
                    m_axil_rvalid       = s_axil_rvalid[rsel];
                    m_axil_rdata        = s_axil_rdata [rsel];
                    m_axil_rresp        = s_axil_rresp [rsel];
                    s_axil_rready[rsel] = m_axil_rready;
                end else begin
                    m_axil_rvalid = 1'b1;
                    m_axil_rdata  = '0;
                    m_axil_rresp  = AXI_RESP_DECERR;
                end
            end
            default: ;
        endcase
    end

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            rstate <= R_IDLE;
            rsel   <= '0;
            r_dec  <= 1'b0;
        end else begin
            unique case (rstate)
                R_IDLE: if (m_axil_arvalid) begin
                    automatic int unsigned d = decode(m_axil_araddr);
                    if (d < N_SLAVES) begin
                        rsel  <= d[SELW-1:0];
                        r_dec <= 1'b0;
                    end else begin
                        r_dec <= 1'b1;
                    end
                    rstate <= R_AR;
                end
                R_AR:   if (ar_hs) rstate <= R_DATA;
                R_DATA: if (r_hs)  rstate <= R_IDLE;
                default: rstate <= R_IDLE;
            endcase
        end
    end

endmodule : axi_lite_interconnect
