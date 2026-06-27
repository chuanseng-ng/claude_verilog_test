# Per-IP Power Domains + On/Off Sequencing — Evaluation (pre-Phase-6 #5)

**Status:** DECIDED 2026-06-27 — **GO (scoped): behavioral PMU sequencer only.** Build a clock-gate / reset / functional-isolation power-mode controller that is verifiable in the open Verilator flow. True UPF power-gating silicon (real isolation/retention cells, power switches, secondary PDN) is **deferred** — it needs a UPF-capable simulator the open flow lacks. Bead `claude_verilog_test-9m4`.

## 1. Findings

- **UPF is spec-only.** `pnr/constraints/phase5_soc.upf` *declares* 4 domains (PD_CPU/GPU/SRAM/PERIPH) + 2 power switches (PSW_CPU/GPU) + isolation (ISO_CPU/GPU) + a 4-state PST (NORMAL/CPU_OFF/GPU_OFF/IDLE) — but lines 17-18 and `pnr/asap7/soc/pdn.tcl:7-9` state explicitly: **OpenROAD does not insert switches; single-VDD; UPF carried for formal/sim only.** M11 signed off single-domain (62.9 mW, all logic powered).
- **Zero RTL hooks.** `grep cpu_pg_ctrl|gpu_pg_ctrl|cpu_iso_en|gpu_iso_en rtl/` = 0. No PMU, no power-mode registers, no retention logic. `soc_top` has no power-control ports.
- **No power-aware verification.** Verilator has **no UPF support** — it cannot model isolation-cell clamping, retention save/restore, or supply-off X-propagation. The `VERIFICATION_PLAN.md` power-down tests are aspirational/unimplemented.

## 2. The blocker that sets the scope

The goal is *test power on/off sequencing*. Real power-gating verification (does isolation clamp correctly? does retention preserve state across supply-off? does the sequencer order switch/isolation/reset correctly at the supply level?) **requires a UPF-capable simulator** (Xcelium/Questa/VCS) — **not available in this open-source (Verilator) flow**. Building the full power-gating RTL + secondary PDN (~8-12 weeks) without the ability to verify it = high effort, unverifiable, low return for a research SoC that ships single-VDD.

## 3. What IS doable now (the scoped GO)

A **behavioral power-mode controller** modeled as ordinary synchronous RTL — testable in Verilator as plain logic:

- **PMU register block** (APB4 slave, reuses `apb4_register_bank`): power-mode request register, status register, per-domain enable bits.
- **Sequencer FSM**: drives `cpu_clk_en` / `gpu_clk_en` (clock-gating via ICG) + `cpu_iso_en` / `gpu_iso_en` (functional output clamps) + per-domain reset + retention-control outputs (`cpu_ret_save`/`cpu_ret_restore`, GPU likewise), in the full UPF-ordered sequence **both directions**:
  - **Power-down** (e.g. enter CPU_OFF): assert retention-save → assert isolation (clamp outputs) → gate clock → (optionally) assert domain reset. Mirrors the `phase2_cpu.upf` rule "save BEFORE the switch opens".
  - **Power-up** (exit to NORMAL): (release domain reset) → ungate clock → assert retention-restore → de-assert isolation. Mirrors "restore AFTER the switch closes".
  - This is the actual *sequencing* logic — the part with real design content.
- **Functional isolation** = output-clamp muxes at the CPU/GPU macro boundaries (clamp to the UPF `clamp_value 0`) when the domain is "off" — behaviorally identical to isolation cells for sim, synthesizes as logic.
- **Retention scope (explicit):** the PMU *emits* the retention save/restore control signals in the correct order (forward-compatible with the deferred real-power-gating work), and the verification asserts that ordering. But in the behavioral model the domain is **clock-gated, not supply-removed**, so the macro's flops inherently keep their architectural state (MTVEC/MSTATUS/PC) across an off→on cycle — retention save/restore is therefore a **functional no-op in this model**. Real retention-cell save/restore (where the supply is actually cut and state would be lost without it) is part of the **deferred** real-power-gating scope (§4), which needs power switches + a UPF-aware simulator. So: retention *control sequencing* = in scope; retention *cell silicon / true supply-off state preservation* = explicitly out of scope here.

This delivers the **on/off-sequencing controller + its verification** (enter/exit each PST state, observe clock-gate, observe isolation clamp, confirm no functional X-leak from a gated domain). It does **not** model real supply-off, retention-cell silicon, or power switches.

## 4. Documented gap (deferred, needs new tooling)
True power-gating sign-off — real isolation/retention cells inserted in the netlist, power switches placed, secondary VDD_CPU/VDD_GPU PDN routed, UPF-aware gate-level power sim — is deferred to a future phase **gated on a UPF-capable simulator + tape-out intent**. The UPF intent (`phase5_soc.upf`) already captures it.

## 5. Decision options (this PR)
- **A — Behavioral PMU sequencer (CHOSEN):** clock-gate/reset/functional-isolation controller + Verilator tests. Own epic + per-module PRs + re-verify.
- **B — Full power-gating:** + real isolation/retention/switches/secondary-PDN + commercial UPF sim. ~8-12 wk; blocked on tooling. Deferred.
- **C — NO-GO:** keep UPF spec-only. (Rejected — the behavioral sequencer has real, verifiable design value.)

## 6. If GO (A) — implementation sketch (own PRs, each re-verified)
1. **`rtl/soc/pmu.sv`** — power-mode APB register block + sequencer FSM (clock-en, iso-en, retention save/restore, reset per domain; PST-state encode; both-direction ordering per §3). Lint via rtl-design-orchestrator.
2. Wire PMU into `soc_top`: ICG clock-gates on CPU/GPU macro clocks, isolation-clamp muxes on macro outputs, per-domain reset. (New APB slot in the periph map.)
3. **Verification**: cocotb `test_pmu.py` — enter/exit CPU_OFF/GPU_OFF/IDLE, assert clock-gate observed, isolation clamp asserted, gated-domain outputs clamped (no X-leak), sequencer ordering correct; `soc_all` stays green. Via verification-orchestrator.

## 7. Verdict line
**GO, behavioral PMU sequencer.** Real power-gating silicon deferred (tooling-gated). Tracking: GitHub epic + children below.
