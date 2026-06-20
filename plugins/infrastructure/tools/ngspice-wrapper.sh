#!/usr/bin/env bash
# ngspice-wrapper.sh — run ngspice and emit compact JSON output
# Usage: ngspice-wrapper.sh <netlist.sp> [ngspice-args...]
set -euo pipefail

TOOL="ngspice"
NETLIST="${1:-}"
shift || true
LOG=$(mktemp /tmp/ngspice-XXXXXX.log)
EXIT_CODE=0

if ! command -v ngspice &>/dev/null; then
  python3 -c "import json; print(json.dumps({'tool':'ngspice','exit_code':127,'status':'FAIL','summary':{},'errors':['ngspice not found in PATH — enter nix analog devshell'],'warnings':[],'raw_log':'$LOG'}))"
  exit 127
fi

if [[ -z "$NETLIST" ]]; then
  python3 -c "import json; print(json.dumps({'tool':'ngspice','exit_code':1,'status':'FAIL','summary':{},'errors':['No netlist argument provided'],'warnings':[],'raw_log':'$LOG'}))"
  exit 1
fi

ngspice -b "$NETLIST" "$@" >"$LOG" 2>&1 || EXIT_CODE=$?

# Parse .measure results from log
MEASURES=$(grep -E '^\w.*=\s' "$LOG" 2>/dev/null | head -50 || true)
ERRORS=$(grep -iE 'error|fatal' "$LOG" 2>/dev/null | head -20 || true)
WARNINGS=$(grep -iE 'warning' "$LOG" 2>/dev/null | head -20 || true)

STATUS="PASS"
[[ $EXIT_CODE -ne 0 ]] && STATUS="FAIL"
[[ -n "$ERRORS" && $EXIT_CODE -eq 0 ]] && STATUS="WARN"

python3 - <<PYEOF
import json, sys
measures_raw = """$MEASURES"""
errors_raw   = """$ERRORS"""
warnings_raw = """$WARNINGS"""

def nonempty(s):
    return [l.strip() for l in s.splitlines() if l.strip()]

result = {
    "tool":      "ngspice",
    "exit_code": $EXIT_CODE,
    "status":    "$STATUS",
    "summary": {
        "netlist": "$NETLIST",
        "measures": nonempty(measures_raw)
    },
    "errors":   nonempty(errors_raw),
    "warnings": nonempty(warnings_raw),
    "raw_log":  "$LOG"
}
print(json.dumps(result, indent=2))
PYEOF
exit $EXIT_CODE
