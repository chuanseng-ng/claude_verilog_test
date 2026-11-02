# 05k_pin_diag.tcl (v2) -- find a working way to add a met3 wire rectangle to a signal net: add_shape / dbCreateWire / editAddRoute variants.  Reports wire counts and boxes before/after each try.
source [file join [file dirname [file normalize [info script]]] common.tcl]
restore_stage 05k_drv3
common_settings
set net {commit_pc_o[4]}
proc st {net} { set o [dbGet -p top.nets.name $net]; return "wires [llength [dbGet $o.wires]] swires [llength [dbGet $o.sWires]] met3boxes [lsearch -all -inline [dbGet $o.wires.layer.name] met3] shapes [llength [dbGet $o.shapes]]" }
puts "DIAG before: [st $net]"
foreach c {add_shape dbCreateWire dbAddWireSeg editAddRoute} { catch { help $c } e; puts "DIAG help $c: [string range $e 0 700]" }
set o [dbGet -p top.nets.name $net]
puts "DIAG before shapes: [dbGet $o.shapes.box] | [dbGet $o.shapes.layer.name] | swires box: [dbGet $o.sWires.box]"
set obj [add_shape -layer met3 -net $net -rect {0.0 130.735 2.235 131.065}]
catch { puts "DIAG attrs: [dbGet $obj.?]" }
puts "DIAG add_shape obj=$obj type=[dbGet $obj.objType] box=[dbGet $obj.box] layer=[dbGet $obj.layer.name] net=[dbGet $obj.net.name]"
set o [dbGet -p top.nets.name $net]
puts "DIAG after shapes: [dbGet $o.shapes.box] | [dbGet $o.shapes.layer.name] | swires box: [dbGet $o.sWires.box] | wires [llength [dbGet $o.wires]]"
set before [llength [dbGet top.nets.sWires]]
puts "DIAG net list sWires total (all nets) $before"
verify_drc -limit 100 -report $RUN/reports/diag_pin_drc.txt
exit
