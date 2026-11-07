#!/bin/bash
# chain_inn_b6_a.sh -- b6 part A: floorplan + PDN/taps (identical physical setup to b5, taps fixed at source).
cd "$(dirname "$0")/.."; source scripts/b6lib.sh
stage 01_floorplan 01_floorplan 01_floorplan || exit 1
stage 02_pdn 02_pdn 02_pdn || exit 1
grep -E 'PDN_SELFCHECK|B6_NWELL|B6_TAPFIX|MACROS placed|PINS:' runs/$T/logs/02_pdn.log runs/$T/logs/01_floorplan.log >> $L
echo "$(date +%T) chain A done" >> $L
