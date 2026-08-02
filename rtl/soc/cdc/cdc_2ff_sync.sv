// cdc_2ff_sync.sv
// GH #91 — Generic multi-flop CDC synchroniser.
//
// !!! SCOPE WARNING — READ BEFORE INSTANTIATING !!!
// This module is valid ONLY for:
//   * single-bit signals (WIDTH = 1), or
//   * multi-bit buses that are GRAY-CODED such that at most one bit changes
//     per source-clock edge (e.g. a registered gray pointer).
// It is NOT safe for an arbitrary multi-bit binary bus. Independent bits can
// each resolve metastability in a different destination-clock cycle, so the
// sampled word can transiently equal a value the source side never drove.
// A binary bus MUST be converted to gray code (see cdc_gray_fifo.sv) or
// crossed via a full handshake protocol before using this primitive.
//
// (* magic_cdc *) is placed on the flop array so GH #95's cdc_snitch
// structural CDC checker classifies every crossing through this module as an
// intentional, reviewed synchroniser (`CDC`) rather than an unmarked
// crossing (`BAD`/`OKX`). Do not remove the attribute.
//
// Used 10x by the GH #91 dual-clock AXI4 bridge (2 gray pointers x 5
// cdc_gray_fifo instances) and reusable anywhere else a single-bit or
// gray-coded signal must cross clock domains.
//
// Reset: asynchronous assert, synchronous deassert, active-low (new-module
// discipline, docs/development/CODING_GUIDELINES.md §1.4). rst_n_i is
// expected to already be a per-domain-synchronised reset (see
// cdc_reset_sync.sv) at the instantiation site.
//
// Lint target: verilator -Wall -Wno-IMPORTSTAR 0 errors 0 warnings.
//
// ── Simulation-only randomised delay injection (bead claude_verilog_test-rvs) ──
//
// !!! DO NOT SET RAND_CDC_DELAY_EN=1 — THE MODEL BELOW IS KNOWN DEFECTIVE !!!
// The injector is committed as scaffolding only and is inert at every
// instantiation site. Its hold decision is redrawn ONLY inside
// `always @(d_i)`, so once hold_sel latches 1 the assignment
// `stage0_d = sync_q[0]` becomes a self-loop: sync_q[0] can never change, and
// because d_i has finished transitioning the block never fires again to redraw.
// The synchroniser is then STUCK-AT its old value permanently — not delayed by
// a cycle. Measured: forcing RAND_CDC_DELAY_EN=1 gives async_axi_fifo
// TESTS=26 PASS=3 FAIL=23, i.e. the injector breaking the design rather than
// finding bugs in it.
// The fix is to redraw once per DESTINATION CLOCK EDGE while d_i != sync_q[0]
// (fold the decision into the clocked stage-0 process), so a held cycle is
// always followed by another draw and the value converges. Compare OpenTitan's
// prim_cdc_rand_delay.sv, which takes both src_data_i AND prev_data_i and is
// evaluated in the destination clock's process for exactly this reason.
// Acceptance criteria are recorded on bead claude_verilog_test-rvs.
//
// Optional, per-instance, OFF by default (RAND_CDC_DELAY_EN=0): stage 0 of
// the flop array can be made to occasionally "miss" a source-word change and
// re-latch its own previous value instead, i.e. the synchronised output
// takes at least one extra clk_i cycle to reflect a source change. The INTENT
// (not yet achieved — see the defect warning above) is to reproduce the bug
// SHAPE this repo has hit twice on real silicon-
// destined RTL — GH #93's fr_57f49b7f9b29 (a clock-enable synchroniser whose
// reset value read "not disabled" for the whole reset window) and
// fr_280f3ac18c66 (cdc_gray_fifo's wr_ready_o reading "ready" before the
// domain's own reset released) — both of which downstream logic assumed
// updated on the same edge its source changed, and both of which were
// invisible to every 1:1-clock-ratio and lockstep-reset unit test that
// existed at the time.
//
// Corrected claim: earlier revisions of this repo (design_state.json,
// CLAUDE.md, several test docstrings) stated "metastability injection is
// not modelable in Verilator/cocotb." That is imprecise. What follows IS
// modelable and now implemented: a randomised EXTRA-CYCLE-OF-SETTLING-DELAY
// on a synchroniser's first stage, which is exactly the fault model that
// makes a same-edge-assumption bug reproduce. What remains NOT modelable in
// a 2-state simulator (Verilator; this applies equally to any cocotb/
// iverilog flow) is true analog metastability itself — an intermediate,
// non-01, potentially-oscillating voltage on the flop's Q output. 4-state X
// injection at the setup/hold boundary is a different, heavier technique
// (delta-cycle race modelling) that this module does not attempt.
//
// Modelling idea ported (concept only, rewritten to this repo's house style
// and reset discipline — NOT a verbatim copy) from OpenTitan's
// prim_cdc_rand_delay.sv, Apache-2.0, lowRISC contributors:
//   https://github.com/lowRISC/opentitan/blob/master/hw/ip/prim/rtl/prim_cdc_rand_delay.sv
//   https://github.com/lowRISC/opentitan/blob/master/hw/ip/prim_generic/rtl/prim_flop_2sync.sv
//
// Synthesis-path guarantee: every line touched by this feature lives inside
// `ifdef SIMULATION, which this repo's synthesis/lint/CDC-gate flows
// (sim/Makefile's lint_soc, tools/cdc/ sv2v+yosys, pnr/'s sv2v builds) never
// define. Under all of those, and whenever RAND_CDC_DELAY_EN=0 (the default
// at every existing instantiation site today), this file elaborates to
// bit-for-bit the same two lines it always has: `sync_q[0] <= d_i;`.
//
// Per house style: no `default_nettype` directive (Spyglass IND, CODING
// GUIDELINES §1.3) — matching pmu.sv:123 and the sibling cdc_reset_sync.sv /
// cdc_gray_fifo.sv. Implicit-net detection is covered by Verilator
// (IMPLICIT/UNDRIVEN) and Verible instead.

