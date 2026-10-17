###############################################################################
# sky130_soc_cdc_check.sdc -- POST-ROUTE CDC BUDGET VERIFICATION ONLY (Sky130 SoC)
#
# bead claude_verilog_test-j41m.5 (2026-10-16). Sky130 port of
# pnr/constraints/phase5_soc_multiclock_check.sdc (ASAP7). Read ONLY by
# pnr/scripts/check_cdc_timing_sky130.tcl (`make -C pnr check-cdc-timing-sky130-soc`).
# It is NOT an implementation SDC: sky130_soc.sdc is (it declares core_clk / cpu_clk
# asynchronous), this file deliberately does not.
#
# WHY A SEPARATE FILE (tool-verified by bead k07, OpenSTA 2.6.0 and the OpenROAD-embedded
# engine, restated in sky130_soc.sdc "Clock groups"):
#   1. set_max_delay has no -datapath_only flag in OpenSTA; read_sdc aborts with STA-0563.
#      It is therefore never used here.
#   2. A set_max_delay between clocks that are declared set_clock_groups -asynchronous (or
#      false-pathed) is dropped: set_false_path > set_max_delay, whatever the specificity.
# So the CDC budgets can only be timed by a file that declares BOTH clocks and NEVER relates
# them. Consequence (same as the ASAP7 file): this file is for TARGETED queries on the
# crossings below; a full unfiltered report_wns/report_tns against it would show fabricated
# violations on every unrelated pair of flops that happen to sit in different domains.
#
# WHAT IS DIFFERENT FROM THE ASAP7 FILE, AND WHY (tool-verified on the Sky130 SoC netlist, not
# assumed -- see the object-resolution notes below):
#   * Time unit is NANOSECONDS (sky130_fd_sc_hd Liberty time_unit 1ns), not picoseconds.
#   * Both clocks are 25.0 ns, so every budget is a ratio of 25.0 (gray pointers 0.5x, the
#     handshake and single-bit crossings 1.0x, the domain-wide fallback 0.9x, the same
#     ratios the ASAP7 file uses against the destination period).
#   * SYNTH_HIERARCHY_MODE is flatten here too: cells are anonymous (_143120_), hierarchy
#     survives only as dot-joined escaped NET names. But, unlike ASAP7, the plain top-level
#     nets pmu_cpu_iso_en / ext_irq / timer_irq / pmu_cpu_rst_n and, for several gray
#     pointers, the d_i nets do NOT survive. What always survives is the synchroniser's own
#     stage-0 Q net (`<inst>.sync_q[0]...`), and its driver is by construction the capture
#     flop. So EVERY crossing below is found structurally from that net: capture flop = the
#     driver of the stage-0 net; launch flops = the from_clk-domain startpoints in the fan-in
#     of its D pin (get_fanin -flat traces through any buffer/inverter synthesis inserted).
#   * Sky130 flops expose Q (ASAP7 ones only QN), so no polarity-inverter hazard, but the
#     fan-in trace is kept anyway because it is also what makes a shared buffer harmless.
#   * Async set/reset pins are handled structurally (all_registers -async_pins) instead of by
#     the "rst_sync" instance-name match the ASAP7 file needs, which cannot work on anonymous
#     cells.
#
# OBJECT-RESOLUTION GOTCHAS carried over from the ASAP7 file and re-verified here:
#   * `get_nets -hierarchical -filter {name =~ *a.b*}`: a literal '.' inside the pattern is
#     not a safe glob character in this tool. Patterns below are '*'-joined dot-free tokens;
#     any finer test is done in Tcl with `string match` on the full name.
#   * -from/-to exceptions beat -through ones, and between two overlapping -from/-to ones the
#     LAST DECLARED wins -> the broad domain-wide fallback (section 10) is declared FIRST.
#   * A non-empty match proves a NAME matched, not that the exception bound. The script checks
#     every group by reading the budget back out of the timing report.
###############################################################################

###############################################################################
# 1. Clocks (same period/uncertainty as sky130_soc.sdc; NOT related to each other)
###############################################################################
set clock_period 25.0

create_clock -name core_clk -period $clock_period [get_ports clk_i]
set_clock_uncertainty -setup 0.300 [get_clocks core_clk]
set_clock_uncertainty -hold  0.150 [get_clocks core_clk]

