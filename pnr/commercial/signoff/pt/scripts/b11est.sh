#!/bin/bash
# b11est.sh <rc> <lib>  -- ONE pt_shell what-if on the b10 netlist/SPEF (see b11est.tcl).  env VARIANTS.  Output runs_b11est/<rc>_<lib>/
set -eu
rc=$1; lib=$2
HERE=$(cd "$(dirname "$0")" && pwd); ROOT=$(cd "$HERE/../../../../.." && pwd)
. "$HERE/arms.sh"
NL=$ROOT/$(arm_netlist ${ARM:-innovusb10}); SP=$ROOT/$(arm_spef ${ARM:-innovusb10} $rc)
SDC=$ROOT/pnr/sky130/cpu/constraints/sky130_cpu.sdc
out=$ROOT/pnr/commercial/signoff/pt/runs_b11est/${TAGP:-}${rc}_${lib}; mkdir -p $out
. "$ROOT/tools/eda/pd_env.sh" >/dev/null 2>&1 || true
cd $out
export J_ROOT=$ROOT J_NETLIST=$NL J_SPEF=$SP J_RC=$rc J_LIB=$lib J_SDC=$SDC J_OUT=$out VARIANTS="${VARIANTS:-buf_6 buf_8 buf_12 buf_16}"
export SAFE_THREADS=2 SAFE_MEM_MAX=6G SAFE_TIMEOUT=3600
"$ROOT/pnr/commercial/pdk/sky130/scripts/safe_run.sh" $out/pt.log pt_shell -f $HERE/b11est.tcl
