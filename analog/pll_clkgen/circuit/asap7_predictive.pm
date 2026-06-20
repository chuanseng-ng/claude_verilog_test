* ============================================================
* ASAP7-PREDICTIVE FinFET SPICE Model Card  (ngspice-compatible)
* LABEL: PREDICTIVE_PLACEHOLDER
* Source: PTM-MG (predictive technology model, multi-gate) 7nm
*   http://ptm.asu.edu/  — Arizona State University
*   Adapted for ASAP7 nominal (TT, 0.7V, 25C) FinFET parameters
*   after Vashishtha & Clark (2019) ASAP7 PDK publication.
*
* WARNING: These are representative / academic models.
*   They are NOT the real ASAP7 BSIM-CMG library.
*   They reproduce correct order-of-magnitude behaviour for topology
*   sizing and Kvco / CP mismatch checks.
*   DO NOT use for sign-off; hand off to circuit-simulation
*   orchestrator with real foundry models for PVT closure.
*
* Fin pitch = 27 nm; Fin height = 32 nm; tox_eff = 0.9 nm
* Unit fin width Wfin = 7 nm (electrical).
* W = nfins * Wfin  (quantised; min 1 fin)
* RVT Vth_n ~ 0.276 V, Vth_p ~ -0.284 V  @ Vds=Vdd/2
* SLVT Vth_n ~ 0.20 V, Vth_p ~ -0.22 V   @ Vds=Vdd/2
*
* ngspice BSIM4 (level=14) compatible parameters only.
* Removed: nlx, tox (use toxe), cj/cjsw/cjswg, pb/pbsw/pbswg,
*          mj/mjsw/mjswg, jss/jsd, jsws/jswd, jswgs/jswgd, xtis/xtid,
*          tpb/tcj variants, cgsl/cgdl duplicates, ckappas/ckappad
* ============================================================

* ---- NMOS RVT (nfinfet_rvt) ----
.model nfinfet_rvt nmos level=14
+ version=4.5
+ toxe=9.0e-10 toxp=7.0e-10 toxm=9.0e-10 dtox=2.0e-10
+ epsrox=3.9
+ wint=0 lint=0
+ vth0=0.276 k1=0.5 k2=0.0 k3=0.0
+ dvt0=2.0 dvt1=0.53 dvt2=-0.032
+ dvt0w=0 dvt1w=0 dvt2w=0
+ dsub=0.5 minv=0.0 voffl=0 dvtp0=1e-10 dvtp1=0.1
+ w0=2.5e-6 k3b=0
+ ngate=0
+ vsat=1.7e5 a0=2.0 ags=1e-20 a1=0 a2=1.0
+ keta=0.04 nsub=6.0e18 ndep=1.7e18
+ nsd=2.0e20
+ phin=0
+ cdsc=2.4e-4 cdscb=0 cdscd=0 cit=0
+ u0=0.060 ua=6e-10 ub=0 uc=0
+ voff=-0.13 nfactor=1.0 etab=0
+ clc=0 cle=0.6
+ delta=0.01
+ rdsw=150 rdswmin=0 prwg=0 prwb=0
+ pclm=0.04 pdiblc1=0.0 pdiblc2=0.0 pdiblcb=0.0
+ drout=0.0 pscbe1=8.14e8 pscbe2=1e-7
+ pvag=0
+ mobmod=0
+ cgso=6.24e-11 cgdo=6.24e-11 cgbo=0
+ cf=0
+ xpart=0
+ tnom=27 kt1=-0.11 kt1l=0 kt2=0.022
+ ute=-1.5 ua1=4.31e-9 ub1=-7.61e-18 uc1=-5.6e-11
+ at=3.3e4 prt=0
+ xl=-4e-9

* ---- PMOS RVT (pfinfet_rvt) ----
.model pfinfet_rvt pmos level=14
+ version=4.5
+ toxe=9.0e-10 toxp=7.0e-10 toxm=9.0e-10 dtox=2.0e-10
+ epsrox=3.9
+ wint=0 lint=0
+ vth0=-0.284 k1=0.5 k2=0.0 k3=0.0
+ dvt0=2.0 dvt1=0.53 dvt2=-0.032
+ dvt0w=0 dvt1w=0 dvt2w=0
+ dsub=0.5 minv=0.0 voffl=0 dvtp0=1e-10 dvtp1=0.1
+ w0=2.5e-6 k3b=0
+ ngate=0
+ vsat=1.1e5 a0=2.0 ags=1e-20 a1=0 a2=1.0
+ keta=0.04 nsub=6.0e18 ndep=1.7e18
+ nsd=2.0e20
+ phin=0
+ cdsc=2.4e-4 cdscb=0 cdscd=0 cit=0
+ u0=0.025 ua=6e-10 ub=0 uc=0
+ voff=-0.13 nfactor=1.0 etab=0
+ clc=0 cle=0.6
+ delta=0.01
+ rdsw=200 rdswmin=0 prwg=0 prwb=0
+ pclm=0.04 pdiblc1=0.0 pdiblc2=0.0 pdiblcb=0.0
+ drout=0.0 pscbe1=8.14e8 pscbe2=1e-7
+ pvag=0
+ mobmod=0
+ cgso=6.24e-11 cgdo=6.24e-11 cgbo=0
+ cf=0
+ xpart=0
+ tnom=27 kt1=-0.11 kt1l=0 kt2=0.022
+ ute=-1.5 ua1=4.31e-9 ub1=-7.61e-18 uc1=-5.6e-11
+ at=3.3e4 prt=0
+ xl=-4e-9

