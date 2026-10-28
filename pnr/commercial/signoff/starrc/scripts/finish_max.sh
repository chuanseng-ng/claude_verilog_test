#!/bin/bash
# finish_max.sh -- after grdgenxo max has produced build/nxtgrd/max/sky130A_max.nxtgrd:
# extract max for openroad, icc2, innovus (one at a time, safe_run gated), then rebuild the correlation tables and the per-arm table.
# Safe to re-run: finished runs (.done) are skipped.  Progress: reports/finish_max.status
cd "$(dirname "$0")/.." || exit 1
NX=../../pdk/sky130/build/nxtgrd/max/sky130A_max.nxtgrd
st=reports/finish_max.status
echo "$(date -Is) waiting for $NX" > $st
until [ -s "$NX" ] && ! pgrep -f "grdgenxo sky130A_max.itf" >/dev/null; do sleep 60; done
echo "$(date -Is) nxtgrd max present, extracting" >> $st
make runs/openroad_max/.done runs/icc2_max/.done runs/innovus_max/.done >> $st.log 2>&1
make corr >> $st.log 2>&1
python3 -I scripts/collect_stats.py > reports/per_arm.md 2>> $st.log
python3 -I ../../pdk/sky130/scripts/tune/pinfit.py runs/corr/rcx_openroad_max.tsv runs/corr/sr_openroad_max.tsv ../../runs/openroad/rv32i_cpu_top.max.spef > reports/pinfit_max.txt 2>> $st.log
echo "$(date -Is) DONE: reports/correlation_max.md reports/per_arm.md reports/pinfit_max.txt" >> $st
