# Project Phase Status

Last updated: 2026-09-26

## Current Phase

**Phase 5: SoC Integration** - ✅ COMPLETE (2026-06-24) — M1–M12 done. M10 L2 gate → NO-GO (`docs/M10_L2_DECISION_ANALYSIS.md`); M11 ASAP7 SoC P&R signed off **571 MHz / 62.9 mW / 520×520 µm / 65.6 % util / 0 DRC / 0 antenna** (sv2v frontend; `docs/PHASE5_RUN_HISTORY.md`). Indicative ASAP7 (predictive PDK). ⚠️ **Timing/power now also unvalidated** (bead `8f3`/`0p6`, 2026-09-16): produced by `OpenROAD.STAMidPNR-3` without an in-session re-route, a defect proven to give false-clean zero-wire STA; run 14's artifacts are wiped and cannot be re-checked. ✅ **Update 2026-09-18 (bead `0d0`)**: the SoC on *current* RTL has since been re-measured three times on the fixed flow (`STA_POSTGRT_INSESSION_GRT=1`, pinned OpenROAD 26Q2, annotation-gated). Current honest point, superseding the earlier 258.5 mW / −2084 ps snapshot: **setup WNS −727.37 ps / TNS −60,665 ps / 781 violators, hold CLEAN, 283.6 mW total / 89.6 mW fabric-only** (`RUN_2026-09-17_20-41-11`). Timing is still NOT closed at 1750 ps, and run 14's own numbers remain unvalidated — `docs/PHASE5_RUN_HISTORY.md` §"Power figure caveat".

**Phase 7: Mixed-Signal PLL Clock Generator** - 🚧 IN PROGRESS — M-a/M-b1/M-b2/M-c ✅ complete (2026-06-20); M-d = documentation (this update). Dual-PDK charge-pump PLL via analog-design agents (ASAP7 indicative + Sky130 real CP-block DRC/LVS), AMS RNM integrated as SoC clock source. See `docs/PHASE7_MIXED_SIGNAL_PLL_PLAN.md`. (Phase 7 ran alongside the in-progress Phase 5 PD/sign-off tail.)

- M1–M8 ✅: AXI4 crossbar + AXI-Lite ring, cache burst upgrade, peripherals (UART/SPI/timer/IRQ), DMA, behavioral SRAM, perf counters, SoC top.
- M9 ✅ SoC verification: boot 100/100; DMA+UART+SPI loopback; SW coherency (D$ flush→GPU→D$ inval); CPU-GPU IRQ integration; DUT-side boot SRAM check. `soc_all` 73/73 at M9 (now 120/120 — see the PMU entry below); 1M+ cycle stress (1,079,867 cyc, 0 fail). Two RTL bugs found+fixed: D-cache MMIO caching (`go9`) and axi4_crossbar AR/AW handshake+arbitration (`7fs`).

**Phase 6a: GPIO controller (bead `ckc`)** - ✅ COMPLETE (2026-09-26; RTL 2026-09-20, Sky130 harden 2026-09-26). First Phase 6 peripheral. New `rtl/periph/gpio_controller.sv` — APB4 slave on `apb4_register_bank`, 32 pins.

- **Bus**: APB4, per `docs/PERIPHERAL_BUS_EVALUATION.md` ("Phase 6 peripherals become trivial APB drop-ins"). The "AXI4-Lite" wording in `docs/ROADMAP.md` and `CLAUDE.md` was stale and has been corrected.
- **Integration**: APB slave index 7 at `0x2000_A000–AFFF`; `APB_N_SLAVES` 7 → 8; `AXIL_APB_LIMIT` and `PERIPH_LIMIT` both extended `0x2000_9FFF` → `0x2000_AFFF` — the same two-edit pattern used for PLL, PMU and PLL2. New IRQ source at `interrupt_controller` bit 5 (`N_SOURCES` 5 → 6).
- **Pins**: unidirectional triplet `gpio_out_o[31:0]` / `gpio_oe_o[31:0]` / `gpio_in_i[31:0]` on `soc_top`. There is **no tristate anywhere in this RTL tree** and the Sky130 SoC hardens as a core macro with no pad ring, so the bidirectional merge is deliberately a pad-ring integration concern. `gpio_in_i` is asynchronous and is synchronised per pin by `N_PINS` separate `cdc_2ff_sync #(.WIDTH(1))` instances — not one wide instance, because that primitive's scope warning forbids multi-bit binary buses.
- **Interrupts**: per-pin level/edge with polarity. `GPIO_IRQ_STAT` is **edge-sticky / level-live** (ARM PL061 semantics): edge-mode bits latch until a `GPIO_IRQ_CLR` write, with a set beating a same-cycle clear so an edge is never lost to a racing clear; level-mode bits track their condition live and ignore `GPIO_IRQ_CLR` entirely. A fully sticky raw register was rejected because the reset defaults (level, active-low, pins low) make every pin's condition true, latching all-ones out of reset. `GPIO_IRQ_EN` masks the output only. `irq_o` is level-held, which the 2-FF CPU-domain crossing at `soc_top.sv:623-627` requires.
- **Verification**: `test_gpio` **16/16** (reset defaults incl. the deliberate all-ones `GPIO_IRQ_STAT` at level/active-low defaults, RW round-trip, output/OE mirroring, the cycle-exact 3-edge input-sync latency, rising/falling edge capture, level tracking, edge stickiness + clear, set-beats-same-cycle-clear, clear-no-effect-on-level, `pstrb` partial-word clear, `GPIO_IRQ_EN` masking the output only, `irq_o` held 50 cycles, `GPIO_IRQ_CLR` reads-as-0, out-of-range access). `soc_all` **217/217** across 27 suites, up from 201. Extending the APB window broke `test_axil_interconnect.test_decerr_unmapped`, which probed `0x2000_A000` expecting DECERR — now the GPIO slot; `BAD_HIGH` bumped to `0x2000_B000`, the maintenance step that test's own comment prescribes for each window growth.
- **Hardened 2026-09-26** (`RUN_2026-09-26_00-07-59`, bead `00ef`): **Netgen LVS PASSED** ("Circuits match uniquely", 0 errors), routing DRC 0, **setup AND hold both clean at all 9 corners** (+7.08 ns / +0.1413 ns), 48.25 mW, 38.98 % util, die unchanged 6700 × 3100 µm. Magic DRC 9,081 is the only remaining deferred error (bead `45a` waiver). First Sky130 SoC hardening since 2026-07-30 — ⚠️ NOT single-variable vs. that baseline (33 RTL commits between, 13 touching `soc_top.sv`). **The ss setup failure that bead `ujv` was deferred on is gone** on current RTL. KLayout DRC deliberately skipped (8.5 GB OOM on this 15 GB host, and it sits before LVS in the flow) — deferred, not waived. Hold went **71 → 3 → 0**: resizer hold margins 0.05 → 0.3 closed 68, and `set_false_path -from [get_ports gpio_in_i]` closed the 3 survivors (all one path, `gpio_in_i[31]` → a `cdc_2ff_sync` stage-1 flop). Detail: `docs/SKY130_REAL_DRC_LVS_EVALUATION.md`.

**Sky130 PD quality campaign, 2026-09-26** — four runs after the GPIO harden, each single-variable:

| Bead | Change | Result | Cost |
| :--- | :----- | :----- | :--- |
| `00ef` | `set_false_path` on `gpio_in_i` + `cpu_rst_n_i` | hold 3 → **0** at all 9 corners | — |
| `e45j` | design-repair margins 10→30 / 20→40 % | max-slew 8623 → **2380**, cap 346 → **70** | antenna 191 → 263 pins |
| `58q` | `GRT_ANTENNA_ITERS` 8→20, `MARGIN` 25→50 | antenna 263 → **182** pins, 182 → **114** nets | max-slew 2380 → 3199 |

