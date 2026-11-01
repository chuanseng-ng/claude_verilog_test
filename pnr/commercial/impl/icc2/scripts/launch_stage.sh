#!/bin/bash
# launch_stage.sh <stage> <tag> -- wait for the licensed-tool slot, then run one ICC2 stage via run_stage.sh (detached caller recommended)
H=$(cd "$(dirname "$0")" && pwd); $H/wait_licensed_idle.sh; exec $H/run_stage.sh "$@"
