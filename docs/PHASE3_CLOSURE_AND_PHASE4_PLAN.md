# Phase 3 Closure + Phase 4 (GPU-Lite SIMT) Implementation Plan

> **Golden spec** — once this plan is approved, the first execution step is to
> copy it verbatim to `docs/PHASE3_CLOSURE_AND_PHASE4_PLAN.md` so future
> Claude Code sessions in this repo can load it as the authoritative reference
> for finishing Phase 3 and executing Phase 4. Keep this plan file and the doc
> in sync — edits to one must be mirrored to the other.

---

## 1. Context

**Why this plan exists.** The repo just signed off ASAP7 Run 43 at 1418 MHz
(commit `901fca6`, 2026-05-20) which integrated the Phase 2 pipeline **and**
the Phase 3 I-cache / D-cache / arbiter RTL into a single timing-closed top.
The recent campaign was driven through `phase-2-3/asap7-run-rtl-ppa-improv`.

However, two things are still open:

1. **Phase 3 is RTL-complete but not formally signed-off in verification.**
   `docs/PHASE_STATUS.md` still marks Phase 3 as 🔄 IN PROGRESS. Two gates
   listed in `CLAUDE.md` § "Phase 3 Workflow" remain unconfirmed since cache
   integration: (a) the 111-test Phase 2 regression must be re-run with caches
   enabled (FENCE.I is now a legal instruction rather than an illegal-instr
   trap), (b) the 50,000-instruction random regression must be re-run with
   caches enabled.
2. **Phase 4 (GPU-Lite SIMT) has not started in RTL.** The spec
   (`docs/design/PHASE4_GPU_ARCHITECTURE_SPEC.md`, frozen) and the Python
   reference model (`tb/models/gpu_kernel_model.py`, 507 LOC, 12/12 tests
   passing) are ready, but `rtl/gpu/` and `tb/cocotb/gpu/` do not yet exist.

The intended outcome is: (i) close Phase 3 with a recorded sign-off, then
(ii) implement Phase 4 RTL to full CLAUDE.md scope (9 modules including
shared memory), with AXI4-Lite control, and close with an ASAP7 GPU-block
PD sign-off comparable to Run 43.

**User decisions captured for this plan** (asked 2026-05-20):

| Question | Decision |
|---|---|
| Phase 3 gap handling | Close Phase 3 verification first, before any Phase 4 RTL |
| Phase 4 scope | Full CLAUDE.md scope — all 9 modules including `shared_memory.sv` |
| GPU control interface | **AXI4-Lite slave** (overrides any APB3 wording in the spec) |
| Phase 4 PD scope | RTL + sim sign-off **plus** ASAP7 GPU-block PD sign-off |

---

## 2. Current State (verified during planning, 2026-05-20)

### Phase 3 RTL — all present
- `rtl/mem/rv32i_cache_pkg.sv` ✅ (49 lines)
- `rtl/mem/rv32i_icache.sv` ✅ (~500 lines, 4 KB direct-mapped, FENCE.I, ASAP7/Sky130/FreePDK45 SRAM selectable)
- `rtl/mem/rv32i_dcache.sv` ✅ (~700 lines, 4 KB write-back + write-allocate, 5-state FSM)
- `rtl/mem/rv32i_cache_arbiter.sv` ✅ (D-cache priority)
- `rtl/cpu/core/rv32i_core.sv` ✅ (instantiates `u_icache`, `u_dcache`, `u_cache_arb`)
- Modified pipeline stages, decoder, hazard unit, pipeline package ✅

### Phase 3 verification artefacts — present but not formally re-gated
- `tb/models/cache_model.py` ✅ (DirectMappedCache, 257 LOC)
- `tb/cocotb/mem/test_icache.py` ✅ (~387 lines)
- `tb/cocotb/mem/test_dcache.py` ✅ (~487 lines, 8 cocotb tests last seen passing 2026-05-15)
- `tb/cocotb/cpu/test_cache_integration.py` ✅ (10.8 KB)

### Phase 3 verification gates — open
- Phase 2 regression (`tb/cocotb/cpu/`, 111 tests) **not re-run** since caches
  landed. FENCE.I is now legal — any test asserting it traps would now fail.
