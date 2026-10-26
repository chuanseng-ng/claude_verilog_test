# DFT Stage 2 (bead claude_verilog_test-j41m.8): netlist-level scan insertion with OpenROAD `dft`.
#
# Run by the CVT.ScanInsert step (librelane_plugin_cvt_sky130/__init__.py) with an OpenROAD that has
# set_dft_config / scan_replace / execute_dft_plan (26Q2; the Sky130 flow's own edf00dff has a different,
# defective stitcher, DFT_ARCHITECTURE.md 1.1/1.3).  Everything is parameterised through the environment:
#
#   CVT_SCAN_NL_IN / CVT_SCAN_NL_OUT   flow netlist in, scan netlist out
#   CVT_SCAN_TOP                       design name
#   CVT_SCAN_LEFS / CVT_SCAN_LIBS      Tcl lists
#   CVT_SCAN_CLOCKS                    Tcl list of {name port period_ns} triples (STA clocks the stitcher needs)
#   CVT_SCAN_EXCL_CLKNETS              Tcl list of clock NET names whose flops are NOT scanned (TAP clock, test clock);
#                                      inverters/buffers fed only from these nets are followed (negedge-tck flops)
#   CVT_SCAN_EXCL_QRX                  regex on the Q net name of flops that are NOT scanned (crypto key registers)
#   CVT_SCAN_EXPECT_QEXCL              expected count of Q-net-excluded flops (-1 = do not check); mismatch aborts
#   CVT_SCAN_MAX_LENGTH                set_dft_config -max_length
#   CVT_SCAN_PORT_ORDER                Tcl list of regexes on the first flop's clock net; chains are given port indices
#                                      in this class order (first class -> lowest indices)
#   CVT_SCAN_IN_FMT / CVT_SCAN_OUT_FMT existing top ports, e.g. scan_in_i[%d]  (printf style)
#   CVT_SCAN_EN_NET                    existing net every SCE pin is joined to (soc_top: dft_scan_en, macro: scan_en_i)
#   CVT_SCAN_BUF_CELL                  buffer master put between a chain's last Q net and its scan_out port
#   CVT_SCAN_REPORT                    report file (key=value lines, parsed by the step and by check_scan_chains.py)
#
# Finding (j41m.8, DFT_ARCHITECTURE.md 14.4): 26Q2 insert_dft does NOT reuse existing ports.  It always creates its own
# scan_enable_0 / scan_in_<k> / scan_out_<k>; -scan_*_name_pattern only renames them (a pattern without %d gives every chain
# the same name).  So the tool's ports are created, then merged into the pre-existing soc_top ports below.

proc env_or {name default} {
    if {[info exists ::env($name)]} { return $::env($name) }
    return $default
}

set top        $::env(CVT_SCAN_TOP)
set nl_in      $::env(CVT_SCAN_NL_IN)
set nl_out     $::env(CVT_SCAN_NL_OUT)
set rpt_file   $::env(CVT_SCAN_REPORT)
set max_len    $::env(CVT_SCAN_MAX_LENGTH)
set in_fmt     $::env(CVT_SCAN_IN_FMT)
set out_fmt    $::env(CVT_SCAN_OUT_FMT)
set en_net_nm  $::env(CVT_SCAN_EN_NET)
set buf_cell   $::env(CVT_SCAN_BUF_CELL)
set excl_nets  [env_or CVT_SCAN_EXCL_CLKNETS {}]
set excl_qrx   [env_or CVT_SCAN_EXCL_QRX {}]
set expect_q   [env_or CVT_SCAN_EXPECT_QEXCL -1]
set port_order [env_or CVT_SCAN_PORT_ORDER {{.*}}]

foreach f $::env(CVT_SCAN_LEFS) { read_lef $f }
foreach f $::env(CVT_SCAN_LIBS) { read_liberty $f }
read_verilog $nl_in
link_design $top
foreach c $::env(CVT_SCAN_CLOCKS) {
    lassign $c cname cport cper
    create_clock -name $cname -period $cper [get_ports $cport]
}

set db    [ord::get_db]
set block [ord::get_db_block]

set report {}
proc rpt {k v} { lappend ::report "$k=$v" }

