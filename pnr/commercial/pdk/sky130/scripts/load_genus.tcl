# load_genus.tcl -- Genus load check: MMMC + physical (tech LEF, cell LEF, SRAM LEF) + trivial netlist.
#   genus -no_gui -files load_genus.tcl      (env HERE = pdk/sky130 dir, PDK_ROOT, SDC)
set HERE $::env(HERE)
set PDKR $::env(PDK_ROOT)/sky130A/libs.ref
set_db information_level 6
set_db hdl_error_on_blackbox true
read_mmmc $HERE/scripts/mmmc.tcl
read_physical -lef [list $PDKR/sky130_fd_sc_hd/techlef/sky130_fd_sc_hd__nom.tlef \
                         $PDKR/sky130_fd_sc_hd/lef/sky130_fd_sc_hd.lef \
                         $PDKR/sky130_sram_macros/lef/sky130_sram_1kbyte_1rw1r_32x256_8.lef]
read_hdl $HERE/tests/link_trivial.v
elaborate link_trivial
init_design
puts "=== check_design"
check_design -unresolved
puts "=== counts"
puts "base_cells (lib): [llength [get_db base_cells]]  lib_cells: [llength [get_db lib_cells]]"
puts "physical lib cells: [llength [get_db lib_cells -if {.is_physical_only==true}]]"
puts "insts: [llength [get_db insts]]  ports: [llength [get_db ports]]"
puts "layers: [get_db layers .name]"
puts "routing layers dir: [lmap l [get_db layers -if {.type==routing}] {list [get_db $l .name] [get_db $l .direction]}]"
puts "sites: [get_db sites .name]"
puts "analysis views: [get_db analysis_views .name]"
puts "rc corners: [get_db rc_corners .name]"
puts "=== dont_use"
source $HERE/scripts/dont_use.tcl
puts "dont_use cells: [llength [get_db base_cells -if {.dont_use==true}]]"
puts "=== report_timing (trivial)"
report_timing -max_paths 1
exit
