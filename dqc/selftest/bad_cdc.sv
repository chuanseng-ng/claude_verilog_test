// bad_cdc.sv - DQC negative/positive control. Deliberately broken; never part of any RTL list.
//
//   bad_data_q  : a clk_a flop captured DIRECTLY by a clk_b flop (no synchroniser)     -> CDC violation
//   ok_data_q   : the same crossing through a 2-flop synchroniser                       -> must NOT be flagged
//   bad_rst_q   : a clk_a-domain flop's output is the ASYNC reset of a clk_b flop        -> RDC violation
// `make -C dqc selftest` fails unless SpyGlass reports the bad crossings and spares the good one.
module bad_cdc (
    input  logic clk_a,
    input  logic clk_b,
    input  logic rst_a_n,
    input  logic rst_b_n,
    input  logic d_i,
    output logic bad_o,
    output logic ok_o,
    output logic rdc_o
);
    logic src_q;
    always_ff @(posedge clk_a or negedge rst_a_n)
        if (!rst_a_n) src_q <= 1'b0; else src_q <= d_i;

    // BAD: unsynchronised clk_a -> clk_b
    logic bad_data_q;
    always_ff @(posedge clk_b or negedge rst_b_n)
        if (!rst_b_n) bad_data_q <= 1'b0; else bad_data_q <= src_q;
    assign bad_o = bad_data_q;

    // GOOD: 2-flop synchroniser
    logic s1_q, ok_data_q;
    always_ff @(posedge clk_b or negedge rst_b_n)
        if (!rst_b_n) begin s1_q <= 1'b0; ok_data_q <= 1'b0; end
        else begin s1_q <= src_q; ok_data_q <= s1_q; end
    assign ok_o = ok_data_q;

    // BAD (RDC): clk_a-domain register drives the async reset of a clk_b register
    logic soft_rst_q;
    always_ff @(posedge clk_a or negedge rst_a_n)
        if (!rst_a_n) soft_rst_q <= 1'b0; else soft_rst_q <= d_i;
    logic bad_rst_q;
    always_ff @(posedge clk_b or negedge soft_rst_q)
        if (!soft_rst_q) bad_rst_q <= 1'b0; else bad_rst_q <= ok_data_q;
    assign rdc_o = bad_rst_q;
endmodule
