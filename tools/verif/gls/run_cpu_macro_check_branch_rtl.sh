#!/usr/bin/env bash
# Arm 3 (frontend-independent RTL reference, Verilator) of the bead ma7
# step-1 branch-dependent regfile read-port check. Mirrors u99's un-committed
# scratch Verilator harness, but is committed here since this check's
# decisiveness depends on it being reproducible.
#
# Builds tb_verilator_top_branch.v + the UNMODIFIED tb_cpu_macro_check.v
# against the CPU-only RTL source list (rv32i_cpu_top + its full core/
# pipeline/cache tree), using the project's Verilator-compatible behavioural
# SRAM model (sim/sram_1rw_256x32_verilator.v, SRAM_TARGET=freepdk45 -- same
# default sim/Makefile uses for the CPU-only VERILOG_SOURCES list).
#
# MUST be run inside `nix develop` at the repo root (Verilator is not on the
# system PATH -- see docs project memory reference_verilator_env.md).
#
# Usage: run_cpu_macro_check_branch_rtl.sh <out_dir> [mem_cap]
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$HERE/../../.." && pwd)"
OUT_DIR="$1"
MEM_CAP="${2:-4G}"

command -v verilator >/dev/null 2>&1 || {
  echo "ERROR: verilator not on PATH -- run this inside 'nix develop' at the repo root." >&2
  exit 3
}

mkdir -p "$OUT_DIR"
python3 "$HERE/gen_cpu_check_rom_branch.py" "$OUT_DIR/rom_cpu_check.hex" 64

RTL="$REPO_ROOT/rtl"
SIM="$REPO_ROOT/sim"

SOURCES=(
  "$SIM/sram_1rw_256x32_verilator.v"
  "$RTL/soc/axi_pkg.sv"
  "$RTL/soc/soc_addr_map_pkg.sv"
  "$RTL/cpu/core/rv32i_pipeline_pkg.sv"
  "$RTL/mem/rv32i_cache_pkg.sv"
  "$RTL/cpu/core/rv32i_alu.sv"
  "$RTL/cpu/core/rv32i_imm_gen.sv"
  "$RTL/cpu/core/rv32i_regfile.sv"
  "$RTL/cpu/core/rv32i_decode.sv"
  "$RTL/cpu/core/rv32i_branch_comp.sv"
  "$RTL/cpu/core/rv32i_hazard_unit.sv"
  "$RTL/cpu/core/rv32i_forwarding_unit.sv"
  "$RTL/cpu/core/rv32i_csr_file.sv"
  "$RTL/cpu/core/rv32i_interrupt_ctrl.sv"
  "$RTL/mem/rv32i_icache.sv"
  "$RTL/mem/rv32i_dcache.sv"
  "$RTL/mem/rv32i_cache_arbiter.sv"
  "$RTL/cpu/core/pipeline/rv32i_pipeline_if.sv"
  "$RTL/cpu/core/pipeline/rv32i_pipeline_id.sv"
  "$RTL/cpu/core/pipeline/rv32i_pipeline_ex.sv"
  "$RTL/cpu/core/pipeline/rv32i_pipeline_ex1b.sv"
  "$RTL/cpu/core/pipeline/rv32i_pipeline_ex1c.sv"
  "$RTL/cpu/core/pipeline/rv32i_pipeline_ex2.sv"
  "$RTL/cpu/core/pipeline/rv32i_pipeline_mem.sv"
  "$RTL/cpu/core/pipeline/rv32i_pipeline_wb.sv"
  "$RTL/cpu/core/rv32i_core.sv"
  "$RTL/cpu/rv32i_cpu_top.sv"
  "$HERE/tb_cpu_macro_check.v"
  "$HERE/tb_verilator_top_branch.v"
)

BUILD_DIR="$OUT_DIR/vbuild"
mkdir -p "$BUILD_DIR"

systemd-run --user --scope -p "MemoryMax=$MEM_CAP" -p MemorySwapMax=0 --collect \
  timeout 600 verilator --binary --timing --trace -Wno-fatal -Wno-WIDTH -Wno-CASEINCOMPLETE -Wno-UNOPTFLAT \
  -I"$RTL/cpu/core" -I"$RTL/mem" -I"$RTL/soc" \
  --top-module tb_verilator_top_branch \
  "${SOURCES[@]}" \
  -o Vtb_branch --Mdir "$BUILD_DIR" \
  2>&1 | tee "$OUT_DIR/verilator_build.log"

cd "$BUILD_DIR"
cp "$OUT_DIR/rom_cpu_check.hex" .
systemd-run --user --scope -p "MemoryMax=$MEM_CAP" -p MemorySwapMax=0 --collect \
  timeout 300 ./Vtb_branch 2>&1 | tee "$OUT_DIR/cpu_rtl_branch_check.log"
cp cpu_rtl_branch_out.vcd "$OUT_DIR/" 2>/dev/null || true

echo "== commit trace (RTL/Verilator) =="
python3 "$HERE/parse_cpu_commit_trace.py" "$BUILD_DIR/cpu_rtl_branch_out.vcd"
