###############################################################################
# phase5_soc_multiclock_check.sdc — POST-ROUTE CDC BUDGET VERIFICATION ONLY
#
# bead claude_verilog_test-k07 (2026-08-02), GH #96 (epic #90 -> #91..#96).
# Re-bound to the flattened netlist under bead claude_verilog_test-7l5
# (2026-08-06, GH #96 / bead claude_verilog_test-8nz) — see section "OBJECT
# RESOLUTION" below for the full, tool-verified writeup of why every
# exception in this file had to change shape, not just separator.
#
# Sections 12/12a updated under bead claude_verilog_test-rfz (2026-08-12):
# apb_cdc_bridge.sv converted from a 2-phase NRZ toggle handshake to a
# 4-phase RZ handshake; req_toggle_q/ack_toggle_q renamed to req_q/ack_q.
# Only the `-filter {name =~ ...}` patterns and description strings changed
# (same electrical role, same object-mapping methodology) — this is
# precisely the "stale name pattern silently matches zero objects" hazard
# bead 7l5 warns about in OBJECT RESOLUTION item 3, so it is called out here
# too, not just at the two touched sections.
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
#
# Base: sections 1 (clocks) and 4 (async reset false-paths) are copied
# verbatim from phase5_soc_multiclock.sdc so this file is self-contained
# for read_sdc; keep them in sync by hand if either file's clock periods
# change (Run-13 CTS lesson applies identically here — do NOT add
# create_generated_clock for core_clk/cpu_core_clk).
#
# =============================================================================
# OBJECT RESOLUTION ON A FLATTENED NETLIST (bead 7l5, 2026-08-06)
# =============================================================================
# pnr/asap7/soc/config_multiclock.json sets SYNTH_HIERARCHY_MODE=flatten.
# This has two consequences that made every exception below match an EMPTY
# collection until this rewrite (tool-verified against
# final/nl/soc_top.nl.v, RUN_2026-08-06_09-44-51):
#
#   (1) SEPARATOR: hierarchy is preserved only as literal '.' characters
#       baked into escaped Verilog identifiers (e.g.
#       `\u_cpu_axi_cdc.u_aw_fifo.u_wr_ptr_to_rd.d_i[0] `), not as real
#       instance nesting. The OLD file used '/' — 0 matches, always.
#
#   (2) CELLS ARE ANONYMOUS: technology mapping renames every cell to a
#       number (`_419265_`); RTL instance/port names (u_wr_ptr_to_rd, q_o,
#       rst_n_i, ...) do not survive on cells or pins AT ALL. get_cells and
#       get_pins hierarchical name patterns therefore always return empty on
#       this netlist, regardless of separator. Only get_nets can match, and
#       only nets that kept a clean RTL-derived name.
#
#   (3) A THIRD, UNDOCUMENTED FAILURE MODE, discovered by this rewrite:
#       OpenSTA's `get_nets -hierarchical -filter "name =~ <pattern>"` does
#       NOT treat a literal '.' inside <pattern> as an ordinary glob
#       character once wildcards surround it. Tool-verified: with
#       liberty+netlist loaded from this run,
#         `-filter {name =~ *u_aw_fifo*}`                 -> 22 nets (works)
#         `-filter {name =~ *u_aw_fifo.u_wr_ptr_to_rd*}`   -> 0 nets (breaks)
#         `-filter {name =~ *.d_i*}`                       -> 231528 nets
#                                                              (matches
#                                                              almost the
#                                                              whole design)
#       i.e. a literal '.' inside the pattern is NOT a safe glob character
#       here — neither escaping it (`\.`), bracket-escaping it (`[.]`), nor
#       matching it with `?` recovers a correct match; the filter engine
#       silently mis-parses the expression instead of erroring. THE FIX:
#       every filter pattern in this file uses ONLY '*'-joined, dot-free
#       tokens (e.g. `*u_cpu_axi_cdc*u_aw_fifo*u_wr_ptr_to_rd*d_i*`) — pure
#       substring-presence matching, verified to return exactly the
#       expected object set for every pattern below (see bead 7l5 session
#       notes for the full battery of `sta` probes this was derived from).
#       DO NOT put a literal '.' back into any `-filter "name =~ ..."`
#       pattern in this file without re-verifying it against a real routed
#       netlist first.
#
#   (4) SEMANTICS: the pre-existing exceptions ALSO targeted the wrong
#       point even where they did resolve. `u_wr_ptr_to_rd/q_o` /
#       `u_ack_sync/q_o` / etc. are the OUTPUT of the synchroniser's LAST
#       flop — a path lying entirely inside the DESTINATION domain (see
#       rtl/soc/cdc/cdc_2ff_sync.sv: `assign q_o = sync_q[STAGES-1];`).
#       The real clock-domain crossing is the SOURCE register -> the
#       synchroniser's FIRST flop D input (`sync_q[0] <= d_i;`). Every
#       exception below has been re-pointed at that launch->first-capture
#       segment: `d_i` where it survives as its own net (some d_i ports
#       collapse into their driving net's name during optimisation instead
#       — verified case by case below), or the source register net
#       directly (`rd_gray_q`, `req_q`, `ext_irq`, ...) where it
#       does not.
#
#   (5) mem_q AND the apb_cdc_bridge cmd_*/resp_* payload capture registers
#       are UNMATCHABLE BY NAME on this netlist — 0 occurrences anywhere in
#       final/nl/soc_top.nl.v, confirmed by grep as well as by OpenSTA. This
#       is not a pattern bug: `assign rd_data_o = mem_q[rd_bin_q[...]];`-
#       style muxed array reads and the FSM-gated `cmd_paddr_cap_q <=
#       cmd_paddr_q;` capture do not survive optimisation as identifiable
#       nets the way a straight passthrough (`req_q`, `ext_irq`, ...)
#       does. Section 10 below (declared BEFORE sections 11-13 -- see its
#       PRECEDENCE note for why) replaces all of these with a domain-wide
#       max_delay fallback instead of a per-signal exception.
#
#   (6) PRECEDENCE (measured, not assumed, two rounds): with both a narrow
#       `set_max_delay <n> -through <net>` AND a broad
#       `set_max_delay <m> -from [all_registers -clock A] -to
#       [all_registers -clock B]` applicable to the SAME path, OpenSTA
#       ALWAYS applies the -from/-to exception's value, REGARDLESS of
#       declaration order (tested both orders) and regardless of how much
#       narrower the -through net list is. A -through exception is
#       silently dominated by any -from/-to exception that also reaches the
#       same path -- this is why every per-crossing exception below is
#       expressed as `-from <cell(s)> -to <cell(s)>` rather than `-through
#       <net>`.
#       Between TWO overlapping -from/-to exceptions, precedence was
#       measured to be DECLARATION ORDER, not specificity: whichever is
#       declared LAST wins, even when it is the broad `all_registers`-based
#       one. This is why section 10 (the domain-wide fallback) is declared
#       BEFORE sections 11-13 in this file, not after — see section 10's
#       own header for the full write-up of this (two-round) measurement.
#
#   (7) -from/-to CELL DERIVATION MUST TRACE THROUGH LOGIC, NOT JUST THE
#       MATCHED NET'S IMMEDIATE PINS (bead 7l5, second pass): the naive
#       `get_cells -of_objects [get_pins -of_objects $net -filter
#       {direction == output}]` looked correct (non-empty, cdc_require_match
#       passed) but was WRONG for req_q (named req_toggle_q before bead
#       claude_verilog_test-rfz's NRZ->RZ rename): the matched net's immediate
#       driver was an INVxp67 polarity inverter, not the real source
#       register (the ASAP7 flop cells used here only expose an inverted Q
#       (QN); synthesis inserts an inverter even for a "direct RTL
#       passthrough" signal). A combinational cell is not a valid -from
#       startpoint, so that exception silently never applied -- every
#       crossing's REPORTED max_delay was still the section-10 fallback,
#       even though cdc_require_match reported success. Caught only by
#       reviewing the .rpt files' actual applied max_delay value against
#       the value each section intended (Definition of Done item 3), not by
#       the empty-collection guard. Fixed with `get_fanin`/`get_fanout`
#       (`-startpoints_only`/`-endpoints_only -flat -only_cells`), which
#       trace THROUGH intervening combinational logic to the real register
#       cells — see cdc_net_from_to below. Lesson: a non-empty
#       cdc_require_match result proves the NAME pattern matched something;
#       it does not prove the resulting -from/-to exception is electrically
#       correct or was actually applied. Always cross-check the .rpt files'
#       max_delay column against the intended per-section value after
#       touching this file.
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
# former sections 11-13/15 — GH #94 hardening, CodeRabbit review PR #132;
# extended by bead 7l5 to also gate the -from/-to cell derivation, not just
# the initial net match).
#
# Every exception below is built from get_nets -hierarchical -filter against
# a dot-free, '*'-joined substring pattern (see OBJECT RESOLUTION item 3
# above for why literal '.' cannot appear in these patterns). If a pattern
# is ever renamed — RTL refactor, resynthesis, a different
# SYNTH_HIERARCHY_MODE — it silently matches an EMPTY collection;
# cdc_require_match reports every miss via a grep-able
# "CDC-EXCEPTION-MISS:" puts and records it in ::cdc_exception_misses.
# cdc_apply_max_delay additionally gates on the -from/-to cell derivation
# succeeding (a matched net whose driver/load cells could not be resolved is
# ALSO a miss, not a silent no-op). Section 15 (end of file) promotes any
# recorded miss to a hard Tcl `error`.
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

