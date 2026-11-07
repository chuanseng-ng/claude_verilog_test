#!/bin/bash
# run_diag_pv.sh <variant> <arm> <rc> <lib> -- diag_io_viol.tcl on the per-view run's own SPEF snapshot/netlist/table row, then summ_io_viol.py.
set -eu
variant=$1; arm=$2; rc=$3; lib=$4
HERE=$(cd "$(dirname "$0")" && pwd); ROOT=$(cd "$HERE/../../../../.." && pwd); . "$HERE/arms.sh"
case $variant in arm) set_=iolat_pv ;; shared) set_=iolat_pvs ;; esac
key=${arm}_${rc}_${lib}; out=$ROOT/pnr/commercial/signoff/pt/runs_$set_/$key
SP=$(ls "$out"/spef/*.spef)
. "$ROOT/tools/eda/pd_env.sh" >/dev/null 2>&1 || true
cd "$out"
export J_ROOT=$ROOT J_NETLIST=$ROOT/$(arm_netlist "$arm") J_SPEF=$SP J_RC=$rc J_LIB=$lib J_SDC=$ROOT/pnr/commercial/constraints/sky130_cpu_iolat_pv.sdc
export IOLAT_PV_TABLE=$ROOT/pnr/commercial/signoff/pt/iolat_pv/iolat_pv_$variant.tsv IOLAT_PV_KEY=$key
export SAFE_THREADS=2 SAFE_MEM_MAX=6G SAFE_TIMEOUT=1800
"$ROOT/pnr/commercial/pdk/sky130/scripts/safe_run.sh" "$out/diag_pt.log" pt_shell -f "$HERE/diag_io_viol.tcl"
[ -s io_viol.tsv ] || { echo "no io_viol.tsv for $key" >&2; exit 1; }
python3 -I "$HERE/summ_io_viol.py" "$out"
dd if="$SP" iflag=nocache count=0 status=none 2>/dev/null || true
echo "DIAG $set_ $key"
