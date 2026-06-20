#!/usr/bin/env bash
# install-gdstk.sh — gdstk Python package
# NOTE: Do NOT auto-run this script. Review and execute manually.
set -euo pipefail
PYTHON_EXEC="${PYTHON_EXEC:-/usr/bin/python3}"
"$PYTHON_EXEC" -m pip install gdstk
echo "gdstk installed for $PYTHON_EXEC"
