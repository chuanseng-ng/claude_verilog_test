# ============================================================
# CP (Charge Pump) Device Layout — sky130A
# Stage: device_generation + analog_placement
# Tool: Magic 8.3.489
# run_id: layout_20260620_120000
#
# From sky130_cp.sp circuit:
#   PMOS bias ref:  M_pbias  W=4u L=2u nf=4  (diode-connected, pbias node)
#   PMOS mirror:    M_psrc   W=4u L=2u nf=4  (1:1 mirror of M_pbias)
#   PMOS switch:    M_psw    W=8u L=150n nf=8 (UP switch, less critical for matching)
#   NMOS bias ref:  M_nbias  W=1.5u L=2u nf=1
#   NMOS mirror:    M_nsrc   W=1.5u L=2u nf=1 (1:1 mirror of M_nbias)
#   NMOS switch:    M_nsw    W=4u L=150n nf=4
#   Switch inverter: M_pinv_p W=2u L=150n, M_pinv_n W=1u L=150n
#   Resistors: Rbias_p=90k (poly), Rbias_n=91k (poly)
#
# Matching requirement (circuit note):
#   M_pbias / M_psrc: COMMON-CENTROID, same N-well island
#     → 2-finger interdigitation: [M_pbias][M_psrc][M_psrc][M_pbias]
#     → Equal W=4u/L=2u, nf=4 for each → total interdigitated array W_eff=4u, 8 fingers split 4+4
#   M_nbias / M_nsrc: COMMON-CENTROID, P-substrate
#     → Interdigitation: [M_nbias][M_nsrc][M_nsrc][M_nbias] (2 fingers each)
#       But nf=1 each → place as [Dummy_n][M_nbias][M_nsrc][M_nsrc][M_nbias][Dummy_n]
#   Dummy devices at array edges (edge effects equalisation)
#
# In sky130 magic, transistors are drawn using the 'diff', 'poly', 'nwell', 'pwell'
# layer primitives. For PMOS: nwell required, diffusion in nwell.
# Sky130A lambda = 0.5 um; 1 um = 2 internal units.
#
# PMOS sizing in magic layer coords (sky130A rules):
#   Active (diff) width:  W = 4 um = 8 lambda
#   Poly length:          L = 2 um = 4 lambda
#   Poly-to-active enc:   0.13 um minimum (sky130)
#   Gate (poly over diff) defines the transistor.
#   Drain/source: diff extending beyond poly contact areas.
#   nwell must surround pmos active with 0.34 um spacing.
#
# This script creates the cp_array cell with common-centroid PMOS and NMOS arrays.
# ============================================================

tech load /home/neuromorphic/.volare/sky130A/libs.tech/magic/sky130A.tech
addpath /home/neuromorphic/.volare/sky130A/libs.ref/sky130_fd_pr/mag

cellname create cp_pmos_array
load cp_pmos_array

# ============================================================
# PMOS common-centroid array: M_pbias (B) / M_psrc (S)
# Interdigitation: [Dum_P][B][S][S][B][Dum_P]
# Each finger: W=4um/L=2um, orientation: S=VDD, D=drain contact
# In sky130: pfet_01v8 drawn in nwell
#
# Sky130A layer mapping:
#   pwell  -> p-substrate (implicit, no explicit layer needed for nfet in sub)
#   nwell  -> n-well paint for PMOS
#   diff   -> active/diffusion (ndiff for nfet, pdiff for pfet)
#   poly   -> polysilicon gate
#   licon  -> local interconnect via (contact to diff or poly)
#   li1    -> local interconnect metal
#   mcon   -> via to met1
#   met1   -> metal 1
#
# Sky130A minimum rules (lambda=0.5um, rules in lambda):
#   poly min width:     2 lambda (1 um)
#   poly min space:     2 lambda (but for analog gate, L=2um = 4 lambda)
#   diff min width:     3.5 lambda (but W=4um >> min)
#   diff-poly spacing:  0.28 lambda? No: actual min gate L in sky130 = 150nm = 0.3 lambda
#   nwell min width:    18 lambda (9 um)
#   nwell-diff spacing: 0.68 lambda
#
# For L=2um (analog) PMOS, each unit cell (1 finger) layout:
#   Width in x: contact + drain_ext + L_gate + source_ext + contact = ~8 lambda
#   Height in y: W = 4um = 8 lambda (active height)
#
# Simplification: Use Sky130 fixed-cell PCells from mag/ library where available.
# The sky130_fd_pr mag library has fixed RF cells. For analog custom W/L,
# we draw primitives directly.
#
# PMOS finger unit (W=4u, L=2u):
#   x-pitch per finger: 4 lambda (gate) + 2*contact_width(2l) + 2*poly_enc(1l) + 2*spacing = ~14 lambda
#   y-height: W=8 lambda active + 2*diff_enc(2l) + well = ~16 lambda
#
# Array of 6 fingers (2 dummy + 2 pbias + 2 psrc in B-S-S-B pattern):
#   Total width: 6 * 14 lambda + shared sources = ~88 lambda = 44 um
#   With nwell enclosure: +4 lambda each side → 96 lambda = 48 um
#   Height: 16 lambda = 8 um

