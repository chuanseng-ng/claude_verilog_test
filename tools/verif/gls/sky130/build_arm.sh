#!/usr/bin/env bash
# Build one arm of the bead-dud4 differential with Verilator.
#
#   build_arm.sh rtl  <outdir>                 RTL arm   (pinned-commit RTL tree)
#   build_arm.sh gate <outdir> [netlist.v]     gate arm  (Sky130 macro netlist)
#
# Both arms compile the SAME testbench (tb_sky130_cpu_check.sv) and the SAME
# SRAM behavioural model (sim/sky130_sram_1kbyte_1rw1r_32x256_8.sv, the model
# the cache RTL is simulated with under +define+SRAM_SKY130). They differ only
# in what implements rv32i_cpu_top.
#
# Environment (defaults match the dud4 session; override as needed):
#   RTL_ROOT   tree containing rtl/ and sim/ at the commit the netlist was
#              synthesised from (default: extracted by extract_rtl.sh)
#   NETLIST    gate netlist (default: gunzip of pnr/sky130/cpu/macro/rv32i_cpu_top.nl.v.gz)
#   PDK_VLOG   sky130_fd_sc_hd/verilog dir of the PDK (functional models)
#   VERILATOR_BIN / VERILATOR_ROOT   Verilator install (5.048 used)
set -euo pipefail
ARM="$1"
OUT="$2"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../../../.." && pwd)"

VBIN="${VERILATOR_BIN:-/nix/store/xjx9zx3vaz367c7lbnvsd1isvqfkmgg7-verilator-5.048/bin/verilator}"
export VERILATOR_ROOT="${VERILATOR_ROOT:-/nix/store/xjx9zx3vaz367c7lbnvsd1isvqfkmgg7-verilator-5.048/share/verilator}"
PDK_VLOG="${PDK_VLOG:-$HOME/.ciel/ciel/sky130/versions/0fe599b2afb6708d281543108caf8310912f54af/sky130A/libs.ref/sky130_fd_sc_hd/verilog}"
RTL_ROOT="${RTL_ROOT:-/nobackup/claude_sim_build/dud4/rtl_5c49ddf}"
SRAM_MODEL="$RTL_ROOT/sim/sky130_sram_1kbyte_1rw1r_32x256_8.sv"
TB="$HERE/tb_sky130_cpu_check.sv"

mkdir -p "$OUT"
# Optional probes: PROBE_FILE=<path from gen_probes.py> adds hierarchical taps
# (ID/EX register + regfile storage) under the same names in both arms.
PROBE=()
[ -n "${PROBE_FILE:-}" ] && PROBE=("-DPROBE_FILE=\"$PROBE_FILE\"")
COMMON=(--binary --timing -Wno-fatal -Wno-lint -Wno-style -Wno-TIMESCALEMOD --build-jobs 2
        --top-module tb_sky130_cpu_check -o Vtb ${PROBE[@]+"${PROBE[@]}"})

case "$ARM" in
  rtl)
    R="$RTL_ROOT/rtl"
    # Same file list/order as pnr/sky130/cpu/config.json VERILOG_FILES (unchanged
    # between the netlist's source commit and HEAD), minus the SRAM stub.
    SRC=(
      "$R/soc/axi_pkg.sv" "$R/soc/soc_addr_map_pkg.sv"
      "$R/cpu/core/rv32i_pipeline_pkg.sv" "$R/mem/rv32i_cache_pkg.sv"
      "$R/cpu/core/rv32i_alu.sv" "$R/cpu/core/rv32i_branch_comp.sv"
      "$R/cpu/core/rv32i_imm_gen.sv" "$R/cpu/core/rv32i_regfile.sv"
      "$R/cpu/core/rv32i_decode.sv" "$R/cpu/core/rv32i_forwarding_unit.sv"
      "$R/cpu/core/rv32i_hazard_unit.sv" "$R/cpu/core/rv32i_interrupt_ctrl.sv"
      "$R/cpu/core/rv32i_csr_file.sv"
      "$R/cpu/core/pipeline/rv32i_pipeline_if.sv" "$R/cpu/core/pipeline/rv32i_pipeline_id.sv"
      "$R/cpu/core/pipeline/rv32i_pipeline_ex.sv" "$R/cpu/core/pipeline/rv32i_pipeline_ex1c.sv"
      "$R/cpu/core/pipeline/rv32i_pipeline_ex1b.sv" "$R/cpu/core/pipeline/rv32i_pipeline_ex2.sv"
      "$R/cpu/core/pipeline/rv32i_pipeline_mem.sv" "$R/cpu/core/pipeline/rv32i_pipeline_wb.sv"
      "$R/mem/rv32i_icache.sv" "$R/mem/rv32i_dcache.sv" "$R/mem/rv32i_cache_arbiter.sv"
      "$R/cpu/core/rv32i_core.sv" "$R/cpu/rv32i_cpu_top.sv"
      "$SRAM_MODEL" "$TB"
    )
    "$VBIN" "${COMMON[@]}" +define+SRAM_SKY130 -I"$R/cpu/core" -I"$R/mem" -I"$R/soc" \
      --Mdir "$OUT/obj" "${SRC[@]}" 2>&1 | tee "$OUT/build.log" | tail -5
    ;;
  gate)
    NETLIST="${3:-${NETLIST:-/nobackup/claude_sim_build/dud4/rv32i_cpu_top.nl.v}}"
    "$VBIN" "${COMMON[@]}" -DFUNCTIONAL '-DUNIT_DELAY=' \
      --Mdir "$OUT/obj" "$PDK_VLOG/primitives.v" "$PDK_VLOG/sky130_fd_sc_hd.v" \
      "$SRAM_MODEL" "$NETLIST" "$TB" 2>&1 | tee "$OUT/build.log" | tail -5
    ;;
  *) echo "usage: $0 rtl|gate <outdir> [netlist]" >&2; exit 2 ;;
esac
ls -la "$OUT/obj/Vtb"
