#!/bin/bash
# wait_licensed_idle.sh -- block until no other licensed EDA tool runs on this host (one licensed tool at a time, host rule).  pgrep -x only.
# Idle must hold across a random 25-95 s settle window (two agents polling the same condition otherwise launch in the same 30 s tick).
busy() { pgrep -x "icc2_shell|icc2_exec|innovus|fm_shell|StarXtract|pt_shell|lec|lec_64|genus|dc_shell|quantus|calibre" >/dev/null; }
while true; do
  while busy; do sleep 30; done
  sleep $((25 + RANDOM % 70))
  busy || break
done
