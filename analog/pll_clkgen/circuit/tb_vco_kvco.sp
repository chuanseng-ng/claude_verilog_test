* ============================================================
* Testbench: VCO Kvco sweep + free-running frequency
* Sweeps vtune from 0.05 V to 0.65 V in 50 mV steps.
* Measures oscillation frequency by observing the ring VCO output
* via a transient simulation at each vtune bias point.
*
* Strategy (ngspice batch):
*   1. For each vtune step: set DC bias, run .tran for 10 ns, FFT vco_outp.
*   2. Extract peak frequency from .meas or manual inspection of output.
*
* Simplified approach: at each vtune, run short .tran and use .measure
* to find the first rising crossing -> extract period -> f = 1/T
*
* This tb sweeps vtune as a parameter and uses .measure TRIG/TARG.
* ============================================================

.title VCO Kvco Sweep Testbench
.include asap7_predictive.pm
.include ring_vco.sp

* ---- Supply and global parameters ----
.param vdd_val = 0.7
.param vtune_val = 0.35
.param capsel_val = 0

VDD   vdd   gnd   DC 'vdd_val'

* ---- Tuning voltage (parameter-driven for sweep) ----
Vtune  vtune  gnd  DC 'vtune_val'

* ---- Cap bank control: all bits = 0 (minimum cap = fastest) ----
Vcapsel0  capsel0  gnd  DC 'capsel_val'
Vcapsel1  capsel1  gnd  DC 0
Vcapsel2  capsel2  gnd  DC 0

* ---- VCO instance ----
Xvco  vco_outp  vco_outn  vtune
+     capsel0  capsel1  capsel2  vdd  gnd  ring_vco

* ---- Initial conditions to kick-start oscillation ----
.ic V(vco_outp) = 0.6  V(vco_outn) = 0.1
.ic V(Xvco.X1.s1_outp) = 0.1  V(Xvco.X1.s1_outn) = 0.6
.ic V(Xvco.X2.s2_outp) = 0.6  V(Xvco.X2.s2_outn) = 0.1
.ic V(Xvco.X3.s3_outp) = 0.1  V(Xvco.X3.s3_outn) = 0.6
.ic V(Xvco.X4.s4_outp) = 0.6  V(Xvco.X4.s4_outn) = 0.1
.ic V(Xvco.X5.s5_outp) = 0.1  V(Xvco.X5.s5_outn) = 0.6

* ---- Transient simulation (long enough for 5+ cycles at ~1 GHz) ----
.tran 10p 20n uic

* ---- Measure period: first two rising crossings of vco_outp at 0.35 V ----
.measure tran t_rise1 TRIG V(vco_outp) VAL=0.35 RISE=2
.measure tran t_rise2 TRIG V(vco_outp) VAL=0.35 RISE=3
.measure tran t_period PARAM='t_rise2 - t_rise1'
.measure tran f_osc PARAM='1.0 / t_period'

* ---- Parametric sweep over vtune ----
.control
  * Run sweep over vtune from 0.10 to 0.60 V in 0.10 V steps
  * (Coarser sweep to get Kvco; for full sanity check)
  let vtune_arr = [ 0.10 0.15 0.20 0.25 0.30 0.35 0.40 0.45 0.50 0.55 0.60 ]
  let n_pts = length(vtune_arr)
  let freq_arr = vector(n_pts)
  let i = 0
  dowhile i < n_pts
    alter Vtune dc = vtune_arr[i]
    tran 10p 20n uic
    * measure period between 2nd and 3rd rising edge at 0.35V threshold
    meas tran t_r1 TRIG v(vco_outp) VAL=0.35 RISE=2
    meas tran t_r2 TRIG v(vco_outp) VAL=0.35 RISE=3
    if t_r1 > 0 and t_r2 > 0
      let period = t_r2 - t_r1
      let freq_arr[i] = 1.0 / period
    else
      let freq_arr[i] = 0
    end
    echo "vtune=" vtune_arr[i] " f_osc=" freq_arr[i]
    let i = i + 1
  end

  * Compute Kvco from linear fit (endpoints)
  * Kvco_fine = (f_max - f_min) / (vtune_max - vtune_min)
  let f_at_0p10 = freq_arr[0]
  let f_at_0p60 = freq_arr[10]
  let kvco_total = (f_at_0p60 - f_at_0p10) / 0.50
  echo "=========================================="
  echo "KVCO TOTAL (0.1V to 0.6V sweep) [Hz/V]:"
  print kvco_total
  echo "f_osc at vtune=0.10V:" f_at_0p10
  echo "f_osc at vtune=0.35V:" freq_arr[5]
  echo "f_osc at vtune=0.60V:" f_at_0p60
  echo "=========================================="

  * Check if 1.4 GHz is reachable at vtune=0.60V
  * (SS corner not simulated here; this is TT; SS would shift lower)
  if f_at_0p60 >= 1.4e9
    echo "PASS: f_osc >= 1.4 GHz at vtune=0.6V (TT corner)"
  else
    echo "WARN: f_osc < 1.4 GHz at vtune=0.6V (TT corner) -> SS corner risk"
  end

  quit
.endc

.end
