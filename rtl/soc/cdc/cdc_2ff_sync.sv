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
// ── On simulating CDC delay (bead claude_verilog_test-rvs) ────────────────
// This module now carries an optional simulation-time randomised settling-
// delay injector on stage 0 of the flop array (RAND_CDC_DELAY_EN, default
// OFF at every instantiation site). This is the SECOND attempt: the first
// (commit 4197139) landed as disabled scaffolding and was reverted (commit
// be485fd) because its model was wrong — it could latch a hold permanently
// and stick the synchroniser instead of delaying it by a cycle. See "Why
// this converges" below for the precise difference.
//
// The finding that motivated this stands regardless of either attempt's
// fate, and is worth recording here because this repo has repeatedly
// written the opposite: the claim that "metastability injection is not
// modelable in Verilator/cocotb" (design_state.json, CLAUDE.md, several test
// docstrings) is imprecise. What IS modelable, and what OpenTitan actually
// does, is a randomised EXTRA-CYCLE-OF-SETTLING-DELAY on a synchroniser's
// first stage — plain RTL, no timing control, so it works in a 2-state
// cycle-based simulator. That is precisely the fault model that reproduces a
// same-edge-assumption bug, which is the class this repo hit twice in GH #93
// (fr_57f49b7f9b29 and fr_280f3ac18c66) and which every 1:1-ratio,
// lockstep-reset unit test was structurally blind to.
//
// What remains genuinely NOT modelable here is analog metastability itself —
// an intermediate, non-0/1, potentially oscillating voltage on Q. 4-state X
// injection at the setup/hold boundary is a different and heavier technique
// this module does not attempt.
//
// Ported from (Apache-2.0, lowRISC contributors — concept and reset/seed
// discipline adapted to this repo's house style, not a verbatim copy):
//   https://github.com/lowRISC/opentitan/blob/master/hw/ip/prim/rtl/prim_cdc_rand_delay.sv
//   https://github.com/lowRISC/opentitan/blob/master/hw/ip/prim_generic/rtl/prim_flop_2sync.sv
//
// Why this converges where the reverted attempt did not: the reverted
// version redrew its hold decision (`hold_sel`) ONLY inside `always @(d_i)`,
// with nothing that ever cleared it back to 0 once d_i stopped moving — so a
// hold could latch and stage0_d = sync_q[0] became a permanent self-loop
// (measured: forcing it on gave async_axi_fifo TESTS=26 PASS=3 FAIL=23).
// This version instead tracks `d_prev_q`, a plain register that is updated
// EVERY destination-clock edge unconditionally (`d_prev_q <= d_i`, no
// dependence on the hold decision). The hold decision is only even DRAWN
// while `d_i !== d_prev_q`, and because d_prev_q always catches up to d_i on
// the very next edge regardless of what was decided, that window can never
// span more than one destination-clock cycle — there is no state here that
// can persist once d_i has settled. This is the same guarantee OpenTitan's
// own design provides via a differently-shaped mechanism (an unconditional
// synchronous clear of `data_sel` on every posedge, racing a combinational,
// event-gated re-arm on `src_data_i`) — both designs take BOTH the new
// source value and the previously-captured value and evaluate the decision
// in the DESTINATION clock's process, which is exactly the property the
// reverted attempt lacked.
//
// Per house style: no `default_nettype` directive (Spyglass IND, CODING
// GUIDELINES §1.3) — matching pmu.sv:123 and the sibling cdc_reset_sync.sv /
// cdc_gray_fifo.sv. Implicit-net detection is covered by Verilator
// (IMPLICIT/UNDRIVEN) and Verible instead.

module cdc_2ff_sync #(
    parameter int unsigned WIDTH  = 1,
    parameter int unsigned STAGES = 2,

    // Simulation-only randomised settling-delay injection on stage 0 (see
    // header). Defeatable per instance; OFF by default at every existing
    // instantiation site, so today's bit-exact deterministic regression is
    // unaffected unless a testbench explicitly opts in. Unused outside
    // `ifdef SIMULATION (every synthesis/lint/CDC-gate elaboration) — same
    // pattern as pll_clkgen.sv's RNM params.
    /* verilator lint_off UNUSEDPARAM */
    parameter bit          RAND_CDC_DELAY_EN   = 1'b0,
    // Percent chance [0,100), drawn once per destination-clock edge at which
    // d_i is found to differ from what was captured on the previous edge,
    // that stage 0 "misses" this edge's update and re-latches its own
    // currently-held value (sync_q[0]) instead.
    parameter int unsigned RAND_CDC_DELAY_PCT  = 32'd50,
    // Reseeds this instance's own random stream once, at time 0, independent
    // of the surrounding simulation's global seed — reproducible run to run
    // for a given (SEED, RAND_CDC_DELAY_PCT, stimulus) combination, instead
    // of depending on an outer harness seed nobody pinned.
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
    // stage0_d: what actually gets clocked into sync_q[0] on the next
    // destination-clock edge. Equals d_i unless RAND_CDC_DELAY_EN=1 injects
    // a "missed edge" (see g_rand_cdc_delay below). Declared/driven ONLY
    // under `ifdef SIMULATION — absent from every synthesis/lint/CDC-gate
    // elaboration, so it cannot affect the synthesised netlist.
    logic [WIDTH-1:0] stage0_d;

    if (RAND_CDC_DELAY_EN) begin : g_rand_cdc_delay
        // Tracks d_i unconditionally, every destination-clock edge, with NO
        // dependence on the hold decision below. This is what guarantees
        // self-clearing convergence (see "Why this converges" in the header)
        // — d_prev_q always catches up to d_i on the very next edge whether
        // or not that edge's capture was held.
        logic [WIDTH-1:0] d_prev_q;

        initial void'($urandom(RAND_CDC_DELAY_SEED));

        always_ff @(posedge clk_i or negedge rst_n_i) begin
            if (!rst_n_i) begin
                d_prev_q <= '0;
            end else begin
                d_prev_q <= d_i;
            end
        end

        // Draw a hold decision only while a source change is pending capture
        // (d_i differs from what the previous edge saw). That window is at
        // most one destination-clock cycle wide by construction (d_prev_q
        // above), so a "hold" here can delay sync_q[0] by at most one extra
        // cycle — it can never persist once d_i has settled.
        always_comb begin
            stage0_d = d_i;
            if (d_i !== d_prev_q) begin
                if ($urandom_range(0, 99) < RAND_CDC_DELAY_PCT) begin
                    stage0_d = sync_q[0];
                end
            end
        end
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
