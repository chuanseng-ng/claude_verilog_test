* ============================================================
* VCO Kvco Sanity Simulation — Self-contained
* Extracts oscillation frequency vs vtune for 5-stage current-starved ring
* Uses BSIM4 predictive models inline (no .lib/.endl)
* ============================================================
VCO Kvco Sweep

* ---- Models ----
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

* ---- Supply ----
.param vdd_val=0.7
VDD vdd 0 DC 'vdd_val'

* ---- Tuning voltage ----
.param vtune_val=0.35
Vtune vtune 0 DC 'vtune_val'

* ---- Cap bank: all off (capsel=0) ----
Vcs0 capsel0 0 DC 0
Vcs1 capsel1 0 DC 0
Vcs2 capsel2 0 DC 0

* ============================================================
* Single differential VCO stage (inline for self-contained test)
* ============================================================
* Stage 1
MP_cc1_1  n1p  n1n  vdd  vdd  pfinfet_rvt  w=28n  l=14n
MP_cc2_1  n1n  n1p  vdd  vdd  pfinfet_rvt  w=28n  l=14n
MN_dp1_1  n1p  n5n  vt1  0   nfinfet_rvt  w=28n  l=14n
MN_dp2_1  n1n  n5p  vt1  0   nfinfet_rvt  w=28n  l=14n
MN_cs_1   vt1  vtune  0   0   nfinfet_rvt  w=28n  l=21n
MC0_1p    n1p  capsel0  0  0  nfinfet_rvt  w=14n  l=14n
MC0_1n    n1n  capsel0  0  0  nfinfet_rvt  w=14n  l=14n
MC1_1p    n1p  capsel1  0  0  nfinfet_rvt  w=28n  l=14n
MC1_1n    n1n  capsel1  0  0  nfinfet_rvt  w=28n  l=14n
MC2_1p    n1p  capsel2  0  0  nfinfet_rvt  w=56n  l=14n
MC2_1n    n1n  capsel2  0  0  nfinfet_rvt  w=56n  l=14n

* Stage 2
MP_cc1_2  n2p  n2n  vdd  vdd  pfinfet_rvt  w=28n  l=14n
MP_cc2_2  n2n  n2p  vdd  vdd  pfinfet_rvt  w=28n  l=14n
MN_dp1_2  n2p  n1n  vt2  0   nfinfet_rvt  w=28n  l=14n
MN_dp2_2  n2n  n1p  vt2  0   nfinfet_rvt  w=28n  l=14n
MN_cs_2   vt2  vtune  0   0   nfinfet_rvt  w=28n  l=21n
MC0_2p    n2p  capsel0  0  0  nfinfet_rvt  w=14n  l=14n
MC0_2n    n2n  capsel0  0  0  nfinfet_rvt  w=14n  l=14n
MC1_2p    n2p  capsel1  0  0  nfinfet_rvt  w=28n  l=14n
MC1_2n    n2n  capsel1  0  0  nfinfet_rvt  w=28n  l=14n
MC2_2p    n2p  capsel2  0  0  nfinfet_rvt  w=56n  l=14n
MC2_2n    n2n  capsel2  0  0  nfinfet_rvt  w=56n  l=14n

* Stage 3
MP_cc1_3  n3p  n3n  vdd  vdd  pfinfet_rvt  w=28n  l=14n
MP_cc2_3  n3n  n3p  vdd  vdd  pfinfet_rvt  w=28n  l=14n
MN_dp1_3  n3p  n2n  vt3  0   nfinfet_rvt  w=28n  l=14n
MN_dp2_3  n3n  n2p  vt3  0   nfinfet_rvt  w=28n  l=14n
MN_cs_3   vt3  vtune  0   0   nfinfet_rvt  w=28n  l=21n
MC0_3p    n3p  capsel0  0  0  nfinfet_rvt  w=14n  l=14n
MC0_3n    n3n  capsel0  0  0  nfinfet_rvt  w=14n  l=14n
MC1_3p    n3p  capsel1  0  0  nfinfet_rvt  w=28n  l=14n
MC1_3n    n3n  capsel1  0  0  nfinfet_rvt  w=28n  l=14n
MC2_3p    n3p  capsel2  0  0  nfinfet_rvt  w=56n  l=14n
MC2_3n    n3n  capsel2  0  0  nfinfet_rvt  w=56n  l=14n

