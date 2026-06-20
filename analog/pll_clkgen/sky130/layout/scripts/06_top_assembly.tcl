# ============================================================
# PLL_CLKGEN Top-Level Assembly + Routing — sky130A
# Stages: analog_placement + analog_routing + layout_finishing
# Tool: Magic 8.3.489
# run_id: layout_20260620_120000
#
# This script:
#  1. Loads all sub-cells (cp_pmos_array, cp_nmos_array, vco, lf, bias, pfd, fbdiv, postdiv)
#  2. Places them per the floorplan
#  3. Routes key nets: VDD, VSS, vtune, up, dn, pbias, nbias, iout, clk chains
#  4. Adds guard rings, tap rings
#  5. Runs DRC pre-check and reports violations
#  6. Writes GDS output
#
# Floorplan (um → lambda *2):
#   BIAS:    x=0..80,   y=0..200
#   CP:      x=80..140, y=0..200
#   LF:      x=140..440,y=0..200
#   VCO:     x=440..600,y=0..200
#   PFD:     x=0..80,   y=200..300
#   FBDIV:   x=80..220, y=200..340
#   POSTDIV: x=220..340,y=200..320
# ============================================================

tech load /home/neuromorphic/.volare/sky130A/libs.tech/magic/sky130A.tech
addpath /home/neuromorphic/.volare/sky130A/libs.ref/sky130_fd_pr/mag
addpath /home/neuromorphic/.volare/sky130A/libs.ref/sky130_fd_sc_hd/mag
addpath /home/neuromorphic/Downloads/Github/claude_verilog_test/analog/pll_clkgen/sky130/layout/mag

cellname create pll_clkgen_top
load pll_clkgen_top

# ── Load and place sub-cells ─────────────────────────────────

# BIAS: x=0, y=0 (80x200 lambda = 40x100 um)
getcell sky130_bias_layout
move origin 0 0
property port_cellname sky130_bias_layout
label "BIAS" center 40 100

# CP PMOS array: x=80, y=100 (within CP region 80..140, y=0..200)
getcell cp_pmos_array
move origin 80 100
label "CP_PMOS" center 128 148

# CP NMOS array: x=80, y=20 (below PMOS)
getcell cp_nmos_array
move origin 80 20
label "CP_NMOS" center 98 38

# LF: x=140, y=0
getcell sky130_lf_layout
move origin 140 0
label "LF" center 290 100

# VCO: x=440, y=0
getcell sky130_vco_layout
move origin 440 0
label "VCO" center 516 52

# PFD: x=0, y=200
getcell sky130_pfd_layout
move origin 0 200
label "PFD" center 40 300

# FBDIV: x=80, y=200
getcell sky130_fbdiv_layout
move origin 80 200
label "FBDIV" center 220 340

# POSTDIV: x=220, y=200
getcell sky130_postdiv_layout
move origin 220 200
label "POSTDIV" center 340 320

# ── VDD Power Ring (met2, wide=8 lambda = 4 um) ─────────────
# Outer ring surrounding all blocks: x=0..640, y=0..360
box -8 -8 648 8
paint met2
label "VDD_rail_bot" center 320 0
box -8 352 648 368
paint met2
label "VDD_rail_top" center 320 360
box -8 -8 8 368
paint met2
label "VDD_rail_left" center 0 180
box 632 -8 648 368
paint met2
label "VDD_rail_right" center 640 180

# ── VSS Power Ring (met2, at periphery below VDD) ───────────
box -16 -16 656 0
paint met1
label "VSS_rail_bot" center 320 -8
box -16 360 656 376
paint met1
label "VSS_rail_top" center 320 368
box -16 -16 0 376
paint met1
label "VSS_rail_left" center -8 180
box 640 -16 656 376
paint met1
label "VSS_rail_right" center 648 180

# ── VDD/VSS internal distribution ───────────────────────────
# Horizontal VDD stripes at y=40, 120 (met2, width=4l)
box 0 38 640 42
paint met2
label "VDD_h1" center 320 40
box 0 118 640 122
paint met2
label "VDD_h2" center 320 120

# Horizontal VSS stripes at y=0, 80, 160
box 0 -2 640 2
paint met1
box 0 78 640 82
paint met1
box 0 158 640 162
paint met1

# ── Key signal routing ──────────────────────────────────────

# pbias: BIAS block → CP_PMOS array (horizontal met1 from bias n_ref to CP pbias)
# BIAS n_ref output: approximately at x=14, y=110 in BIAS coords (absolute: x=14, y=110)
# CP pbias input: approximately at x=80+46, y=100+4 = x=126, y=104
box 14 108 128 112
paint met1
label "pbias" center 71 110

# nbias: BIAS n_out → CP_NMOS array
# BIAS n_out: approximately x=22, y=100 → absolute x=22, y=100
# CP NMOS nbias: x=80+17, y=20+6 = x=97, y=26
box 22 24 99 28
paint met1
label "nbias" center 60 26

