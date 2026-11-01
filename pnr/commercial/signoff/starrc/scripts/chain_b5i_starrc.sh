#!/bin/bash
# StarRC nom/min/max for ICC2 b5i (arm icc2b5i), strictly one at a time; skips corners already complete.  Waits for every other licensed tool (gate_licensed.sh).
cd "$(dirname "$0")/.."
for c in ${CORNERS:-nom min max}; do
  [ -f runs/icc2b5i_$c/star/.starrc_complete ] && continue
  GATE_LIGHT=1 ../../impl/innovus/scripts/gate_licensed.sh || exit 1
  echo "$(date +%T) start starrc $c"; scripts/run_starrc.sh icc2b5i $c > runs/icc2b5i_$c.out 2>&1; echo "$(date +%T) end starrc $c rc=$?"
done