- 50,000-instruction random regression with caches enabled — **not recorded**
  for the cache-integrated DUT.
- `docs/PHASE_STATUS.md` and `docs/ROADMAP.md` still mark Phase 3 as in
  progress.

### Phase 4 — spec frozen, reference model done, RTL absent
- `docs/design/PHASE4_GPU_ARCHITECTURE_SPEC.md` — 16.3 KB, FROZEN
- `tb/models/gpu_kernel_model.py` — 507 LOC, 12/12 pytest tests passing
- `tb/tests/test_gpu_model.py` — 375 LOC
- `rtl/gpu/` — does not exist
- `tb/cocotb/gpu/` — does not exist
- No GPU SDC / config files under `pnr/asap7/`

### Tooling patterns to reuse
- Simulation: `sim/Makefile` with `MODULE=tb.cocotb.<pkg>.<test>`,
  Verilator backend, `SRAM_TARGET={freepdk45,sky130,asap7}`.
- BFMs: `tb/cocotb/bfm/` already has AXI4-Lite master and APB3 master.
- pyuvm framework: `tb/cpu_uvm/` (5 agents, scoreboards, sequences) — copy
  pattern for `tb/gpu_uvm/`.
- PD: `pnr/asap7/config.json`, `pnr/asap7/constraints/asap7.sdc`,
  `pnr/asap7/macro_placement.cfg` — clone for GPU-block run.
- Memory: existing ASAP7 SRAM macro `sram_1rw_256x32_asap7_TT_0p7V_25C.lib`
  — reusable for GPU register file and shared memory banks (with sizing
  adjustments).

---

## 3. Plan — Step 0: Persist this plan as the golden spec

Before any code or PD work, copy this file to a project-tracked location so
future sessions load it deterministically.

- **Action:** create `docs/PHASE3_CLOSURE_AND_PHASE4_PLAN.md` with this
  document's content verbatim (omit the `Step 0` self-reference at the top of
  this section once copied; add a front-matter note that this doc was hand-
  promoted from `~/.claude/plans/read-and-check-if-shiny-hennessy.md`).
- **Update `CLAUDE.md`** "Key Documentation > Architecture & Design" table to
  add a row pointing at `docs/PHASE3_CLOSURE_AND_PHASE4_PLAN.md`.
- **Update `docs/PHASE_STATUS.md`** "Next Steps" to link the new doc.
- **Commit** with `[Doc] Add Phase 3 closure + Phase 4 implementation plan as golden spec`.

Rationale: Plan-mode `~/.claude/plans/*.md` files are per-user and not
checked into the repo. Future sessions need a repo-tracked source of truth.

---

## 4. Plan — Phase 3 Closure (must complete before any Phase 4 RTL)

### 4.1 Re-run Phase 2 regression with caches enabled
- **Target:** all 111 tests in `tb/cocotb/cpu/` pass against the
  cache-integrated `rv32i_core.sv`.
- **Driver:** `cd sim && make test` inside `nix-shell ~/Downloads/Github/librelane`.
  Iterate over the 111 known test modules; capture pass/fail count and any
  failing modules in `docs/regression/PHASE3_CACHE_REGRESSION.md`.
- **FENCE.I expectation:** any test that previously asserted FENCE.I traps as
  illegal must be updated to assert FENCE.I executes cleanly and (for D$
  dirty lines) does **not** disturb D-cache state. Document the diff.
- **Coverage delta:** record cache hit/miss counts via the existing
  `tb/cocotb/common/coverage.py` scaffold; commit the report.

### 4.2 50,000-instruction random regression with caches
- **Driver:** `tb/generators/rv32i_instr_gen.py` (already used for Phase 2's
  50k regression). Re-run with cache-integrated DUT.
- **Scoreboard:** `tb/cocotb/common/scoreboard.py` compares DUT commit
  stream against `rv32i_model.py`. Cache misses must be invisible to the
  scoreboard (architectural state only).
- **Pass criterion:** 0 mismatches across 50,000 instructions; record seed,
  duration, and mismatch count in
  `docs/regression/PHASE3_RANDOM_REGRESSION.md`.
