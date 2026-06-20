* ============================================================
* RING VCO — 5-stage current-starved differential ring oscillator
* PDK:  ASAP7 predictive (PREDICTIVE_PLACEHOLDER)
* VDD:  0.7 V
* Spec:
*   f_osc_nom = 1.282 GHz (VDD=0.7V, TT, 25C)
*   f_osc_min = 1.000 GHz (SS, 0.63V, 125C) at vtune=0.1V
*   f_osc_max = 1.400 GHz (SS corner, vtune=0.6V)
*   Kvco_fine  = 80 MHz/V  (analog fine tune; cap-bank coarse ~500 MHz/V)
*   Power      <= 2.0 mW
*   Area       <= 800 um2
*   FLAGGED MEDIUM RISK: 1.4 GHz at SS corner requires all stages fast
*
* TOPOLOGY: 5-stage current-starved differential inverter ring
*   Each stage: differential pair with cross-coupled load + current-starve NMOS
*   Coarse: 3-bit binary-weighted switchable load caps (cap-bank, digital control)
*   Fine:   analog vtune drives NMOS current-starve gate (Kvco_fine = 80 MHz/V)
*
* SIZING rationale (gm/Id method, TT 0.7V 25C):
*   Target Id_stage = 2 mW / (5 stages * 0.7 V) = 571 uA/stage
*   But differential: 2 branches -> ~285 uA per side branch
*   NMOS delay cell (MN_dp): 2 fins, L=14nm (2x min for frequency control)
*     Id_fin ~ 40 uA/fin @ Vgs=0.45V -> 2 fins -> 80 uA per gate
*     Need ~285 uA: 7-8 fins -> use 8 fins NMOS differential pair
*   PMOS cross-coupled load (MP_cc): 4 fins L=14nm (negative-resistance load)
*   Current-starve NMOS (MN_cs): gm/Id=10, gate=vtune, sizes for fine gain
*     MN_cs tail current: 4 fins L=21nm -> Id ~ 0.28 mA @ vtune=0.35V (nominal)
*   Total per stage: ~570 uA -> 5 stages = 2.85 mA -> too high
*   -> Reduce MN_dp to 4 fins: Id ~ 160 uA per branch; 2 branches = 320 uA
*   -> 5 stages * 320 uA * 0.7 V = 1.12 mW  [within 2.0 mW budget, w/ cap-bank overhead]
*
* Differential stage (one of 5 identical stages, inst. X1..X5):
*   outp, outn = differential output pair of this stage
*   inp, inn   = differential input pair from previous stage
*   vdd, gnd
*   vtune      = analog fine-tuning (all stages share same vtune)
*   capsel[2:0]= coarse cap-bank select bits (all stages share)
*
* Cap bank: 3-bit binary-weighted, each bit adds ~50 fF to each node
*   1b = 50fF: bit0, 2b = 100fF: bit1, 4b = 200fF: bit2
*   Coarse range: 8 settings * 50fF * Kvco_coarse / C = adjusts f by ~400 MHz total
*   Implemented as switched NMOS (diode-connected as cap in off state)
*
* ERC notes:
*   All bulk: NMOS bulk -> gnd, PMOS bulk -> vdd
*   No floating gates: vtune always driven, capsel always driven
*   CS device gate = vtune (external, always driven by loop filter)
* ============================================================

