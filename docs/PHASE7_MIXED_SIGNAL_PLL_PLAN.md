# Phase 7 Mixed-Signal PLL Clock Generator — Roadmap & Implementation Plan

**Status as of 2026-06-20**: This document is the **golden specification** for Phase 7 (Mixed-Signal PLL Clock Generator). It records the dual-PDK charge-pump PLL designed end-to-end via the analog-design orchestrator agents, its integration into the SoC as the clock source, and the honest sign-off status (real Sky130 CP-block DRC+LVS vs indicative ASAP7 vs remaining follow-ups). Subsequent sessions should read this file first.

**Last verified**: 2026-06-20 (commits `5e181d6..b839b3c`; RTL/cosim state audited; `analog/pll_clkgen/{,sky130}/` and `rtl/soc/pll/` confirmed present).

**Dual nature of this phase**: Phase 7 is BOTH a real engineering deliverable (a fabricatable Sky130 PLL block + an AMS-integrated SoC clock seam) AND a validation run of the installed analog-design agent suite. §8 reports the agent-suite findings; everything else treats the PLL as a normal deliverable.

## How to use this document

1. Read §1 (scope) and §2 (dual-PDK rationale) to understand what is real vs indicative.
2. §3/§4 carry the PLL specs (both variants); §5 the analog flow stages + which agents ran + per-stage sign-off status.
3. §6 is the SoC integration (clock seam, AXI-Lite map, the 2 RTL bugs fixed, cosim results).
4. §7 is the milestone table (M-a..M-d); §9 the honest "real vs indicative vs remaining" ledger.
5. The analog flow state lives in `analog/pll_clkgen/{,sky130}/design_state.json` — **separate from the digital `design_state.json`** at repo root.

---

## 1. Scope & locked decisions

**Phase 7 goal**: design a charge-pump integer-N PLL clock generator with a ring VCO, in two PDKs (ASAP7 predictive + Sky130 real), through the analog flow (architecture → behavioral modeling → circuit → simulation → custom layout → physical verification), then integrate it into the SoC top as the clock source via a PDK-agnostic real-number model (RNM).

**Locked decisions** (this phase):

| # | Decision | Note |
|---|----------|------|
| 1 | **Dual-PDK split**: ASAP7 = indicative, Sky130 = real sign-off | Open ngspice has no BSIM-CMG FinFET models → ASAP7 transistor sims use a calibrated planar BSIM4 substitute. Sky130 uses real `sky130_fd_pr` models. |
| 2 | **Integer-N, charge-pump, ring VCO** topology for both variants | Simplest topology that closes the SoC clock spec on the open toolchain. |
| 3 | **RNM is the integration vehicle** | `pll_rnm.sv` is PDK-agnostic; transistor-level GDS is **not** instantiated into the SoC. STUB mode (CI default) is synth-safe; RNM mode is cosim-only. |
| 4 | **Sky130 = the fabrication candidate** | Real magic layout on `sky130A.tech`, real magic DRC + netgen LVS. ASAP7 is predictive only. |
| 5 | **OpenVAF not available** → ngspice-behavioral fallback | OpenVAF is not in nixpkgs; behavioral models run in ngspice instead of compiled OSDI. |

---

## 2. Dual-PDK rationale (predictive ASAP7 vs real Sky130)

The PLL was built twice on purpose, to bracket "matches the digital sign-off node" against "is genuinely fabricatable on the open toolchain":

- **ASAP7 variant** (`analog/pll_clkgen/`) targets the ASAP7 SoC clock (780 ps / 1.282 GHz). It exercises the full analog flow at the open-toolchain level, but ASAP7 is a **predictive 7nm FinFET PDK** and the open ngspice ships **no BSIM-CMG FinFET models**. Transistor sims therefore used a **calibrated planar BSIM4 substitute**, so all ASAP7 electrical results are **indicative, not silicon sign-off**. Architecture + modeling + circuit were signed off at the open-toolchain level; the meta pipeline serviced two fix_requests (VCO SLVT device migration, charge-pump array sizing) and accepted the BSIM-CMG gap as a documented PDK-model limitation.
- **Sky130 variant** (`analog/pll_clkgen/sky130/`) targets a clean 10 MHz → 100 MHz multiply and uses **real `sky130_fd_pr` models** end-to-end, with **real magic custom layout** on `sky130A.tech` and **real magic DRC + netgen LVS**. This is the variant that carries genuine physical sign-off (at the charge-pump block level — see §9).

