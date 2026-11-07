#!/bin/bash
# chain_all.sh -- dynamic (with EM modes) for 3 arms, then the no-decap sensitivity for 3 arms.  Sequential, resumable.
cd "$(dirname "$0")/.." || exit 1
scripts/chain.sh dynamic
scripts/chain.sh dynamic-nodecap
echo ALL_DONE
