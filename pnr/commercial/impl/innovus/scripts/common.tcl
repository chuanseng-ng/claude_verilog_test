# common.tcl -- shared setup for every Innovus stage script (Step B5b).  env: REPO PDKDIR RUN TAG HERE
set REPO   $::env(REPO)
set PDKDIR $::env(PDKDIR)
set RUN    $::env(RUN)
set TOP    rv32i_cpu_top
set SRAM   sky130_sram_1kbyte_1rw1r_32x256_8
set CFGDIR $REPO/pnr/sky130/cpu
set SDC    $CFGDIR/constraints/sky130_cpu.sdc          ;# ORIGINAL SDC (not Genus's), md5 3c69635042a9d65cb87e71a9db713e4e
# ---- B5h (B5H=1): (1) symmetric, SDC-visible I/O latency: virtual clock clk_io (gen_innovus_io_sdc.py).  Pre-CTS the clocks are ideal, so latency 0.0; 04_cts.tcl writes the post-CTS
#      file with the measured mean insertion delay and `update_constraint_mode`s it.  Innovus' own `update_io_latency` is disabled (common_settings).
#      (2) rc_nom uses the layer-correct capTable built from the tuned ICT (captbl6/, M1=li1..M6=met5) in EVERY stage.
set B5H 0
if {[info exists ::env(B5H)] && $::env(B5H) == 1} {
  set B5H 1
  set SDC $REPO/pnr/commercial/constraints/sky130_cpu_innovus_pre.sdc
  set ::env(CAPTBL) $REPO/pnr/commercial/impl/innovus/captbl6/sky130A_nom_li1m1.captbl
}
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
  global PDKDIR PDKREF B5H
  if {$B5H} { if {[catch { set_ccopt_property update_io_latency false } e]} { puts "B5H update_io_latency false: $e" } else { puts "B5H: ccopt update_io_latency = [get_ccopt_property update_io_latency]" } }
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
