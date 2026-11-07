#!/bin/bash
# StarRC nom/min/max for Innovus b5h (arm innovusb5h), strictly one at a time; skips corners already complete.
cd "$(dirname "$0")/.."
for c in nom min max; do
  [ -f runs/innovusb5h_$c/star/.starrc_complete ] && continue
  ../../impl/innovus/scripts/gate_host.sh || exit 1
  echo "$(date +%T) start starrc $c"; scripts/run_starrc.sh innovusb5h $c > runs/innovusb5h_$c.out 2>&1; echo "$(date +%T) end starrc $c rc=$?"
done
