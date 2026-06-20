#!/usr/bin/env bash
# install-hdl21.sh — hdl21 Python package
# NOTE: Do NOT auto-run this script. Review and execute manually.
set -euo pipefail
PYTHON_EXEC="${PYTHON_EXEC:-/usr/bin/python3}"
"$PYTHON_EXEC" -m pip install hdl21
echo "hdl21 installed for $PYTHON_EXEC"
