# PLL Clock Generator — Connect-Rule / Boundary Plan
# Design: pll_clkgen  Milestone M-b / M-c  bead: claude_verilog_test-010
# Author: behavioral-modeling-orchestrator  2026-06-20

## 1. Overview

The PLL spans the analog–digital boundary in two places:

1. **Digital inputs → analog/RNM PLL core** (L2R: logic-to-real)
2. **Analog/RNM PLL core → digital outputs** (R2L: real-to-logic)

There is no direct analog (continuous-time electrical) signal at the soc_top boundary.
The behavioral ngspice deck (`pll_behavioral.sp`) models the loop filter and VCO as analog
nodes internally; these do NOT cross the RTL boundary.

At the soc_top / M-c co-simulation boundary, all crossing signals are either
standard logic (1-bit or multi-bit) or the SystemVerilog RNM (`pll_rnm.sv`).

---

## 2. Signal Crossing Table

| Signal         | Direction      | Type      | Boundary      | Rule       | Notes                                    |
|---------------|---------------|-----------|---------------|------------|------------------------------------------|
| `ref_clk_i`   | Crystal → PLL  | logic 1b  | L2R (D→A/RNM) | L2R_STD    | 100 MHz, 0→VDD swing                     |
| `rst_n_i`     | SoC → PLL      | logic 1b  | L2R (D→A/RNM) | L2R_STD    | Active-low async reset                   |
| `feedback_div`| SoC → PLL      | logic 4b  | L2R (D→A/RNM) | L2R_MULTI  | Config register output, quasi-static      |
| `post_div_sel`| SoC → PLL      | logic 2b  | L2R (D→A/RNM) | L2R_MULTI  | Config register output, quasi-static      |
| `out_clk_o`   | PLL → SoC      | logic 1b  | R2L (A/RNM→D) | R2L_CLK    | Clock output, feeds clock distribution    |
| `locked_o`    | PLL → SoC      | logic 1b  | R2L (A/RNM→D) | R2L_STATUS | Status flag to IRQ controller / CSR       |

### Internal-only (no boundary crossing)
| Signal        | Scope         | Type      | Notes                                     |
|--------------|--------------|-----------|-------------------------------------------|
| `vtune`      | RNM-internal  | real      | Loop filter output; NOT exported          |
| `phi_vco`    | ngspice-only  | real node | VCO phase accumulator in .sp model         |
| `icp_out`    | ngspice-only  | real node | Charge pump current                        |

---

## 3. Connect-Rule Definitions

### L2R_STD — Logic-to-Real (1-bit, standard logic threshold)
```
Direction  : logic → real (digital signal drives RNM input)
VIH thresh : 0.5 * VDD = 0.5 * 0.7 V = 0.35 V  (50% of supply, corner-parameterised)
VIL thresh : 0.35 V
High value : 1 (logic 1 detected above VIH)
Low  value : 0 (logic 0 detected below VIL)
Z/X        : resolve to 0 (safe default; PLL reset if X on rst_n_i)
Rise/fall  : not applicable (event-driven RNM)
Supply ref : constraints.supply.vdd_v = 0.7 V
Corner     : VIH/VIL = 0.5 * vdd_v (parameterised; valid across tt/ss/ff corners)
```

### L2R_MULTI — Logic-to-Real (multi-bit bus)
```
Same as L2R_STD, applied per-bit.
Bus semantics: unsigned binary encoding (feedback_div: 4b; post_div_sel: 2b)
Undefined bits (X/Z): clamp to 0; RNM uses default parameter
```

### R2L_CLK — Real-to-Logic (clock output)
```
Direction  : real/RNM → digital clock network
Driver     : out_clk_o toggled by pll_rnm phase accumulator (logic 0/1)
VOH        : 1 (logic 1; full swing at VDD)
VOL        : 0 (logic 0)
Skew model : not modelled in behavioral RNM; inserted at M-c soc_top level as
             parameter CLOCK_LATENCY_NS (default 0.5 ns for cocotb co-sim)
Buffer req : out_clk_o must be buffered before feeding any SoC clock tree
             (model does not include drive strength; clock tree is digital)
```

### R2L_STATUS — Real-to-Logic (status flag)
```
Direction  : real/RNM → digital logic (combinational/registered path)
Driver     : locked_o, 1-bit, asserted synchronous to ref_clk_i
Metastability: not modelled; in real design add a 2-FF synchronizer in the
              target clock domain before use in logic (M-c recommendation)
```

---

## 4. Analog ↔ Digital Boundary for ngspice Deck (M-c Co-sim Plan)

In M-c (AMS co-simulation with cocotb), the `pll_rnm.sv` module is the
**sole** AMS boundary element. The ngspice deck (`pll_behavioral.sp`) is used
for **standalone analog validation only** (Model-vs-SPICE lock test).

At soc_top level:
```
soc_top.sv
  └─ pll_rnm  u_pll (
       .ref_clk_i   (xo_clk),           // from crystal oscillator model
       .rst_n_i     (pll_rst_n),         // from reset controller
       .feedback_div(pll_fb_div_cfg),    // from AXI-Lite config register
       .post_div_sel(pll_postdiv_cfg),   // from AXI-Lite config register
       .out_clk_o   (sys_clk),           // drives clock crossbar / distribution
       .locked_o    (pll_locked)         // to IRQ controller + CSR status
     )
```

The cocotb testbench in M-c will:
1. Assert rst_n_i=0, release after 2 ref cycles
2. Drive feedback_div=4'h0 (N=13), post_div_sel=2'b00 (/1)
3. Wait for locked_o=1 → confirm within 20 µs (spec)
4. Sample out_clk_o and measure frequency: expect 1.282 GHz ± 5%

---

## 5. Supply-Corner Robustness

| Corner | vdd_v | VIH (L2R) | VIL (L2R) | f_vco range       | lock_time (model) |
|--------|-------|-----------|-----------|-------------------|-------------------|
| TT     | 0.700 | 0.350 V   | 0.350 V   | 1.282 GHz ± small | ~100 ns            |
| SS     | 0.630 | 0.315 V   | 0.315 V   | 1.0–1.4 GHz       | ~100 ns            |
| FF     | 0.770 | 0.385 V   | 0.385 V   | 1.0–1.4 GHz       | ~100 ns            |

VIH/VIL parameterised as `0.5 * vdd_v` → no explicit corner fix-up needed.
f_vco range confirmed feasible per architecture (ASAP7 ring VCO 0.9–1.5 GHz).

---

## 6. Coverage Requirement for M-c Sign-off

- [ ] L2R_STD boundary exercised: ref_clk_i toggles observed at RNM input
- [ ] L2R_STD boundary exercised: rst_n_i assert/release cycle verified
- [ ] L2R_MULTI boundary exercised: all 3 post_div_sel values driven (2'b00/01/10)
- [ ] L2R_MULTI boundary exercised: feedback_div=4'h0 (default) verified
- [ ] R2L_CLK: out_clk_o measured for frequency at /1, /2, /4
- [ ] R2L_STATUS: locked_o seen asserting after reset, deasserts on re-reset
- [ ] X/Z propagation: no X/Z on logic outputs after reset release