- **Random FENCE.I:** include FENCE.I in the random instruction mix at low
  probability (≈1 %) to exercise the I-cache invalidate path.

### 4.3 Phase 3 sign-off documentation
- Add `docs/PHASE3_SIGNOFF.md` summarising: RTL files frozen, regression
  results (4.1 + 4.2), ASAP7 Run 43 metrics that already cover this RTL
  (1418 MHz / 27.27 mW / 3 844 µm² / +5.97 ps slack), reference-model
  cross-validation status. Mirror the Phase 2 sign-off doc format.
- Update `docs/PHASE_STATUS.md` to mark Phase 3 ✅ COMPLETE with the
  sign-off date and link.
- Update `docs/ROADMAP.md` Phase 3 row to ✅.
- Commit: `[Spec] Phase 3 sign-off — caches verified vs reference model`.

### 4.4 Phase 3 exit gate
Phase 4 RTL work does **not** start until 4.1, 4.2, and 4.3 are all on
`main` (or merged into the Phase 4 working branch). This is a hard gate.

---

## 5. Plan — Phase 4 RTL Implementation

### 5.1 Branch + scaffolding
- Branch: `phase-4/gpu-lite-rtl` off `main` after Phase 3 closure merges.
- Create `rtl/gpu/` and `tb/cocotb/gpu/` (empty placeholders committed first
  so the rest of the work lands in small reviewable commits).
- Create `tb/gpu_uvm/` mirroring `tb/cpu_uvm/` structure (env, agents,
  monitors, scoreboards, sequences, tests).

### 5.2 RTL module list (full CLAUDE.md scope, 9 modules)
All paths under `rtl/gpu/`:

| # | File | Responsibility |
|---|---|---|
| 1 | `gpu_pkg.sv` | Constants, struct typedefs, opcode enums, lane/warp count parameters |
| 2 | `gpu_top.sv` | Top-level. AXI4-Lite slave (control regs), AXI4 master (memory), `gpu_irq` output |
| 3 | `gpu_command_queue.sv` | Kernel descriptor FIFO: kernel PC, grid_dim_{x,y,z}, block_dim_{x,y,z}, arg pointer |
| 4 | `warp_scheduler.sv` | Round-robin warp ready selection, per-warp PC + active_mask, divergence reconverge |
| 5 | `gpu_compute_unit.sv` | 4-stage FETCH/DECODE/EX/WB pipeline; instantiates ALU, regfile, divergence stack |
| 6 | `vector_register_file.sv` | 32 regs × 8 lanes per warp; up to 8 warps (256 regs per warp × 8 = 64 KiB if all warps active; size against SRAM macro) |
| 7 | `vector_alu.sv` | 8 parallel ALU lanes — VADD, VSUB, VMUL, VAND, VOR, VXOR, VSLL, VSRL, VSRA, VADDI, VANDI, VORI, VXORI |
| 8 | `gpu_memory_unit.sv` | Per-lane address generation; issues to coalescer; handles VLD / VST |
| 9 | `memory_coalescer.sv` | 8 per-lane requests → minimal AXI4 transactions (consecutive-address detection within 32-byte line) |
| 10 | `shared_memory.sv` | 16 KB scratchpad, 32 banks, single-port per bank, SRAM-macro backed |

(Yes, 10 files — `gpu_pkg.sv` is a structural prerequisite added on top of
the 9 functional modules in CLAUDE.md.)

### 5.3 ISA implementation order
1. Arithmetic + immediate: VADD, VSUB, VADDI, VAND, VOR, VXOR, VANDI, VORI, VXORI, VSLL, VSRL, VSRA — covered by `vector_alu.sv` alone.
2. VMUL — single-cycle in `vector_alu.sv` for Phase 4 (no pipelining yet).
3. Special-register reads: tid.x/y/z and bid.x/y/z via `VMOV` — sourced from `warp_scheduler.sv` per-warp state and broadcast to lanes.
4. Memory: VLD, VST → exercise `gpu_memory_unit.sv` → `memory_coalescer.sv`.
5. Branch: VBEQ, VBNE, VBLT, VBGE — per-lane condition; if both masks non-zero, push (return_pc, mask_not_taken) onto divergence stack in `gpu_compute_unit.sv`.
6. Control: VJMP (unconditional), VRET (warp completion), VSYNC (barrier — wait for all warps in block).

