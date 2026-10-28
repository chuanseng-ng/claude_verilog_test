#!/bin/bash
# ctr.sh <container-name> <cmd...>
# Run a command inside the LibreLane container (Magic 8.3.489 / Netgen 1.5.278 / KLayout 0.29.4 / python3.11 / klayout module)
# with $HOME and the PDK mounted at the same paths and cwd preserved. No --memory flag: it is not enforced on this
# cgroup-v1 host; use guard_run.sh (kills the container when MemAvailable drops) instead.
set -u
name=$1; shift
export PDK_ROOT=${PDK_ROOT:-$HOME/pdk} PDK=${PDK:-sky130A} STD_CELL_LIBRARY=${STD_CELL_LIBRARY:-sky130_fd_sc_hd}
IMG=${LIBRELANE_IMAGE:-ghcr.io/librelane/librelane:2.4.13}
exec podman run --rm --name "$name" -v "$HOME:$HOME" -v "$PDK_ROOT:$PDK_ROOT" \
  -e PDK_ROOT -e PDK -e STD_CELL_LIBRARY -e HOME -w "$PWD" "$IMG" "$@"
