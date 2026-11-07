#!/bin/bash
# run_equiv.sh <tag> -- route 2: Yosys equiv_make + equiv_struct/simple/induct inside the LibreLane 2.4.13 container (same image/Yosys 0.46 as the B2 run).  One tool at a time (licensed_lock), safe_run caps.
set -u
TAG=${1:-e3}
NETLIST=${2:-}   # gate netlist; default = the B2 Yosys synthesis netlist already named in equiv1.ys
HERE=/home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/commercial/signoff/lec/yosys
R=/home/RD/ryan/Desktop/Github/claude_verilog_test
P=$R/pnr/commercial/pdk/sky130/scripts
IMG=ghcr.io/librelane/librelane:2.4.13
export SAFE_MIN_AVAIL_GB=6 SAFE_THREADS=2 SAFE_MEM_MAX=10G SAFE_TIMEOUT=10800 SAFE_MAX_LOAD=6
mkdir -p $HERE/runs/$TAG
if [ -n "$NETLIST" ]; then sed "s#^read_verilog -sv .*rv32i_cpu_top.nl.v\$#read_verilog -sv $NETLIST#" $HERE/scripts/equiv1.ys > $HERE/runs/$TAG/equiv1.ys; else cp $HERE/scripts/equiv1.ys $HERE/runs/$TAG/equiv1.ys; fi
run() { $P/licensed_lock.sh $P/safe_run.sh $HERE/runs/$TAG/$1.stdout podman run --rm -v $R:$R -v /home/RD/ryan/pdk:/home/RD/ryan/pdk -w $HERE/runs/$TAG $IMG yosys -l $HERE/runs/$TAG/$1.log $HERE/scripts/$2; }
[ -f $HERE/runs/$TAG/equiv_made.il ] || run make ../runs/$TAG/equiv1.ys
sed "s#read_rtlil .*#read_rtlil $HERE/runs/$TAG/equiv_made.il#" $HERE/scripts/equiv3.ys > $HERE/runs/$TAG/equiv3.ys
sleep 5
run prove ../runs/$TAG/equiv3.ys
touch $HERE/runs/$TAG/CHAIN_DONE
