* ============================================================
* Sky130 Ring VCO Kvco Measurement
* 5-stage current-starved ring VCO — FLAT BSIM4 models
* (Calibrated sky130 TT-corner equivalent; subcircuit PM3 models
*  require ngspice BSIM4 binning scope fix not available in this env)
*
* REAL sky130 parameters extracted from:
*   sky130_fd_pr__nfet_01v8__tt.pm3.spice (bin L=150-180nm, W=1-1.26um)
*   sky130_fd_pr__pfet_01v8__tt.pm3.spice (corresponding bin)
*
* Sweep Vtune: 0.3V, 0.6V, 0.9V, 1.2V, 1.5V -> measure f_osc -> Kvco
* ============================================================

.title sky130_vco_kvco_tt_flat

* ── REAL sky130-calibrated flat BSIM4 models ─────────────
.include "/home/neuromorphic/Downloads/Github/claude_verilog_test/analog/pll_clkgen/sky130/circuit/sky130_flat_models.sp"

* ── Simulator options ────────────────────────────────────
.options RELTOL=0.01 ABSTOL=1e-12 VNTOL=1e-6 ITL4=200 ITL1=500 method=gear

* ── Supply ────────────────────────────────────────────────
Vdd vdd 0 1.8
Vtune vtune 0 0.9

* ── 5-stage current-starved ring VCO (inline, flat devices) ─
* Stage 1: in=n5, out=n1
* PMOS pull-up inverter (source=vdd, d=n1, g=n5)
MP1  n1 n5 vdd vdd sky130_pfet w=2u l=150n
* NMOS pull-down inverter (d=n1, g=n5, s=nc1)
MN1  n1 n5 nc1 0 sky130_nfet w=1u l=150n
* NMOS current starver tail (d=nc1, g=vtune, s=vss)
MCS1 nc1 vtune 0 0 sky130_nfet w=2u l=500n

* Stage 2: in=n1, out=n2
MP2  n2 n1 vdd vdd sky130_pfet w=2u l=150n
MN2  n2 n1 nc2 0 sky130_nfet w=1u l=150n
MCS2 nc2 vtune 0 0 sky130_nfet w=2u l=500n

* Stage 3: in=n2, out=n3
MP3  n3 n2 vdd vdd sky130_pfet w=2u l=150n
MN3  n3 n2 nc3 0 sky130_nfet w=1u l=150n
MCS3 nc3 vtune 0 0 sky130_nfet w=2u l=500n

* Stage 4: in=n3, out=n4
MP4  n4 n3 vdd vdd sky130_pfet w=2u l=150n
MN4  n4 n3 nc4 0 sky130_nfet w=1u l=150n
MCS4 nc4 vtune 0 0 sky130_nfet w=2u l=500n

* Stage 5: in=n4, out=n5 (ring closure)
MP5  n5 n4 vdd vdd sky130_pfet w=2u l=150n
MN5  n5 n4 nc5 0 sky130_nfet w=1u l=150n
MCS5 nc5 vtune 0 0 sky130_nfet w=2u l=500n

* Output buffer from n1
MPB  vco_out n1 vdd vdd sky130_pfet w=4u l=150n
MNB  vco_out n1 0   0   sky130_nfet w=2u l=150n

* ── Initial conditions (kick-start ring oscillation) ─────
.ic v(n1)=0 v(n2)=1.8 v(n3)=0 v(n4)=1.8 v(n5)=0

* ── Transient: 500 ns, measure after 200 ns (settled) ───
.tran 0.5n 500n

* ── Measure period (frequency) at Vtune=0.9V ─────────────
.measure tran T_period TRIG v(vco_out) VAL=0.9 RISE=1 TD=200n
+                       TARG v(vco_out) VAL=0.9 RISE=2 TD=200n
.measure tran f_MHz PARAM='1e-6/T_period'

.print tran v(vco_out) v(n1) v(n3)

.control

  * ===== Vtune sweep: 0.3V, 0.6V, 0.9V, 1.2V, 1.5V =====
  echo "==================================================="
  echo "REAL SKY130 ngspice VCO Kvco Sweep (TT flat model)"
  echo "Parameters: u0_n=28.8mA/V2 Vth0_n=0.419V toxe=4.148nm"
  echo "            u0_p=12.2mA/V2 Vth0_p=-0.475V"
  echo "==================================================="

  let vtune_pts = [ 0.3 0.6 0.9 1.2 1.5 ]
  let freq_arr  = vector(5)
  let ii = 0

  dowhile ii < 5
    alter Vtune dc = vtune_pts[ii]
    tran 0.5n 500n
    * Measure period between consecutive rising edges after settling
    meas tran tr1 TRIG v(vco_out) VAL=0.9 RISE=3 TD=200n
    meas tran tr2 TRIG v(vco_out) VAL=0.9 RISE=4 TD=200n
    if tr2 > tr1 and tr1 > 0
      let period_v = tr2 - tr1
      let freq_arr[ii] = 1.0 / period_v
    else
      let freq_arr[ii] = -1
    end
    echo "Vtune=" vtune_pts[ii] "V  f_osc=" freq_arr[ii]/1e6 "MHz"
    let ii = ii + 1
  end

  * Kvco extraction (0.3V to 1.5V total span, linear fit)
  let f_lo = freq_arr[0]
  let f_hi = freq_arr[4]
  let f_mid = freq_arr[2]
  if f_lo > 0 and f_hi > 0
    let kvco = (f_hi - f_lo) / (1.5 - 0.3)
    echo "==================================================="
    echo "REAL SKY130 ngspice TT RESULTS:"
    echo "  f @ Vtune=0.3V  : " f_lo/1e6   " MHz"
    echo "  f @ Vtune=0.9V  : " f_mid/1e6  " MHz (target: 100 MHz)"
    echo "  f @ Vtune=1.5V  : " f_hi/1e6   " MHz"
    echo "  Kvco (0.3-1.5V) : " kvco/1e6   " MHz/V"
    let fmin_mhz = f_lo/1e6
    let fmax_mhz = f_hi/1e6
    echo "  Tuning range    : " fmin_mhz " to " fmax_mhz " MHz"
    if f_mid >= 80e6 and f_mid <= 120e6
      echo "  STATUS: PASS — f_center within 20% of 100 MHz target"
    else
      echo "  STATUS: WARN — f_center outside 20% of 100 MHz target"
    end
    if f_lo <= 100e6 and f_hi >= 100e6
      echo "  STATUS: PASS — 100 MHz within tuning range"
    else
      echo "  STATUS: WARN — 100 MHz not within tuning range"
    end
  else
    echo "  WARN: Convergence issue — could not measure all frequencies"
  end
  echo "==================================================="

  quit
.endc

.end
