#!/usr/bin/env bash
# Run the BerkeleyLab/Bedrock cdc_snitch clock-domain-crossing check on a
# SystemVerilog design: sv2v -> yosys (flatten to gates) -> cdc_snitch.py.
#
# This is an INFORMATIONAL check by default (CDC_STRICT=0): on this single-clock
# SoC, cdc_snitch reports thousands of false-positive BADs because it models
# every top-level input port (including the async reset and synchronous APB/SPI
# buses) as an independent clock domain. See tools/cdc/README.md and
# docs/verification/CDC_SNITCH_POC.md for the full story.
#
# Env (all optional except CDC_FLIST):
#   CDC_FLIST    newline-separated list of source files (required)
#   CDC_CACHE    tool/work dir            (default: <repo>/sim/build/cdc)
#   CDC_INCDIRS  space-separated incdirs  (default: none)
#   CDC_TOP      top module name          (default: soc_top)
#   CDC_STRICT   1 = exit non-zero on BAD>0 (gate); 0 = informational (default)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

CDC_CACHE="${CDC_CACHE:-$REPO_ROOT/sim/build/cdc}"
CDC_TOP="${CDC_TOP:-soc_top}"
CDC_STRICT="${CDC_STRICT:-0}"
CDC_INCDIRS="${CDC_INCDIRS:-}"
: "${CDC_FLIST:?set CDC_FLIST to a file listing the RTL sources}"

# Make cached sv2v / oss-cad-suite yosys discoverable without polluting PATH.
export PATH="$CDC_CACHE/oss-cad-suite/bin:$CDC_CACHE/sv2v-Linux:$PATH"

command -v sv2v   >/dev/null 2>&1 || { echo "ERROR: sv2v not found. Run tools/cdc/fetch_cdc_tools.sh"; exit 3; }
command -v yosys  >/dev/null 2>&1 || { echo "ERROR: yosys not found. Install yosys>=0.23 or run fetch_cdc_tools.sh --with-yosys"; exit 3; }
[[ -f "$CDC_CACHE/cdc_snitch.py" ]] || { echo "ERROR: cdc_snitch.py missing. Run tools/cdc/fetch_cdc_tools.sh"; exit 3; }

mkdir -p "$CDC_CACHE"
INC_FLAGS=()
for d in $CDC_INCDIRS; do INC_FLAGS+=("-I$d"); done

mapfile -t FILES < <(grep -vE '^\s*(#|$)' "$CDC_FLIST")

echo "== [1/3] sv2v: SystemVerilog -> Verilog-2005 =="
sv2v "${INC_FLAGS[@]}" "--top=$CDC_TOP" "${FILES[@]}" > "$CDC_CACHE/${CDC_TOP}_flat.v"

echo "== [2/3] yosys: elaborate + flatten -> JSON =="
yosys -q -p "read_verilog $CDC_CACHE/${CDC_TOP}_flat.v; script $CDC_CACHE/cdc_snitch_proc.ys; write_json $CDC_CACHE/${CDC_TOP}_yosys.json"

echo "== [3/3] cdc_snitch: categorize registers =="
set +e
python3 "$CDC_CACHE/cdc_snitch.py" "$CDC_CACHE/${CDC_TOP}_yosys.json" -o "$CDC_CACHE/${CDC_TOP}_cdc.txt"
rc=$?
set -e
echo "report: $CDC_CACHE/${CDC_TOP}_cdc.txt"

if [[ "$CDC_STRICT" -eq 1 ]]; then
  exit "$rc"
fi
echo "NOTE: informational mode (CDC_STRICT=0). On this single-clock SoC the BAD"
echo "      count is dominated by false positives (async reset + synchronous"
echo "      APB/SPI ports modeled as separate clock domains). Not a CI gate yet;"
echo "      see docs/verification/CDC_SNITCH_POC.md."
exit 0