Net: ASAP7 demonstrates the flow against the real digital clock target; Sky130 demonstrates real, checkable silicon-grade artifacts.

---

## 3. PLL specification — ASAP7 variant (indicative)

| Parameter | Value | Notes |
|-----------|-------|-------|
| Reference frequency | 100 MHz | SoC external `clk_i` |
| Output frequency | 1.282 GHz | Matches ASAP7 SoC 780 ps clock |
| Divide ratio N | 13 | Integer-N |
| Topology | Charge-pump, ring VCO | |
| Supply (VDD) | 0.7 V | ASAP7 nominal |
| Device models | Calibrated planar **BSIM4 substitute** | ngspice has no BSIM-CMG → **indicative only** |
| Sign-off status | Architecture + modeling + circuit signed off (open-toolchain); electrical **indicative** | BSIM-CMG gap accepted as PDK-model limitation |
| fix_requests serviced | VCO SLVT migration; CP array sizing | Closed by meta pipeline loop |

## 4. PLL specification — Sky130 variant (real sign-off)

| Parameter | Value | Notes |
|-----------|-------|-------|
| Reference frequency | 10 MHz | |
| Output frequency | 100 MHz | |
| Divide ratio N | 10 | Integer-N |
| Topology | Charge-pump, ring VCO | |
| Supply (VDD) | 1.8 V | Sky130 nominal |
| Device models | Real `sky130_fd_pr` | Real ngspice electrical |
| VCO gain Kvco | 530 MHz/V | Covers 100 MHz at tt/ss/ff corners |
| Lock behavior | 100.000 MHz lock in 1.38 µs | Behavioral lock sim |
| Charge-pump UP/DN mismatch | 4.78% → **0.37%** | Fixed via independent PMOS/NMOS bias legs |
| Layout | Real magic custom layout on `sky130A.tech` | |
| Physical verification (CP block) | **DRC = 0**; netgen LVS topology **MATCH**; 4 pfet + 1 nfet `sky130_fd_pr` devices extracted | Genuine block-level sign-off (see §9) |
| Sign-off status | CP block: **real DRC + LVS signed off**; VCO/LF/BIAS: regen pending | See §9 ledger |

---

## 5. Analog flow — stages, agents, per-stage sign-off

Legend: ✅ signed off · 🟡 indicative · ⏸️ remaining

| Stage | Agent (orchestrator) | ASAP7 | Sky130 | Notes |
|-------|----------------------|-------|--------|-------|
| Infrastructure | `analog-design-infrastructure` | ✅ | ✅ | `analog` nix devshell in `librelane/flake.nix` (ngspice/xschem/magic/klayout/netgen). OpenVAF absent → ngspice-behavioral fallback. |
| Architecture | `analog-architecture` | ✅ | ✅ | Spec capture → signal-chain budgeting → topology partitioning → feasibility → architecture sign-off. |
| Behavioral modeling | `behavioral-modeling` | ✅ | ✅ | Verilog-A / RNM authoring; ngspice-behavioral compile + model-vs-SPICE validation. |
| Circuit design | `circuit-design` | ✅ | ✅ | gm/Id sizing, biasing, schematic capture, pre-layout ERC. Sky130 CP UP/DN mismatch fix (independent bias legs). |
| Simulation (ngspice) | `circuit-simulation` | 🟡 (BSIM4 substitute) | ✅ (real `sky130_fd_pr`) | DC/AC/transient/corners. Sky130 Kvco 530 MHz/V at tt/ss/ff; behavioral lock 100.000 MHz / 1.38 µs. |
| Custom layout (magic) | `custom-layout` | n/a | ✅ | Real magic layout on `sky130A.tech`. |
| Physical verification (magic DRC + netgen LVS) | `physical-verification` | n/a | ✅ (CP block) | Adversarial PV caught a **false DRC pass**; CP block then fixed to genuine sign-off (DRC = 0, real FETs, LVS MATCH). |
| Meta pipeline-orchestration | `analog-design-meta:pipeline-orchestrator` | ✅ | ✅ | Closed-loop fix_request servicer: VCO SLVT migration, CP array sizing (ASAP7); CP regeneration (Sky130). |

