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
- ✅ `rtl/soc/axi_pkg.sv` — AXI4 + AXI4-Lite params: `AXI_ADDR_WIDTH=32`, `AXI_DATA_WIDTH=32`, `AXI_ID_WIDTH=4`, burst encodings (`AXI_BURST_INCR=2'b01`), `AXI_LEN_LINE=3` (4-beat), `AXI_SIZE_4B=2`. (SV interfaces deferred — flat ports used.)
- ✅ `rtl/soc/soc_addr_map_pkg.sv` — address-decode constants + `decode_slave()`; ROM @0x0000_1000–1FFF, SRAM @0x0000_2000–0x0FFF_FFFF.
- ✅ Reconcile `docs/design/MEMORY_MAP.md`: peripherals are now an **AXI-Lite-native ring** (APB3 bridge dropped for peripherals; APB3 kept only on CPU debug @0x2000_0000–0FFF). Captured in `rtl/soc/soc_periph_map_pkg.sv` and documented in MEMORY_MAP.md: GPU 0x2000_1000, UART _2000, SPI _3000, Timer _4000, DMA _5000, IRQ _6000 (4 KB/slave).
- **Exit**: package lint-clean (`make -C sim lint`); MEMORY_MAP.md updated + reviewed. *(data-fabric slice ✅; peripheral-map reconcile ✅ done with M3 interconnect)*

### M2 — AXI4 burst upgrade of cache refill FSMs *(deps: M1)* ✅ COMPLETE
- ✅ `rtl/mem/rv32i_icache.sv` — single AR (ARLEN=3, ARSIZE=2, ARBURST=INCR) + 4× R beats.
- ✅ `rtl/mem/rv32i_dcache.sv` — burst refill **and** writeback (single AW + 4× W burst).
- ✅ `rtl/mem/rv32i_cache_arbiter.sv` — burst signals passed through; merged to main.
- ✅ `rtl/mem/rv32i_cache_pkg.sv` — `REFILL_BEATS=4` burst-length param.
- ✅ `tb/cocotb/cpu/axi_models.py` extended for ARLEN-aware burst.
- **Exit**: full Phase 3 regression green with burst FSMs — icache 7/7, dcache 8/8, cache_integration 5/5, 139/139 total.

### M3 — AXI4 crossbar + AXI-Lite control interconnect *(deps: M1)*
- ✅ `rtl/soc/axi4_crossbar.sv` — N-master (CPU cache arbiter, GPU data master, DMA) × M-slave (SRAM ctrl, + boot ROM). Addr-decode routing, per-slave priority-grant write/read engines (from `rv32i_cache_arbiter.sv` pattern), depth-1 outstanding lock, per-master DECERR engines for unmapped addresses. **Lint-clean (0 err / 0 warn, Verilator -Wall); 6/6 tests pass.**
- ✅ `rtl/soc/axi_lite_interconnect.sv` — single-master (CPU config) × 6-slave AXI-Lite router (GPU ctrl, UART, SPI, Timer, DMA ctrl, IRQ ctrl). Pure address-demux + response-mux (no arbitration: one master), depth-1 outstanding write+read, per-channel DECERR engine for unmapped addresses. Parameterized `SLV_BASE`/`SLV_LIMIT` (top-level passes `soc_periph_map_pkg`). **Lint-clean (0 err / 0 warn, Verilator -Wall).**
- ✅ `rtl/soc/axi_lite_register_bank.sv` — reusable parameterized register-file slave: per-register `WMASK` (RW/RO/partial), `wstrb` byte lanes, HW status-injection path (`hw_wen_i`/`hw_wdata_i`, bypasses WMASK), OOR addresses ack OKAY. Used by M4 peripherals + as the M3 interconnect test slave. **Lint-clean.**
- ✅ `rtl/soc/soc_periph_map_pkg.sv` — AXI-Lite control-ring address map (`AXIL_N_SLAVES=6`, base/limit arrays, `decode_axil_slave()`); 0x2000_1000–6FFF, 4 KB/slave.
- ✅ Unit tests `tb/cocotb/soc/test_crossbar.py` — **6/6 PASS**: routing+DECERR, same-slave arbitration, cross-slave concurrency, backpressure, 4-beat burst, response steering. New BFM `tb/cocotb/bfm/axi4_master.py` (burst+len) + `tb/cocotb/soc/axi4_slave_model.py` (burst+id echo).
- ✅ `tb/cocotb/soc/test_register_bank.py` — **6/6 PASS**: RW round-trip, RO WMASK, HW status injection, wstrb lanes, partial WMASK, out-of-range. `tb/cocotb/soc/test_axil_interconnect.py` — **4/4 PASS**: per-slave routing+isolation, multi-register routing, DECERR (below/above ring), master-side bready/rready backpressure. Both via reused `tb/cocotb/bfm/axi4lite_master.py`; `make soc_all` runs all three suites.
- **Exit**: routing + arbitration + backpressure unit tests pass. **✅ DONE — crossbar 6/6 + register bank 6/6 + AXI-Lite interconnect 4/4 = 16/16 green; all M3 RTL Verilator -Wall clean.**

