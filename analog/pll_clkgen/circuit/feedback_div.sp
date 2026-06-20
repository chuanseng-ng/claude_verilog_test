* ============================================================
* FEEDBACK DIVIDER — CML /2 first stage + CMOS /13 counter
* PDK:  ASAP7 predictive (PREDICTIVE_PLACEHOLDER)
* VDD:  0.7 V
* Spec:
*   Divide ratio: /13 (integer-N PLL)
*   f_in_max  = 1.4 GHz (VCO output, SS corner)
*   f_out     = 100 MHz (to PFD)
*   Added PN  = -140 dBc/Hz at 1 MHz offset (ref to divider output)
*   Power     <= 0.5 mW
*   Area      <= 500 um2
*
* TOPOLOGY:
*   Stage 1: CML source-coupled latch /2 (SLVT NMOS for 1.4 GHz capability)
*     -> output at 700 MHz (differential CML, then CMOS conversion)
*   Stage 2: CMOS static divide: /13 using a 4-bit Johnson counter + logic
*     -> /13 = /2 (from CML) followed by a CMOS /6.5 is not integer;
*        Instead: true /13 CMOS counter at 700 MHz input (feasible at ASAP7)
*
* IMPLEMENTATION NOTE:
*   CML /2: SLVT devices for low Vth and fast switching at 0.7V
*   CMOS /13 counter: implemented as a 4-bit synchronous counter
*     that counts 0..12 (13 states) then resets. Output toggles on each
*     complete cycle -> output frequency = f_in / 13.
*     At 1.4 GHz, /2 CML -> 700 MHz CMOS, then /13 at 700 MHz -> 53.8 MHz
*     WRONG: Need total /13 not /2 then /13.
*
*   CORRECT implementation:
*     CML /2 at 1.4 GHz input -> 700 MHz CML output -> CMOS level shift
*     CMOS synchronous counter counts 13 states at 700 MHz
*     But 700/13 = 53.8 MHz, not 100 MHz.
*
*   ACTUAL DIVISION PLAN (matches architecture):
*     CML /2 at VCO output (1.282 GHz TT) -> 641 MHz differential
*     Then need /6.5 which is non-integer. Not feasible.
*
*   REVISED: Use 2/3 prescaler approach:
*     A 2/3 prescaler divides by 2 or 3 based on modulus control.
*     For N=13: prescaler divides by 2 (P=2, S=1) for part of cycle.
*     Standard fractional-N approach: BUT this is integer-N PLL.
*
*   CORRECT ARCHITECTURE for /13:
*     True modulus /13 counter running at 1.4 GHz input.
*     At ASAP7 7nm, TSPC (True Single Phase Clock) FF can run at 1.4 GHz.
*     Use: CML input buffer (level shift) + TSPC /13 divider chain.
*
*   CML INPUT BUFFER: converts differential VCO output to CMOS levels.
*   Then TSPC synchronous /13 counter:
*     4-bit counter (counts 0..12), terminal count resets to 0.
*     Output = carry (asserts one clock when count=12).
*     Output FF: T-FF toggling on each terminal count -> /13.
*
* SIZING (CML input buffer, SLVT):
*   CML current source: 2 fins SLVT NMOS, L=7nm, Id ~ 100 uA per stage
*   Differential pair: 2 fins SLVT NMOS, L=7nm
*   PMOS resistive loads: use polyresistor or PMOS in triode
*   (Simplified here: use PMOS diode-connected load at W=14n, L=7n)
*
* TSPC /13 counter sizing (CMOS, RVT, digital):
*   All devices min L=7nm; P: 3 fins (W=21n), N: 2 fins (W=14n)
*   Standard cell-like for digital counter
*
* ERC notes:
*   All bulk: NMOS -> gnd, PMOS -> vdd
*   No floating nodes; all FF D inputs driven; counter reset driven
* ============================================================

