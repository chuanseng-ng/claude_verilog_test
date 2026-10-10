#!/usr/bin/env bash
# Build both probe-instrumented arms (rtl_p, gate_p) under <work_dir>.
# usage: build_probe_arms.sh <work_dir>
set -eu
W="$1"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
python3 "$HERE/gen_probes.py" rtl "$W/probe_rtl.vh"
NETLIST="${NETLIST:-$W/rv32i_cpu_top.nl.v}" python3 "$HERE/gen_probes.py" gate "$W/probe_gate.vh"
PROBE_FILE="$W/probe_rtl.vh" bash "$HERE/build_arm.sh" rtl "$W/rtl_p" > "$W/rtl_p.out" 2>&1
PROBE_FILE="$W/probe_gate.vh" bash "$HERE/build_arm.sh" gate "$W/gate_p" "${NETLIST:-$W/rv32i_cpu_top.nl.v}" > "$W/gate_p.out" 2>&1
tail -2 "$W/rtl_p.out" "$W/gate_p.out"
