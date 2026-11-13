# sky130_soc_cdc_check.sdc - Post-route CDC budget constraints for the 2-domain Sky130 SoC (companion SDC)
#
# Scope: check_cdc_timing_sky130.tcl times it (make -C pnr check-cdc-timing-sky130-soc).
#   tb/tests/test_cvt_scan_step.py and tools/docs/check_pinned_text.py read its text. No implementation flow reads it.
# Contents: clocks core_clk (clk_i), cpu_clk (cpu_clk_i) and tck (tck_i, when present); reset false paths; functional-view case analysis;
#   Tcl helper procs; section 10 fallback; max-delay budgets on the CDC crossings.
# Inputs: environment variables CVT_SDC_SCAN_VIEW and CDC_CHECK_MBIST_BUDGET_NS (both optional).
#   The file sets clock_period and tck_period itself. All time values are in ns, the sky130_fd_sc_hd Liberty unit.
# User rules:
#   This is not an implementation SDC. sky130_soc.sdc is, and it declares core_clk and cpu_clk asynchronous.
#   This file declares no clock group and no false path between core_clk, cpu_clk and tck. This is deliberate.
#   The CDC budgets can only be timed by a file that declares the clocks and never relates them.
#   Use it for targeted queries only. A full report_wns or report_tns shows fabricated violations on unrelated cross-domain flop pairs.
#   OpenSTA has no set_max_delay -datapath_only. read_sdc stops on it.
#   Between two overlapping -from/-to exceptions the last one declared wins,
#   so the section 10 fallback must stay before the per-crossing budgets.
#   Do not put a literal '.' in a get_nets -filter pattern.
# Doc: tm:pd:sky130-soc-cdc-check-sdc, cr:pd:sky130-soc-cdc-check-sdc

set clock_period 25.0

create_clock -name core_clk -period $clock_period [get_ports clk_i]
set_clock_uncertainty -setup 0.300 [get_clocks core_clk]
set_clock_uncertainty -hold  0.150 [get_clocks core_clk]

create_clock -name cpu_clk -period $clock_period [get_ports cpu_clk_i]
set_clock_uncertainty -setup 0.300 [get_clocks cpu_clk]
set_clock_uncertainty -hold  0.150 [get_clocks cpu_clk]

set tck_period 100.0
if {[llength [get_ports -quiet tck_i]] > 0} {
    create_clock -name tck -period $tck_period [get_ports tck_i]
    set_clock_uncertainty -setup 0.300 [get_clocks tck]
    set_clock_uncertainty -hold  0.150 [get_clocks tck]
}

# DELIBERATE ABSENCE: no set_clock_groups, no set_false_path between core_clk, cpu_clk and tck.

###############################################################################
# 2. Asynchronous reset ports (as in sky130_soc.sdc)
###############################################################################
set_false_path -from [get_ports rst_n_i]
set_false_path -from [get_ports cpu_rst_n_i]
foreach _p [get_ports -quiet trst_ni] { set_false_path -from $_p }

# 2b. Functional-view case analysis (user decision)
proc cdc_net_driver_pins {full} {
    set out {}
    foreach n [get_nets -quiet -hierarchical *] {
        if {[get_full_name $n] eq $full} {
            foreach p [get_pins -quiet -of_objects $n] {
                if {[get_property $p direction] eq "output"} { lappend out $p }
            }
        }
    }
    return $out
}
if {[info exists ::env(CVT_SDC_SCAN_VIEW)] && $::env(CVT_SDC_SCAN_VIEW) eq "1"} {
    puts "INFO: CDC-FUNCTIONAL-VIEW: CVT_SDC_SCAN_VIEW=1 -- functional-view case analysis NOT applied (scan view)."
} else {
    foreach _p {scan_mode_i scan_en_i} {
        foreach _q [get_ports -quiet $_p] { set_case_analysis 0 $_q }
    }
    set _ts [cdc_net_driver_pins {u_dft_ctrl.tap_serial}]
    foreach _p $_ts { set_case_analysis 0 $_p }
    puts "INFO: CDC-FUNCTIONAL-VIEW: case analysis 0 on scan_mode_i, scan_en_i and [llength $_ts] driver pin(s) of u_dft_ctrl.tap_serial"
}

