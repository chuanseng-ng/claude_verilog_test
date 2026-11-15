#!/bin/bash
# chain_apl_all.sh <arm> [<arm> ...] -- STEP 8: static, dynamic, dynamic-nodecap for the listed arms (sequential, resumable; see chain_apl.sh)
cd "$(dirname "$0")/.." || exit 1
for m in static dynamic dynamic-nodecap; do scripts/chain_apl.sh $m "$@"; done
echo ALL_APL_DONE
