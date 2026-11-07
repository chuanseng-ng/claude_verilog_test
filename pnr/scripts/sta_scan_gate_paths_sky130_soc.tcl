# j41m.17 post-route replica STA queries (scan_out gate and crypto done -> SE paths). Sourced through
# pnr/scripts/sta_load_sky130_soc.tcl (STA_CMDS=this file; also set J_OUT=<dir>, STA_PNR=<pnr dir>, STA_SDC=<analysis SDC from
# tools/dft/make_scan_analysis_sdc.py>). Prints "Q: key value" lines. Analysis only; the repo SDC is unchanged.
proc q_out {k v} { puts "Q: $k $v" }
proc sl {p kind} {
    set s [get_property $p $kind]
    if {$s eq "" || $s eq "INF" || $s eq "-INF"} { return "" }
    return $s
}

# 1. the standard block (per-clock worst setup/hold, macro input hold, dft_scan_en reports)
set ::env(STA_Q) main
set ::env(STA_OUT) $::env(J_OUT)
source [file join $::env(STA_PNR) scripts sta_scan_queries_sky130_soc.tcl]

# 2. every register data endpoint with negative setup slack: count, endpoints, clock
set neg {}
foreach clk {core_clk cpu_clk tck} {
    if {[llength [get_clocks -quiet $clk]] == 0} continue
    foreach p [all_registers -clock [get_clocks $clk] -data_pins] {
        set s [sl $p slack_max]
        if {$s ne "" && $s < 0} { lappend neg [list $s [get_full_name $p] $clk] }
    }
}
set neg [lsort -real -index 0 $neg]
q_out "setup_negative_endpoints" [llength $neg]
foreach r [lrange $neg 0 39] { q_out "setup_neg" $r }
# output ports and macro input pins with negative setup slack
set nport 0
foreach p [get_ports -quiet *] {
    if {[get_property $p direction] ne "output"} continue
    set s [sl $p slack_max]
    if {$s ne "" && $s < 0} { incr nport; q_out "setup_neg_port" "[get_full_name $p] $s" }
}
q_out "setup_negative_output_ports" $nport

# 3. SE pins: worst setup/hold over every scan flop SCE pin (all launches), and the crypto-done launched paths
set se [get_pins -quiet -hierarchical */SCE]
q_out "se_pins" [llength $se]
set w ""; set wp ""; set nneg 0
foreach p $se {
    set s [sl $p slack_max]
    if {$s eq ""} continue
    if {$s < 0} { incr nneg }
    if {$w eq "" || $s < $w} { set w $s; set wp [get_full_name $p] }
}
q_out "se_setup_worst_all_launches" "$w $wp"
q_out "se_setup_negative" $nneg

set dn [get_nets -quiet crypto_wipe_done]
q_out "crypto_wipe_done_net_found" [llength $dn]
if {[llength $dn]} {
    puts "=== setup, paths through crypto_wipe_done to SE pins (done -> and4 -> dft_scan_en tree -> SCE) ==="
    report_checks -path_delay max -through $dn -to $se -group_count 1 -format full_clock_expanded -digits 3 -fields {fanout slew cap}
    set pd [find_timing_paths -path_delay max -through $dn -to $se -group_count 1 -sort_by_slack]
    foreach pp $pd { q_out "done_to_SE_setup_slack" "[get_property $pp slack] start=[get_full_name [get_property $pp startpoint]] end=[get_full_name [get_property $pp endpoint]]" }
    puts "=== setup, paths through crypto_wipe_done to scan_out_o (done -> AND2 -> buf -> port) ==="
    report_checks -path_delay max -through $dn -to [get_ports scan_out_o*] -group_count 1 -format full_clock_expanded -digits 3
    set pd [find_timing_paths -path_delay max -through $dn -to [get_ports scan_out_o*] -group_count 6 -sort_by_slack]
    foreach pp $pd { q_out "done_to_scan_out_setup_slack" "[get_property $pp slack] start=[get_full_name [get_property $pp startpoint]] end=[get_full_name [get_property $pp endpoint]]" }
    # also the other AND input: chain last flop -> AND -> port
    set pd [find_timing_paths -path_delay max -to [get_ports scan_out_o*] -group_count 6 -sort_by_slack]
    foreach pp $pd { q_out "any_to_scan_out_setup_slack" "[get_property $pp slack] start=[get_full_name [get_property $pp startpoint]] end=[get_full_name [get_property $pp endpoint]]" }
    puts "=== hold, same paths ==="
    report_checks -path_delay min -through $dn -to $se -group_count 1 -format full_clock_expanded -digits 3
    set pd [find_timing_paths -path_delay min -through $dn -to $se -group_count 1 -sort_by_slack]
    foreach pp $pd { q_out "done_to_SE_hold_slack" [get_property $pp slack] }
}
