#================================================================
# Post-route CDC budget verification for the 2-domain ASAP7 SoC
# Tool: OpenSTA (invoked as 'sta' standalone binary)
# bead claude_verilog_test-k07 / GH #96
#
# Companion to pnr/constraints/phase5_soc_multiclock_check.sdc — see that
# file's header (and phase5_soc_multiclock.sdc section 3) for WHY this is a
# separate SDC/script from the normal 07_sta.tcl signoff flow: OpenSTA does
# not honour set_max_delay exceptions on paths between clocks declared
# set_clock_groups -asynchronous (tool-verified, bead k07), so the CDC
# budgets can only be timed by a file that never makes that declaration —
# which means it cannot be used for a full-chip report_wns/report_tns
# sweep (every unrelated cross-domain FF pair would show as a fabricated
# violation). This script therefore only runs TARGETED report_checks
# queries against the specific CDC endpoints phase5_soc_multiclock_check.sdc
# excepts, not a general signoff sweep.
#
# Invoked via: sta pnr/scripts/check_cdc_timing.tcl
# (Makefile target: make check-cdc-timing-asap7-soc, see pnr/Makefile)
#
# Requires a routed netlist that actually contains the CDC modules
# (async_axi_fifo / apb_cdc_bridge / second PLL stub) — i.e. a P&R run of
# pnr/asap7/soc/config.json with PNR_SDC_FILE pointed at
# phase5_soc_multiclock.sdc instead of the single-clock phase5_soc.sdc.
# That re-closure run is GH #96's scope, not this bead's — as of
# 2026-08-02 no such run exists yet (the signed-off run 14 predates GH
# #91-95's CDC RTL entirely). Until then this script will correctly report
# "Netlist not found" rather than silently doing nothing.
#
# EXIT CODE CONTRACT (bead claude_verilog_test-dwp, 2026-08-03):
# OpenSTA's batch-mode 'sta' binary returns exit code 0 even when a Tcl
# script calls the Tcl `error` command (tool-confirmed, both standalone
# 'sta' and OpenROAD's embedded STA engine) -- so this script must never
# rely on an uncaught Tcl error to signal failure to its caller. Every
# check below funnels into one of two explicit `exit` calls at the very
# end (or an immediate `exit 2` for setup problems), mirroring the
# convention tools/cdc/cdc_gate.py already uses (see that file -- NOT
# modified here, this script only mirrors the convention):
#   exit 0 -- PASS: every CDC exception matched a real object and every
#             targeted timing budget was met.
#   exit 1 -- CDC FINDING(S): a design/constraint problem -- one or more
#             CDC exceptions matched an EMPTY collection (unmatched /
#             renamed instance) and/or one or more targeted budgets
#             reported a VIOLATED slack. Names of every finding are
#             printed in the final CDC-CHECK-RESULT block, not just the
#             exit code.
#   exit 2 -- SETUP/USAGE ERROR: the check itself could not run at all
#             (missing env var, missing liberty/netlist/SDC file, or an
#             SDC read failure unrelated to the CDC-EXCEPTION-MISS
#             mechanism below). This is a tool/environment problem, not a
#             finding about the design -- CI must be able to tell the two
#             apart.
# All checks are accumulated (see ::cdc_check_findings /
# ::cdc_check_finding_msgs below) -- a single run reports every unmatched
# exception and every violated budget, not just the first one hit.
#================================================================

# cdc_fatal_setup: used ONLY for problems that mean the check cannot be
# meaningfully run at all (missing tool inputs). Exits immediately with
# code 2 -- see EXIT CODE CONTRACT above. Not used for CDC findings.
proc cdc_fatal_setup {msg} {
    puts "ERROR: CDC-CHECK-SETUP-ERROR: $msg"
    exit 2
}

# cdc_check_findings / cdc_check_finding_msgs: accumulate EVERY CDC
# finding (unmatched exception collections and violated timing budgets)
# across the whole run so the final report names all of them, not just
# the first. Populated by cdc_record_finding below, and by the read_sdc
# catch block folding in phase5_soc_multiclock_check.sdc's own
# ::cdc_exception_misses list (that file's cdc_require_match proc is the
# canonical "does this collection match anything" check; this script
# reuses it rather than re-implementing the empty-collection idiom --
# CodeRabbit PR #133 finding 2).
set ::cdc_check_findings 0
set ::cdc_check_finding_msgs {}

