#!/bin/bash
# run_tessent.sh <dofile> <logname>   -- runs Tessent in build/run with the environment the dofiles expect.
set -e
here="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export MBIST_MODEL="${MBIST_MODEL:-real}"
export MBIST_HERE="$here" MBIST_BUILD="$here/build" MBIST_ROOT="$(cd "$here/../../.." && pwd)"
mkdir -p "$here/build/run"
cd "$here/build/run"
exec "${TESSENT:-tessent}" -shell -log "$2" -replace -dofile "$1"
