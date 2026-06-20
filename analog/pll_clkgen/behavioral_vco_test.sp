* behavioral_vco_test.sp
* Behavioral relaxation VCO for ngspice smoke test
* Topology: B-source current-controlled oscillator
* f_osc = Kvco * Vctrl / (2 * C * V_swing)
* Target: ~1.282 GHz at Vctrl = 0.5V (rough behavioral stand-in)

.title PLL_VCO_Behavioral_Test

* Supply and bias
Vdd  vdd  0  DC 0.7
Vctrl vctrl 0 DC 0.5

* Behavioral VCO using two B-sources + capacitor (ring-osc approximation)
* State variable: Vosc ramps with frequency = Kvco * Vctrl
* Kvco = 1.0 GHz/V (behavioral), so at 0.5V -> 500 MHz for this test
* (Full 1.282 GHz requires divider; this is a sanity sim)

* Capacitor to integrate charge
C1  vosc  0  1f  IC=0

* Current source: I = C * 2*pi*f = C * 2*pi * Kvco * Vctrl
* Kvco = 2e9 rad/s/V; C = 1f
* At Vctrl=0.5V: I = 1e-15 * 2*pi*1e9*0.5 = ~3.14e-6 A
B1  vosc  0  I = 1e-15 * 2 * 3.14159265 * 1e9 * v(vctrl) * (1 - v(vosc)/0.7)

* Limiter to keep vosc bounded [0, 0.7]
.model Dclamp D (IS=1e-14)
D1  vosc  vdd  Dclamp
D2  0     vosc Dclamp

* Output buffer (VCVS)
Ebuf vout  0  vosc 0  1.0

.tran 10p 5n UIC

* Measure approximate frequency by tracking zero-crossings (behavioral)
.meas tran t_rise WHEN v(vosc)=0.35 RISE=1
.meas tran t_rise2 WHEN v(vosc)=0.35 RISE=2
.meas tran f_osc PARAM='1/(t_rise2-t_rise)'

.control
run
print t_rise t_rise2 f_osc
write /tmp/vco_test_out.raw
.endc

.end
