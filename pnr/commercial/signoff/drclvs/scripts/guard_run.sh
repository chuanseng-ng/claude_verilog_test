#!/bin/bash
# guard_run.sh <logfile> <container-name> <cmd...>
# safe_run.sh (load/mem wait, process-group time watchdog) + scripts/watchdog.sh (low-overhead MemAvailable / container-RSS watchdog that
# `podman kill`s the container; podman is queried once for the PID, then /proc is polled every 10 s). safe_run's MemoryMax and podman
# --memory are not enforced on this cgroup-v1 host, hence the watchdog.
# Env: SAFE_TIMEOUT (s), SAFE_MIN_AVAIL_GB (start gate, whole GiB truncated), SAFE_MAX_LOAD, GUARD_MIN_GB (default 1.5), GUARD_RSS_GB (default 9)
set -u
log=$1; name=$2; shift 2
here=$(cd "$(dirname "$0")" && pwd)
SAFE=${SAFE_RUN:-$here/../../../pdk/sky130/scripts/safe_run.sh}
: > "$log.guard"
"$here/watchdog.sh" "$name" "$log.guard" "${GUARD_MIN_GB:-1.5}" "${GUARD_RSS_GB:-9}" 10 &
gpid=$!
start=$(date +%s)
"$SAFE" "$log" "$@"
rc=$?
kill $gpid 2>/dev/null; wait $gpid 2>/dev/null
echo "guard_run: rc=$rc wall=$(( $(date +%s)-start ))s" >> "$log.guard"
exit $rc