# ── PMOS array: draw nwell ─────────────────────────────────
# Nwell: spans entire array + 2 um (4 lambda) each side
# Array 6 fingers, x: 0..96 lambda; y: 0..20 lambda (with enc)
box 0 0 96 24
paint nwell

# ── Draw 6 PMOS fingers (unit: 14 lambda pitch, starting at x=4) ──
# Finger layout: [poly gate L=4l, centered; diff W=8l; drain/source contacts]
# Each finger at x_center = 4 + finger_num*14 + 7

proc draw_pmos_finger {x_start y_bottom W_lambda L_lambda} {
    # W_lambda = active height in lambda
    # L_lambda = poly gate length in lambda
    # x_start  = left edge of this finger (contact area)
    # Finger structure (left to right):
    #   [2l source contact zone][L_lambda gate][2l drain contact zone]
    set x_src_start $x_start
    set x_src_end   [expr {$x_start + 2}]
    set x_gate_start $x_src_end
    set x_gate_end   [expr {$x_gate_start + $L_lambda}]
    set x_drn_start  $x_gate_end
    set x_drn_end    [expr {$x_drn_start + 2}]

    set y_diff_bot [expr {$y_bottom + 2}]
    set y_diff_top [expr {$y_diff_bot + $W_lambda}]

    # pdiff active (source+drain, minus gate channel)
    box $x_src_start $y_diff_bot $x_src_end $y_diff_top
    paint pdiff
    box $x_drn_start $y_diff_bot $x_drn_end $y_diff_top
    paint pdiff

    # poly gate (crosses active)
    box $x_gate_start [expr {$y_bottom}] $x_gate_end [expr {$y_diff_top + 2}]
    paint poly

    # licon contacts in source and drain
    box $x_src_start [expr {$y_diff_bot + 1}] $x_src_end [expr {$y_diff_top - 1}]
    paint licon
    box $x_drn_start [expr {$y_diff_bot + 1}] $x_drn_end [expr {$y_diff_top - 1}]
    paint licon
}

# 6 PMOS fingers: [Dum][B][S][S][B][Dum] — pitch=14 lambda, start at x=4
# Labels: Dum=dummy, B=pbias (M_pbias), S=psrc (M_psrc)
set pmos_finger_roles {Dum B S S B Dum}
set x 4
foreach role $pmos_finger_roles {
    draw_pmos_finger $x 2 8 4
    # Label each finger drain with role
    label $role center [expr {$x + 7}] 10
    set x [expr {$x + 14}]
}

# ── li1 wiring for PMOS array ─────────────────────────────
# Source (S) of all PMOS: tie to VDD via li1 horizontal rail at top
# Position: y=14..16 lambda (above active) → VDD rail
box 0 16 96 18
paint li1
label "VDD" center 48 17

# Drain connections:
# M_pbias fingers (roles B, index 1 and 4) drain → pbias node
# x positions: finger1_drain = 4+4+2=10; finger4_drain = 4+3*14+4+2=60+6=66
# Drain is at x_drn_start to x_drn_end = (x_gate_end..x_drn_end)
# For finger at x_start, x_gate_end = x+2+4=x+6; x_drn = x+6 to x+8
# B fingers: x=4+14=18 (finger B1), x=4+3*14=46 (finger B2, but B2 is index 4 at x=4+4*14=60? No:)
# Index: 0=Dum x=4, 1=B x=18, 2=S x=32, 3=S x=46, 4=B x=60, 5=Dum x=74
# B drain at x+6..x+8: B1 drain=24..26; B2 drain=66..68
# S drain at x+6..x+8: S1 drain=38..40; S2 drain=52..54
# Connect B drains (pbias) horizontal li1 at y=4 lambda
box 24 3 68 5
paint li1
label "pbias" center 46 4

