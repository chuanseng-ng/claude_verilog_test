* VCO Ring Oscillator — 5-stage current-starved
* Uses BSIM4 with W=500nm/fin (valid BSIM4 range), u0 adjusted to give correct Id/fin
* Target: 30uA NMOS / 15uA PMOS per fin at nominal bias
* At W=500nm: need Id=30uA -> u0_adj = u0_bsim4_target
* From BSIM4 saturation: Id = Cox*u0*(W/(2*L))*(Vgs-Vth)^2 (simplified, velocity sat ignored)
* Id=30e-6, W=500e-9, L=14e-9, Cox=38e-3 F/m2, Vov=0.424V
* u0 = Id*2*L / (Cox*W*Vov^2) = 30e-6 * 2*14e-9 / (38e-3 * 500e-9 * 0.18)
*    = 840e-15 / (3.42e-12) = 0.000246 m2/Vs ~ 2460 cm2/Vs
* But at high vsat=1.7e5 m/s (velocity saturated), Idsat ~ Cox*W*vsat*Vov
* Id = Cox*W*vsat*Vov/2 = 38e-3*500e-9*1.7e5*0.424/2 = 38e-3*500e-9*36040
*    = 38e-3 * 18.02e-6 = 685 pA -- wrong (vsat is too low for planar equiv)
* Use vsat=5e6 m/s (adjusted for 7nm): Id = 38e-3*500e-9*5e6*0.424 = 40.3 uA/fin CLOSE
* -> set vsat=5e6, u0=0.01

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
Vcs capsel0 0 DC 0
Vcs1 capsel1 0 DC 0
Vcs2 capsel2 0 DC 0

* W per fin in this sim: 500nm (keeps BSIM4 in valid planar regime)
* n fins scaled: DP pair was 4 fins (28n real) -> 4*500n=2000n here
* CC load was 4 fins PMOS -> 4*500n=2000n
* CS tail was 4 fins NMOS -> 4*500n=2000n
* Cap bank: 2-8 fins -> 1000n-4000n

* ---- Stage 1 ----
MP_cc1_1  n1p  n1n  vdd  vdd  pm_vco  w=2000n  l=14n
MP_cc2_1  n1n  n1p  vdd  vdd  pm_vco  w=2000n  l=14n
MN_dp1_1  n1p  n5n  vt1  0   nm_vco  w=2000n  l=14n
MN_dp2_1  n1n  n5p  vt1  0   nm_vco  w=2000n  l=14n
MN_cs_1   vt1  vtune  0   0   nm_vco  w=2000n  l=21n
MC0_1p    n1p  capsel0  0  0  nm_vco  w=1000n  l=14n
MC0_1n    n1n  capsel0  0  0  nm_vco  w=1000n  l=14n

* ---- Stage 2 ----
MP_cc1_2  n2p  n2n  vdd  vdd  pm_vco  w=2000n  l=14n
MP_cc2_2  n2n  n2p  vdd  vdd  pm_vco  w=2000n  l=14n
MN_dp1_2  n2p  n1n  vt2  0   nm_vco  w=2000n  l=14n
MN_dp2_2  n2n  n1p  vt2  0   nm_vco  w=2000n  l=14n
MN_cs_2   vt2  vtune  0   0   nm_vco  w=2000n  l=21n
MC0_2p    n2p  capsel0  0  0  nm_vco  w=1000n  l=14n
MC0_2n    n2n  capsel0  0  0  nm_vco  w=1000n  l=14n

* ---- Stage 3 ----
MP_cc1_3  n3p  n3n  vdd  vdd  pm_vco  w=2000n  l=14n
MP_cc2_3  n3n  n3p  vdd  vdd  pm_vco  w=2000n  l=14n
MN_dp1_3  n3p  n2n  vt3  0   nm_vco  w=2000n  l=14n
MN_dp2_3  n3n  n2p  vt3  0   nm_vco  w=2000n  l=14n
MN_cs_3   vt3  vtune  0   0   nm_vco  w=2000n  l=21n
MC0_3p    n3p  capsel0  0  0  nm_vco  w=1000n  l=14n
MC0_3n    n3n  capsel0  0  0  nm_vco  w=1000n  l=14n

* ---- Stage 4 ----
MP_cc1_4  n4p  n4n  vdd  vdd  pm_vco  w=2000n  l=14n
MP_cc2_4  n4n  n4p  vdd  vdd  pm_vco  w=2000n  l=14n
MN_dp1_4  n4p  n3n  vt4  0   nm_vco  w=2000n  l=14n
MN_dp2_4  n4n  n3p  vt4  0   nm_vco  w=2000n  l=14n
MN_cs_4   vt4  vtune  0   0   nm_vco  w=2000n  l=21n
MC0_4p    n4p  capsel0  0  0  nm_vco  w=1000n  l=14n
MC0_4n    n4n  capsel0  0  0  nm_vco  w=1000n  l=14n

* ---- Stage 5 ----
MP_cc1_5  n5p  n5n  vdd  vdd  pm_vco  w=2000n  l=14n
MP_cc2_5  n5n  n5p  vdd  vdd  pm_vco  w=2000n  l=14n
MN_dp1_5  n5p  n4n  vt5  0   nm_vco  w=2000n  l=14n
MN_dp2_5  n5n  n4p  vt5  0   nm_vco  w=2000n  l=14n
MN_cs_5   vt5  vtune  0   0   nm_vco  w=2000n  l=21n
MC0_5p    n5p  capsel0  0  0  nm_vco  w=1000n  l=14n
MC0_5n    n5n  capsel0  0  0  nm_vco  w=1000n  l=14n

.ic V(n1p)=0.6 V(n1n)=0.1 V(n2p)=0.1 V(n2n)=0.6
.ic V(n3p)=0.6 V(n3n)=0.1 V(n4p)=0.1 V(n4n)=0.6
.ic V(n5p)=0.6 V(n5n)=0.1

.tran 1p 10n uic

.print tran v(n3p) v(n3n)

.end
