#!/bin/bash
# run_inn.sh -- one read-only Innovus diagnostic session on b5g 06_finish under safe_run.sh (<=2 threads, 7G).  Only when no other licensed PD tool is running.
set -eu
SD=$(cd "$(dirname "$0")" && pwd); REPO=$(cd "$SD/../../../../../.." && pwd); PDKDIR=$REPO/pnr/commercial/pdk/sky130
export REPO PDKDIR HERE=$PDKDIR TAG=b5g_innovus RUN=$REPO/pnr/commercial/impl/innovus/runs/b5g_innovus
export GOUT=$REPO/pnr/commercial/signoff/pt/runs_diag_b5g/innovus_${1:-a}
export STARSPEF=$REPO/pnr/commercial/signoff/starrc/runs/innovus_nom/rv32i_cpu_top.nom.spef
mkdir -p $GOUT
source $REPO/tools/eda/pd_env.sh >/dev/null 2>&1
export SAFE_MEM_MAX=7G SAFE_THREADS=2 SAFE_TIMEOUT=3600
cd $GOUT
$PDKDIR/scripts/safe_run.sh $GOUT/inn.log innovus -nowin -files $SD/inn_gap.tcl -log $GOUT/inn.innovus.log -overwrite