* ---- NMOS SLVT (nfinfet_slvt) — for CML / high-speed divider ----
.model nfinfet_slvt nmos level=14
+ version=4.5
+ toxe=9.0e-10 toxp=7.0e-10 toxm=9.0e-10 dtox=2.0e-10
+ epsrox=3.9
+ wint=0 lint=0
+ vth0=0.200 k1=0.5 k2=0.0 k3=0.0
+ dvt0=2.0 dvt1=0.53 dvt2=-0.032
+ dsub=0.5 minv=0.0 voffl=0
+ w0=2.5e-6 k3b=0
+ vsat=2.0e5 a0=2.0 ags=1e-20 a1=0 a2=1.0
+ keta=0.04 nsub=6.0e18 ndep=1.7e18
+ nsd=2.0e20
+ cdsc=2.4e-4 cdscb=0 cdscd=0 cit=0
+ u0=0.070 ua=6e-10 ub=0 uc=0
+ voff=-0.10 nfactor=1.0 etab=0
+ delta=0.01
+ rdsw=100 rdswmin=0 prwg=0 prwb=0
+ pclm=0.04 pdiblc1=0.0 pdiblc2=0.0 pdiblcb=0.0
+ drout=0.0 pscbe1=8.14e8 pscbe2=1e-7
+ cgso=6.24e-11 cgdo=6.24e-11 cgbo=0
+ cf=0
+ xpart=0
+ tnom=27 kt1=-0.11 kt1l=0 kt2=0.022
+ ute=-1.5 ua1=4.31e-9 ub1=-7.61e-18 uc1=-5.6e-11
+ at=3.3e4 prt=0
+ xl=-4e-9

* ---- PMOS SLVT ----
.model pfinfet_slvt pmos level=14
+ version=4.5
+ toxe=9.0e-10 toxp=7.0e-10 toxm=9.0e-10 dtox=2.0e-10
+ epsrox=3.9
+ wint=0 lint=0
+ vth0=-0.220 k1=0.5 k2=0.0 k3=0.0
+ dvt0=2.0 dvt1=0.53 dvt2=-0.032
+ dsub=0.5 minv=0.0 voffl=0
+ w0=2.5e-6 k3b=0
+ vsat=1.3e5 a0=2.0 ags=1e-20 a1=0 a2=1.0
+ keta=0.04 nsub=6.0e18 ndep=1.7e18
+ nsd=2.0e20
+ cdsc=2.4e-4 cdscb=0 cdscd=0 cit=0
+ u0=0.030 ua=6e-10 ub=0 uc=0
+ voff=-0.10 nfactor=1.0 etab=0
+ delta=0.01
+ rdsw=150 rdswmin=0 prwg=0 prwb=0
+ pclm=0.04 pdiblc1=0.0 pdiblc2=0.0 pdiblcb=0.0
+ drout=0.0 pscbe1=8.14e8 pscbe2=1e-7
+ cgso=6.24e-11 cgdo=6.24e-11 cgbo=0
+ cf=0
+ xpart=0
+ tnom=27 kt1=-0.11 kt1l=0 kt2=0.022
+ ute=-1.5 ua1=4.31e-9 ub1=-7.61e-18 uc1=-5.6e-11
+ at=3.3e4 prt=0
+ xl=-4e-9

* ============================================================
* gm/Id lookup reference (derived from these model parameters)
*  at TT 0.7V 25C, L=14nm (2x min), Vds=Vdd/2=0.35V
*
*  NMOS RVT: Id at Vgs=0.4V ~  30 uA/fin;  Vgs=0.5V ~ 70 uA/fin
*            Vth~0.28V -> Vgs_sat_min = Vth + Vdsat ~ 0.42V
*            gm/Id range: 10-20 V^-1 (low-Id / weak-moderate inversion)
*  PMOS RVT: Id at Vgs=-0.4V ~ 15 uA/fin; gm/Id ~ 8-15 V^-1
*
* Design convention (this project):
*   1 fin = Wfin=7nm.  Multi-fin => W = nfins*7nm.
*   Minimum L used: 14nm (2xLmin) for analog; 7nm for CML buffers.
*   Current-starve devices (VCO): 4-8 fins at L=21nm
*   CP mirror devices: 16 fins PMOS / 12 fins NMOS at L=21nm
*   BGR diode-connected: 8 fins at L=21nm
* ============================================================
