// Models for check_scan_clk_rst.py on the ASAP7 SoC netlist (pnr/asap7/soc/soc_top_sv2v.v), which instantiates
// two things it does not define. Analysis only: never part of any synthesis or simulation file list.
//
//   ICGx1_ASAP7_75t_R  library integrated clock gate. The latch is transparent while CLK is low and its D input
//                      is ENA | SE, exactly the structure rv32i_clock_gate's behavioural arm builds, so the
//                      checker can see that the enable cone contains the scan-mode term (SE = test_en).
//   sram_1rw_256x32_asap7  hard macro; only its port directions matter (dout0 is an output, nothing else is).
module ICGx1_ASAP7_75t_R (
    input  CLK,
    input  ENA,
    input  SE,
    output GCLK
);
  reg en_l;
  always @* if (!CLK) en_l = ENA | SE;
  assign GCLK = CLK & en_l;
endmodule

(* blackbox *)
module sram_1rw_256x32_asap7 (
    input         clk0,
    input         csb0,
    input         web0,
    input  [7:0]  addr0,
    input  [31:0] din0,
    output [31:0] dout0
);
endmodule
