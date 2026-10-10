// cdc_reset_sync.sv
// GH #91 — Async-assert / sync-deassert active-low reset synchroniser.
//
// Async assert: any level change on rst_n_i propagates to rst_n_o's chain
// immediately via the async clear path, so a downstream domain can never run
// through a reset event waiting for a clock edge. Sync deassert: release of
// rst_n_o is re-timed onto clk_i through STAGES flops, so every flop in the
// destination domain observes reset de-assert relative to the same clk_i
// edge (no reset-removal timing violation, no partial-reset race).
//
// (* magic_cdc *) marks the flop chain so GH #95's cdc_snitch classifies
// this as an intentional CDC primitive rather than an unmarked crossing.
//
// Contract on the caller: rst_n_i must be held low for >= STAGES+1 periods
// of clk_i for a clean, glitch-free deassertion to be observed correctly by
// this domain. A pulse shorter than that can be swallowed or produce a
// deassert edge with insufficient recovery margin.
//
// Used 2x by the GH #91 async_axi_fifo (one per clock domain, driven from a
// shared `s_rst_n_i & m_rst_n_i` root — see async_axi_fifo.sv header for the
// rationale) and reusable by any future multi-clock-domain reset tree (#93
// reuses this for per-domain PMU resets).
//
// Reset: asynchronous assert, synchronous deassert, active-low (new-module
// discipline, docs/development/CODING_GUIDELINES.md §1.4).
//
// ── Scan bypass (DFT, beads claude_verilog_test-07n and j41m.2) ────────────
// Two muxes, both selected by scanmode_i, make this reset fully owned by the
// tester in scan mode (docs/design/DFT_ARCHITECTURE.md sec.4 items 3 and 7):
//
//  1. INPUT mux (07n, OpenTitan prim_rst_sync style): the async clear of the
//     STAGES flops is `scanmode_i ? scan_rst_ni : rst_n_i`. Without it the
//     chain's own clear would follow a functional or derived reset (a PMU or
//     WDT flop, say) while the tester shifts, and clear flops mid-shift.
//  2. OUTPUT mux (j41m.2): the reset DELIVERED to the destination domain,
//     rst_n_o, is `scanmode_i ? scan_rst_ni : sync_q[STAGES-1]`. The chain
//     flops are scan flops: they toggle as data is shifted through them. With
//     only the input mux, rst_n_o = sync_q[last] would therefore pulse every
//     downstream async reset (hundreds of flops) during shift. With the output
//     mux the delivered reset in scan mode is the scan reset itself and does
//     not depend on the state of this module's flops at all.
//
// Consequence for scan mode: rst_n_o is NOT re-timed onto clk_i. A scan_rst_ni
// release is asynchronous to clk_i by construction; the tester owns that timing
// (hold scan_rst_ni stable across the capture window; see the scan-mode SDC,
// Stage 2). Functional mode (scanmode_i = 0) is the original path, bit for bit.
//
// scanmode_i is quasi-static: set before the first test clock edge and not
// toggled while clk_i is running (the same contract every DFT mode signal has).
//
// SystemVerilog has no port default values, so BOTH scanmode_i and
// scan_rst_ni must be connected explicitly at every instantiation. soc_top
// connects them to its dft_scan_mode / dft_scan_rst_n nets; unit tests and
// non-DFT users tie scanmode_i=1'b0, scan_rst_ni=1'b1 (a pure pass-through).
//
// Lint target: verilator -Wall -Wno-IMPORTSTAR 0 errors 0 warnings.

module cdc_reset_sync #(
    parameter int unsigned STAGES = 2
) (
    input  logic clk_i,
    input  logic rst_n_i,

    // ── DFT scan bypass — see the "Scan bypass (DFT)" note above. Must be
    //    connected explicitly at every instantiation (no SV port defaults);
    //    tie scanmode_i=1'b0, scan_rst_ni=1'b1 outside a scan-aware parent. ──
    input  logic scanmode_i,
    input  logic scan_rst_ni,

    output logic rst_n_o
);

    // Elaboration-time guard: STAGES < 2 leaves no settling margin for the
    // deasserting edge. Generate-scope $fatal (not wrapped in `initial`) so
    // it fires under `verilator --lint-only` elaboration, not just
    // simulation — see rtl/soc/sram_controller.sv:110-126.
    if (STAGES < 2) begin : g_stages_check
        $fatal(1, "cdc_reset_sync: STAGES (%0d) must be >= 2", STAGES);
    end

    // Input mux: scan_rst_ni replaces rst_n_i as the chain's async clear in
    // scan mode (see the header). Scanmode low => rst_n_async === rst_n_i.
    logic rst_n_async;
    assign rst_n_async = scanmode_i ? scan_rst_ni : rst_n_i;

    // One always_ff PER STAGE (genvar generate), packed vector storage.
    // Functionally: shift a '1' in at stage 0 every cycle out of reset, i.e.
    // equivalent to `sync_q <= {sync_q[STAGES-2:0], 1'b1}` with async clear.
    //
    // Deliberately NOT written as a single always_ff looping/shifting over
    // an unpacked array or a self-referencing packed vector: this module's
    // rst_n_o is, by construction, always consumed as an ASYNC RESET by
    // flops in the destination domain (that is the entire purpose of a
    // reset synchronizer). Verilator's SYNCASYNCNET check has a false-
    // positive interaction with that combination specifically: a *single*
    // always_ff driving multiple array/vector elements via a for-loop, whose
    // result is later used as a downstream async reset, gets its array
    // elements misclassified as "used both synchronously and
    // asynchronously" (confirmed by isolated repro; cdc_2ff_sync uses the
    // identical array+for-loop shape and lints clean ONLY because its
    // outputs are consumed as data, never as a reset edge). One always_ff
    // per stage sidesteps the false positive entirely and is, if anything,
    // the more idiomatic description of a discrete synchroniser flop chain.
    (* magic_cdc *)
    logic [STAGES-1:0] sync_q;

    genvar g;
    generate
        for (g = 0; g < STAGES; g++) begin : g_stage
            if (g == 0) begin : g_first
                always_ff @(posedge clk_i or negedge rst_n_async) begin
                    if (!rst_n_async) begin
                        sync_q[0] <= 1'b0;
                    end else begin
                        sync_q[0] <= 1'b1;
                    end
                end
            end else begin : g_rest
                always_ff @(posedge clk_i or negedge rst_n_async) begin
                    if (!rst_n_async) begin
                        sync_q[g] <= 1'b0;
                    end else begin
                        sync_q[g] <= sync_q[g-1];
                    end
                end
            end
        end
    endgenerate

    // Output mux: the delivered reset is the scan reset in scan mode,
    // independent of the chain flops (see the header). Scanmode low =>
    // rst_n_o === sync_q[STAGES-1], the original output.
    assign rst_n_o = scanmode_i ? scan_rst_ni : sync_q[STAGES-1];

endmodule : cdc_reset_sync