# cdc_net_from_to: given a (possibly multi-bit) net collection that is
# somewhere on a synchroniser's launch->first-capture path, return
# {startpoint_cells endpoint_cells} suitable for `set_max_delay -from -to`.
#
# NOT simply the matched net's immediate driver/load cell (bead 7l5,
# second-pass fix, 2026-08-06): a first attempt used
# `get_cells -of_objects [get_pins -of_objects $netc -filter {direction ==
# output}]` for -from directly. That is WRONG whenever technology mapping
# inserted a buffer/inverter between the true source register and the
# matched net -- tool-verified this happens even for a "direct RTL
# passthrough" signal (e.g. req_q's matched net is actually driven
# by an INVxp67 polarity inverter, itself fed by the real source flop's QN
# output; the ASAP7 flop cells used here (DFFASRHQNx1) only expose an
# inverted Q). Using the inverter cell as `-from` produced a -from/-to
# exception that OpenSTA silently never applies (the inverter is not a
# valid path startpoint), so the exception appeared to succeed
# (cdc_require_match saw a non-empty collection) but had NO EFFECT --
# every crossing's reported max_delay silently fell back to section 10's
# domain-wide budget instead. Caught by budget-verdict review (Definition
# of Done item 3: verdicts must be reported and checked, not just "did the
# exception match"), not by cdc_require_match, which is why this comment
# is here: cdc_require_match/cdc_apply_max_delay's emptiness guard cannot
# by itself prove an exception PRODUCED the intended constraint. Fixed
# using get_fanin/get_fanout (-flat -only_cells, tracing THROUGH any
# intervening combinational logic to the real register), not
# -of_objects (one hop only):
# cdc_regs_on_clock / cdc_filter_by_clock: THIRD-PASS fix (bead 7l5,
# 2026-08-06). get_fanin/get_fanout (above) fixed the "wrong immediate pin"
# bug but exposed a further one: -flat fanin/fanout tracing can walk INTO a
# buffer/gate that is SHARED between the intended crossing and a completely
# unrelated net (confirmed case: u_cpu_axi_cdc.u_r_fifo's wr_gray_q[3]
# driver pin fans out to its real cpu_clk-domain sync destination AND to
# two more cells still sitting in the SOURCE (sys_clk) domain -- almost
# certainly synthesis-level buffer/logic sharing, not anything meaningful
# in the RTL, since cdc_gray_fifo.sv gives wr_gray_q exactly one consumer).
# Passing a -to collection that mixes the correct cpu_clk endpoint with
# spurious sys_clk-domain cells made OpenSTA silently refuse the WHOLE
# `-from/-to` exception (it fell back to the section-10 domain-wide
# fallback for that bit, or -- for later runs -- to no exception at all,
# i.e. the raw beat-period alignment check the file header warns is
# fabricated noise). Fix: filter the fanin/fanout result down to cells that
# are ACTUALLY clocked by the direction's own expected launch/capture
# clock, using `all_registers -clock <name>` (name-set membership, cached
# per clock so repeated calls don't re-walk the whole register list).
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

