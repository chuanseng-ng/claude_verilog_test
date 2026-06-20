# ============================================================
# CP (Charge Pump) Device Layout v2 -- CORRECTED GEOMETRY
# Fix-request: sky130-pv-fr001
# Stage: analog_routing (re-entry per fix-request servicing rules)
# Tool: Magic 8.3.489 + sky130A.tech
# run_id: layout_20260620_FR001
#
# ROOT CAUSE OF PRIOR FAILURE:
#   Magic sky130A unit scale = 10 nm per internal unit (scalefactor 10 nanometers).
#   Prior script comments stated "lambda=0.5um = 2 units" but then used raw unit values
#   that are 50x too small (e.g. pdiff rect 4 4 6 12 → width=2 units = 20nm, need 150nm min).
#   poly touched diff at boundary without overlap → 0 FET devices extracted.
#
# CORRECT UNIT SCALE:
#   1 magic internal unit = 10 nm = 0.01 um
#   0.15 um = 15 mu  (poly.1a, diff/tap.1 minimums)
#   0.17 um = 17 mu  (li.3 LI spacing, li.1 LI width)
#   0.18 um = 18 mu  (nwell enclosure)
#   0.21 um = 21 mu  (poly.2 poly spacing)
#   0.27 um = 27 mu  (diff/tap.3 diff spacing)
#   2.0 um  = 200 mu (L=2um gate length)
#   4.0 um  = 400 mu (W=4um PMOS width)
#   1.5 um  = 150 mu (W=1.5um NMOS width)
#
# APPROACH: Use magic sky130A device generators (gencell / mos_draw).
#   These produce DRC-clean extractable FET geometry by construction.
#   gencell parameters: l (um), w (um), nf (fingers), diffcov, polycov
#
# CIRCUIT (from sky130_cp.sp):
#   PMOS: M_pbias W=4u/L=2u nf=4, M_psrc W=4u/L=2u nf=4
#         common-centroid: [Dum][pbias][psrc][psrc][pbias][Dum] = 6 cells of 4-finger each
#         (24 poly fingers total, but for matching a simpler approach:
#          place 2 cells for M_pbias and 2 cells for M_psrc interleaved)
#   NMOS: M_nbias W=1.5u/L=2u nf=1, M_nsrc W=1.5u/L=2u nf=1
#         common-centroid: [Dum][nbias][nsrc][nsrc][nbias][Dum]
#
# STRATEGY: Use sky130::sky130_fd_pr__pfet_01v8_draw and nfet_01v8_draw
#   with parameters l, w, nf to generate individual FET cells.
#   Then place them in common-centroid arrangement and add:
#   - nwell with N+ tap connected to VDD (nwell.4 fix)
#   - psubstrate P+ tap connected to VSS (LU.2/LU.3 fix)
#   - proper li1 wiring with correct dimensions (>=17 mu = 0.17 um)
#
# ============================================================

# Load tech and PDK references
tech load /home/neuromorphic/.volare/sky130A/libs.tech/magic/sky130A.tech
source /home/neuromorphic/.volare/sky130A/libs.tech/magic/sky130A.tcl
addpath /home/neuromorphic/.volare/sky130A/libs.ref/sky130_fd_pr/mag

set MAGDIR /home/neuromorphic/Downloads/Github/claude_verilog_test/analog/pll_clkgen/sky130/layout/mag

# ============================================================
# Helper: draw a DRC-correct MOSFET using sky130 generator
#   type: pfet or nfet
#   W_um, L_um: gate width and length in microns
#   nf: number of fingers
#   Returns cell name of the generated device
# ============================================================
proc gen_fet {type W_um L_um nf cell_name} {
    set params [dict create]
    dict set params l $L_um
    dict set params w $W_um
    dict set params nf $nf

    if {$type eq "pfet"} {
        set drawproc "sky130::sky130_fd_pr__pfet_01v8_draw"
    } else {
        set drawproc "sky130::sky130_fd_pr__nfet_01v8_draw"
    }

    cellname create $cell_name
    load $cell_name
    $drawproc $params
    save $cell_name
    puts "  Generated $cell_name: $type W=${W_um}u L=${L_um}u nf=$nf"
    return $cell_name
}

