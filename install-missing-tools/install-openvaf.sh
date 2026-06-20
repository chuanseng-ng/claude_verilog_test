#!/usr/bin/env bash
# install-openvaf.sh — OpenVAF (Verilog-A to OSDI compiler)
# OpenVAF is NOT in nixpkgs. nix/openvaf.nix in librelane is a STUB with TODO
# URL/sha256. M-a/M-b proceed with ngspice B-sources / XSPICE behavioral models.
# NOTE: Do NOT auto-run this script. Review and execute manually.
set -euo pipefail

# --- Option A (when openvaf.nix TODO is resolved): ---
# 1. Fill in the correct url + sha256 in ~/Downloads/Github/librelane/nix/openvaf.nix
# 2. Un-comment the openvaf line in flake.nix analog devShell extra-packages
# 3. nix develop ~/Downloads/Github/librelane#analog

# --- Option B: Manual prebuilt binary install ---
# OPENVAF_VERSION="23.5.0"
# URL="https://github.com/pascalkuthe/OpenVAF/releases/download/v${OPENVAF_VERSION}/openvaf_${OPENVAF_VERSION}_linux_amd64"
# mkdir -p ~/.local/bin
# curl -L "$URL" -o ~/.local/bin/openvaf
# chmod +x ~/.local/bin/openvaf
# Verify: openvaf --version

# --- Option C: Build from source ---
# Requires Rust toolchain (cargo)
# git clone https://github.com/pascalkuthe/OpenVAF
# cd OpenVAF && cargo build --release
# sudo cp target/release/openvaf /usr/local/bin/

echo "OpenVAF: STUB. M-a/M-b use ngspice B-sources + XSPICE instead."
echo "To enable OSDI: resolve nix/openvaf.nix URL+sha256 and un-comment in flake.nix#analog."

# --- TCL modulefile skeleton ---
EDA_MODULEFILES_ROOT="${EDA_MODULEFILES_ROOT:-/usr/share/modulefiles}"
echo "TCL modulefile would go to: $EDA_MODULEFILES_ROOT/openvaf/23.5.0"
