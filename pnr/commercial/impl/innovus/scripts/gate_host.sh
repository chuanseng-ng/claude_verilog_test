#!/bin/bash
# gate_host.sh -- block until the host can take a licensed PD tool: no heavy DRC/LVS job from the other agent (any magic; klayout RSS > 4 GB), MemAvailable > 6 GB.
MINAV=${GATE_MIN_AVAIL_GB:-6}; LIGHT=${GATE_LIGHT:-0}   # GATE_LIGHT=1: tools with <=1.2 GB RSS (StarRC, pt_shell): only wait for other licensed PD tools and MemAvailable
for i in $(seq 1 720); do
  avail=$(awk '/MemAvailable/{printf "%d", $2/1048576}' /proc/meminfo)
  heavy=0
  [ $LIGHT = 0 ] && pgrep -x magic >/dev/null && heavy=1
  [ $LIGHT = 0 ] && for p in $(pgrep -x klayout); do r=$(awk '/VmRSS/{printf "%d",$2/1048576}' /proc/$p/status 2>/dev/null); [ "${r:-0}" -ge 6 ] && heavy=1; done
  for t in innovus innovus_exec icc2_shell pt_shell StarXtract; do for p in $(pgrep -x $t); do st=$(awk '/^State/{print $2}' /proc/$p/status 2>/dev/null); [ "$st" != Z ] && [ -n "$st" ] && heavy=1; done; done
  [ $heavy = 0 ] && [ "$avail" -ge $MINAV ] && exit 0
  sleep 30
done
echo "gate_host: host never cleared" >&2; exit 1
