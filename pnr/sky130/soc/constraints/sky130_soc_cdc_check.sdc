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

# Third root: the JTAG TAP clock (bead y5mn / j41m.10). Same period as sky130_soc.sdc's placeholder. It exists
# here ONLY so the MBIST control-word and status crossings (section 14) have a launch/capture clock; as for
# the other two clocks it is deliberately NOT related to them. Guarded so an older netlist without the port
# still sources. The test clock reaches the functional trees through the dft_clk_mux (flow STA), so a flop in
# core_clk/cpu_clk may carry `tck` as a second clock: section 14 therefore NEVER identifies a TCK-domain cell
# by `all_registers -clock tck`, only structurally (fan-in of a synchroniser, minus the destination domain).
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

###############################################################################
# 2b. Functional-view case analysis (bead j41m.17, user decision 2026-10-27)
#
# This check bounds FUNCTIONAL-mode clock-domain crossings. The scan enable tree (`dft_scan_en` -> the SE pin of
# every scan flop) is not one: in functional mode it is constant 0, and in scan mode both domains run on the one
# test clock. But the crypto wipe-done gate (PR #332) makes `dft_scan_en` = (TAP/pin request) & crypto_wipe_done,
# a core_clk-launched path that reaches the 981 SE pins of the cpu_core_clk scan chain through a 28-buffer tree,
# which an unconstrained check reads as a core_clk -> cpu_clk crossing (measured -1.581 ns at max_ss against the
# 0.9 x 25 ns domain-wide fallback, RUN_2026-10-27_05-40-27).
#
# The functional view pins the three controls that make the request 0:
#   scan_mode_i = 0 and scan_en_i = 0 (the pin leg, as sky130_soc.sdc does), and the TAP serial-select flop
#   `u_dft_ctrl.tap_serial` = 0 (TAP not in serial scan; it selects tap_scan_en over the pin leg).
# scan_mode_i alone does NOT make dft_scan_en constant (scan_en_o is not gated by scan_mode, and the TAP can raise
# scan_mode itself), measured: with only scan_mode_i = 0 the crossing still fails. With the three, the request is a
# constant 0, so the AND (and its resizer clone) is constant and the SE tree drops out. Every other group is
# unchanged (22 groups, same worst slacks): see DFT_ARCHITECTURE.md 14.14.1.
#
# The SCAN VIEW is not affected: CVT_SDC_SCAN_VIEW=1 in the environment skips this section (same switch as
# sky130_soc.sdc), and sky130_soc.sdc itself is not touched by this section.
###############################################################################
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
# pointer label ("u_aw_fifo.wr2rd") -> {from_clk to_clk {capture D pins of its bits}}: the unit of the
# per-pointer bit-skew report (check_cdc_timing_sky130.tcl, bead j41m.5 option C). Filled by sec. 11.
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
        # -to the capture flop's D PIN, not the cell: the section-10 fallback is -to D pins, and
        # OpenSTA ranks a pin-qualified exception above a cell-qualified one, so a -to <cell>
        # budget silently LOSES to the fallback whatever the declaration order (measured on the
        # baseline netlist: the intended 25.0 ns applied as the fallback's 22.5 ns). With both
        # sides pin-qualified the later declaration wins, as the ASAP7 file documents.
        set_max_delay $val -from $_launch -to $_dpins
        dict lappend ::cdc_groups $group {*}$_dpins
        lappend ::cdc_last_pins {*}$_dpins
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

# 13a. Isolation-ack RETURN crossing (bead 3ogd): u_cpu_iso_ack_sync samples pmu_cpu_iso_en_sync
#      (the CPU-domain clamp control, cpu_clk) into core_clk for the PMU's cpu_iso_ack_i. The only
#      PMU crossing in the cpu_clk -> core_clk direction; same 1.0x destination-period budget and
#      the same structural binding as every row above. Not yet run on a routed Sky130 netlist.
cdc_apply_sync_budget pmu_iso_ack u_cpu_iso_ack_sync $clock_period cpu_clk core_clk \
    "sec.13a u_cpu_iso_ack_sync single-bit crossing (cpu_clk -> core_clk)"

###############################################################################
# 14. MBIST TCK <-> functional crossings (bead y5mn, j41m.10 Q12; DFT_ARCHITECTURE.md 16.5, 16.11)
#
# PR #306 added, per destination domain (core_clk: u_mbist.u_xing_core; cpu_core_clk: u_mbist.g_cpu.u_xing_cpu):
#   (a) a depth-2 cdc_gray_fifo, write side tck, read side the UNGATED destination clock, rd_ready tied 1:
#         u_fifo.u_wr_ptr_to_rd  tck -> dst  gray write pointer (2-FF)      GRAY    budget
#         u_fifo.u_rd_ptr_to_wr  dst -> tck  gray read pointer  (2-FF)      GRAY    budget
#         u_fifo.mem_q -> mbist_ctl_hold ctl_q  tck -> dst  combinational read of the 2x29-bit storage into the
#                                                               holding register                    PAYLOAD budget
#   (b) mbist_status_sync: 69 per-bit single-bit cdc_sync dst -> tck (u_stsync_core / g_cpu.u_stsync_cpu).
# For the CPU domain the status launch is the CPU hard macro itself (mbist_status_o[], launched by clk_i), so
# the launch cell is the macro instance; its 35 pins {23,22} U [68:36] (rec_addr[9:8] since AW = 8, rec_port[1], and err_mask, tied 0 since the collar-local compare,
# DFT_ARCHITECTURE.md 16.12) have no launching arc, are recognised as constants and are accounted for, not skipped.
#
# BUDGETS (new numbers, chosen here; OpenSTA has no -datapath_only, see the header):
#   * gray pointers, both directions: 0.5 x min(source, destination) period = 12.5 ns. The existing FIFO rows use
#     0.5 x the DESTINATION period; with a 100 ns tck that rule would give the dst->tck pointer 50 ns, four times
#     looser than the 25 ns functional clock that launches it, so the faster period governs here.
#   * mem_q -> ctl_q payload: 0.9 x the destination period = 22.5 ns (the section-10 payload convention). The data
#     is only consumed after the pointer has crossed (>= 2 destination edges), so this is conservative.
#   * status bits dst -> tck: 1.0 x min(source, destination) period = 25 ns (single-bit level crossings; the
#     documented >= 3 TCK settle rule and the done/busy extra flop do the coherency, section 16.5).
# All three are CLOCKS-IDEAL datapath bounds like every other row.
#
# NEGATIVE CONTROL: CDC_CHECK_MBIST_BUDGET_NS=<ns> forces every section-14 budget to that value (e.g. 0.001); the
# check must then FAIL on every section-14 group. A check that cannot fail is not a check.
#
# NOT COVERED HERE, ON PURPOSE (listed so the gap is visible, not hidden):
#   * mbist_force (TAP falling-edge flop, tck) -> u_cpu_cg enable: a single UNSYNCHRONISED quasi-static control,
#     the section 15.5 "crossing 2" contract; async-grouped in the implementation SDC. No synchroniser exists to
#     bind a budget to; a CDC lint rule, not an SDC row, is the right owner.
#   * mbist_run_i / mbist_cfg_i[25:0] into the CPU macro: launched by the cpu_core_clk holding register, captured by
#     the macro on cpu_gated_clk (the same clock root), and the macro Liberty carries setup/hold arcs for every one
#     of them. They are ordinary synchronous cpu_clk paths, timed by the flow STA, not CDC.
#   * macro mbist_status_o[1:0] -> u_cpu_cg enable (cpu_cg_en feedback): same clock root, ordinary clock-gating check.
###############################################################################
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