⚠️ **The slew and antenna knobs pull against each other** — repair buffers cut slew and raise antenna;
antenna diodes cut antenna and raise slew, each diode being another load pin. Both current points are
**single-axis optima**; the Pareto frontier is demonstrated but has never been swept jointly.

Two structural findings from that campaign, both recorded rather than fixed:

- **No post-RCX repair stage exists in LibreLane.** Every repair/resizer step is pre-route on
  GRT-*estimated* parasitics, so real-parasitic erosion appears first at post-route STA and last at a
  point where nothing can act on it (slew/cap 0 at steps 33/40/41 → thousands at step 51). The same gap
  explains the hold regression. Adding a stage needs a shared-LibreLane edit — evaluated, and
  recommended *not yet*, in [`docs/LIBRELANE_PATCHING_EVALUATION.md`](LIBRELANE_PATCHING_EVALUATION.md).
- **`max fanout violations = 0` is vacuous** — `sky130_soc.sdc` has no `set_max_fanout` at all, so a
  211-fanout net reports clean. Do not cite that metric until a real constraint exists.

**LibreLane install state captured 2026-09-26** (`pnr/librelane_patches/`). The shared install carried
15 modified files (+641/−89) as *uncommitted* edits, and the pre-existing patch archive lived under the
**gitignored** `memory/` — so no PD figure in this repo was reproducible from a clean checkout, and the
exact tool state behind every number existed on one disk, unbacked-up. Now tracked, with sha256s and a
verified (`git apply --check --reverse`) full diff. ⚠️ One patch in that set, `drt.tcl`'s
catch-and-continue around `detailed_route`, is why every ASAP7 "0 DRC / 0 antenna" claim was withdrawn
(bead `xy6`); re-examining it is the next step.

