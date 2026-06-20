# ============================================================
# PLL_CLKGEN Sky130 — Floorplan Script
# Stage: layout_floorplan
# Tool: Magic 8.3.489 + sky130A tech
# Orchestrator: custom-layout-orchestrator
# run_id: layout_20260620_120000
#
# Floorplan (all coordinates in magic internal units = lambda = 0.5 um):
#   Total target: 300 um x 140 um = 42,000 um2
#   Magic units: 600 x 280 lambda
#
# Block regions (X_start Y_start X_end Y_end in um):
#   BIAS:    0,0  ->  40,100   (4000 um2)
#   CP:      40,0 ->  70,100   (3000 um2)
#   LF:      70,0 -> 220,100   (15000 um2) — passive region, large caps
#   VCO:    220,0 -> 300,100   (8000 um2)  — square-ish for ring symmetry
#   PFD:     0,100-> 40,150    (2000 um2)
#   FBDIV:   40,100->110,170   (4900 um2)
#   POSTDIV:110,100->170,160   (3600 um2)
#
# Symmetry axes:
#   CP mirror axis: vertical at x=55 um (centre of CP block)
#   VCO ring axis:  vertical at x=260 um, horizontal at y=50 um (centre of VCO)
#
# Sensitive net channels:
#   Vtune (high-Z): shielded horizontal track at y=95..105 um,
#         from LF out (x=220 um) to VCO in (x=220 um), metal2 with gnd shields
#   Ibias (bias):   narrow channel at x=35..45 um from BIAS to CP/VCO
#   UP/DN signals:  routed metal1 from PFD to CP, direct (low-Z, less critical)
# ============================================================

tech load /home/neuromorphic/.volare/sky130A/libs.tech/magic/sky130A.tech
addpath /home/neuromorphic/.volare/sky130A/libs.ref/sky130_fd_pr/mag

# Create the top-level floorplan cell
cellname create pll_clkgen_fp
load pll_clkgen_fp

# ── Paint block boundary markers using the comment/frame layer ──
# In magic, use 'comment' or 'border' paint; or use metal/poly as placeholder
# We annotate block regions with met1 boundary boxes (will be replaced by real cells)
# Coordinates: magic uses lambda units; 1 lambda = 0.5 um for sky130A
# So 1 um = 2 lambda units

# Helper: draw a label at the center of a region
proc label_block {name x_um y_um} {
    set x [expr {int($x_um * 2)}]
    set y [expr {int($y_um * 2)}]
    label $name center $x $y
}

# ── BIAS block region (0..40 x 0..100 um) ──
box 0 0 [expr {40*2}] [expr {100*2}]
paint comment
label_block "BIAS" 20 50

# ── CP block region (40..70 x 0..100 um) ──
box [expr {40*2}] 0 [expr {70*2}] [expr {100*2}]
paint comment
label_block "CP" 55 50

# ── LF block region (70..220 x 0..100 um) ──
box [expr {70*2}] 0 [expr {220*2}] [expr {100*2}]
paint comment
label_block "LF" 145 50

# ── VCO block region (220..300 x 0..100 um) ──
box [expr {220*2}] 0 [expr {300*2}] [expr {100*2}]
paint comment
label_block "VCO" 260 50

# ── PFD block region (0..40 x 100..150 um) ──
box 0 [expr {100*2}] [expr {40*2}] [expr {150*2}]
paint comment
label_block "PFD" 20 125

# ── FBDIV block region (40..110 x 100..170 um) ──
box [expr {40*2}] [expr {100*2}] [expr {110*2}] [expr {170*2}]
paint comment
label_block "FBDIV" 75 135

# ── POSTDIV block region (110..170 x 100..160 um) ──
box [expr {110*2}] [expr {100*2}] [expr {170*2}] [expr {160*2}]
paint comment
label_block "POSTDIV" 140 130

# ── Symmetry axis markers: CP vertical axis at x=55 um ──
box [expr {55*2-1}] 0 [expr {55*2+1}] [expr {100*2}]
paint comment
label "CP_SYM_AXIS" center [expr {55*2}] [expr {50*2}]

# ── Symmetry axis: VCO centre x=260, y=50 um ──
box [expr {260*2-1}] 0 [expr {260*2+1}] [expr {100*2}]
paint comment
label "VCO_SYM_AXIS_V" center [expr {260*2}] [expr {25*2}]
box [expr {220*2}] [expr {50*2-1}] [expr {300*2}] [expr {50*2+1}]
paint comment
label "VCO_SYM_AXIS_H" center [expr {260*2}] [expr {50*2}]

# ── Vtune shielded channel: y=95..105 um, x=145..230 um ──
# Reserve with comment paint; actual shield will be met2 gnd wires
box [expr {145*2}] [expr {95*2}] [expr {230*2}] [expr {105*2}]
paint comment
label "VTUNE_CHANNEL" center [expr {187*2}] [expr {100*2}]

# ── Ibias channel: x=38..42 um, y=0..100 um ──
box [expr {38*2}] 0 [expr {42*2}] [expr {100*2}]
paint comment
label "IBIAS_CHANNEL" center [expr {40*2}] [expr {50*2}]

# Save floorplan
save pll_clkgen_fp
puts "Floorplan saved: pll_clkgen_fp.mag"
puts "Total floorplan: 300 x 170 um = 51000 um2 (target 50000 um2 with guard-ring reserve)"
puts "FLOORPLAN COMPLETE"
quit
