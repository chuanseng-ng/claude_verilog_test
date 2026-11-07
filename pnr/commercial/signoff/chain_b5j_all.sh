#!/bin/bash
# chain_b5j_all.sh -- b5j licensed verification chain, strictly sequential, each licensed tool under the host-wide flock:
#   (wait for the Innovus 07_restream to exit) -> Conformal LEC (4 compares + 4 negative controls) -> StarRC nom/min/max -> PT judge (own, base, iolat x 9 corners).
# Open-deck DRC/LVS (drclvs/scripts/chain_innovus_b5j.sh) is a separate, non-licensed chain.
cd "$(dirname "$0")"
L=chain_b5j_all.log; LOCK=/tmp/claude-1001/licensed_tool.lock
while pgrep -x innovus >/dev/null; do sleep 60; done
echo "$(date +%T) innovus idle; start LEC" >> $L
flock $LOCK make -C lec/conformal lec-innovus-all INNTAG=b5j_innovus STEP=b4j > lec/conformal/b4j_make.log 2>&1; echo "$(date +%T) end LEC rc=$?" >> $L
bash starrc/scripts/chain_b5j_starrc.sh >> $L 2>&1; echo "$(date +%T) end StarRC" >> $L
bash pt/scripts/chain_b5j_pt.sh >> $L 2>&1; echo "$(date +%T) end PT chain" >> $L