proc is_flop {master} { return [regexp {^sky130_fd_sc_hd__(sdf|df)} $master] }
proc is_scan_flop {master} { return [regexp {^sky130_fd_sc_hd__sdf} $master] }
proc pin_net {inst pin} {
    set it [$inst findITerm $pin]
    if {$it eq "NULL"} { return "NULL" }
    return [$it getNet]
}

# ---------------------------------------------------------------- exclusions
array set exclnet {}
foreach n $excl_nets { set exclnet($n) 1 }
# follow single-input inverters / buffers whose input is an excluded clock net
for {set pass 0} {$pass < 4} {incr pass} {
    foreach inst [$block getInsts] {
        set m [[$inst getMaster] getName]
        if {![regexp {^sky130_fd_sc_hd__(inv|clkinv|buf|clkbuf)_} $m]} continue
        set inn [pin_net $inst A]
        if {$inn eq "NULL" || ![info exists exclnet([$inn getName])]} continue
        set outn [pin_net $inst Y]
        if {$outn eq "NULL"} { set outn [pin_net $inst X] }
        if {$outn ne "NULL"} { set exclnet([$outn getName]) 1 }
    }
}
set n_clk_excl 0
set n_q_excl 0
set n_flops 0
foreach inst [$block getInsts] {
    set m [[$inst getMaster] getName]
    if {![is_flop $m]} continue
    incr n_flops
    set cn [pin_net $inst CLK]
    if {$cn ne "NULL" && [info exists exclnet([$cn getName])]} {
        $inst setDoNotTouch 1
        incr n_clk_excl
        continue
    }
    if {$excl_qrx ne ""} {
        set qn [pin_net $inst Q]
        if {$qn ne "NULL" && [regexp $excl_qrx [$qn getName]]} {
            $inst setDoNotTouch 1
            incr n_q_excl
        }
    }
}
rpt flops_total_before $n_flops
rpt excluded_by_clock $n_clk_excl
rpt excluded_by_qnet $n_q_excl
puts "CVT-SCAN: flops=$n_flops excluded(clock)=$n_clk_excl excluded(qnet)=$n_q_excl"
if {$expect_q >= 0 && $n_q_excl != $expect_q} {
    puts "CVT-SCAN-ERROR: expected $expect_q Q-net-excluded flops, found $n_q_excl (renamed/merged register?)"
    exit 2
}

# ---------------------------------------------------------------- insertion
set_dft_config -max_length $max_len -clock_mixing no_mix
scan_replace
report_dft_plan -verbose
execute_dft_plan

# ---------------------------------------------------------------- chain discovery
set se_bterm [$block findBTerm scan_enable_0]
if {$se_bterm eq "NULL"} { puts "CVT-SCAN-ERROR: tool created no scan_enable_0 (nothing to scan?)"; exit 2 }
set chains {}
set k 0
while {[set sin [$block findBTerm scan_in_$k]] ne "NULL"} {
    set sout [$block findBTerm scan_out_$k]
    if {$sout eq "NULL"} { puts "CVT-SCAN-ERROR: scan_in_$k without scan_out_$k"; exit 2 }
    set net [$sin getNet]
    set first ""
    foreach it [$net getITerms] {
        if {[[$it getMTerm] getName] eq "SCD" && [is_scan_flop [[[$it getInst] getMaster] getName]]} { set first [$it getInst] }
    }
    if {$first eq ""} { puts "CVT-SCAN-ERROR: scan_in_$k reaches no SCD pin"; exit 2 }
    set cur $first
    set len 1
    array unset seen
    set seen([$cur getName]) 1
    while {1} {
        set q [pin_net $cur Q]
        set nxt ""
        foreach it [$q getITerms] {
            if {[[$it getMTerm] getName] eq "SCD" && [is_scan_flop [[[$it getInst] getMaster] getName]]} { set nxt [$it getInst] }
        }
        if {$nxt eq ""} break
        if {[info exists seen([$nxt getName])]} { puts "CVT-SCAN-ERROR: chain $k loops at [$nxt getName]"; exit 2 }
        set seen([$nxt getName]) 1
        set cur $nxt
        incr len
    }
    set lastq [pin_net $cur Q]
    if {[$lastq getName] ne [[$sout getNet] getName]} {
        puts "CVT-SCAN-ERROR: chain $k ends at [$lastq getName], scan_out_$k is on [[$sout getNet] getName]"
        exit 2
    }
    set clknet [[pin_net $first CLK] getName]
    set cls 999
    set ci 0
    foreach rx $port_order {
        if {[regexp $rx $clknet]} { set cls $ci; break }
        incr ci
    }
    lappend chains [list $cls $k $len $clknet $first $cur]
    incr k
}
if {[llength $chains] == 0} { puts "CVT-SCAN-ERROR: no chains"; exit 2 }
set chains [lsort -integer -index 0 [lsort -integer -index 1 $chains]]