**This-session scope (crossbar + minimal M1 foundation):** delivered `axi_pkg.sv`,
`soc_addr_map_pkg.sv`, `axi4_crossbar.sv` (3M×2S), cocotb wrapper `tb_axi4_crossbar.sv`,
`make soc_all` target. RTL lint via **rtl-design** agent; tests via **verification** agent.
No PD this item (crossbar hardens at SoC top, M11).

### M4 — Peripherals *(deps: M3; sub-items parallelizable)* ✅ COMPLETE (2026-06-01)
- ✅ `rtl/periph/uart_controller.sv` — AXI-Lite slave; TX/RX FIFO, baud divisor, status + IRQ. **Hardened (dq4):** 16× oversample RX with mid-bit 2-of-3 majority vote, STOP-bit framing-error detect (`UART_STATUS[6]`, read-to-clear), sticky TX-empty IRQ qualifier (no spurious reset IRQ), WSTRB byte-lane snoop. *Note: `UART_BAUD` now sets the oversample-tick period — 1 bit = 16×(D+1) clocks.*
- ✅ `rtl/periph/spi_controller.sv` — AXI-Lite slave; SPI master, configurable CPOL/CPHA, IRQ. **Hardened (dq4):** WSTRB byte-lane snoop; real-MISO + RX-overflow tests added.
- ✅ `rtl/periph/timer.sv` — AXI-Lite slave; mtime/mtimecmp → drives CPU `timer_irq_i`.
- ✅ `rtl/periph/interrupt_controller.sv` — aggregate UART/SPI/timer/DMA/GPU IRQ → CPU `ext_irq_i` (MEIP); maskable + prioritized.
- ✅ Per-peripheral cocotb test + register-map check (`tb/cocotb/soc/test_{uart,spi,timer,irq}.py`). UART 11/11, SPI 13/13, full `soc_all` green; Phase 1–4 rollup green.
- **Exit**: ✅ each peripheral test green; IRQ routing to CPU verified; dq4 hardening findings closed.

### M5 — DMA engine *(deps: M3)* ✅ COMPLETE
- ✅ `rtl/periph/dma_engine.sv` — descriptor queue, AXI4 master (burst), AXI-Lite ctrl slave, IRQ out → IRQ controller.
- ✅ Tests: descriptor-driven mem→mem copy, IRQ-on-complete, error handling (`test_dma.py`, 6/6 in `soc_all`).
- **Exit**: ✅ DMA transfer test passes against SRAM controller.

### M6 — Behavioral SRAM controller *(deps: M1)* ✅ COMPLETE
- ✅ `rtl/soc/sram_controller.sv` — AXI4 slave, burst-capable, behavioral (no DRAM refresh), parameterizable; backs main memory 0x0000_2000–0x0FFF_FFFF.
- **Exit**: ✅ AXI4 burst read/write protocol test passes (`test_sram_controller.py`, 7/7 in `soc_all`).

### M7 — Performance counters *(deps: CPU+GPU integrated in M8, but spec early)* ✅ COMPLETE
- ✅ CSR-mapped (CPU `mcycle`/`minstret`/`mhpmcounter3-5`) + AXI-Lite-readable (GPU stats). CPU re-sign-off at ASAP7 780 ps / 1282 MHz (perf-CSR cost; see CLAUDE.md + ASAP7_RUN_HISTORY.md).
- **Exit**: ✅ counter read-back test matches injected events (7/7).

### M8 — SoC top integration *(deps: M2–M7)* ✅ COMPLETE
- ✅ `rtl/soc/soc_top.sv` — CPU + GPU(×2 masters) + DMA + crossbar (4M×3S) + AXI-Lite ring (6 slaves) + peripherals + SRAM ctrl + IRQ ctrl; `gpu_irq_o` + peripheral IRQs → IRQ ctrl → CPU.
- ✅ Behavioral boot ROM @0x0000_1000 (`rtl/soc/boot_rom.sv`).
- **Exit**: ✅ SoC elaborates lint-clean (`make -C sim lint_soc`); functionally booted in M9 foundation slice.

