#!/bin/bash
# run_apl_ef_fix.sh -- re-characterise sky130_ef_sc_hd__decap_12.  The first pass (run_apl_all.sh decap step) gave 10.2 nF and 43 mA leakage for this cell: the ef cell is not in the hd Liberty/LEF, so
# APL did not know its VPB/VNB pins and left the well/bulk nodes floating.  Fix = a CUSTOM_LIBS_FILE (pins.lib) declaring the 4 P/G pins of that cell.  The bad cdev is kept as ef_decap12_bad.cdev.
set -u
HERE=$(cd "$(dirname "$0")" && pwd); APL=$(cd "$HERE/.." && pwd); ROOT=$(cd "$APL/../../../../.." && pwd)
W=$APL/runs/main; cd $W
[ -f efdecap.done ] && { echo skip; exit 0; }
printf 'cell sky130_ef_sc_hd__decap_12 {\n    pin VPB {\n        type vdd\n    }\n    pin VPWR {\n        type vdd\n    }\n    pin VGND {\n        type gnd\n    }\n    pin VNB {\n        type gnd\n    }\n}\n' > pins.lib
grep -q CUSTOM_LIBS_FILE apl.config || printf 'CUSTOM_LIBS_FILE {\n  %s/pins.lib\n}\n' $W >> apl.config
printf 'sky130_ef_sc_hd__decap_12\n' > ef_list
CAP=$W/results/TT_25_1v80/CAP
[ -f $CAP/ef_decap12_bad.cdev ] || mv $CAP/sky130_ef_sc_hd__decap_12.cdev $CAP/ef_decap12_bad.cdev
rm -rf $W/.apache/APL/sky130_ef_sc_hd__decap_12*
. $ROOT/tools/eda/pd_env.sh >/dev/null 2>&1
export APACHEROOT=$REDHAWK_HOME BROWSER=/bin/true SAFE_THREADS=2 SAFE_MEM_MAX=6G SAFE_MIN_AVAIL_GB=6 SAFE_TIMEOUT=7200
sleep 60
$ROOT/pnr/commercial/pdk/sky130/scripts/licensed_lock.sh $ROOT/pnr/commercial/pdk/sky130/scripts/safe_run.sh $W/efdecap.log /usr/bin/time -v -o $W/efdecap.log.time apldi -p ef_list apl.config
echo "rc=$?" >> $W/efdecap.log.time; echo $? > efdecap.done
[ -s $CAP/sky130_ef_sc_hd__decap_12.cdev ] || echo "WARNING: ef cdev missing" >> $W/efdecap.log.time
