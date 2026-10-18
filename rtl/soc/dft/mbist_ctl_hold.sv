// mbist_ctl_hold.sv
// DFT Stage 4 (bead claude_verilog_test-j41m.10, GH #244).
//
// Destination-domain holding register of the MBIST control word (see mbist_xing.sv). A module of its own so
// tools/dft/check_scan_clk_rst.py --tck-sink can name it as one of the only two cells allowed to read the
// control-word FIFO's TCK-domain storage.
//
// Lint target: verilator -Wall -Wno-IMPORTSTAR 0 errors 0 warnings.

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
