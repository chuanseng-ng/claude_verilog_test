#!/bin/bash
# chain_equiv.sh -- gate = diode/physical-stripped OpenROAD FINAL netlist (end-to-end), then 4 negative controls (mutants of the final netlist); one run at a time, resumable (CHAIN_DONE per tag)
H=/home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/commercial/signoff/lec
Y=$H/yosys; F=$H/formality/runs
cd $Y
for spec in "e5_final:$F/or_nodiode.nl.v" "e6_neg_fwdb_inv:$F/mutant_or_fwdb_inv.nl.v" "e7_neg_swap:$F/mutant_or_swap.nl.v" "e8_neg_bufinv:$F/mutant_or_bufinv.nl.v" "e9_neg_tiehi:$F/mutant_or_tiehi.nl.v"; do
  tag=${spec%%:*}; nl=${spec#*:}
  [ -f runs/$tag/CHAIN_DONE ] && continue
  bash scripts/run_equiv.sh $tag $nl
  sleep 60
done
touch runs/CHAIN_EQUIV_COMPLETE
