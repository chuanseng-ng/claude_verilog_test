###############################################################################
# pdn.tcl — Power Distribution Network for sky130_soc on Sky130A HD
#
# Die: 6700 x 3100 um (GH #104 clearance fix, 2026-07-22).  Single power
#   domain (VPWR/VGND at 1.8 V).
#
# *** KNOWN LIMITATION, SEE constraints/sky130_soc.sdc HEADER FOR FULL
# DETAIL. UPDATED 2026-07-25: rv32i_cpu_top is NOW characterized
# per-corner (9 exact corner keys -> 9 distinct Liberty views, verified
# from each corner's own sta.log). Only sky130_sram_4kbyte_1rw1r_32x1024_8
# remains nom_tt-only, wildcarded to every PVT corner, and it is now the
# SOLE source of this limitation (GH #120 / bead o1i).
#
# The fix showed the earlier "ss hold is pessimistic" reasoning was WRONG:
# with real per-corner CPU libs, hold got WORSE (max_ss -0.0708 ->
# -0.3997 ns; nom_tt +0.1807 MET -> -0.0923 VIOLATING), and max_ss setup
# went -5.3197 -> -10.4730 ns. The wildcard was optimistic in BOTH
# directions. CAVEAT: that run also enabled antenna repair (+2018 diodes,
# perturbing routing), so the deltas are not cleanly attributable to the
# libs alone. Still a TYPICAL-CORNER (nom_tt) sign-off -- and even nom_tt
# now carries a hold violation. Do not let a summary imply otherwise. ***
#
# KNOWN LIMITATION (GH #104, 2026-07-24): sky130_sram_4kbyte_1rw1r_32x1024_8
# is NOT KLayout-DRC-clean. Full-deck KLayout DRC (sky130A_mr.drc, the
# authoritative signoff deck) on the Stage-2 sign-off GDS
# (RUN_2026-07-24_09-58-19) found exactly 4 real violations, ALL inside
# this macro's own OpenRAM-generated internal cells (confirmed via a
# standalone full-deck KLayout run on the macro's raw GDS alone, with NO
# SoC context: identical violations, identical coordinates -- proving
# they are inherent to the macro compile, not introduced or fixable by
# any SoC-level PDN/floorplan/routing change):
#   m2.2   (met2 spacing <0.14um) x1 -- cell ..._wmask_dff,
#           measured 0.055um -- ~60% SHORT of spec (the most significant
#           of the four; NOT rounded away).
#   via2.2 (via2 spacing <0.2um)  x2 -- cell sky130_sram_4kbyte_1rw1r_32x1024_8
#           (macro top) and cell ..._bank, both measured 0.125um -- ~37.5%
#           short of spec.
#   m3.2   (met3 spacing <0.3um)  x1 -- cell ..._bank, measured 0.29um --
#           ~3% short (~1nm); plausibly a grid-rounding/floating-point
#           boundary artifact in OpenRAM's geometry engine, but still
#           technically non-conformant -- not waved off as pure noise.
# ROOT CAUSE: this macro was compiled views-first with check_lvsdrc=False
# (a deliberate choice made after the check_lvsdrc=True extraction pass
# died to a host reboot at the ~7h mark -- see memory/pd/run_state.md).
# OpenRAM's own DRC therefore never ran on this macro at all. Enabling
# check_lvsdrc=True would have REPORTED these same 4 violations but not
# fixed them: OpenRAM's layout generation is deterministic from its
# module code and config (compiler/modules/bank.py, and the generic
# dff_array factory type instantiated as wmask_dff) -- the checker only
# observes geometry the generator already committed to, it does not
# iterate or auto-remediate.
# SCOPE: confirmed via compiler/modules/bank.py (OpenRAM's own top-level
# bank-assembly Python class) and by searching the installed
# sky130_fd_bd_sram foundry-primitive library (zero matches for
# "wmask_dff"/"bank") that these violations sit in OpenRAM's GENERATED
# ASSEMBLY layer, not in a foundry-drawn hand-crafted primitive cell.
# They are NOT caused by, and NOT fixable via, this project's SoC
# integration work (PDN grid, floorplan, macro placement, or routing).
# USER DECISION (2026-07-24): accept + document, do not patch the GDS,
# do not retry the OpenRAM config, do not attempt a DRC-clean regenerate
# at this time. Rationale: upstream OpenRAM-generator issues, provably
# unfixable at the SoC level (proven by the standalone-macro isolation
# test above); a GDS-level hand-patch would break reproducibility from
# the OpenRAM config and is not a sustainable fix. The Stage-2 milestone
# value -- proving the SoC integrates and clears PSM-0040/GRT/DRT/LVS
# end-to-end on a real, fabricatable PDK with a genuine OpenRAM hard
# macro -- holds regardless of this open item.
# SIGN-OFF RECORD PHRASING: this is NOT "KLayout DRC clean". State it as
# "KLayout DRC: 4 violations, all macro-internal, upstream OpenRAM
# generator, accepted+documented". Do not let a summary imply a clean
# full-chip DRC signoff.
# FOLLOW-UP: CLOSED WON'T-FIX 2026-07-25 (GH #121, bead
# claude_verilog_test-0jp). Evidence for the acceptance: efabless's own
# prebuilt sky130_sram_2kbyte_1rw1r_32x512_8 -- the macro used in real
# MPW silicon -- ships 32 magic DRC errors in its OWN committed OpenRAM
# build log, and is likewise "Analytical model enabled" / "Only
# generating nominal corner timing" with a single _TT_1p8V_25C.lib. The
# repo has no 4 KB 32x1024_8 variant to swap to. These 4 violations are
# OpenRAM generator norm, not a consequence of our check_lvsdrc=False
# shortcut (OpenRAM geometry is deterministic; the checker only reports).
# Re-open trigger: a genuine tape-out-readiness review.
#
# RE-CONFIRMED 2026-07-25 at RUN_2026-07-25_13-29-40: still EXACTLY 4,
# same rules and same cells (m2.2 in ..._wmask_dff; via2.2 x2 in macro-top
# and ..._bank; m3.2 in ..._bank). Notably this run inserted 2018 antenna
# diodes and re-routed, and introduced ZERO new KLayout violations --
# so the antenna flow is DRC-safe. Magic DRC also unchanged at 9081
# (nwell.4 = 9049 + met4.4a = 32, the known artifact class).
#
# KNOWN LIMITATION (GH #104, 2026-07-24): IR-drop analysis
# (OpenROAD.IRDropReport) is NOT meaningful for this flow -- VSRC_LOC_FILES
# is unset (in this config AND in pnr/sky130/cpu/config.json; a
# pre-existing, project-wide gap, not introduced here). Without a real
# power-source location, analyze_power_grid has nothing to source current
# from, producing physically nonsensical IR numbers (observed: "Worstcase
# IR drop: 6.48e+06 V" on a 1.8 V supply). This is documented, expected
# LibreLane behavior absent VSRC_LOC_FILES, not a bug. Setting
# VSRC_LOC_FILES requires real bond-pad/bump (x,y) locations from a
# padframe or package map -- this design has NO padframe defined at this
# project phase (direct I/O ports, no pad ring), so any such file written
# now would be an invented, unfounded coordinate set. Deliberately NOT
# fabricated. Revisit once a package/bump plan exists in a future phase.
# PSM-0040 connectivity ("all shapes connected") IS meaningful and clean
# regardless -- it is the real signal from this PDN flow, not IR drop.
#
# GH #104 UPDATE (2026-07-23/24, REVERSES Option C): the sram_controller
# module's backing store is a hard macro again -- but NOT the old
# custom-hardened composite block (whole AXI4 wrapper + array hardened as
# one unit) that hit the persistent ~7,400-node PSM-0069 VPWR/VGND gap
# documented in memory/pd/run_state.md (ring removal, instance-specific
# grids, precisely-anchored straps -- never fully closed). That approach
# is abandoned. Instead, only the raw sky130_sram_4kbyte_1rw1r_32x1024_8
# OpenRAM primitive is now a hard macro (instance path
# u_sram.u_sram_macro post-flatten), with a STANDARD OpenRAM PG abstract
# (vccd1/vssd1 on met3+met4) -- the same style as rv32i_cpu_top's own 10
# internal OpenRAM SRAMs, which are PSM-0040 clean. TWO hard macros now:
# rv32i_cpu_top (VPWR/VGND, met4) + sky130_sram_4kbyte_1rw1r_32x1024_8
# (vccd1/vssd1, met3+met4).
#
# CPU macro (rv32i_cpu_top, regenerated balanced-pin GDS RUN_2026-07-21_18-02-11)
#   occupies (150,207.0)-(3750,2007.0), 3600 x 1800 um. y_origin=207.0
#   (Run 12 GCell-grid-alignment fix, 2026-07-22 -- see macro_placement.cfg
#   for the full GRT-0118 root-cause writeup: GRT's GCell tile pitch is a
#   fixed 6.9um technology constant; 207.0 = 6.9*30 lands the macro's south
#   edge exactly on a tile boundary instead of straddling one).
#   VPWR/VGND on met4 (V-stripes from Stage-1 P&R).
#   PDN status: CONFIRMED CLEAN (PSM-0040, "all shapes connected") after
#   removing the add_pdn_ring call below (Test Fix 2, GH #104) -- verified
#   via a genuinely fresh -T OpenROAD.GeneratePDN run
#   (RUN_2026-07-22_18-16-30): 0 violations attributable to u_cpu anywhere
#   in the design.
#
# PDN topology:
#   met1  — followpins (horizontal standard-cell rails)
#   met4  — vertical stripes (pitch=200 um, width=3.1 um)
#   met5  — horizontal stripes (pitch=100 um, width=3.1 um)
#
# Run 8 GRT-0118 diagnosis (RUN_2026-07-19_11-13-47): congestion was NOT a
# global-capacity or macro-channel-gap issue (global GRT usage only 11%).
# It was 100% localized to the CPU macro's own footprint/top-edge
# pin-access region -- CPU's 565 pin RECTs were heavily concentrated on
# its TOP edge (256 of 565) in the pre-regen macro. Root cause: CPU macro
# pin skew, fixed by regenerating with a balanced pin_order.cfg
# (N=95/S=97/E=113/W=96). See memory/pd/run_state.md for the full
# GRT-0118 -> grid-alignment -> GRT_MACRO_EXTENSION resolution chain
# (Runs 8-13) -- GRT is now confirmed fully clean (0/0/0 overflow) and
# detailed routing confirmed 0 DRT violations on the real flow.
#
# GRT_MACRO_EXTENSION is set to 0 in config.json (was 2) -- confirmed via
# controlled A/B test on the post-grid-alignment-fix floorplan that this
# clears the last few GCell-row overflow units near the CPU's escape
# routes; a genuine routing-margin parameter, not a congestion mask.
###############################################################################