###############################################################################
# Coverage guard + helper procs
###############################################################################
set ::cdc_exception_misses {}
# group name -> list of capture D pins, filled by the appliers, consumed by the script
set ::cdc_groups [dict create]
set ::cdc_ptr_info [dict create]
# capture D pins of the most recent cdc_apply_sync_budget call (one synchroniser = one pointer)
set ::cdc_last_pins {}
# group name -> expected budget (ns), so the script can verify the budget was actually applied
set ::cdc_group_budget [dict create]

proc cdc_require_match {collection description} {
    if {[llength $collection] > 0} {
        return 1
    }
    puts "ERROR: CDC-EXCEPTION-MISS: ${description} -- pattern matched an EMPTY collection. This CDC timing exception was NOT applied; the boundary is UNCONSTRAINED."
    lappend ::cdc_exception_misses $description
    return 0
}

set ::cdc_regs_by_clock [dict create]

proc cdc_regs_on_clock {clk_name} {
    if {![dict exists $::cdc_regs_by_clock $clk_name]} {
        set _nameset [dict create]
        foreach c [all_registers -clock [get_clocks $clk_name]] {
            dict set _nameset [get_full_name $c] 1
        }
        dict set ::cdc_regs_by_clock $clk_name $_nameset
    }
    return [dict get $::cdc_regs_by_clock $clk_name]
}

proc cdc_filter_by_clock {cells clk_name} {
    set _nameset [cdc_regs_on_clock $clk_name]
    set _result {}
    foreach c $cells {
        if {[dict exists $_nameset [get_full_name $c]]} {
            lappend _result $c
        }
    }
    return $_result
}

# Full name with OpenSTA's bracket/dot escaping removed, for Tcl `string match`.
proc cdc_plain_name {obj} {
    return [string map {"\\" ""} [get_full_name $obj]]
}

# cdc_sync_stage0_nets: the stage-0 Q nets of the synchroniser(s) whose full net name contains
# $inst_token and matches `sync_q[0]` (2-D `sync_q[0][b]` for WIDTH>1, 1-D `sync_q[0]` for
# WIDTH=1; stage 1 is `sync_q[1]...` and does not match).
proc cdc_sync_stage0_nets {inst_token} {
    set _out {}
    foreach _n [get_nets -hierarchical -filter "name =~ *${inst_token}*sync_q*" -quiet] {
        set _nm [cdc_plain_name $_n]
        # NOT `string match ...sync_q\[0\]...`: inside a double-quoted Tcl word that
        # becomes the glob character class [0], which matches "sync_q0", not "sync_q[0]".
        if {[string match "*${inst_token}*" $_nm] && [string first "sync_q\[0\]" $_nm] >= 0} {
            lappend _out $_n
        }
    }
    return $_out
}

