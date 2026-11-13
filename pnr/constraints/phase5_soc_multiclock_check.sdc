# phase5_soc_multiclock_check.sdc — POST-ROUTE CDC BUDGET VERIFICATION ONLY
# These SDC's are not used for synthesis, since they collide with the
# set_clock_groups -asynchronous constraint in phase5_soc_multiclock.sdc.
# Instead, they are used to time the design after P&R in order to make sure
# that the CDC crossings are all within spec. (Wording deliberately mirrors
# OpenTitan's hw/top_earlgrey/syn/chip_earlgrey_asic_check_only.sdc, the
# precedent this split follows.)
# USAGE — read this file's purpose narrowly:
#   This file is for TARGETED post-route queries against the specific CDC
#   endpoints named in sections 10-13 below (report_checks -to/-through a
#   named pin, as pnr/scripts/check_cdc_timing.tcl does). It is NOT a
#   substitute full-chip signoff SDC: because sys_clk and cpu_clk have no
#   group/false-path relationship here, a full unfiltered `report_checks`
#   or `report_wns`/`report_tns` sweep against this file WILL show
#   fabricated setup/hold violations on every OTHER pair of FFs that
#   happen to sit in different domains but are not part of a deliberate
#   synchroniser (there is no exception suppressing those, by design — see
#   above). That is expected, not a defect: interrogate specific CDC paths
#   only. Full-chip signoff continues to use phase5_soc_multiclock.sdc.
# Base: sections 1 (clocks) and 4 (async reset false-paths) are copied
# verbatim from phase5_soc_multiclock.sdc so this file is self-contained
# for read_sdc; keep them in sync by hand if either file's clock periods
# change (Run-13 CTS lesson applies identically here — do NOT add
# create_generated_clock for core_clk/cpu_core_clk).
# Doc: tm:pd:phase5-soc-multiclock-check-sdc, cr:pd:phase5-soc-multiclock-check-sdc

create_clock -name sys_clk -period 1750 -waveform {0 875} [get_ports clk_i]

set_clock_uncertainty -setup 15 [get_clocks sys_clk]
set_clock_uncertainty -hold  10 [get_clocks sys_clk]
set_clock_transition   10       [get_clocks sys_clk]
set_clock_latency -source 50    [get_clocks sys_clk]

create_clock -name cpu_clk -period 780 -waveform {0 390} [get_ports cpu_clk_i]

set_clock_uncertainty -setup 15 [get_clocks cpu_clk]
set_clock_uncertainty -hold  10 [get_clocks cpu_clk]
set_clock_transition   10       [get_clocks cpu_clk]
set_clock_latency -source 50    [get_clocks cpu_clk]

# DELIBERATE ABSENCE: no set_clock_groups -asynchronous, no
# set_false_path -from/-to between sys_clk and cpu_clk. See the file
# header — this is the entire reason the file exists.

###############################################################################
# 4. Asynchronous resets — not timed (verbatim copy of section 4; harmless
#    here and prevents port-reset noise from polluting -through queries).
###############################################################################
set_false_path -from [get_ports rst_n_i]
set_false_path -from [get_ports cpu_rst_n_i]

set ::cdc_exception_misses {}

proc cdc_require_match {collection description} {
    if {[llength $collection] > 0} {
        return 1
    }
    puts "ERROR: CDC-EXCEPTION-MISS: ${description} -- pattern matched an EMPTY collection. This CDC timing exception was NOT applied; the boundary is UNCONSTRAINED."
    lappend ::cdc_exception_misses $description
    return 0
}

# cdc_net_from_to: given a (possibly multi-bit) net collection that is
# somewhere on a synchroniser's launch->first-capture path, return
# {startpoint_cells endpoint_cells} suitable for `set_max_delay -from -to`.
set ::cdc_regs_by_clock [dict create]

