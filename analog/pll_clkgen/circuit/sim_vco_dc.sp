* VCO single stage DC operating point check
* Verify NMOS tail current vs PMOS cross-coupled load balance

.model nm_vco nmos level=14 version=4.5
+ toxe=9.0e-10 epsrox=3.9 wint=0 lint=0
+ vth0=0.276 k1=0.5 k2=0 k3=0 dvt0=2 dvt1=0.53 dvt2=-0.032
+ dvt0w=0 dvt1w=0 dvt2w=0
+ dsub=0.5 voffl=0 w0=2.5e-6 k3b=0 ngate=0
+ vsat=5.0e6 a0=2.0 ags=0 a1=0 a2=1.0
+ keta=0.04 nsd=2.0e20 phin=0 cdsc=2.4e-4 cdscb=0 cdscd=0 cit=0
+ u0=0.01 ua=6e-10 ub=0 uc=0
+ voff=-0.13 nfactor=1.0 etab=0 clc=0 cle=0.6 delta=0.01
+ rdsw=15 pclm=0.04 pdiblc1=0 pdiblc2=0 pdiblcb=0
+ drout=0.0 pscbe1=8.14e8 pscbe2=1e-7 pvag=0 mobmod=0
+ cgso=6.24e-11 cgdo=6.24e-11 cgbo=0 cf=0 xpart=0
+ tnom=27 kt1=-0.11 kt1l=0 kt2=0.022
+ ute=-1.5 ua1=4.31e-9 ub1=-7.61e-18 uc1=-5.6e-11
+ at=3.3e4 prt=0

.model pm_vco pmos level=14 version=4.5
+ toxe=9.0e-10 epsrox=3.9 wint=0 lint=0
+ vth0=-0.284 k1=0.5 k2=0 k3=0 dvt0=2 dvt1=0.53 dvt2=-0.032
+ dvt0w=0 dvt1w=0 dvt2w=0
+ dsub=0.5 voffl=0 w0=2.5e-6 k3b=0 ngate=0
+ vsat=3.0e6 a0=2.0 ags=0 a1=0 a2=1.0
+ keta=0.04 nsd=2.0e20 phin=0 cdsc=2.4e-4 cdscb=0 cdscd=0 cit=0
+ u0=0.005 ua=6e-10 ub=0 uc=0
+ voff=-0.13 nfactor=1.0 etab=0 clc=0 cle=0.6 delta=0.01
+ rdsw=20 pclm=0.04 pdiblc1=0 pdiblc2=0 pdiblcb=0
+ drout=0.0 pscbe1=8.14e8 pscbe2=1e-7 pvag=0 mobmod=0
+ cgso=6.24e-11 cgdo=6.24e-11 cgbo=0 cf=0 xpart=0
+ tnom=27 kt1=-0.11 kt1l=0 kt2=0.022
+ ute=-1.5 ua1=4.31e-9 ub1=-7.61e-18 uc1=-5.6e-11
+ at=3.3e4 prt=0

VDD vdd 0 DC 0.7
Vtune vtune 0 DC 0.35

* Single stage: forced differential with Vdiff input
* Sweep vtune, measure tail current (which sets oscillation speed)
MN_cs  vtail  vtune  0  0  nm_vco  w=2000n  l=21n
* NMOS drain load (representing one side of diff pair)
MN_dp1  out1  vin1  vtail  0  nm_vco  w=2000n  l=14n
Vin1   vin1  0  DC 0.35

* Check Id vs vtune
.dc Vtune 0.10 0.65 0.05

.print dc i(Vtune) @MN_cs[ids] @MN_dp1[ids]

.end
