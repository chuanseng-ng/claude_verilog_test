# Cheap, no-routing exercise of the drt.tcl fix's set_routing_layers call, per coordinator
# request: confirm `set_routing_layers -signal <min>-<max>` (the exact call drt.tcl now makes
# on 26Q2 ahead of a flag-free detailed_route) is ACCEPTED on a loaded post-placement/post-CTS
# ODB, on both toolchains, without running any actual routing.
puts "\[ROUTELAYER_PROBE\] DB loaded"
if {[catch {set_routing_layers -signal M2-M7} errmsg]} {
    puts "\[ROUTELAYER_PROBE\] set_routing_layers FAILED: $errmsg"
} else {
    puts "\[ROUTELAYER_PROBE\] set_routing_layers ACCEPTED (signal M2-M7)"
}
puts "\[ROUTELAYER_PROBE\] DONE"
exit

# Usage notes (bead bpp, 2026-09-15):
#   26Q2:     openroad -no_splash -exit -db <odb> bpp_routing_layers_probe.tcl
#   bundled edf00dff has NO -db CLI flag (older CLI) -- prepend `read_db {<odb>}` as the
#   first line of a copy of this script instead, then:
#     openroad -no_splash -exit <that copy>.tcl
# Validated against bpp-3's 26Q2 CTS-stage ODB and bpp-4b's bundled-edf00dff CTS-stage ODB:
# `set_routing_layers -signal M2-M7` ACCEPTED on both, no full detailed-routing run performed.
