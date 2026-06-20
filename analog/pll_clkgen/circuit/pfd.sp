* ============================================================
* PFD — Phase-Frequency Detector
* Topology: CMOS Tri-state D-FF pair + reset AND gate
* PDK:      ASAP7 predictive (PREDICTIVE_PLACEHOLDER)
* VDD:      0.7 V
* Spec:     0.2 mW, 150 um2, dead_zone < 10 ps, f_ref_max = 150 MHz
* ============================================================
* Sizing rationale:
*   All devices at min L=7nm (digital logic — speed-critical)
*   Fin counts selected for ~equal PMOS/NMOS drive (P has ~0.6x Idsat):
*     Standard cell: NMOS 2 fins, PMOS 3 fins (drive balance)
*   Reset AND gate needs fast pull-down to clear UP/DN within 0.5 ns
*   Tri-state output: keep nodes UP, DN LOW when PFD locked (both = 0)
*
* ERC notes:
*   - All bulk/body connections tied (NMOS bulk -> gnd, PMOS bulk -> vdd)
*   - No floating gates: D inputs are driven; reset is driven
* ============================================================

.subckt pfd ref clk up dn vdd gnd
*
* --- Internal nodes ---
* q1, q1b  = output of FF1 (ref-side)  = UP (active-high charge-up)
* q2, q2b  = output of FF2 (clk-side)  = DN (active-high charge-dn)
* rst       = AND(q1,q2) = reset pulse
*
* === FF1: Rising-edge triggered D-FF clocked by REF ===
* D input = vdd (DFF in PFD always has D=1; state captured on edge)
* Implemented as: MS D-FF (master: transmission gate + inverter; slave: TG + inv)
* Simplified here as ideal CMOS DFF using transistor-level description
*
* --- Master latch FF1 ---
* Clocked inverter (master, clk=ref, passes when ref=0)
MP1a  inv1_in  ref     vdd    vdd   pfinfet_rvt  w=21n  l=7n  nfins=3
MN1a  inv1_in  ref_b   gnd    gnd   nfinfet_rvt  w=14n  l=7n  nfins=2
* Drive D=VDD directly (PFD D input is tied high)
Vd1   master_d  gnd  DC 'vdd_val'
MP1b  inv1_out  inv1_in  vdd  vdd  pfinfet_rvt  w=21n  l=7n  nfins=3
MN1b  inv1_out  inv1_in  gnd  gnd  nfinfet_rvt  w=14n  l=7n  nfins=2
*
* Transmission gate (master pass gate, on when ref=0)
MP1tg  inv1_in  ref_b  master_d  vdd  pfinfet_rvt  w=21n  l=7n  nfins=3
MN1tg  inv1_in  ref    master_d  gnd  nfinfet_rvt  w=14n  l=7n  nfins=2
*
* ref_b = inverted ref
MP1ri  ref_b  ref  vdd  vdd  pfinfet_rvt  w=21n  l=7n  nfins=3
MN1ri  ref_b  ref  gnd  gnd  nfinfet_rvt  w=14n  l=7n  nfins=2
*
* --- Slave latch FF1 ---
* Transmission gate (slave pass gate, on when ref=1)
MP1st  inv2_in  ref    inv1_out  vdd  pfinfet_rvt  w=21n  l=7n  nfins=3
MN1st  inv2_in  ref_b  inv1_out  gnd  nfinfet_rvt  w=14n  l=7n  nfins=2
*
MP1s   q1b  inv2_in  vdd  vdd  pfinfet_rvt  w=21n  l=7n  nfins=3
MN1s   q1b  inv2_in  gnd  gnd  nfinfet_rvt  w=14n  l=7n  nfins=2
*
MP1sb  q1   q1b  vdd  vdd  pfinfet_rvt  w=21n  l=7n  nfins=3
MN1sb  q1   q1b  gnd  gnd  nfinfet_rvt  w=14n  l=7n  nfins=2
*
* Feedback inverter (hold state)
MP1fb  inv2_in  q1   vdd  vdd  pfinfet_rvt  w=21n  l=7n  nfins=3
MN1fb  inv2_in  q1b  gnd  gnd  nfinfet_rvt  w=14n  l=7n  nfins=2
*
* === FF2: Rising-edge triggered D-FF clocked by CLK ===
MP2ri  clk_b  clk  vdd  vdd  pfinfet_rvt  w=21n  l=7n  nfins=3
MN2ri  clk_b  clk  gnd  gnd  nfinfet_rvt  w=14n  l=7n  nfins=2
*
Vd2   master_d2  gnd  DC 'vdd_val'
MP2tg  inv3_in  clk_b  master_d2  vdd  pfinfet_rvt  w=21n  l=7n  nfins=3
MN2tg  inv3_in  clk    master_d2  gnd  nfinfet_rvt  w=14n  l=7n  nfins=2
*
MP2b  inv3_out  inv3_in  vdd  vdd  pfinfet_rvt  w=21n  l=7n  nfins=3
MN2b  inv3_out  inv3_in  gnd  gnd  nfinfet_rvt  w=14n  l=7n  nfins=2
*
MP2st  inv4_in  clk    inv3_out  vdd  pfinfet_rvt  w=21n  l=7n  nfins=3
MN2st  inv4_in  clk_b  inv3_out  gnd  nfinfet_rvt  w=14n  l=7n  nfins=2
*
MP2s   q2b  inv4_in  vdd  vdd  pfinfet_rvt  w=21n  l=7n  nfins=3
MN2s   q2b  inv4_in  gnd  gnd  nfinfet_rvt  w=14n  l=7n  nfins=2
*
MP2sb  q2   q2b  vdd  vdd  pfinfet_rvt  w=21n  l=7n  nfins=3
MN2sb  q2   q2b  gnd  gnd  nfinfet_rvt  w=14n  l=7n  nfins=2
*
MP2fb  inv4_in  q2   vdd  vdd  pfinfet_rvt  w=21n  l=7n  nfins=3
MN2fb  inv4_in  q2b  gnd  gnd  nfinfet_rvt  w=14n  l=7n  nfins=2
*
* === Reset AND gate: rst = q1 AND q2 ===
* NAND + INV implementation (faster than AND)
* NAND: pull-down stack MN_and1,2 in series; pull-up MP parallel
MP_nd1  nand_out  q1  vdd  vdd  pfinfet_rvt  w=21n  l=7n  nfins=3
MP_nd2  nand_out  q2  vdd  vdd  pfinfet_rvt  w=21n  l=7n  nfins=3
MN_nd1  nand_out  q1  nd_int  gnd  nfinfet_rvt  w=14n  l=7n  nfins=2
MN_nd2  nd_int    q2  gnd    gnd  nfinfet_rvt  w=14n  l=7n  nfins=2
*
* INV after NAND -> rst (active high)
MP_ri  rst  nand_out  vdd  vdd  pfinfet_rvt  w=21n  l=7n  nfins=3
MN_ri  rst  nand_out  gnd  gnd  nfinfet_rvt  w=14n  l=7n  nfins=2
*
* === Reset connections (active high rst clears both FFs) ===
* Reset is applied to additional NMOS device pulling FF outputs low
* When rst=1: pull-down FF1 slave output (q1) and FF2 slave output (q2)
MN_rst1  q1  rst  gnd  gnd  nfinfet_rvt  w=14n  l=7n  nfins=2
MN_rst2  q2  rst  gnd  gnd  nfinfet_rvt  w=14n  l=7n  nfins=2
*
* === Output buffers / drivers for UP and DN ===
* UP = q1 buffered
MP_upb  up   q1b  vdd  vdd  pfinfet_rvt  w=21n  l=7n  nfins=3
MN_upb  up   q1b  gnd  gnd  nfinfet_rvt  w=14n  l=7n  nfins=2
*
* DN = q2 buffered
MP_dnb  dn   q2b  vdd  vdd  pfinfet_rvt  w=21n  l=7n  nfins=3
MN_dnb  dn   q2b  gnd  gnd  nfinfet_rvt  w=14n  l=7n  nfins=2

.ends pfd
* ============================================================
* End PFD subcircuit
* ============================================================
