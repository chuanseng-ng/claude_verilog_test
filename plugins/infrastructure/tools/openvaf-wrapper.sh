#!/usr/bin/env bash
# openvaf-wrapper.sh — compile Verilog-A to OSDI and emit compact JSON output
# Usage: openvaf-wrapper.sh <model.va> [--output <model.osdi>]
set -euo pipefail

LOG=$(mktemp /tmp/openvaf-XXXXXX.log)
EXIT_CODE=0

if ! command -v openvaf &>/dev/null; then
  python3 -c "import json; print(json.dumps({'tool':'openvaf','exit_code':127,'status':'FAIL','summary':{'note':'openvaf not available — M-a/M-b use ngspice B-sources instead'},'errors':['openvaf not found in PATH; see install-missing-tools/install-openvaf.sh'],'warnings':[],'raw_log':'$LOG'}))"
  exit 127
fi

openvaf "$@" >"$LOG" 2>&1 || EXIT_CODE=$?
STATUS="PASS"; [[ $EXIT_CODE -ne 0 ]] && STATUS="FAIL"
OSDI=$(grep -oE '\S+\.osdi' "$LOG" 2>/dev/null | head -1 || echo "")
ERRORS=$(grep -iE 'error|fatal' "$LOG" 2>/dev/null | head -20 || true)
WARNINGS=$(grep -iE 'warning' "$LOG" 2>/dev/null | head -10 || true)

python3 - <<PYEOF
import json
errors_raw   = """$ERRORS"""
warnings_raw = """$WARNINGS"""
def nonempty(s): return [l.strip() for l in s.splitlines() if l.strip()]
print(json.dumps({
    "tool":      "openvaf",
    "exit_code": $EXIT_CODE,
    "status":    "$STATUS",
    "summary":   {"osdi_output": "$OSDI"},
    "errors":    nonempty(errors_raw),
    "warnings":  nonempty(warnings_raw),
    "raw_log":   "$LOG"
}, indent=2))
PYEOF
exit $EXIT_CODE
