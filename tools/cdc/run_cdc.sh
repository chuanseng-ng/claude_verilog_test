#!/usr/bin/env bash
# Run the BerkeleyLab/Bedrock cdc_snitch clock-domain-crossing check on a
# SystemVerilog design: sv2v -> yosys (flatten to gates) -> cdc_snitch.py.
#
# cdc_snitch's own BAD count is NOT the verdict. It models every top-level input
# port as its own clock domain, cannot tell a clock-gate output from its source
# clock, and cannot express a qualified crossing -- on this SoC that puts the
# raw count in the thousands, essentially all modelling artifacts. The raw
# report is therefore post-processed by tools/cdc/cdc_gate.py, which
# canonicalizes domains (per tools/cdc/cdc_config.yml, mirroring
# pnr/constraints/phase5_soc_multiclock.sdc) and applies explicit justified
# waivers. The GATE's exit status is the verdict. See tools/cdc/README.md and
# docs/verification/CDC_SNITCH_POC.md.
#
# Env (all optional except CDC_FLIST):
#   CDC_FLIST    newline-separated list of source files (required)
#   CDC_CACHE    tool/work dir            (default: <repo>/sim/build/cdc)
#   CDC_INCDIRS  space-separated incdirs  (default: none)
#   CDC_TOP      top module name          (default: soc_top)
#   CDC_CONFIG   cdc_gate.py config       (default: tools/cdc/cdc_config.yml)
#   CDC_STRICT   1 = exit non-zero if the gate fails; 0 = informational (default)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

CDC_CACHE="${CDC_CACHE:-$REPO_ROOT/sim/build/cdc}"
CDC_TOP="${CDC_TOP:-soc_top}"
CDC_STRICT="${CDC_STRICT:-0}"
CDC_INCDIRS="${CDC_INCDIRS:-}"
CDC_CONFIG="${CDC_CONFIG:-$SCRIPT_DIR/cdc_config.yml}"
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

echo "== [3/4] cdc_snitch: categorize registers =="
# cdc_snitch exits non-zero whenever its raw BAD count is non-zero, which is
# expected here -- the gate below is what decides. Don't let set -e kill us.
set +e
python3 "$CDC_CACHE/cdc_snitch.py" "$CDC_CACHE/${CDC_TOP}_yosys.json" -o "$CDC_CACHE/${CDC_TOP}_cdc.txt"
set -e
echo "raw report: $CDC_CACHE/${CDC_TOP}_cdc.txt"

echo "== [4/4] cdc_gate: canonicalize domains + apply waivers =="
set +e
python3 "$SCRIPT_DIR/cdc_gate.py" "$CDC_CACHE/${CDC_TOP}_cdc.txt" \
  -c "$CDC_CONFIG" --json "$CDC_CACHE/${CDC_TOP}_cdc_gate.json"
rc=$?
set -e

if [[ "$rc" -eq 2 ]]; then
  echo "ERROR: cdc_gate.py could not run (bad config or unreadable report)." >&2
  exit 2
fi

if [[ "$CDC_STRICT" -eq 1 ]]; then
  exit "$rc"
fi
if [[ "$rc" -ne 0 ]]; then
  echo
  echo "NOTE: informational mode (CDC_STRICT=0) -- the gate FAILED but this run"
  echo "      still exits 0. Re-run with CDC_STRICT=1 for gate semantics."
fi
exit 0
