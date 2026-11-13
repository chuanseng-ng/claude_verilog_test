// cdc_reset_sync - reset synchroniser with asynchronous assert and synchronous deassert.
//
// Function: rst_n_o asserts at once when rst_n_i goes low. rst_n_o deasserts after STAGES edges of clk_i.
//   The flop chain carries the magic_cdc attribute.
//   Scan bypass (DFT): when scanmode_i is 1, scan_rst_ni is the async clear of the chain and is rst_n_o.
//   The module does not re-time scan_rst_ni.
// Parameters: STAGES. The default is 2. The value must be at least 2.
// Clocks and resets: clk_i is the destination clock. rst_n_i is the active-low source reset.
// Caller rules:
//   - Hold rst_n_i low for at least STAGES+1 periods of clk_i.
//   - Connect scanmode_i and scan_rst_ni at every instance. Without a scan flow, tie scanmode_i=1'b0 and scan_rst_ni=1'b1.
//   - Keep scanmode_i quasi-static. Set it before the first test clock edge. Do not toggle it while clk_i runs.
//   - In scan mode the tester owns the timing of the scan_rst_ni release.
// Doc: ds:mod:cdc-reset-sync, tm:mod:cdc-reset-sync, cr:mod:cdc-reset-sync

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

    // STAGES must be at least 2. The $fatal runs at elaboration, outside an `initial` block.
    if (STAGES < 2) begin : g_stages_check
        $fatal(1, "cdc_reset_sync: STAGES (%0d) must be >= 2", STAGES);
    end

    // Input mux: scan_rst_ni replaces rst_n_i as the chain's async clear in
    // scan mode (see ds:mod:cdc-reset-sync). Scanmode low => rst_n_async === rst_n_i.
    logic rst_n_async;
    assign rst_n_async = scanmode_i ? scan_rst_ni : rst_n_i;

    // One always_ff PER STAGE (genvar generate), packed vector storage.
    // Functionally: shift a '1' in at stage 0 every cycle out of reset, i.e.
    // equivalent to `sync_q <= {sync_q[STAGES-2:0], 1'b1}` with async clear.
    // Use one always_ff per stage. A loop in one always_ff gives a false SYNCASYNCNET warning.
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
    // independent of the chain flops (see ds:mod:cdc-reset-sync). Scanmode low =>
    // rst_n_o === sync_q[STAGES-1], the original output.
    assign rst_n_o = scanmode_i ? scan_rst_ni : sync_q[STAGES-1];

endmodule : cdc_reset_sync
