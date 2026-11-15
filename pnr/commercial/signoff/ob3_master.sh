#!/bin/bash
# ob3_master.sh -- OpenROAD B3 sign-off driver: judge chain, then LEC chain (one heavy tool at a time; both resumable).  Log chain_ob3_all.log / ob3_master.log.
cd "$(dirname "$0")"
echo "$(date +%T) ob3_master start" >> ob3_master.log
./chain_ob3_all.sh
echo "$(date +%T) judge chain returned" >> ob3_master.log
./lec/chain_ob3_lec.sh > chain_ob3_lec.stdout 2>&1
echo "$(date +%T) ob3_master done" >> ob3_master.log