### M9 — SoC verification *(deps: M8)* ✅ COMPLETE (2026-06-19) — foundation slice ✅ DONE (2026-06-03)
**Foundation slice ✅ (2026-06-03):**
- ✅ Created `tb/cocotb/soc/` boot infra + `soc_boot`/`soc_boot_diag` targets; `soc_all` extended to all M3–M6 component suites + boot.
- ✅ SoC reference model `tb/models/soc_model.py` — composes `rv32i_model.RV32IModel` + `memory_model.MemoryModel` over ROM+SRAM; golden committed-PC stream + final state. (Peripheral-state models deferred to integration fast-follows.)
- ✅ `tb/cocotb/soc/tb_soc_top.sv` — cocotb wrapper (flat ports + `MEM_INIT_FILE`); `boot_fw/` 8-instr RV32I firmware + generator.
- ✅ Boot test `tb/cocotb/soc/test_boot.py` — PC scoreboard + SRAM sentinels + **100/100 boot-stability gate, 0 fail**. `soc_all` green (crossbar 6, register_bank 6, axil 4, sram 7, dma 6, timer 5, irq 6, uart 11, spi 13, boot 3 — 0 FAIL).
- ✅ Bring-up bugs fixed: (1) CPU reset PC hardcoded 0x0 → added `RESET_PC` param (default 0x0) through `rv32i_pipeline_if`→`rv32i_core`→`rv32i_cpu_top`, `soc_top` sets 0x0000_1000; (2) boot ROM image never loaded (string `MEM_INIT_FILE` baked empty under Verilator) → cocotb backdoor load of `boot.hex` into `boot_rom.mem`.

**Fast-follows ✅ COMPLETE (2026-06-19):**
- ✅ DMA + peripheral loopback (`qdd`): `test_periph_loopback.py` — DMA mem→mem + UART TX→RX + SPI internal loopback through `soc_top`, self-checking PASS_PC + backdoor DMA check. **1/1.** *(Unblocked by `go9` D-cache MMIO bypass: `addr ≥ 0x2000_0000` uncached single-beat AXI + flush/inval CSRs 0x7C0/0x7C1 — `rv32i_dcache.sv`/`rv32i_csr_file.sv`; commit 9f53f65.)*
- ✅ Software coherency (`777`): `test_soc_coherency.py` — CPU writes src → `CSRW 0x7C0` flush → GPU kernel reads src + writes dst → `CSRW 0x7C1` inval → CPU reads dst. **3/3** (positive + no_flush negative reaches FAIL_PC + no_inval cold-line). *(Unblocked by `7fs` crossbar AR/AW fix below.)*
- ✅ CPU→GPU integration (`ov2`): `test_cpu_gpu_irq.py` — CPU launches GPU kernel via AXI-Lite cmd queue, waits interrupt-driven on `gpu_irq`, ISR runs, reads result from SRAM. **2/2** (positive + IRQ-not-enabled teeth). Commit 4c2ffd9.
- ✅ Stronger SRAM check (`yqc`): `test_boot_sram_sentinels` now backdoor-reads the hardware SRAM array to confirm 0xDEADBEEF/0x12345678 physically landed (boot fw flushes D$ before halt). Commit 83883dc.
- ✅ Full regression: `soc_all` **73/73**; CPU rollup green (smoke/c_programs/isa_uvm 54 + fault_inj + caches + gpu_all); **1M+ cycle random SoC stress 0 failures** (`pgf`, `test_soc_stress.py` — 10-iter multi-master mix, **1,079,867 cycles**, watchdog + integrity invariants). Commit 2fad468.
- ✅ Benchmarks (`pgf`, per iteration): CPU 32-word burst 2358 cyc; DMA mem→mem 26587 cyc; GPU kernel+flush+inval 50538 cyc.
- ✅ **RTL bugs found+fixed via SoC verification:** `go9` (D-cache cached MMIO) and `7fs` (axi4_crossbar single-cycle-AR/AW handshake hang + arbitration priority mismatch — AR/AW capture regs + single-grant early-accept + lowest-index FSM capture; commit 550bd97; latent since Phase 4, masked by combinational-arready mock slaves).
- **Exit**: ✅ all SoC tests green; boot 100/100 ✅; soc_all 73/73; 1M-cycle random clean (1,079,867 cyc, 0 fail). **M9 DONE.**

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
