* ============================================================
* Testbench: Charge Pump UP/DN current matching
* Measures Iup and Idn at multiple Vcpout (output compliance) voltages.
* Reports mismatch percentage = (Iup - Idn) / ((Iup+Idn)/2) * 100
* Target: <= 1% mismatch across Vcpout = [0.1 V, 0.6 V]
* ============================================================

.title Charge Pump UP/DN Mismatch Testbench
.include asap7_predictive.pm
.include charge_pump.sp

* ---- Supply and global parameters ----
.param vdd_val = 0.7
VDD   vdd   gnd   DC 'vdd_val'

* ---- Bias voltages (representing Bias_Ref nominal output) ----
* vbias_p: PMOS gate, ~0.40 V below vdd -> ~0.30 V (Vgs_p = -0.4V relative to vdd)
* Actual: vbias_p at VDD - |Vgs_p| ~ 0.7 - 0.4 = 0.30V from gnd
* For CP PMOS reference: MP_ref Vgs = vdd - vbias_p = 0.4V -> Id ~ 36*15u = 540 uA
* We need ~1 mA, so target vbias_p ~ VDD - 0.36 = 0.34V
Vbias_p  vbias_p  gnd  DC 0.34
*
* vbias_n: NMOS gate ~ 0.38 V (Vgs_n = 0.38V -> above Vth=0.276V -> in saturation)
* Id ~ 20*28u = 560 uA (close to 0.5 mA per mirror half)
Vbias_n  vbias_n  gnd  DC 0.38

* ---- UP pulse (held high for DC measurement of Iup) ----
Vup  up_ctrl  gnd  DC 1 PWL 0 0 1n 0 1.1n 'vdd_val' 50n 'vdd_val'
Vdn  dn_ctrl  gnd  DC 0

* ---- CP output voltage (sweep for mismatch vs Vcpout) ----
Vcpout  cpout  gnd  DC 0.35

* ---- CP instance ----
Xcp  up_ctrl  dn_ctrl  cpout  vbias_p  vbias_n  vdd  gnd  charge_pump

* ---- DC measurement of UP current ----
.dc Vcpout 0.10 0.60 0.05

.control
  * ---- Measure Iup: UP=1, DN=0 ----
  alter Vup dc = 'vdd_val'
  alter Vdn dc = 0
  dc Vcpout 0.10 0.60 0.05
  * Current sourced from vdd into cpout through PMOS switch = -I(VDD) adjusted
  * Easier: measure current through Vcpout source (current into node from voltage source)
  let Iup_arr = -i(Vcpout)
  * Note: Vcpout sinks current when CP sources (Iup > 0 into cpout)

  * ---- Measure Idn: UP=0, DN=1 ----
  alter Vup dc = 0
  alter Vdn dc = 'vdd_val'
  dc Vcpout 0.10 0.60 0.05
  let Idn_arr = i(Vcpout)
  * Idn flows out of cpout into NMOS sink (positive = current leaving node)

  * ---- Print results ----
  echo "Vcpout [V] | Iup [uA] | Idn [uA] | Mismatch [%]"
  echo "------------------------------------------------------"
  let n = length(Iup_arr)
  let vi = 0
  dowhile vi < n
    let vcpout_v = 0.10 + vi * 0.05
    let iup = Iup_arr[vi] * 1e6
    let idn = Idn_arr[vi] * 1e6
    let imean = (iup + idn) / 2.0
    if imean > 0
      let mismatch = (iup - idn) / imean * 100.0
    else
      let mismatch = 0
    end
    echo vcpout_v " | " iup " | " idn " | " mismatch
    let vi = vi + 1
  end

  * ---- Summary at nominal (Vcpout=0.35V, index 5) ----
  let iup_nom = Iup_arr[5] * 1e6
  let idn_nom = Idn_arr[5] * 1e6
  let imean_nom = (iup_nom + idn_nom) / 2.0
  let mismatch_nom = (iup_nom - idn_nom) / imean_nom * 100.0
  echo "=========================================="
  echo "Nominal (Vcpout=0.35V):"
  echo "  Iup = " iup_nom " uA"
  echo "  Idn = " idn_nom " uA"
  echo "  Mismatch = " mismatch_nom " %"
  if abs(mismatch_nom) <= 1.0
    echo "  PASS: mismatch <= 1%"
  else
    echo "  FAIL: mismatch > 1% -> check mirror sizing"
  end
  echo "=========================================="

  quit
.endc

.end
