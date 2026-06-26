// axi4_crossbar.sv
// Phase 5 (M3) — N-master x M-slave AXI4 data crossbar.
//
// Routes AW/W/B and AR/R between N masters and M slaves by address decode.
// Arbitration reuses the proven priority-grant pattern from
// rtl/mem/rv32i_cache_arbiter.sv, generalised to a per-slave grant engine.
//
// Design points (see docs/PHASE5_SOC_INTEGRATION_PLAN.md M3):
//   * Per-slave write engine + read engine, each depth-1 outstanding.  A slave
//     channel is locked to one master for the life of a transaction, so bursts
//     never interleave and the fabric cannot deadlock.
//   * Independent slaves serve different masters concurrently (no head-of-line
//     block across slaves).
//   * Fixed priority among masters: lowest index wins (master 0 highest).  This
//     matches the cache-arbiter precedent; round-robin is a fairness upgrade if
//     benchmarks show starvation.
//   * Unmapped address -> the crossbar returns a DECERR response and completes
//     the transaction (a bad address never stalls a master).
//   * Master-facing ports carry NO id; the crossbar tags slave-facing requests
//     with the master index (s_*id) and routes responses back via the per-slave
//     grant register (engine memory), so id echo is not required for routing.
//   * ASSUMPTION: read and write engines are independent, so a master may hold
//     one AR and one AW in flight to the same slave, but the crossbar provides
//     NO ordering between them (AXI4 has none either).  A master that requires
//     read-after-write ordering to the same slave must wait for B before AR.
//     The deadlock-free claim covers only masters that drain responses; a
//     master that stalls its R/B channel indefinitely wedges that slave engine.
//
// Lint note: packed 2D arrays for all internal state; generate blocks that
// used always_comb to drive port array slices are replaced with two-step
// patterns: (1) always_comb drives packed intermediate wires, (2) a generate
// for uses simple continuous assign to wire intermediates to unpacked ports.
// Synlig/UHDM has an RTLIL empty-wire bug (kernel/rtlil.cc:2150) that fires
// when always_comb (inside or outside generate) drives port array slices via
// a loop variable index.  Continuous assign in generate is not affected.