source $::env(SCRIPTS_DIR)/openroad/common/set_global_connections.tcl
set_global_connections

set secondary []
foreach vdd $::env(VDD_NETS) {
    if { $vdd != $::env(VDD_NET) } {
        lappend secondary $vdd
        set db_net [[ord::get_db_block] findNet $vdd]
        if { $db_net == "NULL" } {
            set net [odb::dbNet_create [ord::get_db_block] $vdd]
            $net setSpecial
            $net setSigType "POWER"
        }
    }
}

foreach gnd $::env(GND_NETS) {
    if { $gnd != $::env(GND_NET) } {
        set db_net [[ord::get_db_block] findNet $gnd]
        if { $db_net == "NULL" } {
            set net [odb::dbNet_create [ord::get_db_block] $gnd]
            $net setSpecial
            $net setSigType "GROUND"
        }
    }
}

set_voltage_domain -name CORE \
    -power $::env(VDD_NET) \
    -ground $::env(GND_NET) \
    -secondary_power $secondary

###############################################################################
# Standard-cell PDN grid
# met1 followpins -> met4 V-stripes -> met5 H-stripes
###############################################################################

define_pdn_grid \
    -name stdcell_grid \
    -starts_with POWER \
    -voltage_domain CORE \
    -pins "met5 met4"