**Bead `ujv` re-examined 2026-09-26 — its ss setup failure NO LONGER REPRODUCES.** At an unchanged
25.0 ns period, max_ss went **−4.328 ns FAIL → +8.097 ns PASS** (nom_ss −2.885 → +9.232, min_ss −1.120
→ +10.069), a +12.4 ns swing. Its parking condition ("do not chase ss until hold is green at all 9
corners") is also now satisfied. ⚠️ But the **root cause is bypassed, not fixed**: `ujv` blamed the CPU
macro's 8.155 ns ss clk→Q, and `u_cpu` now appears **zero times** in max_ss's 1000 worst paths while the
macro views are unchanged since 2026-07-27 — so that weakness is latent and would resurface at a shorter
period. **Opportunity:** +8.1 ns of ss margin now exists where −4.3 ns did, so real frequency headroom
above 40 MHz is likely and has never been swept. The ROADMAP's 75 MHz Sky130 figure for GPIO remains a projection. Sky130 SoC headroom at the last sign-off was 37.9 % utilisation on a 6700 × 3100 µm die, with the tightest margin max_tt setup +0.339 ns.

**Pre-Phase-6 #5: behavioral PMU (GH epic #98)** - ✅ COMPLETE (2026-08-01). New `rtl/soc/pmu.sv` — APB4 slave (reusing `apb4_register_bank`) + a per-domain sequencer FSM encoding the 4 PST states from `pnr/constraints/phase5_soc.upf` (NORMAL/CPU_OFF/GPU_OFF/IDLE).

- **Sequencing order is fixed by the UPF, not chosen**: power-down `ret_save → iso_en → gate clock → assert reset`; power-up `release reset → ungate clock → ret_restore → de-assert iso_en`. Each domain walks an explicit 9-state chain, one action per cycle, so the order is structurally guaranteed and directly assertable.
- **Integration** (#100): no free APB slot existed — every 4 KB slot from `0x2000_2000` to `0x2000_7FFF` was taken — so `PERIPH_LIMIT` and `AXIL_APB_LIMIT` were both extended to `0x2000_8FFF`, with PMU at `0x2000_8000–8FFF` as APB slave 5. Two `rv32i_clock_gate` cells now gate `core_clk` into `u_cpu`/`u_gpu` — the first SoC-level clock gates. Isolation clamps sit in `soc_top` outside the gated domains, per the UPF's `-location parent`.
- **Scope limit**: this is a *sequencing* controller. Retention save/restore are emitted in the correct order for verification to assert but are a functional no-op — `phase5_soc.upf:23` declares no retention registers in Phase 5. No real supply removal, power switches, or retention silicon; `pg_ctrl` is deliberately not emitted.
- **Verification** (#101): `soc_all` **120/120** (was 82/82), `test_pmu` 10/10 with per-cycle ordering assertions in both directions. Reset defaults leave both domains on/un-isolated/un-reset, so the SoC is functionally identical to pre-PMU for firmware that never writes CTRL.

**Pre-Phase-6 #4: 2-domain multi-clock SoC + CDC (GH epic #90)** - ✅ COMPLETE (2026-08-09). The SoC is split into a CPU domain and a GPU+bus+peripheral domain, giving exactly **one** CDC boundary (CPU ↔ crossbar M0).

- **PD result** (#96, run 23 `RUN_2026-08-09_14-36-16`): `cpu_clk` 780 ps at **+9.8 ps** WS, TNS 0, 0 violators → **1282 MHz MET**; `sys_clk` 1750 ps at **+74.8 ps** WS, TNS 0, 0 violators → **571 MHz MET**. 0 routing DRC, 0 antenna, 0 slew/cap, 51.9 mW, 66.9 % util, die unchanged 520 × 520 µm, post-route CDC budget check PASS. **The CPU runs at 2.24× the fabric clock and is no longer de-rated onto the 1750 ps cycle** — the point of the epic. Run 14 remains the accepted single-clock M11 sign-off and is byte-reproducible; the multi-clock flow runs off `pnr/asap7/soc/config_multiclock.json` + `constraints/phase5_soc_multiclock.sdc`.
- **RTL** (#91/#92/#93): `rtl/soc/async_axi_fifo.sv` (dual-clock AXI4 bridge on new `rtl/soc/cdc/` primitives), a second `pll_subsystem` + `APB_PLL2` slot, and `rtl/soc/apb_cdc_bridge.sv`. `soc_all` 159/159; `soc_multiclock` 4/4 at a **7 ns / 3 ns coprime ratio** — the first real CDC coverage in this repo, and it found two RTL bugs invisible to every 1:1 suite (both a *reset value that advertises availability*).
- **Two PD root causes, both now fixed and documented**: the CPU macro Liberty exported ~600–800 ps combinational in→out arcs on its APB outputs (fixed by making all three outputs pure registered), and the macro's boundary pins free-floated between regenerations — **393 of 401 moved**, worth 535 ps of setup — fixed by `pnr/asap7/cpu/pin_order.cfg` (`pnr/asap7/cpu/README_pin_order.md`).
- ⚠️ **Do not quote 62.9 → 51.9 mW as a multi-clock power win.** `report_power` attributes 0.00 W to the macros, and the drop coincides with the first-ever ICG insertion (`USE_ICG_CELL`). ASAP7 IR drop remains unobtainable — `analyze_power_grid` fails `PSM-0069` on both rails from the M1-only tap-cell connectivity artifact. Both tracked as beads.
- ⚠️ **The run-23 timing figures above (both domains MET) are also unvalidated** (bead `8f3`/`0p6`): produced by the stock, non-re-routing `OpenROAD.STAMidPNR-3` step, proven elsewhere to report false-clean zero-wire STA. Run 23's artifacts are wiped; not re-verifiable directly. ✅ The honest *current-RTL* point (2026-09-18, bead `0d0`) is setup WNS −727.37 ps / 781 violators / hold clean / 283.6 mW at `RUN_2026-09-17_20-41-11` — a different, still-unclosed design point, not a re-run of run 23. See `docs/PHASE5_RUN_HISTORY.md` §"Power figure caveat".
- Full record: [`docs/PHASE5_RUN_HISTORY.md`](PHASE5_RUN_HISTORY.md) and [`docs/3PLL_CDC_EVALUATION.md`](3PLL_CDC_EVALUATION.md).

**Sky130 real DRC/LVS sign-off (GH epic #102)** — Stages 1–2 ✅ complete (2026-07-31); Stages 3–4 ⏸️ host-gated.
- **Stage 1** (CPU standalone, GH #103): KLayout DRC 0, Netgen LVS MATCH, setup +0.366 ns @ 75 MHz. Magic DRC 27.7 M waived — 100 % inside SRAM macro footprints, PDK artifact (bead `45a`).
- **Stage 2** (CPU macro + peripherals SoC, no GPU, GH #104): LVS PASSED, routing DRC 0, PDN 0, hold clean, 40 MHz, nom_tt 37.63 mW, 226,952 stdcells, die 6700 × 3100 µm. Setup fails at ss (bead `ujv`) and antenna leaves a 140/120 residual (bead `58q`) — both documented, deferred.
- ⚠️ **Timing scope: typical-corner (nom_tt) only.** The SRAM macro is characterized at TT alone, so the nine reported corners are nine labels backed by one macro model. The physical gates (LVS/DRC/PDN) are not affected and stand as real results. Closing ss honestly needs per-corner SRAM SPICE characterization, measured at ~80–95 h on a host that reboots every 2–8 h → bead `o1i`, deferred host-blocked.
- **Stages 3–4** (GPU standalone + full SoC incl. GPU, GH #105/#106): not attempted; need ≥32 GB RAM + ~500 GB scratch. GPU stays ASAP7-indicative-only.
- Full record: [`docs/SKY130_REAL_DRC_LVS_EVALUATION.md`](SKY130_REAL_DRC_LVS_EVALUATION.md) §7.

**Previous Phases**:
- Phase 4 (GPU-Lite SIMT Compute Engine) - ✅ COMPLETE (2026-05-27) — all GPU tests green, ASAP7 ≥500 MHz sign-off
- Phase 3 (Memory System & Caches) - ✅ COMPLETE (2026-05-21) — all 20 cache tests passing, 139/139 total
- Phase 2 (Pipelined CPU) - ✅ COMPLETE (2026-03-08) — 75 MHz on Sky130 130nm
- Phase 1 (Minimal RV32I Core) - ✅ COMPLETE (2026-02-13)
- Phase 0 (Foundations) - ✅ COMPLETE (2026-01-18)

## Phase Progress

### Phase 0: Foundations ✅

**Status**: Specifications and implementation complete

**Completed**:

- ✅ RV32I subset defined (PHASE0_ARCHITECTURE_SPEC.md)
- ✅ Reset behavior specified
- ✅ Trap behavior specified
- ✅ Memory ordering rules specified
- ✅ Commit semantics specified
- ✅ Project structure created (rtl/, tb/, sim/, docs/)
- ✅ Interface specifications (RTL_DEFINITION.md) - AXI4-Lite & APB3 protocols defined
- ✅ GPU architecture specification (PHASE4_GPU_ARCHITECTURE_SPEC.md) - complete
- ✅ Reference model specification (REFERENCE_MODEL_SPEC.md) - complete
- ✅ Memory map specification (MEMORY_MAP.md) - complete with 4 KB alignment
- ✅ Phase-aligned verification plan (VERIFICATION_PLAN.md) - structured by phases
- ✅ Phase 1 CPU specification (PHASE1_ARCHITECTURE_SPEC.md) - complete
- ✅ Python reference model implementation - 66/66 tests passing (memory, RV32I, GPU)
- ✅ cocotb test infrastructure setup - complete with BFMs, scoreboard, utilities, documentation

**Remaining**:

- None - Phase 0 complete!

**Exit Criteria Status**:

- ✅ Written ISA + microarchitecture spec (PHASE0_ARCHITECTURE_SPEC.md exists)
- ✅ No RTL yet (confirmed - directories empty)
- ✅ Supporting specifications complete (all 7 specs finalized)
- ✅ Python reference model matches specification (66/66 tests passing)
- ✅ Test infrastructure ready (cocotb infrastructure complete)
- ✅ Final human specification review complete (approved 2026-01-18)

**Target Completion**: 2026-01-31

### Phase 1: Minimal RV32I Core ✅ VERIFICATION COMPLETE

**Status**: RTL implementation complete, all 9/9 verification exit criteria met (2026-02-13)

**Prerequisites**: ✅ Phase 0 exit criteria met

**RTL Modules** (8/8 complete, ~1,900 lines total):

| Module | File | Status |
|--------|------|--------|
| CPU top-level (AXI4-Lite + APB3) | `rtl/cpu/rv32i_cpu_top.sv` | ✅ Complete |
| CPU core wrapper | `rtl/cpu/core/rv32i_core.sv` | ✅ Complete |
| Control FSM | `rtl/cpu/core/rv32i_control.sv` | ✅ Complete |
| Instruction decoder | `rtl/cpu/core/rv32i_decode.sv` | ✅ Complete |
| ALU | `rtl/cpu/core/rv32i_alu.sv` | ✅ Complete |
| Register file | `rtl/cpu/core/rv32i_regfile.sv` | ✅ Complete |
| Immediate generator | `rtl/cpu/core/rv32i_imm_gen.sv` | ✅ Complete |
| Branch comparator | `rtl/cpu/core/rv32i_branch_comp.sv` | ✅ Complete |

**Verification Exit Criteria** (9/9 met):

| # | Criterion | Target | Status |
|---|-----------|--------|--------|
| 1 | Smoke tests passing | 6/6 | ✅ MET — 6/6 with scoreboard |
| 2 | Scoreboard mismatches | 0 | ✅ MET — 0 mismatches |
| 3 | Instruction coverage | 37/37 (100%) | ✅ MET — all 37 RV32I instructions |
| 4 | Random instruction tests | 10,000+, 0 fail | ✅ MET — 10,000 instructions, 0 failures |
| 5 | AXI protocol tests | 100% pass | ✅ MET — 11/11 tests passing |
| 6 | Debug interface tests | 100% pass | ✅ MET — 6/6 tests (single-step, BP0, BP1, GPR/PC write) |
| 7 | Code coverage | >95% | ✅ MET — Verilator annotated reports, `make coverage` |
| 8 | State coverage | 8/8 (100%) | ✅ MET — 8/8 FSM states covered |
| 9 | Failing random seeds | 0 | ✅ MET — 0 failing seeds (100/100 pass) |

**Key RTL Fixes Applied**:
- Branch/jump timing fix (registered decision flag in rv32i_control.sv)
- Load data latching fix (mem_rdata_raw register in rv32i_core.sv)
- Register file combinational reads (rv32i_regfile.sv)

**Verification Milestones**:
- 2026-01-24: Task 1 complete — Scoreboard integration (6/6 smoke tests)
- 2026-01-26: Task 2 complete — ISA compliance tests (37/37 passing)
- 2026-01-28: Task 3 complete — Random instruction generator (10,000 instructions, 0 failures)
- 2026-02-07: Task 4 complete — AXI4-Lite protocol tests (11/11 implemented)
- 2026-02-13: Tasks 5, 6, 7 complete — Debug interface (6/6), Coverage (100%), Docs

### Phase 2: Pipelined CPU ✅ COMPLETE

**Status**: ✅ COMPLETE (2026-03-08) — 75 MHz achieved on Sky130 130nm

**Prerequisites**: ✅ Phase 1 exit criteria met (2026-02-13)

**Architecture Spec**: `docs/design/PHASE2_ARCHITECTURE_SPEC.md` — APPROVED (2026-02-14), all 7 open questions resolved

**RTL Modules** (14/14 complete):

| Module | File | Status |
|--------|------|--------|
| CPU top-level (AXI4-Lite + APB3) | `rtl/cpu/rv32i_cpu_top.sv` | ✅ Complete |
| CPU core wrapper | `rtl/cpu/core/rv32i_core.sv` | ✅ Complete |
| IF pipeline stage | `rtl/cpu/core/pipeline/rv32i_pipeline_if.sv` | ✅ Complete |
| ID pipeline stage | `rtl/cpu/core/pipeline/rv32i_pipeline_id.sv` | ✅ Complete |
| EX pipeline stage | `rtl/cpu/core/pipeline/rv32i_pipeline_ex.sv` | ✅ Complete |
| MEM pipeline stage | `rtl/cpu/core/pipeline/rv32i_pipeline_mem.sv` | ✅ Complete |
| WB pipeline stage | `rtl/cpu/core/pipeline/rv32i_pipeline_wb.sv` | ✅ Complete |
| Pipeline package | `rtl/cpu/core/rv32i_pipeline_pkg.sv` | ✅ Complete |
| Hazard unit | `rtl/cpu/core/rv32i_hazard_unit.sv` | ✅ Complete |
| Forwarding unit | `rtl/cpu/core/rv32i_forwarding_unit.sv` | ✅ Complete |
| CSR file | `rtl/cpu/core/rv32i_csr_file.sv` | ✅ Complete |
| Interrupt controller | `rtl/cpu/core/rv32i_interrupt_ctrl.sv` | ✅ Complete |
| AXI arbiter | `rtl/cpu/rv32i_axi_arbiter.sv` | ✅ Complete |
| Decode (updated for CSR) | `rtl/cpu/core/rv32i_decode.sv` | ✅ Complete |

**Reused Phase 1 Modules** (4/4):
- ALU (`rv32i_alu.sv`)
- Register file (`rv32i_regfile.sv`)
- Immediate generator (`rv32i_imm_gen.sv`)
- Branch comparator (`rv32i_branch_comp.sv`)

**Architecture Decisions Implemented (2026-02-14)**:
- OQ-1: ✅ Modified in-place (Phase 1 archived to `micro_p/`)
- OQ-2: ✅ External interrupt (MEIP) > Timer interrupt (MTIP)
- OQ-3: ✅ EBREAK sets `mcause=3` + `mepc` + triggers debug halt
- OQ-4: ✅ CSR write takes priority over same-cycle interrupt check in EX
- OQ-5: ✅ Debug halt drains pipeline immediately (no wait for MRET)
- OQ-6: ✅ In-flight AXI transaction completes; flushed responses discarded
- OQ-7: ✅ Add pipeline stage first → ASAP7 second → relax frequency last resort

**Verification Progress** (2026-02-27):
- ✅ RTL implementation complete (2026-02-16)
- ✅ Initial testing complete (115/115 regression tests passing)
- ✅ Comprehensive verification complete (111/111 tests, all 7 suites pass):
  - smoke_uvm: 4/4 PASS
  - isa_uvm: 54/54 PASS (37/37 RV32I instructions + CSR)
  - pipeline_hazards: 16/16 PASS (RAW/control hazards, forwarding, store-store, JAL rd)
  - interrupts: 12/12 PASS (timer/ext IRQ, MIE gating, MRET, CSR insns, latency ≤3 cyc)
  - debug: 6/6 PASS (single-step, BP0/BP1, GPR write, PC write, reg reads)
  - axi_protocol: 12/12 PASS (back-pressure, error injection, arbiter)
  - fault_injection: 7/7 PASS (misaligned, illegal, AXI fetch error)
- ✅ Random regression: 500 seeds × 100 instructions = **50,000 instructions, 0 failures**
- ✅ Backend flow: **75 MHz achieved on Sky130 130nm** (200 MHz target not met due to PDK limitations)
  - SDC constraints: `pnr/constraints/phase2_cpu.sdc`
  - UPF power intent: `pnr/constraints/phase2_cpu.upf`
- ✅ ASAP7 backend flow: **1418 MHz achieved at Run 43 (2026-05-20)** — 27.27 mW, 3 844 µm² stdcell, 0 DRC/antenna/timing violations ⚠️ unvalidated, STA-zero-wire (bead `8f3`/`0p6`); artifacts wiped, not re-checkable — `docs/ASAP7_RUN_HISTORY.md`
  - Run directory: `pnr/asap7/runs/RUN_2026-05-20_06-27-10/`
  - Config: `pnr/asap7/config.json` (CLOCK_PERIOD 0.705, CTS clustering 8/10)
  - Constraints: `pnr/asap7/constraints/asap7.sdc`
  - Full per-run history: `docs/ASAP7_RUN_HISTORY.md`

### Phase 3: Memory System & Caches ✅ COMPLETE

**Status**: ✅ COMPLETE (2026-05-21) — all 20 Phase 3 tests passing, 139/139 total tests clean

**Prerequisites**: ✅ Phase 2 exit criteria met (2026-03-08)

**Architecture Spec**: `docs/design/PHASE3_ARCHITECTURE_SPEC.md` — APPROVED (2026-03-08), all 6 open questions resolved

**RTL Modules** (10/10 complete):

| Module | File | Status |
|--------|------|--------|
| Cache package | `rtl/mem/rv32i_cache_pkg.sv` | ✅ Complete |
| I-Cache | `rtl/mem/rv32i_icache.sv` | ✅ Complete |
| D-Cache | `rtl/mem/rv32i_dcache.sv` | ✅ Complete |
| Cache arbiter | `rtl/mem/rv32i_cache_arbiter.sv` | ✅ Complete |
| IF stage (cache IF) | `rtl/cpu/core/pipeline/rv32i_pipeline_if.sv` | ✅ Complete |
| MEM stage (cache IF + FENCE.I) | `rtl/cpu/core/pipeline/rv32i_pipeline_mem.sv` | ✅ Complete |
| Hazard unit (renamed stalls) | `rtl/cpu/core/rv32i_hazard_unit.sv` | ✅ Complete |
| Core (cache integration) | `rtl/cpu/core/rv32i_core.sv` | ✅ Complete |
| Pipeline package (fence_i field) | `rtl/cpu/core/rv32i_pipeline_pkg.sv` | ✅ Complete |
| Decoder (FENCE.I) | `rtl/cpu/core/rv32i_decode.sv` | ✅ Complete |

**Architecture Decisions Implemented (2026-03-08)**:
- OQ-1: ✅ Direct-mapped (1-way) associativity
- OQ-2: ✅ 16-byte cache line (4 words, 4 AXI transactions per refill)
- OQ-3: ✅ Write-back + write-allocate for D-cache
- OQ-4: ✅ No AXI burst — 4 separate AXI4-Lite transactions per refill
- OQ-5: ✅ 75 MHz target on Sky130 (matches Phase 2 achieved frequency)
- OQ-6: ✅ Blocking cache (stall pipeline on every miss)

**Bug Fixes Landed (2026-05-21)**:
- ✅ PDN `pdn_asap7.tcl` — GND nets removed from `-secondary_power` (API bug #35)
- ✅ I-cache AXI cancel race — `cancel_ar_q` + `cancel_wait_r_q` flags added (bug #36): three
  timing races fixed: R-same-cycle-as-cancel, AR-accepted-same-cycle-as-cancel, AXI A3.2.1
  arvalid-no-retract compliance
- ✅ D-cache CS_REFILL — audit comment added confirming no equivalent cancel race

**Verification Results** (2026-05-21):

| Suite | Tests | Result |
|-------|-------|--------|
| I-Cache unit tests (`make icache`) | 7/7 | ✅ PASS |
| D-Cache unit tests (`make dcache`) | 8/8 | ✅ PASS |
| Cache integration (`make cache_integration`) | 5/5 | ✅ PASS |
| Phase 2 full regression (`make test`) | 119/119 | ✅ PASS |
| **Total** | **139/139** | **✅ ALL PASS** |

**Achieved frequency**: 75 MHz on Sky130 130nm (ASAP7 runs 1–43 logged in `docs/CPU_ASAP7_RUN_HISTORY.md`)

### Phase 4: GPU-Lite Compute Engine ✅ COMPLETE

**Status**: ✅ COMPLETE (2026-05-27) — all GPU tests green, 1,000-kernel random regression pass, ASAP7 PD sign-off

**Prerequisites**: ✅ Phase 3 exit criteria met (2026-05-21)

**RTL Modules** (9/9 complete):

| Module | File | Status |
|--------|------|--------|
| GPU top | `rtl/gpu/gpu_top.sv` | ✅ Complete |
| Command queue | `rtl/gpu/gpu_command_queue.sv` | ✅ Complete |
| Warp scheduler | `rtl/gpu/warp_scheduler.sv` | ✅ Complete |
| Compute unit | `rtl/gpu/gpu_compute_unit.sv` | ✅ Complete |
| Vector register file | `rtl/gpu/vector_register_file.sv` | ✅ Complete |
| Vector ALU | `rtl/gpu/vector_alu.sv` | ✅ Complete |
| Memory unit | `rtl/gpu/gpu_memory_unit.sv` | ✅ Complete |
| Memory coalescer | `rtl/gpu/memory_coalescer.sv` | ✅ Complete |
| Shared memory | `rtl/gpu/shared_memory.sv` | ✅ Complete |

**Verification Results** (2026-05-23):

| Suite | Tests | Result |
|-------|-------|--------|
| GPU unit tests (`make gpu_unit`) | all | ✅ PASS |
| GPU kernel tests (`make gpu_kernels`) | all | ✅ PASS |
| CPU-GPU handoff (`test_cpu_gpu_handoff.py`) | 1/1 | ✅ PASS |
| CPU re-gate (`make test` + `make random_uvm`) | 140/140 + 100k instr | ✅ PASS |
| GPU random regression (`make gpu_random`) | 1,000 kernels | ✅ PASS |

**Physical Design** (2026-05-28):
- ✅ ASAP7 sign-off: **571 MHz (1.75 ns) / 262 mW / 115,600 µm² die / 60,500 µm² stdcell / 70% util** ⚠️ unvalidated, STA-zero-wire (bead `8f3`/`0p6`); GPU run artifacts wiped, re-validation deferred (host cost estimate: several hours / 9–14+ GiB) — `docs/GPU_ASAP7_RUN_HISTORY.md`
- ✅ Setup WS +197.3 ps (0 violations), Hold WS +16.3 ps (0 violations), slew/cap/fanout 0, antenna 0
- ✅ Run: `pnr/asap7/gpu/runs/RUN_2026-05-28_06-29-48/` (supersedes 500 MHz `RUN_2026-05-27_11-16-37`)
- ✅ Constraints: `pnr/asap7/gpu/constraints/asap7_gpu.sdc`; full history: `docs/GPU_ASAP7_RUN_HISTORY.md`

**Phase 4 sign-off frequency is 571 MHz** — the `CLOCK_PERIOD` 2.0→1.75 ns stretch push closed clean (`RUN_2026-05-28_06-29-48`), upgrading the GPU signoff from the prior 500 MHz `RUN_2026-05-27_11-16-37` (now superseded). Hold is clean at +16.3 ps / 0 viol at the final stage; the prior 500 MHz run's `final/metrics.json` showed hold −212 ps / 368 viol.

**Signoff caveats** (deferred to Phase-5 SoC PD, same as the prior run): PDN connectivity not closed (`PSM-0069` / `PDN-0179`, 9.56 M grid viol — identical to the 500 MHz run); 325 `DRT-0074` on top-level I/O ports only (0 internal-net DRC); timing is post-GRT estimated (`STAPostPNR` + `RCX` gated off — same methodology as prior run). A confirmation re-run with post-PnR STA + RCX enabled is recommended before locking the number.

**Step-37 runtime note**: `repair_design_postgrt` is the bottleneck (~18.9 h single-threaded — runs GRT twice + a multi-thousand-iteration repair loop on ~485 K instances). Mitigation: `DRT_THREADS` 4→12 (`pnr/asap7/gpu/config.json`).

**Macro views**: signoff DB exported for Phase-5 SoC via `make macro-views-asap7 BLOCK=gpu` → `pnr/asap7/gpu/macro/{gpu_top.lef, *.lib, gpu_top.nl.v.gz}` (netlist gzipped to clear GitHub's 100 MB limit; `gunzip -k` to restore).

### Phase 5: SoC Integration ✅

**Status**: COMPLETE (2026-06-24) — M1–M12 done. M11 ASAP7 SoC P&R signed off 571 MHz / 62.9 mW / 520×520 µm / 65.6 % util / 0 DRC / 0 antenna ⚠️ timing/power unvalidated post-bead-`8f3` (see top of this file) (`docs/PHASE5_RUN_HISTORY.md`). Milestone detail in `docs/PHASE5_SOC_INTEGRATION_PLAN.md` (golden spec)

| Milestone | Scope | Status |
| :-------- | :---- | :----- |
| M1 | AXI4/AXI-Lite shared package | ✅ 2026-05-31 (lint-clean) |
| M2 | Cache refill FSMs → AXI4 burst | ✅ 2026-05-31 (146/146 tests) |
| M3 | AXI4 crossbar + AXI-Lite interconnect | ✅ 2026-05-31 (16/16 tests) |
| M4 | UART / SPI / timer / IRQ controller | ✅ 2026-06-01 |
| M5 | DMA engine | ✅ 2026-06-01 (6/6 tests) |
| M6 | Behavioral SRAM controller | ✅ 2026-06-01 (7/7 tests) |
| M7 | Performance counters (CSR + AXI-Lite GPU stats) | ✅ 2026-06-02 (CPU re-sign-off 1282 MHz) |
| M8 | SoC top integration (`rtl/soc/soc_top.sv`) | ✅ 2026-06-02 (lint-clean) |
| M9 | SoC verification — foundation slice (boot 100/100) | ✅ 2026-06-03 (PR #65) |
| M9 | Fast-follows: CPU→GPU kernel launch, SW coherency, DMA/peripheral loopback, SRAM readback, 1M-cycle random, benchmarks | ✅ 2026-06-24 (1,079,867 cyc, 0 fail) |
| M10 | L2 cache decision gate (needs M9 benchmarks) | ✅ 2026-06-21 — **NO-GO** (`docs/M10_L2_DECISION_ANALYSIS.md`) |
| M11 | SoC P&R + STA (`phase5_soc.sdc`/`.upf`) | ✅ 2026-06-24 ⚠️ figures unvalidated, bead `0p6` |
| M12 | Sign-off + documentation | ✅ 2026-06-24 |

### Phase 6: IP Expansion 🚧

**Golden spec**: `docs/PHASE6_IP_EXPANSION_PLAN.md` (added 2026-09-28, bead `f7vs.1`).
**Tracking**: bead epic `claude_verilog_test-f7vs`.
**Definition of done, per item**: RTL + cocotb verification + SoC integration. Physical design is
a separately batched gate (Gate A synthesis probe per item; Gate B one Sky130 harden), not
per-item.

| Item | Scope | APB idx / IRQ bit | Bead | Status |
| :--- | :---- | :---------------- | :--- | :----- |
| 6a-1 | GPIO controller, 32 pins | 7 / 5 | `ckc`, `00ef` | ✅ 2026-09-26 (Sky130-hardened; LVS PASS, DRC 0, setup+hold clean 9/9) |
| G1 | Golden spec + ROADMAP bus/numbering corrections | — | `f7vs.1` | ✅ 2026-09-28 |
| G2 | APB window + IRQ source pre-allocation | — | `f7vs.2` | ✅ 2026-09-28 (PR #197) |
| G3 | `tb_soc_top.sv` ports + SDC exceptions, one forced clean | — | `f7vs.3` | ✅ 2026-09-28 (PR #197) |
| G4 | File-list checker + first `apb_interconnect` unit suite | — | `f7vs.4` | ✅ 2026-09-28 (PR #197) |
| G5 | This section + de-staled Next Actions | — | `f7vs.5` | ✅ 2026-09-28 (PR #197) |
| 6a-2 | PWM controller, 4 channels | 8 / 6 | `f7vs.6` | ✅ 2026-09-28 (RTL + 16/16 L1 + soc_pwm L2; `soc_all_ci` 279) |
| 6a-3 | Watchdog timer | 9 / 7 | `f7vs.7` | ✅ 2026-09-29 (RTL + 22/22 L1 + soc_wdt L2 incl. RST_EN reset path; `soc_all_ci` 303) |
| 6a-4 | TRNG (portable LFSR entropy; RO source Sky130-only) | 10 / 8 | `f7vs.8` | ✅ 2026-10-01 (RTL bit-exact vs Python model + 22/22 L1 + soc_trng L2; `soc_all_ci` 326) |
| 6a-5 | I2C master controller | 11 / 9 | `f7vs.9` | ✅ 2026-10-03 (RTL + bit engine + `i2c_slave` BFM + 46/46 L1 + soc_i2c L2; PR #208; `soc_all_ci` 394) |
| 6b | CRYPTO — AES-128 (ECB+CTR) + SHA-256 | 12 / 10 | `f7vs.10` | ✅ 2026-10-03 (RTL 3 files + 41/41 L1 + soc_crypto L2 + **Gate A run**: 277 875 µm² ≈ 28 % of SoC stdcell area — first recorded as 3.59 % against a stdcell+macro denominator, corrected 2026-10-04 — +14.04 ns ss @ 25 ns) |
| 6c | INT8 NPU, 4×4 systolic, 4 KB weight SRAM | 13 / 11 | `f7vs.11` | ⏸️ Not started |

Three documentation defects were corrected when the golden spec landed: AES/SHA is **APB4**, not
AXI4-Lite (`ROADMAP.md:431` was a survivor of the pre-2026-09-20 text); the AES throughput figures
describe a **deferred AXI4-master version**, not what 6b lands; and the TRNG **RTL is portable** —
only its ring-oscillator entropy source is Sky130-exclusive.

⚠️ **ASAP7 is out of scope for all of Phase 6**, triple-blocked on beads `ma7` (proven Synlig
`OPT_MUXTREE` miscompile in the CPU/GPU macro netlists), `lxv` (routing-congestion regression) and
`2kn` (needs a ≥32 GB host; this one has ~15 GB). Every peripheral still goes into the ASAP7 sv2v
file list, enforced by `tools/verif/check_periph_filelists.py`, so unblocking is a re-run rather
than a porting exercise.

### Phase 7: Mixed-Signal PLL Clock Generator 🚧

**Status**: M-a/M-b1/M-b2/M-c ✅ complete (2026-06-20); M-d = documentation (this update). Golden spec: `docs/PHASE7_MIXED_SIGNAL_PLL_PLAN.md`.

Dual-PDK charge-pump integer-N PLL (ring VCO) designed end-to-end via the analog-design orchestrator agents, integrated into the SoC as the clock source via a PDK-agnostic real-number model (RNM). Doubled as a validation run of the analog-design agent suite (real ngspice/magic/netgen ran; closed-loop meta fix loop + adversarial physical verification both added value — the latter caught a false DRC pass).

| Milestone | Scope | Status |
| :-------- | :---- | :----- |
| M-a | Analog infra (`analog` devshell) + dual-PDK PLL architecture + modeling | ✅ |
| M-b1 | ASAP7 variant: circuit + ngspice — 100 MHz→1.282 GHz, N=13, 0.7 V | ✅ (electrical **indicative**: BSIM4 substitute, no BSIM-CMG) |
| M-b2 | Sky130 variant: real `sky130_fd_pr` circuit/sim + magic layout — 10→100 MHz, N=10, 1.8 V; **CP-block DRC=0 + netgen LVS MATCH** | ✅ (CP block; VCO/LF/BIAS regen ⏸️) |
| M-c | SoC integration (`rtl/soc/pll/`): clock seam, AXI-Lite slave @0x2000_7000 (`AXIL_N_SLAVES` 6→7), 2 RTL bugs fixed, cosim 7/7 + regression | ✅ |
| M-d | Phase 7 documentation (plan/roadmap/status/CLAUDE.md) | ✅ 2026-06-20 |

**Real vs indicative**: Sky130 CP block carries **real** DRC+LVS sign-off; ASAP7 electrical is **indicative** (no BSIM-CMG FinFET models in open ngspice). **Follow-ups**: Sky130 full-chip DRC/LVS (mechanical VCO/LF/BIAS PDK-generator regen) and the RNM-mode AXI CDC synchroniser. Two RTL bugs found+fixed: PLL bootstrap deadlock (regs were on the gated core domain → moved to ref `clk_i`, default-enable `CONTROL[0]`) and `PERIPH_LIMIT` decode hole (0x2000_6FFF → 0x2000_7FFF).

## Recent Project Changes

### 2026-06-20: Phase 7 Mixed-Signal PLL — M-a..M-c complete, M-d docs

- ✅ Dual-PDK charge-pump integer-N PLL (ring VCO) designed end-to-end via the analog-design orchestrator agents.
- ✅ ASAP7 variant (indicative): 100 MHz→1.282 GHz, N=13, 0.7 V; electrical via calibrated planar BSIM4 substitute (no BSIM-CMG in open ngspice).
- ✅ Sky130 variant (real): 10→100 MHz, N=10, 1.8 V, real `sky130_fd_pr`; Kvco 530 MHz/V; CP UP/DN mismatch 4.78%→0.37% (independent bias legs); behavioral lock 100.000 MHz / 1.38 µs; real magic layout + **CP-block DRC=0 + netgen LVS MATCH** (4 pfet + 1 nfet extracted). Adversarial PV caught a false DRC pass (hand-drawn geometry 50× too small → 0 FETs).
- ✅ SoC integration (`rtl/soc/pll/`): clock seam (`clk_i`→PLL ref→`core_clk`, `core_rst_n = rst_n_i & pll_locked`), AXI-Lite slave @0x2000_7000 (`AXIL_N_SLAVES` 6→7). Cosim 7/7 (`test_pll_lock` 3/3 + `test_pll_regs` 4/4) + boot/periph regression clean.
- ✅ Two RTL bugs found+fixed: PLL bootstrap deadlock (regs on gated core domain → ref `clk_i` + default-enable `CONTROL[0]`); `PERIPH_LIMIT` 0x2000_6FFF→0x2000_7FFF.
- ⏸️ Follow-ups: Sky130 full-chip DRC/LVS (VCO/LF/BIAS PDK-generator regen) and RNM-mode AXI CDC synchroniser.

### 2026-05-21: Phase 3 COMPLETE ✅

**All exit criteria met — 139/139 tests passing**:

- ✅ 10/10 Phase 3 RTL modules implemented (cache_pkg, icache, dcache, cache_arbiter, 6 modified pipeline files)
- ✅ Bug fixes: PDN secondary_power API (#35), I-cache AXI cancel race with 3 sub-cases (#36)
- ✅ I-cache unit tests: 7/7 PASS (`make icache`) — hit, miss, conflict, FENCE.I, latency, boundary
- ✅ D-cache unit tests: 8/8 PASS (`make dcache`) — read/write hit/miss, dirty eviction, strobes, latency
- ✅ Cache integration tests: 5/5 PASS (`make cache_integration`) — locality, load-after-store, FENCE.I self-modifying code, conflict stress, warmup IPC
- ✅ Phase 2 full regression: 119/119 PASS (no regressions from Phase 3 RTL changes)
- ✅ Makefile fix: `PYTHON3=/usr/bin/python3` (system Python 3.10 matches `PYTHONHOME=/usr`; nix Python 3.11 was mismatched)
- ✅ Test timing fix: 4 tests updated to use `_fetch()`/`_read()`/`_write()` helpers (5-state SRAM pipeline takes 3 cycles for a hit from CS_DONE, not 1)
- **TOTAL: 139/139 tests (119 Phase 2 + 20 Phase 3), 0 failures**
- **Branch**: `bug-fix-35-36` → ready to merge to `main`

### 2026-03-08: Phase 3 RTL Implementation Started

**Phase 3 kicked off**:

- ✅ PHASE3_ARCHITECTURE_SPEC.md approved — all 6 open questions resolved
- ✅ Phase 2 marked complete — 75 MHz achieved on Sky130 130nm
- 🔄 Phase 3 RTL implementation in progress (cache package, I-cache, D-cache, arbiter)
- 🔄 Python cache reference model development started (`tb/models/cache_model.py`)

**Architecture highlights**:
- I-Cache: 4 KB direct-mapped, 16-byte lines, 256 sets; read-only; FENCE.I invalidation
- D-Cache: 4 KB direct-mapped, 16-byte lines, 256 sets; write-back + write-allocate
- External interface: 4 sequential AXI4-Lite transactions per refill (no burst)
- Cache arbiter: D-cache priority over I-cache (replaces Phase 2 AXI arbiter)
- Target frequency: 75 MHz on Sky130 130nm

### 2026-02-27: Phase 2 Comprehensive Verification COMPLETE

**All 7 test suites passing, 50,000 random instructions verified**:

- ✅ smoke_uvm: 4/4 PASS
- ✅ isa_uvm: 54/54 PASS — full RV32I ISA + Zicsr (CSR) instructions
- ✅ pipeline_hazards: 16/16 PASS — RAW/control hazards, EX/MEM/WB forwarding
- ✅ interrupts: 12/12 PASS — timer/ext IRQ delivery, MIE gating, MRET, IRQ latency ≤3 cycles
- ✅ debug: 6/6 PASS — single-step, breakpoints, GPR/PC write, register reads
- ✅ axi_protocol: 12/12 PASS — back-pressure, error injection, protocol compliance
- ✅ fault_injection: 7/7 PASS — misaligned access, illegal instruction, AXI fetch error
- ✅ Random regression: 500 seeds × 100 instructions = **50,000 instructions, 0 failures**
- **TOTAL: 111/111 Phase 2 tests passing**

**Infrastructure improvements**:
- Created `tb/cocotb/cpu/phase2_test_utils.py` — shared APBDebug + setup helpers
- Added Phase 2 Makefile targets (`pipeline_hazards`, `interrupts`, `axi_protocol`, `fault_injection`, `phase2_all`)
- Added 2 new pipeline hazard tests (`test_back_to_back_stores`, `test_jal_rd_dependency`)
- Fixed `test_csr_mstatus_mie_gate`: DBG_MSTATUS (APB 0x200) is READ-ONLY per RTL design

### 2026-02-16: Phase 2 RTL Implementation COMPLETE 🎉

**All 14 RTL modules implemented**:

- ✅ 5-stage pipeline modules (IF, ID, EX, MEM, WB)
- ✅ Hazard detection and forwarding units
- ✅ CSR file and interrupt controller
- ✅ AXI arbiter for IF/MEM priority
- ✅ Phase 1 modules reused (ALU, regfile, imm_gen, branch_comp)
- ✅ Initial regression: 115/115 tests passing
- 🔄 Comprehensive verification in progress

### 2026-02-14: Phase 2 Architecture Approved 🎉

**Architecture specification finalized**:

- ✅ All 7 open questions resolved
- ✅ 5-stage pipeline design approved
- ✅ Interrupt support (M-mode, timer + external)
- ✅ CSR instructions (CSRRW/S/C/I variants)
- ✅ Hazard handling strategy defined
- ✅ Debug interface updated for pipeline drain
- ✅ RTL implementation authorized

### 2026-02-13: Phase 1 Verification COMPLETE 🎉

**All 9/9 exit criteria met**:

- ✅ Tasks 5, 6, 7 complete — debug interface tests (6/6), coverage (37/37 instructions, 8/8 states), documentation
- ✅ Phase 1 RTL implementation confirmed complete (8/8 modules, ~1,900 lines)
- ✅ All verification suites passing with 0 failures
- ✅ Ready to begin Phase 2 (5-stage pipelined CPU)

### 2026-02-07: Task 4 Complete — AXI Protocol Tests 🎉

- ✅ 11/11 AXI4-Lite protocol tests implemented and passing
- ✅ Back-pressure, error injection, and protocol compliance categories covered
- ✅ `tb/cocotb/cpu/axi_models.py` (380 lines) + `test_axi_protocol.py` (860 lines)

### 2026-01-28: Task 3 Complete — Random Instruction Tests 🎉

- ✅ 10,000 random instructions (100 seeds × 100 instructions), 0 failures
- ✅ `tb/generators/rv32i_instr_gen.py` implemented
- ✅ `tb/cocotb/cpu/test_random_instructions.py` with multi-seed support

### 2026-01-26: Task 2 Complete — ISA Compliance Tests 🎉

- ✅ All 37/37 RV32I instructions tested and passing
- ✅ Major RTL bugs fixed (branch/jump timing, load data latching, register file reads)

### 2026-01-18: Phase 0 APPROVED - Ready for Phase 1 🎉

**Phase 0 Exit Criteria Met**:

- ✅ All 7 specifications reviewed and approved by human
- ✅ Python reference models validated (66/66 tests passing)
- ✅ cocotb test infrastructure reviewed and approved
- ✅ Project ready to transition to Phase 1 RTL implementation

**Authorization**: Phase 1 RTL development may now begin per PHASE1_ARCHITECTURE_SPEC.md

### 2026-01-18: Phase 0 Implementation Complete ✅

**Python Reference Models**:

- ✅ `tb/models/memory_model.py` - Sparse memory model with alignment checking (157 lines, 21 tests)
- ✅ `tb/models/rv32i_model.py` - Instruction-accurate RV32I CPU model (450+ lines, 33 tests)
- ✅ `tb/models/gpu_kernel_model.py` - SIMT GPU execution model (450+ lines, 12 tests)
- ✅ All 66 unit tests passing

**cocotb Test Infrastructure**:

- ✅ `tb/cocotb/bfm/axi4lite_master.py` - AXI4-Lite master BFM (200+ lines)
- ✅ `tb/cocotb/bfm/apb3_master.py` - APB3 master BFM with debug interface (250+ lines)
- ✅ `tb/cocotb/common/scoreboard.py` - RTL vs reference model comparison (130+ lines)
- ✅ `tb/cocotb/common/clock_reset.py` - Clock and reset utilities
- ✅ `tb/cocotb/cpu/test_example_counter.py` - Example test (3/3 tests passing)
- ✅ `tb/cocotb/cpu/test_smoke.py` - CPU smoke tests (6/6 tests passing)
- ✅ `tb/cocotb/cpu/test_isa_compliance.py` - ISA compliance tests (33/37 passing)
- ✅ Complete documentation (README.md, COCOTB_SETUP_SUMMARY.md)

**Issues Resolved**:

- Fixed Makefile clean target conflicts
- Updated to cocotb 2.0 API (logging changes)
- Fixed test timing issues in counter disable test

**Phase 0 Status**: ✅ COMPLETE - All specifications, reference models, and infrastructure approved (2026-01-18)

### 2026-01-17: Phase 0 Documentation Complete

- ✅ All 7 specification documents finalized
- ✅ MEMORY_MAP.md aligned to 4 KB minimum regions
- ✅ All known documentation issues resolved
- Ready to proceed with Python reference model implementation
- Phase 0 specifications ready for human review

### 2026-01-17: Specification Alignment

- Identified documentation gaps
- Created phase status tracking
- Aligning all specifications with current project state

### 2026-01-16: Project Restart

- Removed previous RTL implementation
- Starting fresh with specification-driven approach
- Commit: `1b4bb3b [Code] Remove database to restart project`

## Known Issues

### ✅ Resolved (2026-01-17)

All previous specification issues have been resolved:

1. ✅ **CLAUDE.md RTL references** - All RTL references properly labeled as "Planned Architecture (Phase 1)"
2. ✅ **RTL_DEFINITION.md protocol details** - Now includes AXI4-Lite (ARM IHI 0022E) and APB3 (ARM IHI 0024C) specifications
3. ✅ **GPU specification** - PHASE4_GPU_ARCHITECTURE_SPEC.md created (520 lines)
4. ✅ **Reference model specification** - REFERENCE_MODEL_SPEC.md created (596 lines)
5. ✅ **Memory map** - MEMORY_MAP.md created (360 lines) with 4 KB minimum alignment
6. ✅ **Verification plan phase alignment** - Restructured by phases (Phase 0-5 sections)
7. ✅ **Interrupt support clarity** - Clearly stated as Phase 2+ in ROADMAP.md

### 🔄 Current Issues

**None** - All Phase 0 documentation and implementation complete

## Next Actions

### Immediate — Phase 6 IP Expansion

**Phases 0-5 are complete.** Phase 5 signed off 2026-06-24 (M1-M12); Phase 6a's first peripheral
(GPIO) landed and hardened on Sky130 2026-09-26; Phase 7 M-a..M-c complete 2026-06-20.

**Current priority**: 6c — the INT8 NPU (bead `f7vs.11`), the last Phase 6 item. 6a and 6b are complete.
Golden spec: `docs/PHASE6_IP_EXPANSION_PLAN.md`. Tracking: bead epic `claude_verilog_test-f7vs`.

1. **Groundwork** (G1-G5) — front-loads the risk so each later peripheral is near-pure RTL + test:
   - ✅ G1 golden spec + ROADMAP bus/numbering corrections
   - G2 pre-allocate the APB window to `0x2001_0FFF` and `N_SOURCES` 6 → 12, in one commit
   - G3 pre-add every planned `tb_soc_top.sv` port and SDC exception, one forced clean
   - G4 `check_periph_filelists.py` + the first-ever `apb_interconnect` unit suite
   - G5 this status section

2. **6a peripherals**, derisk-first: PWM → WDT → TRNG → I2C. Each is RTL + L1 unit suite + L2
   SoC-fabric suite + SoC integration, with tests written **before** the RTL.

3. **Gate B** — one batched Sky130 harden after all of 6a
   (`make librelane-sky130-soc-noklayout`; the full target OOMs in KLayout DRC on this host,
   which sits before Netgen LVS in LibreLane's Classic flow).

4. **6b CRYPTO**, then **6c NPU** — the NPU warrants its own planning pass.

### Deferred / host-blocked (not Phase 6 work)

| Bead | Item | Blocker |
| :--- | :--- | :------ |
| `ma7` | ASAP7 CPU/GPU macros are Synlig-built with a proven branch miscompile | ≥32 GB host (`2kn`) |
| `lxv` | ASAP7 CPU sv2v re-harden: routing-congestion regression | ≥32 GB host (`2kn`) |
| `8qn4` | ASAP7 SoC has never been run with GPIO | chained to `ma7`/`lxv` |
| `e45j` | Sky130 post-RCX max-slew/max-cap; no post-RCX repair stage exists in LibreLane | re-measured at Gate B; **not** a Phase 6 exit criterion |
| `o1i` | Per-corner SRAM SPICE characterization (~80-95 h) | host stability |
| GH #105/#106 | Sky130 GPU stages 3-4 | ≥32 GB RAM + ~500 GB scratch |

## Documentation Structure

```text
docs/
├── ROADMAP.md                        # High-level project plan
├── PHASE_STATUS.md                   # This file - current status
├── design/
│   ├── PHASE0_ARCHITECTURE_SPEC.md   # Phase 0 CPU specification
│   ├── PHASE1_ARCHITECTURE_SPEC.md   # Phase 1 CPU specification (verified 2026-02-13)
│   ├── PHASE4_GPU_ARCHITECTURE_SPEC.md # Phase 4 GPU specification (frozen, ✅ complete)
│   ├── DESIGN_EXPECTATION.md         # High-level design goals
│   ├── RTL_DEFINITION.md             # Interface definitions
│   ├── GPU_MODEL.md                  # GPU execution model overview
│   ├── MEMORY_MAP.md                 # Address space allocation (complete 2026-01-17)
│   └── REFERENCE_MODEL_SPEC.md       # Python model specification (complete 2026-01-17)
└── verification/
    └── VERIFICATION_PLAN.md          # Verification strategy
```

## AI/Human Responsibilities for Phase 0 Remaining Tasks

### Python Reference Model Implementation

**AI may assist with**:

- Class structure and boilerplate code
- Simple instruction implementations (ADD, SUB, AND, OR, XOR, SLL, SRL, SRA)
- Register file and memory model scaffolding
- Unit test generation and formatting

**Human must**:

- Implement complex instructions (BRANCH, LOAD, STORE, JAL, JALR)
- Design and approve control flow logic
- Verify instruction semantics match RISC-V specification
- Cross-validate against spike simulator
- Final code review and approval

### cocotb Infrastructure Setup

**AI may assist with**:

- cocotb configuration files (Makefile, pyproject.toml)
- AXI4-Lite and APB3 driver scaffolding
- Test harness boilerplate
- Monitor and scoreboard templates

**Human must**:

- Review test strategy alignment with VERIFICATION_PLAN.md
- Approve infrastructure design decisions
- Validate driver implementations against protocol specs

### Final Specification Review

**HUMAN-ONLY**:

- Review all specifications for consistency and completeness
- Approve Phase 0 completion
- Authorize transition to Phase 1 (RTL implementation)

## Key Decisions

### Architecture Decisions

- **ISA**: RV32I subset (no CSR, no MMU, no compressed)
- **Initial pipeline**: Single-cycle (Phase 1), 5-stage pipeline (Phase 2)
- **Memory interface**: AXI4-Lite for main memory, APB3 for debug
- **Debug strategy**: APB3 slave interface with halt/resume/step
- **Verification**: Python reference model + cocotb + pyuvm

### Process Decisions

- **Specification-first**: All specs finalized before RTL
- **No architecture drift**: Phase N cannot start until Phase N-1 exits
- **AI boundaries**: AI assists with RTL/tests, humans own architecture
- **Verification requirement**: Reference model must match RTL

## Contact

For questions about project status or phase transitions, refer to ROADMAP.md or the latest git commits.
