// RTL-side driver (arm 3) for the bead ma7 step-1 branch-dependent regfile
// read-port check: a frontend-independent RTL reference, mirroring u99's
// un-committed tb_verilator_top.v. Wraps the UNMODIFIED tb_cpu_macro_check.v
// with a plain clk/rst generator -- Verilator (unlike yosys's
// `sim -clock/-resetn`) drives its DUT from ordinary Verilog delay
// statements, not from -clock/-resetn command-line ports.
//
// Build (inside `nix develop` at the repo root -- see
// docs project memory reference_verilator_env.md / project_nix_sim_flake.md):
//   [run the] verilator --binary --timing -Wno-fatal -Wno-WIDTH -Wno-CASEINCOMPLETE \
//     --top-module tb_verilator_top_branch \
//     <CPU-only VERILOG_SOURCES from sim/Makefile, SRAM_TARGET=freepdk45> \
//     tools/verif/gls/tb_cpu_macro_check.v \
//     tools/verif/gls/tb_verilator_top_branch.v \
//     -o Vtb_branch --Mdir <builddir>
//   cd <builddir> && ./Vtb_branch    # writes cpu_rtl_branch_out.vcd there
//
// See tools/verif/gls/run_cpu_macro_check_branch_rtl.sh for the exact
// invocation this project uses (nix develop + systemd-run memory cap).
`timescale 1ns/1ps
module tb_verilator_top_branch;
  reg clk_i;
  reg rst_n_i;

  initial clk_i = 1'b0;
  always #5 clk_i = ~clk_i; // 10 ns period, matches other project RTL sims

  initial begin
    rst_n_i = 1'b0;
    #55 rst_n_i = 1'b1;
  end

  // HALT_START_CYC/READ_START_CYC pushed well past this program's single
  // icache-miss redirect + retire so the testbench's own one-shot APB
  // halt/read sequencer (unmodified logic, just later-firing) cannot land
  // mid-flight and freeze the pipeline before it parks at PASS -- see
  // tb_cpu_macro_check.v's header comment on these parameters.
  tb_cpu_macro_check #(
    .HALT_START_CYC(300),
    .READ_START_CYC(340)
  ) dut (
    .clk_i(clk_i),
    .rst_n_i(rst_n_i)
  );

  // 1500 cycles * 10 ns/cycle = 15000 ns, plus reset/margin. Generous
  // headroom: the program has exactly one taken-branch redirect (one I$
  // miss/refill, observed to cost ~19-55 cycles end to end), well inside
  // this budget.
  initial begin
    $dumpfile("cpu_rtl_branch_out.vcd");
    $dumpvars(0, tb_verilator_top_branch);
    #15000;
    $finish;
  end
endmodule