# cdc_apply_sync_budget: for every stage-0 net of $inst_token, resolve
#   capture cell = the to_clk-domain register driving the net,
#   launch cells = the from_clk-domain startpoints in the fan-in of that cell's D pin,
# and apply `set_max_delay $val -from <launch> -to <capture cell>` PER BIT (a bus never mixes
# one bit's cells into another's exception). Capture D pins are recorded under $group for the
# script's report. Returns the number of bits applied; every unresolved bit is a recorded miss.
proc cdc_apply_sync_budget {group inst_token val from_clk to_clk description} {
    set ::cdc_last_pins {}
    set _nets [cdc_sync_stage0_nets $inst_token]
    if {![cdc_require_match $_nets $description]} {
        return 0
    }
    set _applied 0
    foreach _n $_nets {
        set _drv_pins [get_pins -of_objects $_n -filter {direction == output} -quiet]
        set _caps [cdc_filter_by_clock [get_cells -of_objects $_drv_pins -quiet] $to_clk]
        if {[llength $_caps] == 0} {
            puts "ERROR: CDC-EXCEPTION-MISS: ${description} (net [get_full_name $_n]) -- no ${to_clk}-domain register drives the stage-0 net. NOT applied."
            lappend ::cdc_exception_misses "${description} (net [get_full_name $_n])"
            continue
        }
        set _dpins [get_pins -of_objects $_caps -filter {direction == input && name == D} -quiet]
        if {[llength $_dpins] == 0} {
            puts "ERROR: CDC-EXCEPTION-MISS: ${description} (net [get_full_name $_n]) -- capture register has no D pin. NOT applied."
            lappend ::cdc_exception_misses "${description} (net [get_full_name $_n]) no D pin"
            continue
        }
        set _launch [cdc_filter_by_clock [get_fanin -to $_dpins -startpoints_only -flat -only_cells] $from_clk]
        if {[llength $_launch] == 0} {
            puts "ERROR: CDC-EXCEPTION-MISS: ${description} (net [get_full_name $_n]) -- no ${from_clk}-domain launch register in the fan-in of the capture D pin. NOT applied."
            lappend ::cdc_exception_misses "${description} (net [get_full_name $_n]) no launch"
            continue
        }
# Target the capture flop's D PIN, not the cell. The section-10 fallback is -to D pins, and OpenSTA ranks a pin-qualified exception above a cell-qualified one.
# So a -to <cell> budget silently loses to the fallback, whatever the declaration order.
# With both sides pin-qualified the later declaration wins, as the ASAP7 file documents.
        set_max_delay $val -from $_launch -to $_dpins
        dict lappend ::cdc_groups $group {*}$_dpins
        lappend ::cdc_last_pins {*}$_dpins
        incr _applied
    }
    dict set ::cdc_group_budget $group $val
    return $_applied
}

set_max_delay [expr {$clock_period * 0.9}] \
    -from [all_registers -clock cpu_clk] -to [all_registers -clock core_clk -data_pins]
set_max_delay [expr {$clock_period * 0.9}] \
    -from [all_registers -clock core_clk] -to [all_registers -clock cpu_clk -data_pins]

###############################################################################
# 10a. cdc_reset_sync async set/reset pins: cross-domain recovery/removal is waived.
set _async_to_cpu  [all_registers -clock cpu_clk  -async_pins]
set _async_to_core [all_registers -clock core_clk -async_pins]
if {[llength $_async_to_cpu] > 0}  { set_false_path -from [get_clocks core_clk] -to $_async_to_cpu }
if {[llength $_async_to_core] > 0} { set_false_path -from [get_clocks cpu_clk]  -to $_async_to_core }