* ---- Differential inverter stage subcircuit ----
.subckt vco_stage  inp  inn  outp  outn  vtune
+                  capsel0  capsel1  capsel2  vdd  gnd
*
* === PMOS cross-coupled load (negative resistance for oscillation sustain) ===
* MP_cc1: drain=outp, gate=outn (cross-coupled)
* MP_cc2: drain=outn, gate=outp
* W=28n (4 fins), L=14nm -> provides -Rcc = -2/gm_p ~ -500 Ohm per stage
MP_cc1  outp  outn  vdd  vdd  pfinfet_rvt  w=28n  l=14n  nfins=4
MP_cc2  outn  outp  vdd  vdd  pfinfet_rvt  w=28n  l=14n  nfins=4
*
* === NMOS differential delay cell ===
* 4-fin, L=14nm, gm/Id ~ 12 V^-1
* Differential input pair: inp drives left branch, inn drives right branch
MN_dp1  outp  inp  vtail  gnd  nfinfet_rvt  w=28n  l=14n  nfins=4
MN_dp2  outn  inn  vtail  gnd  nfinfet_rvt  w=28n  l=14n  nfins=4
*
* === Current-starve tail device (analog fine tune) ===
* Gate = vtune; controls tail current -> controls oscillation frequency
* L=21nm (3x min) for better Vt matching and finer analog control
* 4 fins: Id ~ 0 at vtune=0V, ~320 uA at vtune=0.35V, ~640 uA at vtune=0.7V
MN_cs   vtail  vtune  gnd  gnd  nfinfet_rvt  w=28n  l=21n  nfins=4
*
* === Coarse cap-bank (3-bit binary weighted, NMOS switch-cap) ===
* Each capsel bit switches a MOS capacitor in parallel with output nodes
* NMOS gate=vdd (always as cap when on), drain=source=output
* Switch: gate=capsel -> when capsel=1, Vgs=vdd -> cap in strong inversion
*
* Bit 0: weight=1 (50 fF equivalent) — smallest step
MC0p_p  outp  capsel0  gnd  gnd  nfinfet_rvt  w=14n  l=14n  nfins=2
MC0p_n  outn  capsel0  gnd  gnd  nfinfet_rvt  w=14n  l=14n  nfins=2
*
* Bit 1: weight=2 (100 fF equivalent)
MC1p_p  outp  capsel1  gnd  gnd  nfinfet_rvt  w=28n  l=14n  nfins=4
MC1p_n  outn  capsel1  gnd  gnd  nfinfet_rvt  w=28n  l=14n  nfins=4
*
* Bit 2: weight=4 (200 fF equivalent)
MC2p_p  outp  capsel2  gnd  gnd  nfinfet_rvt  w=56n  l=14n  nfins=8
MC2p_n  outn  capsel2  gnd  gnd  nfinfet_rvt  w=56n  l=14n  nfins=8
*
.ends vco_stage

* ---- Ring VCO top-level subcircuit ----
* Five stages forming a differential ring
* Stage outputs connect: stage N outp -> stage N+1 inp
*                        stage N outn -> stage N+1 inn
* Inversion provided by swapping outp/outn on last stage back to first
* (differential ring: 5 stages, each inverting -> 5-stage ring is oscillatory)
*
.subckt ring_vco  vco_outp  vco_outn  vtune
+                 capsel0  capsel1  capsel2  vdd  gnd
*
* Stage 1: input from stage 5 (swapped for ring inversion)
X1  s5_outn  s5_outp  s1_outp  s1_outn  vtune
+   capsel0  capsel1  capsel2  vdd  gnd  vco_stage
*
* Stage 2
X2  s1_outp  s1_outn  s2_outp  s2_outn  vtune
+   capsel0  capsel1  capsel2  vdd  gnd  vco_stage
*
* Stage 3
X3  s2_outp  s2_outn  s3_outp  s3_outn  vtune
+   capsel0  capsel1  capsel2  vdd  gnd  vco_stage
*
* Stage 4
X4  s3_outp  s3_outn  s4_outp  s4_outn  vtune
+   capsel0  capsel1  capsel2  vdd  gnd  vco_stage
*
* Stage 5 (output stage, also the inversion point)
X5  s4_outp  s4_outn  s5_outp  s5_outn  vtune
+   capsel0  capsel1  capsel2  vdd  gnd  vco_stage
*
* VCO outputs tapped from stage 3 (balanced point in 5-stage ring)
Vout_p_buf  vco_outp  s3_outp  0
Vout_n_buf  vco_outn  s3_outn  0
*
.ends ring_vco
* ============================================================
* End RingVCO subcircuit
* ============================================================
