# common.tcl -- shared setup for every ICC2 stage script (Step B5a).  env: REPO PDKDIR RUN TAG
set REPO   $::env(REPO)
set PDKDIR $::env(PDKDIR)
set RUN    $::env(RUN)
set B      $PDKDIR/build
set TOP    rv32i_cpu_top
set SRAM   sky130_sram_1kbyte_1rw1r_32x256_8
set CFGDIR $REPO/pnr/sky130/cpu
set SDC    $CFGDIR/constraints/sky130_cpu.sdc
set NETLIST $REPO/pnr/commercial/syn/dc/runs/b3a_dc_tt/out/rv32i_cpu_top.nl.v
set DLIB   $RUN/rv32i.dlib
set SCRIPTDIR [file dirname [info script]]
file mkdir $RUN/reports $RUN/out $RUN/logs
set_host_options -max_cores 2
catch {set_svf -off}   ;# icc2_shell otherwise drops one default-*.svf per session into the run dir
set_app_var sh_continue_on_error false
# Stage chaining.  A stage copies the PREVIOUS label to the NEW label, closes the old one, and edits the new one.
# (save_lib after editing an opened block would otherwise write the edits back into the previous stage's label.)
proc open_stage {prev new} {
  global DLIB TOP B
  open_lib $DLIB
  open_block ${TOP}/${prev}
  catch {remove_blocks -force ${TOP}/${new}}
  copy_block -from_block ${TOP}/${prev} -to_block ${TOP}/${new}
  close_blocks -force
  open_block ${TOP}/${new}
  current_block ${TOP}/${new}
  source $B/ndm/sky130_tech_setup.tcl
}
# view an existing label for debug/report scripts: never call save_lib afterwards
proc view_stage {label} {
  global DLIB TOP B
  open_lib $DLIB
  open_block ${TOP}/${label}
  current_block ${TOP}/${label}
  source $B/ndm/sky130_tech_setup.tcl
}
proc save_stage {label} {
  global TOP
  save_block
  save_lib
  puts "STAGE_SAVED: $label"
}
proc stage_time {name t0} { puts "STAGE_TIME: $name [expr {[clock seconds]-$t0}] s" }
