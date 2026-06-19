#!/usr/bin/env bash
# Fetch the (pinned) tools used by the CDC check into the cache dir.
#
#   - cdc_snitch.py + cdc_snitch_proc.ys  (BerkeleyLab/Bedrock, pinned commit)
#   - sv2v                                (zachjs/sv2v, pinned release)
#   - oss-cad-suite (yosys)               (only with --with-yosys)
#
# Idempotent: existing files are left in place unless --force is given.
#
# Usage:
#   tools/cdc/fetch_cdc_tools.sh [--with-yosys] [--force]
#
# Env:
#   CDC_CACHE   destination dir (default: <repo>/sim/build/cdc)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/versions.env"

CDC_CACHE="${CDC_CACHE:-$REPO_ROOT/sim/build/cdc}"
WITH_YOSYS=0
FORCE=0
for arg in "$@"; do
  case "$arg" in
    --with-yosys) WITH_YOSYS=1 ;;
    --force)      FORCE=1 ;;
    *) echo "unknown arg: $arg" >&2; exit 2 ;;
  esac
done

mkdir -p "$CDC_CACHE"
cd "$CDC_CACHE"

fetch() {  # fetch <url> <dest>
  local url="$1" dest="$2"
  if [[ -s "$dest" && "$FORCE" -eq 0 ]]; then
    echo "  [skip] $dest (exists)"
    return
  fi
  echo "  [get ] $dest"
  curl -fsSL --retry 4 --retry-delay 2 --max-time 600 -o "$dest" "$url"
}

echo "== cdc_snitch (Bedrock @ ${BEDROCK_SHA:0:12}) =="
base="https://raw.githubusercontent.com/BerkeleyLab/Bedrock/${BEDROCK_SHA}/build-tools"
fetch "$base/cdc_snitch.py"      "cdc_snitch.py"
fetch "$base/cdc_snitch_proc.ys" "cdc_snitch_proc.ys"

echo "== sv2v (${SV2V_VERSION}) =="
if [[ ! -x "$CDC_CACHE/sv2v-Linux/sv2v" || "$FORCE" -eq 1 ]]; then
  fetch "https://github.com/zachjs/sv2v/releases/download/${SV2V_VERSION}/sv2v-Linux.zip" "sv2v.zip"
  unzip -o -q sv2v.zip
  chmod +x "$CDC_CACHE/sv2v-Linux/sv2v"
else
  echo "  [skip] sv2v-Linux/sv2v (exists)"
fi

if [[ "$WITH_YOSYS" -eq 1 ]]; then
  echo "== oss-cad-suite (${OSS_CAD_SUITE_TAG}) — ~700 MB =="
  if [[ ! -x "$CDC_CACHE/oss-cad-suite/bin/yosys" || "$FORCE" -eq 1 ]]; then
    date="${OSS_CAD_SUITE_TAG//-/}"
    fetch "https://github.com/YosysHQ/oss-cad-suite-build/releases/download/${OSS_CAD_SUITE_TAG}/oss-cad-suite-linux-x64-${date}.tgz" "oss-cad-suite.tgz"
    tar -xzf oss-cad-suite.tgz
  else
    echo "  [skip] oss-cad-suite/bin/yosys (exists)"
  fi
fi

echo "done -> $CDC_CACHE"
