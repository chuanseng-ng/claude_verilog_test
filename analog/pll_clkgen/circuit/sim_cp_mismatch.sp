* ============================================================
* Charge Pump UP/DN Current Matching — Self-contained
* DC sweep: Iup vs Idn vs Vcpout
* Models inline, no .lib/.endl
* ============================================================
CP Mismatch Sim

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

* ============================================================
* Simplified CP: two matched mirror legs, switched by ideal switches
* UP branch: PMOS mirror (36 fins, L=21nm) diode ref + copy
* DN branch: NMOS mirror (20 fins, L=21nm) diode ref + copy
* Ideal switch: voltage-controlled current source approach
* For matching measurement: both UP and DN measured separately
* ============================================================

* --- UP branch (PMOS mirror diode-connected ref) ---
* Reference: diode-connected, driven by PMOS-side bias current sink
* Bias: NMOS current sink (vbias_n sets ~ 0.5 mA into PMOS ref)
MN_bias_up   vbias_p_int  vbias_p_int  0  0  nfinfet_rvt  w=140n  l=21n
* The PMOS reference (diode-connected)
MP_ref  vbias_p_int  vbias_p_int  vdd  vdd  pfinfet_rvt  w=252n  l=21n
* PMOS mirror copy to output node (vcpout_up = swept node)
MP_src  vcpout_up  vbias_p_int  vdd  vdd  pfinfet_rvt  w=252n  l=21n
* Voltage source at output to sweep compliance and measure current
Vcp_up  vcpout_up  0  DC 0.35

* --- DN branch (NMOS mirror) ---
* Reference: diode-connected NMOS
MN_ref  vbias_n_int  vbias_n_int  0  0  nfinfet_rvt  w=140n  l=21n
* Bias: PMOS current source (same Vbias_p from PMOS mirror ref)
MP_bias_dn  vbias_n_int  vbias_p_int  vdd  vdd  pfinfet_rvt  w=252n  l=21n
* NMOS mirror copy to output
MN_snk  vcpout_dn  vbias_n_int  0  0  nfinfet_rvt  w=140n  l=21n
* Voltage source at output
Vcp_dn  vcpout_dn  0  DC 0.35

.dc Vcp_up 0.10 0.60 0.025

.control
  * Measure Iup (current from vdd through MP_src into vcpout_up)
  dc Vcp_up 0.10 0.60 0.025
  let Iup = -i(Vcp_up)

  * For Idn: sweep vcpout_dn (same range)
  let Vcp_up_save = 0.35
  alter Vcp_up dc = 0.35
  dc Vcp_dn 0.10 0.60 0.025
  let Idn = i(Vcp_dn)

  echo "============================================"
  echo "CHARGE PUMP MISMATCH CHECK:"
  echo "Vcpout=0.10V: Iup=" Iup[0]*1e6 "uA  Idn=" Idn[0]*1e6 "uA"
  echo "Vcpout=0.35V: Iup=" Iup[10]*1e6 "uA  Idn=" Idn[10]*1e6 "uA"
  echo "Vcpout=0.60V: Iup=" Iup[20]*1e6 "uA  Idn=" Idn[20]*1e6 "uA"

  let iup_nom = Iup[10]*1e6
  let idn_nom = Idn[10]*1e6
  let imean_nom = (iup_nom + idn_nom)/2
  if imean_nom > 0
    let mm_pct = (iup_nom - idn_nom)/imean_nom*100
  else
    let mm_pct = 999
  end
  echo "Nominal mismatch (Vcpout=0.35V): " mm_pct " %"
  if abs(mm_pct) <= 1.0
    echo "PASS: mismatch <= 1.0%"
  else
    echo "WARN: mismatch > 1.0% at nominal"
  end
  echo "============================================"

  quit
.endc

.end
