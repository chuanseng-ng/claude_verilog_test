#!/bin/bash
# chain_b5k_captbl.sh -- b5k step 8: min and max Innovus capTables (same li1->met0 ICT trick, scripts/mk_ict_li1m1.py; no Techgen/Quantus), one Innovus at a time under the host-wide flock.
# Starts only after the b5j PT judge chain has finished (round 2 is queued behind b5j).  ~50-60 min per corner on a quiet host.
cd "$(dirname "$0")/.."
LOCK=/tmp/claude-1001/licensed_tool.lock
SIGN=../../signoff
until grep -q "end PT chain" $SIGN/chain_b5j_all.log 2>/dev/null; do sleep 60; done
for c in ${CORNERS:-min max}; do
  [ -s captbl6/sky130A_${c}_li1m1.captbl ] && continue
  echo "$(date +%T) wait lock captbl $c" >> captbl6/chain_b5k.log
  flock $LOCK bash -c "scripts/gate_host.sh || exit 1; echo \"\$(date +%T) start captbl $c\" >> captbl6/chain_b5k.log; scripts/run_captbl6.sh $c > captbl6/run_$c.out 2>&1; echo \"\$(date +%T) end captbl $c rc=\$?\" >> captbl6/chain_b5k.log"
done
