#!/bin/bash
# run_iolat_pv_soc.sh <arm> <rc> <lib> -- ONE judge run (run_one.sh, unchanged) with the per-view iolat SDC + SoC-context input-delay budgets (step 4b)
#   SDC   pnr/commercial/constraints/sky130_cpu_iolat_pv_soc.sdc   (ONE file for every arm and corner; md5 recorded by run_one.sh as sdc_md5)
#   clk_io latency table   pt/iolat_pv/iolat_pv_arm.tsv   (per-arm, per-corner tree latency, as the 4.2b per-view runs)
#   input-delay budgets    pt/iolat_pv/iobud_soc.tsv      (rc, lib, group, max_delay_ns; built by soc_budget/scripts/mk_budget.py)
# Output: pt/runs_iolat_pv_soc/<arm>_<rc>_<lib>/.  PrimePower runs at nom_tt only (power flag 1), as the other variants.
# After the run the SDC's echoed 'IOLAT_PV ...' and 'IOBUD ...' lines are checked against the tables; the evidence goes to iolat_pv_soc.txt.
set -eu
arm=$1; rc=$2; lib=$3
HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$HERE/../../../../.." && pwd)
TABLE=$ROOT/pnr/commercial/signoff/pt/iolat_pv/iolat_pv_arm.tsv
BUD=$ROOT/pnr/commercial/signoff/pt/iolat_pv/iobud_soc.tsv
SDCREL=pnr/commercial/constraints/sky130_cpu_iolat_pv_soc.sdc
key=${arm}_${rc}_${lib}
row=$(awk -F'\t' -v k="$key" '$0 !~ /^#/ && ($1"_"$2"_"$3)==k {print $4" "$5}' "$TABLE")
[ -n "$row" ] || { echo "no row $key in $TABLE" >&2; exit 2; }
want_e=${row% *}; want_l=${row#* }
want_b=$(awk -F'\t' -v r="$rc" -v l="$lib" '$0 !~ /^#/ && $1==r && $2==l {printf " %s=%s",$3,$4}' "$BUD")
[ -n "$want_b" ] || { echo "no budget rows for ${rc}_${lib} in $BUD" >&2; exit 2; }
pw=0; [ "$rc" = nom ] && [ "$lib" = tt ] && pw=1
out=$ROOT/pnr/commercial/signoff/pt/runs_iolat_pv_soc/${key}
export IOLAT_PV_TABLE=$TABLE IOLAT_PV_KEY=$key IOBUD_TABLE=$BUD
FORCE=1 PT_SET=iolat_pv_soc PT_SDC=own PT_SDC_FILE=$SDCREL "$HERE/run_one.sh" "$arm" "$rc" "$lib" "$pw"
line=$(grep -m1 "^IOLAT_PV key=$key " "$out/pt.log" || true)
[ "$line" = "IOLAT_PV key=$key early=$want_e late=$want_l" ] || { echo "IOLAT_PV echo mismatch for $key: got '$line'" >&2; rm -f "$out/.done"; exit 6; }
bl=$(grep -m1 "^IOBUD key=${rc}_${lib} " "$out/pt.log" || true)
# order of groups in the echo = the SDC's group list; compare as sorted key=value sets
exp=$(echo "IOBUD key=${rc}_${lib}${want_b}" | tr ' ' '\n' | sort | tr '\n' ' ')
got=$(echo "$bl" | tr ' ' '\n' | sort | tr '\n' ' ')
[ -n "$bl" ] && [ "$exp" = "$got" ] || { echo "IOBUD echo mismatch for $key: got '$bl' want '$exp'" >&2; rm -f "$out/.done"; exit 6; }
{ echo "variant=soc_budget"; echo "key=$key"; echo "latency_table=$TABLE"; echo "latency_table_md5=$(md5sum "$TABLE" | cut -d' ' -f1)"; echo "budget_table=$BUD"; echo "budget_table_md5=$(md5sum "$BUD" | cut -d' ' -f1)"; echo "sdc=$SDCREL"; echo "sdc_md5=$(md5sum "$ROOT/$SDCREL" | cut -d' ' -f1)"; echo "echo_latency=$line"; echo "echo_budget=$bl"; } > "$out/iolat_pv_soc.txt"
echo "DONE iolat_pv_soc $key"
for f in "$out"/spef/*.spef "$ROOT"/$(. "$HERE/arms.sh"; arm_spef "$arm" "$rc") ; do dd if="$f" iflag=nocache count=0 status=none 2>/dev/null || true; done
