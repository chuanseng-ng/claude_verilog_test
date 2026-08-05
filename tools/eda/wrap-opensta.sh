#!/usr/bin/env bash
# wrap-opensta.sh — run an OpenSTA Tcl script, emit a compact JSON verdict.
# Usage: wrap-opensta.sh <script.tcl> [sta args...]
#
# The reason this wrapper exists: `sta` exits 0 even when it reports violated
# paths, and an empty report is indistinguishable from a clean one at the exit
# code. summarize.py fails on violations and reports ERROR (2) on an empty
# report, so a gate built on this can actually fail. See bead `dwp`.
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/eda_common.sh"
declare -a EDA_SUMMARIZE_EXTRA=()

eda::need sta "PD tools live in the librelane nix-shell: cd ~/Downloads/Github/librelane && nix-shell --run '...'"

[[ $# -ge 1 ]] || { echo '{"tool":"opensta","status":"ERROR","exit_code":2,"summary":{"errors":["no Tcl script given"]}}'; exit 2; }
eda::run opensta "$(eda::logfile opensta)" -- sta -no_splash -exit "$@"
