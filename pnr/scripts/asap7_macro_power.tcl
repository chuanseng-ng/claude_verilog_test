# asap7_macro_power.tcl — characterize lumped macro power for an ASAP7 hard
# macro (rv32i_cpu_top / gpu_top) from its own flat gate-level netlist.
#
# Companion to (NOT a modification of) asap7_macro_views.tcl. write_timing_model
# (used by that script) has no power-characterization code path — verified
# zero 'power' hits in vendored OpenSTA MakeTimingModel.cc — so the abstracted
# macro .lib it produces declares leakage_power_unit but never emits
# cell_leakage_power / internal_power. That means report_power attributes
# 0.00 W to the macro at every level above it (bead claude_verilog_test-86a,
# root-caused while resolving bead ew3). This script does not touch
# write_timing_model or the LEF/timing views it produces; it only computes a
# power number to inject afterward with asap7_macro_power_inject.py.
#
# Tool: plain OpenSTA ("sta -exit ..."), NOT OpenROAD — no ODB/floorplan is
# needed or used. This deliberately works from just the macro's own flat
# post-route netlist + the same Liberty set used for synthesis/STA + its
# block-level SDC. That also means there is no post-route SPEF/DEF in this
# flow, so net parasitics are whatever OpenSTA infers from gate input-pin
# capacitance alone (no wire RC) — see the header comment
# asap7_macro_power_inject.py writes into the target .lib for the full
# caveat; it is carried into the injected numbers, not hidden.
#
# Activity assumption: uniform toggle rate + duty, applied globally via
# set_power_activity. Default 0.20 / 0.5 matches this repo's own established
# convention for "no VCD available" power estimation (pnr/scripts/08_power.tcl,
# Sky130 Phase 3 flow: "0.20 (20%) ... conservative ... errs on the side of
# overestimating dynamic power, which is safe for thermal and IR-drop
# budgeting"). It is NOT derived from any captured workload trace for this
# design — no gate-level VCD/SAIF exists for either macro (same gap already
# documented in this project's memory for other blocks: no SDF support in the
# Verilator sim flow, no per-node switching capture). Override via
# ACTIVITY_RATE / ACTIVITY_DUTY env vars, or point VCD_FILE at a real
# simulation dump (with VCD_SCOPE set to the dut's instance path in that
# testbench) to replace the flat default with measured activity.
#
# Invoked via: sta -exit scripts/asap7_macro_power.tcl
#   (or through the MCP eda-opensta session: read_liberty/read_verilog/
#    link_design/read_sdc by hand, then source this script's activity+
#    report_power tail — see README.md in this directory for the manual
#    session-based equivalent used to validate this script.)
#
# Inputs (env vars):
#   NETLIST_PATH   — flat gate-level netlist for the macro's OWN block
#                     (gunzipped .nl.v — e.g. pnr/asap7/cpu/macro/rv32i_cpu_top.nl.v
#                     after `gunzip -k`). This is the macro's own internal
#                     implementation, not a black-box view — it must resolve
#                     down to real standard cells + any internal hard macros
#                     (e.g. the SRAM instances inside rv32i_cpu_top).
#   ASAP7_LIBS     — space-separated Liberty files: the 5 ASAP7 stdcell libs
#                     + the macro's own internal SRAM lib(s). Same set
#                     asap7_macro_views.tcl reads for write_timing_model.
#   SDC_PATH       — the macro's OWN block-level SDC (defines its clock
#                     period — this is what fixes the frequency the
#                     characterized power corresponds to).
#   DESIGN_NAME    — top module name (rv32i_cpu_top / gpu_top).
#   POWER_REPORT_OUT — informational only (recorded in the printed header);
#                     this script writes its report to STDOUT (plain OpenSTA
#                     has no in-Tcl redirect — see the note above the
#                     report_power call below), so the caller must itself
#                     redirect stdout to this path for
#                     asap7_macro_power_inject.py to consume. Required so the
#                     printed header names the same path the caller intends
#                     to use.
#   ACTIVITY_RATE  — global toggle-rate override (default 0.20).
#   ACTIVITY_DUTY  — global duty-cycle override (default 0.5).
#   VCD_FILE / VCD_SCOPE — optional: read_vcd instead of the flat default.
#
# Output: STDOUT — full report_power -digits 6 text (Internal / Switching /
# Leakage / Total, by group: Sequential / Combinational / Clock / Macro /
# Pad, plus the Total row asap7_macro_power_inject.py parses). Redirect it:
#   sta -exit pnr/scripts/asap7_macro_power.tcl > "$POWER_REPORT_OUT" 2>&1
#----------------------------------------------------------------

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

# ── 4. Switching activity ─────────────────────────────────────────────────
# NOTE: no SPEF/DEF is read here — this macro's post-route run directory is
# gone (bead 86a), so this is Liberty-table power from gate input-pin
# capacitance only, no post-route wire RC. That is a second, independent
# approximation on top of the activity assumption; asap7_macro_power_inject.py
# writes both into the target .lib's header comment.
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
# Plain OpenSTA ("sta", as opposed to "openroad") has no `redirect { ... }`
# block command or exposed sta::redirect_file_begin/end proc — both were
# tried against this repo's vendored OpenSTA 2.7.0 and neither exists
# (`info commands *redirect*` is empty). So this script does not write
# POWER_REPORT_OUT itself; it prints the header + report_power output to
# stdout in the exact format asap7_macro_power_inject.py expects, and the
# caller captures stdout to $POWER_REPORT_OUT:
#
#   sta -exit pnr/scripts/asap7_macro_power.tcl > "$POWER_REPORT_OUT" 2>&1
#
# (the eda-opensta MCP session equivalent already writes its own report file
# per call — see tools/eda/README.md — so a caller driving this through that
# MCP server instead of a bare `sta -exit` can use that file directly and
# skip the shell redirect.)
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
