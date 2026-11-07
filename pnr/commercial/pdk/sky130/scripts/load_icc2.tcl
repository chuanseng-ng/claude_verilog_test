# load_icc2.tcl -- icc2_shell smoke test: design lib on the Sky130 reference NDMs, link, floorplan, tracks, directions.
#   icc2_shell -f load_icc2.tcl   (env HERE)
set HERE $::env(HERE)
set B $HERE/build
file delete -force $B/work/icc2/T.dlib
create_lib -technology $B/ndm/sky130_hd.tf \
  -ref_libs [list $B/ndm/sky130_hd_tt.ndm $B/ndm/sky130_hd_phys.ndm $B/ndm/sky130_sram_1kbyte_1rw1r_32x256_8.ndm] $B/work/icc2/T.dlib
read_verilog -top link_trivial $HERE/tests/link_trivial.v
current_block link_trivial
link_block
puts "LINK_CELLS: [sizeof_collection [get_cells]]"
puts "=== layer dirs straight from the NDM (expected unknown: ICC2 keeps routing_direction in the design lib)"
foreach l [get_layers {li1 met1 met2 met3 met4 met5}] { puts "dir [get_object_name $l] [get_attribute $l routing_direction] mask=[get_attribute $l mask_name]" }
puts "=== sourcing sky130_tech_setup.tcl (design-lib side)"
source $B/ndm/sky130_tech_setup.tcl
foreach l [get_layers {li1 met1 met2 met3 met4 met5}] { puts "dir2 [get_object_name $l] [get_attribute $l routing_direction]" }
puts "=== floorplan"
initialize_floorplan -site_def unithd -core_offset 5 -side_length {700 600}
puts "rows: [sizeof_collection [get_site_rows]]  tracks: [sizeof_collection [get_tracks]]"
foreach t [get_tracks] { puts "trk [get_attribute $t layer_name] dir=[get_attribute $t direction] space=[get_attribute $t space] offset=[get_attribute $t offset]" }
puts "=== clock pin attributes"
puts "dfxtp CLK is_clock_pin: [get_attribute [get_lib_pins */sky130_fd_sc_hd__dfxtp_1/CLK] clock]"
puts "=== pg"
puts "lib pg pins: [get_object_name [get_lib_pins */sky130_fd_sc_hd__dfxtp_1/VPWR]] / sram [get_object_name [get_lib_pins -quiet */sky130_sram_1kbyte_1rw1r_32x256_8/vccd1]]"
catch {check_design -checks physical_constraints} e
exit
