#!/usr/bin/env bash
# install-Xyce.sh — Xyce parallel SPICE simulator (build from source)
# NOTE: Do NOT auto-run this script. Review and execute manually.
set -euo pipefail
# Xyce is not in nixpkgs. Build from source:
#   https://github.com/Xyce/Xyce
# Requires: trilinos, bison, flex, cmake, MPI
# Or download pre-built binaries from: https://xyce.sandia.gov/downloads/
echo "Xyce: build from source at https://github.com/Xyce/Xyce or download prebuilt from https://xyce.sandia.gov/downloads/"
EDA_MODULEFILES_ROOT="${EDA_MODULEFILES_ROOT:-/usr/share/modulefiles}"
echo "TCL modulefile would go to: $EDA_MODULEFILES_ROOT/xyce/<version>"
