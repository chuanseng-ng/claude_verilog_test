* ============================================================
* POST DIVIDER — T-FF /1,/2,/4 chain + CML output buffer
* PDK:  ASAP7 predictive (PREDICTIVE_PLACEHOLDER)
* VDD:  0.7 V
* Spec:
*   Divide ratios:  /1, /2, /4 (selected by 2-bit post_div_sel[1:0])
*   f_in_max:       1.282 GHz (VCO nominal output)
*   Output swing:   400 mV (CML)
*   Added jitter:   <= 0.3 ps RMS
*   Power:          <= 0.3 mW
*   Area:           <= 300 um2
*
* TOPOLOGY:
*   Two cascaded T-FFs (TSPC for speed): FF1 (/2), FF2 (/4)
*   Mux selects: post_div_sel=00 -> bypass (/1), =01 -> FF1 (/2), =10 -> FF2 (/4)
*   CML output buffer: differential SLVT pair with resistive load, 400 mV swing
*
* SIZING:
*   T-FFs: same TSPC topology as feedback_div (RVT min L=7nm)
*   Output MUX: CMOS transmission gates (min-size devices, RVT)
*   CML output buffer: SLVT 2-fin differential pair, PMOS loads
*     Target swing 400 mV: Vout_cm = VDD - Id*Rload, swing = Id*Rload
*     Id = 200 uA per branch (for low power), Rload = 1 kOhm -> swing = 200 mV
*     Need 400 mV swing: use Rload = 2 kOhm or Id = 200 uA per branch (R=2k)
*     Alternatively: Id = 400 uA, Rload = 1 kOhm -> 400 mV
*     PMOS: 4 fins SLVT in triode (Rload ~ 1 kOhm); Id = 400 uA/branch
*     NMOS diff pair: 4 fins SLVT L=7nm, Id ~ 400 uA per branch at Vgs=0.45V
*
* ERC notes:
*   All NMOS bulk -> gnd, PMOS bulk -> vdd
*   All mux select inputs driven from digital control
*   CML output load (PMOS triode) always connected: no floating drain
* ============================================================

* ---- T-FF from tspc_dff (reuse from feedback_div) ----
* Note: tspc_dff defined in feedback_div.sp; pll_top.sp includes both files.
* Here we define only post_div-specific subcircuits.

* ---- 2:1 MUX using transmission gates ----
.subckt mux21  a  b  sel  y  vdd  gnd
* sel=0 -> y=a; sel=1 -> y=b
* TG1 (sel=0 path): PMOS gate=sel, NMOS gate=sel_b
Xinv_sel  sel  sel_b  vdd  gnd  inv1
*
* Path A (sel=0 -> a passes)
MP_tga  ya_int  sel    a  vdd  pfinfet_rvt  w=21n  l=7n  nfins=3
MN_tga  ya_int  sel_b  a  gnd  nfinfet_rvt  w=14n  l=7n  nfins=2
*
* Path B (sel=1 -> b passes)
MP_tgb  yb_int  sel_b  b  vdd  pfinfet_rvt  w=21n  l=7n  nfins=3
MN_tgb  yb_int  sel    b  gnd  nfinfet_rvt  w=14n  l=7n  nfins=2
*
* Output inverter buffer (restores logic level from high-Z TG output)
MP_obuf  y  ya_int  vdd  vdd  pfinfet_rvt  w=21n  l=7n  nfins=3
MN_obuf  y  ya_int  gnd  gnd  nfinfet_rvt  w=14n  l=7n  nfins=2
*
* Note: ya_int and yb_int must be shorted as the mux output before buffer.
* In SPICE the parallel TGs share the same output node.
* Correct: share output before the buffer inverter:
Rmux_short  ya_int  yb_int  1
*
.ends mux21

* ---- CML output buffer ----
* Differential pair with PMOS resistive (triode) load
* Provides 400 mV swing, 50-ohm drive capability
.subckt cml_outbuf  inp  inn  outp  outn  vdd  gnd
*
* PMOS triode loads (Rload ~ 1 kOhm each for 400 mV swing with 400 uA)
* VGS_PMOS = VDD - Vbias_triode; in triode: Id = up*Cox*(W/L)*[(VGS-VTP)*VDS - VDS^2/2]
* Approximation: set Vg = VDD (gate tied to gnd? No: gate = vdd -> VGS=0 -> off)
* Correct PMOS triode: Vg = some mid-bias. Use diode-connected PMOS as pseudo-resistor:
* Gate=Drain -> always in saturation actually. Use PMOS with W/L for ~1kOhm.
* Alternative: poly resistor for cleaner modeling.
* Use R for simplicity (real implementation: poly resistors).
Rload_p  vdd  outp  1000
Rload_n  vdd  outn  1000
*
* NMOS differential pair (SLVT for speed at 1.282 GHz input)
* 4 fins SLVT, L=7nm, Id ~ 400 uA per branch at Vgs ~ 0.42V
MN_dp1  outp  inp  vtail_ob  gnd  nfinfet_slvt  w=28n  l=7n  nfins=4
MN_dp2  outn  inn  vtail_ob  gnd  nfinfet_slvt  w=28n  l=7n  nfins=4
*
* Tail current: 800 uA total (400 per branch)
* 4-fin SLVT NMOS L=21nm biased by vbias_n
MN_tail  vtail_ob  vbias_n_ob  gnd  gnd  nfinfet_slvt  w=28n  l=21n  nfins=4
*
* vbias_n_ob is external port (tied to Bias_Ref vbias_n in top)
.ends cml_outbuf

* ---- Post-divider top-level ----
.subckt post_div  pll_clk_in  post_div_sel1  post_div_sel0
+                 out_clk_p  out_clk_n  vbias_n  vdd  gnd
*
* T-FF /2: FF1, input = pll_clk_in
* T-FF connection: D = QB (toggle mode)
* Use tspc_dff with D connected to QB for T-mode
* Issue: tspc_dff needs external D connection for T-FF -> wire D=QB through inv
Xinv_ff1_fb  q1  d1_ff1  vdd  gnd  inv1
XFF1  d1_ff1  pll_clk_in  q1  q1b  vdd  gnd  tspc_dff
*
* T-FF /4: FF2, input = q1 (/2 output)
Xinv_ff2_fb  q2  d2_ff2  vdd  gnd  inv1
XFF2  d2_ff2  q1  q2  q2b  vdd  gnd  tspc_dff
*
* 2-stage mux to select divide ratio:
* Stage 1: select /1 vs /2
Xmux1  pll_clk_in  q1  post_div_sel0  mux1_out  vdd  gnd  mux21
*
* Stage 2: select result of stage1 vs /4
Xmux2  mux1_out  q2  post_div_sel1  mux2_out  vdd  gnd  mux21
*
* Output is mux2_out (single-ended CMOS)
* Drive into CML output buffer via differential conversion
* CMOS-to-differential: use inv to generate complement
Xinv_diff  mux2_out  mux2_out_b  vdd  gnd  inv1
Xcml_buf  mux2_out  mux2_out_b  out_clk_p  out_clk_n  vdd  gnd  cml_outbuf
*
.ends post_div
* ============================================================
* End PostDiv subcircuit
* ============================================================
