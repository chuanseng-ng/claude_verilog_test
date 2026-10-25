#!/bin/bash
# Run the CVT.ScanInsert step ALONE through LibreLane (no full flow), on the state of an earlier run.
# Catches plugin/State/logging bugs in ~30 s instead of at hour 0 of a multi-hour harden (bead j41m.8).
#
# usage: run_scan_step_isolated.sh CONFIG.json STATE_OUT.json RUN_TAG RUNS_DIR
#   CONFIG.json    a config that selects flow CVTClassicScan (pnr/sky130/{soc/config_rccal,cpu/config}.json)
#   STATE_OUT.json state_out.json of the step right before CVT.ScanInsert in an earlier run, e.g.
#                  <run>/06-checker-netlistassignstatements/state_out.json (its netlist is the synthesis output)
#   RUN_TAG        run directory name created under RUNS_DIR (it is deleted first)
#   RUNS_DIR       the runs directory the config's design dir links to (e.g. /nobackup/sky130_soc_runs)
# env: LIBRELANE_DIR (default ~/Downloads/Github/librelane), CVT_SCAN_OPENROAD (default: the 26Q2 build used by pnr/Makefile)
# Exit 0 only if the step passed AND the netlist it produced is the step's state output AND its dft__ metrics exist.
set -u
CONFIG=$(readlink -f "$1")
STATE=$(readlink -f "$2")
TAG=$3
RUNS=$4
LL=${LIBRELANE_DIR:-$HOME/Downloads/Github/librelane}
OR=${CVT_SCAN_OPENROAD:-/nix/store/hgqrwa4687mf7n0y2x6lcgx1kj42sfga-openroad-26Q2/bin/openroad}
PLUGINS=$(cd "$(dirname "$0")/../../pnr" && pwd)
rm -rf "${RUNS:?}/${TAG:?}"
cd "$LL" || exit 2
nix-shell --run "CVT_SCAN_OPENROAD=$OR PYTHONPATH=$PLUGINS/sky130/soc/plugin:$PLUGINS/plugins:\$PYTHONPATH python3 -m librelane --run-tag $TAG --only CVT.ScanInsert -i $STATE $CONFIG" > "${TMPDIR:-/tmp}/run_scan_step_isolated.$TAG.log" 2>&1
RC=$?
STEP=$(ls -d "$RUNS/$TAG"/*cvt-scaninsert 2>/dev/null | head -1)
if [ $RC -ne 0 ] || [ -z "$STEP" ]; then
    echo "FAIL: librelane rc=$RC, no step dir; see ${TMPDIR:-/tmp}/run_scan_step_isolated.$TAG.log"; tail -15 "${TMPDIR:-/tmp}/run_scan_step_isolated.$TAG.log"; exit 1
fi
python3 - "$STEP" <<'E' || exit 1
import json, os, sys
d = sys.argv[1]
s = json.load(open(os.path.join(d, "state_out.json")))
nl = s["nl"]
m = {k: v for k, v in s["metrics"].items() if k.startswith("dft__")}
assert os.path.isfile(nl) and os.path.basename(os.path.dirname(nl)) == os.path.basename(d), f"state nl not from this step: {nl}"
assert m.get("dft__scan_chains", 0) >= 1 and m.get("dft__scan_flops", 0) > 0, m
print("OK step", d, m)
print("NETLIST", nl)
E
