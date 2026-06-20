#!/usr/bin/env bash
# install-netgen.sh — netgen 6.2.2505 is included via librelane.includedTools
# NOTE: Do NOT auto-run this script. Review and execute manually.
set -euo pipefail

# --- Option A: nix analog devshell (RECOMMENDED) ---
# nix develop ~/Downloads/Github/librelane#analog
# netgen arrives via librelane.includedTools.

# --- Option B: apt ---
# sudo apt-get install -y netgen-lvs

echo "netgen 6.2.2505: already included in the nix#analog devshell via librelane.includedTools."