# ---------------------------------------------------------------- map tool ports onto the existing soc_top ports
set buf_master "NULL"
foreach lib [$db getLibs] {
    set cand [$lib findMaster $buf_cell]
    if {$cand ne "NULL"} { set buf_master $cand }
}
if {$buf_master eq "NULL"} { puts "CVT-SCAN-ERROR: no master $buf_cell"; exit 2 }
set idx 0
foreach ch $chains {
    lassign $ch cls k len clknet first last
    set in_nm  [format $in_fmt $idx]
    set out_nm [format $out_fmt $idx]
    set tin  [$block findBTerm $in_nm]
    set tout [$block findBTerm $out_nm]
    if {$tin eq "NULL" || $tout eq "NULL"} {
        puts "CVT-SCAN-ERROR: chain $k needs ports $in_nm / $out_nm, which do not exist (more chains than ports)"
        exit 2
    }
    # scan in: merge the tool's scan_in_<k> net into the existing port net
    set sin [$block findBTerm scan_in_$k]
    set kin_net [$sin getNet]
    odb::dbBTerm_destroy $sin
    set tgt [$tin getNet]
    if {[llength [$tgt getITerms]] != 0} { puts "CVT-SCAN-ERROR: $in_nm already has loads"; exit 2 }
    $tgt mergeNet $kin_net
    # scan out: drop the placeholder tie, put a buffer between the chain's last Q net and the port net
    set sout [$block findBTerm scan_out_$k]
    set qnet [$sout getNet]
    odb::dbBTerm_destroy $sout
    set onet [$tout getNet]
    foreach it [$onet getITerms] {
        set im [[[$it getInst] getMaster] getName]
        if {![regexp {^sky130_fd_sc_hd__conb_} $im]} {
            puts "CVT-SCAN-ERROR: $out_nm is driven by $im, expected a conb tie"; exit 2
        }
        odb::dbInst_destroy [$it getInst]
    }
    set bi [odb::dbInst_create $block $buf_master "u_cvt_scan_out_buf_$idx"]
    [$bi findITerm A] connect $qnet
    [$bi findITerm X] connect $onet
    rpt "chain.$idx" "tool_id=$k length=$len clock=$clknet first_flop=[$first getName] last_flop=[$last getName] last_q=[$qnet getName]"
    incr idx
}
rpt chains [llength $chains]

# scan enable: join every SCE to the existing net
set se_net [$se_bterm getNet]
odb::dbBTerm_destroy $se_bterm
set en_net [$block findNet $en_net_nm]
if {$en_net eq "NULL"} { puts "CVT-SCAN-ERROR: no net $en_net_nm"; exit 2 }
set n_sce 0
foreach it [$se_net getITerms] { incr n_sce }
$en_net mergeNet $se_net
rpt scan_enable_net $en_net_nm
rpt scan_enable_new_sinks $n_sce

# ---------------------------------------------------------------- census after
array set cnt {}
set left_nonscan 0
foreach inst [$block getInsts] {
    set m [[$inst getMaster] getName]
    if {![is_flop $m]} continue
    if {[is_scan_flop $m]} {
        if {![info exists cnt(scan)]} { set cnt(scan) 0 }
        incr cnt(scan)
    } else {
        if {![info exists cnt(nonscan)]} { set cnt(nonscan) 0 }
        incr cnt(nonscan)
    }
}
rpt scan_flops [expr {[info exists cnt(scan)] ? $cnt(scan) : 0}]
rpt nonscan_flops [expr {[info exists cnt(nonscan)] ? $cnt(nonscan) : 0}]

write_verilog $nl_out
set fh [open $rpt_file w]
foreach l $report { puts $fh $l }
close $fh
puts "CVT-SCAN: done, [llength $chains] chains, $n_sce SCE sinks joined to $en_net_nm"
exit 0
