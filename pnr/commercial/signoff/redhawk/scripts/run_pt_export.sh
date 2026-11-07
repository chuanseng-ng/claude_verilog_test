#!/bin/bash
# run_pt_export.sh <arm>  -- ONE pt_shell (PrimePower per-instance power + RedHawk .timing) under licensed_lock + safe_run.
#   arm: openroad | icc2b6 | innovusb6   (netlist/SPEF from signoff/pt/scripts/arms.sh, same as the judge)
set -eu
arm=$1
HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$HERE/../../../../.." && pwd)
. "$ROOT/pnr/commercial/signoff/pt/scripts/arms.sh"
NL=$ROOT/$(arm_netlist "$arm"); SP=$ROOT/$(arm_spef "$arm" nom)
SDC=$ROOT/pnr/sky130/cpu/constraints/sky130_cpu.sdc; SDC_MD5=3c69635042a9d65cb87e71a9db713e4e
out=$ROOT/pnr/commercial/signoff/redhawk/runs/$arm/pt; mkdir -p "$out"
tail -c 64 "$SP" | grep -q '^\*END' || { echo "SPEF incomplete" >&2; exit 4; }
. "$ROOT/tools/eda/pd_env.sh" >/dev/null 2>&1 || true
cd "$out"
export J_ROOT=$ROOT J_NETLIST=$NL J_SPEF=$SP J_SDC=$SDC J_SDC_MD5=$SDC_MD5 J_OUT=$out
{ echo "netlist=$NL md5=$(md5sum $NL|cut -d' ' -f1)"; echo "spef=$SP md5=$(md5sum $SP|cut -d' ' -f1)"; echo "sdc_md5=$SDC_MD5"; } > inputs.txt
export SAFE_THREADS=2 SAFE_MEM_MAX=6G SAFE_TIMEOUT=1800
"$ROOT/pnr/commercial/pdk/sky130/scripts/licensed_lock.sh" "$ROOT/pnr/commercial/pdk/sky130/scripts/safe_run.sh" "$out/pt.log" \
  /usr/bin/time -v -o "$out/time.txt" pt_shell -f "$HERE/pt_export.tcl"
rc=$?
[ -s instance_power.txt ] && [ -s rv32i_cpu_top.timing.gz ] && echo "$arm PT EXPORT DONE" > .done || { echo "$arm PT EXPORT INCOMPLETE rc=$rc"; exit 1; }