# met5 horizontal stripes (coarsest — top-level H distribution)
add_pdn_stripe \
    -grid stdcell_grid \
    -layer met5 \
    -width 3.1 \
    -pitch $::env(FP_PDN_HPITCH) \
    -offset $::env(FP_PDN_HOFFSET) \
    -spacing 2.0 \
    -starts_with POWER -extend_to_core_ring

# met4 vertical stripes (primary distribution)
add_pdn_stripe \
    -grid stdcell_grid \
    -layer met4 \
    -width 3.1 \
    -pitch $::env(FP_PDN_VPITCH) \
    -offset $::env(FP_PDN_VOFFSET) \
    -spacing 2.0 \
    -starts_with POWER -extend_to_core_ring

# met1 followpins rails (standard-cell power rails)
add_pdn_stripe \
    -grid stdcell_grid \
    -layer met1 \
    -width $::env(FP_PDN_RAIL_WIDTH) \
    -followpins \
    -starts_with POWER

# Via connections: met1->met4 (OpenROAD generates via1/via2/via3 stack)
add_pdn_connect -grid stdcell_grid -layers "met1 met4"
# met4->met5 via4 stack
add_pdn_connect -grid stdcell_grid -layers "met4 met5"

###############################################################################
# Hard-macro PDN grid — CPU + SRAM, shared stock default-macro grid
#
# u_cpu uses standard VPWR/VGND power pins on met4.
# u_sram.u_sram_macro (sky130_sram_4kbyte_1rw1r_32x1024_8) uses OpenRAM's
# standard vccd1/vssd1 pins, present as PORT rects on BOTH met3 (top/
# bottom ring segments) and met4 (left/right ring segments) -- confirmed
# from the generated LEF.
#
# GH #104 Test Fix 2 (2026-07-22): REMOVED add_pdn_ring around macros.
# Root-cause comparison against the STOCK LibreLane pdn_cfg.tcl (which
# keeps CPU-alone's own PDN -- including its OWN internal SRAM hard
# macros from Stage-1 P&R -- fully clean, PSM-0040) shows the stock
# script's default macro grid does ONLY `define_pdn_grid -macro -default`
# + `add_pdn_connect -grid macro -layers "$V $H"` -- it never calls
# add_pdn_ring around macros at all. Matching that exactly here fixed
# u_cpu's connectivity completely (confirmed clean, 0 violations).
#
# GH #104 (2026-07-23/24): kept this SAME stock, ring-less, single shared
# "-macro -default" grid for the newly re-added SRAM macro rather than
# writing an instance-specific grid -- per the lesson from the failed
# composite macro, the stock path (proven on CPU + its internal OpenRAM
# SRAMs) has a real chance where hand-rolled instance-specific
# rings/straps did not.
#
# GH #104 FIX -- CONFIRMED (2026-07-24): the "met3 met4" connect
# (originally added alongside "met4 met5" so the SRAM's met3-layer PG pin
# rects would also be via-stitched, since the LEF exposes vccd1/vssd1 on
# BOTH met3 and met4) was REMOVED after Magic.DRC on the canary run
# (RUN_2026-07-24_05-27-21) found 32 met4.4a (Metal4 minimum area
# <0.24um^2) violations, ALL confined to the SRAM macro's footprint, ALL
# sitting exactly on its bottom-edge LEF-boundary row (y=0-0.38um
# macro-local), each a uniform 0.38x0.38um (0.1444 um^2) square -- classic
# via-landing-pad geometry generated by the met3->met4 via stitching
# itself, not scattered/random defects.
#
# CONFIRMED via a controlled experiment (run tag
# SRAM_MET3_REMOVED_EXPERIMENT, -T Magic.DRC, this exact connect line
# removed, everything else identical): PSM-0040 stays fully clean on
# BOTH VPWR and VGND with ZERO unconnected shapes -- the macro's met4 PG
# pin rects (left/right ring segments) alone are sufficient for the
# "met4 met5" connect to fully stitch it to the grid; the met3 path was
# never load-bearing for connectivity. Removing it is a strict
# improvement: eliminates 32 real undersized-metal geometry defects with
# zero connectivity cost. See memory/pd/run_state.md for the full
# experiment record and the sign-off run's Magic.DRC confirmation that
# met4.4a drops to 0.
###############################################################################

define_pdn_grid \
    -macro \
    -default \
    -name macro_grid \
    -starts_with POWER \
    -halo "10 10"

add_pdn_connect -grid macro_grid -layers "met4 met5"
