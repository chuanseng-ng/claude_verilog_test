#!/usr/bin/env bash
# Independent-simulator confirmation (bead dud4): run the ORIGINAL ma7/u99 yosys
# `sim -clock/-resetn` harness (tools/verif/gls/tb_cpu_macro_check.v, unmodified)
# on the Sky130 CPU macro netlist, with the sky130_fd_sc_hd Liberty models
# (yosys read_liberty -> cycle-based, race-free sequential model).
#
# This exists to rule out a Verilator zero-delay/UDP scheduling race as the cause
# of the gate-vs-RTL differences seen with tb_sky130_cpu_check.sv.
#
# usage: run_yosys_gate_check.sh <netlist.nl.v> <rom.hex> <out_dir> <halt_cyc> <read_cyc> <n_cycles>
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GLS="$HERE/.."
NETLIST="$1"; ROM="$2"; OUT="$3"; HALT="$4"; READ="$5"; NCYC="$6"
YOSYS="${YOSYS:-/nix/store/f1q0w7rd0a4ny4hqvfxlhs4cmariidcy-yosys-0.62/bin/yosys}"
LIB="${SKY130_LIB:-$HOME/.ciel/ciel/sky130/versions/0fe599b2afb6708d281543108caf8310912f54af/sky130A/libs.ref/sky130_fd_sc_hd/lib/sky130_fd_sc_hd__tt_025C_1v80.lib}"
SRAM="${SRAM_MODEL:-/nobackup/claude_sim_build/dud4/rtl_5c49ddf/sim/sky130_sram_1kbyte_1rw1r_32x256_8.sv}"
mkdir -p "$OUT"
cp "$ROM" "$OUT/rom_cpu_check.hex"
cat > "$OUT/check.ys" <<EOF
read_liberty -ignore_miss_func $LIB
read_verilog -sv $SRAM
read_verilog $NETLIST
read_verilog $GLS/tb_cpu_macro_check.v
hierarchy -top tb_cpu_macro_check
chparam -set HALT_START_CYC $HALT -set READ_START_CYC $READ tb_cpu_macro_check
proc
flatten
sim -vcd $OUT/out.vcd -clock clk_i -resetn rst_n_i -rstlen 5 -n $NCYC -zinit tb_cpu_macro_check
EOF
cd "$OUT"
timeout 3000 "$YOSYS" -Q -T -l "$OUT/check.log" "$OUT/check.ys" > /dev/null 2>&1 || true
echo "errors: $(grep -c ERROR "$OUT/check.log" || true)"
python3 "$GLS/parse_cpu_commit_trace.py" "$OUT/out.vcd" | head -20
