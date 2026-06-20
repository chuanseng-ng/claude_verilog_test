#!/usr/bin/env bash
# install-klayout.sh — klayout 0.30.8 is included via librelane.includedTools
# NOTE: Do NOT auto-run this script. Review and execute manually.
set -euo pipefail

# --- Option A: nix analog devshell (RECOMMENDED) ---
# nix develop ~/Downloads/Github/librelane#analog

# --- Option B: apt ---
# sudo apt-get install -y klayout

echo "klayout 0.30.8: already included in the nix#analog devshell via librelane.includedTools."
