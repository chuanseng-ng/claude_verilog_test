#================================================================
# DFT Stage 2 post-route queries (bead j41m.8). Sourced through sta_load_sky130_soc.tcl (env STA_CMDS).
#   STA_OUT   output directory for small result files (default .)
#   STA_Q     which block: main | exempt_pins | scan_pins
#     main         per-clock worst setup/hold, clock latency + skew, hold/setup through dft_scan_en, CPU-macro input-pin hold
#     exempt_pins  (functional view) write the capture D pins the SDC exempts from hold to $STA_OUT/exempt_pins.txt
#     scan_pins    (scan view, STA_VIEW=scan) hold slack of those pins, tck -> tck included
# Every number is printed as a "Q: <key> <value>" line so it can be grepped.
#================================================================
proc q_out {k v} { puts "Q: $k $v" }
proc q_slack {pin kind} {
    set s [get_property $pin $kind]
    if {$s eq "" || $s eq "INF" || $s eq "-INF"} { return "" }
    return $s
}
set OUT [expr {[info exists ::env(STA_OUT)] && $::env(STA_OUT) ne "" ? $::env(STA_OUT) : "."}]
set Q [expr {[info exists ::env(STA_Q)] ? $::env(STA_Q) : "main"}]

proc worst_for_clock {clk kind} {
    # worst endpoint slack over register data pins clocked by $clk -> "<slack> <pin>"
    set pins [all_registers -clock [get_clocks $clk] -data_pins]
    if {[llength $pins] == 0} { return "" }
    set w ""; set wp ""
    set prop [expr {$kind eq "max" ? "slack_max" : "slack_min"}]
    foreach p $pins {
        set s [q_slack $p $prop]
        if {$s eq ""} continue
        if {$w eq "" || $s < $w} { set w $s; set wp [get_full_name $p] }
    }
    return "$w $wp"
}

if {$Q eq "main"} {
    foreach clk {core_clk cpu_clk tck} {
        if {[llength [get_clocks -quiet $clk]] == 0} continue
        q_out "setup_worst_ns.$clk" [worst_for_clock $clk max]
        q_out "hold_worst_ns.$clk"  [worst_for_clock $clk min]
    }
    catch { q_out "worst_slack_max_ns" [sta::worst_slack_cmd max] }
    catch { q_out "worst_slack_min_ns" [sta::worst_slack_cmd min] }
    puts "=== clock latency / skew ==="
    catch { report_clock_latency -clock core_clk -digits 3 }
    catch { report_clock_latency -clock cpu_clk -digits 3 }
    catch { report_clock_skew -setup -clock core_clk -digits 3 }
    catch { report_clock_skew -hold -clock core_clk -digits 3 }
    catch { report_clock_skew -setup -clock cpu_clk -digits 3 }
    catch { report_clock_skew -hold -clock cpu_clk -digits 3 }
    puts "=== hold/setup through dft_scan_en ==="
    set n [get_nets -quiet dft_scan_en]
    q_out "dft_scan_en_net_found" [llength $n]
    if {[llength $n]} {
        catch { report_checks -path_delay min -through $n -group_count 1 -format full_clock_expanded -digits 3 }
        catch { report_checks -path_delay max -through $n -group_count 1 -format full_clock_expanded -digits 3 }
    }
    puts "=== CPU macro input pins, hold and setup slack ==="
    set worst_h ""; set worst_s ""; set nneg_h 0; set nneg_s 0; set npins 0
    foreach p [get_pins -quiet u_cpu/*] {
        if {[get_property $p direction] ne "input"} continue
        incr npins
        set h [q_slack $p slack_min]
        set s [q_slack $p slack_max]
        if {$h ne ""} { if {$worst_h eq "" || $h < $worst_h} { set worst_h $h; set wh [get_full_name $p] }; if {$h < 0} { incr nneg_h } }
        if {$s ne ""} { if {$worst_s eq "" || $s < $worst_s} { set worst_s $s; set ws [get_full_name $p] }; if {$s < 0} { incr nneg_s } }
    }
    q_out "macro_inputs" $npins
    q_out "macro_input_hold_worst_ns" "$worst_h [expr {[info exists wh] ? $wh : ""}]"
    q_out "macro_input_hold_negative" $nneg_h
    q_out "macro_input_setup_worst_ns" "$worst_s [expr {[info exists ws] ? $ws : ""}]"
    q_out "macro_input_setup_negative" $nneg_s
    foreach pn {scan_en_i scan_in_i[0] scan_in_i[1]} {
        set p [get_pins -quiet u_cpu/$pn]
        if {[llength $p]} { q_out "macro_pin_hold.$pn" [q_slack $p slack_min] }
    }
}

if {$Q eq "exempt_pins"} {
    set fh [open $OUT/exempt_pins.txt w]
    foreach p $::cvt_cdc_hold_exempt_pins { puts $fh $p }
    close $fh
    q_out "exempt_pins" [llength $::cvt_cdc_hold_exempt_pins]
}

if {$Q eq "scan_pins"} {
    set fh [open $OUT/exempt_pins.txt r]
    set names [split [string trim [read $fh]] "\n"]
    close $fh
    set viol 0; set worst ""; set n 0; set rows {}
    foreach nm $names {
        set p [get_pins -quiet $nm]
        if {[llength $p] == 0} continue
        incr n
        set s [q_slack $p slack_min]
        if {$s eq ""} continue
        lappend rows "$nm $s"
        if {$s < 0} { incr viol }
        if {$worst eq "" || $s < $worst} { set worst $s }
    }
    q_out "scan_view_pins_checked" $n
    q_out "scan_view_hold_violating" $viol
    q_out "scan_view_hold_worst_ns" $worst
    set fh [open $OUT/scan_view_pin_slacks.txt w]
    foreach r $rows { puts $fh $r }
    close $fh
    catch { q_out "scan_view_worst_global_hold_ns" [sta::worst_slack_cmd min] }
}

if {$Q eq "mux"} {
    # insertion delay of the DFT clock mux + root buffer: the capture-clock path of one register per clock, fully expanded
    foreach clk {core_clk cpu_clk} {
        set pins [all_registers -clock [get_clocks $clk] -data_pins]
        set pick [lindex $pins [expr {[llength $pins] / 2}]]
        puts "=== capture clock path, $clk, endpoint [get_full_name $pick] ==="
        catch { report_checks -path_delay max -to $pick -format full_clock_expanded -digits 3 }
    }
}
