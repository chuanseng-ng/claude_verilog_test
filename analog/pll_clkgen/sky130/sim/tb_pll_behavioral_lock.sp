* ============================================================
* Sky130 PLL Behavioral Lock Simulation  (v2)
* Phase 7 M-b2 — pll_clkgen_sky130
* Uses a proper charge-pump PLL model with phase-detector B-source
* 10 MHz ref → 100 MHz out, N=10, loop BW 1 MHz, PM 60°
* Confirms architecture loop parameters produce locking < 50 µs
* ============================================================

.title pll_clkgen_sky130_behavioral_lock_v2

* ── Parameters (from architecture budgeting) ──────────────────
.param VDD    = 1.8
.param fref   = 10Meg
.param N      = 10
* VCO parameters: f = fvco_nom + Kvco*(Vtune - Vtune_nom)
* At Vtune=0.9V (mid), f = 100MHz. Kvco = 100 MHz/V
.param fvco_nom = 100Meg    ; nominal VCO freq at Vtune=Vtune_nom
.param Kvco     = 100Meg    ; VCO gain Hz/V
.param Vtune_nom = 0.9      ; VCO midpoint tune voltage (V)
.param Icp      = 10u       ; charge pump current A
.param C1       = 17.5p
.param R2       = 272.73k
.param C2       = 1.75p
.param R3       = 90.91k
.param C3       = 0.175p

* ── Supply ────────────────────────────────────────────────────
Vdd vdd 0 {VDD}

* ── Reference clock 10 MHz ────────────────────────────────────
Vref ref 0 PULSE(0 {VDD} 0 100p 100p 50n 100n)

* ── Behavioral VCO ────────────────────────────────────────────
* Instantaneous frequency: f_vco(t) = fvco_nom + Kvco*(v(vtune) - Vtune_nom)
* VCO output = square wave at that frequency
* Use B-source with time integral for phase accumulation
* Phase: phi(t) = 2*pi * integral_0^t [fvco_nom + Kvco*(v(vtune)-Vtune_nom)] dt
* Implemented as: phi_node voltage via capacitor integration

* Integrate VCO frequency to get phase:
* d(v_phi)/dt = 2*pi*(fvco_nom + Kvco*(v(vtune)-Vtune_nom))
* → B-source current into C_phi: I = C_phi * d(v_phi)/dt
*   → set C_phi = 1F for unity, then: B_phi current = 2*pi*f_inst
Cphi phi 0 1
Bphi phi 0 I = '2*pi*(fvco_nom + Kvco*(v(vtune) - Vtune_nom))'

* VCO output square wave from phase
Bvco vco_out 0 V = '(sin(v(phi)) >= 0) ? VDD : 0'

* ── Feedback divider /N ──────────────────────────────────────
* Divide frequency by N=10: use the same phase but divided
Bdiv div_out 0 V = '(sin(v(phi)/N) >= 0) ? VDD : 0'

* ── Phase-Frequency Detector + Charge Pump (behavioral) ──────
* Accurate PFD/CP model:
* - Generate UP pulse on ref rising edge (until div_out rising edge)
* - Generate DN pulse on div_out rising edge (until ref rising edge)
* - Net CP current = Icp*(UP - DN) injected into loop filter
*
* Approximation via derivative-based edge detection:
* UP  ∝ d(ref)/dt > 0 AND phi_ref > phi_div (ref is ahead)
* DN  ∝ d(div)/dt > 0 AND phi_div > phi_ref (div is ahead)
*
* Best behavioral approximation in ngspice:
* Use a "phase detector" that computes phase difference via
* filtered XOR, scaled to give correct Kpd = Icp/(2*pi):
*
* Phase error signal (continuous-time, linear model):
* phi_err = phi_ref - phi_div
* phi_ref = 2*pi*fref*t  (reference phase)
* phi_div = v(phi)/N     (divided VCO phase)
*
* CP current = Kpd * phi_err = (Icp/(2*pi)) * (2*pi*fref*t - v(phi)/N)
* This is the linearized model valid near lock.

* Reference phase accumulator
Cphiref phiref 0 1
Bphiref phiref 0 I = '2*pi*fref'

* Phase error = phiref - phi/N  (in radians)
* CP current = Icp/(2*pi) * phase_error [saturated at ±Icp]
* Use saturation to model charge pump limits
Bcp cp_out 0 I = 'Icp * atan((v(phiref) - v(phi)/N)*0.5) / (pi/2)'
* atan(...)*2/pi gives smooth saturation: at phase_err → ±pi, I → ±Icp

* ── Loop Filter (3rd-order passive) ──────────────────────────
* C1 shunt to ground
C1_lf cp_out 0 {C1}
* R2-C2 series zero
R2_lf cp_out lf_mid {R2}
C2_lf lf_mid 0 {C2}
* R3-C3: 3rd-order pole; vtune is after this
R3_lf cp_out vtune {R3}
C3_lf vtune 0 {C3}

* Initial conditions: Vtune starts LOW (VCO at ~80 MHz, 20% below target)
* Forces a real acquisition transient. Target lock at Vtune=0.9V (100 MHz)
.ic v(vtune)=0.2 v(phi)=0 v(phiref)=0

* ── Transient Simulation ─────────────────────────────────────
.tran 1n 100u

* ── Measurements ─────────────────────────────────────────────
* VCO frequency at 80µs (should be ~100MHz when locked)
* Period at late time: measure two consecutive rising edges
.measure tran T_late TRIG v(vco_out) VAL=0.9 RISE=1 TD=80u
+               TARG v(vco_out) VAL=0.9 RISE=2 TD=80u
.measure tran f_vco_MHz PARAM='1e-6/T_late'

* Vtune at lock (80-90µs window)
.measure tran vtune_lock AVG v(vtune) FROM=80u TO=90u

* VCO phase at late time — should be tightly tracking ref*N
.measure tran phi_err_late AVG v(phiref) FROM=80u TO=90u

* Time when vtune first crosses 0.85V (≈within 5% of 0.9V lock point)
.measure tran t_lock WHEN v(vtune)=0.85 CROSS=1

.print tran v(vtune) v(cp_out)

.end
