#!/bin/bash
# chain_apl.sh <static|dynamic|dynamic-nodecap> <arm> [<arm> ...] -- STEP 8 RedHawk re-run, sequential, .done markers (rh-apl-<mode>/.done), 60 s gap, load gate.  Rerun skips finished arms.
mode=$1; shift
cd "$(dirname "$0")/.." || exit 1
for a in "$@"; do
  if [ -f runs/$a/rh-apl-$mode/.done ]; then echo "skip $a"; continue; fi
  while [ "$(awk '{printf "%d",$1}' /proc/loadavg)" -ge 6 ]; do sleep 20; done
  bash scripts/run_redhawk_apl.sh $a $mode > runs/${a}_apl_$mode.driver.log 2>&1
  if grep -q "Finish RedHawk \(Static\|Dynamic\) Flow\|Finish Dynamic" runs/$a/rh-apl-$mode/redhawk.log; then touch runs/$a/rh-apl-$mode/.done; echo "done $a $mode $(date +%T)"; else echo "FAILED $a $mode $(date +%T)"; fi
  sleep 60
done
echo CHAIN_DONE