proc cdc_record_finding {msg} {
    incr ::cdc_check_findings
    lappend ::cdc_check_finding_msgs $msg
}

if {![info exists ::env(CDC_CHECK_RUN_DIR)]} {
    cdc_fatal_setup "CDC_CHECK_RUN_DIR is not set. Point it at a routed ASAP7 SoC run directory built with PNR_SDC_FILE=phase5_soc_multiclock.sdc (containing final/nl/soc_top.nl.v) -- e.g. 'make check-cdc-timing-asap7-soc RUN_DIR=/path/to/RUN_...' (see pnr/Makefile), or export CDC_CHECK_RUN_DIR yourself before invoking 'sta pnr/scripts/check_cdc_timing.tcl' directly."
}
set RUN_DIR    $::env(CDC_CHECK_RUN_DIR)
set TOP_MODULE "soc_top"

# phase5_soc_multiclock_check.sdc lives under pnr/constraints/ (shared
# staging location, alongside phase5_soc_multiclock.sdc — see that file's
# STATUS header), NOT under pnr/asap7/soc/constraints/ where the per-node
# signed-off SDCs live. Pass an absolute path via CDC_CHECK_SDC (the
# Makefile target does); fall back to a path relative to this script's own
# location so the script also works if invoked directly from pnr/.
if {[info exists ::env(CDC_CHECK_SDC)]} {
    set CHECK_SDC $::env(CDC_CHECK_SDC)
} else {
    set CHECK_SDC [file join [file dirname [info script]] .. constraints phase5_soc_multiclock_check.sdc]
}

set NETLIST "$RUN_DIR/final/nl/${TOP_MODULE}.nl.v"
set REPORTS_DIR "reports"
file mkdir $REPORTS_DIR

#----------------------------------------------------------------
# ASAP7 stdcell + macro liberty (paths match pnr/asap7/soc/config.json's
# LIB/EXTRA_LIBS; override via env if the PDK is installed elsewhere).
#----------------------------------------------------------------
set ASAP7_LIB_DIR [expr {[info exists ::env(ASAP7_LIB_DIR)] \
    ? $::env(ASAP7_LIB_DIR) \
    : "/home/neuromorphic/pdk/asap7/libs.ref/asap7sc7p5t_SIMPLE/lib"}]

set _stdcell_libs {
    asap7sc7p5t_AO_RVT_TT_nldm_211120.lib
    asap7sc7p5t_INVBUF_RVT_TT_nldm_220122.lib
    asap7sc7p5t_OA_RVT_TT_nldm_211120.lib
    asap7sc7p5t_SEQ_RVT_TT_nldm_220123.lib
    asap7sc7p5t_SIMPLE_RVT_TT_nldm_211120.lib
}

puts "================================================================"
puts "Reading ASAP7 stdcell liberty ($ASAP7_LIB_DIR)"
puts "================================================================"
foreach _lib $_stdcell_libs {
    set _path "$ASAP7_LIB_DIR/$_lib"
    if {![file exists $_path]} {
        cdc_fatal_setup "Liberty file not found: $_path (set ASAP7_LIB_DIR if the PDK lives elsewhere)"
    }
    read_liberty $_path
}

# Macro libs (CPU/GPU hard macros, SRAM) — same set as EXTRA_LIBS in
# pnr/asap7/soc/config.json.
foreach _macro_lib {
    macro/rv32i_cpu_top__nom_tt_025C_0p7V.lib
    macro/gpu_top__nom_tt_025C_0p7V.lib
} {
    set _path "$_macro_lib"
    if {[file exists $_path]} {
        read_liberty $_path
    } else {
        puts "  (skip, not found: $_path)"
    }
}
if {[file exists "../sram_1rw_256x32_asap7_TT_0p7V_25C.lib"]} {
    read_liberty "../sram_1rw_256x32_asap7_TT_0p7V_25C.lib"
}

#----------------------------------------------------------------
# Gate-level netlist
#----------------------------------------------------------------
puts "================================================================"
puts "Reading gate-level netlist: $NETLIST"
puts "================================================================"
if {![file exists $NETLIST]} {
    cdc_fatal_setup "Netlist not found: $NETLIST -- no CDC re-closure P&R run exists yet (GH #96 scope). Run pnr/asap7/soc/config.json with PNR_SDC_FILE=phase5_soc_multiclock.sdc first, then set CDC_CHECK_RUN_DIR to that run's directory."
}
read_verilog $NETLIST
link_design $TOP_MODULE

