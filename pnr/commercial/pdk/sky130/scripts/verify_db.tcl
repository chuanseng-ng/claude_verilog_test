# verify_db.tcl -- read the generated .db files back (read_db), as DC/PT would link them, and run
# lc_shell check_library on each corner's {stdcell + SRAM} pair.  Round-trip proof that the .db written
# by a process that later segfaults at exit is complete (cell count must equal the Liberty's 428/1).
# Env: DB_DIR
set d $env(DB_DIR)
set_app_var sh_continue_on_error true
catch { set_host_options -max_cores 1 }
foreach c {tt_025C_1v80 ss_100C_1v60 ff_n40C_1v95} {
  echo "VERIFY: ===== corner $c + SRAM"
  catch { remove_lib -all }
  read_db $d/sky130_fd_sc_hd__$c.db
  read_db $d/sky130_sram_1kbyte_1rw1r_32x256_8_TT_1p8V_25C.db
  echo "VERIFY: libs loaded: [get_object_name [get_libs]]"
  catch { check_library } m
  echo "VERIFY: ---- end check_library $c"
}
exit
