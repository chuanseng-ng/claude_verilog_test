# b10m_netgeom.tcl -- VIEW-ONLY: for each net in env NETLIST (file, one net per line) print every terminal with coordinates (inst terms: inst centre; ports: pin shape centre) and the routed wire length.  Never saves.
source [file join [file dirname [file normalize [info script]]] common.tcl]
set FL [expr {[info exists ::env(FROM_LABEL)] ? $::env(FROM_LABEL) : "09_eco"}]
restore_stage $FL
common_settings
set R $RUN/reports/b10probe; file mkdir $R
set fo [open $R/netgeom.txt w]
set fh [open $::env(NETLIST) r]
while {[gets $fh nn] >= 0} {
  if {$nn eq ""} continue
  set n [dbGetNetByName $nn]
  if {$n eq "0x0"} { puts $fo "NET $nn NOT FOUND"; continue }
  set wl 0; catch { set wl [format %.1f [expr [join [dbGet $n.wires.length -e] +]]] }
  puts $fo "NET $nn wirelen=$wl"
  foreach it [dbGet $n.instTerms] {
    set b [lindex [dbGet $it.inst.box] 0]
    puts $fo [format "   %-6s %-60s %-34s x=%.0f y=%.0f" [expr {[dbGet $it.isOutput] ? "DRV" : "load"}] [dbGet $it.name] [dbGet $it.inst.cell.name] [expr {([lindex $b 0]+[lindex $b 2])/2}] [expr {([lindex $b 1]+[lindex $b 3])/2}]]
  }
  foreach t [dbGet $n.terms] { catch { set b [lindex [dbGet $t.pins.allShapes.shapes.rect] 0]; puts $fo [format "   PORT   %-60s x=%.0f y=%.0f" [dbGet $t.name] [expr {([lindex $b 0]+[lindex $b 2])/2}] [expr {([lindex $b 1]+[lindex $b 3])/2}]] } }
}
close $fh; close $fo
puts "PROBE_DONE"
exit
