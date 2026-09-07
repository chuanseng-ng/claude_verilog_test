#!/usr/bin/env bash
# wrap-bambu.sh — run Bambu HLS, emit a compact JSON verdict.
# Usage: wrap-bambu.sh <out-dir> <top-fname> [bambu args...]
#   e.g. wrap-bambu.sh /nobackup/hls/out/gate_b coal_shape /abs/path/gate_b.c \
#          --generate-interface=INFER --simulate --simulator=VERILATOR
#
# NOTE: pass SOURCE AND TESTBENCH PATHS AS ABSOLUTE. This wrapper cd's into
# <out-dir> before running, because Bambu writes <top-fname>.v and its HLS_output/
# tree into the current directory and `-o` does NOT relocate them; running in
# place would scatter build artefacts through the source tree.
#
# Bambu exits 0 on a generation-only run that produced nothing useful, and its
# co-simulation can die without the HLS phase noticing. The verdict therefore
# comes from summarize.py, which cross-checks the log against the generated .v
# and against whether the recorded command line asked for --simulate. See bead
# `dwp`.
#
# Must run inside the HLS devshell: Bambu locates Verilator with a literal
# `which verilator`, so a Verilator outside the FHS sandbox is invisible to it.
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/eda_common.sh"

OUT_DIR="${1:?usage: wrap-bambu.sh <out-dir> <top-fname> [bambu args...]}"
TOP="${2:?usage: wrap-bambu.sh <out-dir> <top-fname> [bambu args...]}"
shift 2

eda::need bambu "enter the HLS devshell: nix develop .#hls --command <cmd>"

# json_err: emit the ERROR reply with the message JSON-encoded as a whole, so a
# caller-supplied path holding a quote or backslash cannot produce invalid JSON.
json_err() {
  python3 -c 'import json,sys; print(json.dumps({"tool":"bambu","status":"ERROR","exit_code":2,"summary":{"errors":[sys.argv[1]]}}))' "$1"
}

mkdir -p "$OUT_DIR" 2>/dev/null || {
  json_err "cannot create out dir: $OUT_DIR"
  exit 2
}
OUT_DIR="$(cd "$OUT_DIR" && pwd -P)"

# Bambu names the top module after the top function, so this is the artefact the
# run must produce. Delete any stale copy first: a leftover .v from a previous
# run would otherwise be hashed and reported as this run's output.
VERILOG="$OUT_DIR/$TOP.v"
rm -f "$VERILOG"

cd "$OUT_DIR"

declare -a EDA_SUMMARIZE_EXTRA=(--verilog "$VERILOG")
eda::run bambu "$(eda::logfile bambu)" -- bambu --top-fname="$TOP" "$@"
