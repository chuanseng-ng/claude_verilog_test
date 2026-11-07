#!/bin/bash
# chain_all.sh -- Techgen (cell flow) then Quantus on the three b6 DEFs, corner by corner, strictly one licensed tool at a time.
# Resumable: Techgen steps carry .done_<step> markers in build/qrc/<corner>; Quantus runs carry runs/<arm>_<corner>/.done.
# Waits (does not start a second Techgen) when a run_techgen_cell.sh for the corner is already alive.
HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$HERE/../../../../.." && pwd)
SK=$ROOT/pnr/commercial/pdk/sky130
log=$HERE/../runs/chain_all.log; mkdir -p "$HERE/../runs"
say() { echo "$(date -Is) $*" >> "$log"; }
for c in ${CORNERS:-nom min max}; do
  d=$SK/build/qrc/$c
  if [ ! -f "$d/.done_migrate" ]; then
    if pgrep -x run_techgen_cell.sh >/dev/null 2>&1 || [ -n "$(ps -eo args | grep -E '^/bin/bash .*run_techgen_cell.sh '"$c"'$' | grep -v grep)" ]; then
      say "waiting for running Techgen $c"; until [ -f "$d/.done_migrate" ]; do sleep 30; done
    else
      say "START techgen $c"; "$SK/scripts/run_techgen_cell.sh" "$c" >> "$SK/build/logs/techgen_cell_$c.chain.log" 2>&1; rc=$?
      say "END techgen $c rc=$rc"; [ $rc -eq 0 ] || { say "STOP: techgen $c failed"; exit $rc; }
    fi
  fi
  say "techgen $c ready: $(cat "$d/techgen_cell.timing" | tr '\n' ';')"
  for arm in ${ARMS:-icc2b6 innovusb6 openroad}; do
    o=$HERE/../runs/${arm}_$c
    [ -f "$o/.done" ] && { say "skip quantus $arm $c (done)"; continue; }
    sleep 60
    say "START quantus $arm $c"
    SAFE_MIN_AVAIL_GB=6 "$SK/scripts/licensed_lock.sh" "$HERE/run_quantus.sh" "$arm" "$c" >> "$HERE/../runs/${arm}_$c.out" 2>&1; rc=$?
    say "END quantus $arm $c rc=$rc"
    [ $rc -eq 0 ] && tail -c 64 "$o/rv32i_cpu_top.$c.spef" | grep -q '^\*END' && touch "$o/.done" || { say "STOP: quantus $arm $c failed"; exit 1; }
  done
done
say "CHAIN DONE"
