#!/usr/bin/env bash
# Run the probe-instrumented arms (built with PROBE_FILE=..., see gen_probes.py)
# on one program and write <work>/<arm>.<prog>.{log,probe}.
# usage: run_probe.sh <work_dir> <prog> <haltcyc>   (arms: rtl_p, gate_p under <work_dir>)
set -u
W="$1"; P="$2"; C="$3"
for a in rtl_p gate_p; do
  "$W/$a/obj/Vtb" +rom="$W/progs/$P.hex" +haltcyc="$C" +probe="$W/$a.$P.probe" > "$W/$a.$P.log" 2>&1
done
echo "== regfile STORAGE at halt (arch index: rtl gate)"
paste <(grep '^STATE' "$W/rtl_p.$P.log") <(grep '^STATE' "$W/gate_p.$P.log") | head -40
