# vivado_fmax.tcl -- driven by tools/fpga/vivado_fmax.sh through VFMAX_* environment variables (bead hlrm).
# Non-project batch flow. Not for CI (Vivado is not available there).

proc env_or {name default} {
    if {[info exists ::env($name)] && $::env($name) ne ""} { return $::env($name) }
    return $default
}
set root    $::env(VFMAX_ROOT)
set out     $::env(VFMAX_OUT)
set gpu     $::env(VFMAX_GPU)
set phase   $::env(VFMAX_PHASE)
set tag     $::env(VFMAX_TAG)
set part    [env_or VFMAX_PART xc7a200tsbg484-1]
set threads [env_or VFMAX_THREADS 4]
set dir     $out/$gpu
set rdir    $dir/$tag
set t0 [clock seconds]
proc stamp {msg} {
    puts "VFMAX-STAMP [expr {[clock seconds] - $::t0}]s: $msg"
    flush stdout
}

set_param general.maxThreads $threads
if {$phase eq "probe"} {
    # cheap licence / part check: no design is read
    puts "VFMAX-PROBE version=[version -short]"
    puts "VFMAX-PROBE part=[get_parts $part]"
    puts "VFMAX-PROBE family=[get_property FAMILY [get_parts $part]] luts=[get_property LUT_ELEMENTS [get_parts $part]]"
    exit 0
}
file mkdir $rdir
stamp "start phase=$phase gpu=$gpu part=$part version=[version -short]"

if {$phase eq "synth" || $phase eq "both"} {
    set fh [open $dir/filelist.txt r]
    set files [split [string trim [read $fh]] "\n"]
    close $fh
    stamp "read_verilog -sv [llength $files] files"
    # one read_verilog per file: a `default_nettype none left open by one file must not leak into the next (Vivado carries
    # compiler directives across the files of a single read_verilog call; pnr/sky130/soc/gpu_top_tieoff.sv is implicit-net style)
    foreach f $files {
        if {[file tail $f] eq "gpu_top_tieoff.sv"} {
            # Vivado 2026.1 rejects `input logic x` under `default_nettype none` ([Synth 8-6735]); Verilator, sv2v and
            # yosys accept it. Read a copy with that one directive line removed (the repo file is untouched, the
            # module's logic is identical: every port is explicitly typed, so the directive has no effect on it).
            set fh [open $f r]; set txt [read $fh]; close $fh
            regsub -all -line {^`default_nettype (none|wire)\s*$} $txt "" txt
            set f $dir/gpu_top_tieoff_vivado.sv
            set fh [open $f w]; puts -nonewline $fh $txt; close $fh
            stamp "gpu_top_tieoff.sv read from a copy without default_nettype ($f)"
        }
        read_verilog -sv $f
    }
    stamp "synth_design"
    # In-context synthesis of the 6-pin timing harness; default flatten_hierarchy (rebuilt) keeps module names in cell
    # paths so critical paths can be attributed to modules. +define FPGA / __pnr__ as Stage 0 (sv2v flow) uses.
    synth_design -top ecp5_timing_harness -part $part -verilog_define FPGA -verilog_define __pnr__
    stamp "synth_design done"
    write_checkpoint -force $dir/synth.dcp
    report_utilization -file $dir/synth.utilization.rpt
    report_utilization -hierarchical -hierarchical_depth 3 -file $dir/synth.utilization_hier.rpt
    report_clocks -file $dir/synth.clocks.rpt
    report_drc -file $dir/synth.drc.rpt
    stamp "synth reports written"
}

if {$phase eq "impl" || $phase eq "both" || $phase eq "constr"} {
    if {$phase ne "both"} {
        stamp "open_checkpoint synth.dcp"
        open_checkpoint $dir/synth.dcp
    }
    source $::env(VFMAX_HERE)/vivado_fmax_constraints.tcl
    apply_constraints [env_or VFMAX_PERIOD 10.0] [env_or VFMAX_PERIOD_CPU 10.0] $rdir
    stamp "constraints applied"
    report_clocks -file $rdir/pre.clocks.rpt
    report_clock_networks -file $rdir/pre.clock_networks.rpt
    check_timing -verbose -file $rdir/pre.check_timing.rpt
    if {$phase eq "constr"} { stamp "constr-only run, exiting"; exit 0 }

    opt_design
    stamp "opt_design done"
    place_design
    stamp "place_design done"
    report_timing_summary -no_header -max_paths 1 -file $rdir/post_place.timing_summary.rpt
    phys_opt_design
    stamp "phys_opt_design done"
    route_design
    stamp "route_design done"
    if {[env_or VFMAX_PHYS_OPT_POST 0] eq "1"} {
        phys_opt_design
        stamp "post-route phys_opt_design done"
    }
    write_checkpoint -force $rdir/routed.dcp

    report_timing_summary -max_paths 10 -report_unconstrained -file $rdir/timing_summary.rpt
    report_utilization -file $rdir/utilization.rpt
    report_utilization -hierarchical -hierarchical_depth 3 -file $rdir/utilization_hier.rpt
    report_clock_interaction -delay_type min_max -file $rdir/clock_interaction.rpt
    report_clock_utilization -file $rdir/clock_utilization.rpt
    report_methodology -file $rdir/methodology.rpt
    report_drc -file $rdir/drc.rpt
    report_high_fanout_nets -timing -max_nets 15 -file $rdir/high_fanout.rpt
    report_exceptions -file $rdir/exceptions.rpt
    report_cdc -details -file $rdir/cdc.rpt
    # Top paths: per capture clock (setup), 3 each, full detail with logic levels and the route/logic split.
    foreach c [get_clocks] {
        set cn [get_property NAME $c]
        report_timing -delay_type max -max_paths 3 -nworst 1 -to $c -input_pins \
            -file $rdir/paths_setup_to_$cn.rpt
    }
    report_timing -delay_type min -max_paths 5 -nworst 1 -input_pins -file $rdir/paths_hold_worst.rpt
    stamp "impl reports written"
}
stamp "done"
