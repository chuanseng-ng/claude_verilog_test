#!/bin/bash
cd /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/commercial/signoff/pt/runs_diag_b5g
while ! grep -q CHAIN1_DONE chain1.log; do sleep 10; done
S=scripts/run_g.sh
$S e5_natexact_nat /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/commercial/signoff/pt/runs_diag_b5g/sdc/natexact.sdc /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/commercial/impl/innovus/runs/b5g_innovus/out/rv32i_cpu_top.innovus_native.spef
$S e6_natexact_star /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/commercial/signoff/pt/runs_diag_b5g/sdc/natexact.sdc /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/commercial/signoff/starrc/runs/innovus_nom/rv32i_cpu_top.nom.spef
$S e0b_base_star_part /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/commercial/signoff/starrc/runs/innovus_nom/rv32i_cpu_top.nom.spef
echo CHAIN2_DONE
