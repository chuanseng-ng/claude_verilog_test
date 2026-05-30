# Phase 5 SoC Integration — Roadmap & Implementation Plan

**Status as of 2026-05-30**: This document is the **golden specification** for Phase 5 (SoC Integration). It reconciles `CLAUDE.md`, `docs/ROADMAP.md`, `docs/PHASE_STATUS.md`, `docs/design/MEMORY_MAP.md`, and `docs/verification/VERIFICATION_PLAN.md` into a single ordered work breakdown. Subsequent sessions should read this file first.

**Last verified**: 2026-05-30 (RTL/test/PD state audited; `rtl/periph/` and `rtl/soc/` confirmed absent)

**Decisions captured (2026-05-30)**: PD sign-off target = **ASAP7** (hierarchical block + top-level, consistent with Phase 3 1418 MHz and Phase 4 GPU 571 MHz). Breakdown = detailed sub-milestones. Beads = `bd create` commands listed in §6, executed at implementation start.

## How to use this document

1. Read §2 (current state) to know what exists vs what must be built.
2. Work milestones in dependency order (§4 graph). Each milestone (§3) has its own checkbox sub-items and **Exit** criteria.
3. Create the beads issues in §6 before writing code; mark `in_progress` per milestone.
4. Do **not** change Phase 3 cache FSMs except via milestone **M2**.
5. PD target is **ASAP7**; reuse `pnr/asap7/template/`.

---

## 1. Scope & locked decisions

**Phase 5 goal**: integrate the standalone Phase 1–4 blocks into a bootable SoC: CPU + GPU + DMA + AXI4 data crossbar + AXI-Lite control bus + UART + SPI + Timer + interrupt controller + behavioral SRAM controller + performance counters + power domains.

**Locked architecture decisions** (from `CLAUDE.md`, confirmed 2026-03-28 / 2026-05-20):

| # | Decision | Note |
|---|----------|------|
| 1 | Cache line = 16 bytes | Locked; revisit only with L2 |
| 2 | Direct-mapped caches | Locked; upgrade only if Phase 5 benchmarks prove conflict-miss impact |
| 3 | **AXI4 burst upgrade happens in Phase 5** | Phase 3 refill FSMs use 4 sequential AXI4-Lite beats; upgraded to burst here (M2) — do not change before |
| 4 | L2 cache | Not in base scope; gated on benchmarks (M10) |
| 5 | DRAM controller | Behavioral AXI4-slave SRAM only (M6); real DRAM is Phase 6+ |
| 6 | GPU control = AXI4-Lite slave | Overrides older APB3 wording in `MEMORY_MAP.md` |

---

## 2. Current state (verified 2026-05-30)

### Exists ✅
| Block | Path | Key external interface |
|-------|------|------------------------|
| CPU top | `rtl/cpu/rv32i_cpu_top.sv` | AXI4-Lite **master** (unified I/D, 32b addr/data, `axi_ar*/r*/aw*/w*/b*`); APB3 **slave** debug (`apb_paddr_i[11:0]`); IRQ in: `ext_irq_i` (MEIP), `timer_irq_i` (MTIP) |
| Caches | `rtl/mem/rv32i_{icache,dcache,cache_arbiter}.sv` | AXI4-Lite master, **4 sequential beats** per refill (`REFILL_BEATS=4`); no ARLEN/ARBURST yet |
| GPU top | `rtl/gpu/gpu_top.sv` | AXI4-Lite **ctrl slave** (`s_axil_*`, 12b); AXI4-Lite **ifetch master** (`m_axil_if_*`); AXI4 **data master** (`m_axi_*`, single-beat in P4); IRQ out: `gpu_irq_o` |

### Missing ❌ (Phase 5 must create)
- `rtl/soc/` — `axi_pkg.sv`, `axi4_crossbar.sv`, `axi_lite_interconnect.sv`, `axi_lite_register_bank.sv`, `sram_controller.sv`, `soc_top.sv`
- `rtl/periph/` — `uart_controller.sv`, `spi_controller.sv`, `timer.sv`, `interrupt_controller.sv`, `dma_engine.sv`
- No shared AXI package / SV interface defs (all modules use flat per-channel ports today)
- `tb/cocotb/soc/` test dir; `make soc_all` target in `sim/Makefile`; SoC-level reference model
- `pnr/asap7/soc/` config; `pnr/constraints/phase5_soc.sdc` + `phase5_soc.upf`; `make librelane-asap7-soc`

