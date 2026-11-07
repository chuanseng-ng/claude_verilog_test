#!/bin/bash
cd "$(dirname "$0")/.."; T=b5c_innovus_s2
scripts/run_stage.sh 05d_final_repair $T > runs/$T/05d.out 2>&1
FROM_LABEL=05d_final scripts/run_stage.sh 06_finish $T > runs/$T/06b.out 2>&1
echo "$(date +%T) s3 done" >> runs/$T/chain.log
