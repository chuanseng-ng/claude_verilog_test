#!/usr/bin/env bash
# Shared helpers for the wrap-*.sh EDA drivers in this directory.
# Sourced, never executed directly.

# shellcheck shell=bash

EDA_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$EDA_DIR/../.." && pwd)"
EDA_LOG_DIR="${EDA_LOG_DIR:-$REPO_ROOT/sim/build/eda-logs}"

# Same cache layout tools/cdc/fetch_cdc_tools.sh populates, so a clone that has
# already run the CDC flow needs no second download.
CDC_CACHE="${CDC_CACHE:-$REPO_ROOT/sim/build/cdc}"
export PATH="$CDC_CACHE/oss-cad-suite/bin:$CDC_CACHE/sv2v-Linux:$PATH"

# eda::need <command> <how-to-get-it>
# Exits 3 (distinct from the wrapper's own PASS/FAIL/ERROR) when the tool is
# absent, with the devshell hint instead of a stack trace.
eda::need() {
  local cmd="$1" hint="$2"
  if ! command -v "$cmd" >/dev/null 2>&1; then
    printf '{\n  "tool": "%s",\n  "status": "ERROR",\n  "exit_code": 3,\n  "summary": {"errors": ["%s not found in PATH — %s"]},\n  "raw_log": null\n}\n' \
      "$cmd" "$cmd" "$hint"
    exit 3
  fi
}

# eda::logfile <tool> -> prints a fresh log path
eda::logfile() {
  mkdir -p "$EDA_LOG_DIR"
  printf '%s/%s-%s-%s.log' "$EDA_LOG_DIR" "$1" "$(date +%Y%m%d-%H%M%S)" "$$"
}

# eda::run <tool> <logfile> -- <command...>
# Runs the command with stdout+stderr teed to the log, then hands the log to
# summarize.py. The wrapper's exit status is summarize.py's verdict, NOT the
# tool's: a tool that exits 0 while reporting violations must still fail here.
eda::run() {
  local tool="$1" log="$2"; shift 2
  [[ "$1" == "--" ]] && shift

  local rc=0
  "$@" >"$log" 2>&1 || rc=$?

  # EDA_SUMMARIZE_EXTRA is an optional array of extra summarize.py flags; expand
  # it only when non-empty so `set -u` does not turn it into an empty argument.
  if [[ ${#EDA_SUMMARIZE_EXTRA[@]} -gt 0 ]]; then
    python3 "$EDA_DIR/summarize.py" --tool "$tool" --log "$log" --exit-code "$rc" \
      "${EDA_SUMMARIZE_EXTRA[@]}"
  else
    python3 "$EDA_DIR/summarize.py" --tool "$tool" --log "$log" --exit-code "$rc"
  fi
}