# cdc_net_from_to: given ONE net that sits somewhere on a synchroniser's
# launch->first-capture path, plus the launch/capture clock names the
# design intends for that crossing, return {startpoint_cells
# endpoint_cells} suitable for `set_max_delay -from -to`. Called per-bit
# (never on a whole multi-bit collection at once -- see cdc_apply_max_delay)
# so a bus never mixes one bit's cells into another's exception.
#
# NOT simply the matched net's immediate driver/load cell (bead 7l5,
# second-pass fix, 2026-08-06): a first attempt used
# `get_cells -of_objects [get_pins -of_objects $netc -filter {direction ==
# output}]` for -from directly. That is WRONG whenever technology mapping
# inserted a buffer/inverter between the true source register and the
# matched net -- tool-verified this happens even for a "direct RTL
# passthrough" signal (e.g. req_q's matched net is actually driven
# by an INVxp67 polarity inverter, itself fed by the real source flop's QN
# output; the ASAP7 flop cells used here (DFFASRHQNx1) only expose an
# inverted Q). Using the inverter cell as `-from` produced a -from/-to
# exception that OpenSTA silently never applies (the inverter is not a
# valid path startpoint), so the exception appeared to succeed
# (cdc_require_match saw a non-empty collection) but had NO EFFECT --
# every crossing's reported max_delay silently fell back to section 10's
# domain-wide budget instead. Fixed using get_fanin/get_fanout (-flat
# -only_cells, tracing THROUGH intervening combinational logic to the real
# register) instead of a one-hop -of_objects lookup. That fix in turn
# exposed the buffer-SHARING issue cdc_regs_on_clock/cdc_filter_by_clock
# above fix (third pass). Lesson standing after both passes: a non-empty
# cdc_require_match result proves the NAME pattern matched something; it
# does not prove the resulting -from/-to exception is electrically correct
# or was actually applied -- always cross-check the .rpt files' max_delay
# column against the intended per-section value after touching this file.
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

