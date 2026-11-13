// cdc_sync - multi-flop synchroniser for a single bit or a gray-coded bus.
//
// Function: The module passes d_i through STAGES flops on clk_i. q_o shows the result.
//   A change on d_i reaches q_o after exactly STAGES edges of clk_i.
//   The flop array carries the magic_cdc attribute. Do not remove it.
// Parameters:
//   WIDTH      Number of bits. Use more than 1 only for a gray-coded bus.
//   STAGES     Number of flop ranks. The default is 2. The value must be at least 2.
//   RESET_VAL  Value of every rank while rst_n_i is low. The default is '0. Use 1 for an idle-high line.
//   RAND_CDC_DELAY_EN, RAND_CDC_DELAY_PCT, RAND_CDC_DELAY_SEED  Simulation-only random settling delay. The default is off.
// Clocks and resets: clk_i is the destination clock. rst_n_i is active low.
//   It asserts asynchronously and deasserts synchronously. It is expected to be already synchronised to clk_i (see cdc_reset_sync).
// Caller rules:
//   - Use WIDTH greater than 1 only if at most one bit changes per source-clock edge.
//   - Never cross an arbitrary binary bus. Convert it to gray code or use a full handshake.
//   - RESET_VAL must be a value that is safe to show downstream during reset.
//   - The module has no `default_nettype directive.
// Doc: ds:mod:cdc-sync, tm:mod:cdc-sync, cr:mod:cdc-sync
// Ported from (Apache-2.0, lowRISC contributors — concept and reset/seed
// discipline adapted to this repo's house style, not a verbatim copy):
//   https://github.com/lowRISC/opentitan/blob/master/hw/ip/prim/rtl/prim_cdc_rand_delay.sv
//   https://github.com/lowRISC/opentitan/blob/master/hw/ip/prim_generic/rtl/prim_flop_2sync.sv

module cdc_sync #(
    parameter int unsigned WIDTH  = 1,
    parameter int unsigned STAGES = 2,

    // Value of every stage while rst_n_i is asserted (see ds:mod:cdc-sync). Plain
    // packed-vector parameter sized by WIDTH; no struct member select.
    parameter logic [WIDTH-1:0] RESET_VAL = '0,

    // Simulation-only randomised settling-delay injection on stage 0 (see cr:mod:cdc-sync).
    // Defeatable per instance; OFF by default at every existing
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

    // STAGES must be at least 2. The $fatal runs at elaboration, outside an `initial` block.
    if (STAGES < 2) begin : g_stages_check
        $fatal(1, "cdc_sync: STAGES (%0d) must be >= 2", STAGES);
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
        // self-clearing convergence (see tm:mod:cdc-sync)
        // — d_prev_q always catches up to d_i on the very next edge whether
        // or not that edge's capture was held.
        logic [WIDTH-1:0] d_prev_q;

        initial void'($urandom(RAND_CDC_DELAY_SEED));

        always_ff @(posedge clk_i or negedge rst_n_i) begin
            if (!rst_n_i) begin
                d_prev_q <= RESET_VAL;
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
                sync_q[i] <= RESET_VAL;
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

endmodule : cdc_sync
