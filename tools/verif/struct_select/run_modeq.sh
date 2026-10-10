#!/usr/bin/env bash
# usage: run_modeq.sh <repo-root> <outroot> <module-set: cpu|gpu|neg>
# Per-module Synlig-vs-sv2v equivalence of the modules that contain struct-member selects (bead ainf).
set -u
RR=$1; OUT=$2; SET=$3
HERE=$(cd "$(dirname "$0")" && pwd)
M="$HERE/modeq.sh"
C="$RR/rtl/cpu/core"
G="$RR/rtl/gpu"
cd "$OUT" || exit 2
case "$SET" in
  cpu)
    "$M" "$OUT/wb"   rv32i_pipeline_wb   "$C/rv32i_pipeline_pkg.sv $C/pipeline/rv32i_pipeline_wb.sv"
    "$M" "$OUT/ex1c" rv32i_pipeline_ex1c "$C/rv32i_pipeline_pkg.sv $C/pipeline/rv32i_pipeline_ex1c.sv"
    "$M" "$OUT/mem"  rv32i_pipeline_mem  "$C/rv32i_pipeline_pkg.sv $C/pipeline/rv32i_pipeline_mem.sv"
    "$M" "$OUT/ex"   rv32i_pipeline_ex   "$C/rv32i_pipeline_pkg.sv $C/rv32i_alu.sv $C/rv32i_branch_comp.sv $C/pipeline/rv32i_pipeline_ex.sv"
    ;;
  gpu)
    "$M" "$OUT/cu" gpu_compute_unit "$G/gpu_pkg.sv $G/vector_register_file.sv $G/vector_alu.sv $G/gpu_compute_unit.sv" "vector_register_file vector_alu"
    ;;
  *) echo "unknown set $SET"; exit 2 ;;
esac
