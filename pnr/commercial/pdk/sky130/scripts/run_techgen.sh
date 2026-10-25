#!/bin/bash
# run_techgen.sh <corner> -- Cadence Quantus Techgen: ICT -> qrcTechFile (cell-level, DEF/Innovus flow).
# Nice'd, memory-capped via safe_run.sh.  Techgen "simulation" runs a field solver
# and can take hours; -2d_only and -simulation_FS_off skip the 3-D sidewall models and the Quantus-FS data
# (Quantus FS is not needed for the Innovus/DEF flow).  -compilation (LVS-input flow) is NOT run: only the DEF
# flow is needed.  Output: build/qrc/<corner>/qrcTechFile.   SAFE_TIMEOUT defaults to 12 h here (nom reached 47 % in 4 h single-thread, 2026-10-26).
# TECHGEN_CPUS (default 1) is passed as -multi_cpu.
set -u
here=$(cd "$(dirname "$0")" && pwd); b=$here/../build
c=$1; d=$b/qrc/$c; mkdir -p "$d" "$b/logs"
cp "$b/tech/ict/sky130A_$c.ict" "$d/"
( cd "$d" && SAFE_TIMEOUT=${SAFE_TIMEOUT:-43200} "$here/safe_run.sh" "$b/logs/techgen_$c.log" \
    Techgen -multi_cpu ${TECHGEN_CPUS:-1} -simulation_FS_off -2d_only -cleanup "sky130A_$c.ict" ); rc=$?
ls -la "$d"; echo "Techgen $c rc=$rc"
[ -s "$d/qrcTechFile" ]
