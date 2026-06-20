* CP Mismatch — Analytic BSIM4 calibration approach
* Use scaled models (BSIM4 level=14 with calibrated u0 and W_eff)
* to represent ASAP7 7nm FinFET behavior at correct current levels.
*
* Calibration target (from ASAP7 PDK characterization data, Vashishtha 2019):
*   NMOS RVT, nfins=1 (Wfin=7nm), L=14nm: Id_sat ~ 30 uA at Vgs=Vds=0.7V
*   PMOS RVT, nfins=1, L=14nm: Id_sat ~ 15 uA at |Vgs|=|Vds|=0.7V
*
* Since BSIM4 level=14 with W=7nm gives wrong currents,
* we use W_scale = 1000nm/7nm = ~143x and adjust u0 proportionally
* to represent 1 fin = 7nm effective:
*   u0_eff = u0_original / W_scale (so that I = u0*Cox*(W/L)*Veff^2 remains correct)
*   The rationale: BSIM4 Id ~ Cox*u0*(W/L)*(Vgs-Vth)^2/2
*   To get I=30uA with W=1000nm, L=14nm, need u0 such that:
*   30e-6 = Cox * u0_eff * (1000e-9/14e-9) * (Vov)^2/2
*   For Vov ~ Vgs-Vth = 0.7-0.276 = 0.424V:
*   Cox ~ epsrox*eps0/toxe = 3.9*8.85e-12/9e-10 = 38.4 mF/m2
*   u0_eff = 30e-6 / (38.4e-3 * (1000e-9/14e-9) * (0.424)^2/2)
*          = 30e-6 / (38.4e-3 * 71.4 * 0.0899)
*          = 30e-6 / 0.2463 = 1.22e-4 m^2/Vs = 0.000122
*
* Use W = 1000nm to represent 1 fin, scale nfin count accordingly.
* CP mirror: 36 fins PMOS, 20 fins NMOS -> W = 36000nm, 20000nm
* This keeps device ratios correct.
*
* For PMOS: Id_sat ~ 15 uA/fin at VDD=0.7V
*   Vov_p = 0.7-0.284 = 0.416V
*   Cox_p = 38.4 mF/m2 (same tox)
*   u0_p_eff = 15e-6 / (38.4e-3 * 71.4 * (0.416)^2/2)
*            = 15e-6 / (38.4e-3 * 71.4 * 0.0866)
*            = 15e-6 / 0.2376 = 6.32e-5 m^2/Vs = 0.0000632
*
* Rounding for ngspice: u0_n=0.000122, u0_p=0.000063

.model nfinfet_rvt nmos level=14 version=4.5
+ toxe=9.0e-10 toxp=7.0e-10 toxm=9.0e-10 dtox=2.0e-10
+ epsrox=3.9 wint=0 lint=0
+ vth0=0.276 k1=0.5 k2=0.0 k3=0.0
+ dvt0=2.0 dvt1=0.53 dvt2=-0.032 dvt0w=0 dvt1w=0 dvt2w=0
+ dsub=0.5 minv=0.0 voffl=0 dvtp0=1e-10 dvtp1=0.1
+ w0=2.5e-6 k3b=0 ngate=0
+ vsat=1.7e7 a0=2.0 ags=1e-20 a1=0 a2=1.0
+ keta=0.04 nsub=6.0e18 ndep=1.7e18 nsd=2.0e20 phin=0
+ cdsc=2.4e-4 cdscb=0 cdscd=0 cit=0
+ u0=0.000122 ua=6e-10 ub=0 uc=0
+ voff=-0.13 nfactor=1.0 etab=0 clc=0 cle=0.6 delta=0.01
+ rdsw=0.15 rdswmin=0 prwg=0 prwb=0
+ pclm=0.04 pdiblc1=0 pdiblc2=0 pdiblcb=0
+ drout=0.0 pscbe1=8.14e8 pscbe2=1e-7 pvag=0 mobmod=0
+ cgso=6.24e-11 cgdo=6.24e-11 cgbo=0 cf=0 xpart=0
+ tnom=27 kt1=-0.11 kt1l=0 kt2=0.022
+ ute=-1.5 ua1=4.31e-9 ub1=-7.61e-18 uc1=-5.6e-11
+ at=3.3e4 prt=0 xl=0

.model pfinfet_rvt pmos level=14 version=4.5
+ toxe=9.0e-10 toxp=7.0e-10 toxm=9.0e-10 dtox=2.0e-10
+ epsrox=3.9 wint=0 lint=0
+ vth0=-0.284 k1=0.5 k2=0.0 k3=0.0
+ dvt0=2.0 dvt1=0.53 dvt2=-0.032 dvt0w=0 dvt1w=0 dvt2w=0
+ dsub=0.5 minv=0.0 voffl=0 dvtp0=1e-10 dvtp1=0.1
+ w0=2.5e-6 k3b=0 ngate=0
+ vsat=1.1e7 a0=2.0 ags=1e-20 a1=0 a2=1.0
+ keta=0.04 nsub=6.0e18 ndep=1.7e18 nsd=2.0e20 phin=0
+ cdsc=2.4e-4 cdscb=0 cdscd=0 cit=0
+ u0=0.000063 ua=6e-10 ub=0 uc=0
+ voff=-0.13 nfactor=1.0 etab=0 clc=0 cle=0.6 delta=0.01
+ rdsw=0.20 rdswmin=0 prwg=0 prwb=0
+ pclm=0.04 pdiblc1=0 pdiblc2=0 pdiblcb=0
+ drout=0.0 pscbe1=8.14e8 pscbe2=1e-7 pvag=0 mobmod=0
+ cgso=6.24e-11 cgdo=6.24e-11 cgbo=0 cf=0 xpart=0
+ tnom=27 kt1=-0.11 kt1l=0 kt2=0.022
+ ute=-1.5 ua1=4.31e-9 ub1=-7.61e-18 uc1=-5.6e-11
+ at=3.3e4 prt=0 xl=0

VDD vdd 0 DC 0.7

* ============================================================
* Device sizes: scale W by 1000n per fin
* 36-fin PMOS -> W = 36000n = 36u
* 20-fin NMOS -> W = 20000n = 20u
* L = 21n (keep nominal to maintain Leff/Wfin ratio)
* ============================================================

* PMOS mirror reference (diode-connected)
MP_ref  vbias_p  vbias_p  vdd  vdd  pfinfet_rvt  w=36u  l=21n
Ibias_p  0  vbias_p  DC  1m

* PMOS mirror copy (output)
MP_out  vcp_up  vbias_p  vdd  vdd  pfinfet_rvt  w=36u  l=21n
Vcp_up  vcp_up  0  DC 0.35

* NMOS mirror reference (diode-connected)
MN_ref  vbias_n  vbias_n  0  0  nfinfet_rvt  w=20u  l=21n
Ibias_n  vbias_n  0  DC  1m

* NMOS mirror copy (output)
MN_out  vcp_dn  vbias_n  0  0  nfinfet_rvt  w=20u  l=21n
Vcp_dn  vcp_dn  0  DC 0.35

.dc Vcp_up 0.10 0.60 0.05

.print dc v(vbias_p) -i(Vcp_up) v(vbias_n) i(Vcp_dn)

.end
