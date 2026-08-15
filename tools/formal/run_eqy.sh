#!/usr/bin/env bash
# tools/formal/run_eqy.sh — EQY sv2v-vs-RTL equivalence entrypoint (bead claude_verilog_test-q7n).
#
# eqy/yosys/sby are only available inside the librelane nix devshell (not on
# this repo's bare PATH, not in this repo's own flake.nix). This wrapper pays
# the nix devshell startup cost exactly once per invocation and runs
# run_eqy.py for every module requested in one session — pass multiple
# --module flags, --tier N, or --all rather than calling this repeatedly.
#
# Usage:
#   tools/formal/run_eqy.sh --tier 1
#   tools/formal/run_eqy.sh --module cdc_2ff_sync --module dma_engine
#   tools/formal/run_eqy.sh --all --pnr-negative-control
#
# Exit code is run_eqy.py's aggregate verdict (0 PASS / 1 FAIL / 2 ERROR / 3 no match).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
LIBRELANE_DIR="${LIBRELANE_DIR:-$HOME/Downloads/Github/librelane}"

if [[ ! -d "$LIBRELANE_DIR" ]]; then
  echo "ERROR: librelane devshell not found at $LIBRELANE_DIR (set LIBRELANE_DIR to override)." >&2
  exit 3
fi

exec nix develop "$LIBRELANE_DIR" --command python3 "$SCRIPT_DIR/run_eqy.py" "$@"
