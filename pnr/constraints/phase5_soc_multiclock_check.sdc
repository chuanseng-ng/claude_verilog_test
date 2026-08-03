###############################################################################
# phase5_soc_multiclock_check.sdc — POST-ROUTE CDC BUDGET VERIFICATION ONLY
#
# bead claude_verilog_test-k07 (2026-08-02), GH #96 (epic #90 -> #91..#96).
#
# These SDC's are not used for synthesis, since they collide with the
# set_clock_groups -asynchronous constraint in phase5_soc_multiclock.sdc.
# Instead, they are used to time the design after P&R in order to make sure
# that the CDC crossings are all within spec. (Wording deliberately mirrors
# OpenTitan's hw/top_earlgrey/syn/chip_earlgrey_asic_check_only.sdc, the
# precedent this split follows.)
#
# WHY THIS FILE EXISTS (tool-verified, not asserted — see
# phase5_soc_multiclock.sdc section 3's header note for the full writeup):
#   1. OpenSTA's set_max_delay/set_min_delay do not implement a
#      -datapath_only flag at all (only -rise -fall -ignore_clock_latency
#      -reset_path -comment — see OpenSTA sdc/Sdc.tcl). Any SDC using
#      -datapath_only aborts read_sdc immediately with STA-0563 "is not a
#      known keyword or flag" — reproduced identically in both the
#      standalone `sta` binary and OpenROAD's embedded STA engine
#      (OpenSTA 2.6.0, OpenROAD edf00dff9). -datapath_only is therefore
#      NEVER used in this file.
#   2. Independently of (1): even a syntactically legal
#      `set_max_delay <n> -through <pin>` is NOT honoured by OpenSTA when
#      the two clocks it bridges are declared via
#      `set_clock_groups -asynchronous` (or an equivalent
#      `set_false_path -from <clkA> -to <clkB>`) — report_checks reports
#      "No paths found" / "Path Group: unconstrained" for that path rather
#      than a timed max_delay check, REGARDLESS of the max_delay
#      exception's -through specificity. Standard SDC precedence
#      (set_false_path > set_max_delay > set_multicycle_path) applies
#      unconditionally in this tool, not just on exact-match ties.
# CONSEQUENCE: this file intentionally declares BOTH clocks but NEVER
# declares them asynchronous and NEVER false-paths one from/to the other.
# That is what makes the set_max_delay budgets below real, timed checks.
#
# USAGE — read this file's purpose narrowly:
#   This file is for TARGETED post-route queries against the specific CDC
#   endpoints named in sections 11-13 below (report_checks -to/-through a
#   named pin, as pnr/scripts/check_cdc_timing.tcl does). It is NOT a
#   substitute full-chip signoff SDC: because sys_clk and cpu_clk have no
#   group/false-path relationship here, a full unfiltered `report_checks`
#   or `report_wns`/`report_tns` sweep against this file WILL show
#   fabricated setup/hold violations on every OTHER pair of FFs that
#   happen to sit in different domains but are not part of a deliberate
#   synchroniser (there is no exception suppressing those, by design — see
#   above). That is expected, not a defect: interrogate specific CDC paths
#   only. Full-chip signoff continues to use phase5_soc_multiclock.sdc.
#
# Base: sections 1 (clocks) and 4 (async reset false-paths) are copied
# verbatim from phase5_soc_multiclock.sdc so this file is self-contained
# for read_sdc; keep them in sync by hand if either file's clock periods
# change (Run-13 CTS lesson applies identically here — do NOT add
# create_generated_clock for core_clk/cpu_core_clk).
###############################################################################

###############################################################################
# 1. Primary clocks (verbatim copy of phase5_soc_multiclock.sdc section 1)
###############################################################################
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

###############################################################################
# CDC exception coverage guard (carried over from phase5_soc_multiclock.sdc's
# former sections 11-13/15 — GH #94 hardening, CodeRabbit review PR #132).
# Every exception below is built from get_pins/get_nets -hierarchical
# -filter against a specific instance path. If that path is ever renamed —
# RTL refactor, or synthesis hierarchy flattening — the pattern silently
# matches an EMPTY collection; cdc_require_match reports every miss via a
# grep-able "CDC-EXCEPTION-MISS:" puts and records it in
# ::cdc_exception_misses. Section 15 (end of file) promotes any recorded
# miss to a hard Tcl `error`.
###############################################################################
set ::cdc_exception_misses {}

