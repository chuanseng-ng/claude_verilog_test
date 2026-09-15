#!/usr/bin/env bash
# cleanup_runs.sh — prune old LibreLane run directories under /nobackup.
#
# Cron-driven replacement for the original /nobackup/cleanup_runs.sh, which was
# lost in the 2026-09-15 drive reorg (bead alq). It now lives in the repo so a
# wipe of /nobackup cannot take it out again.
#
# Policy per runs directory (same as pnr/Makefile's prune_runs):
#   - keep the newest MAX_RUNS RUN_* directories;
#   - never delete a run carrying a .signoff marker;
#   - additionally, never delete a run modified within MIN_AGE_MIN minutes, so
#     a flow still writing into an older-named directory is left alone.
#
# Usage:  cleanup_runs.sh [--dry-run]
# Env:    NOBACKUP_ROOT (default /nobackup), MAX_RUNS (default 10),
#         MIN_AGE_MIN (default 360)
#
# Example crontab:
#   */15 * * * * <repo>/tools/setup/cleanup_runs.sh >> /nobackup/cleanup_runs.log 2>&1
set -euo pipefail

NOBACKUP_ROOT="${NOBACKUP_ROOT:-/nobackup}"
MAX_RUNS="${MAX_RUNS:-10}"
MIN_AGE_MIN="${MIN_AGE_MIN:-360}"
DRY_RUN=0

case "${1:-}" in
  --dry-run) DRY_RUN=1 ;;
  "") ;;
  *) echo "usage: $0 [--dry-run]" >&2; exit 2 ;;
esac

if ! [[ "$MAX_RUNS" =~ ^[0-9]+$ && "$MIN_AGE_MIN" =~ ^[0-9]+$ ]]; then
  echo "ERROR: MAX_RUNS and MIN_AGE_MIN must be non-negative integers" >&2
  exit 2
fi

# Refuse to run against an unmounted mountpoint: that would prune nothing useful
# and hides a missing disk.
if ! mountpoint -q "$NOBACKUP_ROOT"; then
  echo "$(date '+%F %T') ERROR: $NOBACKUP_ROOT is not a mountpoint; skipping" >&2
  exit 1
fi

# Only the expected run layouts; anything else under /nobackup is left alone.
shopt -s nullglob
RUNS_DIRS=("$NOBACKUP_ROOT"/*_runs "$NOBACKUP_ROOT"/pnr_macros/*/*_runs)

total_deleted=0
for runs_dir in "${RUNS_DIRS[@]}"; do
  [[ -d "$runs_dir" && ! -L "$runs_dir" ]] || continue

  # Newest first, by modification time.
  mapfile -t runs < <(ls -dt "$runs_dir"/RUN_* 2>/dev/null || true)
  (( ${#runs[@]} > MAX_RUNS )) || continue

  for run in "${runs[@]:MAX_RUNS}"; do
    [[ -d "$run" && ! -L "$run" ]] || continue
    if [[ -e "$run/.signoff" ]]; then
      echo "$(date '+%F %T') keep (signoff): $run"
      continue
    fi
    if [[ -n "$(find "$run" -maxdepth 2 -newermt "-${MIN_AGE_MIN} minutes" -print -quit 2>/dev/null)" ]]; then
      echo "$(date '+%F %T') keep (recent activity): $run"
      continue
    fi
    if (( DRY_RUN )); then
      echo "$(date '+%F %T') would delete: $run"
    else
      echo "$(date '+%F %T') delete: $run"
      rm -rf -- "$run"
    fi
    total_deleted=$((total_deleted + 1))
  done
done

if (( total_deleted > 0 )); then
  echo "$(date '+%F %T') done: $total_deleted run(s) $( ((DRY_RUN)) && echo 'eligible' || echo 'deleted')"
fi
