#!/bin/bash
# run_grdgenxo.sh <corner> -- ITF -> nxtgrd (+ TLU+ for ICC2) via StarRC grdgenxo, under safe_run.sh
set -u
here=$(cd "$(dirname "$0")" && pwd); b=$here/../build
c=$1; d=$b/nxtgrd/$c; mkdir -p "$d" "$b/logs"
cp "$b/tech/itf/sky130A_$c.itf" "$d/"
# TLU+ first (about a minute), then the nxtgrd field-solver run: single-threaded it takes ~40-50 min, so the default
# 30-min safe_run timeout (which killed the first attempt, rc=143) is raised to 4 h.
( cd "$d" && "$here/safe_run.sh" "$b/logs/grdgenxo_tluplus_$c.log" grdgenxo -itf2TLUPlus -i "sky130A_$c.itf" -o "sky130A_$c.tluplus" ); rc2=$?
( cd "$d" && SAFE_TIMEOUT=${SAFE_TIMEOUT:-14400} "$here/safe_run.sh" "$b/logs/grdgenxo_$c.log" grdgenxo "sky130A_$c.itf" ); rc=$?
ls -la "$d"
echo "grdgenxo $c nxtgrd rc=$rc tluplus rc=$rc2"
[ $rc -eq 0 ] && [ -n "$(ls "$d"/*.nxtgrd "$d"/sky130A_$c/*.nxtgrd 2>/dev/null)" ]
