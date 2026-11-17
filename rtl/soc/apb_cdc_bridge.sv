// apb_cdc_bridge - APB4 clock-domain-crossing bridge with a 4-phase return-to-zero handshake.
//
// Function: The s_* face is an APB4 slave on s_clk_i. The m_* face is an APB4 master on m_clk_i.
//   One transfer is outstanding. A transfer has four phases: assert req, assert ack, deassert req, deassert ack.
//   Only the req and ack levels cross, through cdc_sync. The payload buses stay stable and are read after the level arrives.
//   s_pready_o pulses only after the full round trip. The throughput is halved.
// Parameters: ADDR_W. SYNC_STAGES_TO_S and SYNC_STAGES_TO_M set the synchroniser stages. The default is 2.
// Clocks and resets: s_rst_n_i and m_rst_n_i are active low.
//   The source FSM resets with s_rst_n_i only.
//   The destination FSM, its command capture and armed_q reset with rst_both_n, which is s_rst_n_i & m_rst_n_i.
//   The completion record (ack_q, resp_prdata_dq, resp_pslverr_dq) and the u_req_sync synchroniser reset with
//   s_rst_n_i only, through u_comp_rst_sync. A destination reset therefore cannot erase a completed transfer.
//   m_rst_sync_n (the destination reset after u_m_rst_sync) holds u_m_alive_sync in reset. The reset is asserted
//   without a clock, so a pulse of any width reaches the s_clk_i domain. u_m_alive_dly_sync then resamples it as m_rst_n_s.
// Behaviour: A transfer that completed before the destination reset ends with the real response, also for a read.
//   A destination reset before completion ends with s_pready_o=1 and s_pslverr_o=1, and no later transfer.
//   m_rst_n_s lags the reset by one cycle more than ack_s lags ack_q, so a completed response always wins the race.
//   armed_q stops the destination from starting a request that was served or abandoned before the reset. It sets
//   only when req_m is low.
//   If the destination clock stops after the completion, a destination reset ends S_DROP, so the source never waits for it.
//   A request that finds a stale ack_s, or the destination in reset, completes locally with an error and no transfer.
//   dest_off_i marks the destination domain as powered off. It counts as the destination not alive: m_rst_n_s is
//   m_rst_n_s_raw with dest_off_i cleared in. A request that starts while dest_off_i is high, or sees it rise before the ack,
//   ends with s_pslverr_o=1 and s_prdata_o=OFF_RDATA. An error from a reset alone, with dest_off_i low, still returns prdata 0.
//   There is no timeout. A destination clock that stops while the domain is on and not in reset stalls the transfer
//   until the clock returns or the destination resets.
// Caller rules:
//   - STA must set set_max_delay -datapath_only on the four payload buses, on req_q and ack_q, and on resp_prdata_dq and resp_pslverr_dq.
//     The path from m_rst_sync_n to u_m_alive_sync is a reset crossing: constrain it as in the CDC check scripts.
//   - m_rst_n_i must not glitch, because it acts on the s_clk_i domain without a clock.
//   - Connect scanmode_i and scan_rst_ni at every instance. Tie dest_off_i to 0 when the destination is always on.
//   - dest_off_i is a level in the s_clk_i domain. It must not come from another clock without a synchroniser.
//   - Use the bridge for configuration and debug paths only. It is not a data path.
//   - A reset on s_rst_n_i abandons a destination transfer with no response and no SLVERR. The upstream master re-issues it after reset.
//   - phase5_soc_multiclock_check.sdc matches req_q and ack_q by name. Do not rename them.
// Doc: ds:mod:apb-cdc-bridge, tm:mod:apb-cdc-bridge, cr:mod:apb-cdc-bridge

