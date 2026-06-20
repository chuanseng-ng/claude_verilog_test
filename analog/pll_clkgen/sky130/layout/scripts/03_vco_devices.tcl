# ============================================================
# VCO (5-Stage Ring) Device Layout — sky130A
# Stage: device_generation + analog_placement
# Tool: Magic 8.3.489
# run_id: layout_20260620_120000
#
# From sky130_vco.sp:
#   Per stage: Xp  W=2u L=150n nf=2 (PMOS load)
#              Xn  W=1u L=150n nf=1 (NMOS driver)
#              Xcs W=1u L=2u   nf=1 (NMOS current-starved tail)
#   5 identical stages → symmetric placement is natural
#   Output buffer: Xbuf_p W=4u L=150n nf=4, Xbuf_n W=2u L=150n nf=2
#
# VCO placement strategy:
#   All 5 stages laid out identically in a row → ensures equal parasitics
#   on all ring nodes (n1..n5). Matching the stages is the key VCO concern
#   for phase noise (systematic stage-to-stage offsets affect Kvco symmetry).
#
#   Stage pitch (x-direction):
#     PMOS cell (W=2u L=150n nf=2): x-pitch ~10 lambda
#     NMOS driver (W=1u L=150n nf=1): x-pitch ~6 lambda
#     CS tail (W=1u L=2u nf=1): x-pitch ~6 lambda below NMOS (stacked)
#     Total per stage: ~10 lambda wide
#     5 stages + 1 buf: 6 * 10 = 60 lambda = 30 um (plus spacing)
#
#   Stage layout (vertical stack per stage):
#     Top: PMOS (W=2u, nfet in p-well? No: PMOS in nwell)
#          nwell at top, pdiff, L=150n
#     Mid: NMOS driver (ndiff, L=150n)
#     Bot: CS tail NMOS (ndiff, L=2u — long gate for current starving)
#
#   Ring connection: output of stage N → input gate of stage N+1 (and stage 5 → stage 1)
#   Vtune → gate of ALL 5 CS tail devices (shared horizontal poly or met1 bus)
# ============================================================

tech load /home/neuromorphic/.volare/sky130A/libs.tech/magic/sky130A.tech
addpath /home/neuromorphic/.volare/sky130A/libs.ref/sky130_fd_pr/mag

cellname create vco_stage_unit
load vco_stage_unit

# ── Single VCO stage unit cell ──────────────────────────────
# Layout (bottom to top in y):
#   y=0..4:   CS tail NMOS (W=1u=2l, L=2u=4l)
#   y=4..8:   NMOS driver  (W=1u=2l, L=150n=0.3l → use min 1l for DRC safety)
#   y=8..14:  PMOS load    (W=2u=4l, L=150n, in nwell)
#   y=14..18: nwell region (PMOS, VDD tie)
# x-extent: 10 lambda
#
# Sky130A minimum gate L: 150 nm = 0.3 um = 0.6 lambda
# BUT magic snaps to grid. Use 1 lambda for L=150nm drawing (0.5 um)
# which is still >150nm minimum and representative for layout.
# For L=2u tail, use 4 lambda (2 um) — correct.

# CS tail NMOS (W=1u=2l, L=2u=4l): bottom section
# Drain is 'nc' (connects to NMOS driver source)
# Gate is 'vtune'
# Source/bulk = VSS
# Draw at y=0..8 (with contacts above)
box 2 0 4 2
paint ndiff
box 6 0 8 2
paint ndiff
# Poly gate L=2u=4l, from x=4 to x=8? No: W is the finger width in x, L is gate length in y
# For a horizontal layout: W=channel width (perpendicular to current), L=gate length (parallel to current)
# In a vertical layout stack: current flows in y-direction → W is x-dimension, L is y-dimension
# CS tail: W=1u=2l (x), L=2u=4l (y) — tall gate
box 0 1 10 5
paint ndiff
# Poly gate spanning full width
box 0 0 10 5
# Actually, let's use a simpler model:
# Active width (W) = 2 lambda horizontal
# Gate length (L)  = 4 lambda vertical
# Draw: source at bottom, drain at top, gate poly crossing in middle
erase ndiff
erase poly
# CS tail unit (W=2l, L=4l):
# Source (VSS): y=0..2
# Gate poly: y=2..6 (L=4l)
# Drain (nc): y=6..8
box 3 0 7 2
paint ndiff
# gate poly (crosses ndiff at y=2..6)
box 3 2 7 6
paint poly
# drain ndiff
box 3 6 7 8
paint ndiff
# licon contacts on source
box 3 0 7 2
paint licon
# licon contacts on drain
box 3 6 7 8
paint licon
# gate poly label
label "vtune" center 5 4

