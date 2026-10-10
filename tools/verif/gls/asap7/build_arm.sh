#!/usr/bin/env bash
# Build one arm of the bead ma7 / dud4 ASAP7 differential with Verilator.
#
#   build_arm.sh rtl  <outdir>                 RTL arm  (RTL_ROOT tree, +define SRAM_ASAP7 USE_ICG_CELL)
#   build_arm.sh gate <outdir> <netlist.v>     gate arm (ASAP7 rv32i_cpu_top netlist)
#
# Both arms compile the SAME testbench (../sky130/tb_sky130_cpu_check.sv or the
# TB named by TB=) and the SAME behavioural models for the two ASAP7 macros the
# CPU contains (asap7_sram_1rw_256x32_model.v, ICGx1 in asap7_seq_cell_models.v).
# They differ only in what implements rv32i_cpu_top.
#
# The gate arm needs behavioural Verilog for the combinational ASAP7 cells. ASAP7
# ships none, so gen_cell_lib.sh derives it from the Liberty `function` attributes
# (yosys read_liberty + write_verilog): CELLLIB=<that file>.
# Physical-only cells (DECAP*, FILLER*, TAPCELL; zero ports) of a post-P&R netlist must be
# stripped first: strip_physical.sh.
#
# Environment: RTL_ROOT (tree with rtl/), CELLLIB, VERILATOR_BIN/VERILATOR_ROOT, TB.
set -euo pipefail
ARM="$1"
OUT="$2"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GLS="$HERE/.."
REPO="$(cd "$GLS/../../.." && pwd)"

VBIN="${VERILATOR_BIN:-/nix/store/xjx9zx3vaz367c7lbnvsd1isvqfkmgg7-verilator-5.048/bin/verilator}"
export VERILATOR_ROOT="${VERILATOR_ROOT:-/nix/store/xjx9zx3vaz367c7lbnvsd1isvqfkmgg7-verilator-5.048/share/verilator}"
RTL_ROOT="${RTL_ROOT:-$REPO}"
CELLLIB="${CELLLIB:-/nobackup/claude_sim_build/dud4/asap7_sim/asap7_comb_cells.v}"
TB="${TB:-$HERE/tb_asap7_cpu_check.sv}"
TOP="$(basename "$TB" | sed 's/\.sv$//')"
MODELS=("$GLS/asap7_sram_1rw_256x32_model.v" "$GLS/asap7_seq_cell_models.v")

mkdir -p "$OUT"
PROBE=()
[ -n "${PROBE_FILE:-}" ] && PROBE=("-DPROBE_FILE=\"$PROBE_FILE\"")
COMMON=(--binary --timing -Wno-fatal -Wno-lint -Wno-style -Wno-TIMESCALEMOD --build-jobs 2
        --top-module "$TOP" -o Vtb ${PROBE[@]+"${PROBE[@]}"})

case "$ARM" in
  rtl)
    R="$RTL_ROOT/rtl"
    # Same order as pnr/asap7/cpu/config.json CPU_SV_FILES, minus the SRAM / ICG stubs
    # (replaced by the behavioural models).
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
      "$R/mem/rv32i_clock_gate.sv"
      "$R/mem/rv32i_icache.sv" "$R/mem/rv32i_dcache.sv" "$R/mem/rv32i_cache_arbiter.sv"
      "$R/cpu/core/rv32i_core.sv" "$R/cpu/rv32i_cpu_top.sv"
      "${MODELS[@]}" "$TB"
    )
    "$VBIN" "${COMMON[@]}" +define+SRAM_ASAP7 +define+USE_ICG_CELL \
      -I"$R/cpu/core" -I"$R/mem" -I"$R/soc" \
      --Mdir "$OUT/obj" "${SRC[@]}" 2>&1 | tee "$OUT/build.log" | tail -5
    ;;
  gate)
    NETLIST="$3"
    "$VBIN" "${COMMON[@]}" --Mdir "$OUT/obj" "$CELLLIB" "${MODELS[@]}" "$NETLIST" "$TB" \
      2>&1 | tee "$OUT/build.log" | tail -5
    ;;
  *) echo "usage: $0 rtl|gate <outdir> [netlist]" >&2; exit 2 ;;
esac
ls -la "$OUT/obj/Vtb"
