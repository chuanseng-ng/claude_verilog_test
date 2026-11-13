# asap7_macro_power.tcl - Lumped power of an ASAP7 hard macro (rv32i_cpu_top or gpu_top) from its flat gate-level netlist
#
# Scope: sta -exit pnr/scripts/asap7_macro_power.tcl > "$POWER_REPORT_OUT" 2>&1
#   The report goes to stdout. asap7_macro_power_inject.py parses it.
# Contents: reads the Liberty files, the netlist and the block SDC; sets switching activity (a global default or a VCD);
#   runs report_power -digits 6 and prints a header and the report.
# Inputs (environment variables):
#   NETLIST_PATH: flat gate-level netlist of the macro's own block (the gunzipped .nl.v). It must resolve to standard cells
#     and internal hard macros, such as the SRAM instances. A black-box view does not work.
#   ASAP7_LIBS: space-separated Liberty files: the five ASAP7 stdcell libs and the internal SRAM lib(s).
#     It is the set that asap7_macro_views.tcl reads for write_timing_model.
#   SDC_PATH: the block-level SDC of the macro. Its clock period fixes the frequency of the characterized power.
#   DESIGN_NAME: top module name. POWER_REPORT_OUT: required, and used only in the printed header.
#   ACTIVITY_RATE (default 0.20) and ACTIVITY_DUTY (default 0.5): global toggle rate and duty cycle.
#   VCD_FILE and VCD_SCOPE (optional): read the activity from a VCD instead of the flat default.
# User rules:
#   Redirect stdout to the path in POWER_REPORT_OUT yourself. Plain OpenSTA has no in-Tcl redirect.
#   Set POWER_REPORT_OUT to the path you redirect to, so the printed header names that path.
#   The script reads no SPEF, so net load is pin capacitance only. The default activity is an assumption, not a measured trace.
# Doc: tm:pd:scripts-asap7-macro-power-tcl

set NETLIST         $::env(NETLIST_PATH)
set DESIGN          $::env(DESIGN_NAME)
set SDC_PATH        $::env(SDC_PATH)
set REPORT_OUT      $::env(POWER_REPORT_OUT)

set ACTIVITY_RATE 0.20
if {[info exists ::env(ACTIVITY_RATE)]} { set ACTIVITY_RATE $::env(ACTIVITY_RATE) }
set ACTIVITY_DUTY 0.5
if {[info exists ::env(ACTIVITY_DUTY)]} { set ACTIVITY_DUTY $::env(ACTIVITY_DUTY) }

set VCD_FILE ""
if {[info exists ::env(VCD_FILE)] && [file exists $::env(VCD_FILE)]} {
    set VCD_FILE $::env(VCD_FILE)
}
set VCD_SCOPE ""
if {[info exists ::env(VCD_SCOPE)]} { set VCD_SCOPE $::env(VCD_SCOPE) }

# ── 1. Liberty ─────────────────────────────────────────────────────────────
foreach lib [split $::env(ASAP7_LIBS) " "] {
    set lib [string trim $lib]
    if {$lib eq ""} continue
    puts "Reading liberty: [file tail $lib]"
    read_liberty $lib
}

# ── 2. Netlist ───────────────────────────────────────────────────────────────
puts "=== Reading netlist: $NETLIST ==="
if {![file exists $NETLIST]} {
    error "Netlist not found: $NETLIST (gunzip the .nl.v.gz first)"
}
read_verilog $NETLIST
link_design $DESIGN

# ── 3. SDC (fixes the clock period this characterization corresponds to) ──
puts "=== Reading SDC: $SDC_PATH ==="
read_sdc $SDC_PATH

if {$VCD_FILE ne ""} {
    puts "=== Switching activity: VCD $VCD_FILE (scope: $VCD_SCOPE) ==="
    if {$VCD_SCOPE ne ""} {
        read_vcd $VCD_FILE -scope $VCD_SCOPE
    } else {
        read_vcd $VCD_FILE
    }
} else {
    puts "=== Switching activity: flat default (activity=$ACTIVITY_RATE, duty=$ACTIVITY_DUTY) ==="
    set_power_activity -global -activity $ACTIVITY_RATE -duty $ACTIVITY_DUTY
}

# ── 5. report_power ────────────────────────────────────────────────────────
# Plain OpenSTA (sta, not openroad) has no redirect block command and no sta::redirect_file_begin proc.
# So this script does not write POWER_REPORT_OUT. It prints the header and the report_power output to stdout in the format
# that asap7_macro_power_inject.py expects. The caller captures stdout: sta -exit pnr/scripts/asap7_macro_power.tcl > "$POWER_REPORT_OUT" 2>&1
set ACTIVITY_SOURCE_STR "flat_default"
if {$VCD_FILE ne ""} { set ACTIVITY_SOURCE_STR "vcd:$VCD_FILE" }

puts "# asap7_macro_power.tcl report — design=$DESIGN"
puts "# activity_source=$ACTIVITY_SOURCE_STR"
puts "# activity_rate=$ACTIVITY_RATE duty=$ACTIVITY_DUTY"
puts "# netlist=$NETLIST"
puts "# sdc=$SDC_PATH"
puts ""
puts "=== Macro power characterization ($DESIGN) ==="
report_power -digits 6
