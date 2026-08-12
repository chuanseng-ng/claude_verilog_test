// apb_cdc_bridge.sv
// GH #93 — APB4 clock-domain-crossing bridge (4-phase RZ handshake).
//
// Converted from a 2-phase (NRZ) toggle handshake to 4-phase (RZ,
// return-to-zero) by bead claude_verilog_test-rfz (2026-08-12) — see
// "Why 4-phase, not a documented contract" below before "simplifying" this
// back to a toggle scheme. All other design decisions in this file (the
// asymmetric reset strategy, the m_rst_n_s availability exception, the
// bounded S_WAIT/S_REQ escape paths) predate the encoding change and are
// UNCHANGED by it except where the prose below explicitly says so.
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
// fix to GH #93/#95). GH #95 reused this same module for the APB3 debug
// port (u_apb_dbg_cdc) too.
//
// ── Why 4-phase, not a documented contract (bead claude_verilog_test-rfz) ──
// The ORIGINAL version of this module used a 2-phase (NRZ) toggle handshake:
// a single bit flipped once per transfer, and the peer domain detected a
// transfer by comparing its synchronised copy against a locally-tracked
// "last seen" value (req_seen_q / ack_seen_q, now removed — see below). PULP
// (cdc_reset_ctrlr.sv) and OpenTitan (prim_sync_reqack.sv) both
// independently conclude that encoding is unsafe under ONE-SIDED
// asynchronous reset, and both ship a 4-phase RZ variant specifically to
// fix it:
//   - PULP: "We use a 4-phase rather than a 2-phase CDC to avoid the issues
//     of one-sided async reset that might trigger spurious transactions."
//   - OpenTitan: its RZ option "is safe to reset either domain in isolation,
//     since the two FSMs cannot get out of sync due to persistent EVEN/ODD
//     states." Its NRZ default instead carries an explicit machine-checked
//     contract that resetting one domain requires resetting the other AT
//     THE SAME TIME.
// Three independent async-APB bridges surveyed for this bead — ARM
// cmsdk_ahb_to_apb_async.v, Hazard3 hazard3_apb_async_bridge, and OpenDAP —
// are all 4-phase, and OpenDAP states the failure mode in exactly these
// terms: "A NRZI toggle handshake ... can cause spurious bus accesses when
// only one side of the link is reset." This module's structure already
// matched ARM's bridge exactly (2x 2-FF sync on the handshake only, payload
// held stable and read combinationally once qualified) — only the encoding
// differed, and NRZ was the one all three surveyed projects avoided.
//
// The cheaper alternative — document + assert a contract that a CPU-domain
// PMU reset must not overlap an in-flight APB_PLL2 transaction — was
// evaluated and REJECTED: OpenTitan's NRZ contract requires that resetting
// one domain also resets the other, OVERLAPPING — which this SoC's PMU
// cannot honour, since PD_CPU power-down resets the CPU domain (this
// module's m_* face for u_apb_pll2_cdc) ALONE by design. Worse, the PMU
// power-down path has no drain/quiesce step (a known, documented gap —
// see soc_top.sv), so nothing guarantees the config path is idle before a
// one-sided reset can land. Documenting a contract the design already
// violates is not a fix.
//
// GH #95 directed testing (test_reset_asym_s_held_m_free,
// test_reset_asym_staggered_s_then_m, test_reset_asym_staggered_m_then_s —
// 3 stagger windows x 2 release orders each) found NO counterexample under
// the OLD NRZ encoding. This conversion is therefore a structural fix
// against a class two upstream projects and three independent bridges treat
// as real, not a response to an observed simulation failure. Throughput is
// halved (two round trips instead of one per transfer, see protocol below);
// this is fine and expected on a config/debug path (APB_PLL2, APB3 debug),
// never a data path.
//
// Protocol: 4-phase (return-to-zero) handshake, depth-1 (one outstanding
// transfer). Unlike the old NRZ scheme, NEITHER side keeps a "last seen"
// comparator register — each side tracks only the CURRENT LEVEL of its own
// request/ack line and the peer's synchronised copy, so there is no
// parity/count state that a one-sided reset can desynchronise. A transfer
// is one full round trip through four phases (assert req, assert ack,
// deassert req, deassert ack):
//   Source (s_*) domain:
//     - Captures {pwrite, paddr, pwdata, pstrb} into a register the instant
//       the upstream APB master (axil_to_apb) enters SETUP (psel && !penable)
//       — this is the one cycle APB guarantees these fields are already
//       stable and unchanging through the whole subsequent ACCESS phase.
//     - S_REQ: asserts req_q ONLY if the destination domain is currently
//       observed out of reset (see "Availability fix" below); otherwise the
//       request is completed locally with an error and req_q is never
//       asserted at all. Holds off completion until either the
//       destination's ack round-trips back (ack_s asserts), OR the
//       destination domain is observed to enter reset while the request is
//       in flight — whichever happens first. Either way S_REQ is guaranteed
//       to resolve within a bounded number of s_clk_i cycles; the source
//       domain can never be held waiting on a destination that will never
//       answer. On resolving, the response (real or synthesised error) is
//       captured into resp_prdata_q/resp_pslverr_q immediately, req_q is
//       deasserted, and control moves to S_DROP — NOT to a pready pulse
//       yet, see below.
//     - S_DROP: waits for ack_s to fall back to 0 (the destination
//       completing its own half of the return-to-zero handshake) before
//       s_pready_o is allowed to assert. This ordering is NOT optional: APB
//       is master-driven, so the instant s_pready_o pulses the upstream
//       master is free to drive a brand-new SETUP as early as the very next
//       cycle, and it will NOT retry if this slave was not actually back at
//       (or one cycle from) S_IDLE to see it — S_IDLE is the only state
//       that samples a SETUP at all. Pulsing pready before the
//       return-to-zero half is done would silently drop the next
//       transaction's SETUP. So the FULL 4-phase round trip (assert +
//       deassert) gates s_pready_o for EVERY transaction, not just
//       back-to-back throughput.
//     - S_DONE (NEW STATE, but same one-cycle-pulse ROLE the old NRZ
//       scheme's S_DONE had): one-cycle s_pready_o pulse using the
//       already-captured response, then back to S_IDLE — ready for a new
//       SETUP the very next cycle, exactly like the old scheme.
//   Destination (m_*) domain:
//     - Synchronises ONLY req_q (single bit) via cdc_2ff_sync, never the
//       multi-bit command payload itself — see the CDC argument below.
//     - D_IDLE: on req_m (the synchronised level) reading 1, captures the
//       (already stable) command payload and moves to D_SETUP.
//     - D_SETUP / D_ACCESS: drives one APB SETUP+ACCESS transfer at the m_*
//       face (a plain APB master), waiting for m_pready_i exactly like any
//       other APB master — unchanged from the old scheme.
//     - D_ACK (NEW): on m_pready_i, captures {prdata, pslverr} and asserts
//       ack_q. Waits for req_m to be observed dropping back to 0 (the
//       source saw the ack and deasserted req_q) before deasserting ack_q
//       and returning to D_IDLE — completing the 4-phase round trip on
//       this side and re-arming for the next request.
//
// CDC argument (why the multi-bit payloads are safe without per-bit sync):
//   Both cmd_*_q (source domain) and resp_*_dq (destination domain) are
//   registered ONCE per transfer and then held perfectly stable for the
//   ENTIRE remainder of that transfer's round trip (many clock periods of
//   the *other* domain — at minimum SYNC_STAGES_TO_{S,M}+1 cycles each way,
//   in practice a full APB SETUP+ACCESS sequence PLUS the return-to-zero
//   half). The capturing domain only samples that stable payload after its
//   own synchronised copy of the corresponding req/ack LEVEL has risen,
//   i.e. strictly after the source value was already stable. This is the
//   same "stable data qualified by a synchronised single-bit control
//   signal" pattern as cdc_gray_fifo's mem_q combinational read (see
//   async_axi_fifo.sv header) — it is NOT the same as running an arbitrary
//   multi-bit binary bus through cdc_2ff_sync (which cdc_2ff_sync's own
//   header explicitly forbids). RZ makes this argument, if anything,
//   stronger than NRZ: the payload is now held stable for the WHOLE
//   4-phase round trip (assert + deassert), not just the assert half.
//
// !!! Cross-domain combinational reads — READ BEFORE STA !!!
// cmd_paddr_q/cmd_pwrite_q/cmd_pwdata_q/cmd_pstrb_q (source domain) are read
// combinationally by the destination-domain capture register, and
// resp_prdata_dq/resp_pslverr_dq (destination domain) are read
// combinationally by the source-domain capture register. Both reads are
// safe per the CDC argument above but are still physical cross-domain
// datapaths. Mirroring the GH #94 action item already open on
// async_axi_fifo.sv, STA must add `set_max_delay -datapath_only` on these
// four payload buses AND on the two single-bit level crossings (req_q,
// ack_q) through their respective cdc_2ff_sync instances, AND on the
// existing m_rst_n_i -> m_rst_n_s single-bit status crossing described
// below. This bead renamed req_toggle_q/ack_toggle_q to req_q/ack_q —
// pnr/constraints/phase5_soc_multiclock_check.sdc sections 12/12a (the only
// place these signal names are matched by literal Tcl pattern, not just
// mentioned in prose) were updated in the same commit; see that file's
// bead-7l5 "OBJECT RESOLUTION" note for why a stale name pattern silently
// matches zero objects instead of erroring.
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
// The fix is ASYMMETRIC, and each half is justified independently. This is
// UNCHANGED by the RZ conversion — the availability bug and its fix are
// orthogonal to the NRZ-vs-RZ handshake encoding, which is what bead
// claude_verilog_test-rfz addresses instead.
//
//   * s_rst_sync_n is rooted in s_rst_n_i ONLY (no longer rst_both_n). The
//     source-domain FSM (s_state_q, cmd_*_q, req_q, req_fwd_q, resp_*_q)
//     resets/advances purely on its own domain's reset, so it is never
//     starved by an event on the OTHER domain. This is what actually closes
//     the availability bug.
//
//   * m_rst_sync_n is DELIBERATELY LEFT on rst_both_n = s_rst_n_i &
//     m_rst_n_i. Under the OLD NRZ scheme this coupling was strictly
//     required to protect req_toggle_q's parity invariant against
//     req_seen_q — the destination domain's "last seen" register, removed
//     by this conversion (see line 29). See the pre-rfz version of this
//     file. Under RZ, req_q/req_m have NO parity/count state to protect
//     (each side just tracks a current level, and D_ACK's exit condition
//     — !req_m — and S_REQ's entry condition — a fresh SETUP — cannot
//     alias: see "no fabricated write" argument below), so this coupling
//     is no longer strictly NECESSARY for correctness. It is retained
//     anyway as a conservative, minimal-diff choice: this bead's scope is
//     the handshake ENCODING, not a re-derivation of the reset topology,
//     and the coupled hard-flush behaviour below is already reviewed,
//     documented, and tested. Revisiting whether m_rst_sync_n can also be
//     decoupled from s_rst_n_i (matching OpenTitan's "safe to reset either
//     domain in isolation" claim even MORE literally) is a follow-up, not
//     this bead.
//
//   Because s_rst_sync_n no longer follows m_rst_n_i, req_q on its own can
//   no longer be guaranteed to land back at 0 in step with the destination
//   for an m_rst_n_i-only event. This is closed by a THIRD mechanism:
//   m_rst_n_i is synchronised into the s domain (m_rst_n_s, via
//   cdc_2ff_sync, single-bit — safe under that module's own scope rules)
//   and used to (a) gate whether a new request is forwarded at all
//   (req_fwd_q captured at SETUP), (b) bound S_REQ so it always resolves —
//   on ack_s (normal), or immediately if the request was never forwarded,
//   or by force-completing with s_pslverr_o=1 if the destination is
//   observed to go into reset while the request is in flight — and (c)
//   continuously clamp req_q to 0 for as long as m_rst_n_s reads 0. That
//   clamp is what re-establishes req_q==0 matching req_m's own reset
//   default for an m_rst_n_i-only event, without needing s_rst_sync_n to
//   depend on m_rst_n_i at all. No write is ever fabricated on the
//   destination side from an errored request: either the request was never
//   forwarded (req_fwd_q=0, req_q never asserted), or it WAS forwarded and
//   the clamp guarantees req_q returns to 0 well before m_rst_sync_n (which
//   the same m_rst_n_i event also asserts, asynchronously and immediately)
//   ever releases and lets D_IDLE resume watching req_m.
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
// No fabricated destination-side write, RZ argument (replaces the old
// toggle-parity argument): D_ACK only returns to D_IDLE once it observes
// req_m==0, so req_m is GUARANTEED 0 every time D_IDLE re-evaluates
// `if (req_m) -> D_SETUP`; any subsequent read of req_m==1 there is
// therefore necessarily a genuine, later rise — never a stale leftover from
// a request the source already gave up on. Symmetrically, S_DROP only
// advances (to S_DONE, and from there unconditionally back to S_IDLE one
// cycle later) once it observes ack_s==0, so ack_s is GUARANTEED 0 every
// time S_IDLE is re-entered; S_REQ's `if (ack_s)` check can therefore never
// alias a NEW request's wait against a stale, undrained ack from a
// PREVIOUS one. This alternation is what removes the need for a
// parity/toggle-compare register entirely — it is enforced structurally by
// each side gating its OWN return-to-idle on the very signal whose rise
// gates leaving idle, not by tracking a count.
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
// regs run on the raw reference, so this bridge's m_* face must too), and a
// second time (u_apb_dbg_cdc, GH #95) between the top-level APB3 debug port
// (source, core_clk domain) and u_cpu's APB3 debug slave (destination,
// cpu_gated_clk domain).
//
// Coding rules: registered FSMs only; async-assert/sync-deassert reset
// (docs/development/CODING_GUIDELINES.md §1.4), matching cdc_2ff_sync /
// cdc_reset_sync discipline.
// Lint target: verilator -Wall -Wno-IMPORTSTAR 0 errors 0 warnings.

