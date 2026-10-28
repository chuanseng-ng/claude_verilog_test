#!/bin/bash
# resume B5d after the host shutdown: 05b_repair was saved with 0 DRC; run post-route opt and finish.
cd "$(dirname "$0")/.."; T=b5d_innovus; L=runs/$T/chain.log
export B5C_SCREEN=1 B5C_STRAP=1 B5D=1
echo "$(date +%T) RESUME start 05_route from 05b_repair" >> $L
FROM_LABEL=05b_repair scripts/run_stage.sh 05_route $T > runs/$T/05.out 2>&1
echo "$(date +%T) start 06_finish" >> $L
FROM_LABEL=05_route scripts/run_stage.sh 06_finish $T > runs/$T/06.out 2>&1
echo "$(date +%T) chain done" >> $L
