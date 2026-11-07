#!/bin/bash
# launch_stage.sh <stage> <tag> -- run one ICC2 stage via run_stage.sh under the host-wide licensed-tool lock (pdk/sky130/scripts/licensed_lock.sh)
H=$(cd "$(dirname "$0")" && pwd); exec $H/../../../pdk/sky130/scripts/licensed_lock.sh $H/run_stage.sh "$@"
