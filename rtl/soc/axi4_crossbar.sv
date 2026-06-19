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
//
// Lint note: flat unpacked-array ports, genvar engines, no SVA (sim-friendly).

module axi4_crossbar #(
    parameter int unsigned N_MASTERS = 3,
    parameter int unsigned N_SLAVES  = 2,
    parameter int unsigned AW        = axi_pkg::AXI_ADDR_WIDTH,
    parameter int unsigned DW        = axi_pkg::AXI_DATA_WIDTH,
    parameter int unsigned SW        = axi_pkg::AXI_STRB_WIDTH,
    parameter int unsigned IW        = axi_pkg::AXI_ID_WIDTH,
    parameter int unsigned LENW      = axi_pkg::AXI_LEN_WIDTH,
    // Per-slave address bounds (inclusive).
    parameter logic [31:0] SLV_BASE  [N_SLAVES] = '{default: '0},
    parameter logic [31:0] SLV_LIMIT [N_SLAVES] = '{default: '0}
) (
    input  logic clk,
    input  logic rst_n,

    // ══ Master-facing ports (no id; len/size/burst accepted, last on W/R) ════
    // Write address
    input  logic [AW-1:0]   m_awaddr   [N_MASTERS],
    input  logic [LENW-1:0] m_awlen    [N_MASTERS],
    input  logic [2:0]      m_awsize   [N_MASTERS],
    input  logic [1:0]      m_awburst  [N_MASTERS],
    input  logic            m_awvalid  [N_MASTERS],
    output logic            m_awready  [N_MASTERS],
    // Write data
    input  logic [DW-1:0]   m_wdata    [N_MASTERS],
    input  logic [SW-1:0]   m_wstrb    [N_MASTERS],
    input  logic            m_wlast    [N_MASTERS],
    input  logic            m_wvalid   [N_MASTERS],
    output logic            m_wready   [N_MASTERS],
    // Write response
    output logic [1:0]      m_bresp    [N_MASTERS],
    output logic            m_bvalid   [N_MASTERS],
    input  logic            m_bready   [N_MASTERS],
    // Read address
    input  logic [AW-1:0]   m_araddr   [N_MASTERS],
    input  logic [LENW-1:0] m_arlen    [N_MASTERS],
    input  logic [2:0]      m_arsize   [N_MASTERS],
    input  logic [1:0]      m_arburst  [N_MASTERS],
    input  logic            m_arvalid  [N_MASTERS],
    output logic            m_arready  [N_MASTERS],
    // Read data
    output logic [DW-1:0]   m_rdata    [N_MASTERS],
    output logic [1:0]      m_rresp    [N_MASTERS],
    output logic            m_rlast    [N_MASTERS],
    output logic            m_rvalid   [N_MASTERS],
    input  logic            m_rready   [N_MASTERS],

    // ══ Slave-facing ports (full AXI4 with id) ═══════════════════════════════
    // Write address
    output logic [IW-1:0]   s_awid     [N_SLAVES],
    output logic [AW-1:0]   s_awaddr   [N_SLAVES],
    output logic [LENW-1:0] s_awlen    [N_SLAVES],
    output logic [2:0]      s_awsize   [N_SLAVES],
    output logic [1:0]      s_awburst  [N_SLAVES],
    output logic            s_awvalid  [N_SLAVES],
    input  logic            s_awready  [N_SLAVES],
    // Write data
    output logic [DW-1:0]   s_wdata    [N_SLAVES],
    output logic [SW-1:0]   s_wstrb    [N_SLAVES],
    output logic            s_wlast    [N_SLAVES],
    output logic            s_wvalid   [N_SLAVES],
    input  logic            s_wready   [N_SLAVES],
    // Write response — s_bid is reserved: responses route via wsel grant register,
    // not by id echo.  Port kept for AXI4-compliant slave interfaces.
    /* verilator lint_off UNUSEDSIGNAL */
    input  logic [IW-1:0]   s_bid      [N_SLAVES],
    /* verilator lint_on  UNUSEDSIGNAL */
    input  logic [1:0]      s_bresp    [N_SLAVES],
    input  logic            s_bvalid   [N_SLAVES],
    output logic            s_bready   [N_SLAVES],
    // Read address
    output logic [IW-1:0]   s_arid     [N_SLAVES],
    output logic [AW-1:0]   s_araddr   [N_SLAVES],
    output logic [LENW-1:0] s_arlen    [N_SLAVES],
    output logic [2:0]      s_arsize   [N_SLAVES],
    output logic [1:0]      s_arburst  [N_SLAVES],
    output logic            s_arvalid  [N_SLAVES],
    input  logic            s_arready  [N_SLAVES],
    // Read data — s_rid is reserved: responses route via rsel grant register,
    // not by id echo.  Port kept for AXI4-compliant slave interfaces.
    /* verilator lint_off UNUSEDSIGNAL */
    input  logic [IW-1:0]   s_rid      [N_SLAVES],
    /* verilator lint_on  UNUSEDSIGNAL */
    input  logic [DW-1:0]   s_rdata    [N_SLAVES],
    input  logic [1:0]      s_rresp    [N_SLAVES],
    input  logic            s_rlast    [N_SLAVES],
    input  logic            s_rvalid   [N_SLAVES],
    output logic            s_rready   [N_SLAVES]
);

    import axi_pkg::*;

    localparam int unsigned MIDX_W = (N_MASTERS > 1) ? $clog2(N_MASTERS) : 1;

    // Address decode: slave index, or N_SLAVES when unmapped.
    function automatic int unsigned decode(input logic [AW-1:0] a);
        decode = N_SLAVES;
        for (int unsigned s = 0; s < N_SLAVES; s++) begin
            if (a >= SLV_BASE[s] && a <= SLV_LIMIT[s]) decode = s;
        end
    endfunction

    // ─────────────────────────────────────────────────────────────────────────
    // Per-slave WRITE engine
    // ─────────────────────────────────────────────────────────────────────────
    typedef enum logic [1:0] { W_IDLE, W_AW, W_DATA, W_RESP } wstate_e;
    wstate_e            wstate    [N_SLAVES];
    logic [MIDX_W-1:0]  wsel      [N_SLAVES];   // granted master per slave
    // AW capture registers: latch master AW fields on W_IDLE→W_AW so that a
    // single-cycle AWVALID master (e.g. future GPU store path) is correctly
    // held until the slave asserts AWREADY (AXI4 IHI0022 rule A3-38).
    logic [AW-1:0]      aw_addr_q [N_SLAVES];
    logic [LENW-1:0]    aw_len_q  [N_SLAVES];
    logic [2:0]         aw_size_q [N_SLAVES];
    logic [1:0]         aw_burst_q[N_SLAVES];

    // ─────────────────────────────────────────────────────────────────────────
    // Per-slave READ engine
    // ─────────────────────────────────────────────────────────────────────────
    typedef enum logic [1:0] { R_IDLE, R_AR, R_DATA } rstate_e;
    rstate_e            rstate    [N_SLAVES];
    logic [MIDX_W-1:0]  rsel      [N_SLAVES];
    // AR capture registers: latch master AR fields on R_IDLE→R_AR so that a
    // single-cycle ARVALID master (gpu_compute_unit if_arvalid_o) is correctly
    // held until the slave asserts ARREADY (AXI4 IHI0022 rule A3-38).
    logic [AW-1:0]      ar_addr_q [N_SLAVES];
    logic [LENW-1:0]    ar_len_q  [N_SLAVES];
    logic [2:0]         ar_size_q [N_SLAVES];
    logic [1:0]         ar_burst_q[N_SLAVES];

    // ─────────────────────────────────────────────────────────────────────────
    // Per-master DECERR engines (for unmapped addresses)
    // ─────────────────────────────────────────────────────────────────────────
    typedef enum logic [1:0] { DW_IDLE, DW_DATA, DW_RESP } dwstate_e;
    dwstate_e dwstate [N_MASTERS];
    typedef enum logic [0:0] { DR_IDLE, DR_DATA } drstate_e;
    drstate_e          drstate [N_MASTERS];
    logic [LENW-1:0]   dr_len  [N_MASTERS];   // latched burst length
    logic [LENW-1:0]   dr_cnt  [N_MASTERS];   // beats sent

    // Master-facing resolution nets (slave-sourced vs decerr-sourced).
    logic           slv_awready [N_MASTERS], dec_awready [N_MASTERS];
    logic           slv_wready  [N_MASTERS], dec_wready  [N_MASTERS];
    logic           slv_bvalid  [N_MASTERS], dec_bvalid  [N_MASTERS];
    logic [1:0]     slv_bresp   [N_MASTERS];
    logic           slv_arready [N_MASTERS], dec_arready [N_MASTERS];
    logic           slv_rvalid  [N_MASTERS], dec_rvalid  [N_MASTERS];
    logic [DW-1:0]  slv_rdata   [N_MASTERS];
    logic [1:0]     slv_rresp   [N_MASTERS];
    logic           slv_rlast   [N_MASTERS], dec_rlast   [N_MASTERS];

    genvar gs, gm;

    // ═════════════════════════ WRITE ENGINES (per slave) ═════════════════════
    generate
    for (gs = 0; gs < N_SLAVES; gs++) begin : g_wr_engine
        // Slave-side drive (combinational, function of state + selected master).
        always_comb begin
            s_awid   [gs] = '0;
            s_awaddr [gs] = '0;
            s_awlen  [gs] = '0;
            s_awsize [gs] = AXI_SIZE_4B;
            s_awburst[gs] = AXI_BURST_INCR;
            s_awvalid[gs] = 1'b0;
            s_wdata  [gs] = '0;
            s_wstrb  [gs] = '0;
            s_wlast  [gs] = 1'b0;
            s_wvalid [gs] = 1'b0;
            s_bready [gs] = 1'b0;
            unique case (wstate[gs])
                W_AW: begin
                    // Drive from captured registers, not live master signals.
                    // AW fields were latched on the W_IDLE→W_AW clock edge so
                    // a single-cycle AWVALID master is safely held until
                    // AWREADY (AXI4 IHI0022 rule A3-38).
                    s_awid   [gs] = IW'(wsel[gs]);
                    s_awaddr [gs] = aw_addr_q [gs];
                    s_awlen  [gs] = aw_len_q  [gs];
                    s_awsize [gs] = aw_size_q [gs];
                    s_awburst[gs] = aw_burst_q[gs];
                    s_awvalid[gs] = 1'b1;   // valid is captured; held until AWREADY
                end
                W_DATA: begin
                    s_wdata  [gs] = m_wdata [wsel[gs]];
                    s_wstrb  [gs] = m_wstrb [wsel[gs]];
                    s_wlast  [gs] = m_wlast [wsel[gs]];
                    s_wvalid [gs] = m_wvalid[wsel[gs]];
                end
                W_RESP: begin
                    s_bready [gs] = m_bready[wsel[gs]];
                end
                default: ;
            endcase
        end

        // Grant FSM.
        always_ff @(posedge clk) begin
            if (!rst_n) begin
                wstate    [gs] <= W_IDLE;
                wsel      [gs] <= '0;
                aw_addr_q [gs] <= '0;
                aw_len_q  [gs] <= '0;
                aw_size_q [gs] <= AXI_SIZE_4B;
                aw_burst_q[gs] <= AXI_BURST_INCR;
            end else begin
                unique case (wstate[gs])
                    W_IDLE: begin
                        // found_wr prevents lower-priority (higher-index) masters
                        // from overwriting the capture once the priority winner
                        // (lowest index) has been latched.  This matches the
                        // aw_priority_winner logic in the master-facing resolution
                        // block, which gates early-accept arready/awready on the
                        // same lowest-index criterion.
                        begin : wr_arb
                            logic found_wr;
                            found_wr = 1'b0;
                            for (int unsigned m = 0; m < N_MASTERS; m++) begin
                                if (!found_wr &&
                                    m_awvalid[m] && decode(m_awaddr[m]) == gs) begin
                                    wsel      [gs] <= m[MIDX_W-1:0];
                                    // Capture AW fields now — master may deassert
                                    // AWVALID the next cycle (AXI4 single-cycle pulse).
                                    aw_addr_q [gs] <= m_awaddr [m];
                                    aw_len_q  [gs] <= m_awlen  [m];
                                    aw_size_q [gs] <= m_awsize [m];
                                    aw_burst_q[gs] <= m_awburst[m];
                                    wstate    [gs] <= W_AW;
                                    found_wr        = 1'b1;
                                end
                            end
                        end
                    end
                    W_AW:   if (s_awready[gs]) wstate[gs] <= W_DATA;
                    W_DATA: if (s_wvalid[gs] && s_wready[gs] && m_wlast[wsel[gs]])
                                wstate[gs] <= W_RESP;
                    W_RESP: if (s_bvalid[gs] && s_bready[gs]) wstate[gs] <= W_IDLE;
                    default: wstate[gs] <= W_IDLE;
                endcase
            end
        end
    end
    endgenerate

    // ═════════════════════════ READ ENGINES (per slave) ══════════════════════
    generate
    for (gs = 0; gs < N_SLAVES; gs++) begin : g_rd_engine
        always_comb begin
            s_arid   [gs] = '0;
            s_araddr [gs] = '0;
            s_arlen  [gs] = '0;
            s_arsize [gs] = AXI_SIZE_4B;
            s_arburst[gs] = AXI_BURST_INCR;
            s_arvalid[gs] = 1'b0;
            s_rready [gs] = 1'b0;
            unique case (rstate[gs])
                R_AR: begin
                    // Drive from captured registers, not live master signals.
                    // AR fields were latched on the R_IDLE→R_AR clock edge so
                    // a single-cycle ARVALID master (e.g. gpu_compute_unit
                    // if_arvalid_o) is correctly held until ARREADY
                    // (AXI4 IHI0022 rule A3-38).
                    s_arid   [gs] = IW'(rsel[gs]);
                    s_araddr [gs] = ar_addr_q [gs];
                    s_arlen  [gs] = ar_len_q  [gs];
                    s_arsize [gs] = ar_size_q [gs];
                    s_arburst[gs] = ar_burst_q[gs];
                    s_arvalid[gs] = 1'b1;   // valid is captured; held until ARREADY
                end
                R_DATA: begin
                    s_rready [gs] = m_rready[rsel[gs]];
                end
                default: ;
            endcase
        end

        always_ff @(posedge clk) begin
            if (!rst_n) begin
                rstate    [gs] <= R_IDLE;
                rsel      [gs] <= '0;
                ar_addr_q [gs] <= '0;
                ar_len_q  [gs] <= '0;
                ar_size_q [gs] <= AXI_SIZE_4B;
                ar_burst_q[gs] <= AXI_BURST_INCR;
            end else begin
                unique case (rstate[gs])
                    R_IDLE: begin
                        // found_rd prevents lower-priority (higher-index) masters
                        // from overwriting the capture once the priority winner
                        // (lowest index) has been latched.  This matches the
                        // ar_priority_winner logic in the master-facing resolution
                        // block, which gates early-accept arready on the same
                        // lowest-index criterion.
                        begin : rd_arb
                            logic found_rd;
                            found_rd = 1'b0;
                            for (int unsigned m = 0; m < N_MASTERS; m++) begin
                                if (!found_rd &&
                                    m_arvalid[m] && decode(m_araddr[m]) == gs) begin
                                    rsel      [gs] <= m[MIDX_W-1:0];
                                    // Capture AR fields now — master may deassert
                                    // ARVALID the next cycle (AXI4 single-cycle pulse,
                                    // e.g. gpu_compute_unit if_arvalid_o).
                                    ar_addr_q [gs] <= m_araddr [m];
                                    ar_len_q  [gs] <= m_arlen  [m];
                                    ar_size_q [gs] <= m_arsize [m];
                                    ar_burst_q[gs] <= m_arburst[m];
                                    rstate    [gs] <= R_AR;
                                    found_rd        = 1'b1;
                                end
                            end
                        end
                    end
                    R_AR:   if (s_arready[gs]) rstate[gs] <= R_DATA;
                    R_DATA: if (s_rvalid[gs] && s_rready[gs] && s_rlast[gs])
                                rstate[gs] <= R_IDLE;
                    default: rstate[gs] <= R_IDLE;
                endcase
            end
        end
    end
    endgenerate

    // ═════════════════════════ DECERR ENGINES (per master) ═══════════════════
    generate
    for (gm = 0; gm < N_MASTERS; gm++) begin : g_decerr
        logic aw_unmapped, ar_unmapped;
        assign aw_unmapped = m_awvalid[gm] && (decode(m_awaddr[gm]) == N_SLAVES);
        assign ar_unmapped = m_arvalid[gm] && (decode(m_araddr[gm]) == N_SLAVES);

        // Write DECERR
        always_comb begin
            dec_awready[gm] = 1'b0;
            dec_wready [gm] = 1'b0;
            dec_bvalid [gm] = 1'b0;
            unique case (dwstate[gm])
                DW_IDLE: dec_awready[gm] = aw_unmapped;
                DW_DATA: dec_wready [gm] = 1'b1;          // sink all W beats
                DW_RESP: dec_bvalid [gm] = 1'b1;
                default: ;
            endcase
        end
        always_ff @(posedge clk) begin
            if (!rst_n) dwstate[gm] <= DW_IDLE;
            else unique case (dwstate[gm])
                DW_IDLE: if (aw_unmapped) dwstate[gm] <= DW_DATA;
                DW_DATA: if (m_wvalid[gm] && m_wlast[gm]) dwstate[gm] <= DW_RESP;
                DW_RESP: if (m_bready[gm]) dwstate[gm] <= DW_IDLE;
                default: dwstate[gm] <= DW_IDLE;
            endcase
        end

        // Read DECERR (returns arlen+1 DECERR beats)
        always_comb begin
            dec_arready[gm] = 1'b0;
            dec_rvalid [gm] = 1'b0;
            dec_rlast  [gm] = 1'b0;
            unique case (drstate[gm])
                DR_IDLE: dec_arready[gm] = ar_unmapped;
                DR_DATA: begin
                    dec_rvalid[gm] = 1'b1;
                    dec_rlast [gm] = (dr_cnt[gm] == dr_len[gm]);
                end
                default: ;
            endcase
        end
        always_ff @(posedge clk) begin
            if (!rst_n) begin
                drstate[gm] <= DR_IDLE;
                dr_len [gm] <= '0;
                dr_cnt [gm] <= '0;
            end else unique case (drstate[gm])
                DR_IDLE: if (ar_unmapped) begin
                    dr_len [gm] <= m_arlen[gm];
                    dr_cnt [gm] <= '0;
                    drstate[gm] <= DR_DATA;
                end
                DR_DATA: if (m_rready[gm]) begin
                    if (dr_cnt[gm] == dr_len[gm]) drstate[gm] <= DR_IDLE;
                    else                          dr_cnt[gm]  <= dr_cnt[gm] + 1'b1;
                end
                default: drstate[gm] <= DR_IDLE;
            endcase
        end
    end
    endgenerate

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

    // Combine slave-sourced and DECERR-sourced master responses.
    generate
    for (gm = 0; gm < N_MASTERS; gm++) begin : g_mout
        assign m_awready[gm] = slv_awready[gm] | dec_awready[gm];
        assign m_wready [gm] = slv_wready [gm] | dec_wready [gm];
        assign m_bvalid [gm] = slv_bvalid [gm] | dec_bvalid [gm];
        assign m_bresp  [gm] = dec_bvalid [gm] ? AXI_RESP_DECERR : slv_bresp[gm];

        assign m_arready[gm] = slv_arready[gm] | dec_arready[gm];
        assign m_rvalid [gm] = slv_rvalid [gm] | dec_rvalid [gm];
        assign m_rdata  [gm] = dec_rvalid [gm] ? '0             : slv_rdata[gm];
        assign m_rresp  [gm] = dec_rvalid [gm] ? AXI_RESP_DECERR : slv_rresp[gm];
        assign m_rlast  [gm] = dec_rvalid [gm] ? dec_rlast[gm]  : slv_rlast[gm];
    end
    endgenerate

endmodule : axi4_crossbar
