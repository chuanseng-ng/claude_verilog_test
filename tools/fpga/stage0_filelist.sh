#!/usr/bin/env bash
# stage0_filelist.sh -- print the RTL file list of the full soc_top, one path per line (bead hlrm, FPGA Stage 0).
#
# usage: stage0_filelist.sh <repo-root> <gpu|nogpu> <sim|fpga>
#
#   gpu    real rtl/gpu/* (the cocotb PLL_SOURCES list minus its testbench and sim-only SRAM models)
#   nogpu  rtl/gpu/* replaced by pnr/sky130/soc/gpu_top_tieoff.sv -- the SAME synthesisable tie-off the
#          Sky130 SoC flow uses (pnr/Makefile SKY130_SOC_SV_FILES); no new exclusion mechanism is invented.
#          NB the Sky130 flow also blackboxes the CPU; here the CPU stays real.
#   sim    append the simulation SRAM models (sim/*.v) -- what every cocotb/Verilator build compiles
#   fpga   append rtl/fpga/*.sv (the `FPGA arm's inferable memories) instead of the sim models
#
# The base list is parsed out of tb/cocotb/soc/Makefile PLL_SOURCES so it cannot drift from the list the
# regression elaborates. Run it on a pristine origin/main export for the byte-identity proof.
set -euo pipefail
root=$1; gpu=$2; mode=$3
mk=$root/tb/cocotb/soc/Makefile
sed -n '/^PLL_SOURCES = /,/tb_soc_pll\.sv/p' "$mk" \
  | grep -v 'PLL_SOURCES\|tb_soc_pll\|SRAM_SIM_MODEL\|GPU_SRAM_SIM' \
  | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*\\$//' -e "s#^\$(RTL)#$root/rtl#" \
  | { if [ "$gpu" = nogpu ]; then grep -v '/rtl/gpu/'; else cat; fi; }
# PLL_SOURCES never lists rv32i_clock_gate.sv: Verilator finds it through -I rtl/mem, but sv2v has no -I
# auto-discovery and would silently blackbox it (CLAUDE.md, #94 sv2v note). List it explicitly.
echo "$root/rtl/mem/rv32i_clock_gate.sv"
if [ "$gpu" = nogpu ]; then echo "$root/pnr/sky130/soc/gpu_top_tieoff.sv"; fi
if [ "$mode" = sim ]; then
  echo "$root/sim/sram_1rw_256x32_verilator.v"
  if [ "$gpu" = gpu ]; then echo "$root/sim/sram_1rw_128x32_asap7.v"; fi
else
  ls "$root"/rtl/fpga/*.sv
fi
