// mbist_ctl_hold - holding register of the MBIST control word in the destination domain.
//
// Function: The register holds a control word of CTL_W bits and loads it when load_i is 1. mbist_xing uses it.
//   It is a module of its own so that a check can name it as one of the only two cells that read the TCK-domain FIFO storage.
// Clocks and resets: clk_i is the destination clock. rst_n_i is the reset.
// Doc: ds:mod:mbist-ctl-hold

module mbist_ctl_hold #(
    parameter int unsigned CTL_W = 29
) (
    input  logic             clk_i,
    input  logic             rst_n_i,
    input  logic             load_i,
    input  logic [CTL_W-1:0] d_i,
    output logic [CTL_W-1:0] q_o
);

    logic [CTL_W-1:0] ctl_q;

    always_ff @(posedge clk_i or negedge rst_n_i) begin
        if (!rst_n_i) begin
            ctl_q <= '0;
        end else if (load_i) begin
            ctl_q <= d_i;
        end
    end

    assign q_o = ctl_q;

endmodule : mbist_ctl_hold
