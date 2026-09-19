#!/usr/bin/env bash
# Bounded GLS branch-dependent regfile-read-port check of the rv32i_cpu_top
# hard macro (bead claude_verilog_test-ma7 step 1, 2026-09-19).
#
# Identical harness/method to run_cpu_macro_check.sh (same tb_cpu_macro_check.v,
# unchanged) but with gen_cpu_check_rom_branch.py's branch-dependent program
# instead of gen_cpu_check_rom.py's straight-line one, so the check exercises
# the ID-stage regfile read ports (rd_data1/rd_data2) via commit_pc_o /
# commit_insn_o -- NOT the known-corrupt APB debug read port.
#
# Usage: run_cpu_macro_check_branch.sh <netlist.nl.v> <out_dir> [mem_cap] [n_cycles]
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NETLIST="$1"
OUT_DIR="$2"
MEM_CAP="${3:-8G}"
N_CYCLES="${4:-1500}"

YOSYS=/nix/store/f1q0w7rd0a4ny4hqvfxlhs4cmariidcy-yosys-0.62/bin/yosys
LIBDIR=/home/neuromorphic/pdk/asap7/libs.ref/asap7sc7p5t_SIMPLE/lib

mkdir -p "$OUT_DIR"
python3 "$HERE/gen_cpu_check_rom_branch.py" "$OUT_DIR/rom_cpu_check.hex" 64

YS="$OUT_DIR/cpu_gate_check_branch.ys"
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
chparam -set HALT_START_CYC 300 -set READ_START_CYC 340 tb_cpu_macro_check
proc
flatten
stat
sim -vcd $OUT_DIR/cpu_gate_out_branch.vcd -clock clk_i -resetn rst_n_i -rstlen 5 -n $N_CYCLES -zinit tb_cpu_macro_check
EOF

cd "$OUT_DIR"
systemd-run --user --scope -p "MemoryMax=$MEM_CAP" -p MemorySwapMax=0 --collect \
  timeout 1800 "$YOSYS" -Q -T -l "$OUT_DIR/cpu_gate_check_branch.log" "$YS"

echo "== errors =="
grep -c ERROR "$OUT_DIR/cpu_gate_check_branch.log" || true
echo "== commit trace =="
python3 "$HERE/parse_cpu_commit_trace.py" "$OUT_DIR/cpu_gate_out_branch.vcd"
