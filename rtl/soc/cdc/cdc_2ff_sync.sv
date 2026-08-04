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
// This module has NO simulation-time delay injection. An attempt at one was
// reverted before merge because its model was wrong (it could latch a hold
// permanently and stick the synchroniser rather than delaying it by a cycle).
//
// The finding that motivated it stands and is worth recording here, because
// this repo has repeatedly written the opposite: the claim that "metastability
// injection is not modelable in Verilator/cocotb" (design_state.json, CLAUDE.md,
// several test docstrings) is imprecise. What IS modelable, and what OpenTitan
// actually does, is a randomised EXTRA-CYCLE-OF-SETTLING-DELAY on a
// synchroniser's first stage — plain RTL, no timing control, so it works in a
// 2-state cycle-based simulator. That is precisely the fault model that
// reproduces a same-edge-assumption bug, which is the class this repo hit twice
// in GH #93 (fr_57f49b7f9b29 and fr_280f3ac18c66) and which every 1:1-ratio,
// lockstep-reset unit test was structurally blind to.
//
// What remains genuinely NOT modelable here is analog metastability itself — an
// intermediate, non-0/1, potentially oscillating voltage on Q. 4-state X
// injection at the setup/hold boundary is a different and heavier technique.
//
// Reference for a correct implementation, should bead rvs be picked up
// (Apache-2.0, lowRISC contributors — note it takes BOTH src_data_i and
// prev_data_i and is evaluated in the DESTINATION clock's process, which is
// exactly what makes it converge):
//   https://github.com/lowRISC/opentitan/blob/master/hw/ip/prim/rtl/prim_cdc_rand_delay.sv
//   https://github.com/lowRISC/opentitan/blob/master/hw/ip/prim_generic/rtl/prim_flop_2sync.sv
//
// Per house style: no `default_nettype` directive (Spyglass IND, CODING
// GUIDELINES §1.3) — matching pmu.sv:123 and the sibling cdc_reset_sync.sv /
// cdc_gray_fifo.sv. Implicit-net detection is covered by Verilator
// (IMPLICIT/UNDRIVEN) and Verible instead.

module cdc_2ff_sync #(
    parameter int unsigned WIDTH  = 1,
    parameter int unsigned STAGES = 2
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

    always_ff @(posedge clk_i or negedge rst_n_i) begin
        if (!rst_n_i) begin
            for (int unsigned i = 0; i < STAGES; i++) begin
                sync_q[i] <= '0;
            end
        end else begin
            sync_q[0] <= d_i;
            for (int unsigned i = 1; i < STAGES; i++) begin
                sync_q[i] <= sync_q[i-1];
            end
        end
    end

    assign q_o = sync_q[STAGES-1];

endmodule : cdc_2ff_sync
