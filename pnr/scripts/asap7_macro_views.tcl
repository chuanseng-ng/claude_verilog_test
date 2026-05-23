# asap7_macro_views.tcl — generate abstract LEF + timing-model LIB for rv32i_cpu_top
#
# Invoked via: openroad -exit scripts/asap7_macro_views.tcl
# Inputs (env vars set by make macro-views-asap7):
#   ODB_PATH      — post-route ODB (final/odb/rv32i_cpu_top.odb)
#   SDC_PATH      — signoff SDC  (final/sdc/rv32i_cpu_top.sdc)
#   ASAP7_LIBS    — space-separated Liberty files (5 stdcell libs + SRAM lib)
#   MACRO_OUT_DIR — destination directory for rv32i_cpu_top.lef + *.lib
#   DESIGN_NAME   — module name (rv32i_cpu_top)
#
# GDS is intentionally omitted: Magic has no ASAP7 tech file and the SRAM stub
# has no GDS geometry.  LEF + LIB + netlist matches the existing SRAM macro
# convention used in this project.

set_cmd_units \
    -time ns -capacitance pF -current mA \
    -voltage V -resistance kOhm -distance um

# ── 1. Load routed design ─────────────────────────────────────────────────────
puts "=== Loading ODB: $::env(ODB_PATH) ==="
read_db $::env(ODB_PATH)

# ── 2. Abstract LEF (purely geometric — no liberty needed) ────────────────────
set out_lef [file join $::env(MACRO_OUT_DIR) "$::env(DESIGN_NAME).lef"]
puts "=== Writing abstract LEF → $out_lef ==="
write_abstract_lef -bloat_occupied_layers $out_lef

# ── 3. Load Liberty for nom_tt_025C_0p7V corner ───────────────────────────────
foreach lib [split $::env(ASAP7_LIBS) " "] {
    set lib [string trim $lib]
    if {$lib eq ""} continue
    puts "Reading liberty: [file tail $lib]"
    read_liberty $lib
}

# ── 4. Load timing constraints ────────────────────────────────────────────────
puts "=== Reading SDC: $::env(SDC_PATH) ==="
read_sdc $::env(SDC_PATH)

# ── 5. Timing model ───────────────────────────────────────────────────────────
# Remove source latencies so the model is context-independent at top level.
set_clock_latency -source -max 0 [all_clocks]
set_clock_latency -source -min 0 [all_clocks]

set out_lib [file join $::env(MACRO_OUT_DIR) \
    "$::env(DESIGN_NAME)__nom_tt_025C_0p7V.lib"]
puts "=== Writing timing model → $out_lib ==="
write_timing_model $out_lib

puts "\n=== Macro views generation complete. ==="