###############################################################################
# 11. async_axi_fifo (u_cpu_axi_cdc): gray-pointer crossings, 0.5x destination period
#     (OpenTitan GRAY_MAX_DELAY). Each cdc_gray_fifo has two pointer synchronisers:
#       u_wr_ptr_to_rd : write domain -> read domain (capture = read clock)
#       u_rd_ptr_to_wr : read domain  -> write domain (capture = write clock)
#     AW/W/AR fifos: write = cpu_clk (s_clk_i), read = core_clk (m_clk_i)
#     B/R    fifos: write = core_clk,           read = cpu_clk
###############################################################################
set _cdc_fifo_dirs {
    u_aw_fifo cpu_clk  core_clk
    u_w_fifo  cpu_clk  core_clk
    u_ar_fifo cpu_clk  core_clk
    u_b_fifo  core_clk cpu_clk
    u_r_fifo  core_clk cpu_clk
}
foreach {_fifo _wr_clk _rd_clk} $_cdc_fifo_dirs {
    cdc_apply_sync_budget fifo_wr2rd "u_cpu_axi_cdc*${_fifo}*u_wr_ptr_to_rd" \
        [expr {$clock_period * 0.5}] $_wr_clk $_rd_clk \
        "sec.11 u_cpu_axi_cdc.${_fifo}.u_wr_ptr_to_rd gray-pointer crossing ($_wr_clk -> $_rd_clk)"
    dict set ::cdc_ptr_info "${_fifo}.wr2rd" [list $_wr_clk $_rd_clk $::cdc_last_pins]
    cdc_apply_sync_budget fifo_rd2wr "u_cpu_axi_cdc*${_fifo}*u_rd_ptr_to_wr" \
        [expr {$clock_period * 0.5}] $_rd_clk $_wr_clk \
        "sec.11 u_cpu_axi_cdc.${_fifo}.u_rd_ptr_to_wr gray-pointer crossing ($_rd_clk -> $_wr_clk)"
    dict set ::cdc_ptr_info "${_fifo}.rd2wr" [list $_rd_clk $_wr_clk $::cdc_last_pins]
}

###############################################################################
# 12 / 12a. apb_cdc_bridge (u_apb_pll2_cdc, u_apb_dbg_cdc): 4-phase RZ handshake, req_q is
#     launched in the s (core_clk) domain and captured in the m (cpu_clk) domain, ack_q the
#     reverse. 1.0x destination period (lower-rate control crossings, as in the ASAP7 file).
#     The cmd_*/resp_* payload registers are covered by the section-10 fallback.
###############################################################################
foreach {_br _grp} {u_apb_pll2_cdc apb_pll2 u_apb_dbg_cdc apb_dbg} {
    cdc_apply_sync_budget ${_grp}_req "${_br}*u_req_sync" $clock_period core_clk cpu_clk \
        "sec.12 ${_br} req_q level crossing (core_clk -> cpu_clk)"
    cdc_apply_sync_budget ${_grp}_ack "${_br}*u_ack_sync" $clock_period cpu_clk core_clk \
        "sec.12 ${_br} ack_q level crossing (cpu_clk -> core_clk)"
}

# u_apb_dbg_cdc also carries a third crossing, u_m_rst_status_sync (m-side reset status ->
# s side, cpu_clk -> core_clk), found by enumerating every stage-0 synchroniser flop whose D
# fan-in reaches the other domain on the baseline netlist (18 crossings: 10 FIFO pointer
# groups, 4 bridge req/ack, this one, 4 PMU/IRQ -- all budgeted). The u_apb_pll2_cdc copy is
# optimised away, so it is deliberately NOT listed (an entry for it would be a permanent miss).
cdc_apply_sync_budget apb_dbg_rst_status "u_apb_dbg_cdc*u_m_rst_status_sync" $clock_period cpu_clk core_clk \
    "sec.12a u_apb_dbg_cdc u_m_rst_status_sync single-bit crossing (cpu_clk -> core_clk)"

###############################################################################
# 13. PMU / IRQ single-bit crossings into the cpu_clk domain (cdc_sync instances in soc_top):
#     u_cpu_clk_dis_sync, u_cpu_iso_en_sync, u_ext_irq_sync, u_timer_irq_sync (13a below adds
#     the one return crossing, u_cpu_iso_ack_sync, cpu_clk -> core_clk).
#     1.0x destination period. (pmu_cpu_rst_n's cdc_reset_sync needs no entry: it has no
#     data input, only an async clear, covered by sec 10a.)
###############################################################################
foreach {_s _g} {u_cpu_clk_dis_sync pmu_clk_dis u_cpu_iso_en_sync pmu_iso_en \
                 u_ext_irq_sync ext_irq u_timer_irq_sync timer_irq} {
    cdc_apply_sync_budget $_g $_s $clock_period core_clk cpu_clk \
        "sec.13 ${_s} single-bit crossing (core_clk -> cpu_clk)"
}