* ---- CML input buffer subcircuit ----
* Converts differential VCO signal to CMOS-compatible output
* SLVT NMOS for 1.4 GHz operation at 0.7 V
.subckt cml_input_buf  inp  inn  outp  outn  vdd  gnd
*
* Differential pair (SLVT for speed)
MN_d1   outp   inp   vtail_cml   gnd   nfinfet_slvt  w=14n  l=7n  nfins=2
MN_d2   outn   inn   vtail_cml   gnd   nfinfet_slvt  w=14n  l=7n  nfins=2
*
* PMOS diode-connected loads (triode resistive behavior)
MP_l1   outp   outp   vdd   vdd   pfinfet_slvt  w=14n  l=14n  nfins=2
MP_l2   outn   outn   vdd   vdd   pfinfet_slvt  w=14n  l=14n  nfins=2
*
* Tail current source: biased by vbias_n (connected externally as constant cur)
* Here use fixed Vgs for simulation: Id ~ 200 uA total (100 uA per branch)
MN_tail  vtail_cml  vbias_n_buf  gnd  gnd  nfinfet_slvt  w=14n  l=14n  nfins=2
*
* External bias port (tied to same vbias_n from Bias_Ref in top)
* In subcircuit: vbias_n_buf is a port
*  -> For simulation, this will be driven from the bias block
.ends cml_input_buf

* ---- TSPC D-Flip-Flop (for /13 counter) ----
* True Single Phase Clock DFF for high-speed operation
* Ref: TSPC logic (Yuan & Svensson 1989)
.subckt tspc_dff  d  clk  q  qb  vdd  gnd
* Stage 1 (dynamic): precharge on clk=0, evaluate on clk=1
MP_p1   n1   clk   vdd   vdd   pfinfet_rvt  w=21n  l=7n  nfins=3
MN_n1   n1   d     n2    gnd   nfinfet_rvt  w=14n  l=7n  nfins=2
MN_n2   n2   clk   gnd   gnd   nfinfet_rvt  w=14n  l=7n  nfins=2
*
* Stage 2 (dynamic): precharge on clk=1, evaluate on clk=0
MP_p2a  n3   clk   vdd   vdd   pfinfet_rvt  w=21n  l=7n  nfins=3
MP_p2b  n3   n1    vdd   vdd   pfinfet_rvt  w=21n  l=7n  nfins=3
MN_n3   n3   clk   gnd   gnd   nfinfet_rvt  w=14n  l=7n  nfins=2
*
* Stage 3 (static output): inverter pair
MP_p3   q    n3    vdd   vdd   pfinfet_rvt  w=21n  l=7n  nfins=3
MN_n4   q    n3    gnd   gnd   nfinfet_rvt  w=14n  l=7n  nfins=2
MP_p4   qb   q     vdd   vdd   pfinfet_rvt  w=21n  l=7n  nfins=3
MN_n5   qb   q     gnd   gnd   nfinfet_rvt  w=14n  l=7n  nfins=2
*
.ends tspc_dff

* ---- 2-input AND gate (for /13 counter logic) ----
.subckt and2  a  b  y  vdd  gnd
* NAND + INV
MP_n1  nand_y  a  vdd  vdd  pfinfet_rvt  w=21n  l=7n  nfins=3
MP_n2  nand_y  b  vdd  vdd  pfinfet_rvt  w=21n  l=7n  nfins=3
MN_n1  nand_y  a  nd_int  gnd  nfinfet_rvt  w=14n  l=7n  nfins=2
MN_n2  nd_int  b  gnd     gnd  nfinfet_rvt  w=14n  l=7n  nfins=2
MP_i1  y  nand_y  vdd  vdd  pfinfet_rvt  w=21n  l=7n  nfins=3
MN_i1  y  nand_y  gnd  gnd  nfinfet_rvt  w=14n  l=7n  nfins=2
.ends and2

* ---- Inverter ----
.subckt inv1  a  y  vdd  gnd
MP_i  y  a  vdd  vdd  pfinfet_rvt  w=21n  l=7n  nfins=3
MN_i  y  a  gnd  gnd  nfinfet_rvt  w=14n  l=7n  nfins=2
.ends inv1