### 5.4 Control interface (AXI4-Lite slave) — register map
Base 0x2000_1000, 4 KiB window. AXI4-Lite 32-bit data, 12-bit byte address.

| Offset | Reg | Direction | Description |
|---|---|---|---|
| 0x000 | GPU_CTRL | RW | [0]=launch, [1]=reset, [2]=irq_enable |
| 0x004 | GPU_STATUS | RO | [0]=idle, [1]=done, [2]=error, [7:4]=active_warp_mask |
| 0x008 | GPU_KERNEL_PC | RW | Kernel entry PC |
| 0x00C | GPU_GRID_X | RW | Grid dim X |
| 0x010 | GPU_GRID_Y | RW | Grid dim Y |
| 0x014 | GPU_GRID_Z | RW | Grid dim Z |
| 0x018 | GPU_BLOCK_X | RW | Block dim X |
| 0x01C | GPU_BLOCK_Y | RW | Block dim Y |
| 0x020 | GPU_BLOCK_Z | RW | Block dim Z |
| 0x024 | GPU_ARG_PTR | RW | Kernel argument base pointer (memory address) |
| 0x028 | GPU_IRQ_CLR | W1C | Writing 1 clears `gpu_irq` |
| 0x030–0x06C | GPU_PERFCNT[0..15] | RO | 16 perf counters (cycles, instructions retired, warps active, divergence events, coalesced txns, scatter txns, etc.) |

The register bank is implemented in `gpu_top.sv` (or a small
`gpu_axil_regbank.sv` if cleaner). Reuse the same `tb/cocotb/bfm/axil_master.py`
pattern as Phase 1/2 debug.

### 5.5 Memory interface (AXI4 master)
- 32-bit address, 32-bit data (Phase 4). No burst — single-beat transactions.
- Phase 5 upgrades this to AXI4 burst when the SoC crossbar lands; treat
  `gpu_memory_unit.sv` ports as already AXI4 (AW/W/B/AR/R channels) with
  `AWLEN=0`/`ARLEN=0` hard-wired in Phase 4 — this avoids re-plumbing in
  Phase 5.

### 5.6 Coalescing heuristic (Phase 4 simple form)
- Active lanes' byte addresses all fall in the **same 32-byte window** and
  are strictly increasing in 4-byte increments → issue 1 AXI transaction
  per active lane bit-set (32-bit data path; 8 lanes max ⇒ up to 8 single
  beats, scheduled back-to-back).
- Otherwise → serialise: one AXI transaction per active lane.
- (Phase 5 upgrades this to true burst coalescing.)

### 5.7 Shared memory
- 16 KiB total, 32 banks × 16 word entries × 4 B per word.
- Single-port SRAM macro per bank → 32 instances of a small 16×32 SRAM.
- If 16×32 macro is not available in `pnr/asap7/`, synthesise from
  registers for Phase 4 RTL and plan a macro substitution PR in Phase 5.
- Bank conflict policy: simple stall — if two lanes hit same bank in the
  same cycle, serialise.

### 5.8 Divergence stack
- Per warp: 4-entry stack of (return_pc, return_mask). Phase 4 spec only
  promises one-level divergence, so 4 entries is generous headroom; stack
  full ⇒ assert an error bit in GPU_STATUS and halt.

### 5.9 Coding standards
- SystemVerilog 2017, lint-clean under Verilator.
- Style consistent with `rtl/cpu/core/pipeline/*.sv` (always_ff for
  registers, always_comb for combinational; explicit reset).
- Every module: header comment block with purpose, parameters, ports.
- One module per file; package types in `gpu_pkg.sv`.

---

## 6. Plan — Phase 4 Verification

### 6.1 Reference model — already done
`tb/models/gpu_kernel_model.py` (507 LOC) is the golden model. All scoreboards
compare DUT against this. **Do not modify the reference model semantics
without updating the spec and the 12 existing pytest cases.** If RTL behaviour
deviates from the model, fix the RTL.

