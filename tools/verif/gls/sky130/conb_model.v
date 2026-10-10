// Plain constant-cell model used (CONB_FIX=1 in build_arm.sh) in place of the PDK
// sky130_fd_sc_hd__conb_1, whose Verilog uses `pullup`/`pulldown` primitives. In the
// Yosys synthesis-output netlists (tie cells drive output ports / nets directly) Verilator
// resolves those primitives as pulled tri-states, reports "Circular combinational
// logic ... __out__strong__out" and returns 0 for HI, so the CPU never starts. A constant
// cell is exactly HI=1, LO=0.
module dud4_conb (output HI, output LO);
  assign HI = 1'b1;
  assign LO = 1'b0;
endmodule