proc cdc_require_match {collection description} {
    if {[llength $collection] > 0} {
        return 1
    }
    puts "ERROR: CDC-EXCEPTION-MISS: ${description} -- pattern matched an EMPTY collection. This CDC timing exception was NOT applied; the boundary is UNCONSTRAINED."
    lappend ::cdc_exception_misses $description
    return 0
}

###############################################################################
# 11. CPU<->fabric CDC boundary — async_axi_fifo (instance u_cpu_axi_cdc)
#
# GH #94 / bead oa7 item 1; retightened per bead k07 item 1 (OpenTitan +
# PULP precedent — this project's original 1.0x-destination-period budget
# was looser than either reference):
#   - gray-pointer crossings (u_wr_ptr_to_rd/q_o, u_rd_ptr_to_wr/q_o; 2 per
#     FIFO x 5 FIFOs = 10 total): 0.5x destination period, matching
#     OpenTitan check_only.sdc's GRAY_MAX_DELAY = 0.5x period for FIFO gray
#     pointers specifically.
#   - mem_q combinational read (1 per FIFO x 5 FIFOs = 5 total): 0.9x
#     destination period, matching OpenTitan check_only.sdc's blanket
#     0.9x-destination-period budget for CDC data-path crossings.
# -datapath_only is NOT used (unsupported by OpenSTA — see file header);
# plain set_max_delay -through is what OpenSTA actually times, and it is
# only reachable here because this file never declares sys_clk/cpu_clk
# asynchronous (see file header).
#
#   AW/W/AR fifos: wr_clk_i = s_clk_i = cpu_clk (780 ps)
#                  rd_clk_i = m_clk_i = sys_clk (1750 ps)
#   B/R    fifos: wr_clk_i = m_clk_i = sys_clk (1750 ps)
#                  rd_clk_i = s_clk_i = cpu_clk (780 ps)
###############################################################################
set _cdc_fifo_dirs {
    u_aw_fifo 780  1750
    u_w_fifo  780  1750
    u_ar_fifo 780  1750
    u_b_fifo  1750 780
    u_r_fifo  1750 780
}

foreach {_fifo_inst _fifo_wr_period _fifo_rd_period} $_cdc_fifo_dirs {
    # (1) mem_q combinational read — 0.9x the READ (destination) domain period
    set _memq [get_nets -hierarchical -filter "name =~ *u_cpu_axi_cdc/${_fifo_inst}/mem_q*" -quiet]
    if {[cdc_require_match $_memq "sec.11 u_cpu_axi_cdc/${_fifo_inst}/mem_q combinational read"]} {
        set_max_delay [expr {$_fifo_rd_period * 0.9}] -through $_memq
    }

    # (2) u_wr_ptr_to_rd: wr_gray_q -> rd domain — 0.5x rd (destination) period
    set _wr2rd [get_pins -hierarchical -filter "full_name =~ *u_cpu_axi_cdc/${_fifo_inst}/u_wr_ptr_to_rd/q_o*" -quiet]
    if {[cdc_require_match $_wr2rd "sec.11 u_cpu_axi_cdc/${_fifo_inst}/u_wr_ptr_to_rd/q_o gray-pointer crossing"]} {
        set_max_delay [expr {$_fifo_rd_period * 0.5}] -through $_wr2rd
    }

    # (3) u_rd_ptr_to_wr: rd_gray_q -> wr domain — 0.5x wr (destination) period
    set _rd2wr [get_pins -hierarchical -filter "full_name =~ *u_cpu_axi_cdc/${_fifo_inst}/u_rd_ptr_to_wr/q_o*" -quiet]
    if {[cdc_require_match $_rd2wr "sec.11 u_cpu_axi_cdc/${_fifo_inst}/u_rd_ptr_to_wr/q_o gray-pointer crossing"]} {
        set_max_delay [expr {$_fifo_wr_period * 0.5}] -through $_rd2wr
    }
}

