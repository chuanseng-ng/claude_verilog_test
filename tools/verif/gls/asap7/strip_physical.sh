#!/usr/bin/env bash
# Strip the zero-port physical-only cells (DECAP*, FILLER*, TAPCELL) from a post-P&R ASAP7
# netlist so it can be simulated. They carry no signal connectivity (the netlist has no power
# pins), so removing them cannot change function. Synthesis-only netlists contain none.
# usage: strip_physical.sh <in.nl.v> <out.v>
set -euo pipefail
grep -vE '^ *(DECAP[A-Za-z0-9]*|FILLER[A-Za-z0-9]*|TAPCELL)_ASAP7_75t_R ' "$1" > "$2"
echo "removed $(( $(wc -l < "$1") - $(wc -l < "$2") )) physical-cell lines"
