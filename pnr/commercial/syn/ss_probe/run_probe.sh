#!/bin/bash
# Step 1: PT timing of the 3 synthesis netlists at nom_tt / nom_ss, ideal clock, no parasitics.
R=$(cd "$(dirname "$0")/../../../.." && pwd)
source $R/tools/eda/pd_env.sh >/dev/null 2>&1
OUT=$R/pnr/commercial/syn/ss_probe/runs/${TAG:-step1}
mkdir -p $OUT; cd $OUT
export ROOT=$R OUT=$OUT LIBS="${LIBS:-tt ss}"
export NETLISTS="${NETLISTS:-yosys=$R/pnr/sky130/cpu/runs/b2_openroad/06-yosys-synthesis/rv32i_cpu_top.nl.v dc_v1=$R/pnr/commercial/syn/dc/runs/b3a_dc_tt/out/rv32i_cpu_top.nl.v genus_v1=$R/pnr/commercial/syn/genus/runs/b3b_genus_tt_r2/out/rv32i_cpu_top.nl.v}"
export SAFE_THREADS=2 SAFE_MEM_MAX=6G SAFE_TIMEOUT=3600
$R/pnr/commercial/pdk/sky130/scripts/licensed_lock.sh $R/pnr/commercial/pdk/sky130/scripts/safe_run.sh $OUT/pt.log pt_shell -f $R/pnr/commercial/syn/ss_probe/pt_synth_probe.tcl
echo "rc=$?" > $OUT/rc.txt