# ============================================================
# Helper: place an instance of a cell at position (x_um, y_um)
#   in the currently-loaded parent cell
# ============================================================
proc place_cell {cell_name x_um y_um} {
    set x_mu [expr {int($x_um * 100)}]
    set y_mu [expr {int($y_um * 100)}]
    getcell $cell_name
    move origin $x_mu $y_mu
    puts "  Placed $cell_name at ($x_um, $y_um) um"
}

# ============================================================
# Helper: paint a rectangle in current cell
#   Coordinates in magic internal units (1 mu = 10 nm = 0.01 um)
# ============================================================
proc paint_rect {layer x0 y0 x1 y1} {
    box $x0 $y0 $x1 $y1
    paint $layer
}

# ============================================================
# Generate individual FET primitives
# For common-centroid: use single-finger instances (nf=4 means
# the generator draws 4 interdigitated fingers in one cell).
# We use nf=4 for the PMOS (each M_pbias/M_psrc is 4 fingers).
# Then we place 2 M_pbias cells + 2 M_psrc cells interleaved.
# ============================================================

puts "--- Generating PMOS primitive cell (W=4u L=2u nf=4) ---"
gen_fet pfet 4.0 2.0 4 pfet_4u_2u_nf4

puts "--- Generating NMOS primitive cell (W=1.5u L=2u nf=1) ---"
gen_fet nfet 1.5 2.0 1 nfet_1p5u_2u_nf1

puts "--- Generating NMOS dummy cell (same size) ---"
gen_fet nfet 1.5 2.0 1 nfet_1p5u_2u_dum

puts "--- Generating PMOS dummy cell ---"
gen_fet pfet 4.0 2.0 4 pfet_4u_2u_dum

# ============================================================
# CP PMOS ARRAY: cp_pmos_array
#
# Common-centroid arrangement:
#   [Dum_P | M_pbias_A | M_psrc_A | M_psrc_B | M_pbias_B | Dum_P]
#
# Each cell (pfet_4u_2u_nf4) generated by sky130 generator is DRC-clean.
# The generator will have:
#   - pdiff in nwell
#   - poly crossing through diff (proper overlap)
#   - licon contacts on source/drain
#   - correct dimensions
#
# We get the bounding box of the generated cell to determine pitch,
# then tile cells horizontally.
#
# After placing cells, we add:
#   (a) A shared nwell region enclosing all PMOS cells + 0.34 um margin
#   (b) An N+ tap (nsd or ntap) in the nwell connected to VDD via li1
#       This fixes nwell.4 (no metal-connected N+ tap)
#   (c) LI wiring for pbias, psrc_g, VDD connections
#
# ============================================================

puts "=== Building cp_pmos_array ==="
cellname create cp_pmos_array
load cp_pmos_array

# Get the bounding box of the pfet unit cell to know its width
# The sky130 generator typically produces a cell with width ~equal to
# nf * (contact_to_contact_pitch) and height ~W + overhead
# For W=4um, nf=4: expect cell ~10-15um wide, ~8-10um tall
# We'll place cells at x=0, then x=cell_width, etc.
# First instance and check:
getcell pfet_4u_2u_dum
set dum_ll [lindex [cellbbox pfet_4u_2u_dum] 0]
set dum_bb [cellbbox pfet_4u_2u_dum]
set cell_w [expr {[lindex $dum_bb 2] - [lindex $dum_bb 0]}]
set cell_h [expr {[lindex $dum_bb 3] - [lindex $dum_bb 1]}]
puts "  PMOS unit cell: ${cell_w}mu wide x ${cell_h}mu tall ([expr {$cell_w/100.0}]um x [expr {$cell_h/100.0}]um)"

