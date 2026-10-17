// mbist_status_sync.sv
// DFT Stage 4 (bead claude_verilog_test-j41m.14, GH #244): MBIST status block, destination domain
// -> TCK. Specification: docs/design/DFT_ARCHITECTURE.md section 16.5 ("Status return crossing").
//
// Every status bit crosses through its OWN 2-FF cdc_sync (WIDTH = 1 per instance: the primitive's scope
// note forbids multi-bit buses, and the bits carry no word coherency requirement of their own). The
// controller freezes every bit except done/busy before it raises done, so the coherency is provided by
// ORDER, not by the synchronisers: `done` and `busy` pass through ONE EXTRA TCK flop, so when the
// tester sees done = 1 every data bit has had a full TCK period to settle. A capture with done = 0
// shows data that may be mid-update; that is the documented meaning of "not done".
//
// The source bits are flop outputs of mbist_ctrl (status_o is a concatenation of flops and of
// combinational selects over flops; the selects only change on rd_sel changes, a quasi-static
// tester action with the documented >= 3 TCK settle rule).
//
// Lint target: verilator -Wall -Wno-IMPORTSTAR 0 errors 0 warnings.

module mbist_status_sync #(
    parameter int unsigned ST_W = 69
) (
    input  logic            tck_i,
    input  logic            rst_tck_n_i,
    input  logic [ST_W-1:0] status_i,        // destination-domain status block (bit0 done, bit1 busy)
    output logic [ST_W-1:0] status_tck_o
);

    logic [ST_W-1:0] sync_w;

    genvar gb;
    generate
        for (gb = 0; gb < ST_W; gb++) begin : g_bit
            cdc_sync #(
                .WIDTH  (1),
                .STAGES (2)
            ) u_sync (
                .clk_i   (tck_i),
                .rst_n_i (rst_tck_n_i),
                .d_i     (status_i[gb]),
                .q_o     (sync_w[gb])
            );
        end
    endgenerate

    logic [1:0] db_q;   // done / busy delayed by one more TCK cycle

    always_ff @(posedge tck_i or negedge rst_tck_n_i) begin
        if (!rst_tck_n_i) begin
            db_q <= 2'b00;
        end else begin
            db_q <= sync_w[1:0];
        end
    end

    assign status_tck_o = {sync_w[ST_W-1:2], db_q};

endmodule : mbist_status_sync
