#!/bin/bash
# run_iolat_pv.sh <variant> <arm> <rc> <lib> -- ONE judge run (run_one.sh, unchanged) with the per-view iolat SDC
#   variant arm     per-arm latency: each arm's clk_io latency = that arm's own measured tree at this corner   -> runs_iolat_pv/
#   variant shared  one latency per corner, the same for every arm                                              -> runs_iolat_pvs/
# The SDC is the SAME file for every arm and variant (pnr/commercial/constraints/sky130_cpu_iolat_pv.sdc); only the table differs
# (pt/iolat_pv/iolat_pv_<variant>.tsv).  run_one.sh sees it as PT_SDC=own (md5 computed and recorded); everything else (netlist, SPEF snapshot,
# judge.tcl, settings) is byte-for-byte the same as the base/iolat/own judge runs.  PrimePower runs at nom_tt only (power flag 1).
# After the run the SDC's echoed 'IOLAT_PV key=.. early=.. late=..' line is checked against the table row; the evidence goes to iolat_pv.txt in the run dir.
set -eu
variant=$1; arm=$2; rc=$3; lib=$4
HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$HERE/../../../../.." && pwd)
case $variant in arm) set_=iolat_pv ;; shared) set_=iolat_pvs ;; *) echo "variant arm|shared" >&2; exit 2 ;; esac
TABLE=$ROOT/pnr/commercial/signoff/pt/iolat_pv/iolat_pv_$variant.tsv
SDCREL=pnr/commercial/constraints/sky130_cpu_iolat_pv.sdc
key=${arm}_${rc}_${lib}
row=$(awk -F'\t' -v k="$key" '$0 !~ /^#/ && ($1"_"$2"_"$3)==k {print $4" "$5}' "$TABLE")
[ -n "$row" ] || { echo "no row $key in $TABLE" >&2; exit 2; }
want_e=${row% *}; want_l=${row#* }
pw=0; [ "$rc" = nom ] && [ "$lib" = tt ] && pw=1
out=$ROOT/pnr/commercial/signoff/pt/runs_$set_/${key}
export IOLAT_PV_TABLE=$TABLE IOLAT_PV_KEY=$key
FORCE=1 PT_SET=$set_ PT_SDC=own PT_SDC_FILE=$SDCREL "$HERE/run_one.sh" "$arm" "$rc" "$lib" "$pw"
line=$(grep -m1 "^IOLAT_PV key=$key " "$out/pt.log" || true)
[ "$line" = "IOLAT_PV key=$key early=$want_e late=$want_l" ] || { echo "IOLAT_PV echo mismatch for $key: got '$line' want early=$want_e late=$want_l" >&2; rm -f "$out/.done"; exit 6; }
{ echo "variant=$variant"; echo "key=$key"; echo "table=$TABLE"; echo "table_md5=$(md5sum "$TABLE" | cut -d' ' -f1)"; echo "early_ns=$want_e"; echo "late_ns=$want_l"; echo "sdc=$SDCREL"; echo "sdc_md5=$(md5sum "$ROOT/$SDCREL" | cut -d' ' -f1)"; echo "echo=$line"; } > "$out/iolat_pv.txt"
echo "DONE $set_ $key early=$want_e late=$want_l"
# drop the page cache of the big SPEF copies (host thrashed in kcompactd with the cache full of SPEFs)
for f in "$out"/spef/*.spef "$ROOT"/$(. "$HERE/arms.sh"; arm_spef "$arm" "$rc") ; do dd if="$f" iflag=nocache count=0 status=none 2>/dev/null || true; done
