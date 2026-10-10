#!/usr/bin/env bash
# Derive behavioural Verilog for the ASAP7 combinational standard cells from the Liberty
# `function` attributes (ASAP7 ships no Verilog models). Sequential cells and the ICG are
# NOT derived: they come from ../asap7_seq_cell_models.v.
# usage: gen_cell_lib.sh <out.v>   (env YOSYS, ASAP7_LIB)
set -euo pipefail
OUT="$1"
YOSYS="${YOSYS:-/nix/store/f1q0w7rd0a4ny4hqvfxlhs4cmariidcy-yosys-0.62/bin/yosys}"
L="${ASAP7_LIB:-$HOME/pdk/asap7/libs.ref/asap7sc7p5t_SIMPLE/lib}"
T="$(mktemp -d)"
cat > "$T/g.ys" <<EOT
read_liberty -ignore_miss_func $L/asap7sc7p5t_AO_RVT_TT_nldm_211120.lib
read_liberty -ignore_miss_func $L/asap7sc7p5t_INVBUF_RVT_TT_nldm_220122.lib
read_liberty -ignore_miss_func $L/asap7sc7p5t_OA_RVT_TT_nldm_211120.lib
read_liberty -ignore_miss_func $L/asap7sc7p5t_SIMPLE_RVT_TT_nldm_211120.lib
write_verilog -noattr $OUT
EOT
timeout 600 "$YOSYS" -q "$T/g.ys"
echo "wrote $OUT: $(grep -c '^module' "$OUT") cell models"
