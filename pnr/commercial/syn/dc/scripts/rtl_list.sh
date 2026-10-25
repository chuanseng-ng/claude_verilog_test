#!/bin/bash
# rtl_list.sh <repo> <out.f> : the exact 28-file RTL list of the OpenROAD arm (single source of truth: pnr/Makefile)
set -e
make -s -C "$1/pnr" sky130-cpu-sv2v-inputs | awk '/^FILE /{print $2}' > "$2"
make -s -C "$1/pnr" sky130-cpu-sv2v-inputs | awk '/^DEFINES /{$1="";print}' > "$2.defines"
echo "rtl_list: $(wc -l < "$2") files; defines:$(cat "$2.defines")"
