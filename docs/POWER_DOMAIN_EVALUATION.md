# Per-IP Power Domains + On/Off Sequencing — Evaluation (pre-Phase-6 #5)

**Status:** DECIDED 2026-06-27 — **GO (scoped): behavioral PMU sequencer only.** Build a clock-gate / reset / functional-isolation power-mode controller that is verifiable in the open Verilator flow. True UPF power-gating silicon (real isolation/retention cells, power switches, secondary PDN) is **deferred** — it needs a UPF-capable simulator the open flow lacks. Bead `claude_verilog_test-9m4`.

## Update 2026-10-17 (bead `h3lm`): the UPF was audited and rewritten

The sections below are the 2026-06-27 decision record and are kept as history. Two of their
statements are no longer true:

- "Zero RTL hooks" and the `cpu_iso_en` / `gpu_iso_en` / `cpu_pg_ctrl` names. The PMU and the clamps
  exist (`pmu.sv`, `soc_top.sv`). The original `phase5_soc.upf` named those nets and two power-switch
  control ports that never existed in `soc_top`, isolated every output while the RTL clamps a handful of
  handshakes, and used option syntax no UPF parser accepts. It is rewritten (IEEE 1801-2015) and
  checked against the elaborated RTL in CI by `tools/verif/check_upf.py`.
- `phase5_soc.upf:23` ("no retention registers") and `:94-95,103-104` (the switches). Those lines
  moved; the file now has **no power switches** (the PMU emits no switch control) and **no retention**.
  Line numbers are no longer cited; use the section names in the UPF header.

What the audit found beyond syntax, kept here because they are design facts, not UPF facts:

1. `m_axil_if_rready` (GPU instruction-fetch R-channel accept) was the one GPU-to-fabric handshake
   `soc_top` did not clamp. It is now clamped like the other seven GPU signals (ISO_GPU is 8 signals,
   ISO_CPU is 6).
2. The previous UPF's "state rebuilt from SRAM on wakeup" was never implemented (section 3).
3. **Isolation versus reset ordering had no handshake (FIXED, bead `3ogd`).** The CPU clamp control passes a
   2-flop synchroniser, the reset a `cdc_reset_sync` with asynchronous assertion; "isolate first" held only
   because 2 x 780 ps is shorter than two PMU cycles of 1750 ps, and failed for a CPU clock slower than the
   fabric clock (reproduced: at 3x slower the reset asserted 6 core cycles before the clamp). Now an
   iso-ack handshake: `soc_top`'s `u_cpu_iso_ack_sync` returns the CPU-domain clamp control to the PMU,
   whose CPU `DOM_PD_ISO` holds the clock gate and the reset until it is seen active, and whose `DOM_PU_ISO`
   holds the settle at ON until it is seen released (4-phase). The UPF step order is unchanged. Bounded by
   `ISO_ACK_TIMEOUT` (255 cycles) with sticky `STATUS[3]` so a dead CPU clock cannot hang the PMU. Cost:
   the CPU power-down and power-up each take longer by the ack round trip (measured: +2 / +4 / +8 / +15
   core cycles per direction for a CPU clock 7:3 faster / 1:1 / 3x / 8x slower than the fabric).
   See the "Isolation handshake" block in `rtl/soc/pmu.sv`.
4. **Scan mode does not override the PMU or the clamps.** Clock gates (`test_en`) and resets are forced
   by `scan_mode_i`, but the PMU is ordinary scan-chain state, so a clamp can be active under scan. The
   UPF `SCAN` state says "all ON"; the mismatch is documented in `docs/design/UPF_POWER_SPEC.md`.
5. Slave-side response outputs of `u_gpu` / `u_cpu` are unclamped by design (section 4 scope).

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
- **Retention scope (explicit):** the PMU *emits* the retention save/restore control signals in the correct order (forward-compatible with the deferred real-power-gating work), and the verification asserts that ordering. But in the behavioral model the domain is **clock-gated, not supply-removed**, and retention save/restore is a **functional no-op in this model**. ⚠️ **Corrected 2026-10-09 (bead `4a7i`):** whether a domain's flops keep their state across an off→on cycle depends on its reset style, not on the clock gating alone. The **CPU** domain uses synchronous reset, and the PMU asserts and releases its reset only while the clock is gated, so CPU state (MTVEC/MSTATUS/PC) does survive — but as a behavioural-model artifact, not retention. The **GPU** domain (`gpu_top`, `gpu_compute_unit`, `warp_scheduler`, …) uses asynchronous reset (`always_ff @(posedge clk or negedge rst_n)`), so asserting `pmu_gpu_rst_n` clears its state (IRQ latch, `GPU_CTRL.irq_enable`, `STATUS.done`) even with the clock gated — reproduced by `tb/cocotb/soc/test_soc_integration.py::test_soc_gpu_isolation_via_pmu`. Neither domain models real retention; real silicon with no retention cells (none in Phase 5, `phase5_soc.upf` header) loses state in both, so the GPU behaviour is the realistic one. **Software must re-initialise the GPU after power-up** (and should not rely on CPU state surviving either). Real retention-cell save/restore (where the supply is actually cut and state would be lost without it) is part of the **deferred** real-power-gating scope (§4), which needs power switches + a UPF-aware simulator. So: retention *control sequencing* = in scope; retention *cell silicon / true supply-off state preservation* = explicitly out of scope here.

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