cdc_apply_sync_budget pmu_iso_ack u_cpu_iso_ack_sync $clock_period cpu_clk core_clk \
    "sec.13a u_cpu_iso_ack_sync single-bit crossing (cpu_clk -> core_clk)"

set ::cdc_mb_const_bits {}
set ::cdc_group_from [dict create]

proc cdc_mb_budget {val} {
    if {[info exists ::env(CDC_CHECK_MBIST_BUDGET_NS)] && $::env(CDC_CHECK_MBIST_BUDGET_NS) ne ""} {
        return $::env(CDC_CHECK_MBIST_BUDGET_NS)
    }
    return $val
}

# Startpoint cells in the fan-in of $dpins, optionally minus the registers of clock $excl_clk.
proc cdc_mb_startpoints {dpins excl_clk} {
    # Startpoint PINS, not cells: a hard-macro output with no launching arc (the tied-0 mbist_status_o bits) comes back
    # as the macro's OUTPUT pin, while a real launch comes back as a clock INPUT pin (clk_i / CLK). Only the latter
    # is a launch; `-only_cells` would report the macro instance for both and hide the difference.
    set _sp {}
    foreach _p [get_fanin -to $dpins -startpoints_only -flat] {
        if {[catch {get_property $_p lib_pin_name}]} { continue }   ;# a port, not a pin
        if {[get_property $_p direction] ne "input"} { continue }
        foreach _c [get_cells -of_objects $_p] { lappend _sp $_c }
    }
    set _sp [lsort -unique $_sp]
    if {$excl_clk eq ""} { return $_sp }
    set _ns [cdc_regs_on_clock $excl_clk]
    set _r {}
    foreach c $_sp { if {![dict exists $_ns [get_full_name $c]]} { lappend _r $c } }
    return $_r
}

# launch_excl: "" = every startpoint; a clock name = every startpoint that is NOT a register of that clock
# (this is how the TCK side is found without `all_registers -clock tck`, see section 1).
# const_ok: list of bit indices (parsed from `g_bit[N]` in the net name) allowed to have NO launch cell.
# One set_max_delay per bit. Returns the bits applied; unresolved bits are recorded misses.
proc cdc_mb_apply_sync {group inst_token val launch_excl to_clk description const_ok} {
    set ::cdc_last_pins {}
    set val [cdc_mb_budget $val]
    set _nets [cdc_sync_stage0_nets $inst_token]
    if {![cdc_require_match $_nets $description]} { return 0 }
    set _applied 0
    foreach _n $_nets {
        set _drv_pins [get_pins -of_objects $_n -filter {direction == output} -quiet]
        set _caps [cdc_filter_by_clock [get_cells -of_objects $_drv_pins -quiet] $to_clk]
        if {[llength $_caps] == 0} {
            puts "ERROR: CDC-EXCEPTION-MISS: ${description} (net [get_full_name $_n]) -- no ${to_clk}-domain register drives the stage-0 net. NOT applied."
            lappend ::cdc_exception_misses "${description} (net [get_full_name $_n])"
            continue
        }
        set _dpins [get_pins -of_objects $_caps -filter {direction == input && name == D} -quiet]
        if {[llength $_dpins] == 0} {
            lappend ::cdc_exception_misses "${description} (net [get_full_name $_n]) no D pin"
            continue
        }
        set _launch [cdc_mb_startpoints $_dpins $launch_excl]
        if {[llength $_launch] == 0} {
            set _idx -1
            regexp {g_bit\[([0-9]+)\]} [cdc_plain_name $_n] -> _idx
            if {$_idx >= 0 && [lsearch -exact $const_ok $_idx] >= 0} {
                lappend ::cdc_mb_const_bits "${group}\[$_idx\]"
                continue
            }
            puts "ERROR: CDC-EXCEPTION-MISS: ${description} (net [get_full_name $_n]) -- no launch cell in the fan-in of the capture D pin. NOT applied."
            lappend ::cdc_exception_misses "${description} (net [get_full_name $_n]) no launch"
            continue
        }
        set_max_delay $val -from $_launch -to $_dpins
        dict lappend ::cdc_groups $group {*}$_dpins
        dict lappend ::cdc_group_from $group {*}$_launch
        lappend ::cdc_last_pins {*}$_dpins
        incr _applied
    }
    dict set ::cdc_group_budget $group $val
    return $_applied
}

