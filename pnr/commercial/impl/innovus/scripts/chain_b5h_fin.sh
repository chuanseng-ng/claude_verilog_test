#!/bin/bash
# chain_b5h_fin.sh -- b5h finish: 06_finish (decap/fill, reports, outputs, power@0.2/0.1, SI-off timing) then 07_restream (GDS + per-net PG connectivity).
cd "$(dirname "$0")/.."
export B5H=1 B5C_SCREEN=1 B5D=1 B5F=1 B5C_STRAP=0
T=b5h_innovus; L=runs/$T/chain.log
scripts/gate_host.sh || exit 1
echo "$(date +%T) start 06_finish" >> $L
FROM_LABEL=05_route scripts/run_stage.sh 06_finish $T > runs/$T/06.out 2>&1; echo "$(date +%T) end 06_finish rc=$?" >> $L
scripts/gate_host.sh || exit 1
echo "$(date +%T) start 07_restream" >> $L
scripts/run_stage.sh 07_restream $T > runs/$T/07.out 2>&1; echo "$(date +%T) end 07_restream rc=$?" >> $L
