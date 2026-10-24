`timescale 1ns/1ps
module t;
  logic tck=0, a_en=0, clk_b=0, sel_a=0, rst_n=0;
  wire clk_a_o, clk_o, en_a_o, en_b_o;
  tb_dft_clk_switch u(.tck_i(tck),.a_en_i(a_en),.clk_b_i(clk_b),.sel_a_i(sel_a),.rst_n_i(rst_n),.clk_a_o(clk_a_o),.clk_o(clk_o),.en_a_o(en_a_o),.en_b_o(en_b_o));
  always #5 tck=~tck;
  initial begin
    #23 rst_n=1; #40 a_en=1; sel_a=1; #200 a_en=0; #60 sel_a=0; #200 $finish;
  end
  always @(clk_o) $display("%0t clk_o=%b  tck=%b clk_a=%b en_a=%b en_b=%b", $time, clk_o, tck, clk_a_o, en_a_o, en_b_o);
endmodule
