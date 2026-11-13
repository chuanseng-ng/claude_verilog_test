#!/bin/bash
# step4b_master.sh -- unattended, idempotent driver of cleanup step 4b (SoC-context input budgets).  RESUME = re-run:
#   cd pnr/commercial/signoff && setsid nohup ./step4b_master.sh > step4b_master.stdout 2>&1 < /dev/null &
# Do NOT start a second copy while `pgrep -af step4b_maste[r]` shows one.  Markers: step4b_master/<step>.done; log step4b_master.log.
# Steps: dc (soc_budget/scripts/run_dc.sh) -> arrival (run_pt_arrival.sh, tt/ss/ff serial) -> budget (mk_budget.py) -> sdc (gen_soc_budget_sdc.py)
#        -> chain (chain_soc_budget.sh: 27 PT runs serial) -> snapshot (snapshot_sources.py --only-soc) -> compare (compare.py).
# Only licensed tools go through licensed_lock.sh (inside the called scripts).  Never run pt_shell probes outside it.
cd "$(dirname "$0")"; M=step4b_master; mkdir -p $M; L=step4b_master.log
S=soc_budget/scripts; R=$(cd ../../.. && pwd)
step() { n=$1; shift; [ -f $M/$n.done ] && { echo "$(date +%T) skip $n" >> $L; return; }
  echo "$(date +%T) start $n" >> $L; "$@" > $M/$n.out 2>&1; rc=$?; echo "$(date +%T) end $n rc=$rc" >> $L; [ $rc = 0 ] && echo 0 > $M/$n.done || { echo "step $n failed rc=$rc" >> $L; exit $rc; }; }
# an arrival run already in flight (started by hand) is waited for, never duplicated
while pgrep -f "run_pt_arriva[l].sh" >/dev/null; do sleep 15; done
[ -s soc_budget/runs/dc/out/async_axi_fifo.mapped.v ] && [ -s soc_budget/runs/dc/out/apb_cdc_bridge.mapped.v ] && echo 0 > $M/dc.done
step dc $S/run_dc.sh
[ -s soc_budget/runs/dc/arrival_tt.tsv ] && [ -s soc_budget/runs/dc/arrival_ss.tsv ] && [ -s soc_budget/runs/dc/arrival_ff.tsv ] && echo 0 > $M/arrival.done
step arrival $S/run_pt_arrival.sh
step budget python3 -I $S/mk_budget.py
step sdc python3 -I ../constraints/gen_soc_budget_sdc.py
step chain ./chain_soc_budget.sh
step snapshot python3 -I ../compare/snapshot_sources.py --only-soc
step compare python3 -I ../compare/compare.py
echo "$(date +%T) step4b_master done" >> $L
