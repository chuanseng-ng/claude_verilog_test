#!/usr/bin/env bash
# install-xschem.sh — Install xschem-3.4.7 via nix analog devshell (PREFERRED)
# NOTE: Do NOT auto-run this script. Review and execute manually.
set -euo pipefail

# --- Option A: Use the nix analog devshell (RECOMMENDED) ---
# xschem-3.4.7 is declared in ~/Downloads/Github/librelane/flake.nix#analog.
# Enter with: nix develop ~/Downloads/Github/librelane#analog

# --- Option B: apt system install ---
# sudo apt-get update
# sudo apt-get install -y xschem

# --- Option C: Build from source ---
# git clone https://github.com/StefanSchippers/xschem
# cd xschem && ./configure && make && sudo make install

echo "xschem: enter 'nix develop ~/Downloads/Github/librelane#analog' to use xschem-3.4.7 immediately."

# --- TCL modulefile skeleton ---
EDA_MODULEFILES_ROOT="${EDA_MODULEFILES_ROOT:-/usr/share/modulefiles}"
MODULE_DIR="$EDA_MODULEFILES_ROOT/xschem/3.4.7"
echo "TCL modulefile location would be: $MODULE_DIR"