# mem_q -> ctl_q payload. Launch = the flops behind the `u_fifo*mem_q*` nets (the FIFO storage, found by NAME because
# yosys keeps the storage nets but renames/merges the bus nets after the holding register: ctl_w[26:1] comes back
# as core_cfg_w). Capture = every destination-domain register D pin in the fan-out of those flops (the holding
# register's bits; anything else the storage reached would show up in the count check). One exception per
# domain: every entry reaches every bit through the read mux.
proc cdc_mb_apply_data {group inst_token val dst_clk description} {
    set val [cdc_mb_budget $val]
    set _nets {}
    foreach _n [get_nets -hierarchical -filter "name =~ *${inst_token}*mem_q*" -quiet] {
        set _nm [cdc_plain_name $_n]
        if {[string match "*${inst_token}*u_fifo*" $_nm]} { lappend _nets $_n }
    }
    if {![cdc_require_match $_nets $description]} { return 0 }
    set _dst [cdc_regs_on_clock $dst_clk]
    set _launch {}
    set _qpins {}
    foreach _n $_nets {
        foreach _p [get_pins -of_objects $_n -filter {direction == output} -quiet] {
            foreach _c [get_cells -of_objects $_p] {
                if {[dict exists $_dst [get_full_name $_c]]} { continue }
                lappend _launch $_c
                lappend _qpins $_p
            }
        }
    }
    set _launch [lsort -unique $_launch]
    if {[llength $_launch] == 0} {
        puts "ERROR: CDC-EXCEPTION-MISS: ${description} -- no non-${dst_clk} register drives a mem_q net. NOT applied."
        lappend ::cdc_exception_misses "${description} launch"
        return 0
    }
    set _dpins {}
    foreach _e [get_fanout -from $_qpins -endpoints_only -flat] {
        if {[catch {get_property $_e lib_pin_name} _lp]} { continue }   ;# a port, not a pin
        if {$_lp ne "D"} { continue }
        set _c [get_cells -of_objects $_e]
        if {[dict exists $_dst [get_full_name $_c]]} { lappend _dpins $_e }
    }
    set _dpins [lsort -unique $_dpins]
    if {[llength $_dpins] == 0} {
        puts "ERROR: CDC-EXCEPTION-MISS: ${description} -- no ${dst_clk} register D pin in the fan-out of the mem_q flops. NOT applied."
        lappend ::cdc_exception_misses "${description} capture"
        return 0
    }
    set_max_delay $val -from $_launch -to $_dpins
    dict lappend ::cdc_groups $group {*}$_dpins
    dict lappend ::cdc_group_from $group {*}$_launch
    dict set ::cdc_group_budget $group $val
    puts "INFO: MBIST-XING: $group: [llength $_launch] mem_q launch flops -> [llength $_dpins] ${dst_clk} D pins."
    return [llength $_dpins]
}

