#!/bin/bash
# gate_host.sh -- block until the host can take a licensed PD tool: no heavy DRC/LVS job from the other agent (any magic; klayout RSS > 4 GB), MemAvailable > 6 GB.
for i in $(seq 1 720); do
  avail=$(awk '/MemAvailable/{printf "%d", $2/1048576}' /proc/meminfo)
  heavy=0
  pgrep -x magic >/dev/null && heavy=1
  for p in $(pgrep -x klayout); do r=$(awk '/VmRSS/{printf "%d",$2/1048576}' /proc/$p/status 2>/dev/null); [ "${r:-0}" -ge 4 ] && heavy=1; done
  for t in innovus innovus_exec icc2_shell pt_shell StarXtract; do pgrep -x $t >/dev/null && heavy=1; done
  [ $heavy = 0 ] && [ "$avail" -ge 6 ] && exit 0
  sleep 30
done
echo "gate_host: host never cleared" >&2; exit 1
