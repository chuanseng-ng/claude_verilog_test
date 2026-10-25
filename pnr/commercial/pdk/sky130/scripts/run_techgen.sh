#!/bin/bash
# run_techgen.sh <corner> -- Cadence Quantus Techgen: ICT -> qrcTechFile (cell-level, DEF/Innovus flow).
# Single-threaded (no -multi_cpu), nice'd, memory-capped via safe_run.sh.  Techgen "simulation" runs a field solver
# and can take hours; -2d_only and -simulation_FS_off skip the 3-D sidewall models and the Quantus-FS data
# (Quantus FS is not needed for the Innovus/DEF flow).  -compilation (LVS-input flow) is NOT run: only the DEF
# flow is needed.  Output: build/qrc/<corner>/qrcTechFile.   SAFE_TIMEOUT defaults to 4 h here.
set -u
here=$(cd "$(dirname "$0")" && pwd); b=$here/../build
c=$1; d=$b/qrc/$c; mkdir -p "$d" "$b/logs"
cp "$b/tech/ict/sky130A_$c.ict" "$d/"
( cd "$d" && SAFE_TIMEOUT=${SAFE_TIMEOUT:-14400} "$here/safe_run.sh" "$b/logs/techgen_$c.log" \
    Techgen -simulation_FS_off -2d_only -cleanup "sky130A_$c.ict" ); rc=$?
ls -la "$d"; echo "Techgen $c rc=$rc"
[ -s "$d/qrcTechFile" ]