* Stage 4
MP_cc1_4  n4p  n4n  vdd  vdd  pfinfet_rvt  w=28n  l=14n
MP_cc2_4  n4n  n4p  vdd  vdd  pfinfet_rvt  w=28n  l=14n
MN_dp1_4  n4p  n3n  vt4  0   nfinfet_rvt  w=28n  l=14n
MN_dp2_4  n4n  n3p  vt4  0   nfinfet_rvt  w=28n  l=14n
MN_cs_4   vt4  vtune  0   0   nfinfet_rvt  w=28n  l=21n
MC0_4p    n4p  capsel0  0  0  nfinfet_rvt  w=14n  l=14n
MC0_4n    n4n  capsel0  0  0  nfinfet_rvt  w=14n  l=14n
MC1_4p    n4p  capsel1  0  0  nfinfet_rvt  w=28n  l=14n
MC1_4n    n4n  capsel1  0  0  nfinfet_rvt  w=28n  l=14n
MC2_4p    n4p  capsel2  0  0  nfinfet_rvt  w=56n  l=14n
MC2_4n    n4n  capsel2  0  0  nfinfet_rvt  w=56n  l=14n

* Stage 5 (ring closure: inp=n4, out=n5 -> feeds back to stage1 swapped)
MP_cc1_5  n5p  n5n  vdd  vdd  pfinfet_rvt  w=28n  l=14n
MP_cc2_5  n5n  n5p  vdd  vdd  pfinfet_rvt  w=28n  l=14n
MN_dp1_5  n5p  n4n  vt5  0   nfinfet_rvt  w=28n  l=14n
MN_dp2_5  n5n  n4p  vt5  0   nfinfet_rvt  w=28n  l=14n
MN_cs_5   vt5  vtune  0   0   nfinfet_rvt  w=28n  l=21n
MC0_5p    n5p  capsel0  0  0  nfinfet_rvt  w=14n  l=14n
MC0_5n    n5n  capsel0  0  0  nfinfet_rvt  w=14n  l=14n
MC1_5p    n5p  capsel1  0  0  nfinfet_rvt  w=28n  l=14n
MC1_5n    n5n  capsel1  0  0  nfinfet_rvt  w=28n  l=14n
MC2_5p    n5p  capsel2  0  0  nfinfet_rvt  w=56n  l=14n
MC2_5n    n5n  capsel2  0  0  nfinfet_rvt  w=56n  l=14n

* ---- Initial conditions (kick-start oscillation) ----
.ic V(n1p)=0.6 V(n1n)=0.1 V(n2p)=0.1 V(n2n)=0.6
.ic V(n3p)=0.6 V(n3n)=0.1 V(n4p)=0.1 V(n4n)=0.6
.ic V(n5p)=0.6 V(n5n)=0.1

.tran 5p 15n uic

.control
  * Sweep vtune, extract frequency
  let vtune_pts = [ 0.10 0.20 0.30 0.35 0.40 0.50 0.60 ]
  let freq_out = vector(7)
  let ii = 0
  dowhile ii < 7
    alter Vtune dc = vtune_pts[ii]
    tran 5p 15n uic
    * Find period between consecutive zero-crossings of n3p at 0.35V
    meas tran trise1 TRIG v(n3p) VAL=0.35 RISE=5
    meas tran trise2 TRIG v(n3p) VAL=0.35 RISE=6
    if trise2 > trise1 and trise1 > 0
      let freq_out[ii] = 1.0 / (trise2 - trise1)
    else
      let freq_out[ii] = -1
    end
    echo "vtune=" vtune_pts[ii] "V  f_osc=" freq_out[ii] "Hz"
    let ii = ii + 1
  end

  * Compute Kvco over fine range (0.3 to 0.4 V = 0.1V window around nominal)
  * indices: 0.30->idx2, 0.40->idx4
  let kvco_fine = (freq_out[4] - freq_out[2]) / 0.10
  let f_nom = freq_out[3]
  let f_hi  = freq_out[6]

  echo "============================================"
  echo "VCO KVCO SUMMARY:"
  echo "  f_nom at vtune=0.35V [GHz]:" f_nom/1e9
  echo "  f_hi  at vtune=0.60V [GHz]:" f_hi/1e9
  echo "  Kvco_fine (0.30-0.40V range) [MHz/V]:" kvco_fine/1e6
  if f_hi >= 1.4e9
    echo "  STATUS: PASS -- f >= 1.4 GHz at vtune=0.60V (TT)"
    echo "  NOTE: SS corner expected ~10-15% lower; verify with SS models"
  else
    echo "  STATUS: WARN -- f < 1.4 GHz at vtune=0.60V"
    echo "  SS corner will be further below 1.4 GHz -> open fix_request"
  end
  if abs(kvco_fine/1e6 - 80) < 40
    echo "  Kvco_fine within 50% of 80 MHz/V target: acceptable"
  else
    echo "  Kvco_fine far from 80 MHz/V: sizing review needed"
  end
  echo "============================================"

  quit
.endc

.end
