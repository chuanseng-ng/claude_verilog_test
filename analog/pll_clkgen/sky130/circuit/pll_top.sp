* ============================================================
* Sky130 PLL Top-Level Netlist
* pll_clkgen_sky130 — Phase 7 M-b2
* 10 MHz ref → 100 MHz VCO output (integer-N, N=10)
* VDD=1.8V, Sky130A PDK, sky130_fd_pr nfet/pfet devices
* ============================================================
* This file includes all 7 block subckts and wires them together.
* Intended for: ERC check, connectivity verification, and future
* post-layout sim once layout is completed.

.title pll_clkgen_sky130_top

* ── Include block subckts ─────────────────────────────────
.include "/home/neuromorphic/Downloads/Github/claude_verilog_test/analog/pll_clkgen/sky130/circuit/sky130_pfd.sp"
.include "/home/neuromorphic/Downloads/Github/claude_verilog_test/analog/pll_clkgen/sky130/circuit/sky130_cp.sp"
.include "/home/neuromorphic/Downloads/Github/claude_verilog_test/analog/pll_clkgen/sky130/circuit/sky130_lf.sp"
.include "/home/neuromorphic/Downloads/Github/claude_verilog_test/analog/pll_clkgen/sky130/circuit/sky130_vco.sp"
.include "/home/neuromorphic/Downloads/Github/claude_verilog_test/analog/pll_clkgen/sky130/circuit/sky130_fbdiv.sp"
.include "/home/neuromorphic/Downloads/Github/claude_verilog_test/analog/pll_clkgen/sky130/circuit/sky130_postdiv.sp"
.include "/home/neuromorphic/Downloads/Github/claude_verilog_test/analog/pll_clkgen/sky130/circuit/sky130_bias.sp"

* ── Top-level subckt ─────────────────────────────────────
.subckt pll_top clk_ref clk_out div0 div1 vdd vss

* Block instances
* PFD: clk_ref, clk_div(from fbdiv), up, dn, vdd, vss
X_pfd  clk_ref clk_div up dn vdd vss sky130_pfd

* CP: up, dn, icp_out, vdd, vss
X_cp   up dn icp_out vdd vss sky130_cp

* Loop Filter: icp_out → vtune
X_lf   icp_out vtune vss sky130_lf

* VCO: vtune, vco_raw, vdd, vss
X_vco  vtune vco_raw vdd vss sky130_vco

* Feedback divider /10: vco_raw → clk_div (back to PFD)
X_fbdiv vco_raw clk_div vdd vss sky130_fbdiv

* Post-divider /1,/2,/4: vco_raw → clk_out
X_postdiv vco_raw clk_out div0 div1 vdd vss sky130_postdiv

* Bias reference: ibias node (connected to VCO and CP bias inputs)
X_bias ibias_out vdd vss sky130_bias

.ends pll_top

* ── ERC check: DC operating point ────────────────────────
* Instantiate pll_top at top level for connectivity check
Xpll clk_ref clk_out_top div0 div1 vdd 0 pll_top

Vdd vdd 0 1.8
Vclkref clk_ref 0 PULSE(0 1.8 0 100p 100p 50n 100n)
Vdiv0 div0 0 0
Vdiv1 div1 0 0

* DC operating point — checks connectivity and bias
.op

.end
