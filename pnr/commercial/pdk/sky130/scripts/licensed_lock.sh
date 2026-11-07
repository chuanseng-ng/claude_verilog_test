#!/bin/bash
# licensed_lock.sh <cmd...> -- run ONE licensed EDA tool at a time, host-wide, race-free.
#   Takes an exclusive flock on $LICENSED_LOCK (default /tmp/claude-1001/licensed_tool.lock) and holds it for the WHOLE lifetime of <cmd>
#   (the lock fd is inherited by the child, so it is released only when the tool and everything it spawned has exited or the kernel closes the fd).
#   While waiting it also waits (pgrep -x, 1 s poll) for licensed tools started by callers that do NOT use the lock yet, so adoption can be gradual.
#   Wrap the tool launch, e.g.  licensed_lock.sh .../safe_run.sh log.txt innovus ...   or   licensed_lock.sh impl/icc2/scripts/run_stage.sh 05i_eco b5i_icc2
LOCK=${LICENSED_LOCK:-/tmp/claude-1001/licensed_tool.lock}
mkdir -p "$(dirname "$LOCK")"
exec 9>>"$LOCK"
flock -x 9 || exit 99
busy() { pgrep -x "icc2_shell|icc2_exec|innovus|fm_shell|StarXtract|pt_shell|lec|lec_64|genus|dc_shell|quantus|calibre" >/dev/null; }
while busy; do sleep 1; done
echo "$(date +%FT%T) licensed_lock: acquired by pid $$ for: $*" >> "$LOCK.log"
"$@"; rc=$?
echo "$(date +%FT%T) licensed_lock: released (rc=$rc) pid $$" >> "$LOCK.log"
exit $rc