### 6.2 Cocotb unit tests (`tb/cocotb/gpu/`)
- `test_warp_scheduler.py` — round-robin ordering, warp ready/busy, divergence reconverge.
- `test_vector_alu.py` — every opcode, per-lane masking, immediate forms.
- `test_vector_regfile.py` — write/read per lane per warp, x0 hardwired-zero invariant.
- `test_memory_unit.py` — VLD/VST single-lane, scatter, contiguous (coalesced).
- `test_memory_coalescer.py` — 8-lane contiguous, 8-lane scatter, mixed-mask scatter, bank-aligned vs unaligned.
- `test_shared_memory.py` — single-bank no conflict, 2-lane same-bank conflict serialised.
- `test_divergence.py` — single-level if/else, nested-attempt overflow → error bit.
- `test_command_queue.py` — back-to-back kernel descriptor accept, full → backpressure.

### 6.3 Kernel-level tests (`tb/cocotb/gpu/kernels/`)
Each kernel runs against both DUT and reference model; scoreboard checks
register file end-state and memory end-state.

- `kernel_vector_add.py` — c[i] = a[i] + b[i] over 64 elements.
- `kernel_dot_product.py` — exercise serial reduction (Phase 4 has no atomics, so reduction is per-warp local + CPU final sum).
- `kernel_divergence_basic.py` — `if (tid.x < 4) ... else ...` with mask verification.
- `kernel_memory_coalesce.py` — proves coalescer issues fewer AXI txns than serial form.
- `kernel_shared_memory_pingpong.py` — lane writes shared[tid], reads shared[7-tid].
- `kernel_sync.py` — VSYNC barrier across two warps.

### 6.4 SoC-precursor integration test
A lightweight harness `tb/cocotb/gpu/test_cpu_gpu_handoff.py` that wires
`rv32i_cpu_top` (with caches) and `gpu_top` to a shared behavioural memory
and an AXI4-Lite crossbar stub. CPU writes a kernel descriptor, launches the
GPU, polls GPU_STATUS, reads the result. Proves the Phase 5 integration
contract without building the full crossbar.

### 6.5 Random kernel regression
- 1,000 randomly generated kernels (grid 1–8, block 1–32, length 4–32
  instructions) against the reference model.
- Pass criterion: 0 architectural mismatches; no deadlocks (100k-cycle
  watchdog per kernel).
- Record in `docs/regression/PHASE4_RANDOM_KERNELS.md`.

### 6.6 Phase 3 regression must still pass
After Phase 4 lands on the integration branch, re-run Phase 2+3 regression
(4.1 + 4.2 above) with the **CPU-only** DUT to prove no shared-package or
shared-file edits broke Phase 3. Hard gate before PD.

---

## 7. Plan — Phase 4 ASAP7 GPU-block PD Sign-off

### 7.1 Clone Phase 2+3 PD config
- New tree: `pnr/asap7/gpu/` containing `config.json`, `macro_placement.cfg`,
  `pdn.tcl`, `constraints/asap7_gpu.sdc`.
- DESIGN_NAME = `gpu_top`. Use only `rtl/gpu/*.sv` plus `gpu_pkg.sv` in
  `VERILOG_FILES`.

### 7.2 SDC starting point
- Same clock topology as `pnr/asap7/constraints/asap7.sdc`: 705 ps period,
  15/10 ps setup/hold uncertainty, 50 ps source latency, 10 ps transition.
- IO budget 150 ps for AXI4-Lite + AXI4 ports; 120 ps for `gpu_irq`.
- SRAM macros (register file banks, shared memory banks): same ICG-gated
  `gclk_sram` generated clock + false-path pattern used in
  `pnr/asap7/runs/RUN_2026-05-20_06-27-10/`.

### 7.3 Target frequency
Initial target 1418 MHz (705 ps) to match the CPU sign-off. If the GPU's
3-deep ALU + register-file write-back path can't meet 705 ps at first
attempt, fall back through 800 / 900 / 1000 ps period in the same
LibreLane-driven incremental campaign Phase 2+3 used (Runs 7→43).