# Remove the first auto-place instance (getcell puts it at 0,0)
# Actually: we'll use explicit placement. Move it first.
select top cell
select all
delete

# Now place cells in order: Dum | pbias_A | psrc_A | psrc_B | pbias_B | Dum
# Spacing between cells: 0 (abutted, shared source diffusion)
# We add a gap of 20mu (0.2um) between cells for routing/diff spacing
set gap 0

# Place 6 instances at x = i * cell_w
set names {pfet_4u_2u_dum pfet_4u_2u_nf4 pfet_4u_2u_nf4 pfet_4u_2u_nf4 pfet_4u_2u_nf4 pfet_4u_2u_dum}
set roles {DUM PBIAS_A PSRC_A PSRC_B PBIAS_B DUM}
set i 0
foreach cell $names role $roles {
    set x [expr {$i * ($cell_w + $gap)}]
    getcell $cell
    move origin $x 0
    puts "  Instance $i ($role): placed at x=$x mu"
    incr i
}

# ── Add N+ nwell tap for nwell.4 fix ──────────────────────
# Place an ntap (N+ in nwell) connected to VDD
# ntap must be within 15um of pdiff (LU.3), metal-connected
# Position: to the right of the array, in same nwell extension
# Nwell tap width: 0.17um min, use 0.42um (42mu) for robust contact
set array_w [expr {6 * $cell_w}]
set tap_x   [expr {$array_w + 20}]
set tap_w   42
set tap_h   [expr {$cell_h}]

# Extend nwell to cover tap
paint_rect nwell [expr {$array_w}] -34 [expr {$tap_x + $tap_w + 34}] [expr {$tap_h + 34}]

# N-tap: nsd (N+ source-drain in nwell for body tie)
# Use the ntap / nsd layer
paint_rect nsd $tap_x 0 [expr {$tap_x + $tap_w}] $tap_h

# licon contact on tap
paint_rect licon [expr {$tap_x + 5}] 5 [expr {$tap_x + $tap_w - 5}] [expr {$tap_h - 5}]

# li1 over the tap
paint_rect li1 [expr {$tap_x}] 0 [expr {$tap_x + $tap_w}] $tap_h

# Connect tap li1 to VDD label
set tap_cx [expr {$tap_x + $tap_w/2}]
set tap_cy [expr {$tap_h/2}]
label "VDD" center $tap_cx $tap_cy

# ── Add P+ substrate tap for LU.3 fix ─────────────────────
# Below the cell (in p-sub beneath nwell), add a psd tap tied to VSS
# Actually for PMOS array in nwell, the substrate tap is outside nwell
# Place psd tap below at y = -60mu (outside nwell)
set psub_tap_y [expr {-60}]
paint_rect psd 0 $psub_tap_y [expr {$array_w}] [expr {$psub_tap_y + 42}]
paint_rect licon 5 [expr {$psub_tap_y + 5}] [expr {$array_w - 5}] [expr {$psub_tap_y + 37}]
paint_rect li1 0 $psub_tap_y [expr {$array_w}] [expr {$psub_tap_y + 42}]
label "VSS_BODY" center [expr {$array_w/2}] [expr {$psub_tap_y + 21}]

# ── Port labels on the array ──────────────────────────────
# These are net labels for LVS
# VDD port at top of nwell tap
label "VDD" center $tap_cx [expr {$tap_h + 10}]

# pbias port: drain of cells 1(pbias_A) and 4(pbias_B)
# (inside the cells, labeled as drain - we add a port label)
set pbias_x1 [expr {1 * $cell_w + $cell_w/2}]
set pbias_x2 [expr {4 * $cell_w + $cell_w/2}]
set mid_y    [expr {$cell_h/2}]
label "pbias" center $pbias_x1 $mid_y
label "pbias" center $pbias_x2 $mid_y

