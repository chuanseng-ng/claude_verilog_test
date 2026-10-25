#!/bin/bash
# chain_after_route.sh -- wait for stage 05, run 05b DRC repair, then 06 finish from 05b_repair when it saved (else from 05_route).
cd "$(dirname "$0")/.."
until [ -s runs_05.out ]; do sleep 15; done
scripts/run_stage.sh 05b_repair b5b_innovus > runs_05b.out 2>&1
if [ -d runs/b5b_innovus/dbs/05b_repair.enc.dat ]; then export FROM_LABEL=05b_repair; else export FROM_LABEL=05_route; fi
scripts/run_stage.sh 06_finish b5b_innovus > runs_06.out 2>&1
echo "chain done FROM_LABEL=$FROM_LABEL" > runs_chain.out
