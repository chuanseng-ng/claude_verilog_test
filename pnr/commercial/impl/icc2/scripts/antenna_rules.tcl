# antenna_rules.tcl -- Sky130 antenna ratios from the tech LEF (ANTENNAMODEL OXIDE1) in ICC2 syntax.
# The generated sky130_antenna_rules proc passes the LEF PWL tables as -diode_ratio pairs, which ICC2 rejects ("Invalid float value '0 75'",
# the vector is {v0 v1 v2 v3} whose meaning depends on the diode mode).  Approximation, recorded in the summary: unprotected ratios are the LEF
# ones (li1 75, mcon 3, met1-4 400, via cuts 6); a net that has a diode attached is treated as protected (diode_mode 1 = unlimited protection),
# i.e. the LEF PWL relaxation (400 -> 2609..11600 with diode area) is not modelled.  Lenient for diode-protected nets, strict for the rest.
catch {remove_antenna_rules}
define_antenna_rule -mode 1 -diode_mode 1 -metal_ratio 400 -cut_ratio 6
foreach {l r} {li1 75 mcon 3 met1 400 via 6 met2 400 via2 6 met3 400 via3 6 met4 400 via4 6 met5 400} {
  define_antenna_layer_rule -mode 1 -layer $l -ratio $r -diode_ratio [list $r 0 $r 0]   ;# vector unused under diode_mode 1
}
