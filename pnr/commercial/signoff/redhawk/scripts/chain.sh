#!/bin/bash
# chain.sh <static|dynamic> -- RedHawk for the three arms, sequential, done markers (.done), 60 s gap, load gate.  Rerun skips finished arms.
mode=$1
cd "$(dirname "$0")/.." || exit 1
for a in icc2b6 innovusb6 openroad; do
  if [ -f runs/$a/rh-$mode/.done ]; then echo "skip $a"; continue; fi
  while [ "$(awk '{printf "%d",$1}' /proc/loadavg)" -ge 6 ]; do sleep 20; done
  bash scripts/run_redhawk.sh $a $mode > runs/${a}_$mode.driver.log 2>&1
  if grep -q "Finish RedHawk \(Static\|Dynamic\) Flow\|Finish Dynamic" runs/$a/rh-$mode/redhawk.log; then touch runs/$a/rh-$mode/.done; echo "done $a $(date +%T)"; else echo "FAILED $a $(date +%T)"; fi
  sleep 60
done
echo CHAIN_DONE
