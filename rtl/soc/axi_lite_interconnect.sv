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
// Design points (see Doc: ds:ch:phase5-soc-integration-plan M3):
//   * Depth-1 outstanding write + depth-1 outstanding read (independent).  The
//     selected slave is latched for the life of the transaction.
//   * Unmapped address -> the interconnect itself returns a DECERR response and
//     completes the transfer (a bad config access never stalls the CPU).
//   * A slave slot that slv_off_i marks as off is answered by the interconnect itself with SLVERR and the read data
//     OFF_RDATA. The request is accepted and never forwarded, also when the flag rises after the transaction started.
//     Each transaction latches the flag (w_off, r_off), so a flag edge during a transaction does not split it.
//     Unmapped addresses keep DECERR and take priority over the off flag. Doc: ds:mod:axi-lite-interconnect
//   * Bounded wait (TIMEOUT_CYCLES, 0 = off). One counter per engine counts the clk cycles in which the selected
//     slot owes progress: AW, W or AR not taken, or B or R not given. Master stalls do not count. At the bound
//     the engine answers SLVERR itself (read data OFF_RDATA), once, takes the master side, and sets the stale bit
//     of that slot for that engine. A request the slot has not taken stays presented from a holder register
//     (one per engine; a second timed-out request while it is busy is dropped).
//     A stale slot gets each new access of that engine answered locally like an off slot, never forwarded. B or R
//     READY stays high towards it, so the late response is absorbed and clears the stale bit. Other slots and the
//     other engine are not affected. Order: DECERR, then the local answer for an off or stale slot. An off and
//     stale slot gives the off answer, and its stale bit waits for the absorption.
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
    parameter logic [N_SLAVES-1:0][AW-1:0] SLV_LIMIT = '0,
    // Read data returned by the local response of an off slot.
    parameter logic [DW-1:0] OFF_RDATA = DW'(32'hDEAD_BEEF),
    // Bound of a wait for a slot, in clk cycles. 0 turns the bounded wait off.
    parameter int unsigned TIMEOUT_CYCLES = 4096
) (
    input  logic clk,
    input  logic rst_n,

    // Per-slot off level in clk. Tie to 0 for a slot that is always on.
    input  logic [N_SLAVES-1:0] slv_off_i,

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

    localparam bit          TO_EN   = (TIMEOUT_CYCLES != 0);
    localparam int unsigned CW      = (TIMEOUT_CYCLES > 1) ? $clog2(TIMEOUT_CYCLES + 1) : 1;
    localparam logic [CW-1:0] TO_LAST = CW'(TIMEOUT_CYCLES - 1);   // wait cycles before the answering cycle

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
    logic            w_off_q;  // selected slot was off at some point in this transaction (sticky) -> SLVERR
    logic            w_off;    // w_off_q or the selected slot is off now; meaningful when !w_dec
    logic            w_slv_off;
    // A forwarded slave response is on m_axil_bvalid and not yet accepted. The response is then locked: the off flag cannot replace it.
    logic            w_b_lock_q;

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

    // Off level of the selected slot, by compare and OR (no runtime-indexed mux).
    logic aw_dec_off;
    always_comb begin
        w_slv_off  = 1'b0;
        aw_dec_off = 1'b0;
        for (int unsigned s = 0; s < N_SLAVES; s++) begin
            if (wsel == SELW'(s))               w_slv_off  = w_slv_off  | slv_off_i[s];
            if (aw_decode_d == 32'(s))          aw_dec_off = aw_dec_off | slv_off_i[s];
        end
    end
    assign w_off = w_off_q | (w_slv_off & ~w_b_lock_q);

    logic aw_hs, w_hs, b_hs;
    assign aw_hs = m_axil_awvalid && m_axil_awready;
    assign w_hs  = m_axil_wvalid  && m_axil_wready;
    assign b_hs  = m_axil_bvalid  && m_axil_bready;

    // Bounded wait, write engine. w_stale_q: the slot may still answer a write that timed out.
    // Holder: AW (w_pa_q) and W (w_pw_q) that the slot w_psel_q has not accepted yet.
    logic [N_SLAVES-1:0] w_stale_q;
    logic [N_SLAVES-1:0] w_stale;
    logic [N_SLAVES-1:0] w_pend;
    logic                w_pa_q, w_pw_q, w_pw_have_q;
    logic [SELW-1:0]     w_psel_q;
    logic [AW-1:0]       w_paddr_q;
    logic [2:0]          w_pprot_q;
    logic [DW-1:0]       w_pdata_q;
    logic [SW-1:0]       w_pstrb_q;
    logic [CW-1:0]       w_cnt_q;
    logic                w_wait, w_to, w_hs_slot, w_cnt_full, w_hold_free;
    logic                w_pa_acc, w_pw_acc, aw_dec_stale;

    assign w_stale = TO_EN ? w_stale_q : '0;

    always_comb begin
        aw_dec_stale = 1'b0;
        w_pa_acc     = 1'b0;
        w_pw_acc     = 1'b0;
        for (int unsigned s = 0; s < N_SLAVES; s++) begin
            if (aw_decode_d == 32'(s)) aw_dec_stale = aw_dec_stale | w_stale[s];
            w_pend[s] = (w_pa_q | w_pw_q) & (w_psel_q == SELW'(s));
            if (w_psel_q == SELW'(s)) begin
                w_pa_acc = w_pa_acc | s_axil_awready[s];
                w_pw_acc = w_pw_acc | s_axil_wready[s];
            end
        end
    end

    // The slot owes the engine a cycle of waiting while the request is presented and no progress was made.
    assign w_cnt_full = (w_cnt_q == TO_LAST);
    assign w_wait = TO_EN && !w_dec && !w_off &&
                    ((wstate == W_AW) || (wstate == W_DATA && m_axil_wvalid) ||
                     (wstate == W_RESP && !m_axil_bvalid));
    assign w_hs_slot = (wstate == W_AW) ? aw_hs : ((wstate == W_DATA) ? w_hs : 1'b0);
    assign w_to = w_wait && w_cnt_full && !w_hs_slot;
    assign w_hold_free = !w_pa_q && !w_pw_q;

    always_ff @(posedge clk) begin
        if (!rst_n || wstate == W_IDLE) w_cnt_q <= '0;
        else if (w_wait && !w_cnt_full)  w_cnt_q <= w_cnt_q + 1'b1;
    end

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            w_pa_q      <= 1'b0;
            w_pw_q      <= 1'b0;
            w_pw_have_q <= 1'b0;
            w_psel_q    <= '0;
            w_paddr_q   <= '0;
            w_pprot_q   <= '0;
            w_pdata_q   <= '0;
            w_pstrb_q   <= '0;
        end else begin
            if (w_pa_q && w_pa_acc) w_pa_q <= 1'b0;
            if (w_pw_q && w_pw_have_q && w_pw_acc) begin
                w_pw_q      <= 1'b0;
                w_pw_have_q <= 1'b0;
            end
            // W of a write that timed out before its W phase: take the data when the master gives it.
            if (w_pw_q && !w_pw_have_q && wstate == W_DATA && m_axil_wvalid) begin
                w_pdata_q   <= m_axil_wdata;
                w_pstrb_q   <= m_axil_wstrb;
                w_pw_have_q <= 1'b1;
            end
            if (w_to && w_hold_free) begin
                if (wstate == W_AW) begin
                    w_psel_q    <= wsel;
                    w_pa_q      <= 1'b1;
                    w_paddr_q   <= m_axil_awaddr;
                    w_pprot_q   <= m_axil_awprot;
                    w_pw_q      <= 1'b1;
                    w_pw_have_q <= 1'b0;
                end else if (wstate == W_DATA) begin
                    w_psel_q    <= wsel;
                    w_pw_q      <= 1'b1;
                    w_pw_have_q <= 1'b1;
                    w_pdata_q   <= m_axil_wdata;
                    w_pstrb_q   <= m_axil_wstrb;
                end
            end
        end
    end

    for (genvar gs = 0; gs < N_SLAVES; gs++) begin : g_w_stale
        always_ff @(posedge clk) begin
            if (!rst_n)                                              w_stale_q[gs] <= 1'b0;
            else if (w_to && wsel == SELW'(gs))                      w_stale_q[gs] <= 1'b1;
            else if (s_axil_bvalid[gs] && !w_pend[gs])               w_stale_q[gs] <= 1'b0;
        end
    end

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
                if (!w_dec && !w_off) begin
                    _s_awaddr [wsel] = m_axil_awaddr;
                    _s_awprot [wsel] = m_axil_awprot;
                    _s_awvalid[wsel] = m_axil_awvalid;
                    m_axil_awready   = s_axil_awready[wsel];
                end else begin
                    m_axil_awready = 1'b1;   // accept and drop (unmapped or off)
                end
            end
            W_DATA: begin
                if (!w_dec && !w_off) begin
                    _s_wdata  [wsel] = m_axil_wdata;
                    _s_wstrb  [wsel] = m_axil_wstrb;
                    _s_wvalid [wsel] = m_axil_wvalid;
                    m_axil_wready    = s_axil_wready[wsel];
                end else begin
                    m_axil_wready = 1'b1;    // sink the data beat
                end
            end
            W_RESP: begin
                if (!w_dec && !w_off) begin
                    m_axil_bvalid    = s_axil_bvalid[wsel];
                    m_axil_bresp     = s_axil_bresp [wsel];
                    _s_bready[wsel]  = m_axil_bready;
                end else begin
                    m_axil_bvalid = 1'b1;
                    m_axil_bresp  = w_dec ? AXI_RESP_DECERR : AXI_RESP_SLVERR;
                end
            end
            default: ;
        endcase

        // Pending request of a timed-out write, and READY towards a stale slot (absorbs the late B).
        for (int unsigned s = 0; s < N_SLAVES; s++) begin
            if (w_pa_q && w_psel_q == SELW'(s)) begin
                _s_awaddr [s] = w_paddr_q;
                _s_awprot [s] = w_pprot_q;
                _s_awvalid[s] = 1'b1;
            end
            if (w_pw_q && w_pw_have_q && w_psel_q == SELW'(s)) begin
                _s_wdata [s] = w_pdata_q;
                _s_wstrb [s] = w_pstrb_q;
                _s_wvalid[s] = 1'b1;
            end
            _s_bready[s] = _s_bready[s] | w_stale[s];
        end
    end

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            wstate <= W_IDLE;
            wsel   <= '0;
            w_dec  <= 1'b0;
            w_off_q <= 1'b0;
            w_b_lock_q <= 1'b0;
        end else begin
            if (w_to) w_off_q <= 1'b1;
            unique case (wstate)
                W_IDLE: if (m_axil_awvalid) begin
                    if (aw_decode_d < N_SLAVES) begin
                        wsel    <= aw_decode_d[SELW-1:0];
                        w_dec   <= 1'b0;
                        w_off_q <= aw_dec_off | aw_dec_stale;
                    end else begin
                        w_dec   <= 1'b1;
                        w_off_q <= 1'b0;
                    end
                    wstate <= W_AW;
                end
                W_AW:   begin
                    if (!w_dec && w_off) w_off_q <= 1'b1;
                    if (aw_hs) wstate <= W_DATA;
                end
                W_DATA: begin
                    if (!w_dec && w_off) w_off_q <= 1'b1;
                    if (w_hs)  wstate <= W_RESP;
                end
                W_RESP: begin
                    if (!w_dec && w_off) w_off_q <= 1'b1;
                    if (!w_dec && !w_off && m_axil_bvalid && !m_axil_bready) w_b_lock_q <= 1'b1;
                    if (b_hs) begin
                        wstate     <= W_IDLE;
                        w_b_lock_q <= 1'b0;
                    end
                end
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
    logic            r_off_q;  // as w_off_q, for the read engine
    logic            r_off;
    logic            r_slv_off;
    logic            ar_dec_off;

    always_comb begin
        r_slv_off  = 1'b0;
        ar_dec_off = 1'b0;
        for (int unsigned s = 0; s < N_SLAVES; s++) begin
            if (rsel == SELW'(s))               r_slv_off  = r_slv_off  | slv_off_i[s];
            if (ar_decode_d == 32'(s))          ar_dec_off = ar_dec_off | slv_off_i[s];
        end
    end
    assign r_off = r_off_q | r_slv_off;

    logic ar_hs, r_hs;
    assign ar_hs = m_axil_arvalid && m_axil_arready;
    assign r_hs  = m_axil_rvalid  && m_axil_rready;

    // The read-data mux output goes through the registers r_d*_d and r_d*_q. This adds one cycle of read latency.
    // r_dreg_ready depends only on r_dvalid_q and m_axil_rready.
    logic          r_dvalid_d, r_dvalid_q;
    logic [DW-1:0] r_ddata_d,  r_ddata_q;
    logic [1:0]    r_dresp_d,  r_dresp_q;
    logic          r_dreg_ready;

    assign r_dreg_ready = !r_dvalid_q || m_axil_rready;

    // Bounded wait, read engine. Same scheme as the write engine; the holder keeps one AR.
    logic [N_SLAVES-1:0] r_stale_q;
    logic [N_SLAVES-1:0] r_stale;
    logic [N_SLAVES-1:0] r_pend;
    logic                r_pa_q;
    logic [SELW-1:0]     r_psel_q;
    logic [AW-1:0]       r_paddr_q;
    logic [2:0]          r_pprot_q;
    logic [CW-1:0]       r_cnt_q;
    logic                r_wait, r_to, r_cnt_full, r_pa_acc, ar_dec_stale;

    assign r_stale = TO_EN ? r_stale_q : '0;

    always_comb begin
        ar_dec_stale = 1'b0;
        r_pa_acc     = 1'b0;
        for (int unsigned s = 0; s < N_SLAVES; s++) begin
            if (ar_decode_d == 32'(s)) ar_dec_stale = ar_dec_stale | r_stale[s];
            r_pend[s] = r_pa_q & (r_psel_q == SELW'(s));
            if (r_psel_q == SELW'(s)) r_pa_acc = r_pa_acc | s_axil_arready[s];
        end
    end

    // In R_DATA the wait ends when the slot's R is taken into the output register (r_dvalid_d, then r_dvalid_q).
    assign r_cnt_full = (r_cnt_q == TO_LAST);
    assign r_wait = TO_EN && !r_dec && !r_off &&
                    ((rstate == R_AR) || (rstate == R_DATA && !r_dvalid_d && !r_dvalid_q));
    assign r_to = r_wait && r_cnt_full && !(rstate == R_AR && ar_hs);

    always_ff @(posedge clk) begin
        if (!rst_n || rstate == R_IDLE) r_cnt_q <= '0;
        else if (r_wait && !r_cnt_full) r_cnt_q <= r_cnt_q + 1'b1;
    end

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            r_pa_q    <= 1'b0;
            r_psel_q  <= '0;
            r_paddr_q <= '0;
            r_pprot_q <= '0;
        end else begin
            if (r_pa_q && r_pa_acc) r_pa_q <= 1'b0;
            if (r_to && rstate == R_AR && !r_pa_q) begin
                r_pa_q    <= 1'b1;
                r_psel_q  <= rsel;
                r_paddr_q <= m_axil_araddr;
                r_pprot_q <= m_axil_arprot;
            end
        end
    end

    for (genvar gs = 0; gs < N_SLAVES; gs++) begin : g_r_stale
        always_ff @(posedge clk) begin
            if (!rst_n)                                  r_stale_q[gs] <= 1'b0;
            else if (r_to && rsel == SELW'(gs))          r_stale_q[gs] <= 1'b1;
            else if (s_axil_rvalid[gs] && !r_pend[gs])   r_stale_q[gs] <= 1'b0;
        end
    end

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            r_dvalid_q <= 1'b0;
            r_ddata_q  <= '0;
            r_dresp_q  <= AXI_RESP_OKAY;
        end else if (r_dreg_ready) begin
            r_dvalid_q <= r_dvalid_d;
            r_ddata_q  <= r_ddata_d;
            r_dresp_q  <= r_dresp_d;
        end
    end

    assign m_axil_rvalid = r_dvalid_q;
    assign m_axil_rdata  = r_ddata_q;
    assign m_axil_rresp  = r_dresp_q;

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
        r_dvalid_d     = 1'b0;
        r_ddata_d      = '0;
        r_dresp_d      = AXI_RESP_OKAY;

        unique case (rstate)
            R_AR: begin
                if (!r_dec && !r_off) begin
                    _s_araddr [rsel] = m_axil_araddr;
                    _s_arprot [rsel] = m_axil_arprot;
                    _s_arvalid[rsel] = m_axil_arvalid;
                    m_axil_arready   = s_axil_arready[rsel];
                end else begin
                    m_axil_arready = 1'b1;
                end
            end
            R_DATA: begin
                if (!r_dec && !r_off) begin
                    r_dvalid_d       = s_axil_rvalid[rsel];
                    r_ddata_d        = s_axil_rdata [rsel];
                    r_dresp_d        = s_axil_rresp [rsel];
                    _s_rready[rsel]  = r_dreg_ready;
                end else begin
                    // The local response (DECERR or off SLVERR) is one-shot. Offer the beat only while the output register is empty.
                    r_dvalid_d = !r_dvalid_q;
                    r_ddata_d  = r_dec ? '0 : OFF_RDATA;
                    r_dresp_d  = r_dec ? AXI_RESP_DECERR : AXI_RESP_SLVERR;
                end
            end
            default: ;
        endcase

        // Pending AR of a timed-out read, and READY towards a stale slot (absorbs the late R).
        for (int unsigned s = 0; s < N_SLAVES; s++) begin
            if (r_pa_q && r_psel_q == SELW'(s)) begin
                _s_araddr [s] = r_paddr_q;
                _s_arprot [s] = r_pprot_q;
                _s_arvalid[s] = 1'b1;
            end
            _s_rready[s] = _s_rready[s] | r_stale[s];
        end
    end

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            rstate <= R_IDLE;
            rsel   <= '0;
            r_dec  <= 1'b0;
            r_off_q <= 1'b0;
        end else begin
            if (r_to) r_off_q <= 1'b1;
            unique case (rstate)
                R_IDLE: if (m_axil_arvalid) begin
                    if (ar_decode_d < N_SLAVES) begin
                        rsel    <= ar_decode_d[SELW-1:0];
                        r_dec   <= 1'b0;
                        r_off_q <= ar_dec_off | ar_dec_stale;
                    end else begin
                        r_dec   <= 1'b1;
                        r_off_q <= 1'b0;
                    end
                    rstate <= R_AR;
                end
                R_AR:   begin
                    if (!r_dec && r_off) r_off_q <= 1'b1;
                    if (ar_hs) rstate <= R_DATA;
                end
                R_DATA: begin
                    if (!r_dec && r_off) r_off_q <= 1'b1;
                    if (r_hs)  rstate <= R_IDLE;
                end
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