###############################################################################
# 10. Domain-wide fallback budget for name-unmatchable payload crossings
#     (bead 7l5, 2026-08-06)
#
# DECLARED BEFORE sections 11-13 ON PURPOSE — see PRECEDENCE note below.
#
# Covers the crossings sections 11/12/12a cannot re-express by name
# post-flatten: the 5x mem_q combinational reads (async_axi_fifo) and the
# cmd_*/resp_* FSM-gated payload captures (both apb_cdc_bridge instances).
# None of these survive as an identifiable net -- 0 occurrences of mem_q,
# cmd_pwrite_q, cmd_paddr_q, cmd_pwdata_q, cmd_pstrb_q, resp_prdata_dq,
# resp_pslverr_dq anywhere in final/nl/soc_top.nl.v (confirmed by both grep
# and OpenSTA get_nets).
#
# Budget: 0.9x destination-domain period, matching OpenTitan
# check_only.sdc's blanket 0.9x-destination-period budget for CDC data-path
# crossings (same convention section 11's mem_q used pre-flatten). This is
# TIGHTER than the cmd_*/resp_* class's original bespoke budget (1.0x
# destination period, see the section 12/12a payload notes below) -- a
# deliberate, documented tightening, not a silent regression: there is no
# way to re-express those two classes with different budgets when neither
# can be distinguished by name post-flatten (both fall into the same
# `-from [all_registers ...] -to [all_registers ...]` point-to-point
# match). A VIOLATED finding here on a former-1.0x-budget crossing is
# expected to be MORE likely than before, not evidence of a broken check.
#
# PRECEDENCE (measured, bead 7l5, real routed netlist, distinctive sentinel
# values, req_q crossing used as the probe):
#   - a `-through <net>` exception is ALWAYS dominated by ANY applicable
#     `-from/-to` exception on the same path, REGARDLESS of declaration
#     order or how much narrower the -through net list is. This is why
#     every per-crossing exception in sections 11-13 below is expressed as
#     `-from <cell(s)> -to <cell(s)>` (cdc_apply_max_delay / cdc_net_from_to,
#     derived from the matched net via get_fanin/get_fanout tracing -- see
#     OBJECT RESOLUTION item 7) rather than `-through <net>`.
#   - between TWO overlapping `-from/-to` exceptions (this section's broad
#     `all_registers`-based one, and a later specific single-cell-pair
#     one), OpenSTA applies whichever was declared LAST, NOT the more
#     specific one -- tested both orders on the identical path/values; it
#     is pure declaration order, not specificity. (An earlier draft of this
#     file assumed "most specific -from/-to wins" from a single-order test;
#     re-testing with the order reversed disproved that and is why this
#     section physically sits BEFORE sections 11-13 in the file, not after
#     them as its section number might suggest.)
# CONSEQUENCE: this section MUST stay textually before sections 11-13 for
# their tighter budgets to remain authoritative. If a future edit moves
# this block after them, every named crossing's budget silently reverts to
# this 0.9x fallback -- re-verify with the check target's .rpt files
# (max_delay value shown for each crossing) after ANY reordering.
###############################################################################
set_max_delay [expr {1750 * 0.9}] \
    -from [all_registers -clock cpu_clk] -to [all_registers -clock sys_clk]
