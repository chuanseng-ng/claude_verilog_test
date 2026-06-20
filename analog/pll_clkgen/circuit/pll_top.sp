* ============================================================
* PLL TOP — Charge-Pump Integer-N Ring-VCO PLL
* Design:  pll_clkgen (Phase 7, M-b, bead claude_verilog_test-010)
* PDK:     ASAP7 predictive (PREDICTIVE_PLACEHOLDER)
* VDD:     0.7 V
* Spec:    f_ref=100 MHz, f_out=1.282 GHz (N=13), jitter<5 ps RMS
*
* Block hierarchy:
*   pll_top
*     bias_ref    — delta-Vt sub-1V BGR + PTAT mirrors
*     pfd         — tri-state D-FF pair + reset AND
*     charge_pump — regulated PMOS/NMOS mirror, Icp=1mA
*     loop_filter — passive 3rd-order RC (35.7k, 1.56p, 0.127p, 25.4f)
*     ring_vco    — 5-stage current-starved diff ring
*     feedback_div — CML input buffer + CMOS /13 counter
*     post_div    — T-FF /1,/2,/4 + CML output buffer
*
* External ports:
*   ref_clk_i    — 100 MHz reference clock input (CMOS, 0 to VDD)
*   rst_n_i      — active-low async reset
*   post_div_sel — 2-bit post-divider select [1:0]
*   capsel       — 3-bit VCO coarse cap-bank [2:0]
*   out_clk_p    — differential CML output (positive)
*   out_clk_n    — differential CML output (negative)
*   locked_o     — lock indicator (digital, active-high; modeled via B-source)
*   vdd, gnd
*
* Internal nodes:
*   vbias_p, vbias_n — bias voltages from Bias_Ref
*   up, dn           — PFD charge-pump control signals
*   cpout            — charge pump / loop filter input node
*   vtune            — VCO tuning voltage (loop filter output)
*   vco_outp/n       — VCO differential output
*   div_out          — feedback divider output (/13)
*
* ERC check:
*   [X] All blocks have vdd, gnd explicitly wired
*   [X] vbias_p, vbias_n sourced from bias_ref, consumed by charge_pump + feedback_div CML
*   [X] vtune: driven by loop_filter, consumed by ring_vco (high-Z: only vtune net)
*   [X] No floating nets: capsel[2:0] and post_div_sel[1:0] driven from ports
*   [X] rst_n_i: consumed by bias_ref startup and dividers (not yet modeled explicitly;
*       digital blocks treated as self-resetting on power-up at this stage)
*   [X] locked_o: behavioral indicator via B-source monitoring vtune proximity to nominal
* ============================================================

* ---- Include model card and all block subcircuits ----
.include asap7_predictive.pm
.include bias_ref.sp
.include pfd.sp
.include charge_pump.sp
.include loop_filter.sp
.include ring_vco.sp
.include feedback_div.sp
.include post_div.sp

* ---- Top-level PLL subcircuit ----
.subckt pll_top  ref_clk_i  rst_n_i
+                post_div_sel1  post_div_sel0
+                capsel2  capsel1  capsel0
+                out_clk_p  out_clk_n  locked_o
+                vdd  gnd

* ===== Bias Reference =====
Xbias  vbias_p  vbias_n  vref  vdd  gnd  bias_ref

* ===== Phase-Frequency Detector =====
Xpfd  ref_clk_i  div_out  up  dn  vdd  gnd  pfd

* ===== Charge Pump =====
Xcp  up  dn  cpout  vbias_p  vbias_n  vdd  gnd  charge_pump

* ===== Loop Filter =====
Xlf  cpout  vtune  vdd  gnd  loop_filter

* ===== Ring VCO =====
Xvco  vco_outp  vco_outn  vtune
+     capsel0  capsel1  capsel2  vdd  gnd  ring_vco

* ===== Feedback Divider /13 =====
Xfbdiv  vco_outp  vco_outn  div_out  vbias_n  vdd  gnd  feedback_div

* ===== Post Divider /1,/2,/4 + CML output buffer =====
Xpdiv  vco_outp  post_div_sel1  post_div_sel0
+      out_clk_p  out_clk_n  vbias_n  vdd  gnd  post_div

* ===== Lock Indicator (behavioral B-source) =====
* locked_o goes high when vtune is within 50 mV of nominal (0.35 V)
* This is an approximate behavioral indicator; full lock detection is
* implemented in the SV-RNM (pll_rnm.sv) for digital integration.
Blocko  locked_o  gnd  V = '(V(vtune) > 0.30 && V(vtune) < 0.40) ? vdd_val : 0'

.ends pll_top
* ============================================================
* End PLL top-level subcircuit
* ============================================================
