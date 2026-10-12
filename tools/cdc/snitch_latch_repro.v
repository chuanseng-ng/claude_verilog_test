// Minimal reproducer for cdc_snitch "BAD magic" on a latch-driven synchroniser.
// Four sources in clock domain A feed a 2-FF synchroniser in domain B:
//   ctl : A flop Q                                  -> expect CDC (clean)
//   lat : latch(E=~clk_a, D=A flop Q)               -> single-domain latch, expect ?
//   and2: AND of two A flops                        -> any 2-input logic, expect ?
//   lat2: latch Q registered by an A flop           -> expect CDC (fix candidate)
module sync2 (input wire clk, input wire d, output wire q);
    (* magic_cdc *) reg s0;
    reg s1;
    always @(posedge clk) begin s0 <= d; s1 <= s0; end
    assign q = s1;
endmodule

module top (input wire clk_a, input wire clk_b, input wire x, input wire y,
            output wire q_ctl, output wire q_lat, output wire q_and, output wire q_lat2);
    reg fa, fb;
    always @(posedge clk_a) begin fa <= x; fb <= y; end

    // control: flop output straight into the synchroniser
    sync2 u_ctl (.clk(clk_b), .d(fa), .q(q_ctl));

    // latch, transparent while clk_a is low, D from an A-domain flop
    reg lat;
    always @* if (!clk_a) lat = fa;
    sync2 u_lat (.clk(clk_b), .d(~lat), .q(q_lat));

    // plain 2-input logic of two A-domain flops
    sync2 u_and (.clk(clk_b), .d(fa & fb), .q(q_and));

    // the latch value registered by an A-domain flop first
    reg lat_r;
    always @(posedge clk_a) lat_r <= lat;
    sync2 u_lat2 (.clk(clk_b), .d(lat_r), .q(q_lat2));
endmodule
