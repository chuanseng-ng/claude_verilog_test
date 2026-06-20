* ============================================================
* Sky130 Bias Current Reference — Widlar-style self-biased
* Target: 10 µA output current, PSRR > 40 dB
* Sub-threshold NMOS ratio for temperature stability
* Ports: ibias vdd vss
* ibias: output node where mirror current flows
* ============================================================
.subckt sky130_bias ibias vdd vss

* ── Self-biased architecture ──────────────────────────────
* PMOS mirror (M_p1, M_p2) + NMOS pair with degeneration resistor
* Startup: M_startup provides initial current
*
* Operating principle:
* M_p1 (W=1u, L=2u) mirrors M_p2 (W=2u, L=2u) → ratio 1:2
* NMOS M_n1 (W=2u, L=2u) in sub-Vt region
* Degeneration Rd sets operating point: I = (Vt/q) * ln(W2/W1) / Rd
* Rd = Vt*ln(2) / I = 26mV*0.693 / 10µA = 1.8 kΩ

* PMOS reference pair
M_p1 n_ref  n_ref vdd vdd sky130_fd_pr__pfet_01v8 l=2u w=1u nf=1
M_p2 n_out  n_ref vdd vdd sky130_fd_pr__pfet_01v8 l=2u w=2u nf=2

* NMOS pair with degeneration
M_n1 n_ref n_ref n1d vss sky130_fd_pr__nfet_01v8 l=2u w=2u nf=2
M_n2 n_out n_ref vss  vss sky130_fd_pr__nfet_01v8 l=2u w=2u nf=2

* Degeneration resistor under M_n1
Rd1 n1d vss 1.8k

* Startup circuit (prevents zero-current state)
M_start vdd vdd n_ref vdd sky130_fd_pr__pfet_01v8 l=10u w=500n nf=1

* Output mirror: PMOS mirror from n_ref to ibias output
M_p_out ibias n_ref vdd vdd sky130_fd_pr__pfet_01v8 l=2u w=1u nf=1

.ends sky130_bias
