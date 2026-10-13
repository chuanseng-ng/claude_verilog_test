#!/usr/bin/env bash
# run_oldnew.sh - old-vs-new equivalence of every module edited by the ainf wire-first rewrite,
# plus a negative control per module (one select deliberately corrupted in a scratch copy of the NEW
# tree; the miter must then report NOT-EQUIV, proving the check is not vacuous).
#
# usage: run_oldnew.sh <old-root> <new-root> <outdir>
#   <old-root>/<new-root> each contain an rtl/ tree  (old: git archive <pre-rewrite rev> rtl | tar -x)
# Every miter is memory-capped at 4G (systemd-run scope).  Output: one line per
# module/frontend/mode  ->  EQUIV (expected) for "real", NOT-EQUIV (expected) for "negctl".
set -u
OLD=$1; NEW=$2; OUT=$3
HERE=$(cd "$(dirname "$0")" && pwd)
EQ="$HERE/oldnew_eq.sh"
C=rtl/cpu/core
G=rtl/gpu
mkdir -p "$OUT"

run() {  # run <mode> <newroot> <module-dir> <top> <files> [bb] [keep]
  local mode=$1 nr=$2 dir=$3; shift 3
  echo "== $mode"
  systemd-run --user --scope -q -p MemoryMax=4G -p MemorySwapMax=0 \
    "$EQ" "$OUT/$mode/$dir" "$1" "$OLD" "$nr" "${@:2}"
}

all() {  # all <mode> <newroot>
  local m=$1 nr=$2
  run "$m" "$nr" wb   rv32i_pipeline_wb   "$C/rv32i_pipeline_pkg.sv $C/pipeline/rv32i_pipeline_wb.sv"
  run "$m" "$nr" ex1c rv32i_pipeline_ex1c "$C/rv32i_pipeline_pkg.sv $C/pipeline/rv32i_pipeline_ex1c.sv"
  run "$m" "$nr" mem  rv32i_pipeline_mem  "$C/rv32i_pipeline_pkg.sv $C/pipeline/rv32i_pipeline_mem.sv"
  run "$m" "$nr" ex   rv32i_pipeline_ex   "$C/rv32i_pipeline_pkg.sv $C/rv32i_alu.sv $C/rv32i_branch_comp.sv $C/pipeline/rv32i_pipeline_ex.sv"
}

all real "$NEW"

# GPU: cone of the id_ex_q -> VLD/VST/VLDS/VSTS address/data logic (see mkcone_oldnew.py for why the
# whole-module miter is not used).  Old cone from OLD, new cone from NEW, same frontends.
cone() {  # cone <mode> <newroot>
  local mode=$1 nr=$2
  rm -rf "$OUT/cone_$mode"; mkdir -p "$OUT/cone_$mode"
  python3 "$HERE/mkcone_oldnew.py" "$OLD" "$OUT/cone_$mode/old" || exit 2
  python3 "$HERE/mkcone_oldnew.py" "$nr" "$OUT/cone_$mode/new" || exit 2
  echo "== $mode (cone)"
  systemd-run --user --scope -q -p MemoryMax=4G -p MemorySwapMax=0 \
    "$EQ" "$OUT/$mode/cu_cone" gpu_cu_cone "$OUT/cone_$mode/old" "$OUT/cone_$mode/new" \
    "rtl/gpu/gpu_pkg.sv cone/gpu_cu_cone.sv"
}
cone real "$NEW"

# Negative controls: corrupt one select per edited file in a scratch copy of the new tree.
NEG="$OUT/negtree"
rm -rf "$NEG"; mkdir -p "$NEG"; cp -r "$NEW/rtl" "$NEG/rtl"
mut() { sed -i -E "$1" "$NEG/$2"; cmp -s "$NEW/$2" "$NEG/$2" && { echo "mutation did not apply to $2"; exit 2; }; }
mut 's/mem_wb_trap_cause_w\[3:0\]/mem_wb_trap_cause_w[4:1]/'      $C/pipeline/rv32i_pipeline_wb.sv
mut 's/case \(ex1a_alu_result_w\[1\]\)/case (ex1a_alu_result_w[2])/' $C/pipeline/rv32i_pipeline_ex1c.sv
mut 's/ex_mem_alu_result_w\[0\]/ex_mem_alu_result_w[1]/'          $C/pipeline/rv32i_pipeline_mem.sv
mut 's/csr_op_w\[2\]/csr_op_w[1]/'                               $C/pipeline/rv32i_pipeline_ex.sv
mut 's/mem_wdata_o\[l\] = id_ex_rs2_data_w\[l\]/mem_wdata_o[l] = id_ex_rs1_data_w[l]/' $G/gpu_compute_unit.sv
all negctl "$NEG"
cone negctl "$NEG"