module apb_cdc_bridge #(
    parameter int unsigned ADDR_W           = 12,  // APB4 local address width (byte address)
    parameter int unsigned SYNC_STAGES_TO_S = 2,    // stages synchronising INTO the s_* domain (ack, s reset, m_rst_n_i status)
    parameter int unsigned SYNC_STAGES_TO_M = 2,    // stages synchronising INTO the m_* domain (req, m reset)
    parameter logic [31:0] OFF_RDATA        = 32'hDEAD_BEEF  // s_prdata_o of an error caused by dest_off_i
) (
    // DFT scan bypass. scanmode_i and scan_rst_ni go to the four internal cdc_reset_sync instances (u_s_rst_sync,
    // u_m_rst_sync, u_comp_rst_sync, u_m_alive_sync). Connect them at every instance.
    input  logic               scanmode_i,
    input  logic               scan_rst_ni,

    // 1 = destination domain powered off. Level in the s_clk_i domain.
    input  logic               dest_off_i,

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
    // The destination reset uses both resets: rst_both_n is s_rst_n_i & m_rst_n_i
    // (see ds:mod:apb-cdc-bridge). The source reset synchroniser u_s_rst_sync
    // (just below) uses s_rst_n_i alone, not rst_both_n. So the source stays
    // available when the destination is in reset.
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

    // Completion-record reset: s_rst_n_i only, so a destination reset keeps a completed response.
    logic m_comp_rst_n;

    cdc_reset_sync #(
        .STAGES (SYNC_STAGES_TO_M)
    ) u_comp_rst_sync (
        .clk_i       (m_clk_i),
        .rst_n_i     (s_rst_n_i),
        .scanmode_i  (scanmode_i),
        .scan_rst_ni (scan_rst_ni),
        .rst_n_o     (m_comp_rst_n)
    );

    // m_alive_fast_s is low from the start of any destination reset until SYNC_STAGES_TO_S s_clk_i edges after
    // m_rst_sync_n releases. It asserts without a clock. Only u_m_alive_dly_sync reads it.
    logic m_alive_fast_s;

    cdc_reset_sync #(
        .STAGES (SYNC_STAGES_TO_S)
    ) u_m_alive_sync (
        .clk_i       (s_clk_i),
        .rst_n_i     (m_rst_sync_n),
        .scanmode_i  (scanmode_i),
        .scan_rst_ni (scan_rst_ni),
        .rst_n_o     (m_alive_fast_s)
    );

    // m_rst_n_s is 1 when the destination is observed alive. It falls SYNC_STAGES_TO_S+1 s_clk_i edges after the
    // reset starts, one edge later than ack_s can follow an ack_q that was set before the reset.
    logic m_rst_n_s_raw;    // 1 = destination domain observed NOT in reset (alive)
    logic m_rst_n_s;        // m_rst_n_s_raw and not dest_off_i

    cdc_sync #(
        .WIDTH     (1),
        .STAGES    (SYNC_STAGES_TO_S + 1),
        .RESET_VAL (1'b0)
    ) u_m_alive_dly_sync (
        .clk_i   (s_clk_i),
        .rst_n_i (s_rst_sync_n),
        .d_i     (m_alive_fast_s),
        .q_o     (m_rst_n_s_raw)
    );

    assign m_rst_n_s = m_rst_n_s_raw && !dest_off_i;

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
    // Latched once at SETUP: the request was forwarded (destination observed alive and no stale ack_s),
    // or captured only to be completed locally with an error. See ds:mod:apb-cdc-bridge.
    logic              req_fwd_q;
    // Latched at SETUP: dest_off_i was high, so the local error returns OFF_RDATA.
    logic              off_err_q;

    logic              ack_s;
    logic              fwd_ok;

    assign fwd_ok = m_rst_n_s && !ack_s;

    always_comb begin
        s_state_d = s_state_q;
        unique case (s_state_q)
            S_IDLE: if (s_psel_i && !s_penable_i) s_state_d = S_REQ;
            S_REQ: begin
                // S_REQ ends on ack_s, on !req_fwd_q or on !m_rst_n_s. ack_s has priority.
                if (ack_s || !req_fwd_q || !m_rst_n_s) s_state_d = S_DROP;
            end
            // S_DROP ends when ack_s falls. It also ends when the request was never forwarded, or when
            // the destination is in reset, because ack_q cannot clear without the destination clock.
            S_DROP: if (!ack_s || !req_fwd_q || !m_rst_n_s) s_state_d = S_DONE;
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
            off_err_q    <= 1'b0;
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
                req_fwd_q    <= fwd_ok;
                off_err_q    <= dest_off_i;
            end
            // req_q asserts once per forwarded request and clears when ack_s is seen.
            // req_q is clamped to 0 while m_rst_n_s is low.
            if (!m_rst_n_s) begin
                req_q <= 1'b0;
            end else if (s_state_q == S_IDLE && s_psel_i && !s_penable_i && fwd_ok) begin
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
        .rst_n_i (m_comp_rst_n),
        .d_i     (req_q),
        .q_o     (req_m)
    );

    // The destination FSM has no ack state: ack_q holds the completion until req_m falls.
    typedef enum logic [1:0] {
        D_IDLE,    // waiting for an armed request
        D_SETUP,   // APB SETUP phase (psel=1, penable=0), one cycle
        D_ACCESS   // APB ACCESS phase (psel=1, penable=1), wait for m_pready_i
    } d_state_e;

    d_state_e d_state_q, d_state_d;

    logic              cmd_pwrite_cap_q;
    logic [ADDR_W-1:0] cmd_paddr_cap_q;
    logic [31:0]       cmd_pwdata_cap_q;
    logic [3:0]        cmd_pstrb_cap_q;
    logic              armed_q;   // 1 = req_m was seen low since the last start or reset
    logic              ack_q;     // level: 1 = response ready, held until req_m falls
    logic [31:0]       resp_prdata_dq;
    logic              resp_pslverr_dq;
    logic              d_start;

    assign d_start = (d_state_q == D_IDLE) && armed_q && req_m;

    always_comb begin
        d_state_d = d_state_q;
        unique case (d_state_q)
            D_IDLE:   if (d_start)    d_state_d = D_SETUP;
            D_SETUP:  d_state_d = D_ACCESS;
            D_ACCESS: if (m_pready_i) d_state_d = D_IDLE;
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
            armed_q          <= 1'b0;
        end else begin
            d_state_q <= d_state_d;
            // Cross-domain combinational capture of the source-domain command latch.
            // STA must set set_max_delay -datapath_only on this read. See ds:mod:apb-cdc-bridge.
            if (d_start) begin
                cmd_pwrite_cap_q <= cmd_pwrite_q;
                cmd_paddr_cap_q  <= cmd_paddr_q;
                cmd_pwdata_cap_q <= cmd_pwdata_q;
                cmd_pstrb_cap_q  <= cmd_pstrb_q;
                armed_q          <= 1'b0;
            end else if (!req_m) begin
                armed_q          <= 1'b1;
            end
        end
    end

    // The completion record clears only with the source reset. It loads from the FSM state, which the
    // destination reset clears: a reset in the cycle of the completion gives completed or not completed.
    always_ff @(posedge m_clk_i or negedge m_comp_rst_n) begin
        if (!m_comp_rst_n) begin
            ack_q           <= 1'b0;
            resp_prdata_dq  <= '0;
            resp_pslverr_dq <= 1'b0;
        end else if (d_state_q == D_ACCESS && m_pready_i) begin
            resp_prdata_dq  <= m_prdata_i;
            resp_pslverr_dq <= m_pslverr_i;
            ack_q           <= 1'b1;
        end else if (ack_q && !req_m) begin
            ack_q           <= 1'b0;
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

    // Source-domain response capture. ack_s of a forwarded request selects the real destination response.
    // A forced completion makes prdata 0 and pslverr 1. STA must set set_max_delay -datapath_only on the read of resp_*_dq.
    logic [31:0] resp_prdata_q;
    logic        resp_pslverr_q;

    always_ff @(posedge s_clk_i or negedge s_rst_sync_n) begin
        if (!s_rst_sync_n) begin
            resp_prdata_q  <= '0;
            resp_pslverr_q <= 1'b0;
        end else if (s_state_q == S_REQ) begin
            if (ack_s && req_fwd_q) begin
                resp_prdata_q  <= resp_prdata_dq;
                resp_pslverr_q <= resp_pslverr_dq;
            end else if (!req_fwd_q || !m_rst_n_s) begin
                resp_prdata_q  <= (dest_off_i || off_err_q) ? OFF_RDATA : 32'h0;
                resp_pslverr_q <= 1'b1;
            end
        end
    end

    assign s_pready_o  = (s_state_q == S_DONE);
    assign s_prdata_o  = resp_prdata_q;
    assign s_pslverr_o = resp_pslverr_q;

endmodule : apb_cdc_bridge
