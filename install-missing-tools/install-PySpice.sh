#!/usr/bin/env bash
# install-PySpice.sh — PySpice Python package
# NOTE: Do NOT auto-run this script. Review and execute manually.
set -euo pipefail
PYTHON_EXEC="${PYTHON_EXEC:-/usr/bin/python3}"
"$PYTHON_EXEC" -m pip install PySpice
echo "PySpice installed for $PYTHON_EXEC"
