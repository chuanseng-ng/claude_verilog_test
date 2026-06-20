#!/usr/bin/env bash
# install-scikit-rf.sh — scikit-rf (skrf) Python package
# NOTE: Do NOT auto-run this script. Review and execute manually.
set -euo pipefail
PYTHON_EXEC="${PYTHON_EXEC:-/usr/bin/python3}"
"$PYTHON_EXEC" -m pip install scikit-rf
echo "scikit-rf installed for $PYTHON_EXEC"
