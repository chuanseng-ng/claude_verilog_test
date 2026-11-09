#!/bin/bash
# b8r2_flow.sh -- b8 ECO round 2 for both arms (residual deck antenna sinks; ICC2 also 2 dout0 pins at the max RC corner and the native DRC=1), then a full re-run of the b8 verification chains on the new layouts.
# Resumable.  ICC2: b8_chain.sh stages b8_06b_eco b8_07_finish b8_08_write_verilog with B5E_FINISH_BASE=06b_eco; Innovus: chain_inn_b8r2.sh.
cd "$(dirname "$0")"; M=b8r2; mkdir -p $M; L=b8r2.log
until [ -f step4_fixups/pv.done ]; do sleep 60; done   # do not touch the b8 layouts while the pv redo of step4_fixups.sh still reads them
R=../impl/icc2/runs/b8_icc2
if [ ! -f $M/icc2.done ]; then
  rm -f $R/markers/b8_07_finish.done $R/markers/b8_08_write_verilog.done
  B8_STAGES="b8_06b_eco b8_07_finish b8_08_write_verilog" B5E_FINISH_BASE=06b_eco ../impl/icc2/scripts/b8_chain.sh; echo $? > $M/icc2.done
  echo "$(date +%T) icc2 round 2 done: $(tail -1 $R/reports/chain.log)" >> $L
fi
if [ ! -f $M/innovus.done ]; then ../impl/innovus/scripts/chain_inn_b8r2.sh; echo $? > $M/innovus.done; echo "$(date +%T) innovus round 2 done" >> $L; fi
for d in chain_b8_icc2 chain_b8_innovus; do rm -f $d/*.done; done
./chain_b8_all.sh icc2; ./chain_b8_all.sh innovus
echo "$(date +%T) b8r2 verification chains done" >> $L
