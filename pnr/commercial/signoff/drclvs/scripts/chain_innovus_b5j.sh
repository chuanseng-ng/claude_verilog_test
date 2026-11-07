#!/bin/bash
# chain_innovus_b5j.sh -- open-deck physical verification of Innovus b5j (ARM=innovus_b5j), one heavy tool at a time:
#   inspect, fixgds, lvs (DEF+LEF), lvs-gds (GDS-mode extraction) + clean/merged netgen variants, kdrc, antenna.  Magic DRC (mdrc) is NOT in the default chain (host-idle only: MDRC=1).
cd "$(dirname "$0")/.."
A=innovus_b5j; mkdir -p runs/$A/logs; L=runs/$A/chain.log
for t in inspect fixgds lvs-gds-extract lvs-gds-variants lvs-gds-netgen kdrc antenna lvs; do
  echo "$(date +%T) start $t" >> $L; make ARM=$A PIN_MODE=none $t > runs/$A/logs/make_$t.log 2>&1; echo "$(date +%T) end $t rc=$?" >> $L
done
if [ "${MDRC:-0}" = 1 ]; then for t in mdrc mdrc-class; do echo "$(date +%T) start $t" >> $L; GUARD_RSS_GB=11 make ARM=$A PIN_MODE=none $t > runs/$A/logs/make_$t.log 2>&1; echo "$(date +%T) end $t rc=$?" >> $L; done; fi
make ARM=$A summary > runs/$A/logs/make_summary.log 2>&1
echo "$(date +%T) chain done" >> $L