### Reusable infrastructure
- BFMs: `tb/cocotb/bfm/axi4lite_master.py`, `apb3_master.py`; AXI memory model `tb/cocotb/cpu/axi_models.py` (`ConfigurableAXIMemory`, error/backpressure injection)
- Reference models: `tb/models/{rv32i_model,cache_model,gpu_kernel_model,memory_model}.py`
- PD: `pnr/asap7/template/`, `pnr/asap7/{cpu,gpu}/config.json`, `pnr/constraints/phase3_cache.{sdc,upf}`; SRAM macros `sram_1rw_256x32_asap7`, `sram_1rw_128x32_asap7`

---

## 3. Milestones

Legend: ⏸️ not started · 🔄 in progress · ✅ done

### M1 — Foundations: AXI package + memory-map freeze *(no deps)*
- ⏸️ `rtl/soc/axi_pkg.sv` — AXI4 + AXI4-Lite params: `AXI_ADDR_WIDTH=32`, `AXI_DATA_WIDTH=32`, `AXI_ID_WIDTH`, burst encodings (`AXI_BURST_INCR=2'b01`), `AXI_LEN` for 4-beat (ARLEN=3), `AXI_SIZE=2` (32-bit). Optional SV interfaces `if_axi4`, `if_axil`.
- ⏸️ `rtl/soc/soc_addr_map_pkg.sv` — address-decode constants per memory map.
- ⏸️ Reconcile `docs/design/MEMORY_MAP.md`: spec routes peripherals via APB3 bridge @0x2000_xxxx, but GPU ctrl is AXI4-Lite. **Recommend AXI-Lite-native peripheral ring** (drop APB3 bridge for peripherals; keep APB3 only on CPU debug). Document the change in MEMORY_MAP.md.
- **Exit**: package lint-clean (`make -C sim lint`); MEMORY_MAP.md updated + reviewed.

### M2 — AXI4 burst upgrade of cache refill FSMs *(deps: M1)*
- ⏸️ `rtl/mem/rv32i_icache.sv` — replace 4× sequential AR→R (`refill_word_q`) with single AR (ARLEN=3, ARSIZE=2, ARBURST=INCR) + 4× R beats.
- ⏸️ `rtl/mem/rv32i_dcache.sv` — same for refill **and** writeback (single AW + 4× W burst).
- ⏸️ `rtl/mem/rv32i_cache_arbiter.sv` — pass burst signals; update grant logic/comment.
- ⏸️ `rtl/mem/rv32i_cache_pkg.sv` — keep `REFILL_BEATS=4` as the burst-length param.
- ⏸️ Extend `tb/cocotb/cpu/axi_models.py` for burst (ARLEN-aware).
- **Exit**: full Phase 3 regression green with burst FSMs — icache 7/7, dcache 8/8, cache_integration 5/5, 139/139 total.

### M3 — AXI4 crossbar + AXI-Lite control interconnect *(deps: M1)*
- ⏸️ `rtl/soc/axi4_crossbar.sv` — N-master (CPU cache arbiter, GPU data master, DMA) × M-slave (SRAM ctrl, + boot ROM). Addr-decode routing, arbitration (start from `rv32i_cache_arbiter.sv` priority pattern), burst + outstanding-transaction handling.
- ⏸️ `rtl/soc/axi_lite_interconnect.sv` — CPU config path + crossbar → AXI-Lite slaves (GPU ctrl, DMA ctrl, UART, SPI, Timer, IRQ ctrl).
- ⏸️ `rtl/soc/axi_lite_register_bank.sv` — reusable register-file slave.
- ⏸️ Unit tests `tb/cocotb/soc/test_crossbar.py`, `test_axil_interconnect.py` (reuse `bfm/axi4lite_master.py`).
- **Exit**: routing + arbitration + backpressure unit tests pass.

### M4 — Peripherals *(deps: M3; sub-items parallelizable)*
- ⏸️ `rtl/periph/uart_controller.sv` — AXI-Lite slave; TX/RX FIFO, baud divisor, status + IRQ.
- ⏸️ `rtl/periph/spi_controller.sv` — AXI-Lite slave; SPI master, configurable CPOL/CPHA, IRQ.
- ⏸️ `rtl/periph/timer.sv` — AXI-Lite slave; mtime/mtimecmp → drives CPU `timer_irq_i`.
- ⏸️ `rtl/periph/interrupt_controller.sv` — aggregate UART/SPI/timer/DMA/GPU IRQ → CPU `ext_irq_i` (MEIP); maskable + prioritized.
- ⏸️ Per-peripheral cocotb test + register-map check (`tb/cocotb/soc/test_{uart,spi,timer,irq}.py`).
- **Exit**: each peripheral test green; IRQ routing to CPU verified.