set_max_delay [expr {780 * 0.9}] \
    -from [all_registers -clock sys_clk] -to [all_registers -clock cpu_clk]

###############################################################################
# 11. CPU<->fabric CDC boundary — async_axi_fifo (instance u_cpu_axi_cdc)
#
# GH #94 / bead oa7 item 1; retightened per bead k07 item 1 (OpenTitan +
# PULP precedent — this project's original 1.0x-destination-period budget
# was looser than either reference):
#   - gray-pointer crossings (2 per FIFO x 5 FIFOs = 10 total): 0.5x
#     destination period, matching OpenTitan check_only.sdc's
#     GRAY_MAX_DELAY = 0.5x period for FIFO gray pointers specifically.
#   - mem_q combinational read: moved to section 10 (bead 7l5 — unmatchable
#     by name on the flattened netlist, see OBJECT RESOLUTION item 5).
#
# Object mapping (bead 7l5, verified against rtl/soc/cdc/cdc_gray_fifo.sv
# and the routed netlist -- both directions are a direct RTL passthrough,
# `.d_i(wr_gray_q)` / `.d_i(rd_gray_q)`, no intervening logic, yet only ONE
# side keeps a distinct `d_i` net after optimisation in each fifo instance):
#   - u_wr_ptr_to_rd.d_i SURVIVES as its own net (wr_gray_q's driving net
#     collapses into the port name instead) -> matched directly.
#   - u_rd_ptr_to_wr.d_i does NOT survive; rd_gray_q (the source register
#     itself, same electrical node as the vanished d_i) does -> matched via
#     the source register's own net instead.
#
#   AW/W/AR fifos: wr_clk_i = s_clk_i = cpu_clk (780 ps)
#                  rd_clk_i = m_clk_i = sys_clk (1750 ps)
#   B/R    fifos: wr_clk_i = m_clk_i = sys_clk (1750 ps)
#                  rd_clk_i = s_clk_i = cpu_clk (780 ps)
###############################################################################
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
    cdc_apply_max_delay $_wr2rd [expr {$_rd_period * 0.5}] $_wr_clk $_rd_clk \
        "sec.11 u_cpu_axi_cdc.${_fifo_inst}.u_wr_ptr_to_rd.d_i gray-pointer crossing"

    # (2) rd_gray_q (source register for u_rd_ptr_to_wr's vanished d_i):
    #     rd_gray_q -> wr domain — 0.5x wr (destination) period
    set _rd2wr [get_nets -hierarchical -filter "name =~ *u_cpu_axi_cdc*${_fifo_inst}*rd_gray_q*" -quiet]
    cdc_apply_max_delay $_rd2wr [expr {$_wr_period * 0.5}] $_rd_clk $_wr_clk \
        "sec.11 u_cpu_axi_cdc.${_fifo_inst}.rd_gray_q gray-pointer crossing"
}

