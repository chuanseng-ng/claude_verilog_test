#!/usr/bin/env bash
# klayout-wrapper.sh — run KLayout DRC/LVS and emit compact JSON output
# Usage: klayout-wrapper.sh -b -r <drc_script.rb> -rd input=<layout.gds> [args...]
set -euo pipefail

LOG=$(mktemp /tmp/klayout-XXXXXX.log)
EXIT_CODE=0

if ! command -v klayout &>/dev/null; then
  python3 -c "import json; print(json.dumps({'tool':'klayout','exit_code':127,'status':'FAIL','summary':{},'errors':['klayout not found in PATH'],'warnings':[],'raw_log':'$LOG'}))"
  exit 127
fi

klayout "$@" >"$LOG" 2>&1 || EXIT_CODE=$?

DRC_COUNT=$(grep -cE 'DRC.*violation|DRC.*error' "$LOG" 2>/dev/null || echo 0)
LVS_MATCH=$(grep -cE 'LVS.*match|Circuits match' "$LOG" 2>/dev/null || echo 0)
ERRORS=$(grep -iE '^Error|fatal' "$LOG" 2>/dev/null | head -20 || true)
WARNINGS=$(grep -iE '^Warning' "$LOG" 2>/dev/null | head -20 || true)

STATUS="PASS"
[[ $EXIT_CODE -ne 0 || "$DRC_COUNT" -gt 0 ]] && STATUS="FAIL"

python3 - <<PYEOF
import json
errors_raw   = """$ERRORS"""
warnings_raw = """$WARNINGS"""
def nonempty(s): return [l.strip() for l in s.splitlines() if l.strip()]
print(json.dumps({
    "tool":      "klayout",
    "exit_code": $EXIT_CODE,
    "status":    "$STATUS",
    "summary":   {"drc_count": $DRC_COUNT, "lvs_match": $LVS_MATCH},
    "errors":    nonempty(errors_raw),
    "warnings":  nonempty(warnings_raw),
    "raw_log":   "$LOG"
}, indent=2))
PYEOF
exit $EXIT_CODE
