#!/bin/bash
# map_def_vias.sh <in.def> <out.def>: MEASUREMENT COPY for tools that cannot resolve ICC2's ContactCode via names (OpenROAD, Magic):
# via_cc->M1M2_PR, mcon_cc->L1M1_PR, via2_cc->M2M3_PR, via3_cc->M3M4_PR, via4_cc->M4M5_PR (names from sky130_fd_sc_hd__nom.tlef).
# Geometry is the LEF default via (not ICC2's ContactCode shape): fine for connectivity/antenna (wire-area) checks, NOT for DRC.
perl -pe 's/(?<= )mcon_cc(?= |$)/L1M1_PR/g; s/(?<= )via_cc(?= |$)/M1M2_PR/g; s/(?<= )via2_cc(?= |$)/M2M3_PR/g; s/(?<= )via3_cc(?= |$)/M3M4_PR/g; s/(?<= )via4_cc(?= |$)/M4M5_PR/g' "$1" | grep -v " VIRTUAL " > "$2"
