#!/usr/bin/env bash
# netgen-wrapper.sh — run netgen LVS and emit compact JSON output
# Usage: netgen-wrapper.sh -batch lvs "<netlist1> <cell1>" "<netlist2> <cell2>" <setup.tcl>
set -euo pipefail

LOG=$(mktemp /tmp/netgen-XXXXXX.log)
EXIT_CODE=0

if ! command -v netgen &>/dev/null; then
  python3 -c "import json; print(json.dumps({'tool':'netgen','exit_code':127,'status':'FAIL','summary':{},'errors':['netgen not found in PATH'],'warnings':[],'raw_log':'$LOG'}))"
  exit 127
fi

netgen "$@" >"$LOG" 2>&1 || EXIT_CODE=$?

LVS_PASS=$(grep -cE 'Circuits match uniquely|LVS CLEAN' "$LOG" 2>/dev/null || echo 0)
LVS_FAIL=$(grep -cE 'Circuits do not match|LVS FAILED' "$LOG" 2>/dev/null || echo 0)
ERRORS=$(grep -iE 'error|fatal' "$LOG" 2>/dev/null | head -20 || true)
WARNINGS=$(grep -iE 'warning' "$LOG" 2>/dev/null | head -10 || true)

STATUS="PASS"
[[ $LVS_FAIL -gt 0 || $EXIT_CODE -ne 0 ]] && STATUS="FAIL"

python3 - <<PYEOF
import json
errors_raw   = """$ERRORS"""
warnings_raw = """$WARNINGS"""
def nonempty(s): return [l.strip() for l in s.splitlines() if l.strip()]
print(json.dumps({
    "tool":      "netgen",
    "exit_code": $EXIT_CODE,
    "status":    "$STATUS",
    "summary":   {"lvs_pass": $LVS_PASS, "lvs_fail": $LVS_FAIL},
    "errors":    nonempty(errors_raw),
    "warnings":  nonempty(warnings_raw),
    "raw_log":   "$LOG"
}, indent=2))
PYEOF
exit $EXIT_CODE
