#!/usr/bin/env bash
# magic-wrapper.sh — run magic DRC/extract and emit compact JSON output
# Usage: magic-wrapper.sh -rcfile <techfile.magicrc> -tcl <script.tcl> [args...]
set -euo pipefail

TOOL="magic"
LOG=$(mktemp /tmp/magic-XXXXXX.log)
EXIT_CODE=0

if ! command -v magic &>/dev/null; then
  python3 -c "import json; print(json.dumps({'tool':'magic','exit_code':127,'status':'FAIL','summary':{},'errors':['magic not found in PATH'],'warnings':[],'raw_log':'$LOG'}))"
  exit 127
fi

magic "$@" >"$LOG" 2>&1 || EXIT_CODE=$?

DRC_COUNT=$(grep -cE '\[DRC\]' "$LOG" 2>/dev/null || echo 0)
ERRORS=$(grep -iE 'error|fatal' "$LOG" 2>/dev/null | head -20 || true)
WARNINGS=$(grep -iE 'warning' "$LOG" 2>/dev/null | head -20 || true)

STATUS="PASS"
[[ $EXIT_CODE -ne 0 || "$DRC_COUNT" -gt 0 ]] && STATUS="FAIL"

python3 - <<PYEOF
import json
errors_raw   = """$ERRORS"""
warnings_raw = """$WARNINGS"""
def nonempty(s): return [l.strip() for l in s.splitlines() if l.strip()]
print(json.dumps({
    "tool":      "magic",
    "exit_code": $EXIT_CODE,
    "status":    "$STATUS",
    "summary":   {"drc_count": $DRC_COUNT},
    "errors":    nonempty(errors_raw),
    "warnings":  nonempty(warnings_raw),
    "raw_log":   "$LOG"
}, indent=2))
PYEOF
exit $EXIT_CODE