### 7.4 Sign-off gates
- WNS ≥ 0 ps setup, WNS ≥ 0 ps hold at TT 0.7 V 25 °C.
- 0 DRC, 0 antenna, 0 LVS short / open.
- Power estimate recorded; area recorded.
- Final run committed as `[PD] ASAP7 Phase 4 GPU sign-off: Run N @ <freq> / <power>`.
- Append to `docs/ASAP7_RUN_HISTORY.md`.

### 7.5 Memory bookkeeping
- Update `tb/models/cache_model.py`-style memory file is not needed for GPU;
  instead, append a Phase 4 section to `docs/ASAP7_RUN_HISTORY.md`.
- Update `MEMORY.md` index with a new `project_asap7_gpu_run_state.md`
  reference for Phase 4 PD runs.

---

## 8. Critical Files

### To create
| Path | Notes |
|---|---|
| `docs/PHASE3_CLOSURE_AND_PHASE4_PLAN.md` | This plan, hand-promoted from `~/.claude/plans/`. Step 0 of execution. |
| `docs/PHASE3_SIGNOFF.md` | Phase 3 closure record. |
| `docs/regression/PHASE3_CACHE_REGRESSION.md` | 111-test cache regression result. |
| `docs/regression/PHASE3_RANDOM_REGRESSION.md` | 50k random regression result. |
| `docs/regression/PHASE4_RANDOM_KERNELS.md` | 1k kernel regression result. |
| `rtl/gpu/gpu_pkg.sv` | Constants and types. |
| `rtl/gpu/gpu_top.sv` | Top with AXI4-Lite slave + AXI4 master + irq. |
| `rtl/gpu/gpu_command_queue.sv` | Kernel descriptor FIFO. |
| `rtl/gpu/warp_scheduler.sv` | Round-robin scheduler. |
| `rtl/gpu/gpu_compute_unit.sv` | 4-stage pipeline + divergence stack. |
| `rtl/gpu/vector_register_file.sv` | 32 regs × 8 lanes × 8 warps. |
| `rtl/gpu/vector_alu.sv` | 8-lane ALU. |
| `rtl/gpu/gpu_memory_unit.sv` | Address gen + VLD/VST. |
| `rtl/gpu/memory_coalescer.sv` | 8→N AXI txn collapsing. |
| `rtl/gpu/shared_memory.sv` | 16 KiB / 32 banks scratchpad. |
| `tb/cocotb/gpu/test_*.py` | 8 unit tests + 6 kernel tests + 1 handoff test. |
| `pnr/asap7/gpu/config.json` | GPU-block PD config. |
| `pnr/asap7/gpu/constraints/asap7_gpu.sdc` | GPU SDC. |
| `pnr/asap7/gpu/macro_placement.cfg` | SRAM macro placement. |
| `pnr/asap7/gpu/pdn.tcl` | Power grid for GPU block. |

### To modify
| Path | Why |
|---|---|
| `CLAUDE.md` | Add doc link to golden spec; update Phase 3 ✅ status; update Phase 4 status from ⏸️ to 🔄 once started. |
| `docs/PHASE_STATUS.md` | Phase 3 → ✅; Phase 4 → 🔄; link golden spec. |
| `docs/ROADMAP.md` | Phase 3 → ✅; Phase 4 status row. |
| `docs/ASAP7_RUN_HISTORY.md` | Append Phase 4 GPU runs. |
| `sim/Makefile` | Add GPU test discovery if needed (likely already pattern-matches `tb.cocotb.gpu.*`). |

### To reuse (do not modify)
| Path | Why |
|---|---|
| `tb/models/gpu_kernel_model.py` | Golden reference. Frozen. |
| `tb/models/memory_model.py` | Shared memory backing store. |
| `tb/cocotb/bfm/axil_master.py` | AXI4-Lite control BFM. |
| `tb/cocotb/common/clock_reset.py`, `coverage.py`, `scoreboard.py` | Shared utilities. |
| `pnr/asap7/sram_1rw_256x32_asap7_TT_0p7V_25C.lib` and macro files | Reusable for GPU. |
| `docs/design/PHASE4_GPU_ARCHITECTURE_SPEC.md` | Frozen spec, source of truth for ISA + semantics. |

