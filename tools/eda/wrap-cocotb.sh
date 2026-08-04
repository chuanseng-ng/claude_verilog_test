#!/usr/bin/env bash
# wrap-cocotb.sh — run a cocotb suite via make, emit a compact JSON verdict.
# Usage: wrap-cocotb.sh <make-dir> <target> [make args...]
#   e.g. wrap-cocotb.sh tb/cocotb/soc async_axi_fifo
#
# For interactive use prefer plain `nix develop --command make -C <dir> <target>`:
# the .rtk/filters.toml `soc-sim` filter already compresses that to the tally
# line. This wrapper is for gates and machine consumers that need the structured
# {passed, failed, failures[]} verdict and a non-zero exit on a missing results.xml.
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/eda_common.sh"

MAKE_DIR="${1:?usage: wrap-cocotb.sh <make-dir> <target> [make args...]}"
TARGET="${2:?usage: wrap-cocotb.sh <make-dir> <target> [make args...]}"
shift 2

eda::need make "install make, or enter the sim devshell"

RESULTS_XML="$REPO_ROOT/$MAKE_DIR/results.xml"
rm -f "$RESULTS_XML"   # a stale file from a previous suite would be read as this run's result

declare -a EDA_SUMMARIZE_EXTRA=(--results-xml "$RESULTS_XML")
eda::run cocotb "$(eda::logfile cocotb)" -- make -C "$REPO_ROOT/$MAKE_DIR" "$TARGET" "$@"