**Key lesson learned (Sky130 layout)**: in `sky130A`, **always use the `sky130A.tcl` PDK device generators, never hand-drawn primitives.** The magic database unit is 10 nm; hand-drawn geometry came out **50× too small**, with poly merely *touching* diffusion → **0 FETs extracted** and a misleading "clean" DRC. Regenerating the devices via the PDK generator produced real extractable FETs and a true LVS match.

---

## 6. SoC integration (M-c)

### 6.1 RTL (`rtl/soc/pll/`)

| File | Role |
|------|------|
| `pll_clkgen.sv` | `PLL_IMPL=STUB\|RNM` generate-select wrapper |
| `pll_clkgen_stub.sv` | Synth-safe stub (CI default; `core_clk == clk_i`, no CDC) |
| `pll_rnm.sv` | PDK-agnostic real-number model — the AMS integration vehicle |
| `pll_axil_regs.sv` | AXI-Lite config/status slave (CONTROL/STATUS) |

### 6.2 Clock seam (`soc_top.sv`)

- External `clk_i` becomes the **PLL reference**.
- `pll_clkgen` `out_clk_o` → `core_clk`, which fans to all SoC children.
- `core_rst_n = rst_n_i & pll_locked` (children held in reset until lock).
- `pll_locked_o` exported as a top-level status output.

### 6.3 AXI-Lite control-ring map

- `AXIL_N_SLAVES` widened **6 → 7**; new `AXIL_PLL = 6` at **0x2000_7000** (4 KB).
- The PLL config/status slave (`pll_axil_regs.sv`) sits on the existing AXI-Lite control ring.

### 6.4 RTL bugs found + fixed (by the verification/RTL agents)

