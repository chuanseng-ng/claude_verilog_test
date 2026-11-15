#!/bin/bash
# run_apl_all.sh -- Ansys APL (apldi, internal NSPICE) characterisation of the Sky130 hd decap cells + the 12 most-used std cells, TT 25 C 1.8 V.  Resumable (markers).
#   Output: apl/runs/main/results/TT_25_1v80/{CAP,CURRENT}/ ; wall + peak RSS per step in apl/runs/main/<step>.log.time ; summary in apl/reports/apl_run.tsv
#   Models: HSPICE-readable conversion of the open_pdks ngspice TT models (mk_hspice_models.py), cell netlists from sky130_fd_sc_hd.spice (mk_cell_netlist.py); values untouched.
#   Config notes (each measured, see doc): no LEF_FILES (the LEF/Liberty VPB/VNB pins become their own supply domains and APL then refuses them as alias pins);
#   VDD_PIN_NAME VPWR / GND_PIN_NAME VGND + DECAP_VDD_PIN {VPWR 1.8 VPB 1.8}; a cell-level pgarc custom lib restricts the P/G arc to VPWR-VGND (as in the RedHawk run).
set -u
HERE=$(cd "$(dirname "$0")" && pwd); APL=$(cd "$HERE/.." && pwd); ROOT=$(cd "$APL/../../../../.." && pwd)
W=$APL/runs/main; mkdir -p $W; cd $W
PDK=${SKY130A:-$HOME/pdk/ciel/sky130/versions/0fe599b2afb6708d281543108caf8310912f54af/sky130A}
CELLS=$(cat $APL/reports/cell_list); DECAPS=$(cat $APL/reports/decap_list)
if [ ! -f setup.done ]; then
  python3.11 -I $HERE/mk_hspice_models.py $W/models > setup.log 2>&1
  python3.11 -I $HERE/mk_cell_netlist.py $W/cells.sp $CELLS $DECAPS >> setup.log 2>&1
  cp $APL/reports/cell_list cell_list; cp $APL/reports/decap_list decap_list
  { for c in $CELLS $DECAPS; do printf 'cell %s {\n    pgarc {\n        VPWR VGND\n    }\n}\n' $c; done; } > pgarc.lib
  cat > apl.config <<CFG
APL_RUN_MODE DI
TMP_DIR $W/tmp
APL_RESULT_DIRECTORY $W/results
SIZE_SCALE 1.0
DESIGN_CORNER {
  TT_25_1v80 {
    TEMP 25
    PROCESS TT
    VDD 1.8
    DEVICE_MODEL_LIBRARY $W/models/sky130_tt_hspice.lib TT
    SPICE_NETLIST $W/cells.sp
    LIB_FILES {
      $W/pgarc.lib CUSTOM
      $PDK/libs.ref/sky130_fd_sc_hd/lib/sky130_fd_sc_hd__tt_025C_1v80.lib
    }
  }
}
DECAP_VDD_PIN {
  VPWR 1.8
  VPB 1.8
}
VDD_PIN_NAME VPWR
GND_PIN_NAME VGND
CFG
  touch setup.done
fi
. $ROOT/tools/eda/pd_env.sh >/dev/null 2>&1
export APACHEROOT=$REDHAWK_HOME BROWSER=/bin/true
export SAFE_THREADS=2 SAFE_MEM_MAX=${SAFE_MEM_MAX:-6G} SAFE_MIN_AVAIL_GB=6 SAFE_TIMEOUT=${SAFE_TIMEOUT:-21600}
LK=$ROOT/pnr/commercial/pdk/sky130/scripts/licensed_lock.sh; SR=$ROOT/pnr/commercial/pdk/sky130/scripts/safe_run.sh
step() { local n=$1; shift
  [ -f $n.done ] && { echo "skip $n"; return; }
  sleep 60   # >= 60 s between licensed-tool starts
  $LK $SR $W/$n.log /usr/bin/time -v -o $W/$n.log.time "$@"; local rc=$?
  echo "rc=$rc" >> $n.log.time; echo $rc > $n.done
  pgrep -u $USER -x firefox >/dev/null && echo "WARNING: firefox running after $n" >> $n.log.time
}
step decap   apldi -p decap_list apl.config
step cellcap apldi -c -l cell_list apl.config
step current apldi -l cell_list apl.config
echo APL_ALL_DONE > all.done
