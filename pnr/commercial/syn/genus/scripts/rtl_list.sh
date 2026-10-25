#!/bin/bash
# rtl_list.sh <repo> <out.f> : same 28-file RTL list as the OpenROAD and DC arms (single source of truth: pnr/Makefile)
exec "$(dirname "$0")/../../dc/scripts/rtl_list.sh" "$@"
