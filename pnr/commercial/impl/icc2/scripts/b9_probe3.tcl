source [file join [file dirname [info script]] b8_common.tcl]
view_stage 06d_eco
source [file join $SCRIPTDIR reload.tcl]
foreach p {ANTDIO_292/DIODE HFSBUF_112_1803/A u_core_u_icache_u_tag_sram/dout0[4]} { catch { puts "R_PIN $p [get_attribute [get_pins $p] bbox] cell=[get_attribute [get_cells -of_objects [get_pins $p]] ref_name] orient=[get_attribute [get_cells -of_objects [get_pins $p]] orientation]" } m }
set net [get_nets {u_core_u_icache_tag_dout0[4]}]
foreach_in_collection s [get_shapes -quiet -of_objects $net] { puts "R_SHAPE [get_attribute $s layer_name] [get_attribute $s bbox] use=[get_attribute $s shape_use]" }
foreach_in_collection v [get_vias -quiet -of_objects $net] { puts "R_VIA [get_attribute $v via_def_name] [get_attribute $v bbox]" } 
puts "R_DONE"
exit