###############################################################################
# 12. APB_PLL2 CDC bridge — apb_cdc_bridge (instance u_apb_pll2_cdc)
#
# GH #94 / bead oa7 item 2. Budgets left at 1.0x destination period —
# bead k07 item 1 only asked for retightening on the gray-pointer FIFOs
# (section 11) and mem_q; these single-bit req/ack level-handshake
# crossings are lower-rate control paths, not the gray-pointer datapath
# OpenTitan singles out for the tighter 0.5x GRAY_MAX_DELAY budget.
#
# RENAMED (bead claude_verilog_test-rfz, 2026-08-12): apb_cdc_bridge.sv
# converted from a 2-phase NRZ toggle handshake to a 4-phase RZ handshake.
# req_toggle_q/ack_toggle_q became req_q/ack_q -- same electrical role (each
# is still the one register whose value crosses via cdc_2ff_sync), so the
# object-mapping methodology below (bead 7l5) is unaffected; only the name
# patterns changed. This is exactly the class of stale-pattern-matches-zero
# hazard bead 7l5 itself warns about (see OBJECT RESOLUTION item 3) -- do
# not let a future RTL rename slip past this file again without updating
# these `-filter {name =~ ...}` strings in the same commit.
#
# Object mapping (bead 7l5): req_q / ack_q are each a direct RTL passthrough
# into their cdc_2ff_sync's d_i (`.d_i(req_q)` / `.d_i(ack_q)`, see
# rtl/soc/apb_cdc_bridge.sv), and in THIS module both source registers keep
# their own clean net names post-optimisation (unlike section 11's
# asymmetric case) -- matched directly, no d_i net needed. The cmd_*/resp_*
# payload capture registers are unmatchable by name (0 occurrences anywhere
# in the routed netlist, same class as mem_q) -- moved to section 10.
###############################################################################
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
#
# GH #95 fix (bead claude_verilog_test-eg2). Same IP, same treatment as
# section 12 (u_apb_pll2_cdc) above, mirrored here rather than duplicated in
# prose.
###############################################################################
set _dbg_req_sync [get_nets -hierarchical -filter {name =~ *u_apb_dbg_cdc*req_q*} -quiet]
cdc_apply_max_delay $_dbg_req_sync 780 sys_clk cpu_clk \
    "sec.12a u_apb_dbg_cdc.req_q level crossing (s->m)"

set _dbg_ack_sync [get_nets -hierarchical -filter {name =~ *u_apb_dbg_cdc*ack_q*} -quiet]
cdc_apply_max_delay $_dbg_ack_sync 1750 cpu_clk sys_clk \
    "sec.12a u_apb_dbg_cdc.ack_q level crossing (m->s)"

# cmd_*/resp_* payload (u_apb_dbg_cdc): unmatchable by name -- see
# section 10's domain-wide fallback, which covers this crossing instead.

