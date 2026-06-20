#!/usr/bin/env bash
# install-magic.sh — magic-vlsi 8.3.629 is included via librelane.includedTools
# and is therefore ALREADY available inside the nix analog devshell.
# NOTE: Do NOT auto-run this script. Review and execute manually.
set -euo pipefail

# --- Option A: nix analog devshell (RECOMMENDED) ---
# magic arrives via librelane.includedTools; no extra config needed.
# nix develop ~/Downloads/Github/librelane#analog

# --- Option B: apt ---
# sudo apt-get install -y magic

# --- Option C: Open Circuit Design source ---
# http://opencircuitdesign.com/magic/

echo "magic-vlsi 8.3.629: already included in the nix#analog devshell via librelane.includedTools."
