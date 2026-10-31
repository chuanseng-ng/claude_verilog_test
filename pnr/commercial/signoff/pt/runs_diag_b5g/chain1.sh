#!/bin/bash
cd /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/commercial/signoff/pt/runs_diag_b5g
S=scripts/run_g.sh
$S e0_base_star /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/commercial/signoff/starrc/runs/innovus_nom/rv32i_cpu_top.nom.spef G_POWER=1 G_TOGGLE=0.1
$S e1_natlat_star /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/commercial/signoff/pt/runs_diag_b5g/sdc/natlat.sdc /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/commercial/signoff/starrc/runs/innovus_nom/rv32i_cpu_top.nom.spef
$S e2_natlat_nat /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/commercial/signoff/pt/runs_diag_b5g/sdc/natlat.sdc /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/commercial/impl/innovus/runs/b5g_innovus/out/rv32i_cpu_top.innovus_native.spef
$S e3_base_nat /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/commercial/impl/innovus/runs/b5g_innovus/out/rv32i_cpu_top.innovus_native.spef
$S e4_base_star_t02 /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc /home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/commercial/signoff/starrc/runs/innovus_nom/rv32i_cpu_top.nom.spef G_POWER=1 G_TOGGLE=0.2
echo CHAIN1_DONE
