#!/bin/bash
# dropcache.sh [dir...] -- evict big files (>= 20 MB) under the given dirs (default: pnr/commercial) from the page cache with POSIX_FADV_DONTNEED
# (dd iflag=nocache count=0).  No root needed.  The 15 GB host thrashes in kswapd/kcompactd when the cache is full of SPEF/GDS/netlist files (load 15, tools in D state).
R=$(cd "$(dirname "$0")/../../../../.." && pwd)
dirs=("$@"); [ ${#dirs[@]} -eq 0 ] && dirs=("$R/pnr/commercial" "$R/pnr/sky130")
n=0
while IFS= read -r -d '' f; do dd if="$f" iflag=nocache count=0 status=none 2>/dev/null; n=$((n+1)); done < <(find "${dirs[@]}" -type f -size +20M -print0 2>/dev/null)
echo "dropcache: $n files; Cached now: $(awk '/^Cached/{printf "%d MB",$2/1024}' /proc/meminfo), MemAvailable $(awk '/MemAvailable/{printf "%d MB",$2/1024}' /proc/meminfo)"