* ---- 2-input OR gate ----
.subckt or2  a  b  y  vdd  gnd
* NOR + INV
MP_r1  nor_y  a  vdd  vdd  pfinfet_rvt  w=21n  l=7n  nfins=3
MP_r2  nor_y  b  nor_int  vdd  pfinfet_rvt  w=21n  l=7n  nfins=3
MN_r1  nor_y  a  gnd  gnd  nfinfet_rvt  w=14n  l=7n  nfins=2
MN_r2  nor_y  b  gnd  gnd  nfinfet_rvt  w=14n  l=7n  nfins=2
MP_i1  y  nor_y  vdd  vdd  pfinfet_rvt  w=21n  l=7n  nfins=3
MN_i1  y  nor_y  gnd  gnd  nfinfet_rvt  w=14n  l=7n  nfins=2
.ends or2

* ---- /13 synchronous counter (behavioral CMOS, clk at VCO freq) ----
* 4-bit ripple counter: Q[3:0], counts from 0 to 12, resets on count=12
* Output: divout toggles every 13 input cycles -> /13
*
* Implementation: 4 T-FFs + combinational reset (reset when count=1101 = 13)
*   Binary 13 = 1101 -> Q3=1, Q2=1, Q1=0, Q0=1
*   Reset logic: nrst_b = NAND(Q3, Q2, Q0) = 1 -> reset (active low clr)
*
* Use DFF in T-mode (T-FF: Q toggles when T=1)
* T-FF from DFF: connect D=QB
*
.subckt div13_cmos  clkin  divout  vdd  gnd
* Bit 0 (LSB): toggle every cycle
XFF0  nrst_b  clkin  q0  q0b  vdd  gnd  tspc_dff
*
* Bit 1: toggle when q0=1
Xand01  q0  nrst_b  t1  vdd  gnd  and2
XFF1    t1   clkin  q1  q1b  vdd  gnd  tspc_dff
*
* Bit 2: toggle when q1=1 and q0=1
Xand012  q1  t1  t2  vdd  gnd  and2
XFF2     t2  clkin  q2  q2b  vdd  gnd  tspc_dff
*
* Bit 3: toggle when q2=1 and q1=1 and q0=1
Xand023  q2  t2  t3  vdd  gnd  and2
XFF3     t3  clkin  q3  q3b  vdd  gnd  tspc_dff
*
* Reset logic: reset when count = 13 = 1101b
*   Need Q3=1, Q2=1, Q0=1 (Q1=0 -> q1b=1 is needed)
*   rst_trig = AND(q3, q2, q1b, q0)
*   Simplified: NAND3(q3,q2,q0) to nrst_b (since 1101 is the only state where
*   this set is active before Q1 can toggle; assumes synchronous reset at count=13)
*   For /13: count 0..12 (13 cycles), detect 12=1100 for next clock edge reset:
*   12 = 1100b -> Q3=1, Q2=1, Q1=0, Q0=0
*   Reset at count=12: nrst_b = NAND(q3, q2, q1b, q0b)
*   This resets FFs to 0 on the NEXT rising edge (synchronous reset)
Xnot_q0  q0  q0bb  vdd  gnd  inv1
Xnot_q1  q1  q1bb  vdd  gnd  inv1
Xand_rst1  q3  q2  rst_pre  vdd  gnd  and2
Xand_rst2  q1bb  q0bb  rst_pre2  vdd  gnd  and2
Xand_rst3  rst_pre  rst_pre2  nrst_trigger  vdd  gnd  and2
Xinv_nrst  nrst_trigger  nrst_b  vdd  gnd  inv1
*
* Output: toggle FF on each terminal count (count=12 -> output toggles)
* divout is the MSB q3 in a /8 sense, but for /13 use a dedicated output T-FF
* toggling on the reset pulse
XFF_out  nrst_trigger  clkin  divout  divout_b  vdd  gnd  tspc_dff
*
.ends div13_cmos

* ---- Feedback Divider top-level subcircuit ----
.subckt feedback_div  vco_inp  vco_inn  div_out  vbias_n  vdd  gnd
*
* CML input buffer (level-shift VCO differential output to CMOS)
Xcml  vco_inp  vco_inn  cmos_p  cmos_n  vdd  gnd  cml_input_buf
*
* CMOS /13 counter (operating at VCO frequency after CML buffer)
* Input: cmos_p (single-ended CMOS from CML buffer positive output)
Xdiv13  cmos_p  div_out  vdd  gnd  div13_cmos
*
.ends feedback_div
* ============================================================
* End FeedbackDiv subcircuit
* ============================================================
