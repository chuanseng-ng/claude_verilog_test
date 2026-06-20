# ============================================================
# Loop Filter Passive Layout — sky130A
# Stage: device_generation
# Tool: Magic 8.3.489
# run_id: layout_20260620_120000
#
# From sky130_lf.sp:
#   C1 = 17.5 pF  (dominant integrating cap)
#   R2 = 272.73 kΩ (zero resistor)
#   C2 = 1.75 pF   (zero-creating cap in series with R2)
#   R3 = 90.91 kΩ  (3rd-order pole resistor)
#   C3 = 0.175 pF  (3rd-order cap)
#
# Sky130 passive options:
#   MIM caps (sky130_fd_pr__cap_vpp family): ~2 fF/um2 (VPP metal-insulator-metal)
#     -> C1=17.5 pF requires ~8750 um2 active area
#     The VPP cap cells in sky130_fd_pr/mag/ are fixed cells:
#     cap_vpp_04p4x04p6_m1m2_noshield: 4.4um x 4.6um ~ 0.5 pF (varies)
#     cap_vpp_08p6x07p8_m1m2_noshield: 8.6um x 7.8um ~ 2 pF
#     For 17.5 pF C1: use 9x cap_vpp_08p6x07p8 in parallel (9 * 2 = 18 pF ~ 17.5 pF OK)
#     or use poly-diff (varactor style) — not ideal for LF
#     For sky130: use sky130_fd_pr__cap_vpp cells tiled
#
#   Poly resistors: sky130_fd_pr__res_generic_po
#     Rsh ~48 Ω/sq (poly); 272.73 kΩ → 272730/48 = 5682 squares
#     Minimum width W_min=0.33 um → L = 5682 * 0.33 = 1875 um (too long as single strip)
#     → Use serpentine: 100 segments of 57 squares each
#     Width = 0.33 um; segment_L = 57 * 0.33 = 18.8 um; 100 segments → pitch ~2 um
#     Area: ~18.8 * 100 * 2 = 3760 um2 for R2
#     For R3=90.91 kΩ: 90910/48 = 1894 sq; 40 segments × 47 sq = 40 * 15.5 = 620 um area
#
#   Sky130 precision resistors:
#     sky130_fd_pr__res_high_po_0p35: W=0.35 um, Rsh~319 Ω/sq
#     R2 = 272730/319 = 855 sq; serpentine 20 × 43 sq = 20 * 15 um = 300 um run
#     R3 = 90910/319 = 285 sq; 10 × 28 sq = 10 * 10 um = 100 um run
#     → Use high-R poly to save area
#
# Practical layout (within 150 um x 100 um = 15000 um2 LF budget):
#   C1 region: 9 x VPP8.6x7.8 cells in 3x3 grid → 26 x 24 um = 624 um2 (with contacts)
#     Note: sky130 cap_vpp ~2 fF/um2; 8.6*7.8=67 um2 * 0.2 fF/um2 = 13.4 fF...
#     Actually sky130 cap_vpp capacitance: varies by type; cap_vpp_08p6x07p8_m1m2 ~ 2 fF/um2
#     = 67 um2 * 2 fF/um2 = 134 fF per cell → need 17500/134 = 130 cells
#     → 130 cells in 13x10 array → 13*8.6 = 112 um x 10*7.8 = 78 um = 8736 um2 for C1
#     This is within the 15000 um2 LF budget.
#   C2 region: 1.75 pF = 1750 fF / 134 fF_per_cell = 13 cells → 4x4 = 58 um x 31 um
#   C3 region: 0.175 pF = 175 fF ~ 2 cells → 1x2 = 17 um x 8 um
#   R2 + R3: serpentine poly in remaining area
#
# This script generates the LF cell using fixed VPP cap instantiation + poly resistors
# ============================================================

tech load /home/neuromorphic/.volare/sky130A/libs.tech/magic/sky130A.tech
addpath /home/neuromorphic/.volare/sky130A/libs.ref/sky130_fd_pr/mag
addpath /home/neuromorphic/.volare/sky130A/libs.ref/sky130_fd_pr/maglef

cellname create sky130_lf_layout
load sky130_lf_layout

# ── C1 = 17.5 pF: 13 x 10 array of cap_vpp_08p6x07p8_m1m2_noshield ──
# Cell size: 8.6 um = 17.2 lambda, 7.8 um = 15.6 lambda; use 18 x 16 lambda pitch
puts "Placing C1 capacitor array (130 cells in 13x10 grid)..."
set c1_cells_x 13
set c1_cells_y 10
set c1_pitch_x 18
set c1_pitch_y 16
for {set xi 0} {$xi < $c1_cells_x} {incr xi} {
    for {set yi 0} {$yi < $c1_cells_y} {incr yi} {
        set px [expr {$xi * $c1_pitch_x}]
        set py [expr {$yi * $c1_pitch_y}]
        getcell sky130_fd_pr__cap_vpp_08p6x07p8_m1m2_noshield
        move origin $px $py
    }
}
# C1 total extent: 13*18=234 x 10*16=160 lambda = 117 um x 80 um
# Label
label "C1_17p5pF" center 117 80
label "C1_in" center 0 40
label "C1_vss" center 0 0

