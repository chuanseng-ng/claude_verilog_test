// Repro for a Verilator coverage-tool limitation (GH #222, bead kp61; Verilator 5.048).
//
// Verilator never increments the arm counters of an if / else-if / else chain whose arms are
// `return` statements inside a FUNCTION.  f_ret() below is called with all four inputs and
// returns the right values, yet every `--coverage-line` point on its if/elsif/else arms reads 0;
// f_asg() is the same chain assigning the function name, and counts normally.
//
// This is why tools/verif/coverage_waivers.txt waives axi4_to_axilite worse_resp() L150/L152 and
// sram_controller last_addr() L175 as "unreachable as measured": the logic runs, the counter does
// not.  It is NOT a general "no arm counters inside functions" limit: axi4_crossbar decode()
// (rtl/soc/axi4_crossbar.sv:142) and axi_lite_interconnect decode() (:95) use the assignment form
// and their arms are counted.
//
// Run (needs Verilator; from this directory):
//   verilator --binary --coverage -Wno-fatal --Mdir obj verilator_return_arm.sv --top-module t
//   ./obj/Vt && verilator_coverage --annotate ann coverage.dat && cat ann/verilator_return_arm.sv
// Expected: `%000000` on every f_ret arm, `%000001`/`%000002` on the f_asg arms.
module t;
  logic [1:0] a;
  // function A: if / else-if / else with return (the axi4_to_axilite / sram_controller shape)
  function automatic logic [1:0] f_ret(input logic [1:0] x);
    if (x == 2'd3)
      return 2'd1;
    else if (x == 2'd2)
      return 2'd2;
    else
      return 2'd0;
  endfunction
  // function B: same chain, but assigns the function name instead of return
  function automatic logic [1:0] f_asg(input logic [1:0] x);
    if (x == 2'd3)
      f_asg = 2'd1;
    else if (x == 2'd2)
      f_asg = 2'd2;
    else
      f_asg = 2'd0;
  endfunction
  logic [1:0] ra, rb;
  initial begin
    for (int i = 0; i < 4; i++) begin
      a = 2'(i);
      ra = f_ret(a);
      rb = f_asg(a);
      #1;
    end
    $display("done %0d %0d", ra, rb);
    $finish;
  end
endmodule