### M5 — DMA engine *(deps: M3)*
- ⏸️ `rtl/periph/dma_engine.sv` — descriptor queue, AXI4 master (burst), AXI-Lite ctrl slave, IRQ out → IRQ controller.
- ⏸️ Tests: descriptor-driven mem→mem copy, IRQ-on-complete, error handling.
- **Exit**: DMA transfer test passes against SRAM controller.

### M6 — Behavioral SRAM controller *(deps: M1)*
- ⏸️ `rtl/soc/sram_controller.sv` — AXI4 slave, burst-capable, behavioral (no DRAM refresh), parameterizable; backs main memory 0x0000_2000–0x0FFF_FFFF.
- **Exit**: AXI4 burst read/write protocol test passes.

### M7 — Performance counters *(deps: CPU+GPU integrated in M8, but spec early)*
- ⏸️ CSR-mapped (CPU) + AXI-Lite-readable (GPU stats): cycle, instret, branch mispredicts, I$/D$ miss counts, active warps, warp-stall cycles, divergence events. Wire from existing CPU/GPU status signals.
- **Exit**: counter read-back test matches injected events.

### M8 — SoC top integration *(deps: M2–M7)*
- ⏸️ `rtl/soc/soc_top.sv` — instantiate CPU + GPU + DMA + crossbar + AXI-Lite bus + peripherals + SRAM ctrl + IRQ ctrl; clock/reset distribution; route `gpu_irq_o` + peripheral IRQs → IRQ ctrl → CPU.
- ⏸️ Behavioral boot ROM @0x0000_1000.
- **Exit**: SoC elaborates lint-clean (`make -C sim lint`).

### M9 — SoC verification *(deps: M8)*
- ⏸️ Create `tb/cocotb/soc/` + `make soc_all` in `sim/Makefile`.
- ⏸️ SoC reference model (compose interconnect + peripheral + memory models in `tb/models/`).
- ⏸️ CPU→GPU integration: kernel launch → `gpu_irq_o` → result read (extend `test_cpu_gpu_handoff.py` to data plane).
- ⏸️ Software coherency: CPU D$ flush → GPU kernel → CPU D$ invalidate.
- ⏸️ DMA transfer + peripheral loopback (UART TX→RX, SPI).
- ⏸️ Boot test: load firmware to ROM, boot, run — **100/100 attempts** (per VERIFICATION_PLAN.md).
- ⏸️ Full regression: prior CPU (140) + GPU + cache; **1M+ cycle random SoC stress, 0 failures**.
- ⏸️ Benchmarks: CPU (vector add, dot product, memcpy, branch loop) + GPU (vector add, reduction, matmul, prefix scan, divergence).
- **Exit**: all SoC tests green; boot 100/100; 1M-cycle random clean.

### M10 — L2 cache decision gate *(deps: M9 benchmarks)*
- ⏸️ Review L1 miss rates from M9. Add `rtl/mem/l2_cache.sv` **only if** justified. Document the decision either way.

### M11 — Physical design (ASAP7, hierarchical) *(deps: M8/M9)*
- ⏸️ `pnr/asap7/soc/` (config.json, macro_placement.cfg, pdn.tcl) from `pnr/asap7/template/`; CPU + GPU as hard macros (macro-views flow).
- ⏸️ `pnr/constraints/phase5_soc.sdc` — multi-clock (CPU/GPU/peripheral domains), SoC I/O delays, false/multicycle paths.
- ⏸️ `pnr/constraints/phase5_soc.upf` — PD_CPU, PD_GPU, PD_SRAM, PD_PERIPH; isolation cells, level shifters, retention.
- ⏸️ `make librelane-asap7-soc` (mirror `librelane-asap7-gpu`).
- ⏸️ Close: timing (WNS≥0, TNS=0 all corners); PDN/IR-drop <5% (resolve P4 GPU `PSM-0069`/`PDN-0179` carry-over at SoC level); DRC/antenna clean.
- **Exit**: ASAP7 SoC sign-off — fmax, power, area documented; PDN closed.

