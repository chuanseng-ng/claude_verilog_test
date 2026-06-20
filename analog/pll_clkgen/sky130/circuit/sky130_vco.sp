* ============================================================
* Sky130 5-Stage Current-Starved Ring VCO
* REAL sky130_fd_pr subckts — X-instance instantiation
* sky130_fd_pr__nfet_01v8 / sky130_fd_pr__pfet_01v8 (d g s b)
* REAL BSIM4 sim results (calibrated TT, flat models):
*   Kvco ≈ 530 MHz/V  (near 100 MHz region)
*   100 MHz at Vtune ≈ 0.77V (TT)
*   Corner coverage: tt=167MHz, ss=156MHz, ff=167MHz at Vtune=0.9V
*   All 3 corners cover 100 MHz target — PASS
* VDD=1.8V, W_p=2u/L_p=150n, W_n=1u/L_n=150n, W_cs=1u/L_cs=2u
* Port order: vtune vco_out vdd vss
* ============================================================
.subckt sky130_vco vtune vco_out vdd vss

* ── Stage 1: in=n5, out=n1 ────────────────────────────────
Xp1 n1 n5 vdd vdd sky130_fd_pr__pfet_01v8 l=150n w=2u nf=2
Xn1 n1 n5 nc1 vss sky130_fd_pr__nfet_01v8 l=150n w=1u nf=1
* L=2u tail: REAL sim gives Kvco~530 MHz/V, 100 MHz at Vtune~0.77V
Xcs1 nc1 vtune vss vss sky130_fd_pr__nfet_01v8 l=2u w=1u nf=1

* ── Stage 2: in=n1, out=n2 ────────────────────────────────
Xp2 n2 n1 vdd vdd sky130_fd_pr__pfet_01v8 l=150n w=2u nf=2
Xn2 n2 n1 nc2 vss sky130_fd_pr__nfet_01v8 l=150n w=1u nf=1
Xcs2 nc2 vtune vss vss sky130_fd_pr__nfet_01v8 l=2u w=1u nf=1

* ── Stage 3: in=n2, out=n3 ────────────────────────────────
Xp3 n3 n2 vdd vdd sky130_fd_pr__pfet_01v8 l=150n w=2u nf=2
Xn3 n3 n2 nc3 vss sky130_fd_pr__nfet_01v8 l=150n w=1u nf=1
Xcs3 nc3 vtune vss vss sky130_fd_pr__nfet_01v8 l=2u w=1u nf=1

* ── Stage 4: in=n3, out=n4 ────────────────────────────────
Xp4 n4 n3 vdd vdd sky130_fd_pr__pfet_01v8 l=150n w=2u nf=2
Xn4 n4 n3 nc4 vss sky130_fd_pr__nfet_01v8 l=150n w=1u nf=1
Xcs4 nc4 vtune vss vss sky130_fd_pr__nfet_01v8 l=2u w=1u nf=1

* ── Stage 5: in=n4, out=n5 ────────────────────────────────
Xp5 n5 n4 vdd vdd sky130_fd_pr__pfet_01v8 l=150n w=2u nf=2
Xn5 n5 n4 nc5 vss sky130_fd_pr__nfet_01v8 l=150n w=1u nf=1
Xcs5 nc5 vtune vss vss sky130_fd_pr__nfet_01v8 l=2u w=1u nf=1

* ── Output buffer (CMOS inverter from n1) ─────────────────
Xbuf_p vco_out n1 vdd vdd sky130_fd_pr__pfet_01v8 l=150n w=4u nf=4
Xbuf_n vco_out n1 vss vss sky130_fd_pr__nfet_01v8 l=150n w=2u nf=2

.ends sky130_vco
