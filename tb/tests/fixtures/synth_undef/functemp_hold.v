// Calls made inside an `if` of a combinational block.  For the branch where the call is not made,
// proc re-assigns the function's own wire to itself ("hold"), a read of the x-initialised wire whose
// value only feeds other dead x-initialised temporaries (cast4, the shape of the SoC's sv2v_cast_*).
// `leaky2` additionally leaves its result unassigned on a path and that value reaches output z.
module functemp_hold (
    input  [3:0] a,
    input        sel,
    input        c,
    output reg [3:0] y,
    output reg [3:0] z
);
  function [3:0] cast4(input [3:0] inp);
    cast4 = inp;
  endfunction
  function [3:0] leaky2(input [3:0] v, input cc);
    if (cc) leaky2 = v;
  endfunction
  always @* begin
    y = 4'd0;
    if (sel) y = cast4(a);
    z = 4'd0;
    if (sel) z = leaky2(a, c);
  end
endmodule
