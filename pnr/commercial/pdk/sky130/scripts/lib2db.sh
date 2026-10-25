#!/bin/bash
# lib2db.sh <in.lib> <out.db> <logfile> -- one lc_shell run per library, run under safe_run.sh.
# lc_shell segfaults at exit on this host (see lib2db.tcl); success = marker in log + .db exists.
set -u
here=$(cd "$(dirname "$0")" && pwd)
in=$1; out=$2; log=$3
work=$(dirname "$out")/../lc_work/$(basename "$out" .db); mkdir -p "$work" "$(dirname "$out")"
( cd "$work" && LIB_IN=$in DB_OUT=$out "$here/safe_run.sh" "$log" lc_shell -f "$here/lib2db.tcl" )
rc=$?
rm -f "$work"/Synopsys_stack_trace_* "$work"/crte_*
if grep -q "LIB2DB: WROTE $out" "$log" && [ -s "$out" ] && grep -q "Thank you for using Library Compiler" "$log"; then
  echo "lib2db: OK $out (lc_shell rc=$rc$( [ $rc -eq 139 ] && echo ', known exit-time segfault'))"; exit 0
fi
echo "lib2db: FAILED $out (rc=$rc), see $log"; exit 1
