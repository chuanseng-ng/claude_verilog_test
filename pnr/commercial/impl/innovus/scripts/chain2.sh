#!/bin/bash
# chain2.sh -- post-route optimisation from 05a_routed (05b ecoRoute repair did not converge), then 06_finish from 05_route.
cd "$(dirname "$0")/.."
FROM_LABEL=05a_routed scripts/run_stage.sh 05_route b5b_innovus > runs_05.out 2>&1
FROM_LABEL=05_route scripts/run_stage.sh 06_finish b5b_innovus > runs_06.out 2>&1
echo done > runs_chain2.out