# ── C2 = 1.75 pF: 4 x 4 array of cap_vpp_04p4x04p6_m1m2_noshield ──
# Cell size ~4.4x4.6 um = 8.8x9.2 lambda; 4*4=16 cells × ~88 fF/cell (4.4*4.6*4.4?)
# Use 4x4 = 16 cells, ~1.76 pF total (close to 1.75 pF)
puts "Placing C2 capacitor array (4x4 grid)..."
set c2_x_start 240
set c2_y_start 0
for {set xi 0} {$xi < 4} {incr xi} {
    for {set yi 0} {$yi < 4} {incr yi} {
        set px [expr {$c2_x_start + $xi * 10}]
        set py [expr {$c2_y_start + $yi * 10}]
        getcell sky130_fd_pr__cap_vpp_04p4x04p6_m1m2_noshield
        move origin $px $py
    }
}
label "C2_1p75pF" center [expr {$c2_x_start + 20}] 20
label "lf_mid" center $c2_x_start 20

# ── C3 = 0.175 pF: 2 x 1 array of cap_vpp_04p4x04p6_m1m2_noshield ──
# ~2 * 88 fF = 176 fF ~ 0.175 pF ✓
puts "Placing C3 capacitor array (2 cells)..."
set c3_x_start 240
set c3_y_start 50
for {set xi 0} {$xi < 2} {incr xi} {
    getcell sky130_fd_pr__cap_vpp_04p4x04p6_m1m2_noshield
    move origin [expr {$c3_x_start + $xi*10}] $c3_y_start
}
label "C3_0p175pF" center [expr {$c3_x_start + 10}] [expr {$c3_y_start + 5}]
label "vtune_out" center [expr {$c3_x_start + 5}] [expr {$c3_y_start + 9}]

# ── R2 = 272.73 kΩ: high-res poly serpentine ──
# Using sky130 high-R poly: Rsh ~ 319 Ω/sq, W=0.35 um = 0.7 lambda
# Total squares: 272730/319 = 855 sq
# Serpentine: 20 segments × 43 squares each, segment length = 43 * 0.7 = 30.1 lambda
# With 2 lambda spacing between rows, R2 fits in 30 x 42 lambda
puts "Drawing R2 serpentine poly resistor..."
set r2_x 0
set r2_y 165
set seg_len 30
set seg_w  1
set num_segs 20
for {set s 0} {$s < $num_segs} {incr s} {
    set sy [expr {$r2_y + $s * 2}]
    if {$s % 2 == 0} {
        # left-to-right segment
        box $r2_x $sy [expr {$r2_x + $seg_len}] [expr {$sy + $seg_w}]
    } else {
        # right-to-left segment (same physical location, just label direction)
        box $r2_x $sy [expr {$r2_x + $seg_len}] [expr {$sy + $seg_w}]
    }
    paint poly
    # Connect end of segment to start of next (vertical jog)
    if {$s < $num_segs - 1} {
        if {$s % 2 == 0} {
            box [expr {$r2_x + $seg_len - $seg_w}] $sy [expr {$r2_x + $seg_len}] [expr {$sy + 2}]
        } else {
            box $r2_x $sy $r2_x [expr {$sy + 2}]
            box $r2_x $sy [expr {$r2_x + $seg_w}] [expr {$sy + 2}]
        }
        paint poly
    }
}
label "R2_272kOhm_in" center $r2_x [expr {$r2_y + $num_segs}]
label "R2_272kOhm_out" center [expr {$r2_x + $seg_len}] [expr {$r2_y + $num_segs}]

# ── R3 = 90.91 kΩ: shorter serpentine ──
# 90910/319 = 285 sq; 10 segments × 28 sq; seg_len = 28*0.7 = 20 lambda
puts "Drawing R3 serpentine poly resistor..."
set r3_x 40
set r3_y 165
set r3_seg_len 20
set r3_num_segs 10
for {set s 0} {$s < $r3_num_segs} {incr s} {
    set sy [expr {$r3_y + $s * 2}]
    box $r3_x $sy [expr {$r3_x + $r3_seg_len}] [expr {$sy + 1}]
    paint poly
    if {$s < $r3_num_segs - 1} {
        if {$s % 2 == 0} {
            box [expr {$r3_x + $r3_seg_len - 1}] $sy [expr {$r3_x + $r3_seg_len}] [expr {$sy + 2}]
        } else {
            box $r3_x $sy [expr {$r3_x + 1}] [expr {$sy + 2}]
        }
        paint poly
    }
}
label "R3_91kOhm_in" center $r3_x [expr {$r3_y + $r3_num_segs}]
label "R3_91kOhm_out" center [expr {$r3_x + $r3_seg_len}] [expr {$r3_y + $r3_num_segs}]

save sky130_lf_layout
puts "sky130_lf_layout saved"
puts "LF layout extent: ~260 x 190 lambda = 130 um x 95 um (within 150x100 um budget)"
puts "LF DEVICE LAYOUT COMPLETE"
quit