module cdc_2ff_sync #(
    parameter int unsigned WIDTH  = 1,
    parameter int unsigned STAGES = 2,

    // Simulation-only randomised delay injection on stage 0 (see header).
    // Defeatable per instance; defaults preserve today's bit-exact
    // deterministic regression (178/178) at every existing instantiation
    // site — nobody has to opt in, and nothing opts in silently.
    // Suppressed: unused outside `ifdef SIMULATION (every synthesis/lint/
    // CDC-gate elaboration) — same pattern as pll_clkgen.sv's RNM params.
    /* verilator lint_off UNUSEDPARAM */
    parameter bit          RAND_CDC_DELAY_EN   = 1'b0,
    // Percent chance [0,100) per destination-clock edge, when d_i differs
    // from the flop's currently-held value, that stage 0 "misses" it.
    parameter int unsigned RAND_CDC_DELAY_PCT  = 32'd50,
    // Reseeds this instance's own random stream on first use, independent
    // of the surrounding simulation's global seed — reproducible run to
    // run for a given (SEED, RAND_CDC_DELAY_PCT, stimulus) combination,
    // instead of depending on an outer harness seed nobody pinned.
    parameter int unsigned RAND_CDC_DELAY_SEED = 32'hCDC2_5EED
    /* verilator lint_on  UNUSEDPARAM */
) (
    // ── Destination-domain clock/reset ───────────────────────────────────────
    input  logic             clk_i,
    input  logic             rst_n_i,

    // ── Data ──────────────────────────────────────────────────────────────────
    input  logic [WIDTH-1:0] d_i,
    output logic [WIDTH-1:0] q_o
);

    // Elaboration-time guard: STAGES < 2 defeats the purpose of a multi-flop
    // synchroniser (single-flop capture gives no metastability settling
    // time). Fails immediately under lint/synth elaboration, not just sim
    // (generate-scope $fatal, not wrapped in `initial` — see
    // rtl/soc/sram_controller.sv:110-126 for why `initial $fatal` alone is
    // not sufficient under `verilator --lint-only`).
    if (STAGES < 2) begin : g_stages_check
        $fatal(1, "cdc_2ff_sync: STAGES (%0d) must be >= 2", STAGES);
    end

    // ── Synchroniser flop array ──────────────────────────────────────────────
    (* magic_cdc *)
    logic [WIDTH-1:0] sync_q [STAGES];

`ifdef SIMULATION
    // stage0_d: what actually gets clocked into sync_q[0]. Equals d_i unless
    // RAND_CDC_DELAY_EN=1 injects a "missed edge" (see g_rand_cdc_delay
    // below). Declared/driven ONLY under `ifdef SIMULATION — absent from
    // every synthesis/lint/CDC-gate elaboration.
    logic [WIDTH-1:0] stage0_d;

    if (RAND_CDC_DELAY_EN) begin : g_rand_cdc_delay
        // Static (module-lifetime) process state — not a clocked register,
        // deliberately: it is simulation bookkeeping for the injector
        // itself, not part of the synchroniser's synthesisable state.
        bit seeded;
        bit hold_sel;

        initial begin
            seeded   = 1'b0;
            hold_sel = 1'b0;
        end

        // Draw a fresh (seeded, reproducible) decision only when the source
        // word actually changes — mirrors OpenTitan's event-gated trigger,
        // avoids re-drawing on unrelated activity, and keeps hold_sel driven
        // from exactly one process (no blocking/non-blocking races on the
        // same signal).
        always @(d_i) begin
            if (!seeded) begin
                void'($urandom(RAND_CDC_DELAY_SEED));
                seeded = 1'b1;
            end
            hold_sel = ($urandom_range(0, 99) < RAND_CDC_DELAY_PCT);
        end

        // On a "miss", stage 0 re-latches what it already holds (sync_q[0])
        // instead of the new d_i — i.e. it misses this edge's update and
        // catches up on a later one, exactly modelling a synchroniser whose
        // visible output lags a real source change by an extra cycle.
        assign stage0_d = hold_sel ? sync_q[0] : d_i;
    end else begin : g_no_rand_cdc_delay
        assign stage0_d = d_i;
    end
`endif

    always_ff @(posedge clk_i or negedge rst_n_i) begin
        if (!rst_n_i) begin
            for (int unsigned i = 0; i < STAGES; i++) begin
                sync_q[i] <= '0;
            end
        end else begin
`ifdef SIMULATION
            sync_q[0] <= stage0_d;
`else
            sync_q[0] <= d_i;
`endif
            for (int unsigned i = 1; i < STAGES; i++) begin
                sync_q[i] <= sync_q[i-1];
            end
        end
    end

    assign q_o = sync_q[STAGES-1];

endmodule : cdc_2ff_sync
