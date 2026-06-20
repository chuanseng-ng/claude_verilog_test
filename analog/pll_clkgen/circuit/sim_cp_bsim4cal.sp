* CP Mismatch — BSIM4 with planar-equivalent calibrated model
* Represents ASAP7 7nm FinFET as equivalent planar BSIM4
* W_eff = nfins * 2*(Hfin+Wfin) ~ nfins * 78nm (ASAP7: Hfin=32nm, Wfin=7nm)
* Per-fin Idsat = 30uA NMOS / 15uA PMOS at VDD=0.7V
* Use BSIM4 NMOS level=54 (BSIM4v4) which is more robust in ngspice

.model nm_cal nmos level=54 version=4.8.2
+ tox=3.5e-9
+ vth0=0.276
+ u0=0.04
+ vsat=2.0e5
+ ua=1e-9 ub=0
+ a0=1.0 b0=0 b1=0
+ rdsw=150
+ cgso=1.0e-10 cgdo=1.0e-10 cgbo=0
+ tnom=27
+ lint=0 wint=0

.model pm_cal pmos level=54 version=4.8.2
+ tox=3.5e-9
+ vth0=-0.284
+ u0=0.018
+ vsat=1.2e5
+ ua=1e-9 ub=0
+ a0=1.0 b0=0 b1=0
+ rdsw=200
+ cgso=1.0e-10 cgdo=1.0e-10 cgbo=0
+ tnom=27
+ lint=0 wint=0

VDD vdd 0 DC 0.7

* ============================================================
* NMOS single-device check
* W = 20 fins * 78nm = 1560nm, L = 21nm
* Target: Id ~ 600 uA at Vgs=0.5V, Vds=0.35V
* ============================================================
MN_t  dn_t  vgs_n  0  0  nm_cal  w=1560n  l=21n
Vgs_n  vgs_n  0  DC 0.5
Vds_n  dn_t   0  DC 0.35

* ============================================================
* PMOS single-device check
* W = 36 fins * 78nm = 2808nm, L = 21nm
* Target: Id ~ 540 uA at Vsg=0.4V, Vsd=0.35V
* ============================================================
MP_t  dp_t  vgp_t  vdd  vdd  pm_cal  w=2808n  l=21n
Vgp_t  vgp_t  0  DC 0.3
Vdp_t  dp_t   0  DC 0.35

.dc Vgs_n 0.0 0.7 0.05

.print dc i(Vds_n) i(Vdp_t)

.end
