#!/bin/bash
# watchdog.sh <container> <logfile> [min_avail_gb=1.5] [rss_max_gb=9] [poll_s=10]
# Low-overhead memory watchdog: `podman kill` the container when MemAvailable < min_avail_gb, or when the container main process RSS
# exceeds rss_max_gb. Looks up the container PID ONCE (podman inspect), caches it, re-queries only when the cached PID is gone (at most
# every 30 s); polls /proc only, every poll_s seconds (>= 10). Never calls podman in a tight loop (an earlier version ran
# `podman inspect` every 3 s and burned ~1 CPU).
name=$1; log=$2; minav=${3:-1.5}; rssmax=${4:-9}; poll=${5:-10}
[ "$poll" -lt 10 ] && poll=10
pid=; lastq=0
while sleep "$poll"; do
  avail_kb=$(awk '/MemAvailable/{print $2; exit}' /proc/meminfo)
  if awk -v a="$avail_kb" -v m="$minav" 'BEGIN{exit !(a/1048576 < m)}'; then
    echo "watchdog: MemAvailable $(awk -v a=$avail_kb 'BEGIN{printf "%.2f",a/1048576}') GiB < ${minav} -> podman kill $name" >> "$log"
    podman kill "$name" >/dev/null 2>&1; exit 0
  fi
  if [ -z "$pid" ] || [ ! -d "/proc/$pid" ]; then
    now=$(date +%s)
    if [ $((now-lastq)) -ge 30 ]; then lastq=$now; pid=$(podman inspect -f '{{.State.Pid}}' "$name" 2>/dev/null); [ "$pid" = 0 ] && pid=; fi
  fi
  if [ -n "$pid" ] && [ -r "/proc/$pid/status" ]; then
    rss=$(awk '/^VmRSS:/{print $2; exit}' "/proc/$pid/status" 2>/dev/null)
    if [ -n "$rss" ] && awk -v r="$rss" -v m="$rssmax" 'BEGIN{exit !(r/1048576 > m)}'; then
      echo "watchdog: container RSS $(awk -v r=$rss 'BEGIN{printf "%.2f",r/1048576}') GiB > ${rssmax} -> podman kill $name" >> "$log"
      podman kill "$name" >/dev/null 2>&1; exit 0
    fi
  fi
done
