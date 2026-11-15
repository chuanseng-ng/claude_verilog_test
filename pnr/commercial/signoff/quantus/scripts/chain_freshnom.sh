#!/bin/bash
# chain_freshnom.sh -- step 6 of the commercial cleanup (2026-11-14): Quantus nom re-extraction with the FRESH nom qrcTechFile
# (build/qrc/nom.fresh, a Techgen -cell run built exactly like min/max) on the three final arms, then the PrimeTime nom_tt sensitivity.
# Strictly one licensed tool at a time (licensed_lock.sh), >= 60 s between job starts.  Resumable: runs_freshnom/<arm>_nom/.done and the PT .done stamps.
# Output dirs: quantus/runs_freshnom/<arm>_nom (SPEFs are large and are not committed), pt/runs_quantus_freshnom/<arm>_nom_tt.  The previous
# (migrated-nom) results in runs/ and pt/runs_quantus/ are left untouched.
HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$HERE/../../../../.." && pwd)
SK=$ROOT/pnr/commercial/pdk/sky130
QR=$HERE/../runs_freshnom; mkdir -p "$QR"
log=$QR/chain_freshnom.log
say() { echo "$(date -Is) $*" >> "$log"; }
d=$SK/build/qrc/nom.fresh
[ -f "$d/.done_migrate" ] || { say "STOP: $d/.done_migrate missing"; exit 2; }
export QUANTUS_TECHDIR=$d
for arm in ${ARMS:-innovusb11 icc2b9 openroad}; do
  o=$QR/${arm}_nom; mkdir -p "$o"
  if [ -f "$o/.done" ]; then say "skip quantus $arm (done)"; continue; fi
  sleep 60; say "START quantus $arm nom (fresh qrcTechFile)"
  SAFE_MIN_AVAIL_GB=6 "$SK/scripts/licensed_lock.sh" "$HERE/run_quantus.sh" "$arm" nom "$o" >> "$QR/${arm}_nom.out" 2>&1; rc=$?
  say "END quantus $arm rc=$rc"
  if [ $rc -eq 0 ] && tail -c 64 "$o/rv32i_cpu_top.nom.spef" | grep -q '^\*END'; then touch "$o/.done"; else say "STOP: quantus $arm failed"; exit 1; fi
done
for arm in ${ARMS:-innovusb11 icc2b9 openroad}; do
  sleep 60; say "START pt $arm nom_tt (Quantus fresh SPEF)"
  ( cd "$ROOT/pnr/commercial/signoff/pt" && "$SK/scripts/licensed_lock.sh" env PT_SET=quantus_freshnom PT_STARRC_DIR=pnr/commercial/signoff/quantus/runs_freshnom PT_NO_MARKER=1 GATE_LIGHT=1 scripts/run_one.sh "$arm" nom tt 1 ) >> "$QR/pt_${arm}.out" 2>&1; rc=$?
  say "END pt $arm rc=$rc"; [ $rc -eq 0 ] || { say "STOP: pt $arm failed"; exit 1; }
done
say "CHAIN DONE"