create_clock -name cpu_clk -period $clock_period [get_ports cpu_clk_i]
set_clock_uncertainty -setup 0.300 [get_clocks cpu_clk]
set_clock_uncertainty -hold  0.150 [get_clocks cpu_clk]

# DELIBERATE ABSENCE: no set_clock_groups, no set_false_path between core_clk and cpu_clk.

###############################################################################
# 2. Asynchronous reset ports (as in sky130_soc.sdc)
###############################################################################
set_false_path -from [get_ports rst_n_i]
set_false_path -from [get_ports cpu_rst_n_i]

###############################################################################
# Coverage guard + helper procs
###############################################################################
set ::cdc_exception_misses {}
# group name -> list of capture D pins, filled by the appliers, consumed by the script
set ::cdc_groups [dict create]
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
        # -to the capture flop's D PIN, not the cell: the section-10 fallback is -to D pins, and
        # OpenSTA ranks a pin-qualified exception above a cell-qualified one, so a -to <cell>
        # budget silently LOSES to the fallback whatever the declaration order (measured on the
        # baseline netlist: the intended 25.0 ns applied as the fallback's 22.5 ns). With both
        # sides pin-qualified the later declaration wins, as the ASAP7 file documents.
        set_max_delay $val -from $_launch -to $_dpins
        dict lappend ::cdc_groups $group {*}$_dpins
        incr _applied
    }
    dict set ::cdc_group_budget $group $val
    return $_applied
}

###############################################################################
# 10. Domain-wide fallback budget for the payload crossings that cannot be found by name
#     (the 5x async_axi_fifo mem_q combinational reads and the apb_cdc_bridge cmd_*/resp_*
#     capture registers): 0.9x the destination period, the OpenTitan check_only convention
#     the ASAP7 file follows. DATA pins only (`all_registers -data_pins`): with a plain
#     `-to [all_registers -clock X]` the exception also lands on the async RESET_B/SET_B
#     pins and fabricates a max-delay check against a reset distribution tree (bead je8).
#
#     DECLARED BEFORE sections 11-13 on purpose: between two overlapping -from/-to exceptions
#     the last declared wins, and the per-crossing budgets below are tighter.
###############################################################################
set_max_delay [expr {$clock_period * 0.9}] \
    -from [all_registers -clock cpu_clk] -to [all_registers -clock core_clk -data_pins]
set_max_delay [expr {$clock_period * 0.9}] \
    -from [all_registers -clock core_clk] -to [all_registers -clock cpu_clk -data_pins]

###############################################################################
# 10a. cdc_reset_sync async set/reset pins: cross-domain recovery/removal is waived.
#      Same class and same justification as ASAP7 sec 10a (bead je8): every always_ff in
#      rtl/soc/cdc/cdc_reset_sync.sv is async-assert / SYNCHRONOUS-deassert (a constant 1 is
#      shifted through the chain on the capture clock), and the launching nets are reset
#      class (rst_both_n = s_rst_n_i & m_rst_n_i, pmu_cpu_rst_n, ...), not data. Recovery
#      and removal on the SAME clock stay timed -- only the cross-clock check is waived.
#      Structural (all_registers -async_pins), so it needs no instance name.
###############################################################################
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
    cdc_apply_sync_budget fifo_rd2wr "u_cpu_axi_cdc*${_fifo}*u_rd_ptr_to_wr" \
        [expr {$clock_period * 0.5}] $_rd_clk $_wr_clk \
        "sec.11 u_cpu_axi_cdc.${_fifo}.u_rd_ptr_to_wr gray-pointer crossing ($_rd_clk -> $_wr_clk)"
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
#     u_cpu_clk_dis_sync, u_cpu_iso_en_sync, u_ext_irq_sync, u_timer_irq_sync.
#     1.0x destination period. (pmu_cpu_rst_n's cdc_reset_sync needs no entry: it has no
#     data input, only an async clear, covered by sec 10a.)
###############################################################################
foreach {_s _g} {u_cpu_clk_dis_sync pmu_clk_dis u_cpu_iso_en_sync pmu_iso_en \
                 u_ext_irq_sync ext_irq u_timer_irq_sync timer_irq} {
    cdc_apply_sync_budget $_g $_s $clock_period core_clk cpu_clk \
        "sec.13 ${_s} single-bit crossing (core_clk -> cpu_clk)"
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
