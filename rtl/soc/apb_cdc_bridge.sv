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
//     - Forwards the request (toggles req_toggle_q) ONLY if the destination
//       domain is currently observed out of reset (see "Availability fix"
//       below); otherwise the request is completed locally with an error
//       and never forwarded at all.
//     - Holds s_pready_o low (arbitrary APB wait states) until either the
//       destination domain's response has round-tripped back, OR the
//       destination domain is observed to enter reset while the request is
//       in flight — whichever happens first. Either way s_pready_o is
//       guaranteed to assert within a bounded number of s_clk_i cycles; the
//       source domain can never be held waiting on a destination that will
//       never answer.
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
// ack_toggle_q) through their respective cdc_2ff_sync instances, AND on the
// new m_rst_n_i -> m_rst_n_s single-bit status crossing described below.
//
// ── Reset strategy (post-#93 availability fix, see PR #132 review) ─────────
// The ORIGINAL strategy here was a straight copy of async_axi_fifo.sv's
// hard-flush, common-root argument: rst_both_n = s_rst_n_i & m_rst_n_i fed
// BOTH cdc_reset_sync instances, so a reset on either side cleared both
// toggle/state machines together. That argument is FALSE for this module's
// source-domain FSM and was the root cause of a confirmed availability bug:
// while m_rst_n_i alone is asserted (the CPU-domain PLL2 reference resets
// independently of the fabric, exactly the scenario #92/#93 exist to
// support), rst_both_n held s_rst_sync_n low too, which held s_state_q in
// S_IDLE — s_pready_o could never assert, EVER, for as long as m_rst_n_i
// stayed low, wedging the upstream axil_to_apb master (and therefore the
// entire fabric APB tree: UART/SPI/timer/IRQ/PMU/both PLL blocks) until a
// full SoC reset. Because the source FSM was itself held in reset, it could
// not even emit an error response — a new state transition alone cannot fix
// this; the reset structure itself has to change.
//
// The fix is now ASYMMETRIC, and each half is justified independently:
//
//   * s_rst_sync_n is rooted in s_rst_n_i ONLY (no longer rst_both_n). The
//     source-domain FSM (s_state_q, cmd_*_q, req_toggle_q, req_fwd_q,
//     ack_seen_q, resp_*_q) resets/advances purely on its own domain's
//     reset, so it is never starved by an event on the OTHER domain. This
//     is what actually closes the availability bug.
//
//   * m_rst_sync_n is DELIBERATELY LEFT on rst_both_n = s_rst_n_i &
//     m_rst_n_i — this coupling is still genuinely required, not an
//     unexamined leftover. Reason: req_seen_q (destination domain) must
//     never observe req_toggle_q (source domain) having advanced past a
//     request the destination never actually completed, or a stale toggle
//     value left over from BEFORE a reset can be misread as a brand-new
//     request once the destination comes back up, and the destination would
//     silently replay (or, symmetrically, silently drop) a transfer the
//     upstream master already believes is resolved. Keeping m_rst_sync_n
//     coupled to s_rst_n_i means an s-side reset still forces req_seen_q
//     (and ack_toggle_q, d_state_q, cmd_*_cap_q) back to their power-on
//     values in lock-step with req_toggle_q resetting to 0 in the source
//     domain, preserving the toggle protocol's invariant. (An earlier fully
//     -decoupled design was analysed and REJECTED for exactly this reason:
//     it reproduces a silent-drop hang on the very first post-reset request
//     whenever an odd number of successful transfers had completed before
//     the s-side reset — see PR #132 discussion.)
//
//   Because s_rst_sync_n no longer follows m_rst_n_i, req_toggle_q on its
//   own can no longer be guaranteed to land back at 0 in step with
//   req_seen_q for an m_rst_n_i-only event. This is closed by a THIRD
//   mechanism: m_rst_n_i is synchronised into the s domain (m_rst_n_s, via
//   cdc_2ff_sync, single-bit — safe under that module's own scope rules)
//   and used to (a) gate whether a new request is forwarded at all
//   (req_fwd_q captured at SETUP), (b) bound S_WAIT so it always resolves —
//   on ack_new (normal), or immediately if the request was never forwarded,
//   or by force-completing with s_pslverr_o=1 if the destination is observed
//   to go into reset while the request is in flight — and (c) continuously
//   clamp req_toggle_q to 0 for as long as m_rst_n_s reads 0. That clamp is
//   what re-establishes the req_toggle_q == req_seen_q(==0) invariant for an
//   m_rst_n_i-only event, without needing s_rst_sync_n to depend on
//   m_rst_n_i at all. No write is ever fabricated on the destination side
//   from an errored request: either the request was never forwarded
//   (req_fwd_q=0, req_toggle_q never moved), or it WAS forwarded and the
//   clamp guarantees req_toggle_q returns to 0 well before m_rst_sync_n
//   (which the same m_rst_n_i event also asserts, asynchronously and
//   immediately) ever releases and lets req_seen_q resume tracking it.
//
// Net effect per reset source:
//   - m_rst_n_i asserts alone: destination domain resets (correct — it is
//     that domain's own reset). Source domain is NOT held; any in-flight or
//     new request completes within a bounded number of s_clk_i cycles via
//     s_pready_o=1, s_pslverr_o=1 instead of hanging. This is the fixed bug.
//   - s_rst_n_i asserts alone: UNCHANGED from the original hard-flush
//     behaviour — rst_both_n still drops, so the destination domain (and,
//     independently, the source domain via its own s_rst_n_i) both flush
//     together. A destination-side in-flight APB transfer to the real
//     downstream slave is simply abandoned; the source never even observes
//     it (it has already gone back to S_IDLE with no response, exactly as
//     before). No SLVERR is fabricated for this direction; the upstream APB
//     master re-issues after reset deasserts.
//
// Caller contract: s_rst_n_i and m_rst_n_i must each be held low for
// >= the respective SYNC_STAGES+1 periods of the OTHER clock, exactly as
// documented in cdc_reset_sync.sv and async_axi_fifo.sv. Note the source
// domain's error-completion path is bounded by SYNC_STAGES_TO_S cycles of
// s_clk_i after m_rst_n_i is asserted, not by any property of m_clk_i.
//
// m_rst_n_i specifically crosses TWO independent synchronisers and the
// contract above must be met against BOTH, i.e. m_rst_n_i must be held low
// for >= max(SYNC_STAGES_TO_M+1 periods of m_clk_i, SYNC_STAGES_TO_S+1
// periods of s_clk_i):
//   (1) rst_both_n -> u_m_rst_sync (cdc_reset_sync, STAGES_TO_M, m_clk_i) —
//       the destination domain's own reset settling, standard contract.
//   (2) ~m_rst_n_i -> u_m_rst_status_sync (cdc_2ff_sync, STAGES_TO_S,
//       s_clk_i) — the availability-status crossing added by the #93
//       availability fix (see "Availability-gating exception" below). This
//       is the NEW crossing this fix introduced; violating its minimum low
//       width (e.g. a glitch/pulse on m_rst_n_i shorter than
//       SYNC_STAGES_TO_S+1 s_clk_i periods) does not just risk the standard
//       metastability outcome — it can make the s domain's synchroniser
//       entirely miss the reset event, so m_rst_n_s never dips and the
//       self-healing bound in the exception below does not apply. That
//       degenerate case is a caller-contract violation (same class as
//       violating (1)), not a defect in this module.
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
    parameter int unsigned SYNC_STAGES_TO_S = 2,    // stages synchronising INTO the s_* domain (ack_toggle, s reset, m_rst_n_i status)
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

    // ── Reset: ASYMMETRIC — see "Reset strategy" in the module header ───────
    // rst_both_n still exists and still couples the DESTINATION domain to
    // BOTH resets (required to keep req_seen_q's toggle bookkeeping
    // consistent across an s_rst_n_i event — see header). The SOURCE
    // domain's own reset sync (u_s_rst_sync, just below) is deliberately
    // rooted in s_rst_n_i alone, NOT rst_both_n — that decoupling is the
    // actual availability fix.
    logic rst_both_n;
    assign rst_both_n = s_rst_n_i & m_rst_n_i;

    logic s_rst_sync_n;
    logic m_rst_sync_n;

    cdc_reset_sync #(
        .STAGES (SYNC_STAGES_TO_S)
    ) u_s_rst_sync (
        .clk_i   (s_clk_i),
        .rst_n_i (s_rst_n_i),
        .rst_n_o (s_rst_sync_n)
    );

    cdc_reset_sync #(
        .STAGES (SYNC_STAGES_TO_M)
    ) u_m_rst_sync (
        .clk_i   (m_clk_i),
        .rst_n_i (rst_both_n),
        .rst_n_o (m_rst_sync_n)
    );

    // ── Destination-reset status, synchronised INTO the source domain ──────
    // Single-bit level crossing of the raw m_rst_n_i input (not m_rst_sync_n
    // — we want the source domain's own view of "is the destination
    // currently reset", independent of the destination's internal sync
    // latency) via the same cdc_2ff_sync primitive already used for the
    // toggle bits.
    //
    // Polarity is DELIBERATE: we synchronise the ACTIVE-HIGH "destination in
    // reset" sense (~m_rst_n_i), not m_rst_n_i directly, so that
    // cdc_2ff_sync's own fixed reset-to-0 behaviour means "presumed NOT in
    // reset" (i.e. presumed alive) the instant s_rst_sync_n releases. This
    // is not just a style choice: an earlier version of this synchroniser
    // sampled m_rst_n_i directly (reset-to-0 = "presumed IN reset"), which
    // is conservative for the availability fix in isolation but silently
    // STACKS a second synchroniser's settling latency onto the very first
    // transaction after every s_rst_n_i release — even when m_rst_n_i was
    // never actually asserted — because the reset-default (0) disagreed
    // with the immediate steady-state truth (1/alive), and it takes
    // SYNC_STAGES_TO_S more s_clk_i cycles for the real value to arrive. In
    // the s_ns=18/m_ns=4 clock-ratio regression this cost exactly one
    // spurious pslverr=1 on the first post-reset write. With the inverted
    // polarity, the reset default (0 = "not in reset") already MATCHES
    // steady-state truth whenever m_rst_n_i is genuinely high, so the good
    // path incurs no extra latency. The bad path (m_rst_n_i genuinely low)
    // is unaffected: the destination's own req_toggle_m/req_seen_q stay
    // async-held at 0 by m_rst_sync_n for as long as m_rst_n_i is actually
    // low (rst_both_n includes it), so a request forwarded during the few
    // cycles before this synchroniser catches up is invisible to the
    // destination and is cleaned up (req_toggle_q clamped to 0, S_WAIT
    // aborted with pslverr) the moment m_in_rst_s does catch up — still
    // bounded, still no fabricated write, just detected a few cycles later
    // in that narrow race. See header "Reset strategy".
    //
    // ── Availability-gating exception (PR #132 review, m_rst_n_s) ──────────
    // Project rule: a signal gated by reset state must not advertise
    // "available" as its OWN reset default (this is the exact bug class
    // behind 4398c2e's cpu_gated_clk-stopped-in-reset bug and 7a9f9d4's
    // cdc_gray_fifo wr_ready_o-asserted-in-reset bug — see CLAUDE.md GH #93
    // status). m_rst_n_s violates that rule on its face: cdc_2ff_sync's
    // reset-to-0 default makes m_rst_n_s read 1 ("destination alive") for up
    // to SYNC_STAGES_TO_S s_clk_i cycles after s_rst_sync_n releases, even
    // when m_rst_n_i is genuinely already low. This IS a deliberate,
    // reviewed, LOCAL exception to that rule, not an oversight — recorded
    // here explicitly so a future audit for the same bug class (GH #95)
    // finds it documented rather than rediscovering it. It is safe only
    // because, unlike the two bugs above, every consumer of the
    // false-"alive" reading is independently re-guarded by a second signal
    // (m_rst_sync_n) that does NOT share the exception:
    //   (a) S_WAIT always exits within a bounded number of cycles: either
    //       ack_new (impossible here, see (b)), !req_fwd_q, or !m_rst_n_s
    //       once the synchroniser catches up (<= SYNC_STAGES_TO_S s_clk_i
    //       cycles after the false read began) — completing with
    //       s_pslverr_o=1, never hanging.
    //   (b) No fabricated destination-side write and no toggle-parity
    //       collision: m_rst_sync_n (rst_both_n, async-assert) is already
    //       low for the entire real duration m_rst_n_i is low, independent
    //       of m_rst_n_s's read. That holds u_req_sync/req_seen_q/d_state_q
    //       /ack_toggle_q at their reset values the whole time, so
    //       req_new = (req_toggle_m != req_seen_q) stays false throughout
    //       even if req_toggle_q toggled on the false-alive reading. The
    //       req_toggle_q clamp (below) restores req_toggle_q == 0 the
    //       moment m_rst_n_s catches up, which is guaranteed to happen
    //       before m_rst_sync_n releases (m_rst_sync_n can only release
    //       after m_rst_n_i itself rises — a strictly later event than the
    //       synchroniser catching up to a m_rst_n_i that is still low).
    //   (c) The false-read window is bounded to exactly SYNC_STAGES_TO_S
    //       s_clk_i cycles — ordinary 2FF-sync propagation latency, not an
    //       unbounded or data-dependent hazard.
    // Why documentation, not enforcement: the reviewer's proposed
    // alternative (gate s_psel_i && !s_penable_i with an asserted reset
    // value) is exactly the conservative polarity already tried and
    // rejected — it regressed test_clock_ratio_slow_s_fast_m at an 18 ns/
    // 4 ns clock ratio by stacking a full extra SYNC_STAGES_TO_S-cycle
    // settle latency onto the FIRST post-reset transaction even when
    // m_rst_n_i was never actually asserted (one spurious pslverr=1 that
    // does not exist today). The forwarding decision (req_fwd_q) is
    // already the narrowest thing this status bit gates — the SETUP is
    // still accepted into S_WAIT unconditionally; only the forward is
    // gated — so there is no cheaper enforcement point to move the gate
    // to. The only way to also close the window itself (rather than just
    // bound and no-op it, as done here) is a synchroniser whose reset
    // default depends on knowing m_rst_n_i's true value at reset time,
    // which is precisely what a synchroniser resolves only after
    // SYNC_STAGES_TO_S clock edges — not achievable without deviating from
    // the shared cdc_2ff_sync primitive and its per-domain-synchronised-
    // reset discipline used uniformly everywhere else in this file. Given
    // the window is already proven bounded and side-effect-free by (a)-(c),
    // that deviation is not worth the extra risk. Documentation is correct.
    logic m_in_rst_s;   // 1 = destination domain observed in reset
    logic m_rst_n_s;    // 1 = destination domain observed NOT in reset (alive)

    cdc_2ff_sync #(
        .WIDTH  (1),
        .STAGES (SYNC_STAGES_TO_S)
    ) u_m_rst_status_sync (
        .clk_i   (s_clk_i),
        .rst_n_i (s_rst_sync_n),
        .d_i     (~m_rst_n_i),
        .q_o     (m_in_rst_s)
    );

    // Reads 1 ("alive") as its reset default even while m_rst_n_i is
    // genuinely low, for up to SYNC_STAGES_TO_S s_clk_i cycles after
    // s_rst_sync_n releases — a reviewed, bounded, documented exception
    // to the availability-gating rule. See "Availability-gating exception
    // (PR #132 review, m_rst_n_s)" comment above.
    assign m_rst_n_s = !m_in_rst_s;

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
    // Latched once at SETUP: was this request actually forwarded to the
    // destination (destination observed live), or was it captured only to
    // be locally error-completed (destination already observed in reset)?
    // Gates both the S_WAIT exit condition and the response below — see
    // header "Reset strategy" / "Availability fix".
    logic              req_fwd_q;

    logic              ack_new;   // defined below; forward-referenced here (SV allows it)

    always_comb begin
        s_state_d = s_state_q;
        unique case (s_state_q)
            S_IDLE: if (s_psel_i && !s_penable_i) s_state_d = S_WAIT;
            S_WAIT: begin
                // Bounded on three independent, mutually-exclusive-in-intent
                // conditions so S_WAIT can NEVER hold forever:
                //   1. ack_new     — normal completion, destination answered.
                //   2. !req_fwd_q  — never forwarded (destination was already
                //                    observed in reset at SETUP); complete
                //                    with error on the very next cycle.
                //   3. !m_rst_n_s  — WAS forwarded, but the destination is
                //                    now observed to have gone into reset
                //                    before answering; abort with error.
                if (ack_new || !req_fwd_q || !m_rst_n_s) s_state_d = S_DONE;
            end
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
            // req_toggle_q: advances exactly once per request that is
            // actually forwarded to a live destination, and is otherwise
            // continuously clamped to 0 whenever the destination is
            // observed in reset. The clamp (not a one-shot "revert") is
            // what keeps req_toggle_q correct even if the destination goes
            // into reset mid-S_WAIT after having already been forwarded —
            // by the time m_rst_sync_n (destination side) later releases,
            // req_toggle_q has been sitting at 0 for many cycles, matching
            // req_seen_q's own reset value. See header "Reset strategy".
            if (!m_rst_n_s) begin
                req_toggle_q <= 1'b0;
            end else if (s_state_q == S_IDLE && s_psel_i && !s_penable_i) begin
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
    //
    // Two ways to complete out of S_WAIT (mirrors the s_state_d bound
    // above): a normal ack_new carries the real destination response
    // through; a forced completion (request never forwarded, or the
    // destination went into reset before answering) synthesises
    // prdata=0/pslverr=1 locally — this is the availability-fix escape path,
    // never a read of resp_*_dq, since there is no valid destination
    // response to read in that case.
    // =========================================================================
    logic [31:0] resp_prdata_q;
    logic        resp_pslverr_q;

    always_ff @(posedge s_clk_i or negedge s_rst_sync_n) begin
        if (!s_rst_sync_n) begin
            resp_prdata_q  <= '0;
            resp_pslverr_q <= 1'b0;
        end else if (s_state_q == S_WAIT) begin
            if (ack_new) begin
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

`default_nettype wire