#----------------------------------------------------------------
# CDC check-only SDC (NOT the implementation SDC -- see file header)
#----------------------------------------------------------------
puts "================================================================"
puts "Reading CDC check-only SDC: $CHECK_SDC"
puts "================================================================"
if {![file exists $CHECK_SDC]} {
    cdc_fatal_setup "CDC check-only SDC not found: $CHECK_SDC"
}

if {[catch {read_sdc $CHECK_SDC} _sdc_err]} {
    # phase5_soc_multiclock_check.sdc's own section 15 gate raises a Tcl
    # `error` when one or more of ITS CDC timing exceptions (sections
    # 11-13) failed to match any pin/net -- an EXPECTED finding, not a
    # tool failure (see that file's cdc_require_match proc / the
    # ::cdc_exception_misses global it populates). Distinguish that case
    # from a genuine SDC read failure (syntax error, bad Tcl elsewhere):
    # only ::cdc_exception_misses being non-empty proves this was the
    # expected mechanism. Continue past it (rather than exiting here) so
    # the report_checks queries below still run and any additional budget
    # violations are folded into the SAME final report -- this is the
    # "accumulate across all checks, don't bail on first" requirement.
    if {[info exists ::cdc_exception_misses] && [llength $::cdc_exception_misses] > 0} {
        foreach _miss $::cdc_exception_misses {
            cdc_record_finding "unmatched CDC exception (phase5_soc_multiclock_check.sdc): $_miss"
        }
        puts "WARNING: check_cdc_timing.tcl: $CHECK_SDC reported [llength $::cdc_exception_misses] unmatched CDC exception(s) above (CDC-EXCEPTION-MISS). Continuing to run the remaining targeted timing queries; all findings are summarized in the final CDC-CHECK-RESULT block."
    } else {
        cdc_fatal_setup "read_sdc failed on $CHECK_SDC for a reason other than an unmatched CDC exception: $_sdc_err"
    }
}

#----------------------------------------------------------------
# Targeted CDC path reports. -unconstrained is NOT used here: the whole
# point is to prove these specific paths ARE constrained (report_checks
# succeeding with a real slack number is the pass signal; "No paths found"
# or "(Path is unconstrained)" is the bead-k07 failure mode this file
# exists to prevent from recurring silently).
#----------------------------------------------------------------
# cdc_report_through: run a targeted report_checks -through query. Reuses
# the cdc_require_match proc that $CHECK_SDC defines (in scope here:
# read_sdc evaluates that file's proc/set statements in this same Tcl
# interpreter, and it ran above) rather than re-inventing the
# empty-collection idiom -- CodeRabbit PR #133 finding 2.
#
# On an empty collection: record the finding via cdc_record_finding and
# `return` (skip this one report) instead of `error`-ing out of the whole
# script -- a single unmatched pattern must not prevent the remaining
# report_checks queries below from running (bead claude_verilog_test-dwp:
# "do not bail on the first failure").
#
# On a non-empty collection: also inspect the generated report for a
# VIOLATED slack and record that as a finding too -- the pre-fix script
# wrote the report but never actually looked at whether the budget was
# met, so a real timing violation would have passed silently.
proc cdc_report_through {collection description report_path} {
    if {![cdc_require_match $collection $description]} {
        cdc_record_finding "empty collection: ${description} (see CDC-EXCEPTION-MISS line above; no report written to $report_path)"
        return
    }
    report_checks -through $collection \
        -path_delay max -format full_clock_expanded -digits 3 \
        > $report_path
    set _fh [open $report_path r]
    set _rpt_content [read $_fh]
    close $_fh
    if {[string match "*VIOLATED*" $_rpt_content]} {
        cdc_record_finding "budget VIOLATED: ${description} (see $report_path)"
    } elseif {[string match "*No paths found*" $_rpt_content] || [string match "*unconstrained*" $_rpt_content]} {
        cdc_record_finding "path unconstrained/not found despite non-empty collection: ${description} (see $report_path)"
    }
}

