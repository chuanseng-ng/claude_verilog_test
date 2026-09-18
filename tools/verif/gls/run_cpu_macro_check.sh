#!/usr/bin/env bash
# Bounded GLS functional check of the rv32i_cpu_top hard macro against a
# fixed 6-instruction RV32I program with known architectural results (bead
# claude_verilog_test-b0t part B CPU/GPU macro extension, 2026-09-18).
#
# Usage: run_cpu_macro_check.sh <netlist.nl.v> <out_dir> [mem_cap] [n_cycles]
#
# See tools/verif/gls/tb_cpu_macro_check.v for the full method writeup
# (why `sim -clock/-resetn`, not `-r`; the ICG + SRAM cell models this
# depends on) and bead claude_verilog_test-b0t's notes for the result.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NETLIST="$1"
OUT_DIR="$2"
MEM_CAP="${3:-8G}"
N_CYCLES="${4:-400}"

YOSYS=/nix/store/f1q0w7rd0a4ny4hqvfxlhs4cmariidcy-yosys-0.62/bin/yosys
LIBDIR=/home/neuromorphic/pdk/asap7/libs.ref/asap7sc7p5t_SIMPLE/lib

mkdir -p "$OUT_DIR"
python3 "$HERE/gen_cpu_check_rom.py" "$OUT_DIR/rom_cpu_check.hex" 64

YS="$OUT_DIR/cpu_gate_check.ys"
cat > "$YS" <<EOF
read_liberty -ignore_miss_func $LIBDIR/asap7sc7p5t_AO_RVT_TT_nldm_211120.lib
read_liberty -ignore_miss_func $LIBDIR/asap7sc7p5t_INVBUF_RVT_TT_nldm_220122.lib
read_liberty -ignore_miss_func $LIBDIR/asap7sc7p5t_OA_RVT_TT_nldm_211120.lib
read_liberty -ignore_miss_func $LIBDIR/asap7sc7p5t_SIMPLE_RVT_TT_nldm_211120.lib
read_verilog $HERE/asap7_seq_cell_models.v
read_verilog $HERE/asap7_sram_1rw_256x32_model.v
read_verilog $NETLIST
read_verilog $HERE/tb_cpu_macro_check.v
hierarchy -top tb_cpu_macro_check
proc
flatten
stat
sim -vcd $OUT_DIR/cpu_gate_out.vcd -clock clk_i -resetn rst_n_i -rstlen 5 -n $N_CYCLES -zinit tb_cpu_macro_check
EOF

cd "$OUT_DIR"
systemd-run --user --scope -p "MemoryMax=$MEM_CAP" -p MemorySwapMax=0 --collect \
  timeout 1800 "$YOSYS" -Q -T -l "$OUT_DIR/cpu_gate_check.log" "$YS"

echo "== errors =="
grep -c ERROR "$OUT_DIR/cpu_gate_check.log" || true
echo "== commit trace =="
python3 "$HERE/parse_cpu_commit_trace.py" "$OUT_DIR/cpu_gate_out.vcd"
