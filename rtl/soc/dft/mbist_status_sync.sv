// mbist_status_sync - MBIST status block, destination domain to TCK.
//
// Function: Every status bit crosses through its own 2-FF cdc_sync with WIDTH = 1.
//   done and busy pass through one extra TCK flop. The controller freezes the data bits before it raises done.
//   When the tester sees done = 1, every data bit has had a full TCK period to settle.
//   A capture with done = 0 can show data that is mid-update.
// Parameters: ST_W is the width of the status.
// Clocks and resets: tck_i is the clock. rst_tck_n_i is the reset.
// Caller rules: The source bits must be flop outputs of mbist_ctrl, or selects over flops that change only on rd_sel changes.
//   The tester must follow the >= 3 TCK settle rule after a change of rd_sel.
// Doc: ds:mod:mbist-status-sync

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