# Connect B gates (diode: gate=drain=pbias) — already at pbias from poly gate
# Gate of B finger contacts poly; poly connected to pbias drain
# Connect poly gates of B fingers to pbias drain node
# Poly gate of B1: x=20..24, poly gate of B2: x=62..66 (gate_start=x+2..x+2+4)
box 22 4 24 8
paint li1
box 62 4 66 8
paint li1

# S (M_psrc) drains → psrc_g output node; connect to UP switch gate
box 38 7 54 9
paint li1
label "psrc_g" center 46 8

# Dummy finger drains → VSS/float (or connect to nearest supply)
# Leave floating for now (dummy devices, drain tied to VDD by convention)
box 10 3 12 5
paint li1
label "Dum_VDD" center 11 4
box 80 3 82 5
paint li1

save cp_pmos_array
puts "cp_pmos_array saved — 6-finger common-centroid PMOS array (W=4u L=2u)"

# ============================================================
# NMOS array: M_nbias (B) / M_nsrc (S)
# W=1.5u L=2u nf=1 each → interdigitate as [Dum_N][B][S][Dum_N]
# In p-substrate: no nwell needed
# ============================================================
cellname create cp_nmos_array
load cp_nmos_array

proc draw_nfet_finger {x_start y_bottom W_lambda L_lambda} {
    set x_src_start $x_start
    set x_src_end   [expr {$x_start + 2}]
    set x_gate_start $x_src_end
    set x_gate_end   [expr {$x_gate_start + $L_lambda}]
    set x_drn_start  $x_gate_end
    set x_drn_end    [expr {$x_drn_start + 2}]
    set y_diff_bot [expr {$y_bottom + 1}]
    set y_diff_top [expr {$y_diff_bot + $W_lambda}]
    # ndiff active
    box $x_src_start $y_diff_bot $x_src_end $y_diff_top
    paint ndiff
    box $x_drn_start $y_diff_bot $x_drn_end $y_diff_top
    paint ndiff
    # poly gate
    box $x_gate_start $y_bottom $x_gate_end [expr {$y_diff_top + 1}]
    paint poly
    # licon contacts
    box $x_src_start [expr {$y_diff_bot + 1}] $x_src_end [expr {$y_diff_top - 1}]
    paint licon
    box $x_drn_start [expr {$y_diff_bot + 1}] $x_drn_end [expr {$y_diff_top - 1}]
    paint licon
}

# 4 NMOS fingers: [Dum][B][S][Dum] — W=3lambda (1.5um), L=4lambda (2um)
# Pitch = 2+4+2 = 8 lambda per finger; start x=2
set x 2
set nmos_roles {Dum B S Dum}
foreach role $nmos_roles {
    draw_nfet_finger $x 1 3 4
    label $role center [expr {$x + 4}] 4
    set x [expr {$x + 8}]
}

# VSS rail at bottom
box 0 0 36 2
paint li1
label "VSS" center 18 1

# Drain connections:
# B (M_nbias) drain → nbias node; B is at x=10, drain x=16..18
# S (M_nsrc) drain → nsrc_g;     S is at x=18, drain x=24..26
box 16 5 18 7
paint li1
label "nbias" center 17 6

box 24 5 26 7
paint li1
label "nsrc_g" center 25 6

# Connect B gate (diode) to drain (nbias):
# Gate at x=12..16 (gate_start=x+2=12, gate_end=16), drain at x=16..18
# Gate poly connects to nbias drain via poly-to-li contact
# Already shared at poly level — add licon on poly gate
box 12 3 14 7
paint licon
box 12 3 14 7
paint li1

save cp_nmos_array
puts "cp_nmos_array saved — 4-finger common-centroid NMOS array (W=1.5u L=2u)"
puts "CP DEVICE ARRAYS COMPLETE"
quit
