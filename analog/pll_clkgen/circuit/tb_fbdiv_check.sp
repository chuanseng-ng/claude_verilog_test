* ============================================================
* Testbench: Feedback Divider /13 verification
* Drives a 1.3 GHz (nominal) single-ended CMOS clock into the divider
* and verifies div_out frequency = 1.3e9 / 13 = 100 MHz.
*
* NOTE: The full feedback_div subcircuit includes the CML input buffer
* which requires differential inputs. For this sanity check we:
*   1. Test the CMOS /13 counter (div13_cmos) directly with a CMOS clock
*      since the CML buffer is a level-shifter, its function is separately
*      verified by inspection (differential pair with appropriate bias).
*   2. Measure div_out period to confirm /13 division.
* ============================================================

.title Feedback Divider /13 Check Testbench
.include asap7_predictive.pm
.include feedback_div.sp

* ---- Supply ----
.param vdd_val = 0.7
VDD  vdd  gnd  DC 'vdd_val'

* ---- 1.3 GHz CMOS clock (period = 769.2 ps) ----
* Use PULSE source: period = 769.2ps, rise/fall = 30ps (realistic CMOS edge)
Vclk  clkin  gnd  PULSE 0 'vdd_val' 0 30p 30p 354.6p 769.2p

* ---- Instantiate CMOS /13 counter directly ----
* (Bypasses CML buffer for this sanity check)
Xdiv13  clkin  divout  vdd  gnd  div13_cmos

* ---- Measure divout period ----
.tran 5p 300n uic

.control
  run
  * Find period of divout
  * Look for rising edges of divout after initial settling (after 50 ns)
  meas tran t_d1 TRIG v(divout) VAL=0.35 RISE=3
  meas tran t_d2 TRIG v(divout) VAL=0.35 RISE=4
  let t_period_div = t_d2 - t_d1
  let f_divout = 1.0 / t_period_div
  let n_div_measured = 1.282e9 / f_divout

  echo "=========================================="
  echo "FEEDBACK DIVIDER /13 CHECK:"
  echo "  Input clock: 1.3 GHz (769.2 ps period)"
  echo "  divout period [ns]:" t_period_div*1e9
  echo "  divout frequency [MHz]:" f_divout*1e-6
  echo "  Measured divide ratio:" n_div_measured
  if abs(n_div_measured - 13) < 0.5
    echo "  PASS: Divide ratio confirmed as /13"
  else
    echo "  FAIL: Divide ratio != 13 -> check counter logic"
  end
  echo "=========================================="

  * Also measure at 1.4 GHz (SS worst-case input)
  alter Vclk PULSE 0 'vdd_val' 0 30p 30p 321.4p 714.3p
  tran 5p 300n uic
  meas tran t_d1h TRIG v(divout) VAL=0.35 RISE=3
  meas tran t_d2h TRIG v(divout) VAL=0.35 RISE=4
  let t_period_div_h = t_d2h - t_d1h
  let f_divout_h = 1.0 / t_period_div_h
  let n_div_h = 1.4e9 / f_divout_h

  echo "  At 1.4 GHz input:"
  echo "  divout freq [MHz]:" f_divout_h*1e-6
  echo "  Divide ratio:" n_div_h
  if abs(n_div_h - 13) < 0.5
    echo "  PASS: /13 confirmed at 1.4 GHz"
  else
    echo "  FAIL: /13 failed at 1.4 GHz"
  end

  quit
.endc

.end