`default_nettype none

module apb_cdc_bridge #(
    parameter int unsigned ADDR_W           = 12,  // APB4 local address width (byte address)
    parameter int unsigned SYNC_STAGES_TO_S = 2,    // stages synchronising INTO the s_* domain (ack, s reset, m_rst_n_i status)
    parameter int unsigned SYNC_STAGES_TO_M = 2     // stages synchronising INTO the m_* domain (req, m reset)
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
    // BOTH resets (a conservative, reviewed choice — see header, no longer
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
    // req/ack levels.
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
    // is unaffected: the destination's own req_m/ack_q/d_state_q stay
    // async-held at 0 by m_rst_sync_n for as long as m_rst_n_i is actually
    // low (rst_both_n includes it), so a request forwarded during the few
    // cycles before this synchroniser catches up is invisible to the
    // destination and is cleaned up (req_q clamped to 0, S_REQ aborted with
    // pslverr) the moment m_in_rst_s does catch up — still bounded, still no
    // fabricated write, just detected a few cycles later in that narrow
    // race. See header "Reset strategy".
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
    // here explicitly so a future audit for the same bug class finds it
    // documented rather than rediscovering it. It is safe only because,
    // unlike the two bugs above, every consumer of the false-"alive" reading
    // is independently re-guarded by a second signal (m_rst_sync_n) that
    // does NOT share the exception:
    //   (a) S_REQ always exits within a bounded number of cycles: either
    //       ack_s (impossible here, see (b)), !req_fwd_q, or !m_rst_n_s once
    //       the synchroniser catches up (<= SYNC_STAGES_TO_S s_clk_i cycles
    //       after the false read began) — completing with s_pslverr_o=1,
    //       never hanging.
    //   (b) No fabricated destination-side write and no stale-level
    //       collision: m_rst_sync_n (rst_both_n, async-assert) is already
    //       low for the entire real duration m_rst_n_i is low, independent
    //       of m_rst_n_s's read. That holds d_state_q/req_m/ack_q/
    //       cmd_*_cap_q at their reset values the whole time, so req_m stays
    //       false throughout even if req_q asserted on the false-alive
    //       reading. The req_q clamp (below) restores req_q == 0 the moment
    //       m_rst_n_s catches up, which is guaranteed to happen before
    //       m_rst_sync_n releases (m_rst_sync_n can only release after
    //       m_rst_n_i itself rises — a strictly later event than the
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
    // still accepted into S_REQ unconditionally; only the forward is
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
    // Source domain (s_clk_i): command capture + req level + FSM
    //
    // 4-phase RZ states (bead claude_verilog_test-rfz): S_IDLE -> S_REQ
    // (assert req_q, wait for ack_s or a bounded abort) -> S_DROP (deassert
    // req_q, wait for ack_s to fall — the NEW "return to zero" half a
    // 2-phase toggle does not need) -> S_DONE (one-cycle s_pready_o pulse,
    // using the response already captured back in S_REQ) -> back to S_IDLE.
    //
    // ORDERING IS DELIBERATE and NOT interchangeable with "pulse pready
    // first, deassert after" (which this file's first RZ draft got wrong
    // and which a directed cocotb regression caught immediately — see
    // bead claude_verilog_test-rfz session notes): APB is MASTER-driven —
    // the instant s_pready_o pulses, the upstream master is free to drive a
    // brand-new SETUP on the very next s_clk_i cycle, and it will NOT retry
    // if this slave was not actually back at S_IDLE to see it (a SETUP
    // presented while s_state_q is anything other than S_IDLE is silently
    // missed — S_IDLE is the only state that samples s_psel_i/s_penable_i
    // at all). So s_pready_o must NOT assert until the return-to-zero half
    // is ALSO done, i.e. until the state that immediately precedes S_IDLE.
    // Net effect: the full 4-phase round trip (assert + deassert) gates
    // EVERY transaction's s_pready_o, not just back-to-back throughput —
    // see the header protocol description and the latency-budget test
    // (tb/cocotb/soc/test_apb_cdc_bridge.py) for the revised bound.
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
    // header "Reset strategy" / "Availability fix".
    logic              req_fwd_q;

    logic              ack_s;   // defined below; forward-referenced here (SV allows it)

    always_comb begin
        s_state_d = s_state_q;
        unique case (s_state_q)
            S_IDLE: if (s_psel_i && !s_penable_i) s_state_d = S_REQ;
            S_REQ: begin
                // Bounded on three independent, mutually-exclusive-in-intent
                // conditions so S_REQ can NEVER hold forever:
                //   1. ack_s       — normal completion, destination answered.
                //   2. !req_fwd_q  — never forwarded (destination was already
                //                    observed in reset at SETUP); complete
                //                    with error on the very next cycle.
                //   3. !m_rst_n_s  — WAS forwarded, but the destination is
                //                    now observed to have gone into reset
                //                    before answering; abort with error.
                // ack_s is checked with priority (see the response-capture
                // always_ff below) so a same-cycle race between a genuine
                // ack and a destination-reset observation resolves in favour
                // of the real response — see test_availability_ack_race_wins.
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
            // req_q: asserted exactly once per request that is actually
            // forwarded to a live destination, deasserted the moment its
            // ack is observed (starting the return-to-zero half), and
            // otherwise continuously clamped to 0 whenever the destination
            // is observed in reset. The clamp (not a one-shot "revert") is
            // what keeps req_q correct even if the destination goes into
            // reset mid-S_REQ after having already been forwarded — by the
            // time m_rst_sync_n (destination side) later releases, req_q
            // has been sitting at 0 for many cycles, matching req_m's own
            // reset value. See header "Reset strategy".
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
    // req_q: s_clk_i -> m_clk_i (single bit — safe for cdc_2ff_sync)
    // =========================================================================
    logic req_m;

    cdc_2ff_sync #(
        .WIDTH  (1),
        .STAGES (SYNC_STAGES_TO_M)
    ) u_req_sync (
        .clk_i   (m_clk_i),
        .rst_n_i (m_rst_sync_n),
        .d_i     (req_q),
        .q_o     (req_m)
    );

    // =========================================================================
    // Destination domain (m_clk_i): command capture + APB master FSM +
    // response capture + ack level
    //
    // D_ACK (NEW) holds ack_q asserted until req_m is observed to have
    // fallen (the source dropped req_q after seeing the ack), then
    // deasserts ack_q and returns to D_IDLE. This — not a toggle/parity
    // register — is what makes D_IDLE's `if (req_m)` check unambiguous: by
    // construction req_m reads 0 every time D_IDLE re-evaluates it (D_ACK's
    // own exit condition guarantees that), so any later req_m==1 is
    // necessarily a genuine new request. See header "No fabricated
    // destination-side write, RZ argument".
    // =========================================================================
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
            // Cross-domain combinational capture of the source-domain
            // command latch — see "CDC argument" in the module header.
            // GH #94 STA action: set_max_delay -datapath_only on this read.
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
    // ack_q: m_clk_i -> s_clk_i (single bit — safe for cdc_2ff_sync)
    // =========================================================================
    cdc_2ff_sync #(
        .WIDTH  (1),
        .STAGES (SYNC_STAGES_TO_S)
    ) u_ack_sync (
        .clk_i   (s_clk_i),
        .rst_n_i (s_rst_sync_n),
        .d_i     (ack_q),
        .q_o     (ack_s)
    );

    // =========================================================================
    // Source-domain response capture (cross-domain combinational read of
    // resp_*_dq — see "CDC argument" in the module header; GH #94 STA
    // action: set_max_delay -datapath_only on this read too) + APB outputs
    //
    // Two ways to complete out of S_REQ (mirrors the s_state_d bound
    // above): a normal ack_s carries the real destination response through;
    // a forced completion (request never forwarded, or the destination went
    // into reset before answering) synthesises prdata=0/pslverr=1 locally —
    // this is the availability-fix escape path, never a read of resp_*_dq,
    // since there is no valid destination response to read in that case.
    // =========================================================================
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
