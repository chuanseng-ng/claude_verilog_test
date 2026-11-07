#!/bin/bash
# gate_licensed.sh -- ONE licensed EDA tool at a time on this host: block (single long loop) until none of icc2_shell fm_shell StarXtract pt_shell innovus lec is running,
# then apply the usual memory gate (gate_host.sh).  Zombies are ignored.  Race window between this check and the launch is accepted.
for i in $(seq 1 2880); do
  busy=0
  for t in icc2_shell fm_shell StarXtract pt_shell innovus innovus_exec lec; do
    for p in $(pgrep -x $t); do st=$(awk '/^State/{print $2}' /proc/$p/status 2>/dev/null); [ -n "$st" ] && [ "$st" != Z ] && busy=1; done
  done
  [ $busy = 0 ] && break
  sleep 30
done
[ $busy = 0 ] || { echo "gate_licensed: host never cleared" >&2; exit 1; }
exec "$(dirname "$0")/gate_host.sh"
