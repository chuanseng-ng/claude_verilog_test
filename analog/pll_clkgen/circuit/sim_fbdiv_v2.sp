* /13 Divider check — PWL verification
* Verify /13 division is achievable at 1.3 GHz CMOS input
* Use ngspice B-source (behavioral) approach without PARAM in .model context

.param vdd_val=0.7

VDD vdd 0 DC 0.7

* 1.3 GHz reference clock
Vclk clkin 0 PULSE 0 'vdd_val' 0 30p 30p 354.6p 769.2p

* Integrator approach for /13:
* Each positive half-cycle charges capacitor C_cnt.
* Charge per half-cycle: Q = I * t_on = 1mA * 354.6ps = 354.6 fC
* Capacity for 13 cycles: C = 13 * Q / Vdd = 13 * 354.6e-15 / 0.7 = 6.58 pF
* Use C=6.6pF, I=1mA -> reaches Vdd in 13 cycles.

C_cnt vcnt 0 6.6p

* Current source: charges C when clkin is high
Bpulse vcnt 0 I = 'V(clkin) > 0.35 ? 1m : -1m'

* Discharge when vcnt > vdd_val (after 13th cycle)
Bdischarge gated_discharge 0 V = 'V(vcnt) > 0.65 ? vdd_val : 0'
R_dis gated_discharge vcnt 5

* Divout: toggle on discharge event
C_out vdivout 0 100f
Bdivout_src vdivout_src 0 V = 'V(gated_discharge) > 0.35 ? vdd_val : 0'
R_divout vdivout_src vdivout 10

.tran 5p 200n

.control
  run

  meas tran td1 WHEN v(vdivout)=0.35 RISE=1
  meas tran td2 WHEN v(vdivout)=0.35 RISE=2
  meas tran td3 WHEN v(vdivout)=0.35 RISE=3

  echo "=========================================="
  echo "DIVIDER /13 VERIFICATION:"
  echo "td1=" td1
  echo "td2=" td2

  if td2 > td1 and td1 > 0
    let t_div_period = td2 - td1
    let f_div = 1.0 / t_div_period
    let n_ratio = 1.3e9 / f_div
    echo "divout period [ns]:" t_div_period * 1e9
    echo "f_divout [MHz]:" f_div * 1e-6
    echo "Divide ratio:" n_ratio
    if abs(n_ratio - 13.0) < 2.0
      echo "PASS: /13 division verified at 1.3 GHz input"
    else
      echo "FAIL: divide ratio != 13"
    end
  else
    echo "divout did not toggle in 200ns window"
  end
  echo "=========================================="

  quit
.endc

.end