if {[llength [get_clocks -quiet tck]] > 0 && [llength [get_nets -hierarchical -filter "name =~ *u_xing_core*" -quiet]] > 0} {
    set _mb_gray [expr {0.5 * min($clock_period, $tck_period)}]
    set _mb_pay  [expr {0.9 * $clock_period}]
    set _mb_bit  [expr {1.0 * min($clock_period, $tck_period)}]
    # Expected bit counts (a count that drifts means a crossing silently lost or gained a bit: a miss, not a pass):
    # DEPTH-2 gray pointer = 2 bits; status block: core 61 (69 minus fail[9:2] of the 8 absent memories, constants that yosys removes), CPU 34 real + 35 constant-0 macro pins; ctl_q 28 bits
    # per domain (the 29-bit word's other-domain enable bit has no consumer in this domain and is optimised away).
    proc cdc_mb_expect {what got want} {
        if {$got != $want} {
            puts "ERROR: CDC-EXCEPTION-MISS: sec.14 $what: bound $got bit(s), expected $want."
            lappend ::cdc_exception_misses "sec.14 $what bit count $got != $want"
        }
    }
    foreach {_dom _xing _sts _dclk _nstat} {
        core u_xing_core u_stsync_core core_clk 61
        cpu  u_xing_cpu  u_stsync_cpu  cpu_clk  34
    } {
        # tck -> dst gray write pointer: launch = the TCK-side pointer flops (everything not in the dst domain)
        set _n [cdc_mb_apply_sync mb_${_dom}_wr2rd "${_xing}*u_fifo*u_wr_ptr_to_rd" $_mb_gray $_dclk $_dclk \
            "sec.14 ${_xing} write-pointer crossing (tck -> ${_dclk})" {}]
        cdc_mb_expect "${_xing} wr2rd" $_n 2
        dict set ::cdc_ptr_info "mb_${_dom}.wr2rd" [list tck $_dclk $::cdc_last_pins]
        # dst -> tck gray read pointer: launch = the dst-domain pointer flops
        set _n [cdc_mb_apply_sync mb_${_dom}_rd2wr "${_xing}*u_fifo*u_rd_ptr_to_wr" $_mb_gray "" tck \
            "sec.14 ${_xing} read-pointer crossing (${_dclk} -> tck)" {}]
        cdc_mb_expect "${_xing} rd2wr" $_n 2
        dict set ::cdc_ptr_info "mb_${_dom}.rd2wr" [list $_dclk tck $::cdc_last_pins]
        # FIFO storage -> holding register
        set _n [cdc_mb_apply_data mb_${_dom}_data $_xing $_mb_pay $_dclk \
            "sec.14 ${_xing} mem_q -> ctl_q payload (tck -> ${_dclk})"]
        cdc_mb_expect "${_xing} ctl_q" $_n 28
        # status block, dst -> tck, one 2-FF per bit
        set _const_ok {}
        if {$_dom eq "cpu"} {
            # rec_addr[9:8] (bits 23:22; the macro controller has AW = 8), rec_port[1] (36), err_mask (68:37)
            set _const_ok {22 23}
            for {set _i 36} {$_i <= 68} {incr _i} { lappend _const_ok $_i }
        }
        set _n [cdc_mb_apply_sync mb_${_dom}_status $_sts $_mb_bit "" tck \
            "sec.14 ${_sts} status bits (${_dclk} -> tck)" $_const_ok]
        cdc_mb_expect "${_sts} status" $_n $_nstat
    }
    cdc_mb_expect "constant status bits (cpu)" [llength $::cdc_mb_const_bits] 35
    puts "INFO: MBIST-XING: constant (no launching arc) status bits accounted for: [llength $::cdc_mb_const_bits] ($::cdc_mb_const_bits)"
}

###############################################################################
# 15. Coverage gate: any miss above is a hard Tcl error (the script turns it into a finding).
###############################################################################
if {[llength $::cdc_exception_misses] > 0} {
    puts "ERROR: CDC-EXCEPTION-MISS: [llength $::cdc_exception_misses] CDC timing exception(s) failed to bind:"
    foreach _miss $::cdc_exception_misses {
        puts "ERROR: CDC-EXCEPTION-MISS:   - ${_miss}"
    }
    error "sky130_soc_cdc_check.sdc: [llength $::cdc_exception_misses] CDC timing exception(s) matched nothing -- see CDC-EXCEPTION-MISS lines above."
}
