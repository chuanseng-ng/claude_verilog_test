#!/bin/bash
# chain_inn_b6_b.sh -- b6 part B: place_opt, CCOpt (MMMC), NanoRoute, post-route optimisation (setup / DRV repeaters / hold with ff / DRV), all three views.
cd "$(dirname "$0")/.."; source scripts/b6lib.sh
stage 03_place 03_place 03_place || exit 1
stage 04_cts 04_cts 04_cts || exit 1
stage 05a_route 05a_route 05a_routed || exit 1
stage 05m_post 05m_post 05_route || exit 1
echo "$(date +%T) chain B done" >> $L
