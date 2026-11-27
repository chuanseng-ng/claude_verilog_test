#!/usr/bin/env bash
# build_replay.sh BUILD_DIR VECTOR_DIR [--harness-only]   (bead j41m.19)
#   BUILD_DIR   output of replay_netlist.py (soc_replay.v, replay_top.v)
#   VECTOR_DIR  output of replay_vectors.py (params_h.h, compiled into the harness)
# Step 1 (about 45 min, 3.8 GiB RSS): Verilator 5.048 --cc build of replay_top (the gate netlist with the PDK functional models, as
#   tools/verif/gls/sky130/build_arm.sh does for the CPU macro) into BUILD_DIR/obj, archived as Vreplay_top__ALL.a.
# Step 2 (seconds): g++ of replay_main.cpp against that archive -> BUILD_DIR/Vreplay.  --harness-only redoes only step 2.
set -euo pipefail
B=$(readlink -f "$1"); V=$(readlink -f "$2")
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GLS="$HERE/../../verif/gls/sky130"
VROOT="${VERILATOR_ROOT:-/nix/store/xjx9zx3vaz367c7lbnvsd1isvqfkmgg7-verilator-5.048/share/verilator}"
VBIN="${VERILATOR_BIN:-/nix/store/xjx9zx3vaz367c7lbnvsd1isvqfkmgg7-verilator-5.048/bin/verilator}"
export VERILATOR_ROOT="$VROOT"
unset VERILATOR_BIN
PDK_VLOG="${PDK_VLOG:-$HOME/.ciel/ciel/sky130/versions/0fe599b2afb6708d281543108caf8310912f54af/sky130A/libs.ref/sky130_fd_sc_hd/verilog}"
if [ "${3:-}" != "--harness-only" ] && [ "${2:-}" != "--harness-only" ]; then
  sed 's/sky130_fd_sc_hd__conb_1 /dud4_conb /' "$B/soc_replay.v" > "$B/soc_replay.conb.v"
  "$VBIN" --cc --timing -Wno-fatal -Wno-lint -Wno-style -Wno-TIMESCALEMOD --build --build-jobs "${JOBS:-2}" \
      --top-module replay_top -DFUNCTIONAL '-DUNIT_DELAY=' --Mdir "$B/obj" \
      "$PDK_VLOG/primitives.v" "$PDK_VLOG/sky130_fd_sc_hd.v" "$GLS/conb_model.v" \
      "$B/soc_replay.conb.v" "$B/replay_top.v" > "$B/build.log" 2>&1
fi
g++ -O1 -std=c++20 -fcoroutines -I"$B/obj" -I"$V" -I"$VROOT/include" -I"$VROOT/include/vltstd" -DVL_TIME_CONTEXT \
    "$HERE/replay_main.cpp" "$B/obj/Vreplay_top__ALL.a" "$B/obj/libverilated.a" -o "$B/Vreplay" -lpthread
ls -la "$B/Vreplay"
