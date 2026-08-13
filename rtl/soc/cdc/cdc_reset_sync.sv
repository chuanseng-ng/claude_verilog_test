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
// ── Scan bypass (DFT, bead claude_verilog_test-07n) ────────────────────────
// During scan shift the tester must be able to control this chain's async
// clear directly — otherwise the synchroniser flops (and everything
// downstream that consumes rst_n_o as an async reset) cannot be scanned, and
// the reset tree feeding them becomes an untestable island. Standard fix,
// same shape as OpenTitan's prim_rst_sync: mux the async-clear SOURCE
// between the functional rst_n_i and a tester-driven scan_rst_ni, selected
// by scanmode_i. The mux output (rst_n_async below) replaces rst_n_i
// everywhere it previously appeared as the `negedge` reset in this file's
// always_ff blocks; scanmode_i itself is treated as quasi-static (driven by
// a scan controller / boundary-scan cell, not toggled mid-shift), matching
// how every other DFT mode signal in a real flow behaves, so this is not an
// arbitrary-glitch combinational hazard in practice.
//
// SystemVerilog has no port default values, so BOTH scanmode_i and
// scan_rst_ni must be connected explicitly at every instantiation. This
// project has no DFT/scan flow yet (bead claude_verilog_test-07n is filed
// pre-emptively): every current instantiation ties scanmode_i=1'b0,
// scan_rst_ni=1'b1 (scan mode off, scan reset held inactive so it can never
// be the clear source), making the mux a pure pass-through of rst_n_i and
// changing nothing about current behaviour. See soc_top.sv's single tie-off
// comment block for where those constants live for this design.
//
// Lint target: verilator -Wall -Wno-IMPORTSTAR 0 errors 0 warnings.

module cdc_reset_sync #(
    parameter int unsigned STAGES = 2
) (
    input  logic clk_i,
    input  logic rst_n_i,

    // ── DFT scan bypass — see "Scan bypass (DFT)" note above. Must be
    //    connected explicitly at every instantiation (no SV port defaults);
    //    tie scanmode_i=1'b0, scan_rst_ni=1'b1 where no scan flow exists. ──
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

    // Scan-mode async-clear source mux (OpenTitan prim_rst_sync style): the
    // functional rst_n_i is replaced by the tester-driven scan_rst_ni while
    // scanmode_i is asserted, so ATPG owns this chain's async clear during
    // scan shift instead of being at the mercy of whatever rst_n_i happens
    // to be doing. With scanmode_i tied low (no scan flow today), this is a
    // pure combinational pass-through and rst_n_async === rst_n_i.
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

    assign rst_n_o = sync_q[STAGES-1];

endmodule : cdc_reset_sync
