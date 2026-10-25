#!/bin/sh
# Fetch the sky130_fd_sc_hd tt Liberty used by the Tessent evaluation flow.
# This host has no sky130 PDK install (no nix/LibreLane/ciel), so the file is taken from the OpenROAD-flow-scripts
# sky130hd platform, which is the same Liberty the OpenROAD/LibreLane flows read. Provenance is pinned by sha256.
# Usage: fetch_lib.sh <dest-dir>
set -e
D=${1:?dest dir}
SHA=ec0e1067a35c8bf20b11e58d1e8ac53326067e4dac84a125cc1b917a3518d0d9
mkdir -p "$D"
F="$D/sky130_fd_sc_hd__tt_025C_1v80.lib"
if [ ! -s "$F" ]; then
  H=raw.githubusercontent.com
  curl -sSL --fail -o "$F" "https://$H/The-OpenROAD-Project/OpenROAD-flow-scripts/master/flow/platforms/sky130hd/lib/sky130_fd_sc_hd__tt_025C_1v80.lib"
fi
echo "$SHA  $F" | sha256sum -c -
