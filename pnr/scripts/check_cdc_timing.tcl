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

# CDC_CHECK_ODB (bead je8, 2026-09-15): opt-in ODB-based loading path for
# checkpoints that only have GRT (or later) parasitics, e.g. a run
# stopped/seeded mid-flow before a `final/nl/*.nl.v` signoff netlist
# exists. Requires OpenROAD (read_db/global_route/estimate_parasitics are
# OpenROAD-only commands -- this script's default path below works under
# plain standalone `sta` precisely because it avoids all of them). Run
# this script with `openroad` instead of `sta` when CDC_CHECK_ODB is set;
# it is silently ignored -- and the netlist/link_design path below runs
# unchanged -- otherwise, so every existing `sta
# pnr/scripts/check_cdc_timing.tcl` invocation (including the tracked
# check-cdc-timing-asap7-soc Makefile target) is byte-identical to
# before.
set CDC_CHECK_ODB [expr {[info exists ::env(CDC_CHECK_ODB)] ? $::env(CDC_CHECK_ODB) : ""}]

# CDC_CHECK_FORCE_GRT (bead je8, 2026-09-15): ODB-mode only, opt-in. By
# default (unset) the GRT-parasitics block below relies on the ODB's own
# already-computed global-routing guides (dbGuide objects a prior
# GlobalRouting step's `write_db`/`write_views` persisted into the
# database) and calls `estimate_parasitics -global_routing` directly --
# tool-verified (2026-09-15) to work with no warning, using far less
# memory than a fresh re-route. `read_guides <file>` was tried first as
# the memory-cheap option but is NOT usable here: OpenROAD prints
# "[WARNING GRT-0008] The read_guides command does not allow parasitics
# estimation from the guides file" -- it loads guide geometry for display/
# DRT purposes only, not into whatever internal state
# estimate_parasitics -global_routing reads. A genuinely fresh
# `global_route` (congestion-driven resource-grid solve over the whole
# design) is memory-heavy regardless of tool -- it OOM'd a 3.5G-capped
# scope on this SoC (520x520um, 138k+ blockages) before completing.
# Set CDC_CHECK_FORCE_GRT=1 only for a checkpoint odb with no persisted
# guides (e.g. loaded before any GlobalRouting step ran) and with enough
# memory headroom for a real global_route.
set CDC_CHECK_FORCE_GRT [expr {[info exists ::env(CDC_CHECK_FORCE_GRT)] && $::env(CDC_CHECK_FORCE_GRT) == "1"}]