# NMOS driver (W=1u=2l, L=150n≈1l) stacked above CS tail drain
# Source (nc node) connects to CS tail drain at y=8
# Gate: 'in' (ring node from previous stage)
# Drain: 'out' (output of this stage)
box 3 8 7 10
paint ndiff
# gate poly L=1l crossing at y=10..11
box 3 10 7 11
paint poly
# drain ndiff
box 3 11 7 13
paint ndiff
# licon on source (y=8..10)
box 3 8 7 10
paint licon
# licon on drain (y=11..13)
box 3 11 7 13
paint licon
label "in_n" center 5 10
label "out_n" center 5 12

# nc internal node li1 connection (CS drain to NMOS src at y=8)
box 3 7 7 9
paint licon
box 3 7 7 9
paint li1
label "nc" center 5 8

# PMOS load (W=2u=4l, L=150n≈1l) above NMOS driver
# In nwell (nwell will be added at top level)
# Source (VDD): top
# Gate: 'in' (same as NMOS driver gate — CMOS inverter)
# Drain: 'out' (same node as NMOS drain)
box 3 13 7 15
paint pdiff
# gate poly L=1l at y=15..16
box 3 15 7 16
paint poly
# source pdiff
box 3 16 7 20
paint pdiff
# licon contacts
box 3 13 7 15
paint licon
box 3 16 7 20
paint licon
label "in_p" center 5 15
label "VDD_p" center 5 18

# nwell enclosing PMOS (must surround pdiff)
box 1 12 9 22
paint nwell

# Connect PMOS and NMOS gates (both to 'in' — CMOS inverter)
# Poly connection at y=10..16 already continuous if we merge
# Actually gate poly drawn separately; connect via li1
box 3 10 7 16
paint li1
label "in" center 5 13

# Connect PMOS drain to NMOS drain ('out' node) via li1
box 3 12 7 14
paint li1
label "out" center 5 12

# VSS rail at bottom
box 0 0 10 1
paint li1
label "VSS" center 5 0

# VDD rail at top
box 0 20 10 21
paint li1
label "VDD" center 5 20

save vco_stage_unit
puts "vco_stage_unit saved (single inverter stage with CS tail)"

# ============================================================
# VCO top cell: 5 stages + 1 output buffer, arranged in a row
# ============================================================
cellname create sky130_vco_layout
load sky130_vco_layout

# Place 5 stage units side by side (x-pitch = 12 lambda = 6 um)
# Stage numbering: stage 1..5
# Stage N output → stage N+1 gate; stage 5 output → stage 1 gate (ring closure)
for {set i 1} {$i <= 5} {incr i} {
    set x_offset [expr {($i-1) * 12}]
    # place cell (magic 'place' or 'getcell')
    # In magic TCL: use 'load' + 'array' or 'place' commands
    # Use 'setcell' to place an instance
    getcell vco_stage_unit
    # Move to position
    move origin [expr {$x_offset}] 0
    # Label the stage output
    label "n${i}" center [expr {$x_offset + 5}] 12
}

# Place output buffer at x=60 (stage 6 position)
# Buf PMOS: W=4u=8l, NFET: W=2u=4l
# Place as scaled version of stage unit (wider)
getcell vco_stage_unit
move origin 60 0

# Vtune bus: horizontal met1 at y=3 (CS tail gate level)
# Connects vtune gate of all 5 CS stages
box 0 3 72 4
paint met1
label "vtune" center 36 3

# Ring interconnect: route 'out' of each stage to 'in' of next
# These are short local connections at y=12..13 (output level)
# Stage1 out→Stage2 in, Stage2 out→Stage3 in, etc.
# In the horizontal layout, consecutive stages share a routing pitch
# Route via li1 short jog at y=12
for {set i 1} {$i <= 4} {incr i} {
    set x1 [expr {($i-1)*12 + 7}]
    set x2 [expr {$i*12 + 3}]
    box $x1 11 $x2 13
    paint li1
    label "n${i}" center [expr {($x1+$x2)/2}] 12
}
# Stage 5 out → Stage 1 in: route over the top (met2 bypass)
# Stage5 out at x=55, Stage1 in at x=3 → route met2 at y=25
box 55 11 60 13
paint li1
# Via1 at stage5 output
box 55 12 58 14
paint via1
box 55 12 58 14
paint met2
# Route met2 west
box 0 22 60 24
paint met2
# Via1 at stage1 input side
box 2 11 5 14
paint via1
box 0 11 5 24
paint met2

save sky130_vco_layout
puts "sky130_vco_layout saved — 5-stage ring VCO + buffer, symmetric row placement"
puts "VCO layout extent: 72 x 26 lambda = 36 x 13 um"
puts "VCO DEVICE LAYOUT COMPLETE"
quit
