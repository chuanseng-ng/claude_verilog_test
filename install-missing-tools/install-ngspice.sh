#!/usr/bin/env bash
# install-ngspice.sh — Install ngspice-45 via nix analog devshell (PREFERRED)
# or via apt as a fallback.
# NOTE: Do NOT auto-run this script. Review and execute manually.
set -euo pipefail

# --- Option A: Use the nix analog devshell (RECOMMENDED) ---
# ngspice-45 is already declared in ~/Downloads/Github/librelane/flake.nix#analog.
# Enter the shell with:
#   nix develop ~/Downloads/Github/librelane#analog
# ngspice will be on PATH inside that shell.

# --- Option B: apt system install ---
# sudo apt-get update
# sudo apt-get install -y ngspice

# --- Option C: Build from source (advanced) ---
# See http://ngspice.sourceforge.net/download.html
# Requires: autoconf, automake, libtool, flex, bison, libx11-dev, libreadline-dev

echo "ngspice: enter 'nix develop ~/Downloads/Github/librelane#analog' to use ngspice-45 immediately."
echo "Alternatively run: sudo apt-get install -y ngspice"

# --- TCL modulefile (for sites with TCL Environment Modules) ---
EDA_MODULEFILES_ROOT="${EDA_MODULEFILES_ROOT:-/usr/share/modulefiles}"
MODULE_DIR="$EDA_MODULEFILES_ROOT/ngspice/45"
# mkdir -p "$MODULE_DIR"
# cat > "$MODULE_DIR/45" <<'MODEOF'
# #%Module1.0
# proc ModulesHelp { } { puts "ngspice 45 — SPICE simulator" }
# set root /usr/local/ngspice-45
# prepend-path PATH            $root/bin
# prepend-path LD_LIBRARY_PATH $root/lib
# MODEOF
echo "TCL modulefile template written to: $MODULE_DIR (mkdir + cat block above — uncomment to activate)"