# CDC_CHECK_PROPAGATED_CLOCK (bead je8, 2026-09-15): ODB-mode only,
# opt-in, OFF by default. The budgets in phase5_soc_multiclock_check.sdc
# are intended as datapath-only bounds (GH #94 intent,
# phase5_soc_multiclock.sdc header: launch-flop CK->Q plus data wires/
# logic to the capture D pin, excluding clock-network latency) --
# `-datapath_only` is the SDC keyword that would normally express that,
# but this file's own header (see above, "WHY THIS FILE EXISTS" item 1)
# already tool-verified OpenSTA 2.6.0 / OpenROAD edf00dff do not
# implement -datapath_only at all (STA-0563 on read_sdc), so it is never
# passed by cdc_apply_max_delay / cdc_apply_max_delay_capture_fallback --
# confirmed again by inspection here, both only ever call plain
# `set_max_delay $val -from ... -to ...`. Given that, the only way this
# tool can approximate "datapath-only" is by keeping clocks IDEAL (each
# clock's SDC-declared `set_clock_latency -source 50` instead of a real,
# walked clock-tree insertion delay) while STILL using GRT-estimated wire
# parasitics on the DATA path -- clock propagation mode and parasitics
# annotation are independent in this tool, so this isolates data-path
# delay without the ~600-900 ps of real sys_clk clock-tree insertion
# delay a fully propagated launch clock would fold into the same
# max_delay budget (bead je8, 2026-09-15: exactly what turned 3 real-
# parasitics groups VIOLATED on run 9 step 02 under
# CDC_CHECK_PROPAGATED_CLOCK=1). This default matches how every prior
# ACCEPTED CDC check in this project's history was run (run 23's
# original post-route check and this bead's own post-CTS early check
# both used ideal/unpropagated clocks, via the plain-netlist STA-only
# path that has no clock-tree structure to propagate at all). Set
# CDC_CHECK_PROPAGATED_CLOCK=1 to get the fdf166b behaviour back (real
# propagated clock latency folded into the same budget -- useful for
# separately characterizing how much of a path's margin is clock-latency
# vs. datapath, as this bead's own notes do).
set CDC_CHECK_PROPAGATED_CLOCK [expr {[info exists ::env(CDC_CHECK_PROPAGATED_CLOCK)] && $::env(CDC_CHECK_PROPAGATED_CLOCK) == "1"}]

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
# Gate-level netlist -- ODB (GRT+ parasitics) or plain-verilog (STA-only,
# no parasitics beyond the check SDC's own ideal clock-latency model).
#----------------------------------------------------------------
if {$CDC_CHECK_ODB ne ""} {
    puts "================================================================"
    puts "Reading OpenROAD database (GRT-parasitics mode): $CDC_CHECK_ODB"
    puts "================================================================"
    if {![file exists $CDC_CHECK_ODB]} {
        cdc_fatal_setup "ODB not found: $CDC_CHECK_ODB"
    }
    if {[catch {read_db $CDC_CHECK_ODB} _odb_err]} {
        cdc_fatal_setup "read_db failed on $CDC_CHECK_ODB -- is this script running under 'openroad', not 'sta'? ($_odb_err)"
    }
    # Minimal equivalent of LibreLane's io.tcl set_global_vars (not sourced
    # here to avoid its other side effects, e.g. read_pnr_libs/
    # read_current_sdc pulling in PNR_SDC_FILE) -- $::tech is needed below
    # by the GRT layer-adjustment loop.
    set ::db [::ord::get_db]
    set ::tech [$::db getTech]
} else {
    puts "================================================================"
    puts "Reading gate-level netlist: $NETLIST"
    puts "================================================================"
    if {![file exists $NETLIST]} {
        cdc_fatal_setup "Netlist not found: $NETLIST -- no CDC re-closure P&R run exists yet (GH #96 scope). Run pnr/asap7/soc/config.json with PNR_SDC_FILE=phase5_soc_multiclock.sdc first, then set CDC_CHECK_RUN_DIR to that run's directory."
    }
    read_verilog $NETLIST
    link_design $TOP_MODULE
}

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
# GRT-parasitics mode (bead je8, 2026-09-15): once the design+SDC are
# loaded from the ODB, get the SAME parasitic basis the real flow's
# rsz_timing_postgrt.tcl uses -- set_propagated_clock (real CTS-built
# clock-tree insertion delay from the loaded odb, not the check SDC's
# ideal `set_clock_latency -source 50` fallback), the ASAP7-calibrated
# per-layer RC values and routing-layer range
# (librelane/scripts/openroad/common/set_rc.tcl /
# set_routing_layers.tcl), the same GRT layer adjustments
# (common/set_layer_adjustments.tcl), then estimate_parasitics
# -global_routing -- by default off the ODB's own persisted routing
# guides (memory-cheap, tool-verified 2026-09-15 to need no fresh route),
# or a genuinely fresh global_route if CDC_CHECK_FORCE_GRT=1 (see that
# variable's header comment above for why re-routing is the heavier,
# opt-in path; rsz_timing_postgrt.tcl always takes it, citing
# https://github.com/The-OpenROAD-Project/OpenROAD/issues/5590, but this
# script defaults to the cheaper odb-persisted path since it was
# confirmed to work without that warning). No repair_timing call -- this
# is a read-only timing snapshot of the checkpoint as routed, never
# modifies the design.
#----------------------------------------------------------------
if {$CDC_CHECK_ODB ne ""} {
    puts "================================================================"
    puts "GRT-parasitics mode: estimate_parasitics -global_routing (force_grt=$CDC_CHECK_FORCE_GRT, propagated_clock=$CDC_CHECK_PROPAGATED_CLOCK)"
    puts "================================================================"
    if {$CDC_CHECK_PROPAGATED_CLOCK} {
        puts "  clocks: PROPAGATED (real walked clock-tree insertion delay -- includes clock latency in every max_delay budget below; see CDC_CHECK_PROPAGATED_CLOCK header comment)"
        set_propagated_clock [all_clocks]
    } else {
        puts "  clocks: IDEAL (SDC-declared set_clock_latency -source 50 -- approximates the intended datapath-only budget; see CDC_CHECK_PROPAGATED_CLOCK header comment)"
        unset_propagated_clock [all_clocks]
    }

    # ASAP7-calibrated per-layer RC (mirrors common/set_rc.tcl's hard-coded
    # ORFS-derived values -- the ASAP7 tech LEF itself has no
    # RESISTANCE/CAPACITANCE attributes).
    set_layer_rc -layer M1 -resistance 7.04175e-02 -capacitance 1e-10
    set_layer_rc -layer M2 -resistance 4.62311e-02 -capacitance 1.84542e-01
    set_layer_rc -layer M3 -resistance 3.63251e-02 -capacitance 1.53955e-01
    set_layer_rc -layer M4 -resistance 2.03083e-02 -capacitance 1.89434e-01
    set_layer_rc -layer M5 -resistance 1.93005e-02 -capacitance 1.71593e-01
    set_layer_rc -layer M6 -resistance 1.18619e-02 -capacitance 1.76146e-01
    set_layer_rc -layer M7 -resistance 1.25311e-02 -capacitance 1.47030e-01
    set_layer_rc -via V1 -resistance 1.72e-02
    set_layer_rc -via V2 -resistance 1.72e-02
    set_layer_rc -via V3 -resistance 1.72e-02
    set_layer_rc -via V4 -resistance 1.18e-02
    set_layer_rc -via V5 -resistance 1.18e-02
    set_layer_rc -via V6 -resistance 8.20e-03
    set_layer_rc -via V7 -resistance 8.20e-03

    # RT_MIN_LAYER/RT_MAX_LAYER (mirrors config_multiclock_hier.json --
    # M2-M9, confirmed against the run's own step config.json).
    # set_routing_layers takes a dash-joined range string directly
    # (common/set_routing_layers.tcl); set_wire_rc -layers wants an actual
    # space-separated LIST of layer names, built the same way
    # common/set_rc.tcl does (routing-level order, gated on between
    # RT_MIN_LAYER and RT_MAX_LAYER inclusive).
    set _rt_min_layer [expr {[info exists ::env(RT_MIN_LAYER)] ? $::env(RT_MIN_LAYER) : "M2"}]
    set _rt_max_layer [expr {[info exists ::env(RT_MAX_LAYER)] ? $::env(RT_MAX_LAYER) : "M9"}]
    set_routing_layers -signal ${_rt_min_layer}-${_rt_max_layer} -clock ${_rt_min_layer}-${_rt_max_layer}

    set _wire_rc_layer_names [list]
    set _adding 0
    foreach _layer [$::tech getLayers] {
        if {[$_layer getRoutingLevel] >= 1} {
            set _lname [$_layer getName]
            if {$_lname eq $_rt_min_layer} { set _adding 1 }
            if {$_adding} { lappend _wire_rc_layer_names $_lname }
            if {$_lname eq $_rt_max_layer} { set _adding 0 }
        }
    }
    if {[llength $_wire_rc_layer_names] > 1} {
        set_wire_rc -signal -layers "$_wire_rc_layer_names"
        set_wire_rc -clock  -layers "$_wire_rc_layer_names"
    } else {
        set_wire_rc -signal -layer "$_wire_rc_layer_names"
        set_wire_rc -clock  -layer "$_wire_rc_layer_names"
    }

    if {!$CDC_CHECK_FORCE_GRT} {
        puts "================================================================"
        puts "Using ODB-persisted global-routing guides (no fresh global_route)"
        puts "================================================================"
    } else {
        puts "================================================================"
        puts "CDC_CHECK_FORCE_GRT=1: re-running global_route from scratch"
        puts "================================================================"
        # GRT layer adjustments (mirrors config_multiclock_hier.json's
        # GRT_ADJUSTMENT / GRT_LAYER_ADJUSTMENTS / GRT_MACRO_EXTENSION,
        # confirmed against the run's own step config.json).
        set_global_routing_layer_adjustment * 0.1
        set _grt_layer_names [list]
        foreach _layer [$::tech getLayers] {
            if {[$_layer getRoutingLevel] >= 1} {
                lappend _grt_layer_names [$_layer getName]
            }
        }
        set _grt_adjustments {0.5 0.0 0.0 0.0 0.0 0.0}
        for {set _i 0} {$_i < [llength $_grt_adjustments]} {incr _i} {
            set _lname [lindex $_grt_layer_names $_i]
            if {$_lname eq ""} { break }
            set_global_routing_layer_adjustment $_lname [lindex $_grt_adjustments $_i]
        }
        set_macro_extension 0

        global_route -congestion_iterations 50 -verbose -allow_congestion
    }
    estimate_parasitics -global_routing
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

# cdc_report_domain_wide: companion to cdc_report_through for the section-14
# domain-wide fallback (phase5_soc_multiclock_check.sdc) -- reports
# report_checks -from <from_clock> -to <to_clock> instead of -through
# <collection>, since mem_q / cmd_*/resp_* have no matchable object to query
# -through post-flatten (bead claude_verilog_test-7l5). from_clock/to_clock
# are expected to already be non-empty get_clocks results (sys_clk/cpu_clk
# are declared unconditionally in section 1, so no cdc_require_match guard
# is needed here the way it is for name-pattern-derived collections).
proc cdc_report_domain_wide {from_clock to_clock description report_path} {
    report_checks -from $from_clock -to $to_clock \
        -path_delay max -format full_clock_expanded -digits 3 \
        > $report_path
    set _fh [open $report_path r]
    set _rpt_content [read $_fh]
    close $_fh
    if {[string match "*VIOLATED*" $_rpt_content]} {
        cdc_record_finding "budget VIOLATED: ${description} (see $report_path)"
    } elseif {[string match "*No paths found*" $_rpt_content] || [string match "*unconstrained*" $_rpt_content]} {
        cdc_record_finding "path unconstrained/not found: ${description} (see $report_path)"
    }
}

puts "================================================================"
puts "CDC boundary timing -- async_axi_fifo (u_cpu_axi_cdc), all 5 channels"
puts "================================================================"
# Object mapping re-derived under bead claude_verilog_test-7l5 (2026-08-06)
# against the FLATTENED netlist (SYNTH_HIERARCHY_MODE=flatten) -- see
# phase5_soc_multiclock_check.sdc's "OBJECT RESOLUTION" header block for the
# full tool-verified writeup. Three independent things changed vs. the
# pre-7l5 version of this script, all confirmed empirically against
# final/nl/soc_top.nl.v, not assumed:
#   (1) separator: hierarchy survives only as literal '.' in escaped
#       identifiers, not '/'.
#   (2) object class: cells are anonymous post-flatten (get_cells/get_pins
#       hierarchical name patterns always return empty) -- get_nets is the
#       only name-matchable class, and even then only for nets that kept a
#       clean RTL-derived name.
#   (3) filter syntax: a literal '.' inside a `-filter "name =~ <pattern>"`
#       pattern is NOT a safe glob character on this tool once wildcards
#       surround it (tool-verified: it either returns 0 or, for a bare
#       leading `*.`, silently matches almost the entire netlist). Every
#       pattern below is therefore a '*'-joined chain of dot-free
#       substrings only.
#   (4) semantics: q_o (the synchroniser's LAST-stage output) is a
#       destination-domain-only net, not the crossing itself -- see
#       cdc_2ff_sync.sv. These reports now target the launch->first-capture
#       segment instead: d_i where it survives as its own net
#       (u_wr_ptr_to_rd.d_i does), or the source register net directly
#       where d_i does not survive (u_rd_ptr_to_wr.d_i collapses into
#       rd_gray_q's net during optimisation -- rd_gray_q is used instead,
#       same electrical node).
# mem_q itself (the FIFO storage array's combinational read) has ZERO
# occurrences anywhere in the routed netlist under any object class or
# separator -- it cannot be re-expressed by name post-flatten. It is no
# longer reported here; it is one of the crossings covered by the
# domain-wide fallback report below (mirrors
# phase5_soc_multiclock_check.sdc section 14).
set _fifo_wr2rd_obj [get_nets -hierarchical -filter {name =~ *u_cpu_axi_cdc*u_wr_ptr_to_rd*d_i*} -quiet]
if {[llength $_fifo_wr2rd_obj] == 0} {
    # deferred_flatten fallback (bead je8, 2026-09-15) -- same
    # cdc_capture_flop_d_pins proc phase5_soc_multiclock_check.sdc's
    # section 11 uses, available here because read_sdc evaluated that
    # file's procs in this same interpreter above. Per-instance/per-
    # direction because this one report spans all 5 fifos but AW/W/AR
    # (cpu_clk->sys_clk) and B/R (sys_clk->cpu_clk) launch/capture in
    # opposite directions.
    set _fifo_wr2rd_obj [concat \
        [cdc_capture_flop_d_pins {u_cpu_axi_cdc u_aw_fifo u_wr_ptr_to_rd} cpu_clk sys_clk] \
        [cdc_capture_flop_d_pins {u_cpu_axi_cdc u_w_fifo  u_wr_ptr_to_rd} cpu_clk sys_clk] \
        [cdc_capture_flop_d_pins {u_cpu_axi_cdc u_ar_fifo u_wr_ptr_to_rd} cpu_clk sys_clk] \
        [cdc_capture_flop_d_pins {u_cpu_axi_cdc u_b_fifo  u_wr_ptr_to_rd} sys_clk cpu_clk] \
        [cdc_capture_flop_d_pins {u_cpu_axi_cdc u_r_fifo  u_wr_ptr_to_rd} sys_clk cpu_clk] \
    ]
}
cdc_report_through \
    $_fifo_wr2rd_obj \
    "check_cdc_timing.tcl u_wr_ptr_to_rd.d_i report query (all 5 fifos)" \
    $REPORTS_DIR/cdc_fifo_wr2rd.rpt
cdc_report_through \
    [get_nets -hierarchical -filter {name =~ *u_cpu_axi_cdc*rd_gray_q*} -quiet] \
    "check_cdc_timing.tcl rd_gray_q report query (all 5 fifos, source of u_rd_ptr_to_wr.d_i)" \
    $REPORTS_DIR/cdc_fifo_rd2wr.rpt

puts "================================================================"
puts "CDC boundary timing -- apb_cdc_bridge (u_apb_pll2_cdc, u_apb_dbg_cdc)"
puts "================================================================"
# req_q / ack_q are each a direct RTL passthrough into their cdc_2ff_sync's
# d_i (see apb_cdc_bridge.sv), and unlike section 11's gray-pointer case,
# BOTH source registers keep their own net name here -- matched directly, no
# d_i lookup needed.
#
# NAMES: these were req_toggle_q / ack_toggle_q until bead
# claude_verilog_test-rfz converted the handshake from 2-phase NRZ to 4-phase
# RZ. The filters below MUST track that rename -- a stale pattern here matches
# zero nets and the budget silently goes unchecked, which is exactly bead
# claude_verilog_test-7l5's failure mode. The cmd_*/resp_* payload capture
# registers have zero occurrences anywhere in the netlist (same class as
# mem_q) and are covered by the domain-wide fallback report below instead.
cdc_report_through \
    [get_nets -hierarchical -filter {name =~ *u_apb_pll2_cdc*req_q* || name =~ *u_apb_pll2_cdc*ack_q*} -quiet] \
    "check_cdc_timing.tcl u_apb_pll2_cdc req_q/ack_q report query" \
    $REPORTS_DIR/cdc_apb_pll2_toggle.rpt
cdc_report_through \
    [get_nets -hierarchical -filter {name =~ *u_apb_dbg_cdc*req_q* || name =~ *u_apb_dbg_cdc*ack_q*} -quiet] \
    "check_cdc_timing.tcl u_apb_dbg_cdc req_q/ack_q report query" \
    $REPORTS_DIR/cdc_apb_dbg_toggle.rpt

puts "================================================================"
puts "CDC boundary timing -- PMU/IRQ single-bit crossings"
puts "================================================================"
# u_cpu_clk_dis_sync is fed `.d_i(~pmu_cpu_clk_en)` (an inverter output --
# real logic between source and synchroniser), so its d_i net survives
# under its own scoped name. u_cpu_iso_en_sync / u_ext_irq_sync /
# u_timer_irq_sync are each a direct passthrough whose d_i net does NOT
# survive; the source signal itself does, as a PLAIN top-level net
# (pmu_cpu_iso_en / ext_irq / timer_irq). NOTE: OpenSTA's -filter grammar
# was tool-verified to only evaluate the first two clauses of a 3+-way
# "||" chain (a latent bug in this script's pre-7l5 4-way OR here, silently
# dropping u_ext_irq_sync and u_timer_irq_sync from the old report even
# before the separator/object-class issues) -- this is why the query below
# is split into two 2-way-OR get_nets calls and concatenated, rather than
# one 4-way chain.
# u_cpu_clk_dis_sync's d_i-name sub-match, split out on its own so a
# deferred_flatten netlist where that name vanishes (bead je8, 2026-09-15)
# doesn't silently ride the OR with pmu_cpu_iso_en -- an OR'd collection
# only needs ONE side non-empty to look "matched" via cdc_report_through's
# llength check, so a vacuous d_i sub-clause was invisible in this report
# every time pmu_cpu_iso_en's plain net matched, i.e. always. That masked
# the exact CDC-EXCEPTION-MISS bead je8's early check on run 8 surfaced.
set _clk_dis_report_obj [get_nets -hierarchical -filter {name =~ *u_cpu_clk_dis_sync*d_i*} -quiet]
if {[llength $_clk_dis_report_obj] == 0} {
    set _clk_dis_report_obj [cdc_capture_flop_d_pins {u_cpu_clk_dis_sync} sys_clk cpu_clk]
}
set _pmu_irq_a [concat $_clk_dis_report_obj [get_nets -hierarchical -filter {name == pmu_cpu_iso_en} -quiet]]
set _pmu_irq_b [get_nets -hierarchical -filter {name == ext_irq || name == timer_irq} -quiet]
cdc_report_through \
    [concat $_pmu_irq_a $_pmu_irq_b] \
    "check_cdc_timing.tcl PMU/IRQ single-bit crossing report query" \
    $REPORTS_DIR/cdc_pmu_irq.rpt

puts "================================================================"
puts "CDC boundary timing -- domain-wide fallback (mem_q + apb cmd_/resp_ payload)"
puts "================================================================"
# mem_q (async_axi_fifo) and cmd_*/resp_* (both apb_cdc_bridge instances)
# have zero occurrences anywhere in the routed netlist by any name/object
# class -- see phase5_soc_multiclock_check.sdc section 14 for the full
# writeup and the measured -through-vs-from/to precedence this relies on.
# This report is inherently a whole-boundary catch-all (report_checks
# -from/-to over ALL registers in each domain, not a query isolated to
# these specific payload buses) since there is no narrower object to query
# post-flatten; the VIOLATED/unconstrained detection below still applies.
cdc_report_domain_wide \
    [get_clocks cpu_clk] [get_clocks sys_clk] \
    "check_cdc_timing.tcl domain-wide fallback report (cpu_clk -> sys_clk, covers mem_q/cmd_*/resp_* class)" \
    $REPORTS_DIR/cdc_domain_wide_cpu_to_sys.rpt
cdc_report_domain_wide \
    [get_clocks sys_clk] [get_clocks cpu_clk] \
    "check_cdc_timing.tcl domain-wide fallback report (sys_clk -> cpu_clk, covers mem_q/cmd_*/resp_* class)" \
    $REPORTS_DIR/cdc_domain_wide_sys_to_cpu.rpt

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
