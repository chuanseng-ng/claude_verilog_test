* CP Mismatch DC Check
* Strategy: run two separate .dc sweeps, print raw data
* Post-process with awk to get mismatch numbers

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

* Supply
.param vdd_val=0.7
VDD vdd 0 DC 0.7

* ============================================================
* UP branch (PMOS mirror): measure current vs compliance voltage
* MP_ref diode-connected ref: 36 fins, L=21nm
* MP_src mirror copy: 36 fins, L=21nm  (matched)
* Bias: NMOS sets ~1mA into PMOS ref -> Vgs_p sets up
* ============================================================
* NMOS bias sink in ref branch (diode-connected: sets vbias level)
MN_b   vbias_p  vbias_p  0  0  nfinfet_rvt  w=140n  l=21n
MP_r   vbias_p  vbias_p  vdd  vdd  pfinfet_rvt  w=252n  l=21n
* PMOS mirror copy
MP_m   vcpout   vbias_p  vdd  vdd  pfinfet_rvt  w=252n  l=21n
* Compliance sweep source
Vout   vcpout   0  DC 0.35

* ============================================================
* DN branch (NMOS mirror): separate measurement
* Uses different node names
* ============================================================
MN_r2   vbias_n  vbias_n  0  0  nfinfet_rvt  w=140n  l=21n
MP_b2   vbias_n  vbias_p  vdd  vdd  pfinfet_rvt  w=252n  l=21n
MN_m2   vcpout2  vbias_n  0  0  nfinfet_rvt  w=140n  l=21n
Vout2   vcpout2  0  DC 0.35

* ============================================================
* DC sweep: sweep Vout from 0.10 to 0.60V
* ============================================================
.dc Vout 0.10 0.60 0.025

.print dc I(Vout) I(Vout2)

.end
