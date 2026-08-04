#!/usr/bin/env bash
# wrap-yosys.sh — run a Yosys script, emit a compact JSON verdict.
# Usage: wrap-yosys.sh <script.ys>            or  wrap-yosys.sh -p "<commands>"
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/eda_common.sh"
declare -a EDA_SUMMARIZE_EXTRA=()

eda::need yosys "run tools/cdc/fetch_cdc_tools.sh --with-yosys, or use the librelane nix-shell"

if [[ $# -ge 1 && -f "$1" && "$1" == *.ys ]]; then
  eda::run yosys "$(eda::logfile yosys)" -- yosys -s "$@"
else
  eda::run yosys "$(eda::logfile yosys)" -- yosys "$@"
fi
