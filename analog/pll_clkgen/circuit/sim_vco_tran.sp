* VCO Transient — measure oscillation freq at several vtune values
* Based on DC analysis: meaningful current at vtune > 0.40V
* Target: find Kvco and f_nom in the achievable range

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
Vtune vtune 0 DC 0.60

Vcs capsel0 0 DC 0
Vcs1 capsel1 0 DC 0
Vcs2 capsel2 0 DC 0

* 5-stage ring (W=2000n=4fins-equivalent in this calibrated model)
* Stage 1
MP_cc1_1  n1p  n1n  vdd  vdd  pm_vco  w=2000n  l=14n
MP_cc2_1  n1n  n1p  vdd  vdd  pm_vco  w=2000n  l=14n
MN_dp1_1  n1p  n5n  vt1  0   nm_vco  w=2000n  l=14n
MN_dp2_1  n1n  n5p  vt1  0   nm_vco  w=2000n  l=14n
MN_cs_1   vt1  vtune  0   0   nm_vco  w=2000n  l=21n
* Stage 2
MP_cc1_2  n2p  n2n  vdd  vdd  pm_vco  w=2000n  l=14n
MP_cc2_2  n2n  n2p  vdd  vdd  pm_vco  w=2000n  l=14n
MN_dp1_2  n2p  n1n  vt2  0   nm_vco  w=2000n  l=14n
MN_dp2_2  n2n  n1p  vt2  0   nm_vco  w=2000n  l=14n
MN_cs_2   vt2  vtune  0   0   nm_vco  w=2000n  l=21n
* Stage 3
MP_cc1_3  n3p  n3n  vdd  vdd  pm_vco  w=2000n  l=14n
MP_cc2_3  n3n  n3p  vdd  vdd  pm_vco  w=2000n  l=14n
MN_dp1_3  n3p  n2n  vt3  0   nm_vco  w=2000n  l=14n
MN_dp2_3  n3n  n2p  vt3  0   nm_vco  w=2000n  l=14n
MN_cs_3   vt3  vtune  0   0   nm_vco  w=2000n  l=21n
* Stage 4
MP_cc1_4  n4p  n4n  vdd  vdd  pm_vco  w=2000n  l=14n
MP_cc2_4  n4n  n4p  vdd  vdd  pm_vco  w=2000n  l=14n
MN_dp1_4  n4p  n3n  vt4  0   nm_vco  w=2000n  l=14n
MN_dp2_4  n4n  n3p  vt4  0   nm_vco  w=2000n  l=14n
MN_cs_4   vt4  vtune  0   0   nm_vco  w=2000n  l=21n
* Stage 5
MP_cc1_5  n5p  n5n  vdd  vdd  pm_vco  w=2000n  l=14n
MP_cc2_5  n5n  n5p  vdd  vdd  pm_vco  w=2000n  l=14n
MN_dp1_5  n5p  n4n  vt5  0   nm_vco  w=2000n  l=14n
MN_dp2_5  n5n  n4p  vt5  0   nm_vco  w=2000n  l=14n
MN_cs_5   vt5  vtune  0   0   nm_vco  w=2000n  l=21n

.ic V(n1p)=0.65 V(n1n)=0.05 V(n2p)=0.05 V(n2n)=0.65
.ic V(n3p)=0.65 V(n3n)=0.05 V(n4p)=0.05 V(n4n)=0.65
.ic V(n5p)=0.65 V(n5n)=0.05
.ic V(vt1)=0.1 V(vt2)=0.1 V(vt3)=0.1 V(vt4)=0.1 V(vt5)=0.1

.tran 1p 5n uic

.control
  run

  * Extract period at vtune=0.60V
  meas tran tr1 TRIG v(n3p) VAL=0.35 RISE=3
  meas tran tr2 TRIG v(n3p) VAL=0.35 RISE=4
  if tr1 > 0 and tr2 > tr1
    let t_period = tr2 - tr1
    let f_osc = 1.0/t_period
    echo "vtune=0.60V: f_osc [GHz]=" f_osc/1e9
  else
    echo "vtune=0.60V: oscillation not detected in 5ns window"
  end

  * Try vtune=0.65V for higher frequency
  alter Vtune dc = 0.65
  tran 1p 5n uic
  meas tran tr1b TRIG v(n3p) VAL=0.35 RISE=3
  meas tran tr2b TRIG v(n3p) VAL=0.35 RISE=4
  if tr1b > 0 and tr2b > tr1b
    let f_osc_h = 1.0/(tr2b - tr1b)
    echo "vtune=0.65V: f_osc [GHz]=" f_osc_h/1e9
  else
    echo "vtune=0.65V: oscillation not detected"
  end

  * Try vtune=0.55V
  alter Vtune dc = 0.55
  tran 1p 5n uic
  meas tran tr1c TRIG v(n3p) VAL=0.35 RISE=3
  meas tran tr2c TRIG v(n3p) VAL=0.35 RISE=4
  if tr1c > 0 and tr2c > tr1c
    let f_osc_l = 1.0/(tr2c - tr1c)
    echo "vtune=0.55V: f_osc [GHz]=" f_osc_l/1e9
  else
    echo "vtune=0.55V: oscillation not detected"
  end

  echo "================================================"
  echo "VCO SANITY SIM SUMMARY (predictive BSIM4 model)"
  echo "NOTE: Real ASAP7 BSIM-CMG model not available."
  echo "These results are from calibrated planar-equiv BSIM4."
  echo "================================================"

  quit
.endc

.end
