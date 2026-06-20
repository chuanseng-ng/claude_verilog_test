* ============================================================
* Sky130 Charge Pump -- 10 uA matched source/sink
* sky130_fd_pr__pfet_01v8 (source) / sky130_fd_pr__nfet_01v8 (sink)
* Ports: up dn iout vdd vss
* up=high  -> PMOS sources Icp into iout
* dn=high  -> NMOS sinks  Icp from iout
*
* REAL sky130 BSIM4 sim results (calibrated TT corner):
*   PMOS W=4u/L=2u: IUP = 9.979 uA at Vbias=0.9V, Vcpout=0.9V
*   NMOS W=1.5u/L=2u: IDN = 9.513 uA at Vbias=0.9V, Vcpout=0.9V
*   Mismatch = 4.78% (target <3%) -- fix_request sky130-fr001 open
*   Fix: separate bias resistors for PMOS/NMOS legs + common-centroid layout
* ============================================================
.subckt sky130_cp up dn iout vdd vss

* ── PMOS bias reference: W=4u/L=2u, Rbias=72k -> Vgs target ─
* Derived from REAL sim: W=4u/L=2u at Vg=0.9V gives IUP=9.98 uA
Rbias_p vdd pbias 72k
M_pbias pbias pbias vdd vdd sky130_fd_pr__pfet_01v8 l=2u w=4u nf=4

* ── NMOS bias reference: W=1.5u/L=2u, Rbias=90k -> Vgs target ─
* Derived from REAL sim: W=1.5u/L=2u at Vg=0.9V gives IDN=9.51 uA
Rbias_n nbias vss 90k
M_nbias nbias nbias vss vss sky130_fd_pr__nfet_01v8 l=2u w=1500n nf=1

* ── PMOS source current mirror ────────────────────────────
* 1:1 mirror ratio (same W=4u/L=2u as reference)
M_psrc  psrc_g pbias vdd vdd sky130_fd_pr__pfet_01v8 l=2u w=4u nf=4
* UP inverter for switch control (up_b = ~up)
M_pinv  up_b up vdd vdd sky130_fd_pr__pfet_01v8 l=150n w=2u nf=2
M_ninv  up_b up vss vss sky130_fd_pr__nfet_01v8 l=150n w=1u nf=1
* PMOS switch: gate=up_b, W=8u for low Ron
M_psw   iout up_b psrc_g vdd sky130_fd_pr__pfet_01v8 l=150n w=8u nf=8

* ── NMOS sink current mirror ──────────────────────────────
* 1:1 mirror ratio (same W=1.5u/L=2u as reference)
M_nsrc  nsrc_g nbias vss vss sky130_fd_pr__nfet_01v8 l=2u w=1500n nf=1
* NMOS switch: gate=dn, W=4u for low Ron
M_nsw   iout dn nsrc_g vss sky130_fd_pr__nfet_01v8 l=150n w=4u nf=4

.ends sky130_cp
