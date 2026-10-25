#!/bin/sh
# Simulate Tessent serial patterns on the scan-inserted gate netlist with VCS (zero-delay Liberty-derived cell models).
# usage: vcs_sim.sh <pattern_testbench.v> <workdir>      (BUILD must point at the flow's build directory)
set -e
HERE=$(cd "$(dirname "$0")" && pwd)
TB=$(readlink -f "$1"); W=$2; B=${BUILD:?}
mkdir -p "$W"; cd "$W"
python3 "$HERE/mk_sim_stubs.py" "$B/bb_ports.v" "$B/sim_stubs.v"
vcs -full64 -sverilog +v2k -timescale=1ns/1ns +nospecify +notimingchecks -j2 -o simv \
    "$B/sky130_hd_models.v" "$B/sim_stubs.v" "${NETLIST:-$B/soc_top_scan.v}" "$TB" -top "$(grep -m1 -o 'top_module_name *= *[A-Za-z0-9_]*' "$TB" | sed 's/.*= *//')" \
    -l vcs_compile.log
# the Tessent testbench opens its .cfg/.vec/.po.name files relative to the cwd, so run from the pattern directory
( cd "$(dirname "$TB")" && /usr/bin/time -v -o "$W/sim.time" "$W/simv" +nospecify -l "$W/vcs_run.log" )
grep -E "Elapsed|Maximum resident" "$W/sim.time"
