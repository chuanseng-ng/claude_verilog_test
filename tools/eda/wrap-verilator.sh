#!/usr/bin/env bash
# wrap-verilator.sh — run Verilator, emit a compact JSON verdict.
# Usage: wrap-verilator.sh [verilator args...]      (e.g. --lint-only -Wall f.sv)
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/eda_common.sh"
declare -a EDA_SUMMARIZE_EXTRA=()

eda::need verilator "enter the sim devshell: nix develop --command <cmd>"
eda::run verilator "$(eda::logfile verilator)" -- verilator "$@"
