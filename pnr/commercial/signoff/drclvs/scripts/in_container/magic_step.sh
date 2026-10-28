#!/bin/bash
# Runs INSIDE the LibreLane container. magic_step.sh <env.tcl> <step_dir> <script under librelane/scripts/magic>
# Reproduces how LibreLane's TclStep/MagicStep launches Magic: same magicrc, same wrapper.tcl, same step script (the patched
# 3562a8d scripts the OpenROAD arm used), configuration via an _env.tcl copied from the reference run.
set -eu
ENVF=$1; STEP_DIR=$2; SCRIPT=$3
export SCRIPTS_DIR=${LL_SCRIPTS:-$HOME/tools/librelane-3562a8d/librelane/scripts}
export STEP_DIR _TCL_ENV_IN=$ENVF MAGTYPE=mag
case "$SCRIPT" in /*) export _MAGIC_SCRIPT=$SCRIPT;; *) export _MAGIC_SCRIPT=$SCRIPTS_DIR/magic/$SCRIPT;; esac
mkdir -p "$STEP_DIR"; cd "$STEP_DIR"
exec magic -dnull -noconsole -rcfile "$PDK_ROOT/$PDK/libs.tech/magic/$PDK.magicrc" "$SCRIPTS_DIR/magic/wrapper.tcl"
