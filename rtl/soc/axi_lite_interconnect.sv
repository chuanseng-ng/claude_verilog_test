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
//   * SINGLE-MASTER ONLY: there is no arbitration logic.  A second control-plane
//     master (e.g. Phase 6 DMA-to-peripheral access) requires an arbiter front
//     end; do not wire one in without it.
//
// Lint note: flat unpacked-array slave ports, single-master engine, no SVA.
// Synlig workaround: always_comb driving output port array slices via variable
// index produces empty RTLIL wire names (kernel/rtlil.cc:2150 assert). Fix:
// always_comb drives packed intermediate wires; generate assigns bridge to ports.

module axi_lite_interconnect #(
    parameter int unsigned N_SLAVES = 6,
    parameter int unsigned AW       = axi_pkg::AXI_ADDR_WIDTH,
    parameter int unsigned DW       = axi_pkg::AXI_DATA_WIDTH,
    parameter int unsigned SW       = axi_pkg::AXI_STRB_WIDTH,
    // Per-slave address bounds (inclusive).
    // Packed 2D [N_SLAVES-1:0][AW-1:0]: avoids Synlig UHDM $mem lowering of
    // unpacked array parameters which emits empty-named RTLIL wires.
    parameter logic [N_SLAVES-1:0][AW-1:0] SLV_BASE  = '0,
    parameter logic [N_SLAVES-1:0][AW-1:0] SLV_LIMIT = '0
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

    // ══ Slave-facing master ports (packed 2D — required for Synlig/UHDM) ═══════
    output logic [N_SLAVES-1:0][AW-1:0] s_axil_awaddr,
    output logic [N_SLAVES-1:0][2:0]    s_axil_awprot,
    output logic [N_SLAVES-1:0]         s_axil_awvalid,
    input  logic [N_SLAVES-1:0]         s_axil_awready,
    output logic [N_SLAVES-1:0][DW-1:0] s_axil_wdata,
    output logic [N_SLAVES-1:0][SW-1:0] s_axil_wstrb,
    output logic [N_SLAVES-1:0]         s_axil_wvalid,
    input  logic [N_SLAVES-1:0]         s_axil_wready,
    input  logic [N_SLAVES-1:0][1:0]    s_axil_bresp,
    input  logic [N_SLAVES-1:0]         s_axil_bvalid,
    output logic [N_SLAVES-1:0]         s_axil_bready,
    output logic [N_SLAVES-1:0][AW-1:0] s_axil_araddr,
    output logic [N_SLAVES-1:0][2:0]    s_axil_arprot,
    output logic [N_SLAVES-1:0]         s_axil_arvalid,
    input  logic [N_SLAVES-1:0]         s_axil_arready,
    input  logic [N_SLAVES-1:0][DW-1:0] s_axil_rdata,
    input  logic [N_SLAVES-1:0][1:0]    s_axil_rresp,
    input  logic [N_SLAVES-1:0]         s_axil_rvalid,
    output logic [N_SLAVES-1:0]         s_axil_rready
);

    import axi_pkg::*;

    localparam int unsigned SELW = (N_SLAVES > 1) ? $clog2(N_SLAVES) : 1;

    // Address decode: slave index (as logic [31:0]), or N_SLAVES when unmapped.
    // Return type is logic [31:0] instead of int unsigned to avoid the Synlig
    // UHDM RTLIL empty-wire bug: int-unsigned function returns create named
    // temporaries (decode$func$...$result) that lose their names after proc.
    function automatic logic [31:0] decode(input logic [AW-1:0] a);
        decode = 32'(N_SLAVES);
        for (int unsigned s = 0; s < N_SLAVES; s++) begin
            if (a >= SLV_BASE[s] && a <= SLV_LIMIT[s]) decode = 32'(s);
        end
    endfunction

    // ─────────────────────────────────────────────────────────────────────────
    // WRITE engine (single outstanding)
    // ─────────────────────────────────────────────────────────────────────────
    typedef enum logic [1:0] { W_IDLE, W_AW, W_DATA, W_RESP } wr_e;
    wr_e             wstate;
    logic [SELW-1:0] wsel;     // selected slave (valid when !w_dec)
    logic            w_dec;    // selected target is unmapped -> DECERR

    // Combinational decode temporaries — avoids `automatic` vars in always_ff
    // (not synthesizable in Yosys/Synlig; causes RTLIL unnamed-wire assertion).
    // Use logic [31:0] + assign (not int unsigned + always_comb) — Synlig UHDM
    // creates empty-name RTLIL wires when always_comb calls a function that
    // returns int unsigned and assigns to an int unsigned net (same root cause
    // as the proc-drives-port-slice bug: unnamed function-result intermediates).
    logic [31:0] aw_decode_d;
    logic [31:0] ar_decode_d;
    assign aw_decode_d = decode(m_axil_awaddr);
    assign ar_decode_d = decode(m_axil_araddr);

    // Intermediate packed wires for all slave-side output port arrays.
    // always_comb drives these (Synlig-safe: internal wires, not ports).
    // generate assigns below connect them to the unpacked port arrays.
    logic [N_SLAVES-1:0][AW-1:0]  _s_awaddr;
    logic [N_SLAVES-1:0][2:0]     _s_awprot;
    logic [N_SLAVES-1:0]          _s_awvalid;
    logic [N_SLAVES-1:0][DW-1:0]  _s_wdata;
    logic [N_SLAVES-1:0][SW-1:0]  _s_wstrb;
    logic [N_SLAVES-1:0]          _s_wvalid;
    logic [N_SLAVES-1:0]          _s_bready;
    logic [N_SLAVES-1:0][AW-1:0]  _s_araddr;
    logic [N_SLAVES-1:0][2:0]     _s_arprot;
    logic [N_SLAVES-1:0]          _s_arvalid;
    logic [N_SLAVES-1:0]          _s_rready;

    logic aw_hs, w_hs, b_hs;
    assign aw_hs = m_axil_awvalid && m_axil_awready;
    assign w_hs  = m_axil_wvalid  && m_axil_wready;
    assign b_hs  = m_axil_bvalid  && m_axil_bready;

    // Slave-side write drive + master-side write handshakes.
    // Drives _s_* intermediates (not port arrays) to avoid Synlig RTLIL bug.
    always_comb begin
        for (int unsigned s = 0; s < N_SLAVES; s++) begin
            _s_awaddr [s] = '0;
            _s_awprot [s] = '0;
            _s_awvalid[s] = 1'b0;
            _s_wdata  [s] = '0;
            _s_wstrb  [s] = '0;
            _s_wvalid [s] = 1'b0;
            _s_bready [s] = 1'b0;
        end
        m_axil_awready = 1'b0;
        m_axil_wready  = 1'b0;
        m_axil_bvalid  = 1'b0;
        m_axil_bresp   = AXI_RESP_OKAY;

        unique case (wstate)
            W_AW: begin
                if (!w_dec) begin
                    _s_awaddr [wsel] = m_axil_awaddr;
                    _s_awprot [wsel] = m_axil_awprot;
                    _s_awvalid[wsel] = m_axil_awvalid;
                    m_axil_awready   = s_axil_awready[wsel];
                end else begin
                    m_axil_awready = 1'b1;   // accept and drop
                end
            end
            W_DATA: begin
                if (!w_dec) begin
                    _s_wdata  [wsel] = m_axil_wdata;
                    _s_wstrb  [wsel] = m_axil_wstrb;
                    _s_wvalid [wsel] = m_axil_wvalid;
                    m_axil_wready    = s_axil_wready[wsel];
                end else begin
                    m_axil_wready = 1'b1;    // sink the data beat
                end
            end
            W_RESP: begin
                if (!w_dec) begin
                    m_axil_bvalid    = s_axil_bvalid[wsel];
                    m_axil_bresp     = s_axil_bresp [wsel];
                    _s_bready[wsel]  = m_axil_bready;
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
                    if (aw_decode_d < N_SLAVES) begin
                        wsel  <= aw_decode_d[SELW-1:0];
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

    // Slave-side read drive + master-side read handshakes.
    // Drives _s_ar*/_s_rready intermediates (not port arrays) to avoid Synlig RTLIL bug.
    always_comb begin
        for (int unsigned s = 0; s < N_SLAVES; s++) begin
            _s_araddr [s] = '0;
            _s_arprot [s] = '0;
            _s_arvalid[s] = 1'b0;
            _s_rready [s] = 1'b0;
        end
        m_axil_arready = 1'b0;
        m_axil_rvalid  = 1'b0;
        m_axil_rdata   = '0;
        m_axil_rresp   = AXI_RESP_OKAY;

        unique case (rstate)
            R_AR: begin
                if (!r_dec) begin
                    _s_araddr [rsel] = m_axil_araddr;
                    _s_arprot [rsel] = m_axil_arprot;
                    _s_arvalid[rsel] = m_axil_arvalid;
                    m_axil_arready   = s_axil_arready[rsel];
                end else begin
                    m_axil_arready = 1'b1;
                end
            end
            R_DATA: begin
                if (!r_dec) begin
                    m_axil_rvalid    = s_axil_rvalid[rsel];
                    m_axil_rdata     = s_axil_rdata [rsel];
                    m_axil_rresp     = s_axil_rresp [rsel];
                    _s_rready[rsel]  = m_axil_rready;
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
                    if (ar_decode_d < N_SLAVES) begin
                        rsel  <= ar_decode_d[SELW-1:0];
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

    // Port bridge: connect packed intermediate wires to packed port arrays.
    // Ports are now packed 2D — direct whole-array assignment is legal and
    // avoids the Synlig RTLIL empty-wire bug entirely.
    assign s_axil_awaddr  = _s_awaddr;
    assign s_axil_awprot  = _s_awprot;
    assign s_axil_awvalid = _s_awvalid;
    assign s_axil_wdata   = _s_wdata;
    assign s_axil_wstrb   = _s_wstrb;
    assign s_axil_wvalid  = _s_wvalid;
    assign s_axil_bready  = _s_bready;
    assign s_axil_araddr  = _s_araddr;
    assign s_axil_arprot  = _s_arprot;
    assign s_axil_arvalid = _s_arvalid;
    assign s_axil_rready  = _s_rready;

endmodule : axi_lite_interconnect
