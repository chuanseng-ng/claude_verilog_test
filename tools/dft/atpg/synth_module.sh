#!/usr/bin/env bash
# synth_module.sh TOP OUTDIR
#
# Standalone sv2v + Yosys synthesis of one SoC block with the Sky130 tt Liberty (bead j41m.15, ladder rungs npu/crypto/dma).
# Same frontend as the flow (sv2v with the Sky130 SoC define set and file list, then Yosys); the recipe is the Stage 0 one
# (tools/dft/synth.ys): synth -flatten, dfflibmap, abc -liberty, hilomap.  It is NOT the LibreLane recipe, so cell counts
# differ from the PD netlist; the rung measures the ATPG tool on a block of that size, not the block's final netlist.
# Black boxes (the Sky130 4 KB SRAM) are kept as instances.
# Output: OUTDIR/TOP.v (gate netlist), OUTDIR/synth_stat.rpt.
set -eu
top=$1; out=$2
here=$(cd "$(dirname "$0")" && pwd)
root=$(cd "$here/../../.." && pwd)
YOSYS=${YOSYS:-/nobackup/claude_sim_build/j41m15/bin/yosys}
SV2V=${SV2V:-/nobackup/claude_sim_build/j41m15/bin/sv2v}
LIB=${LIB:-/nobackup/claude_sim_build/j41m15/in/tt.lib}
mkdir -p "$out"
inputs=$(make -s -C "$root/pnr" sky130-soc-sv2v-inputs)
defines=$(printf '%s\n' "$inputs" | sed -n 's/^DEFINES //p')
files=$(printf '%s\n' "$inputs" | sed -n 's/^FILE //p')
# shellcheck disable=SC2086
"$SV2V" $defines --top="$top" $files -w "$out/$top.sv2v.v" 2> "$out/sv2v.log"
cat > "$out/synth.ys" <<EOF
read_verilog -sv $out/$top.sv2v.v
hierarchy -top $top
blackbox sky130_sram_4kbyte_1rw1r_32x1024_8
synth -top $top -flatten
dfflibmap -liberty $LIB
abc -liberty $LIB
opt_clean -purge
hilomap -singleton -hicell sky130_fd_sc_hd__conb_1 HI -locell sky130_fd_sc_hd__conb_1 LO
opt_clean -purge
tee -o $out/synth_stat.rpt stat -liberty $LIB
write_verilog -noattr -noexpr -nohex -nodec $out/$top.v
EOF
"$YOSYS" -q -l "$out/yosys.log" "$out/synth.ys"
echo "synth $top: $(grep -m1 'Number of cells' "$out/synth_stat.rpt" | tr -s ' ')"