###############################################################################
# 13. PMU/IRQ single-bit crossings into the cpu_core_clk domain
#
# u_cpu_pmu_rst_sync's async-clear input (only) is excluded and given a
# false_path instead: it is consumed only as an ASYNCHRONOUS CLEAR
# (cdc_reset_sync.sv has NO d_i port at all -- its flop chain is driven by
# a tied-high constant and cleared only by this signal), by construction
# with no setup/hold relationship to any clock — a max_delay exception (a
# setup-style data-arrival check) would be the wrong exception type. Object
# mapping (bead 7l5): the RTL port was `rst_n_i`, which does not survive on
# the anonymous flop cells; the net that actually drives every flop's
# async-clear/set pin in this scope DOES survive under its OWN top-level
# name, `pmu_cpu_rst_n` (confirmed via the routed netlist: this net drives
# .SETN on both flops of u_cpu_pmu_rst_sync's chain and nothing else). This
# remains a legitimate, narrowly-scoped false_path (one specific net with a
# single fan-out purpose, not a clock-to-clock blanket exception) and does
# not reintroduce the masking problem this file exists to avoid.
#
# The other four are genuine single-bit DATA crossings through
# cdc_2ff_sync; budgets left at 1.0x destination period (cpu_core_clk =
# cpu_clk, 780 ps) — same rationale as sections 12/12a.
#
# Object mapping for the four data crossings (bead 7l5): u_cpu_clk_dis_sync
# is fed `.d_i(~pmu_cpu_clk_en)` (an INVERTER output, i.e. real logic
# between the source register and the synchroniser) -- its d_i net survives
# under its own scoped name, matched directly. The other three
# (u_cpu_iso_en_sync, u_ext_irq_sync, u_timer_irq_sync) are each fed a
# direct RTL passthrough (`.d_i(pmu_cpu_iso_en)`, `.d_i(ext_irq)`,
# `.d_i(timer_irq)`, no intervening logic) whose d_i net does NOT survive;
# in every case the SOURCE signal itself survives as a plain top-level net
# (pmu_cpu_iso_en / ext_irq / timer_irq -- confirmed single electrical
# fan-out apiece: declaration + drive + this one D pin) and is used
# instead. These three are matched with a PLAIN, non-hierarchical, exact
# `get_nets <name>` (no wildcards): a wildcarded substring match on these
# short top-level names was tool-verified to also catch unrelated longer
# names sharing the substring (e.g. `*ext_irq*` matches 3 nets, not 1),
# so exact matching is required here, unlike the hierarchical dot-free
# patterns used everywhere else in this file.
###############################################################################
set _rst_sync_pins [get_nets pmu_cpu_rst_n -quiet]
if {[cdc_require_match $_rst_sync_pins "sec.13 pmu_cpu_rst_n async-clear reset sync (false_path)"]} {
    set_false_path -through $_rst_sync_pins
}

set _clk_dis_di [get_nets -hierarchical -filter {name =~ *u_cpu_clk_dis_sync*d_i*} -quiet]
cdc_apply_max_delay $_clk_dis_di 780 sys_clk cpu_clk \
    "sec.13 u_cpu_clk_dis_sync.d_i single-bit CDC crossing"

set _iso_en_src [get_nets pmu_cpu_iso_en -quiet]
cdc_apply_max_delay $_iso_en_src 780 sys_clk cpu_clk \
    "sec.13 pmu_cpu_iso_en (source of u_cpu_iso_en_sync) single-bit CDC crossing"

set _ext_irq_src [get_nets ext_irq -quiet]
cdc_apply_max_delay $_ext_irq_src 780 sys_clk cpu_clk \
    "sec.13 ext_irq (source of u_ext_irq_sync) single-bit CDC crossing"

set _timer_irq_src [get_nets timer_irq -quiet]
cdc_apply_max_delay $_timer_irq_src 780 sys_clk cpu_clk \
    "sec.13 timer_irq (source of u_timer_irq_sync) single-bit CDC crossing"

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
