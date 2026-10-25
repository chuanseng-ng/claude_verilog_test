# common.tcl -- shared setup for every Innovus stage script (Step B5b).  env: REPO PDKDIR RUN TAG HERE
set REPO   $::env(REPO)
set PDKDIR $::env(PDKDIR)
set RUN    $::env(RUN)
set TOP    rv32i_cpu_top
set SRAM   sky130_sram_1kbyte_1rw1r_32x256_8
set CFGDIR $REPO/pnr/sky130/cpu
set SDC    $CFGDIR/constraints/sky130_cpu.sdc          ;# ORIGINAL SDC (not Genus's), md5 3c69635042a9d65cb87e71a9db713e4e
set NETLIST $REPO/pnr/commercial/syn/genus/runs/b3b_genus_tt_r2/out/rv32i_cpu_top.nl.v
set SCRIPTDIR [file dirname [file normalize [info script]]]
set PDKREF $::env(PDK_ROOT)/sky130A/libs.ref
set ::env(SDC) $SDC
file mkdir $RUN/reports $RUN/out $RUN/logs $RUN/dbs
setMultiCpuUsage -localCpu 2

proc stage_time {name t0} { puts "STAGE_TIME: $name [expr {[clock seconds]-$t0}] s" }
proc save_stage {label} {
  global RUN TOP
  saveDesign $RUN/dbs/${label}.enc
  puts "STAGE_SAVED: $label"
}
proc restore_stage {label} {
  global RUN TOP
  restoreDesign $RUN/dbs/${label}.enc.dat $TOP
  puts "STAGE_RESTORED: $label"
}
# per-design settings, re-asserted after every restore
proc common_settings {} {
  global PDKDIR PDKREF
  setMultiCpuUsage -localCpu 2
  # signal routing met1..met4 (li1 is not routable); RT_MAX_LAYER met4
  setDesignMode -process 130 -bottomRoutingLayer met1 -topRoutingLayer met4
  # dont_use: PDK-enablement list + LibreLane drc_exclude.cells + EXTRA_EXCLUDED_CELLS
  source $PDKDIR/scripts/dont_use.tcl
  set fh [open $PDKREF/../../sky130A/libs.tech/openlane/sky130_fd_sc_hd/drc_exclude.cells r]
  set excl [list sky130_fd_sc_hd__probe_p_8 sky130_fd_sc_hd__probec_p_8]
  while {[gets $fh l] >= 0} { set l [string trim $l]; if {$l ne "" && ![string match #* $l]} { lappend excl $l } }
  close $fh
  foreach c [lsort -unique $excl] { catch { set_db [get_db base_cells $c] .dont_use true } }
  # diode_2 is a protection cell: dont_use.tcl blocks it for synthesis, the antenna fixer must be allowed to use it
  catch { set_db [get_db base_cells sky130_fd_sc_hd__diode_2] .dont_use false }
  # physical-only cells are never optimisation targets
  foreach p {*decap_* *fill_* *tap* *lpflow_decapkapwr_*} { catch { set_db [get_db base_cells sky130_fd_sc_hd__$p] .dont_use true } }
}
