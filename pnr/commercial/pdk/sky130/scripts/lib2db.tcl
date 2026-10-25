# lib2db.tcl -- Liberty -> Synopsys .db via lc_shell (Library Compiler X-2025.06).
# Env:  LIB_IN=<file.lib>   DB_OUT=<file.db>
# The Liberty is NOT edited.  Any DC/PT-relevant problem is handled with lc_shell options
# or recorded in reports/pdk_enablement_sky130.md.
#
# NOTE: lc_shell X-2025.06 on this host segfaults at process exit after ANY read_lib
# (reproduced with the SRAM lib alone, with/without `exit -force`, `quit`, remove_lib, one
# core, and with no write_lib at all) -- AFTER "Thank you for using Library Compiler" has been
# printed and the .db has been written.  The Makefile therefore judges success from the
# "Wrote the ... library" marker + non-empty .db, not from the exit code (see lib2db.sh).
set lib_in  $env(LIB_IN)
set db_out  $env(DB_OUT)
set_app_var sh_continue_on_error true
catch { set_host_options -max_cores 1 }
echo "LIB2DB: reading $lib_in"
set libs [read_lib $lib_in]
foreach l [get_object_name [get_libs]] {
  echo "LIB2DB: library $l"
  # check_library: units, nominal conditions, missing functions/pins, arcs
  echo "LIB2DB: ---- check_library begin ($l)"
  catch { check_library } cl_msg
  echo "LIB2DB: ---- check_library end"
  write_lib $l -format db -output $db_out
  echo "LIB2DB: WROTE $db_out"
}
exit