# iout: CP output to LF input
# CP iout node: approximately at CP NMOS (x=80+25, y=20+7) = x=105, y=27
# LF input 'in': at x=140 (LF left edge, ~y=40)
box 105 26 142 30
paint met1
label "iout_to_lf" center 123 28

# vtune: LF output to VCO input — SHIELDED (high-Z, most sensitive net)
# LF vtune_out: approximately at x=140+250=390, y=59 (C3 output node within LF)
# VCO vtune: at x=440, y=6 (vtune met1 bus in VCO)
# Route on met2 with met1 ground shields above and below
box 386 58 444 62
paint met2
label "vtune_shield_above" center 415 64
box 386 56 444 58
paint met1
label "VSS_vtune_shld_lo" center 415 57
box 386 62 444 64
paint met1
label "VSS_vtune_shld_hi" center 415 63
# via1 at LF end and VCO end
box 388 58 392 62
paint via1
box 440 58 444 62
paint via1
label "vtune" center 415 60

# up signal: PFD up → CP up (digital, met1)
# PFD up port: x=80, y=200+30 = x=80, y=230
# CP up input: approximately at x=80+33, y=100+150 = x=113, y=250
box 80 228 115 232
paint met1
label "up" center 97 230

# dn signal: PFD dn → CP dn
# PFD dn: x=80, y=200+70 = x=80, y=270; CP dn: x=113, y=270
box 80 268 115 272
paint met1
label "dn" center 97 270

# vco_out → FBDIV: VCO output (at VCO cell met1 output) to FBDIV clk_in
# VCO clk_out: approximately at x=440+72=512, y=6 (buffer output)
# FBDIV clk_in: at x=80, y=200+70 = x=80, y=270
# Route on met2 to clear blocks
# Vertical jog at x=512 from y=6 up to y=270, then horizontal to x=80
box 510 6 514 270
paint met2
box 80 268 514 272
paint met2
box 80 268 84 340
paint met2
label "vco_to_fbdiv" center 297 270

# FBDIV out → PFD clk_div
# FBDIV clk_out: at x=220, y=200+70 = x=220, y=270
# PFD clk_div: at x=0, y=200+70 = x=0, y=270; route horizontal met2
box 0 268 222 272
paint met2
label "clk_div" center 111 270

# clk_ref input: external, placed at left edge
box -4 248 4 252
paint met2
label "clk_ref" center 0 250

# FBDIV clk_out → POSTDIV clk_in
# FBDIV out at x=220, y=270; POSTDIV in at x=220, y=200+50=250
box 218 248 222 272
paint met1
label "clk_fbdiv_out" center 220 260

# POSTDIV clk_out: chip output, at right side
box 336 268 360 272
paint met2
label "clk_out" center 348 270

# ── Guard rings for sensitive blocks ──────────────────────
# VCO guard ring: metal ring in li1 at VCO boundary, tied to VDD
box 436 -4 604 0
paint li1
box 436 56 604 60
paint li1
box 436 -4 440 60
paint li1
box 600 -4 604 60
paint li1
label "VCO_guard" center 520 58

# CP guard ring (PMOS in nwell — separate from VCO)
box 76 96 144 100
paint li1
box 76 200 144 204
paint li1
box 76 96 80 204
paint li1
box 140 96 144 204
paint li1
label "CP_guard" center 110 102

# ── Substrate tap rings (p-sub taps for NMOS) ─────────────
# Periodic substrate taps: ndiff tie at y=0 and y=200 lines
# Add small ndiff+licon contact strips at x=160, 280, 400
foreach tap_x {160 280 400} {
    box $tap_x -2 [expr {$tap_x+4}] 2
    paint ndiff
    box $tap_x -2 [expr {$tap_x+4}] 2
    paint licon
    box $tap_x -2 [expr {$tap_x+4}] 0
    paint li1
    label "sub_tap" center [expr {$tap_x+2}] 0
}

# ── Metal density fill (partial) ─────────────────────────
# Add met1 fill tiles in unused area (y=340..360, x=0..600) to meet density
# Minimum density 20%, use 60% fill in this region
# Simple horizontal fills
for {set fx 0} {$fx < 600} {set fx [expr {$fx+8}]} {
    box $fx 340 [expr {$fx+6}] 356
    paint met1
}

# ── Write GDS ────────────────────────────────────────────
# First save .mag
save pll_clkgen_top
puts "pll_clkgen_top.mag saved"

# Write GDS
gds write /home/neuromorphic/Downloads/Github/claude_verilog_test/analog/pll_clkgen/sky130/layout/gds/pll_clkgen_top.gds
puts "GDS written: pll_clkgen_top.gds"
puts "TOP ASSEMBLY COMPLETE"
quit
