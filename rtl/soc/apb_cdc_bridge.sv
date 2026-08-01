// apb_cdc_bridge.sv
// GH #93 — APB4 clock-domain-crossing bridge (2-phase toggle handshake).
//
// Problem solved: soc_top.sv's APB_PLL2 slot (GH #92) sits between
// axil_to_apb (an APB MASTER running on core_clk / the fabric domain) and
// u_cpu_pll_sub's pll_apb_regs (an APB SLAVE running on cpu_clk_i / the
// CPU-domain PLL reference — a genuinely different clock once GH #93
// re-sources the CPU from cpu_core_clk). apb_interconnect in between is
// purely combinational (no clk port, see soc_bus.sv "5. APB interconnect"),
// so without this bridge the psel/penable/pwrite/paddr/pwdata/pstrb request
// and the pready/prdata/pslverr response cross a clock boundary with zero
// synchronisation — a live, unwaived CDC hazard the moment cpu_clk_i !=
// clk_i (soc_top.sv's now-removed ⚠️ block documented this and deferred the
// fix to GH #93/#95).
//
// Protocol: 2-phase toggle handshake, depth-1 (one outstanding transfer).
//   Source (s_*) domain:
//     - Captures {pwrite, paddr, pwdata, pstrb} into a register the instant
//       the upstream APB master (axil_to_apb) enters SETUP (psel && !penable)
//       — this is the one cycle APB guarantees these fields are already
//       stable and unchanging through the whole subsequent ACCESS phase.
//     - Toggles req_toggle_q once per new request and holds s_pready_o low
//       (arbitrary APB wait states) until the destination domain's response
//       has round-tripped back.
//   Destination (m_*) domain:
//     - Synchronises ONLY req_toggle_q (single bit) via cdc_2ff_sync, never
//       the multi-bit command payload itself — see the CDC argument below.
//     - On the synchronised toggle edge, captures the (already stable)
//       command payload into its own domain and drives one APB SETUP+ACCESS
//       transfer at the m_* face (a plain APB master), waiting for
//       m_pready_i exactly like any other APB master.
//     - On m_pready_i, captures {prdata, pslverr} and toggles ack_toggle_q.
//   Source domain again:
//     - Synchronises ONLY ack_toggle_q (single bit) via cdc_2ff_sync.
//     - On the synchronised ack edge, captures the (already stable) response
//       payload and asserts s_pready_o for one cycle, completing the
//       upstream APB transfer.
//
// CDC argument (why the multi-bit payloads are safe without per-bit sync):
//   Both cmd_*_q (source domain) and resp_*_dq (destination domain) are
//   registered ONCE per transfer and then held perfectly stable for the
//   ENTIRE remainder of that transfer's round trip (many clock periods of
//   the *other* domain — at minimum SYNC_STAGES_TO_{S,M}+1 cycles, in
//   practice a full APB SETUP+ACCESS sequence). The capturing domain only
//   samples that stable payload after its own synchronised copy of the
//   corresponding toggle bit has changed, i.e. strictly after the source
//   value was already stable. This is the same "stable data qualified by a
//   synchronised single-bit control signal" pattern as cdc_gray_fifo's
//   mem_q combinational read (see async_axi_fifo.sv header) — it is NOT the
//   same as running an arbitrary multi-bit binary bus through cdc_2ff_sync
//   (which cdc_2ff_sync's own header explicitly forbids).
//
// !!! Cross-domain combinational reads — READ BEFORE STA !!!
// cmd_paddr_q/cmd_pwrite_q/cmd_pwdata_q/cmd_pstrb_q (source domain) are read
// combinationally by the destination-domain capture register, and
// resp_prdata_dq/resp_pslverr_dq (destination domain) are read
// combinationally by the source-domain capture register. Both reads are
// safe per the CDC argument above but are still physical cross-domain
// datapaths. Mirroring the GH #94 action item already open on
// async_axi_fifo.sv, STA must add `set_max_delay -datapath_only` on these
// four payload buses AND on the two toggle-bit crossings (req_toggle_q,
// ack_toggle_q) through their respective cdc_2ff_sync instances.
//
// ── Reset strategy: hard flush, common root, both domains always together ──
// Identical rationale to async_axi_fifo.sv: rst_both_n = s_rst_n_i &
// m_rst_n_i feeds BOTH cdc_reset_sync instances, so a reset on either side
// clears both toggle/state machines together — there is no scenario where
// one domain resumes mid-transfer while the other has forgotten it was ever
// asked to. This is a hard flush: a transfer in flight when either reset
// asserts is simply dropped (the upstream APB master will re-issue after
// reset deasserts); no SLVERR is fabricated.
//
// Caller contract: s_rst_n_i and m_rst_n_i must each be held low for
// >= the respective SYNC_STAGES+1 periods of the OTHER clock, exactly as
// documented in cdc_reset_sync.sv and async_axi_fifo.sv.
//
// Instantiated in soc_top.sv between apb_psel/penable/...[APB_PLL2] (source,
// core_clk domain) and u_cpu_pll_sub's APB4 slave port (destination,
// cpu_clk_i domain — the CPU-domain PLL's own raw reference clock, NOT
// cpu_core_clk; pll_subsystem.sv:11-17's bootstrap rule requires its APB
// regs run on the raw reference, so this bridge's m_* face must too).
//
// Coding rules: registered FSMs only; async-assert/sync-deassert reset
// (docs/development/CODING_GUIDELINES.md §1.4), matching cdc_2ff_sync /
// cdc_reset_sync discipline.
// Lint target: verilator -Wall -Wno-IMPORTSTAR 0 errors 0 warnings.