###############################################################################
# 12. APB_PLL2 CDC bridge — apb_cdc_bridge (instance u_apb_pll2_cdc)
#
# GH #94 / bead oa7 item 2. Budgets left at 1.0x destination period —
# bead k07 item 1 only asked for retightening on the gray-pointer FIFOs
# (section 11) and mem_q; these single-bit/payload toggle-handshake
# crossings are lower-rate control paths, not the gray-pointer datapath
# OpenTitan singles out for the tighter 0.5x GRAY_MAX_DELAY budget.
###############################################################################
set _req_sync [get_pins -hierarchical -filter "full_name =~ *u_apb_pll2_cdc/u_req_sync/q_o*" -quiet]
if {[cdc_require_match $_req_sync "sec.12 u_apb_pll2_cdc/u_req_sync/q_o toggle-bit crossing (s->m)"]} {
    set_max_delay 780 -through $_req_sync
}

set _ack_sync [get_pins -hierarchical -filter "full_name =~ *u_apb_pll2_cdc/u_ack_sync/q_o*" -quiet]
if {[cdc_require_match $_ack_sync "sec.12 u_apb_pll2_cdc/u_ack_sync/q_o toggle-bit crossing (m->s)"]} {
    set_max_delay 1750 -through $_ack_sync
}

# cmd_* payload (s=sys_clk -> m=cpu_clk domain capture): bound to cpu_clk
set _cmd_nets {}
foreach _sig {cmd_pwrite_q cmd_paddr_q cmd_pwdata_q cmd_pstrb_q} {
    set _n [get_nets -hierarchical -filter "name =~ *u_apb_pll2_cdc/${_sig}*" -quiet]
    if {[cdc_require_match $_n "sec.12 u_apb_pll2_cdc/${_sig} payload read (s->m capture)"]} {
        lappend _cmd_nets {*}$_n
    }
}
if {[llength $_cmd_nets] > 0} {
    set_max_delay 780 -through $_cmd_nets
}

# resp_* payload (m=cpu_clk -> s=sys_clk domain capture): bound to sys_clk
set _resp_nets {}
foreach _sig {resp_prdata_dq resp_pslverr_dq} {
    set _n [get_nets -hierarchical -filter "name =~ *u_apb_pll2_cdc/${_sig}*" -quiet]
    if {[cdc_require_match $_n "sec.12 u_apb_pll2_cdc/${_sig} payload read (m->s capture)"]} {
        lappend _resp_nets {*}$_n
    }
}
if {[llength $_resp_nets] > 0} {
    set_max_delay 1750 -through $_resp_nets
}

###############################################################################
# 12a. APB debug-port CDC bridge — apb_cdc_bridge (instance u_apb_dbg_cdc)
#
# GH #95 fix (bead claude_verilog_test-eg2). Same IP, same six crossing
# paths, same treatment as section 12 (u_apb_pll2_cdc) above, mirrored here
# rather than duplicated in prose. Budgets left at 1.0x destination period
# for the same reason as section 12 (not a gray-pointer/mem_q datapath).
###############################################################################
set _dbg_req_sync [get_pins -hierarchical -filter "full_name =~ *u_apb_dbg_cdc/u_req_sync/q_o*" -quiet]
if {[cdc_require_match $_dbg_req_sync "sec.12a u_apb_dbg_cdc/u_req_sync/q_o toggle-bit crossing (s->m)"]} {
    set_max_delay 780 -through $_dbg_req_sync
}

set _dbg_ack_sync [get_pins -hierarchical -filter "full_name =~ *u_apb_dbg_cdc/u_ack_sync/q_o*" -quiet]
if {[cdc_require_match $_dbg_ack_sync "sec.12a u_apb_dbg_cdc/u_ack_sync/q_o toggle-bit crossing (m->s)"]} {
    set_max_delay 1750 -through $_dbg_ack_sync
}

# cmd_* payload (s=sys_clk -> m=cpu_clk domain capture): bound to cpu_clk
set _dbg_cmd_nets {}
foreach _sig {cmd_pwrite_q cmd_paddr_q cmd_pwdata_q cmd_pstrb_q} {
    set _n [get_nets -hierarchical -filter "name =~ *u_apb_dbg_cdc/${_sig}*" -quiet]
    if {[cdc_require_match $_n "sec.12a u_apb_dbg_cdc/${_sig} payload read (s->m capture)"]} {
        lappend _dbg_cmd_nets {*}$_n
    }
}
if {[llength $_dbg_cmd_nets] > 0} {
    set_max_delay 780 -through $_dbg_cmd_nets
}

