// Every function assigns its result on every path.  yosys still gives the function's own
// argument/local/result wires a constant-x "update" (see docs/SYNTH_UNDEF_GATE.md), but nothing reads them.
module functemp_clean (
    input  [3:0] a,
    input  [3:0] b,
    input        s,
    input  [1:0] k,
    output [3:0] ya,
    output [3:0] yb,
    output [3:0] yc,
    output [3:0] yd
);
  function [3:0] init_then_cond(input [3:0] v, input c);
    reg [3:0] t;
    begin
      t = 4'd0;
      if (c) t = v;
      init_then_cond = t;
    end
  endfunction
  function [3:0] loop_acc(input [3:0] v);
    integer i;
    reg [3:0] acc;
    begin
      acc = 4'd0;
      for (i = 0; i < 4; i = i + 1) acc = acc ^ (v << i);
      loop_acc = acc;
    end
  endfunction
  function [3:0] pick(input [1:0] kk, input [3:0] v);
    case (kk)
      2'd0: pick = v;
      2'd1: pick = ~v;
      default: pick = 4'd0;
    endcase
  endfunction
  function [3:0] sv2v_cast_4(input [3:0] inp);
    sv2v_cast_4 = inp;
  endfunction
  assign ya = init_then_cond(a, s);
  assign yb = loop_acc(a);
  assign yc = pick(k, b);
  assign yd = sv2v_cast_4(a ^ b);
endmodule