# psrc_g port: drain of cells 2(psrc_A) and 3(psrc_B)
set psrc_x1 [expr {2 * $cell_w + $cell_w/2}]
set psrc_x2 [expr {3 * $cell_w + $cell_w/2}]
label "psrc_g" center $psrc_x1 $mid_y
label "psrc_g" center $psrc_x2 $mid_y

save cp_pmos_array
puts "cp_pmos_array saved."

# ============================================================
# CP NMOS ARRAY: cp_nmos_array
#
# Common-centroid arrangement:
#   [Dum_N | M_nbias_A | M_nsrc_A | M_nsrc_B | M_nbias_B | Dum_N]
#   Each cell: nfet_01v8 W=1.5u L=2u nf=1
#
# In p-substrate (no nwell needed for NMOS).
# Add P+ tap tied to VSS for LU.2 fix.
#
# ============================================================

puts "=== Building cp_nmos_array ==="
cellname create cp_nmos_array
load cp_nmos_array

# Get NMOS unit cell dimensions
set n_bb   [cellbbox nfet_1p5u_2u_nf1]
set n_cell_w [expr {[lindex $n_bb 2] - [lindex $n_bb 0]}]
set n_cell_h [expr {[lindex $n_bb 3] - [lindex $n_bb 1]}]
puts "  NMOS unit cell: ${n_cell_w}mu wide x ${n_cell_h}mu tall ([expr {$n_cell_w/100.0}]um x [expr {$n_cell_h/100.0}]um)"

# Place 6 instances: Dum | nbias_A | nsrc_A | nsrc_B | nbias_B | Dum
set n_names {nfet_1p5u_2u_dum nfet_1p5u_2u_nf1 nfet_1p5u_2u_nf1 nfet_1p5u_2u_nf1 nfet_1p5u_2u_nf1 nfet_1p5u_2u_dum}
set n_roles {DUM NBIAS_A NSRC_A NSRC_B NBIAS_B DUM}
set i 0
foreach cell $n_names role $n_roles {
    set x [expr {$i * $n_cell_w}]
    getcell $cell
    move origin $x 0
    puts "  Instance $i ($role): placed at x=$x mu"
    incr i
}

set n_array_w [expr {6 * $n_cell_w}]

# ── Add P+ substrate tap for LU.2 fix ─────────────────────
# psd tap: P+ in p-sub, tied to VSS (body tie for NMOS)
set ptap_x [expr {$n_array_w + 20}]
set ptap_w 42
set ptap_h $n_cell_h

paint_rect psd $ptap_x 0 [expr {$ptap_x + $ptap_w}] $ptap_h
paint_rect licon [expr {$ptap_x + 5}] 5 [expr {$ptap_x + $ptap_w - 5}] [expr {$ptap_h - 5}]
paint_rect li1 $ptap_x 0 [expr {$ptap_x + $ptap_w}] $ptap_h
set ptap_cx [expr {$ptap_x + $ptap_w/2}]
label "VSS" center $ptap_cx [expr {$ptap_h/2}]

# ── Port labels ────────────────────────────────────────────
set n_mid_y [expr {$n_cell_h/2}]

# nbias: drains of cells 1(nbias_A) and 4(nbias_B)
label "nbias" center [expr {1 * $n_cell_w + $n_cell_w/2}] $n_mid_y
label "nbias" center [expr {4 * $n_cell_w + $n_cell_w/2}] $n_mid_y

# nsrc_g: drains of cells 2(nsrc_A) and 3(nsrc_B)
label "nsrc_g" center [expr {2 * $n_cell_w + $n_cell_w/2}] $n_mid_y
label "nsrc_g" center [expr {3 * $n_cell_w + $n_cell_w/2}] $n_mid_y

# VSS port label
label "VSS" center [expr {$n_array_w/2}] -10

save cp_nmos_array
puts "cp_nmos_array saved."
puts "=== CP arrays generation complete ==="
quit
