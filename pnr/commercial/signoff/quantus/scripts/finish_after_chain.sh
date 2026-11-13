#!/bin/bash
# finish_after_chain.sh -- wait for chain_all.sh to log CHAIN DONE (or STOP), then regenerate the committed-report inputs (light python, no licensed tool).
# Afterwards, by hand: python3 -I pnr/commercial/compare/compare.py ; pytest test_compare.py ; update docs/COMMERCIAL_FLOW_COMPARISON.md section 10 and reports/quantus_crosscheck.md ; git add -f ; commit.
HERE=$(cd "$(dirname "$0")" && pwd); L=$HERE/../runs/chain_all.log
until tail -1 "$L" | grep -q -E "CHAIN DONE|STOP:"; do sleep 60; done
PY=/home/EDA/mentor/calibre2026/aok_cal_2026.1_17.11/bin/python3
"$PY" -I "$HERE/correlate_all.py" > "$HERE/../runs/correlate_all.out" 2>&1
python3 -I "$HERE/collect_runs.py" > "$HERE/../runs/collect_runs.out" 2>&1
echo "$(date -Is) FINISH DONE ($(tail -1 "$L"))" >> "$L"
