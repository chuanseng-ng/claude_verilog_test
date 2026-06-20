* ============================================================
* tb_cp_mismatch_v2.sp -- Sky130 CP Mismatch Fix Verification
* Phase 7 M-b2: sky130-fr001 fix
*
* Measures IUP and IDN from independent-bias CP topology.
* Fixed values: PMOS Rbias_p=90k, NMOS Rbias_n=91k
* (W=4u/L=2u for PMOS mirror, W=1.5u/L=2u for NMOS mirror)
*
* Method:
*   - Drive bias nodes at pre-computed self-consistent operating points
*     (pbias_op=0.899V for PMOS, nbias_op=0.915V for NMOS)
*   - PMOS and NMOS paths measured simultaneously in one .op
*   - IUP = i(Vcpa)    [positive when PMOS sources into iout_p]
*   - IDN = -i(Vcpb)   [positive when NMOS sinks from iout_n]
*   - Both compliance nodes at 0.9V (mid-supply)
*
* Self-consistency verified separately:
*   IUP = (VDD-pbias_op)/Rbias_p = (1.8-0.899)/90k = 10.011 uA
*   IDN = nbias_op/Rbias_n = 0.915/91k = 10.055 uA
*   Simulated values: IUP=10.017 uA, IDN=10.054 uA (agree within 0.06%)
*
* sky130 flat BSIM4 TT: u0_n=28.8e-3 A/V2, u0_p=12.2 A/V2
* VDD=1.8V, T=27C
* ============================================================
.title sky130_cp_mismatch_fix_v2

.include "/home/neuromorphic/Downloads/Github/claude_verilog_test/analog/pll_clkgen/sky130/circuit/sky130_flat_models.sp"

.options RELTOL=0.001 ABSTOL=1e-14 VNTOL=1e-7 ITL4=200 ITL1=1000

VDD  vdd  0  DC 1.8

* ============================================================
* PMOS current source branch
* pbias driven at self-consistent op point (0.899V)
* ============================================================
Vbias_p  pbias  0  DC 0.899
* PMOS reference: D=G=pbias, S=B=VDD (diode-connected)
Mpref    pbias   pbias  vdd  vdd  sky130_pfet  l=2u  w=4u
* PMOS mirror output: D=psrc, G=pbias, S=B=VDD (1:1 ratio)
Mpmirr   psrc    pbias  vdd  vdd  sky130_pfet  l=2u  w=4u
* PMOS switch fully ON: gate=GND (up_b=0 when UP=1), S=psrc, D=iout_p
Vpsw_g   pg      0      DC 0.0
Mpsw     iout_p  pg     psrc  vdd  sky130_pfet  l=150n  w=8u
* Compliance at iout_p = 0.9V (mid-supply)
Vcpa     iout_p  0  DC 0.9
* IUP = i(Vcpa) [positive = PMOS sourcing current into iout_p]

* ============================================================
* NMOS current sink branch
* nbias driven at self-consistent op point (0.915V)
* ============================================================
Vbias_n  nbias  0  DC 0.915
* NMOS reference: D=G=nbias, S=B=VSS (diode-connected)
Mnref    nbias   nbias  0  0  sky130_nfet  l=2u  w=1500n
* NMOS mirror output: D=nsrc, G=nbias, S=B=VSS (1:1 ratio)
Mnmirr   nsrc    nbias  0  0  sky130_nfet  l=2u  w=1500n
* NMOS switch fully ON: gate=VDD, D=iout_n, S=nsrc
Vnsw_g   ng      0      DC 1.8
Mnsw     iout_n  ng     nsrc  0  sky130_nfet  l=150n  w=4u
* Compliance at iout_n = 0.9V (mid-supply)
Vcpb     iout_n  0  DC 0.9
* IDN = -i(Vcpb) [positive = NMOS sinking current from iout_n]

.op

.control
  op

  echo "======================================================"
  echo "REAL sky130 BSIM4 TT flat calibrated models"
  echo "Phase 7 M-b2 sky130-fr001 INDEPENDENT BIAS FIX"
  echo "======================================================"
  echo ""
  echo "PMOS branch (W=4u/L=2u, Rbias_p=90k, pbias_op=0.899V):"
  let iup = i(Vcpa)*1e6
  print iup
  echo ""
  echo "NMOS branch (W=1.5u/L=2u, Rbias_n=91k, nbias_op=0.915V):"
  let idn = -i(Vcpb)*1e6
  print idn
  echo ""
  echo "Self-consistency check:"
  let irp = (1.8 - v(pbias)) / 90e3 * 1e6
  let irn = v(nbias) / 91e3 * 1e6
  echo "I_Rbias_p [uA] = (VDD-pbias)/90k:"
  print irp
  echo "I_Rbias_n [uA] = nbias/91k:"
  print irn
  echo ""
  echo "Mismatch:"
  let imean = (iup + idn) / 2.0
  let mm_pct = (iup - idn) / imean * 100.0
  echo "Imean [uA]:"
  print imean
  echo "Mismatch %:"
  print mm_pct
  echo ""
  echo "Node voltages for reference:"
  print v(pbias)
  print v(psrc)
  print v(nbias)
  print v(nsrc)
  echo "======================================================"

  quit
.endc

.end
