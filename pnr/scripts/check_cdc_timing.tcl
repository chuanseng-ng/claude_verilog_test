# check_cdc_timing.tcl - Post-route CDC budget check for the 2-domain ASAP7 SoC (OpenSTA)
#
# Scope: make target check-cdc-timing-asap7-soc runs it as `sta pnr/scripts/check_cdc_timing.tcl`.
#   With CDC_CHECK_ODB set, run it under openroad, not sta. It reads the SDC phase5_soc_multiclock_check.sdc.
# Contents: reads the Liberty files and the routed soc_top netlist, reads the check SDC, then runs targeted report_checks
#   queries on the CDC endpoints that the SDC excepts. It collects every finding and prints one CDC-CHECK-RESULT block.
# Inputs: CDC_CHECK_RUN_DIR (required): a routed ASAP7 SoC run built with PNR_SDC_FILE set to phase5_soc_multiclock.sdc.
#   Optional: CDC_CHECK_SDC (check SDC path), CDC_CHECK_ODB (read this OpenROAD database instead of the netlist),
#   CDC_CHECK_FORCE_GRT=1, CDC_CHECK_PROPAGATED_CLOCK=1, ASAP7_LIB_DIR (Liberty directory),
#   and RT_MIN_LAYER and RT_MAX_LAYER (routing layer range).
# User rules:
#   Exit 0: PASS. Every CDC exception matched a real object and every targeted budget was met.
#   Exit 1: CDC finding. An exception matched an empty collection (unmatched or renamed instance),
#   or a budget has a violated slack. The final CDC-CHECK-RESULT block names every finding.
#   Exit 2: setup or usage error. The check could not run: a missing variable, Liberty, netlist or SDC file,
#   or an SDC read failure unrelated to CDC-EXCEPTION-MISS. CI must tell exit 1 and exit 2 apart.
#   Batch-mode sta returns exit code 0 even after a Tcl error. This script never relies on an uncaught error to fail.
#   This script runs targeted queries only. It is not a full-chip sign-off sweep.
# Doc: tm:pd:scripts-check-cdc-timing-tcl, cr:pd:scripts-check-cdc-timing-tcl

proc cdc_fatal_setup {msg} {
    puts "ERROR: CDC-CHECK-SETUP-ERROR: $msg"
    exit 2
}

# cdc_check_findings / cdc_check_finding_msgs: accumulate EVERY CDC
# finding (unmatched exception collections and violated timing budgets)
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

set CDC_CHECK_ODB [expr {[info exists ::env(CDC_CHECK_ODB)] ? $::env(CDC_CHECK_ODB) : ""}]

set CDC_CHECK_FORCE_GRT [expr {[info exists ::env(CDC_CHECK_FORCE_GRT)] && $::env(CDC_CHECK_FORCE_GRT) == "1"}]

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
# The check SDC raises a Tcl error from its section 15 gate when a CDC exception matched nothing. That is an expected finding.
# Only a non-empty ::cdc_exception_misses proves this mechanism. Any other read_sdc failure is a setup error.
# Continue past the error, so the report_checks queries below still run and all findings go into one final report.
    if {[info exists ::cdc_exception_misses] && [llength $::cdc_exception_misses] > 0} {
        foreach _miss $::cdc_exception_misses {
            cdc_record_finding "unmatched CDC exception (phase5_soc_multiclock_check.sdc): $_miss"
        }
        puts "WARNING: check_cdc_timing.tcl: $CHECK_SDC reported [llength $::cdc_exception_misses] unmatched CDC exception(s) above (CDC-EXCEPTION-MISS). Continuing to run the remaining targeted timing queries; all findings are summarized in the final CDC-CHECK-RESULT block."
    } else {
        cdc_fatal_setup "read_sdc failed on $CHECK_SDC for a reason other than an unmatched CDC exception: $_sdc_err"
    }
}

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

    puts "================================================================"
    puts "ANNOTATION-CHECK: parasitic annotation coverage after estimate_parasitics -global_routing"
    puts "================================================================"
    catch {report_parasitic_annotation}
    puts "================================================================"
    puts "ANNOTATION-CHECK WARNING: if the summary above shows a large 'unannotated drivers' count relative to the design's total driver/instance count, treat every slack/delay number in the CDC-CHECK-RESULT below as datapath-SHAPE-only (real cell delay, real logic depth, real fanout loading -- but wireload-model or near-zero wire RC), NOT a genuine post-GRT/post-route timing verdict. See the CDC_CHECK_FORCE_GRT header comment (bead je8, 2026-09-15) for why this script could not obtain real GRT-parasitics annotation within a 3.5G memory budget on this SoC, and what was tried."
    puts "================================================================"
}

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
set _fifo_wr2rd_obj [get_nets -hierarchical -filter {name =~ *u_cpu_axi_cdc*u_wr_ptr_to_rd*d_i*} -quiet]
if {[llength $_fifo_wr2rd_obj] == 0} {
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

cdc_report_through \
    [get_nets -hierarchical -filter {name == pmu_cpu_iso_en_sync} -quiet] \
    "check_cdc_timing.tcl PMU iso-ack return crossing report query (cpu_clk -> sys_clk)" \
    $REPORTS_DIR/cdc_pmu_iso_ack.rpt

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
