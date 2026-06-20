* CP Mirror DC Check — Proper bias setup
* Tests PMOS and NMOS current mirror legs independently
* Each driven by an explicit current-source bias for DC operating point

.model nfinfet_rvt nmos level=14 version=4.5
+ toxe=9.0e-10 toxp=7.0e-10 toxm=9.0e-10 dtox=2.0e-10
+ epsrox=3.9 wint=0 lint=0
+ vth0=0.276 k1=0.5 k2=0.0 k3=0.0
+ dvt0=2.0 dvt1=0.53 dvt2=-0.032 dvt0w=0 dvt1w=0 dvt2w=0
+ dsub=0.5 minv=0.0 voffl=0 dvtp0=1e-10 dvtp1=0.1
+ w0=2.5e-6 k3b=0 ngate=0
+ vsat=1.7e5 a0=2.0 ags=1e-20 a1=0 a2=1.0
+ keta=0.04 nsub=6.0e18 ndep=1.7e18 nsd=2.0e20 phin=0
+ cdsc=2.4e-4 cdscb=0 cdscd=0 cit=0
+ u0=0.060 ua=6e-10 ub=0 uc=0
+ voff=-0.13 nfactor=1.0 etab=0 clc=0 cle=0.6 delta=0.01
+ rdsw=150 rdswmin=0 prwg=0 prwb=0
+ pclm=0.04 pdiblc1=0 pdiblc2=0 pdiblcb=0
+ drout=0.0 pscbe1=8.14e8 pscbe2=1e-7 pvag=0 mobmod=0
+ cgso=6.24e-11 cgdo=6.24e-11 cgbo=0 cf=0 xpart=0
+ tnom=27 kt1=-0.11 kt1l=0 kt2=0.022
+ ute=-1.5 ua1=4.31e-9 ub1=-7.61e-18 uc1=-5.6e-11
+ at=3.3e4 prt=0 xl=-4e-9

.model pfinfet_rvt pmos level=14 version=4.5
+ toxe=9.0e-10 toxp=7.0e-10 toxm=9.0e-10 dtox=2.0e-10
+ epsrox=3.9 wint=0 lint=0
+ vth0=-0.284 k1=0.5 k2=0.0 k3=0.0
+ dvt0=2.0 dvt1=0.53 dvt2=-0.032 dvt0w=0 dvt1w=0 dvt2w=0
+ dsub=0.5 minv=0.0 voffl=0 dvtp0=1e-10 dvtp1=0.1
+ w0=2.5e-6 k3b=0 ngate=0
+ vsat=1.1e5 a0=2.0 ags=1e-20 a1=0 a2=1.0
+ keta=0.04 nsub=6.0e18 ndep=1.7e18 nsd=2.0e20 phin=0
+ cdsc=2.4e-4 cdscb=0 cdscd=0 cit=0
+ u0=0.025 ua=6e-10 ub=0 uc=0
+ voff=-0.13 nfactor=1.0 etab=0 clc=0 cle=0.6 delta=0.01
+ rdsw=200 rdswmin=0 prwg=0 prwb=0
+ pclm=0.04 pdiblc1=0 pdiblc2=0 pdiblcb=0
+ drout=0.0 pscbe1=8.14e8 pscbe2=1e-7 pvag=0 mobmod=0
+ cgso=6.24e-11 cgdo=6.24e-11 cgbo=0 cf=0 xpart=0
+ tnom=27 kt1=-0.11 kt1l=0 kt2=0.022
+ ute=-1.5 ua1=4.31e-9 ub1=-7.61e-18 uc1=-5.6e-11
+ at=3.3e4 prt=0 xl=-4e-9

VDD vdd 0 DC 0.7

* ============================================================
* PMOS current mirror — UP branch
* Reference: explicit 1mA current into diode-connected PMOS
* Ibias_p pulls 1 mA from drain of MP_ref (into vdd via mirror)
* MP_ref: W=252n (36 fins), L=21nm, diode-connected
* MP_out: W=252n (36 fins), L=21nm, output to compliance node
* ============================================================
* Reference PMOS (diode-connected, sets vbias_p gate voltage)
MP_ref  vbias_p  vbias_p  vdd  vdd  pfinfet_rvt  w=252n  l=21n
* Bias current: 1 mA into ref diode (forces correct Vgs)
Ibias_p  0  vbias_p  DC  1m
*
* Output PMOS mirror copy
MP_out  vcp_up  vbias_p  vdd  vdd  pfinfet_rvt  w=252n  l=21n
* Compliance voltage source (swept)
Vcp_up  vcp_up  0  DC 0.35

* ============================================================
* NMOS current mirror — DN branch (same structure)
* Reference: 1 mA into diode-connected NMOS (MN_ref)
* MN_out: mirrors to vcpout_dn
* ============================================================
MN_ref  vbias_n  vbias_n  0  0  nfinfet_rvt  w=140n  l=21n
Ibias_n  vbias_n  0  DC  1m
*
MN_out  vcp_dn  vbias_n  0  0  nfinfet_rvt  w=140n  l=21n
* Note: DN mirror sinks current FROM compliance node; sweep Vcp_dn
* Use a separate compliance voltage source to sweep
* Vcp_dn sweeps with Vcp_up (same sweep)
Vcp_dn  vcp_dn  0  DC 0.35

.dc Vcp_up 0.10 0.60 0.05

* Print current through both compliance sources
* I(Vcp_up): current from vdd->mirror->vcp_up->Vcp_up (Iup, should be ~1mA positive)
* I(Vcp_dn): current from Vcp_dn->vcp_dn->mirror->gnd (Idn, should be ~1mA negative conv.)
.print dc v(vcp_up) -i(Vcp_up) v(vcp_dn) i(Vcp_dn)

.end
