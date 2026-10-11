// `leaky` leaves its result unassigned when c == 0, and that x reaches the output port.
// A gate that exempted every `$func$` net by name would hide exactly this.
module functemp_unassigned (
    input  [3:0] a,
    input        s,
    output [3:0] ya,
    output [3:0] yb
);
  function [3:0] fine(input [3:0] v, input c);
    reg [3:0] t;
    begin
      t = 4'd0;
      if (c) t = v;
      fine = t;
    end
  endfunction
  function [3:0] leaky(input [3:0] v, input c);
    if (c) leaky = v;
  endfunction
  assign ya = fine(a, s);
  assign yb = leaky(a, s);
endmodule