# resp_* payload (m=cpu_clk -> s=sys_clk domain capture): bound to sys_clk
set _dbg_resp_nets {}
foreach _sig {resp_prdata_dq resp_pslverr_dq} {
    set _n [get_nets -hierarchical -filter "name =~ *u_apb_dbg_cdc/${_sig}*" -quiet]
    if {[cdc_require_match $_n "sec.12a u_apb_dbg_cdc/${_sig} payload read (m->s capture)"]} {
        lappend _dbg_resp_nets {*}$_n
    }
}
if {[llength $_dbg_resp_nets] > 0} {
    set_max_delay 1750 -through $_dbg_resp_nets
}

###############################################################################
# 13. PMU/IRQ single-bit crossings into the cpu_core_clk domain
#
# u_cpu_pmu_rst_sync's rst_n_i pin (only) is excluded and given a
# false_path instead: it is consumed only as an ASYNCHRONOUS CLEAR
# (negedge-sensitive, see cdc_reset_sync.sv), by construction with no
# setup/hold relationship to any clock — a max_delay exception (a
# setup-style data-arrival check) would be the wrong exception type. The
# filter is scoped to the rst_n_i pin specifically, NOT the whole instance
# (CodeRabbit PR #133): an instance-wide wildcard also matches rst_n_o,
# whose fanout (pmu_cpu_rst_n_cpu_sync, feeding u_cpu's synchronous reset
# and the cpu_gated_clk_en AND-gate in soc_top.sv) is a synchronised
# release inside the cpu_core_clk domain and must stay timed. This is a
# legitimate, narrowly-scoped false_path (on one specific pin of one
# reset-sync instance, not a clock-to-clock blanket exception) and does
# not reintroduce the masking problem this file exists to avoid.
#
# The other four are genuine single-bit DATA crossings through
# cdc_2ff_sync; budgets left at 1.0x destination period (cpu_core_clk =
# cpu_clk, 780 ps) — same rationale as sections 12/12a.
###############################################################################
set _rst_sync_pins [get_pins -hierarchical -filter "full_name =~ *u_cpu_pmu_rst_sync/rst_n_i" -quiet]
if {[cdc_require_match $_rst_sync_pins "sec.13 u_cpu_pmu_rst_sync/rst_n_i async-clear reset sync (false_path)"]} {
    set_false_path -through $_rst_sync_pins
}

foreach _sync_inst {u_cpu_clk_dis_sync u_cpu_iso_en_sync u_ext_irq_sync u_timer_irq_sync} {
    set _p [get_pins -hierarchical -filter "full_name =~ *${_sync_inst}/q_o*" -quiet]
    if {[cdc_require_match $_p "sec.13 ${_sync_inst}/q_o single-bit CDC crossing"]} {
        set_max_delay 780 -through $_p
    }
}

###############################################################################
# 15. CDC exception coverage gate — hard-fail on any section 11-13 miss.
#
# See the cdc_require_match proc / ::cdc_exception_misses list defined just
# before section 11. If ANY exception's get_pins/get_nets pattern matched an
# empty collection above, a CDC-EXCEPTION-MISS line was already puts'd at
# the point of failure. This final check promotes that from "logged" to
# "fatal": abort read_sdc with a nonzero-equivalent Tcl `error` rather than
# let the file finish reading as if nothing were wrong — an unconstrained
# CDC boundary that STA reports as "clean" is a strictly worse outcome than
# an aborted read_sdc that names the missing instance/pin/net.
###############################################################################
if {[llength $::cdc_exception_misses] > 0} {
    puts "ERROR: CDC-EXCEPTION-MISS: [llength $::cdc_exception_misses] of sections 11-13's CDC timing exceptions failed to match any object:"
    foreach _miss $::cdc_exception_misses {
        puts "ERROR: CDC-EXCEPTION-MISS:   - ${_miss}"
    }
    error "phase5_soc_multiclock_check.sdc: [llength $::cdc_exception_misses] CDC timing exception(s) in sections 11-13 matched an EMPTY collection -- see CDC-EXCEPTION-MISS lines above. Fix the referenced instance/pin/net path (RTL rename or hierarchy flattening) before trusting this SDC's STA results."
}