module axi4_crossbar #(
    parameter int unsigned N_MASTERS = 3,
    parameter int unsigned N_SLAVES  = 2,
    parameter int unsigned AW        = axi_pkg::AXI_ADDR_WIDTH,
    parameter int unsigned DW        = axi_pkg::AXI_DATA_WIDTH,
    parameter int unsigned SW        = axi_pkg::AXI_STRB_WIDTH,
    parameter int unsigned IW        = axi_pkg::AXI_ID_WIDTH,
    parameter int unsigned LENW      = axi_pkg::AXI_LEN_WIDTH,
    // Per-slave address bounds (inclusive).
    // Packed 2D [N_SLAVES-1:0][31:0]: avoids Synlig UHDM $mem lowering of
    // unpacked array parameters which emits empty-named RTLIL wires.
    // Index s: SLV_BASE[s] selects bits [s*32+31:s*32].
    parameter logic [N_SLAVES-1:0][31:0] SLV_BASE  = '0,
    parameter logic [N_SLAVES-1:0][31:0] SLV_LIMIT = '0
) (
    input  logic clk,
    input  logic rst_n,

    // ══ Master-facing ports (no id; len/size/burst accepted, last on W/R) ════
    // Packed 2D form required for Synlig/UHDM RTLIL emission (Yosys synthesis).
    // Write address
    input  logic [N_MASTERS-1:0][AW-1:0]   m_awaddr,
    input  logic [N_MASTERS-1:0][LENW-1:0] m_awlen,
    input  logic [N_MASTERS-1:0][2:0]      m_awsize,
    input  logic [N_MASTERS-1:0][1:0]      m_awburst,
    input  logic [N_MASTERS-1:0]           m_awvalid,
    output logic [N_MASTERS-1:0]           m_awready,
    // Write data
    input  logic [N_MASTERS-1:0][DW-1:0]   m_wdata,
    input  logic [N_MASTERS-1:0][SW-1:0]   m_wstrb,
    input  logic [N_MASTERS-1:0]           m_wlast,
    input  logic [N_MASTERS-1:0]           m_wvalid,
    output logic [N_MASTERS-1:0]           m_wready,
    // Write response
    output logic [N_MASTERS-1:0][1:0]      m_bresp,
    output logic [N_MASTERS-1:0]           m_bvalid,
    input  logic [N_MASTERS-1:0]           m_bready,
    // Read address
    input  logic [N_MASTERS-1:0][AW-1:0]   m_araddr,
    input  logic [N_MASTERS-1:0][LENW-1:0] m_arlen,
    input  logic [N_MASTERS-1:0][2:0]      m_arsize,
    input  logic [N_MASTERS-1:0][1:0]      m_arburst,
    input  logic [N_MASTERS-1:0]           m_arvalid,
    output logic [N_MASTERS-1:0]           m_arready,
    // Read data
    output logic [N_MASTERS-1:0][DW-1:0]   m_rdata,
    output logic [N_MASTERS-1:0][1:0]      m_rresp,
    output logic [N_MASTERS-1:0]           m_rlast,
    output logic [N_MASTERS-1:0]           m_rvalid,
    input  logic [N_MASTERS-1:0]           m_rready,

    // ══ Slave-facing ports (full AXI4 with id) ═══════════════════════════════
    // Packed 2D form required for Synlig/UHDM RTLIL emission (Yosys synthesis).
    // Write address
    output logic [N_SLAVES-1:0][IW-1:0]   s_awid,
    output logic [N_SLAVES-1:0][AW-1:0]   s_awaddr,
    output logic [N_SLAVES-1:0][LENW-1:0] s_awlen,
    output logic [N_SLAVES-1:0][2:0]      s_awsize,
    output logic [N_SLAVES-1:0][1:0]      s_awburst,
    output logic [N_SLAVES-1:0]           s_awvalid,
    input  logic [N_SLAVES-1:0]           s_awready,
    // Write data
    output logic [N_SLAVES-1:0][DW-1:0]   s_wdata,
    output logic [N_SLAVES-1:0][SW-1:0]   s_wstrb,
    output logic [N_SLAVES-1:0]           s_wlast,
    output logic [N_SLAVES-1:0]           s_wvalid,
    input  logic [N_SLAVES-1:0]           s_wready,
    // Write response — s_bid is reserved: responses route via wsel grant register,
    // not by id echo.  Port kept for AXI4-compliant slave interfaces.
    /* verilator lint_off UNUSEDSIGNAL */
    input  logic [N_SLAVES-1:0][IW-1:0]   s_bid,
    /* verilator lint_on  UNUSEDSIGNAL */
    input  logic [N_SLAVES-1:0][1:0]      s_bresp,
    input  logic [N_SLAVES-1:0]           s_bvalid,
    output logic [N_SLAVES-1:0]           s_bready,
    // Read address
    output logic [N_SLAVES-1:0][IW-1:0]   s_arid,
    output logic [N_SLAVES-1:0][AW-1:0]   s_araddr,
    output logic [N_SLAVES-1:0][LENW-1:0] s_arlen,
    output logic [N_SLAVES-1:0][2:0]      s_arsize,
    output logic [N_SLAVES-1:0][1:0]      s_arburst,
    output logic [N_SLAVES-1:0]           s_arvalid,
    input  logic [N_SLAVES-1:0]           s_arready,
    // Read data — s_rid is reserved: responses route via rsel grant register,
    // not by id echo.  Port kept for AXI4-compliant slave interfaces.
    /* verilator lint_off UNUSEDSIGNAL */
    input  logic [N_SLAVES-1:0][IW-1:0]   s_rid,
    /* verilator lint_on  UNUSEDSIGNAL */
    input  logic [N_SLAVES-1:0][DW-1:0]   s_rdata,
    input  logic [N_SLAVES-1:0][1:0]      s_rresp,
    input  logic [N_SLAVES-1:0]           s_rlast,
    input  logic [N_SLAVES-1:0]           s_rvalid,
    output logic [N_SLAVES-1:0]           s_rready
);

    import axi_pkg::*;

    localparam int unsigned MIDX_W = (N_MASTERS > 1) ? $clog2(N_MASTERS) : 1;

    // Address decode: slave index (as logic [31:0]), or N_SLAVES when unmapped.
    // Return type is logic [31:0] (not int unsigned) to avoid the Synlig UHDM
    // RTLIL empty-wire bug on int-unsigned function-result temporaries.
    function automatic logic [31:0] decode(input logic [AW-1:0] a);
        decode = 32'(N_SLAVES);
        for (int unsigned s = 0; s < N_SLAVES; s++) begin
            if (a >= SLV_BASE[s] && a <= SLV_LIMIT[s]) decode = 32'(s);
        end
    endfunction

    // ─────────────────────────────────────────────────────────────────────────
    // Per-slave WRITE engine state
    // ─────────────────────────────────────────────────────────────────────────
    typedef enum logic [1:0] { W_IDLE, W_AW, W_DATA, W_RESP } wstate_e;
    wstate_e [N_SLAVES-1:0]           wstate;
    logic [N_SLAVES-1:0][MIDX_W-1:0]  wsel;        // granted master per slave
    // AW capture registers: latch master AW fields on W_IDLE→W_AW so that a
    // single-cycle AWVALID master (e.g. future GPU store path) is correctly
    // held until the slave asserts AWREADY (AXI4 IHI0022 rule A3-38).
    logic [N_SLAVES-1:0][AW-1:0]      aw_addr_q;
    logic [N_SLAVES-1:0][LENW-1:0]    aw_len_q;
    logic [N_SLAVES-1:0][2:0]         aw_size_q;
    logic [N_SLAVES-1:0][1:0]         aw_burst_q;

    // ─────────────────────────────────────────────────────────────────────────
    // Per-slave READ engine state
    // ─────────────────────────────────────────────────────────────────────────
    typedef enum logic [1:0] { R_IDLE, R_AR, R_DATA } rstate_e;
    rstate_e [N_SLAVES-1:0]           rstate;
    logic [N_SLAVES-1:0][MIDX_W-1:0]  rsel;
    // AR capture registers: latch master AR fields on R_IDLE→R_AR so that a
    // single-cycle ARVALID master (gpu_compute_unit if_arvalid_o) is correctly
    // held until the slave asserts ARREADY (AXI4 IHI0022 rule A3-38).
    logic [N_SLAVES-1:0][AW-1:0]      ar_addr_q;
    logic [N_SLAVES-1:0][LENW-1:0]    ar_len_q;
    logic [N_SLAVES-1:0][2:0]         ar_size_q;
    logic [N_SLAVES-1:0][1:0]         ar_burst_q;

    // Per-slave write/read arbitration pre-compute (combinational).
    // Identifies the lowest-index master requesting this slave this cycle.
    logic [N_SLAVES-1:0]               wr_arb_valid;   // some master wants this slave
    logic [N_SLAVES-1:0][MIDX_W-1:0]  wr_arb_msel;    // winning master index
    logic [N_SLAVES-1:0][AW-1:0]      wr_arb_addr;
    logic [N_SLAVES-1:0][LENW-1:0]    wr_arb_len;
    logic [N_SLAVES-1:0][2:0]         wr_arb_size;
    logic [N_SLAVES-1:0][1:0]         wr_arb_burst;

    logic [N_SLAVES-1:0]               rd_arb_valid;
    logic [N_SLAVES-1:0][MIDX_W-1:0]  rd_arb_msel;
    logic [N_SLAVES-1:0][AW-1:0]      rd_arb_addr;
    logic [N_SLAVES-1:0][LENW-1:0]    rd_arb_len;
    logic [N_SLAVES-1:0][2:0]         rd_arb_size;
    logic [N_SLAVES-1:0][1:0]         rd_arb_burst;

    // ─────────────────────────────────────────────────────────────────────────
    // Per-master DECERR engine state
    // ─────────────────────────────────────────────────────────────────────────
    typedef enum logic [1:0] { DW_IDLE, DW_DATA, DW_RESP } dwstate_e;
    dwstate_e [N_MASTERS-1:0]          dwstate;
    typedef enum logic [0:0] { DR_IDLE, DR_DATA } drstate_e;
    drstate_e [N_MASTERS-1:0]          drstate;
    logic [N_MASTERS-1:0][LENW-1:0]   dr_len;    // latched burst length
    logic [N_MASTERS-1:0][LENW-1:0]   dr_cnt;    // beats sent

    // Unmapped-address flags (one per master, driven from always_comb below).
    logic [N_MASTERS-1:0]              aw_unmapped;
    logic [N_MASTERS-1:0]              ar_unmapped;

    // Master-facing resolution nets (slave-sourced vs decerr-sourced).
    logic [N_MASTERS-1:0]              slv_awready, dec_awready;
    logic [N_MASTERS-1:0]              slv_wready,  dec_wready;
    logic [N_MASTERS-1:0]              slv_bvalid,  dec_bvalid;
    logic [N_MASTERS-1:0][1:0]         slv_bresp;
    logic [N_MASTERS-1:0]              slv_arready, dec_arready;
    logic [N_MASTERS-1:0]              slv_rvalid,  dec_rvalid;
    logic [N_MASTERS-1:0][DW-1:0]      slv_rdata;
    logic [N_MASTERS-1:0][1:0]         slv_rresp;
    logic [N_MASTERS-1:0]              slv_rlast,   dec_rlast;

    // ─────────────────────────────────────────────────────────────────────────
    // Intermediate packed wires for all driven output port arrays.
    // always_comb drives these (Synlig-safe: internal wires, not ports).
    // Continuous assign in generate connects them to the unpacked port arrays.
    // Synlig/UHDM bug: always_comb driving port array slices via loop index
    // produces empty wire names in RTLIL (kernel/rtlil.cc:2150 assert).
    // Continuous assign inside generate is not affected by this bug.
    // ─────────────────────────────────────────────────────────────────────────
    // Slave-side output intermediates (N_SLAVES slices)
    logic [N_SLAVES-1:0][IW-1:0]    _s_awid;
    logic [N_SLAVES-1:0][AW-1:0]    _s_awaddr;
    logic [N_SLAVES-1:0][LENW-1:0]  _s_awlen;
    logic [N_SLAVES-1:0][2:0]       _s_awsize;
    logic [N_SLAVES-1:0][1:0]       _s_awburst;
    logic [N_SLAVES-1:0]            _s_awvalid;
    logic [N_SLAVES-1:0][DW-1:0]    _s_wdata;
    logic [N_SLAVES-1:0][SW-1:0]    _s_wstrb;
    logic [N_SLAVES-1:0]            _s_wlast;
    logic [N_SLAVES-1:0]            _s_wvalid;
    logic [N_SLAVES-1:0]            _s_bready;
    logic [N_SLAVES-1:0][IW-1:0]    _s_arid;
    logic [N_SLAVES-1:0][AW-1:0]    _s_araddr;
    logic [N_SLAVES-1:0][LENW-1:0]  _s_arlen;
    logic [N_SLAVES-1:0][2:0]       _s_arsize;
    logic [N_SLAVES-1:0][1:0]       _s_arburst;
    logic [N_SLAVES-1:0]            _s_arvalid;
    logic [N_SLAVES-1:0]            _s_rready;
    // Master-side output intermediates (N_MASTERS slices)
    logic [N_MASTERS-1:0]           _m_awready;
    logic [N_MASTERS-1:0]           _m_wready;
    logic [N_MASTERS-1:0]           _m_bvalid;
    logic [N_MASTERS-1:0][1:0]      _m_bresp;
    logic [N_MASTERS-1:0]           _m_arready;
    logic [N_MASTERS-1:0]           _m_rvalid;
    logic [N_MASTERS-1:0][DW-1:0]   _m_rdata;
    logic [N_MASTERS-1:0][1:0]      _m_rresp;
    logic [N_MASTERS-1:0]           _m_rlast;

    // ─────────────────────────────────────────────────────────────────────────
    // Write arbitration (combinational priority encoder, one entry per slave).
    // Selects lowest-index master with AWVALID targeting each slave.
    // ─────────────────────────────────────────────────────────────────────────
    always_comb begin
        for (int unsigned s = 0; s < N_SLAVES; s++) begin
            wr_arb_valid[s] = 1'b0;
            wr_arb_msel [s] = '0;
            wr_arb_addr [s] = '0;
            wr_arb_len  [s] = '0;
            wr_arb_size [s] = AXI_SIZE_4B;
            wr_arb_burst[s] = AXI_BURST_INCR;
            for (int unsigned m = 0; m < N_MASTERS; m++) begin
                if (!wr_arb_valid[s] &&
                    m_awvalid[m] && decode(m_awaddr[m]) == s) begin
                    wr_arb_valid[s] = 1'b1;
                    wr_arb_msel [s] = m[MIDX_W-1:0];
                    wr_arb_addr [s] = m_awaddr [m];
                    wr_arb_len  [s] = m_awlen  [m];
                    wr_arb_size [s] = m_awsize [m];
                    wr_arb_burst[s] = m_awburst[m];
                end
            end
        end
    end

    // ─────────────────────────────────────────────────────────────────────────
    // Read arbitration (combinational priority encoder, one entry per slave).
    // ─────────────────────────────────────────────────────────────────────────
    always_comb begin
        for (int unsigned s = 0; s < N_SLAVES; s++) begin
            rd_arb_valid[s] = 1'b0;
            rd_arb_msel [s] = '0;
            rd_arb_addr [s] = '0;
            rd_arb_len  [s] = '0;
            rd_arb_size [s] = AXI_SIZE_4B;
            rd_arb_burst[s] = AXI_BURST_INCR;
            for (int unsigned m = 0; m < N_MASTERS; m++) begin
                if (!rd_arb_valid[s] &&
                    m_arvalid[m] && decode(m_araddr[m]) == s) begin
                    rd_arb_valid[s] = 1'b1;
                    rd_arb_msel [s] = m[MIDX_W-1:0];
                    rd_arb_addr [s] = m_araddr [m];
                    rd_arb_len  [s] = m_arlen  [m];
                    rd_arb_size [s] = m_arsize [m];
                    rd_arb_burst[s] = m_arburst[m];
                end
            end
        end
    end

    // ═════════════════════════ WRITE ENGINES (per slave) ═════════════════════
    // Slave-side drive (combinational, function of state + selected master).
    // Drives _s_* intermediate packed wires — NOT port arrays directly, to
    // avoid the Synlig RTLIL empty-wire bug on proc-assigned port slices.
    always_comb begin
        for (int unsigned s = 0; s < N_SLAVES; s++) begin
            _s_awid   [s] = '0;
            _s_awaddr [s] = '0;
            _s_awlen  [s] = '0;
            _s_awsize [s] = AXI_SIZE_4B;
            _s_awburst[s] = AXI_BURST_INCR;
            _s_awvalid[s] = 1'b0;
            _s_wdata  [s] = '0;
            _s_wstrb  [s] = '0;
            _s_wlast  [s] = 1'b0;
            _s_wvalid [s] = 1'b0;
            _s_bready [s] = 1'b0;
            unique case (wstate[s])
                W_AW: begin
                    // Drive from captured registers, not live master signals.
                    // AW fields were latched on the W_IDLE→W_AW clock edge so
                    // a single-cycle AWVALID master is safely held until
                    // AWREADY (AXI4 IHI0022 rule A3-38).
                    _s_awid   [s] = IW'(wsel[s]);
                    _s_awaddr [s] = aw_addr_q [s];
                    _s_awlen  [s] = aw_len_q  [s];
                    _s_awsize [s] = aw_size_q [s];
                    _s_awburst[s] = aw_burst_q[s];
                    _s_awvalid[s] = 1'b1;   // valid is captured; held until AWREADY
                end
                W_DATA: begin
                    _s_wdata  [s] = m_wdata [wsel[s]];
                    _s_wstrb  [s] = m_wstrb [wsel[s]];
                    _s_wlast  [s] = m_wlast [wsel[s]];
                    _s_wvalid [s] = m_wvalid[wsel[s]];
                end
                W_RESP: begin
                    _s_bready [s] = m_bready[wsel[s]];
                end
                default: ;
            endcase
        end
    end

    // Grant FSM (per slave, sequential).
    always_ff @(posedge clk) begin
        for (int unsigned s = 0; s < N_SLAVES; s++) begin
            if (!rst_n) begin
                wstate    [s] <= W_IDLE;
                wsel      [s] <= '0;
                aw_addr_q [s] <= '0;
                aw_len_q  [s] <= '0;
                aw_size_q [s] <= AXI_SIZE_4B;
                aw_burst_q[s] <= AXI_BURST_INCR;
            end else begin
                unique case (wstate[s])
                    W_IDLE: begin
                        if (wr_arb_valid[s]) begin
                            wsel      [s] <= wr_arb_msel [s];
                            // Capture AW fields now — master may deassert
                            // AWVALID the next cycle (AXI4 single-cycle pulse).
                            aw_addr_q [s] <= wr_arb_addr [s];
                            aw_len_q  [s] <= wr_arb_len  [s];
                            aw_size_q [s] <= wr_arb_size [s];
                            aw_burst_q[s] <= wr_arb_burst[s];
                            wstate    [s] <= W_AW;
                        end
                    end
                    W_AW:   if (s_awready[s]) wstate[s] <= W_DATA;
                    W_DATA: if (s_wvalid[s] && s_wready[s] && m_wlast[wsel[s]])
                                wstate[s] <= W_RESP;
                    W_RESP: if (s_bvalid[s] && s_bready[s]) wstate[s] <= W_IDLE;
                    default: wstate[s] <= W_IDLE;
                endcase
            end
        end
    end

    // ═════════════════════════ READ ENGINES (per slave) ══════════════════════
    // Drives _s_ar*/_s_rready intermediates — not port arrays directly.
    always_comb begin
        for (int unsigned s = 0; s < N_SLAVES; s++) begin
            _s_arid   [s] = '0;
            _s_araddr [s] = '0;
            _s_arlen  [s] = '0;
            _s_arsize [s] = AXI_SIZE_4B;
            _s_arburst[s] = AXI_BURST_INCR;
            _s_arvalid[s] = 1'b0;
            _s_rready [s] = 1'b0;
            unique case (rstate[s])
                R_AR: begin
                    // Drive from captured registers, not live master signals.
                    // AR fields were latched on the R_IDLE→R_AR clock edge so
                    // a single-cycle ARVALID master (e.g. gpu_compute_unit
                    // if_arvalid_o) is correctly held until ARREADY
                    // (AXI4 IHI0022 rule A3-38).
                    _s_arid   [s] = IW'(rsel[s]);
                    _s_araddr [s] = ar_addr_q [s];
                    _s_arlen  [s] = ar_len_q  [s];
                    _s_arsize [s] = ar_size_q [s];
                    _s_arburst[s] = ar_burst_q[s];
                    _s_arvalid[s] = 1'b1;   // valid is captured; held until ARREADY
                end
                R_DATA: begin
                    _s_rready [s] = m_rready[rsel[s]];
                end
                default: ;
            endcase
        end
    end

    always_ff @(posedge clk) begin
        for (int unsigned s = 0; s < N_SLAVES; s++) begin
            if (!rst_n) begin
                rstate    [s] <= R_IDLE;
                rsel      [s] <= '0;
                ar_addr_q [s] <= '0;
                ar_len_q  [s] <= '0;
                ar_size_q [s] <= AXI_SIZE_4B;
                ar_burst_q[s] <= AXI_BURST_INCR;
            end else begin
                unique case (rstate[s])
                    R_IDLE: begin
                        if (rd_arb_valid[s]) begin
                            rsel      [s] <= rd_arb_msel [s];
                            // Capture AR fields now — master may deassert
                            // ARVALID the next cycle (AXI4 single-cycle pulse,
                            // e.g. gpu_compute_unit if_arvalid_o).
                            ar_addr_q [s] <= rd_arb_addr [s];
                            ar_len_q  [s] <= rd_arb_len  [s];
                            ar_size_q [s] <= rd_arb_size [s];
                            ar_burst_q[s] <= rd_arb_burst[s];
                            rstate    [s] <= R_AR;
                        end
                    end
                    R_AR:   if (s_arready[s]) rstate[s] <= R_DATA;
                    R_DATA: if (s_rvalid[s] && s_rready[s] && s_rlast[s])
                                rstate[s] <= R_IDLE;
                    default: rstate[s] <= R_IDLE;
                endcase
            end
        end
    end

    // ═════════════════════════ DECERR ENGINES (per master) ═══════════════════
    // Unmapped-address detection (combinational).
    always_comb begin
        for (int unsigned m = 0; m < N_MASTERS; m++) begin
            aw_unmapped[m] = m_awvalid[m] && (decode(m_awaddr[m]) == N_SLAVES);
            ar_unmapped[m] = m_arvalid[m] && (decode(m_araddr[m]) == N_SLAVES);
        end
    end

    // Write DECERR (combinational outputs).
    always_comb begin
        for (int unsigned m = 0; m < N_MASTERS; m++) begin
            dec_awready[m] = 1'b0;
            dec_wready [m] = 1'b0;
            dec_bvalid [m] = 1'b0;
            unique case (dwstate[m])
                DW_IDLE: dec_awready[m] = aw_unmapped[m];
                DW_DATA: dec_wready [m] = 1'b1;          // sink all W beats
                DW_RESP: dec_bvalid [m] = 1'b1;
                default: ;
            endcase
        end
    end

    // Write DECERR FSM (sequential).
    always_ff @(posedge clk) begin
        for (int unsigned m = 0; m < N_MASTERS; m++) begin
            if (!rst_n) dwstate[m] <= DW_IDLE;
            else unique case (dwstate[m])
                DW_IDLE: if (aw_unmapped[m]) dwstate[m] <= DW_DATA;
                DW_DATA: if (m_wvalid[m] && m_wlast[m]) dwstate[m] <= DW_RESP;
                DW_RESP: if (m_bready[m]) dwstate[m] <= DW_IDLE;
                default: dwstate[m] <= DW_IDLE;
            endcase
        end
    end

    // Read DECERR (combinational outputs — returns arlen+1 DECERR beats).
    always_comb begin
        for (int unsigned m = 0; m < N_MASTERS; m++) begin
            dec_arready[m] = 1'b0;
            dec_rvalid [m] = 1'b0;
            dec_rlast  [m] = 1'b0;
            unique case (drstate[m])
                DR_IDLE: dec_arready[m] = ar_unmapped[m];
                DR_DATA: begin
                    dec_rvalid[m] = 1'b1;
                    dec_rlast [m] = (dr_cnt[m] == dr_len[m]);
                end
                default: ;
            endcase
        end
    end

    // Read DECERR FSM (sequential).
    always_ff @(posedge clk) begin
        for (int unsigned m = 0; m < N_MASTERS; m++) begin
            if (!rst_n) begin
                drstate[m] <= DR_IDLE;
                dr_len [m] <= '0;
                dr_cnt [m] <= '0;
            end else unique case (drstate[m])
                DR_IDLE: if (ar_unmapped[m]) begin
                    dr_len [m] <= m_arlen[m];
                    dr_cnt [m] <= '0;
                    drstate[m] <= DR_DATA;
                end
                DR_DATA: if (m_rready[m]) begin
                    if (dr_cnt[m] == dr_len[m]) drstate[m] <= DR_IDLE;
                    else                        dr_cnt[m]  <= dr_cnt[m] + 1'b1;
                end
                default: drstate[m] <= DR_IDLE;
            endcase
        end
    end

    // ═════════════════ MASTER-FACING RESOLUTION (scan slaves) ════════════════
    always_comb begin
        // aw_priority_winner[m][s]: 1 when master m is the highest-priority
        // (lowest index) master presenting a valid AW request to slave s.
        // Used to ensure the early-accept W_IDLE arm grants awready to exactly
        // one master per slave per cycle — the same winner the FSM captures.
        logic aw_priority_winner [N_MASTERS][N_SLAVES];
        logic ar_priority_winner [N_MASTERS][N_SLAVES];
        for (int unsigned m = 0; m < N_MASTERS; m++) begin
            for (int unsigned s = 0; s < N_SLAVES; s++) begin
                aw_priority_winner[m][s] = 1'b1;
                ar_priority_winner[m][s] = 1'b1;
                // Check if any lower-index master also targets this slave.
                for (int unsigned m2 = 0; m2 < m; m2++) begin
                    if (m_awvalid[m2] && decode(m_awaddr[m2]) == s)
                        aw_priority_winner[m][s] = 1'b0;
                    if (m_arvalid[m2] && decode(m_araddr[m2]) == s)
                        ar_priority_winner[m][s] = 1'b0;
                end
            end
        end

        for (int unsigned m = 0; m < N_MASTERS; m++) begin
            slv_awready[m] = 1'b0;
            slv_wready [m] = 1'b0;
            slv_bvalid [m] = 1'b0;
            slv_bresp  [m] = AXI_RESP_OKAY;
            slv_arready[m] = 1'b0;
            slv_rvalid [m] = 1'b0;
            slv_rdata  [m] = '0;
            slv_rresp  [m] = AXI_RESP_OKAY;
            slv_rlast  [m] = 1'b0;
            for (int unsigned s = 0; s < N_SLAVES; s++) begin
                // Write path
                // Early-accept (W_IDLE): grant awready only to the priority-
                // winner master — the same master the FSM captures into wsel.
                // Single-grant invariant: at most one master per slave per cycle
                // sees awready=1 from the early-accept arm, preventing the
                // "both see ready, only winner captured" silent-drop bug.
                if (wstate[s] == W_IDLE &&
                    m_awvalid[m] && decode(m_awaddr[m]) == s &&
                    aw_priority_winner[m][s])
                    slv_awready[m] = 1'b1;
                if (wstate[s] == W_AW   && wsel[s] == m[MIDX_W-1:0])
                    slv_awready[m] = s_awready[s];
                if (wstate[s] == W_DATA && wsel[s] == m[MIDX_W-1:0])
                    slv_wready [m] = s_wready[s];
                if (wstate[s] == W_RESP && wsel[s] == m[MIDX_W-1:0]) begin
                    slv_bvalid[m] = s_bvalid[s];
                    slv_bresp [m] = s_bresp [s];
                end
                // Read path
                // Early-accept (R_IDLE): grant arready only to the priority-
                // winner master — the same master the FSM captures into rsel.
                // Single-grant invariant: at most one master per slave per cycle
                // sees arready=1 from the early-accept arm.  The address is
                // latched in ar_*_q on this clock edge; s_arvalid to the slave
                // is driven 1'b1 from ar_*_q starting next cycle.
                if (rstate[s] == R_IDLE &&
                    m_arvalid[m] && decode(m_araddr[m]) == s &&
                    ar_priority_winner[m][s])
                    slv_arready[m] = 1'b1;
                if (rstate[s] == R_AR   && rsel[s] == m[MIDX_W-1:0])
                    slv_arready[m] = s_arready[s];
                if (rstate[s] == R_DATA && rsel[s] == m[MIDX_W-1:0]) begin
                    slv_rvalid[m] = s_rvalid[s];
                    slv_rdata [m] = s_rdata [s];
                    slv_rresp [m] = s_rresp [s];
                    slv_rlast [m] = s_rlast [s];
                end
            end
        end
    end

    // Combine slave-sourced and DECERR-sourced master responses into _m_* intermediates.
    // Does NOT drive port arrays directly — see generate assigns below.
    always_comb begin
        for (int unsigned m = 0; m < N_MASTERS; m++) begin
            _m_awready[m] = slv_awready[m] | dec_awready[m];
            _m_wready [m] = slv_wready [m] | dec_wready [m];
            _m_bvalid [m] = slv_bvalid [m] | dec_bvalid [m];
            _m_bresp  [m] = dec_bvalid [m] ? AXI_RESP_DECERR : slv_bresp[m];

            _m_arready[m] = slv_arready[m] | dec_arready[m];
            _m_rvalid [m] = slv_rvalid [m] | dec_rvalid [m];
            _m_rdata  [m] = dec_rvalid [m] ? '0             : slv_rdata[m];
            _m_rresp  [m] = dec_rvalid [m] ? AXI_RESP_DECERR : slv_rresp[m];
            _m_rlast  [m] = dec_rvalid [m] ? dec_rlast[m]   : slv_rlast[m];
        end
    end

    // ─────────────────────────────────────────────────────────────────────────
    // Port bridging: connect packed intermediate wires to packed port arrays.
    // Ports are now packed 2D — direct whole-array assignment avoids the Synlig
    // RTLIL empty-wire bug entirely (no generate/genvar needed).
    // ─────────────────────────────────────────────────────────────────────────
    assign s_awid    = _s_awid;
    assign s_awaddr  = _s_awaddr;
    assign s_awlen   = _s_awlen;
    assign s_awsize  = _s_awsize;
    assign s_awburst = _s_awburst;
    assign s_awvalid = _s_awvalid;
    assign s_wdata   = _s_wdata;
    assign s_wstrb   = _s_wstrb;
    assign s_wlast   = _s_wlast;
    assign s_wvalid  = _s_wvalid;
    assign s_bready  = _s_bready;
    assign s_arid    = _s_arid;
    assign s_araddr  = _s_araddr;
    assign s_arlen   = _s_arlen;
    assign s_arsize  = _s_arsize;
    assign s_arburst = _s_arburst;
    assign s_arvalid = _s_arvalid;
    assign s_rready  = _s_rready;

    assign m_awready = _m_awready;
    assign m_wready  = _m_wready;
    assign m_bvalid  = _m_bvalid;
    assign m_bresp   = _m_bresp;
    assign m_arready = _m_arready;
    assign m_rvalid  = _m_rvalid;
    assign m_rdata   = _m_rdata;
    assign m_rresp   = _m_rresp;
    assign m_rlast   = _m_rlast;

endmodule : axi4_crossbar
