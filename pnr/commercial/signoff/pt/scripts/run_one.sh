#!/bin/bash
# run_one.sh <arm> <rc> <lib> [power]  -- ONE pt_shell under safe_run.sh (load/mem gate, <=2 threads, process-group kill).
#  * snapshots the SPEF into runs/<arm>_<rc>_<lib>/spef/ with md5 before+after the copy (a file replaced mid-run cannot contaminate)
#  * skips (exit 0) when the input stamp (spef md5 + netlist md5 + sdc md5 + scripts md5 + power flag) equals the last good run
#  * FORCE=1 reruns anyway.  Exit 3 = PENDING inputs (arm not built yet), 4 = SPEF/netlist incomplete.
set -eu
arm=$1; rc=$2; lib=$3; pw=${4:-0}
HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$HERE/../../../../.." && pwd)
. "$HERE/arms.sh"
# PT_SDC selects the SDC variant: base (default; pnr/sky130/cpu/constraints/sky130_cpu.sdc, md5 3c69...) or iolat (comparison-only
# pnr/commercial/constraints/sky130_cpu_iolat.sdc, expected md5 from its generator-written .md5 sidecar, re-verified here)
case "${PT_SDC:-base}" in
  base)  SDC=$ROOT/pnr/sky130/cpu/constraints/sky130_cpu.sdc; SDC_MD5=3c69635042a9d65cb87e71a9db713e4e ;;
  iolat) SDC=$ROOT/pnr/commercial/constraints/sky130_cpu_iolat.sdc; SDC_MD5=$(tr -d ' \n' < "$SDC.md5") ;;
  own)   SDC=$ROOT/${PT_SDC_FILE:?PT_SDC=own needs PT_SDC_FILE (repo-relative)}; SDC_MD5=$(md5sum "$SDC" | cut -d' ' -f1) ;;   # the arm's OWN exported SDC (e.g. Innovus b5h out/rv32i_cpu_top.sdc); md5 recorded in inputs.txt
  *) echo "unknown PT_SDC=$PT_SDC" >&2; exit 2 ;;
esac
[ "$(md5sum "$SDC" | cut -d' ' -f1)" = "$SDC_MD5" ] || { echo "SDC md5 mismatch for variant ${PT_SDC:-base}: $SDC" >&2; exit 5; }
NL=$ROOT/$(arm_netlist "$arm"); SP=$ROOT/$(arm_spef "$arm" "$rc"); MK=$(arm_spef_marker "$arm" "$rc")
tag=${arm}_${rc}_${lib}
# PT_SET (e.g. untuned) selects the run directory runs_<set>/ (default runs/); PT_STARRC_DIR is read by arms.sh
out=$ROOT/pnr/commercial/signoff/pt/runs${PT_SET:+_$PT_SET}/$tag
if [ ! -s "$NL" ] || [ ! -s "$SP" ]; then echo "PENDING $tag: missing $( [ -s "$NL" ] || echo netlist ) $( [ -s "$SP" ] || echo spef )"; exit 3; fi
if [ -n "$MK" ] && [ ! -f "$ROOT/$MK" ]; then echo "PENDING $tag: StarRC not complete ($MK absent)"; exit 3; fi
tail -c 64 "$SP" | grep -q '^\*END' || { echo "SPEF incomplete (no *END): $SP" >&2; exit 4; }
mkdir -p "$out/spef"
# snapshot with a stability check
for try in 1 2 3; do
  m1=$(md5sum "$SP" | cut -d' ' -f1); cp -f "$SP" "$out/spef/$(basename "$SP")"
  m2=$(md5sum "$SP" | cut -d' ' -f1); m3=$(md5sum "$out/spef/$(basename "$SP")" | cut -d' ' -f1)
  [ "$m1" = "$m2" ] && [ "$m1" = "$m3" ] && break
  echo "SPEF changed during copy (try $try), retrying" >&2; sleep 20
done
[ "$m1" = "$m2" ] && [ "$m1" = "$m3" ] || { echo "SPEF unstable: $SP" >&2; exit 4; }
nlmd5=$(md5sum "$NL" | cut -d' ' -f1); sdcmd5=$(md5sum "$SDC" | cut -d' ' -f1)
scmd5=$(cat "$HERE/judge.tcl" "$HERE/run_one.sh" | md5sum | cut -d' ' -f1)
stamp="spef=$m1 netlist=$nlmd5 sdc=$sdcmd5 scripts=$scmd5 power=$pw"
if [ -z "${FORCE:-}" ] && [ -f "$out/.done" ] && [ "$(cat "$out/.done")" = "$stamp" ]; then echo "UP-TO-DATE $tag"; exit 0; fi
rm -f "$out/.done"
{ echo "spef_src=$SP"; echo "spef_md5=$m1"; echo "netlist_src=$NL"; echo "netlist_md5=$nlmd5"; echo "sdc_md5=$sdcmd5"; echo "scripts_md5=$scmd5"; echo "power=$pw"; } > "$out/inputs.txt"
. "$ROOT/tools/eda/pd_env.sh" >/dev/null 2>&1 || true
cd "$out"
export J_ROOT=$ROOT J_NETLIST=$NL J_SPEF=$out/spef/$(basename "$SP") J_RC=$rc J_LIB=$lib J_POWER=$pw J_SDC=$SDC J_SDC_MD5=$SDC_MD5 J_SDC_VARIANT=${PT_SDC:-base} J_OUT=$out
export SAFE_THREADS=2 SAFE_MEM_MAX=${SAFE_MEM_MAX:-6G} SAFE_TIMEOUT=${SAFE_TIMEOUT:-3600}
rc_=0
"$ROOT/pnr/commercial/pdk/sky130/scripts/safe_run.sh" "$out/pt.log" \
  /usr/bin/time -v -o "$out/time.txt" pt_shell -f "$HERE/judge.tcl" || rc_=$?
echo "rc=$rc_" >> "$out/time.txt"
if [ $rc_ -eq 0 ] && [ -s metrics.tsv ] && grep -q '^hold_viol' metrics.tsv && { [ "$pw" = 0 ] || [ -s power_B.txt ]; }; then
  echo "$stamp" > .done; echo "DONE $tag"
else echo "FAILED $tag rc=$rc_ (see $out/pt.log)" >&2; exit 1; fi