proc cdc_regs_on_clock {clk_name} {
    if {![dict exists $::cdc_regs_by_clock $clk_name]} {
        set _regs [all_registers -clock [get_clocks $clk_name]]
        set _nameset [dict create]
        foreach c $_regs {
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

proc cdc_net_from_to {onenet from_clk to_clk} {
    set _drv_pins [get_pins -of_objects $onenet -filter {direction == output} -quiet]
    set _ld_pins  [get_pins -of_objects $onenet -filter {direction == input} -quiet]
    set _from_cells [get_fanin  -to   $_ld_pins  -startpoints_only -flat -only_cells]
    set _to_cells   [get_fanout -from $_drv_pins -endpoints_only   -flat -only_cells]
    set _from_cells [cdc_filter_by_clock $_from_cells $from_clk]
    set _to_cells   [cdc_filter_by_clock $_to_cells   $to_clk]
    return [list $_from_cells $_to_cells]
}

# cdc_apply_max_delay: cdc_require_match on the (possibly multi-bit) net
# collection, then apply set_max_delay via -from/-to (NOT -through -- see
# OBJECT RESOLUTION item 6: -through is silently dominated by the section-10
# domain-wide -from/-to fallback on this tool/netlist, -from/-to is not) ONE
# BIT AT A TIME (cdc_net_from_to per net, not on the whole collection --
# see that proc's header). Returns 1 if at least one bit's exception was
# applied, 0 (and records a finding for every bit that failed) otherwise.
proc cdc_apply_max_delay {netc val from_clk to_clk description} {
    if {![cdc_require_match $netc $description]} {
        return 0
    }
    set _applied 0
    foreach _onenet $netc {
        lassign [cdc_net_from_to $_onenet $from_clk $to_clk] _drv _ld
        if {[llength $_drv] == 0 || [llength $_ld] == 0} {
            puts "ERROR: CDC-EXCEPTION-MISS: ${description} (bit [get_name $_onenet]) -- driver/load cells on the expected clocks ($from_clk/$to_clk) could not be resolved (drv=[llength $_drv] ld=[llength $_ld]). This bit's CDC timing exception was NOT applied."
            lappend ::cdc_exception_misses "${description} (bit [get_name $_onenet])"
            continue
        }
        set_max_delay $val -from $_drv -to $_ld
        incr _applied
    }
    return [expr {$_applied > 0}]
}

proc cdc_capture_flop_d_pins {substr_list from_clk to_clk} {
    set _to_regs [all_registers -clock [get_clocks $to_clk]]
    set _pins {}
    foreach _reg $_to_regs {
        set _fn [get_full_name $_reg]
        set _match 1
        foreach _s $substr_list {
            if {![string match "*${_s}*" $_fn]} {
                set _match 0
                break
            }
        }
        if {!$_match} {
            continue
        }
        set _dpin [get_pins -of_objects $_reg -filter {direction == input && name == D} -quiet]
        if {[llength $_dpin] == 0} {
            continue
        }
        set _fanin_cells [get_fanin -to $_dpin -startpoints_only -flat -only_cells]
        set _fanin_from  [cdc_filter_by_clock $_fanin_cells $from_clk]
        if {[llength $_fanin_from] > 0} {
            lappend _pins $_dpin
        }
    }
    return $_pins
}

# cdc_apply_max_delay_capture_fallback: same contract/finding-accumulation
# as cdc_apply_max_delay (same $::cdc_exception_misses list, same
# non-vacuous requirement -- an empty result IS a recorded
# CDC-EXCEPTION-MISS, not a silent skip), but driven by
# cdc_capture_flop_d_pins instead of a `d_i`-name net collection. Only
# called when the primary d_i-name match is empty (callers check that
# themselves) so flat/run-23-style netlists are completely unaffected --
# they always take the cdc_apply_max_delay path, byte-identical to before.
proc cdc_apply_max_delay_capture_fallback {substr_list val from_clk to_clk description} {
    set _pins [cdc_capture_flop_d_pins $substr_list $from_clk $to_clk]
    if {[llength $_pins] == 0} {
        puts "ERROR: CDC-EXCEPTION-MISS: ${description} -- capture-flop D-pin fallback (deferred_flatten) ALSO found no ${to_clk}-domain flop under *[join $substr_list {*}]* whose D-pin fan-in reaches ${from_clk}. This CDC timing exception was NOT applied; the boundary is UNCONSTRAINED."
        lappend ::cdc_exception_misses $description
        return 0
    }
    set _applied 0
    foreach _dp $_pins {
        set _cell [get_cells -of_objects $_dp -quiet]
        set _from_cells [cdc_filter_by_clock [get_fanin -to $_dp -startpoints_only -flat -only_cells] $from_clk]
        if {[llength $_from_cells] == 0 || [llength $_cell] == 0} {
            puts "ERROR: CDC-EXCEPTION-MISS: ${description} (capture pin [get_full_name $_dp]) -- driver/load cells on the expected clocks ($from_clk/$to_clk) could not be resolved. This bit's CDC timing exception was NOT applied."
            lappend ::cdc_exception_misses "${description} (capture pin [get_full_name $_dp])"
            continue
        }
        set_max_delay $val -from $_from_cells -to $_cell
        incr _applied
    }
    return [expr {$_applied > 0}]
}

set_max_delay [expr {1750 * 0.9}] \
    -from [all_registers -clock cpu_clk] -to [all_registers -clock sys_clk]
set_max_delay [expr {780 * 0.9}] \
    -from [all_registers -clock sys_clk] -to [all_registers -clock cpu_clk]

proc cdc_reset_sync_async_pins {} {
    set _pins {}
    foreach _clk {sys_clk cpu_clk} {
        foreach _reg [all_registers -clock [get_clocks $_clk]] {
            if {![string match "*rst_sync*" [get_full_name $_reg]]} {
                continue
            }
            foreach _pn {RESETN SETN} {
                set _p [get_pins -of_objects $_reg \
                    -filter "direction == input && name == $_pn" -quiet]
                foreach _x $_p { lappend _pins $_x }
            }
        }
    }
    return $_pins
}
set _reset_sync_async_pins [cdc_reset_sync_async_pins]
if {[cdc_require_match $_reset_sync_async_pins "sec.10a cdc_reset_sync async set/reset pins (rst_both_n / pll-lock-derived core_rst_n class, RTL-confirmed bead je8) excluded from domain-wide max_delay fallback"]} {
    set_false_path -to $_reset_sync_async_pins
}

###############################################################################
# 11. CPU<->fabric CDC boundary — async_axi_fifo (instance u_cpu_axi_cdc)
set _cdc_fifo_dirs {
    u_aw_fifo cpu_clk 780  sys_clk 1750
    u_w_fifo  cpu_clk 780  sys_clk 1750
    u_ar_fifo cpu_clk 780  sys_clk 1750
    u_b_fifo  sys_clk 1750 cpu_clk 780
    u_r_fifo  sys_clk 1750 cpu_clk 780
}

foreach {_fifo_inst _wr_clk _wr_period _rd_clk _rd_period} $_cdc_fifo_dirs {
    # (1) u_wr_ptr_to_rd.d_i: wr_gray_q -> rd domain — 0.5x rd (destination) period
    set _wr2rd [get_nets -hierarchical -filter "name =~ *u_cpu_axi_cdc*${_fifo_inst}*u_wr_ptr_to_rd*d_i*" -quiet]
    if {[llength $_wr2rd] > 0} {
        cdc_apply_max_delay $_wr2rd [expr {$_rd_period * 0.5}] $_wr_clk $_rd_clk \
            "sec.11 u_cpu_axi_cdc.${_fifo_inst}.u_wr_ptr_to_rd.d_i gray-pointer crossing"
    } else {
        cdc_apply_max_delay_capture_fallback [list u_cpu_axi_cdc $_fifo_inst u_wr_ptr_to_rd] \
            [expr {$_rd_period * 0.5}] $_wr_clk $_rd_clk \
            "sec.11 u_cpu_axi_cdc.${_fifo_inst}.u_wr_ptr_to_rd.d_i gray-pointer crossing"
    }

    # (2) rd_gray_q (source register for u_rd_ptr_to_wr's vanished d_i):
    #     rd_gray_q -> wr domain — 0.5x wr (destination) period
    set _rd2wr [get_nets -hierarchical -filter "name =~ *u_cpu_axi_cdc*${_fifo_inst}*rd_gray_q*" -quiet]
    cdc_apply_max_delay $_rd2wr [expr {$_wr_period * 0.5}] $_rd_clk $_wr_clk \
        "sec.11 u_cpu_axi_cdc.${_fifo_inst}.rd_gray_q gray-pointer crossing"
}

###############################################################################
# 12. APB_PLL2 CDC bridge — apb_cdc_bridge (instance u_apb_pll2_cdc)
set _req_sync [get_nets -hierarchical -filter {name =~ *u_apb_pll2_cdc*req_q*} -quiet]
cdc_apply_max_delay $_req_sync 780 sys_clk cpu_clk \
    "sec.12 u_apb_pll2_cdc.req_q level crossing (s->m)"

set _ack_sync [get_nets -hierarchical -filter {name =~ *u_apb_pll2_cdc*ack_q*} -quiet]
cdc_apply_max_delay $_ack_sync 1750 cpu_clk sys_clk \
    "sec.12 u_apb_pll2_cdc.ack_q level crossing (m->s)"

# cmd_*/resp_* payload (u_apb_pll2_cdc): unmatchable by name -- see
# section 10's domain-wide fallback, which covers this crossing instead.

###############################################################################
# 12a. APB debug-port CDC bridge — apb_cdc_bridge (instance u_apb_dbg_cdc)
set _dbg_req_sync [get_nets -hierarchical -filter {name =~ *u_apb_dbg_cdc*req_q*} -quiet]
cdc_apply_max_delay $_dbg_req_sync 780 sys_clk cpu_clk \
    "sec.12a u_apb_dbg_cdc.req_q level crossing (s->m)"

set _dbg_ack_sync [get_nets -hierarchical -filter {name =~ *u_apb_dbg_cdc*ack_q*} -quiet]
cdc_apply_max_delay $_dbg_ack_sync 1750 cpu_clk sys_clk \
    "sec.12a u_apb_dbg_cdc.ack_q level crossing (m->s)"

# cmd_*/resp_* payload (u_apb_dbg_cdc): unmatchable by name -- see
# section 10's domain-wide fallback, which covers this crossing instead.

set _rst_sync_pins [get_nets pmu_cpu_rst_n -quiet]
if {[cdc_require_match $_rst_sync_pins "sec.13 pmu_cpu_rst_n async-clear reset sync (false_path)"]} {
    set_false_path -through $_rst_sync_pins
}

set _clk_dis_di [get_nets -hierarchical -filter {name =~ *u_cpu_clk_dis_sync*d_i*} -quiet]
if {[llength $_clk_dis_di] > 0} {
    cdc_apply_max_delay $_clk_dis_di 780 sys_clk cpu_clk \
        "sec.13 u_cpu_clk_dis_sync.d_i single-bit CDC crossing"
} else {
    cdc_apply_max_delay_capture_fallback {u_cpu_clk_dis_sync} 780 sys_clk cpu_clk \
        "sec.13 u_cpu_clk_dis_sync.d_i single-bit CDC crossing"
}

set _iso_en_src [get_nets pmu_cpu_iso_en -quiet]
cdc_apply_max_delay $_iso_en_src 780 sys_clk cpu_clk \
    "sec.13 pmu_cpu_iso_en (source of u_cpu_iso_en_sync) single-bit CDC crossing"

set _ext_irq_src [get_nets ext_irq -quiet]
cdc_apply_max_delay $_ext_irq_src 780 sys_clk cpu_clk \
    "sec.13 ext_irq (source of u_ext_irq_sync) single-bit CDC crossing"

set _timer_irq_src [get_nets timer_irq -quiet]
cdc_apply_max_delay $_timer_irq_src 780 sys_clk cpu_clk \
    "sec.13 timer_irq (source of u_timer_irq_sync) single-bit CDC crossing"

set _iso_ack_src [get_nets pmu_cpu_iso_en_sync -quiet]
cdc_apply_max_delay $_iso_ack_src 1750 cpu_clk sys_clk \
    "sec.13a pmu_cpu_iso_en_sync (source of u_cpu_iso_ack_sync) single-bit CDC crossing (cpu_clk -> sys_clk)"

###############################################################################
# 15. CDC exception coverage gate — hard-fail on any section 11-13 miss.
#
# See the cdc_require_match / cdc_apply_max_delay procs and the
# ::cdc_exception_misses list defined just before section 11. If ANY
# exception's get_nets pattern matched an empty collection, or matched but
# its driver/load cells could not be resolved, above, a CDC-EXCEPTION-MISS
# line was already puts'd at the point of failure. This final check
# promotes that from "logged" to "fatal": abort read_sdc with a
# nonzero-equivalent Tcl `error` rather than let the file finish reading as
# if nothing were wrong — an unconstrained CDC boundary that STA reports as
# "clean" is a strictly worse outcome than an aborted read_sdc that names
# the missing instance/pin/net. Section 10's domain-wide fallback has no
# name-match step and so can never itself trigger this gate.
###############################################################################
if {[llength $::cdc_exception_misses] > 0} {
    puts "ERROR: CDC-EXCEPTION-MISS: [llength $::cdc_exception_misses] of sections 11-13's CDC timing exceptions failed to match any object:"
    foreach _miss $::cdc_exception_misses {
        puts "ERROR: CDC-EXCEPTION-MISS:   - ${_miss}"
    }
    error "phase5_soc_multiclock_check.sdc: [llength $::cdc_exception_misses] CDC timing exception(s) in sections 11-13 matched an EMPTY collection -- see CDC-EXCEPTION-MISS lines above. Fix the referenced instance/pin/net path (RTL rename or hierarchy flattening) before trusting this SDC's STA results."
}
