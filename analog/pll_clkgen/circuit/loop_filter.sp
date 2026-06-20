* ============================================================
* LOOP FILTER — Passive 3rd-order RC
* PDK:  ASAP7 predictive (PREDICTIVE_PLACEHOLDER)
* Spec: R1=35.7k, C1=1.56p, C2=0.127p, C3=0.0254p
*       Loop BW = 10 MHz, PM = 58.1 deg
*
* Topology: C1-R1 series (lead-lag zero) + C2 (parallel shunt)
*           + R_p3-C3 series (3rd pole for spur suppression at ~600 MHz)
*
* Architecture topology:
*   cpout -> [C1 in series with R1] -> vtune
*   cpout -> C2 (shunt to gnd)
*   vtune -> [R3-C3 in series] -> gnd
*
* Standard 3rd-order passive PLL loop filter connection:
*   cpout -----+------ vtune
*              |
*           [C1+R1: series leg from cpout to vtune provides zero]
*
* Correct connection is:
*   cpout ---|C1|---[R1]---+--- vtune
*   cpout ----|C2|------gnd
*   vtune ---[R3]---|C3|---gnd    (3rd pole: f_p3 = 1/(2*pi*R3*C3))
*
* Component values (from architecture):
*   R1 = 35.7 kOhm  (loop zero: f_z1 = 1/(2*pi*R1*C1) = 2.86 MHz)
*   C1 = 1.56 pF    (dominant integrating cap)
*   C2 = 0.127 pF   (2nd pole suppression)
*   C3 = 0.0254 pF  (3rd pole, spur suppression)
*   R3 (implicit): R3 = 1/(2*pi*f_p3*C3); f_p3 ~ 6*f_ref = 600 MHz
*                  R3 = 1/(2*pi*600e6*25.4e-15) = 10.46 kOhm -> use 10.5 kOhm
*
* Area note:
*   C1 = 1.56 pF @ MOM 0.5 fF/um2 -> 3120 um2 (DOMINANT)
*   C2 = 0.127 pF -> 254 um2
*   C3 = 0.0254 pF -> 50.8 um2
*   R1 = 35.7k @ poly 50 Ohm/sq, W=100nm -> 714 sq -> 71.4 um long = 7140 um2
*   Total ~10564 um2 (poly R1 is very long; W=200nm, 100 Ohm/sq -> 35.7kOhm in 357sq = 71um*200nm = 14.2 um2; use 200nm wide poly)
*   (architecture budgeted 6997 um2 assuming more compact R; LF area is the largest block)
*
* ERC: purely passive network; no bulk/well ties needed.
*      All nodes driven by charge pump (no floating nodes).
* ============================================================

.subckt loop_filter  cpout  vtune  vdd  gnd
* Ports:
*   cpout  — charge pump output (driven)
*   vtune  — VCO tuning voltage (high-Z output of filter)
*   vdd, gnd

* --- Series C1-R1 (lead-lag: provides loop zero) ---
* C1: from cpout to intermediate node c1r1
C1   cpout    c1r1    1.56p
* R1: from c1r1 to vtune
R1   c1r1     vtune   35700

* --- C2: shunt from cpout to gnd (2nd pole) ---
C2   cpout    gnd     127f

* --- 3rd pole: R3-C3 from vtune to gnd ---
* f_p3 = 1/(2*pi*R3*C3) ~ 600 MHz (>= 6*f_ref to suppress ref spurs)
R3   vtune    c3_int  10500
C3   c3_int   gnd     25.4f

* Explicit note on parasitic: At this level no parasitics added.
* Post-layout RC extraction will add interconnect parasitics.

.ends loop_filter
* ============================================================
* End LoopFilter subcircuit
* ============================================================