1. **Bootstrap deadlock** — the PLL config registers were originally clocked on the **gated core domain**, so the PLL could never be enabled to lock (chicken-and-egg: no lock → no core clock → can't write the enable). **Fix:** clock the PLL + its registers on the **reference `clk_i`/`rst_n_i`** domain, and default-enable `CONTROL[0]` at reset.
2. **PERIPH_LIMIT decode hole** — `soc_addr_map_pkg.sv` had `PERIPH_LIMIT = 0x2000_6FFF`, so PLL reads at `0x2000_7xxx` hit the crossbar **DECERR**. **Fix:** raise `PERIPH_LIMIT` to `0x2000_7FFF` to cover the new PLL slave.

### 6.5 Cosim results

| Suite | Result |
|-------|--------|
| `test_pll_lock` | 3/3 |
| `test_pll_regs` | 4/4 |
| **PLL subtotal** | **7/7** |
| `soc_boot` (regression) | 3/3 |
| `soc_periph` (regression) | 1/1 |

Regression is clean after the `AXIL_N_SLAVES` bump + clock seam. **CDC note:** RNM-mode AXI control path needs a CDC synchroniser (config writes cross from `clk_i` into `core_clk`) — **documented and deferred**. STUB mode (CI default) has `core_clk == clk_i`, so no CDC is required there.

**Env note**: full-SoC `Vtop` cosim needs `MAKEFLAGS=-j2` (OOM on a 15 GiB host otherwise); sim build dirs route to `/nobackup/sim_log`.

---

## 7. Milestones

Legend: ✅ done · 🟡 indicative/partial · ⏸️ remaining

| Milestone | Scope | Status |
|-----------|-------|--------|
| **M-a** | Analog infrastructure + architecture: `analog` devshell, dual-PDK PLL architecture + modeling | ✅ |
| **M-b1** | ASAP7 variant: circuit + ngspice (indicative, BSIM4 substitute); meta fix loop (VCO SLVT, CP array) | ✅ (electrical 🟡 indicative) |
| **M-b2** | Sky130 variant: real `sky130_fd_pr` circuit + sim, magic layout, **CP-block DRC + LVS sign-off** | ✅ (CP block; VCO/LF/BIAS regen ⏸️) |
| **M-c** | SoC integration: `rtl/soc/pll/`, clock seam, AXI-Lite slave @0x2000_7000, 2 RTL bugs fixed, cosim 7/7 + regression | ✅ |
| **M-d** | Phase 7 documentation (this plan, ROADMAP, PHASE_STATUS, CLAUDE.md) | ✅ |

**Open follow-ups** (not gating M-a..M-d): Sky130 full-chip DRC/LVS (regenerate VCO/LF/BIAS blocks via the PDK device generators — mechanical) and the RNM-mode AXI CDC synchroniser.

---

## 8. Analog-agent validation (this phase doubled as a suite test)

Phase 7 was also the first real exercise of the installed **analog-design agent suite**. Findings:

- **Real tools ran, not stubs.** Real **ngspice** electrical sims (`sky130_fd_pr`), real **magic** custom layout + DRC (`sky130A.tech`), and real **netgen** LVS all executed and produced checkable artifacts.
- **The closed-loop meta fix loop worked.** `pipeline-orchestrator` detected open `fix_request`s in `design_state.json`, dispatched the named servicer (circuit-design / custom-layout), re-validated, and closed the loop — across the VCO SLVT migration, CP array sizing (ASAP7), and CP regeneration (Sky130).
- **Adversarial physical verification earned its keep.** The `physical-verification` agent caught a **false DRC pass** (hand-drawn geometry 50× too small → 0 FETs extracted but "clean" DRC), forcing the CP block to a *genuine* sign-off (real FETs extracted, LVS MATCH). A non-adversarial check would have shipped a layout with no real transistors.
- **Agents persisted learnings.** Real experience records were written to `~/.local/share/chip-design-agents/analog/memory/<domain>/experiences.jsonl` (per-domain), feeding the memory-keeper distillation path.
- **Honest gaps surfaced rather than hidden.** The BSIM-CMG FinFET-model gap (ASAP7 indicative), the OpenVAF-absent → ngspice-behavioral fallback, and the RNM CDC requirement were all flagged in `design_state.json` and carried forward, not papered over.

Conclusion: the suite is functional end-to-end on the open toolchain, the meta orchestration and adversarial sign-off both demonstrably added value, and the limitations it reported are real PDK/tool limits rather than agent failures.

---

## 9. Honest sign-off ledger (real vs indicative vs remaining)

| Item | Status | Basis |
|------|--------|-------|
| Sky130 charge-pump **block** DRC | ✅ **real sign-off** | magic DRC = 0 on `sky130A.tech` |
| Sky130 charge-pump **block** LVS | ✅ **real sign-off** | netgen topology MATCH; 4 pfet + 1 nfet `sky130_fd_pr` devices extracted |
| Sky130 circuit electrical (Kvco, lock, CP match) | ✅ **real** | real `sky130_fd_pr` ngspice |
| ASAP7 architecture / modeling / circuit | ✅ signed off (open-toolchain) | meta fix loop closed |
| ASAP7 electrical | 🟡 **indicative** | calibrated planar BSIM4 substitute (no BSIM-CMG) |
| SoC integration (STUB + RNM cosim) | ✅ | 7/7 PLL + regression clean |
| Sky130 **full-chip** DRC/LVS (VCO/LF/BIAS) | ⏸️ **remaining** | mechanical PDK-generator regeneration of remaining blocks |
| RNM-mode AXI CDC synchroniser | ⏸️ **remaining** | documented + deferred; STUB mode needs none |

---

## 10. Out of scope / future

- Real ASAP7 silicon-grade electrical sign-off (blocked on BSIM-CMG FinFET models, absent from the open ngspice).
- Fractional-N / sigma-delta modulation, LC VCO, jitter/phase-noise sign-off — integer-N ring VCO only this phase.
- PLL hard-macro physical instantiation into the SoC PD flow (the SoC integrates the RNM, not the GDS).