### M12 — Sign-off + docs *(deps: M11)*
- ⏸️ Update `CLAUDE.md`, `docs/ROADMAP.md`, `docs/PHASE_STATUS.md` → Phase 5 complete.
- ⏸️ Write `docs/PHASE5_RUN_HISTORY.md` (mirror `docs/ASAP7_RUN_HISTORY.md`).
- ⏸️ Regenerate knowledge graph: `/graphify rtl docs fixes --update`.
- **Exit**: all VERIFICATION_PLAN.md Phase 5 exit criteria met.

---

## 4. Dependency graph

```
M1 ─┬─> M2 ──────────────┐
    ├─> M3 ─┬─> M4 ──────┤
    │       └─> M5 ──────┤
    └─> M6 ──────────────┤
            M7 ──────────┤
                         └─> M8 ─> M9 ─┬─> M10
                                       └─> M11 ─> M12
```

## 5. Risk matrix

| Risk | Likelihood / Impact | Mitigation |
|------|---------------------|------------|
| Crossbar deadlock / outstanding-txn ordering | High / High | Start from proven `rv32i_cache_arbiter.sv` pattern; exhaustive backpressure tests |
| Cache burst upgrade regresses Phase 3 | Med / High | Re-gate full 139-test suite before integration (M2 exit) |
| SoC multi-clock timing closure | High / Med | CDC review; pre-harden CPU/GPU as macros; per-domain SDC |
| PDN not closed at SoC (carries from P4 GPU) | Med / High | Dedicated PDN sub-task in M11 |
| Boot firmware + 1M-cycle random authoring (human-owned) | Med / Med | Flag AI/Human split per VERIFICATION_PLAN.md; AI scaffolds, human approves |
| Memory-map APB3-vs-AXI-Lite ambiguity | Low / Med | Resolved in M1 (AXI-Lite-native ring) |

## 6. Beads issues (create at implementation start)

```bash
bd create --title="M1: AXI package + memory-map freeze" --type=feature --priority=1
bd create --title="M2: AXI4 burst upgrade of cache refill FSMs" --type=feature --priority=1
bd create --title="M3: AXI4 crossbar + AXI-Lite interconnect" --type=feature --priority=1
bd create --title="M4: Peripherals (UART/SPI/Timer/IRQ ctrl)" --type=feature --priority=2
bd create --title="M5: DMA engine" --type=feature --priority=2
bd create --title="M6: Behavioral SRAM controller" --type=feature --priority=1
bd create --title="M7: Performance counters" --type=feature --priority=2
bd create --title="M8: SoC top integration" --type=feature --priority=1
bd create --title="M9: SoC verification" --type=feature --priority=1
bd create --title="M10: L2 cache decision gate" --type=task --priority=3
bd create --title="M11: ASAP7 SoC physical design sign-off" --type=feature --priority=1
bd create --title="M12: Phase 5 sign-off + docs" --type=task --priority=2
# Dependencies (replace <Mn-id> with actual IDs):
bd dep add <M2-id> <M1-id>
bd dep add <M3-id> <M1-id>
bd dep add <M6-id> <M1-id>
bd dep add <M4-id> <M3-id>
bd dep add <M5-id> <M3-id>
bd dep add <M8-id> <M2-id>; bd dep add <M8-id> <M4-id>; bd dep add <M8-id> <M5-id>
bd dep add <M8-id> <M6-id>; bd dep add <M8-id> <M7-id>
bd dep add <M9-id> <M8-id>
bd dep add <M10-id> <M9-id>
bd dep add <M11-id> <M9-id>
bd dep add <M12-id> <M11-id>
```

## 7. Phase 5 exit criteria (VERIFICATION_PLAN.md + ROADMAP.md)

- ✅ Boots software from ROM (100/100 attempts)
- ✅ 1M+ cycle random regression, 0 failures
- ✅ All peripherals functional; system-level assertions pass
- ✅ Full SoC timing closure (all corners, ASAP7)
- ✅ Power delivery verified (IR drop < 5%)
- ✅ DRC/LVS/antenna clean
- ✅ Tape-out ready (if target technology selected)

## 8. Out of scope (Phase 6+)

GPIO, I2C, PWM, watchdog, TRNG, AES/SHA accelerator, NPU; real DRAM controller; FreePDK45 SoC run. Add only after Phase 5 sign-off (see `CLAUDE.md` Phase 6+).