puts "================================================================"
puts "CDC boundary timing -- async_axi_fifo (u_cpu_axi_cdc), all 5 channels"
puts "================================================================"
# mem_q is queried as get_nets here to match the OBJECT CLASS
# phase5_soc_multiclock_check.sdc sec.11 item 1 writes its set_max_delay
# exception against (get_nets, not get_pins) -- mem_q is a FIFO storage
# array and resolves differently as a net collection vs. a flop-pin
# collection post-synthesis, so a get_pins query here was not guaranteed to
# report against the same paths the SDC actually budgets (CodeRabbit PR
# #133 finding 2).
cdc_report_through \
    [get_nets -hierarchical -filter "name =~ *u_cpu_axi_cdc/*/mem_q*" -quiet] \
    "check_cdc_timing.tcl mem_q report query (u_cpu_axi_cdc/*/mem_q)" \
    $REPORTS_DIR/cdc_fifo_memq.rpt
cdc_report_through \
    [get_pins -hierarchical -filter "full_name =~ *u_cpu_axi_cdc/*/u_wr_ptr_to_rd/q_o*" -quiet] \
    "check_cdc_timing.tcl u_wr_ptr_to_rd/q_o report query" \
    $REPORTS_DIR/cdc_fifo_wr2rd.rpt
cdc_report_through \
    [get_pins -hierarchical -filter "full_name =~ *u_cpu_axi_cdc/*/u_rd_ptr_to_wr/q_o*" -quiet] \
    "check_cdc_timing.tcl u_rd_ptr_to_wr/q_o report query" \
    $REPORTS_DIR/cdc_fifo_rd2wr.rpt

puts "================================================================"
puts "CDC boundary timing -- apb_cdc_bridge (u_apb_pll2_cdc, u_apb_dbg_cdc)"
puts "================================================================"
cdc_report_through \
    [get_pins -hierarchical -filter "full_name =~ *u_apb_pll2_cdc/u_req_sync/q_o* || full_name =~ *u_apb_pll2_cdc/u_ack_sync/q_o*" -quiet] \
    "check_cdc_timing.tcl u_apb_pll2_cdc toggle report query" \
    $REPORTS_DIR/cdc_apb_pll2_toggle.rpt
cdc_report_through \
    [get_pins -hierarchical -filter "full_name =~ *u_apb_dbg_cdc/u_req_sync/q_o* || full_name =~ *u_apb_dbg_cdc/u_ack_sync/q_o*" -quiet] \
    "check_cdc_timing.tcl u_apb_dbg_cdc toggle report query" \
    $REPORTS_DIR/cdc_apb_dbg_toggle.rpt

puts "================================================================"
puts "CDC boundary timing -- PMU/IRQ single-bit crossings"
puts "================================================================"
cdc_report_through \
    [get_pins -hierarchical -filter "full_name =~ *u_cpu_clk_dis_sync/q_o* || full_name =~ *u_cpu_iso_en_sync/q_o* || full_name =~ *u_ext_irq_sync/q_o* || full_name =~ *u_timer_irq_sync/q_o*" -quiet] \
    "check_cdc_timing.tcl PMU/IRQ single-bit crossing report query" \
    $REPORTS_DIR/cdc_pmu_irq.rpt

puts ""
puts "================================================================"
puts "CDC timing reports written to $REPORTS_DIR/cdc_*.rpt"
puts "PASS SIGNAL: each report shows real timed paths with computed slack"
puts "  (not 'No paths found' / 'Path Group: unconstrained' -- see bead"
puts "  k07 / phase5_soc_multiclock.sdc section 3 for why that distinction"
puts "  matters here)."
puts "================================================================"

#----------------------------------------------------------------
# Final gate. See EXIT CODE CONTRACT in the file header: OpenSTA's batch
# mode does not propagate a Tcl `error` into the process exit code, so
# PASS/FAIL must be signalled with an explicit `exit` here regardless of
# whether every check above matched or not.
#----------------------------------------------------------------
puts ""
puts "================================================================"
if {$::cdc_check_findings > 0} {
    puts "CDC-CHECK-RESULT: FAIL -- $::cdc_check_findings CDC finding(s) detected:"
    foreach _msg $::cdc_check_finding_msgs {
        puts "  - $_msg"
    }
    puts "================================================================"
    exit 1
}
puts "CDC-CHECK-RESULT: PASS -- every CDC exception matched a real object and every targeted timing budget was met."
puts "================================================================"
exit 0
