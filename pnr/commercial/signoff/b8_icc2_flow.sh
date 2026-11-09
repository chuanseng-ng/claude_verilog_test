#!/bin/bash
# b8_icc2_flow.sh -- ICC2 b8 after the route stage: deck antenna on the routed DEF -> ECO lists (StarRC + PT judge on the pre-ECO netlist) -> b8_06_eco (hold + dout0 + antenna diodes) -> finish -> write_verilog.
# Resumable (b8_chain.sh markers; b8_lists.sh markers; signoff/b8_icc2_flow/*.done).  Verification afterwards: wait_then_b8.sh icc2 -> chain_b8_all.sh icc2.
cd "$(dirname "$0")"; M=b8_icc2_flow; mkdir -p $M; L=b8_icc2_flow.log
R=../impl/icc2/runs/b8_icc2; LK=../pdk/sky130/scripts/licensed_lock.sh
until [ -f $R/markers/b8_05b_write.done ]; do sleep 60; done
if [ ! -f $M/antenna_route.done ]; then
  cp $R/out/pre_ant.def $R/out/pre_ant_route.def; mkdir -p drclvs/runs/icc2_b8route/logs
  $LK make -C drclvs ARM=icc2_b8route PIN_MODE=none antenna > drclvs/runs/icc2_b8route/logs/make_antenna.log 2>&1
  python3 -I ../impl/icc2/scripts/ant_pins.py drclvs/reports/icc2_b8route_antenna.rpt $R/eco_in/ant_pins.txt >> $L 2>&1; echo $? > $M/antenna_route.done
fi
./b8_lists.sh icc2
cp ../impl/icc2/runs/b8_icc2/eco_in/*.txt /dev/null 2>&1
echo "$(date +%T) lists done: dout0 $(wc -l < $R/eco_in/dout0_all.txt), hold $(wc -l < $R/eco_in/hold_endpoints.txt), ant $(wc -l < $R/eco_in/ant_pins.txt)" >> $L
B8_STAGES="b8_06_eco b8_07_finish b8_08_write_verilog" ../impl/icc2/scripts/b8_chain.sh
echo "$(date +%T) b8_icc2_flow done" >> $L
