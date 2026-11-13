// apb_cdc_bridge - APB4 clock-domain-crossing bridge with a 4-phase return-to-zero handshake.
//
// Function: The s_* face is an APB4 slave on s_clk_i. The m_* face is an APB4 master on m_clk_i.
//   One transfer is outstanding. A transfer has four phases: assert req, assert ack, deassert req, deassert ack.
//   Only the req and ack levels cross, through cdc_sync. The payload buses stay stable and are read after the level arrives.
//   s_pready_o pulses only after the full round trip. The throughput is halved.
// Parameters: ADDR_W. SYNC_STAGES_TO_S and SYNC_STAGES_TO_M set the synchroniser stages. The default is 2.
// Clocks and resets: s_rst_n_i and m_rst_n_i are active low. The source FSM resets with s_rst_n_i only.
//   The destination FSM resets with rst_both_n, which is s_rst_n_i & m_rst_n_i.
//   m_rst_n_i also crosses into s_clk_i through cdc_sync as m_rst_n_s.
// Behaviour: If the destination is in reset, the source completes the request with s_pready_o=1 and s_pslverr_o=1.
//   The source never waits for a destination that cannot answer. No write is made on the destination for an errored request.
// Caller rules:
//   - Hold s_rst_n_i and m_rst_n_i low for at least SYNC_STAGES+1 periods of the other clock.
//   - Hold m_rst_n_i low for at least SYNC_STAGES_TO_M+1 periods of m_clk_i and SYNC_STAGES_TO_S+1 periods of s_clk_i.
//     A shorter pulse can hide the reset from the s domain. This is a caller error.
//   - STA must set set_max_delay -datapath_only on the four payload buses, on req_q and ack_q, and on m_rst_n_i to m_rst_n_s.
//   - Connect scanmode_i and scan_rst_ni at every instance.
//   - Use the bridge for configuration and debug paths only. It is not a data path.
//   - m_rst_n_s can read 1 for up to SYNC_STAGES_TO_S s_clk_i cycles after s_rst_sync_n releases, even while m_rst_n_i is low.
//     This is a reviewed local exception.
//   - A reset on s_rst_n_i abandons a destination transfer with no response and no SLVERR. The upstream master re-issues it after reset.
//   - phase5_soc_multiclock_check.sdc matches req_q and ack_q by name. Do not rename them.
// Doc: ds:mod:apb-cdc-bridge, tm:mod:apb-cdc-bridge, cr:mod:apb-cdc-bridge