`default_nettype none

module apb_cdc_bridge #(
    parameter int unsigned ADDR_W           = 12,  // APB4 local address width (byte address)
    parameter int unsigned SYNC_STAGES_TO_S = 2,    // stages synchronising INTO the s_* domain (ack_toggle, s reset)
    parameter int unsigned SYNC_STAGES_TO_M = 2     // stages synchronising INTO the m_* domain (req_toggle, m reset)
) (
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

    // ── Reset: common root feeding both per-domain synchronisers ────────────
    // (identical rationale to async_axi_fifo.sv — see module header)
    logic rst_both_n;
    assign rst_both_n = s_rst_n_i & m_rst_n_i;

    logic s_rst_sync_n;
    logic m_rst_sync_n;

    cdc_reset_sync #(
        .STAGES (SYNC_STAGES_TO_S)
    ) u_s_rst_sync (
        .clk_i   (s_clk_i),
        .rst_n_i (rst_both_n),
        .rst_n_o (s_rst_sync_n)
    );

    cdc_reset_sync #(
        .STAGES (SYNC_STAGES_TO_M)
    ) u_m_rst_sync (
        .clk_i   (m_clk_i),
        .rst_n_i (rst_both_n),
        .rst_n_o (m_rst_sync_n)
    );

    // =========================================================================
    // Source domain (s_clk_i): command capture + request toggle + FSM
    // =========================================================================
    typedef enum logic [1:0] {
        S_IDLE,   // waiting for upstream APB SETUP (psel && !penable)
        S_WAIT,   // request launched; waiting for the synchronised ack edge
        S_DONE    // one-cycle pready pulse; completes the upstream transfer
    } s_state_e;

    s_state_e s_state_q, s_state_d;

    logic              cmd_pwrite_q;
    logic [ADDR_W-1:0] cmd_paddr_q;
    logic [31:0]       cmd_pwdata_q;
    logic [3:0]        cmd_pstrb_q;
    logic              req_toggle_q;

    logic              ack_new;   // defined below; forward-referenced here (SV allows it)

    always_comb begin
        s_state_d = s_state_q;
        unique case (s_state_q)
            S_IDLE:  if (s_psel_i && !s_penable_i) s_state_d = S_WAIT;
            S_WAIT:  if (ack_new)                  s_state_d = S_DONE;
            S_DONE:  s_state_d = S_IDLE;
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
            req_toggle_q <= 1'b0;
        end else begin
            s_state_q <= s_state_d;
            // Capture happens exactly once per transfer, on the SETUP cycle
            // (psel && !penable) — APB guarantees these fields are already
            // stable here and remain so through the whole ACCESS phase.
            if (s_state_q == S_IDLE && s_psel_i && !s_penable_i) begin
                cmd_pwrite_q <= s_pwrite_i;
                cmd_paddr_q  <= s_paddr_i;
                cmd_pwdata_q <= s_pwdata_i;
                cmd_pstrb_q  <= s_pstrb_i;
                req_toggle_q <= ~req_toggle_q;
            end
        end
    end

    // =========================================================================
    // req_toggle_q: s_clk_i -> m_clk_i (single bit — safe for cdc_2ff_sync)
    // =========================================================================
    logic req_toggle_m;

    cdc_2ff_sync #(
        .WIDTH  (1),
        .STAGES (SYNC_STAGES_TO_M)
    ) u_req_sync (
        .clk_i   (m_clk_i),
        .rst_n_i (m_rst_sync_n),
        .d_i     (req_toggle_q),
        .q_o     (req_toggle_m)
    );

    logic req_seen_q;
    logic req_new;

    assign req_new = (req_toggle_m != req_seen_q);

    always_ff @(posedge m_clk_i or negedge m_rst_sync_n) begin
        if (!m_rst_sync_n) req_seen_q <= 1'b0;
        else               req_seen_q <= req_toggle_m;
    end

    // =========================================================================
    // Destination domain (m_clk_i): command capture + APB master FSM +
    // response capture + ack toggle
    // =========================================================================
    typedef enum logic [1:0] {
        D_IDLE,    // waiting for the synchronised request edge
        D_SETUP,   // APB SETUP phase (psel=1, penable=0), one cycle
        D_ACCESS   // APB ACCESS phase (psel=1, penable=1), wait for m_pready_i
    } d_state_e;

    d_state_e d_state_q, d_state_d;

    logic              cmd_pwrite_cap_q;
    logic [ADDR_W-1:0] cmd_paddr_cap_q;
    logic [31:0]       cmd_pwdata_cap_q;
    logic [3:0]        cmd_pstrb_cap_q;
    logic              ack_toggle_q;
    logic [31:0]       resp_prdata_dq;
    logic              resp_pslverr_dq;

    always_comb begin
        d_state_d = d_state_q;
        unique case (d_state_q)
            D_IDLE:   if (req_new)      d_state_d = D_SETUP;
            D_SETUP:  d_state_d = D_ACCESS;
            D_ACCESS: if (m_pready_i)   d_state_d = D_IDLE;
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
            ack_toggle_q     <= 1'b0;
            resp_prdata_dq   <= '0;
            resp_pslverr_dq  <= 1'b0;
        end else begin
            d_state_q <= d_state_d;
            // Cross-domain combinational capture of the source-domain
            // command latch — see "CDC argument" in the module header.
            // GH #94 STA action: set_max_delay -datapath_only on this read.
            if (d_state_q == D_IDLE && req_new) begin
                cmd_pwrite_cap_q <= cmd_pwrite_q;
                cmd_paddr_cap_q  <= cmd_paddr_q;
                cmd_pwdata_cap_q <= cmd_pwdata_q;
                cmd_pstrb_cap_q  <= cmd_pstrb_q;
            end
            if (d_state_q == D_ACCESS && m_pready_i) begin
                resp_prdata_dq  <= m_prdata_i;
                resp_pslverr_dq <= m_pslverr_i;
                ack_toggle_q    <= ~ack_toggle_q;
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
    // ack_toggle_q: m_clk_i -> s_clk_i (single bit — safe for cdc_2ff_sync)
    // =========================================================================
    logic ack_toggle_s;

    cdc_2ff_sync #(
        .WIDTH  (1),
        .STAGES (SYNC_STAGES_TO_S)
    ) u_ack_sync (
        .clk_i   (s_clk_i),
        .rst_n_i (s_rst_sync_n),
        .d_i     (ack_toggle_q),
        .q_o     (ack_toggle_s)
    );

    logic ack_seen_q;

    assign ack_new = (ack_toggle_s != ack_seen_q);

    always_ff @(posedge s_clk_i or negedge s_rst_sync_n) begin
        if (!s_rst_sync_n) ack_seen_q <= 1'b0;
        else               ack_seen_q <= ack_toggle_s;
    end

    // =========================================================================
    // Source-domain response capture (cross-domain combinational read of
    // resp_*_dq — see "CDC argument" in the module header; GH #94 STA
    // action: set_max_delay -datapath_only on this read too) + APB outputs
    // =========================================================================
    logic [31:0] resp_prdata_q;
    logic        resp_pslverr_q;

    always_ff @(posedge s_clk_i or negedge s_rst_sync_n) begin
        if (!s_rst_sync_n) begin
            resp_prdata_q  <= '0;
            resp_pslverr_q <= 1'b0;
        end else if (s_state_q == S_WAIT && ack_new) begin
            resp_prdata_q  <= resp_prdata_dq;
            resp_pslverr_q <= resp_pslverr_dq;
        end
    end

    assign s_pready_o  = (s_state_q == S_DONE);
    assign s_prdata_o  = resp_prdata_q;
    assign s_pslverr_o = resp_pslverr_q;

endmodule : apb_cdc_bridge

`default_nettype wire