---

## 9. Verification end-to-end

Once Phase 4 RTL + tests + PD are landed, the verification story to prove
Phase 4 sign-off is:

1. `cd sim && nix-shell ~/Downloads/Github/librelane --run "make lint"` →
   Verilator lint clean across all of `rtl/` including `rtl/gpu/`.
2. `make test MODULE=tb.cocotb.gpu.test_warp_scheduler` … through all 8 GPU
   unit tests → all pass.
3. `make test MODULE=tb.cocotb.gpu.kernels.kernel_vector_add` … through all
   6 kernel tests → all pass.
4. `make test MODULE=tb.cocotb.gpu.test_cpu_gpu_handoff` → handoff smoke
   passes.
5. Random kernel regression script (new under `tb/generators/`) →
   1000 kernels, 0 architectural mismatches, 0 deadlocks.
6. Re-run Phase 2+3 regression (CPU-only DUT) → 111/111 + 50k random pass.
7. `make librelane-asap7` on `pnr/asap7/gpu/config.json` (or a new make
   target `librelane-asap7-gpu`) → WNS ≥ 0, hold ≥ 0, 0 DRC, 0 antenna.
8. Commit run history entry → tag Phase 4 ✅ in `docs/PHASE_STATUS.md`.

---

## 10. Risks and mitigations

| Risk | Likelihood | Mitigation |
|---|---|---|
| FENCE.I randomisation surfaces I-cache bug | Medium | Restrict random FENCE.I to 1 % rate initially; if failures, fix RTL — Phase 4 cannot start with broken FENCE.I. |
| GPU register file too big for ASAP7 single-tile | Medium | If 64 KiB register file doesn't fit, reduce to 4 warps in Phase 4; carry note for Phase 5 expansion. |
| Coalescer false-positives miscombine txns | High at first | Start with serial-only path, add coalescing behind a parameter `GPU_ENABLE_COALESCE`, default 0; flip on after dedicated tests pass. |
| Divergence stack overflow in random kernels | Low | Generator restricts to one-level branches; document this constraint in the kernel generator README. |
| ASAP7 GPU sign-off can't hit 1418 MHz | Medium | Iterative PD campaign mirroring Phase 2+3 Runs 7→43; acceptable Phase 4 closure target is any frequency ≥ 1000 MHz with all DRC/LVS clean — record the gap and revisit in Phase 5 integration. |
| Shared memory 32-bank single-port macro unavailable | High | Phase 4 falls back to flop-array shared memory; record as Phase 5 macro-substitution task. |
| Plan-mode plan file diverges from golden-spec doc | Low | Step 0 commits the doc; thereafter only edit the doc. Stop editing the plan-mode file once doc is committed. |

---

## 11. Out of scope (explicitly deferred to Phase 5)

- AXI4 burst mode for GPU memory unit (Phase 4 uses single-beat).
- True multi-master AXI4 crossbar (Phase 4 uses a stub for the handoff test).
- DMA engine, UART, SPI, timer, interrupt controller (all Phase 5).
- L2 cache (only added if Phase 5 benchmarks justify it per CLAUDE.md
  "Locked Architecture Decisions").
- Sky130 and FreePDK45 PD for GPU block (ASAP7 only in Phase 4).
- Power domains UPF for GPU block (Phase 5 SoC integration adds PD_GPU).

---

## 12. How future sessions should use this plan

1. After Step 0 lands, `docs/PHASE3_CLOSURE_AND_PHASE4_PLAN.md` is the
   authoritative source. Always read it first.
2. The `~/.claude/plans/read-and-check-if-shiny-hennessy.md` copy is
   stale-by-default once the doc lands; ignore it.
3. Section numbers in this plan are stable — reference them in commit
   messages, e.g. `[GPU] Phase 4 §5.6 — coalescer contiguous-window detect`.
4. Updates to the plan must come through a `[Doc]` commit that edits the
   project-tracked doc, never via a plan-mode file edit.