module apb_cdc_bridge #(
    parameter int unsigned ADDR_W           = 12,  // APB4 local address width (byte address)
    parameter int unsigned SYNC_STAGES_TO_S = 2,    // stages synchronising INTO the s_* domain (ack, s reset, m_rst_n_i status)
    parameter int unsigned SYNC_STAGES_TO_M = 2     // stages synchronising INTO the m_* domain (req, m reset)
) (
    // DFT scan bypass. scanmode_i and scan_rst_ni go to both internal cdc_reset_sync instances. Connect them at every instance.
    input  logic               scanmode_i,
    input  logic               scan_rst_ni,

    // ══ s_* face — source domain, APB4 SLAVE port (fabric/core_clk side) ═══
    input  logic              s_clk_i,
    input  logic              s_rst_n_i,
    input  logic              s_psel_i,
    input  logic              s_penable_i,
    input  logic              s_pwrite_i,
    input  logic [ADDR_W-1:0] s_paddr_i,
    input  logic [31:0]       s_pwdata_i,
    input  logic [3:0]        s_pstrb_i,
    output logic [31:0]       s_prdata_o,
    output logic              s_pready_o,
    output logic              s_pslverr_o,

    // ══ m_* face — destination domain, APB4 MASTER port (CPU-domain PLL2
    //    reference clock side, e.g. cpu_clk_i) ═══════════════════════════
    input  logic              m_clk_i,
    input  logic              m_rst_n_i,
    output logic              m_psel_o,
    output logic              m_penable_o,
    output logic              m_pwrite_o,
    output logic [ADDR_W-1:0] m_paddr_o,
    output logic [31:0]       m_pwdata_o,
    output logic [3:0]        m_pstrb_o,
    input  logic [31:0]       m_prdata_i,
    input  logic              m_pready_i,
    input  logic              m_pslverr_i
);

    // ── Reset: ASYMMETRIC. See ds:mod:apb-cdc-bridge. ───────
    // rst_both_n still exists and still couples the DESTINATION domain to
    // BOTH resets (a conservative, reviewed choice; see ds:mod:apb-cdc-bridge, no longer
    // strictly required for RZ correctness but retained for this bead's
    // minimal-diff scope). The SOURCE domain's own reset sync (u_s_rst_sync,
    // just below) is deliberately rooted in s_rst_n_i alone, NOT rst_both_n
    // — that decoupling is the actual availability fix.
    logic rst_both_n;
    assign rst_both_n = s_rst_n_i & m_rst_n_i;

    logic s_rst_sync_n;
    logic m_rst_sync_n;

    cdc_reset_sync #(
        .STAGES (SYNC_STAGES_TO_S)
    ) u_s_rst_sync (
        .clk_i       (s_clk_i),
        .rst_n_i     (s_rst_n_i),
        .scanmode_i  (scanmode_i),
        .scan_rst_ni (scan_rst_ni),
        .rst_n_o     (s_rst_sync_n)
    );

    cdc_reset_sync #(
        .STAGES (SYNC_STAGES_TO_M)
    ) u_m_rst_sync (
        .clk_i       (m_clk_i),
        .rst_n_i     (rst_both_n),
        .scanmode_i  (scanmode_i),
        .scan_rst_ni (scan_rst_ni),
        .rst_n_o     (m_rst_sync_n)
    );

    // m_in_rst_s is the cdc_sync of ~m_rst_n_i. It is 1 when the destination is in reset.
    // The polarity makes the reset value of cdc_sync mean not in reset.
    // m_rst_n_s reads 1 for up to SYNC_STAGES_TO_S s_clk_i cycles after s_rst_sync_n releases, even if m_rst_n_i is low.
    // This is a reviewed local exception. m_rst_sync_n holds the destination in reset in that time.
    logic m_in_rst_s;   // 1 = destination domain observed in reset
    logic m_rst_n_s;    // 1 = destination domain observed NOT in reset (alive)

    cdc_sync #(
        .WIDTH  (1),
        .STAGES (SYNC_STAGES_TO_S)
    ) u_m_rst_status_sync (
        .clk_i   (s_clk_i),
        .rst_n_i (s_rst_sync_n),
        .d_i     (~m_rst_n_i),
        .q_o     (m_in_rst_s)
    );

    // m_rst_n_s is the inverse of m_in_rst_s.
    // See ds:mod:apb-cdc-bridge.
    assign m_rst_n_s = !m_in_rst_s;

    // =========================================================================
    // Source domain (s_clk_i): command capture + req level + FSM
    //
    // States are S_IDLE, S_REQ, S_DROP and S_DONE. S_DROP waits until ack_s falls.
    // s_pready_o pulses only in S_DONE, after the return-to-zero half.
    // =========================================================================
    typedef enum logic [1:0] {
        S_IDLE,   // waiting for upstream APB SETUP (psel && !penable)
        S_REQ,    // request launched (or being locally errored); waiting on ack_s / abort
        S_DROP,   // req_q deasserted; waiting for ack_s to fall (return-to-zero)
        S_DONE    // one-cycle pready pulse; completes the upstream transfer
    } s_state_e;

    s_state_e s_state_q, s_state_d;

    logic              cmd_pwrite_q;
    logic [ADDR_W-1:0] cmd_paddr_q;
    logic [31:0]       cmd_pwdata_q;
    logic [3:0]        cmd_pstrb_q;
    logic              req_q;    // level: 1 = request asserted to the destination
    // Latched once at SETUP: was this request actually forwarded to the
    // destination (destination observed live), or was it captured only to
    // be locally error-completed (destination already observed in reset)?
    // Gates both the S_REQ exit condition and the response below — see
    // See ds:mod:apb-cdc-bridge.
    logic              req_fwd_q;

    logic              ack_s;   // defined below; forward-referenced here (SV allows it)

    always_comb begin
        s_state_d = s_state_q;
        unique case (s_state_q)
            S_IDLE: if (s_psel_i && !s_penable_i) s_state_d = S_REQ;
            S_REQ: begin
                // S_REQ ends on ack_s, on !req_fwd_q or on !m_rst_n_s. ack_s has priority.
                if (ack_s || !req_fwd_q || !m_rst_n_s) s_state_d = S_DROP;
            end
            S_DROP: if (!ack_s) s_state_d = S_DONE;
            S_DONE: s_state_d = S_IDLE;
            default: s_state_d = S_IDLE;
        endcase
    end

    always_ff @(posedge s_clk_i or negedge s_rst_sync_n) begin
        if (!s_rst_sync_n) begin
            s_state_q    <= S_IDLE;
            cmd_pwrite_q <= 1'b0;
            cmd_paddr_q  <= '0;
            cmd_pwdata_q <= '0;
            cmd_pstrb_q  <= '0;
            req_q        <= 1'b0;
            req_fwd_q    <= 1'b0;
        end else begin
            s_state_q <= s_state_d;
            // Capture happens exactly once per transfer, on the SETUP cycle
            // (psel && !penable) — APB guarantees these fields are already
            // stable here and remain so through the whole ACCESS phase.
            // cmd_* are always captured (harmless even if never forwarded);
            // req_fwd_q latches whether the destination was observed live
            // at that instant.
            if (s_state_q == S_IDLE && s_psel_i && !s_penable_i) begin
                cmd_pwrite_q <= s_pwrite_i;
                cmd_paddr_q  <= s_paddr_i;
                cmd_pwdata_q <= s_pwdata_i;
                cmd_pstrb_q  <= s_pstrb_i;
                req_fwd_q    <= m_rst_n_s;
            end
            // req_q asserts once per forwarded request and clears when ack_s is seen.
            // req_q is clamped to 0 while m_rst_n_s is low.
            if (!m_rst_n_s) begin
                req_q <= 1'b0;
            end else if (s_state_q == S_IDLE && s_psel_i && !s_penable_i) begin
                req_q <= 1'b1;
            end else if (s_state_q == S_REQ && ack_s) begin
                req_q <= 1'b0;
            end
        end
    end

    // =========================================================================
    // req_q: s_clk_i -> m_clk_i (single bit — safe for cdc_sync)
    // =========================================================================
    logic req_m;

    cdc_sync #(
        .WIDTH  (1),
        .STAGES (SYNC_STAGES_TO_M)
    ) u_req_sync (
        .clk_i   (m_clk_i),
        .rst_n_i (m_rst_sync_n),
        .d_i     (req_q),
        .q_o     (req_m)
    );

    // D_ACK holds ack_q until req_m falls. Then it clears ack_q and returns to D_IDLE.
    typedef enum logic [1:0] {
        D_IDLE,    // waiting for req_m to read 1
        D_SETUP,   // APB SETUP phase (psel=1, penable=0), one cycle
        D_ACCESS,  // APB ACCESS phase (psel=1, penable=1), wait for m_pready_i
        D_ACK      // ack_q asserted; waiting for req_m to fall before re-arming
    } d_state_e;

    d_state_e d_state_q, d_state_d;

    logic              cmd_pwrite_cap_q;
    logic [ADDR_W-1:0] cmd_paddr_cap_q;
    logic [31:0]       cmd_pwdata_cap_q;
    logic [3:0]        cmd_pstrb_cap_q;
    logic              ack_q;   // level: 1 = response ready, held until req_m falls
    logic [31:0]       resp_prdata_dq;
    logic              resp_pslverr_dq;

    always_comb begin
        d_state_d = d_state_q;
        unique case (d_state_q)
            D_IDLE:   if (req_m)      d_state_d = D_SETUP;
            D_SETUP:  d_state_d = D_ACCESS;
            D_ACCESS: if (m_pready_i) d_state_d = D_ACK;
            D_ACK:    if (!req_m)     d_state_d = D_IDLE;
            default:  d_state_d = D_IDLE;
        endcase
    end

    always_ff @(posedge m_clk_i or negedge m_rst_sync_n) begin
        if (!m_rst_sync_n) begin
            d_state_q        <= D_IDLE;
            cmd_pwrite_cap_q <= 1'b0;
            cmd_paddr_cap_q  <= '0;
            cmd_pwdata_cap_q <= '0;
            cmd_pstrb_cap_q  <= '0;
            ack_q            <= 1'b0;
            resp_prdata_dq   <= '0;
            resp_pslverr_dq  <= 1'b0;
        end else begin
            d_state_q <= d_state_d;
            // Cross-domain combinational capture of the source-domain command latch.
            // STA must set set_max_delay -datapath_only on this read. See ds:mod:apb-cdc-bridge.
            if (d_state_q == D_IDLE && req_m) begin
                cmd_pwrite_cap_q <= cmd_pwrite_q;
                cmd_paddr_cap_q  <= cmd_paddr_q;
                cmd_pwdata_cap_q <= cmd_pwdata_q;
                cmd_pstrb_cap_q  <= cmd_pstrb_q;
            end
            if (d_state_q == D_ACCESS && m_pready_i) begin
                resp_prdata_dq  <= m_prdata_i;
                resp_pslverr_dq <= m_pslverr_i;
                ack_q           <= 1'b1;
            end
            if (d_state_q == D_ACK && !req_m) begin
                ack_q <= 1'b0;
            end
        end
    end

    assign m_psel_o    = (d_state_q == D_SETUP) || (d_state_q == D_ACCESS);
    assign m_penable_o = (d_state_q == D_ACCESS);
    assign m_pwrite_o  = cmd_pwrite_cap_q;
    assign m_paddr_o   = cmd_paddr_cap_q;
    assign m_pwdata_o  = cmd_pwdata_cap_q;
    assign m_pstrb_o   = cmd_pstrb_cap_q;

    // =========================================================================
    // ack_q: m_clk_i -> s_clk_i (single bit — safe for cdc_sync)
    // =========================================================================
    cdc_sync #(
        .WIDTH  (1),
        .STAGES (SYNC_STAGES_TO_S)
    ) u_ack_sync (
        .clk_i   (s_clk_i),
        .rst_n_i (s_rst_sync_n),
        .d_i     (ack_q),
        .q_o     (ack_s)
    );

    // Source-domain response capture. ack_s selects the real destination response.
    // A forced completion makes prdata 0 and pslverr 1. STA must set set_max_delay -datapath_only on the read of resp_*_dq.
    logic [31:0] resp_prdata_q;
    logic        resp_pslverr_q;

    always_ff @(posedge s_clk_i or negedge s_rst_sync_n) begin
        if (!s_rst_sync_n) begin
            resp_prdata_q  <= '0;
            resp_pslverr_q <= 1'b0;
        end else if (s_state_q == S_REQ) begin
            if (ack_s) begin
                resp_prdata_q  <= resp_prdata_dq;
                resp_pslverr_q <= resp_pslverr_dq;
            end else if (!req_fwd_q || !m_rst_n_s) begin
                resp_prdata_q  <= '0;
                resp_pslverr_q <= 1'b1;
            end
        end
    end

    assign s_pready_o  = (s_state_q == S_DONE);
    assign s_prdata_o  = resp_prdata_q;
    assign s_pslverr_o = resp_pslverr_q;

endmodule : apb_cdc_bridge
