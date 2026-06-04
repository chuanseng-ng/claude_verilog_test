# PHASE5_MMIO_UNCACHED_DECISION.md
# Architecture Decision: CPU D-Cache MMIO Bypass (Uncached Window)

**Date**: 2026-06-04
**Status**: APPROVED — spec for chip-design-rtl:rtl-design-orchestrator
**Problem verified in**: M9 SoC simulation (`tb/cocotb/soc/`)

---

## 1. Problem Statement

`rv32i_dcache` (Phase 3, write-back / write-allocate / direct-mapped, 4 KB, 16-byte
lines) caches every address presented on `dc_addr_i` without exception. No
uncacheable signal exists anywhere in the dmem path (`rv32i_dcache.sv`,
`rv32i_pipeline_mem.sv`, `rv32i_cache_arbiter.sv`). Consequence in Phase 5:

- CPU firmware stores to the peripheral AXI-Lite ring
  (`0x2000_1000`–`0x2000_6FFF`) are trapped in dirty D-cache lines and never
  reach the peripheral registers until an eviction is forced.
- CPU firmware loads from peripheral status/RX registers return stale cached data;
  the CPU poll-loop spins indefinitely.
- Affected peripherals: GPU-ctrl, UART, SPI, timer, DMA-ctrl, IRQ-ctrl.
- Blocks every CPU-firmware peripheral interaction and therefore the M9 SoC
  verification milestones (CPU-GPU launch, DMA loopback, UART/SPI loopback).

---

## 2. Memory Map Ground Truth

Source: `rtl/soc/soc_addr_map_pkg.sv` and `rtl/soc/soc_periph_map_pkg.sv`.

| Region | Base | Limit | Cacheable |
|---|---|---|---|
| Boot ROM | `0x0000_1000` | `0x0000_1FFF` | Yes (I-cache only) |
| Main SRAM | `0x0000_2000` | `0x0FFF_FFFF` | Yes (D-cache + I-cache) |
| APB3 debug | `0x2000_0000` | `0x2000_0FFF` | No (MMIO) |
| GPU-ctrl | `0x2000_1000` | `0x2000_1FFF` | No (MMIO) |
| UART | `0x2000_2000` | `0x2000_2FFF` | No (MMIO) |
| SPI | `0x2000_3000` | `0x2000_3FFF` | No (MMIO) |
| Timer | `0x2000_4000` | `0x2000_4FFF` | No (MMIO) |
| DMA-ctrl | `0x2000_5000` | `0x2000_5FFF` | No (MMIO) |
| IRQ-ctrl | `0x2000_6000` | `0x2000_6FFF` | No (MMIO) |

The APB3 debug slot at `0x2000_0000` is already inaccessible through the D-cache
AXI path (it connects directly to the CPU debug port), but the same uncached window
covers it at no extra cost.

---

## 3. Decisions

### Decision 1 — Uncached Window Bounds

**Chosen**: `addr >= 32'h2000_0000` is uncached; all lower addresses are cacheable.

The single boundary `0x2000_0000` is a power-of-2-aligned 512 MB boundary, making
the comparator a single 4-bit equality check on `addr[31:28] == 4'h2` combined with
`addr[27]` — synthesises to a fast 5-input AND/OR, negligible timing impact.

Add one localparam to `soc_addr_map_pkg.sv`:

```
localparam logic [31:0] MMIO_BASE = 32'h2000_0000;
```

All three SoC decode packages (`soc_addr_map_pkg`, `soc_periph_map_pkg`) already
define peripheral bases above this boundary. This constant becomes the single
source of truth for every module that needs to classify an address.

**Rejected alternative — per-slave ranges**: decoding each of the six peripheral
4 KB windows individually would require six comparators in the D-cache critical
path. Adds area with no architectural benefit because no cacheable mapping exists
in the `0x2000_xxxx` space.

---

### Decision 2 — Decode and Bypass Location

**Chosen**: inside `rv32i_dcache.sv`, at the top of the CS_IDLE state entry.

The bypass is a read of `dc_addr_i` against `MMIO_BASE` in CS_IDLE, before any
SRAM chip-select is issued. When `dc_addr_i >= MMIO_BASE` and `dc_valid_i`, the
cache FSM skips CS_SRAM_LATCH / CS_HIT_PENDING / CS_TAG_CHECK entirely and jumps
directly to a new `CS_UNCACHED_WR` or `CS_UNCACHED_RD` state:

**CS_UNCACHED_RD**: issue a single-beat AXI AR (`ARLEN=0, ARSIZE=4B, ARBURST=INCR`)
on the existing `axi_ar*` port. Wait for one R beat. Return `axi_rdata_i` directly
on `dc_rdata_o`. Stall the pipeline while waiting (same `dc_stall_o` mechanism).
Transition to CS_DONE (rdata already captured in a 1-word register) then CS_IDLE.

**CS_UNCACHED_WR**: issue a single-beat AXI AW (`AWLEN=0`) + one W beat + wait for
B response. Return to CS_IDLE on B. `dc_stall_o` held asserted throughout, identical
to the existing writeback stall pattern.

No line allocation. No dirty-bit update. No SRAM access.

The existing `dc_*` CPU-side interface (`dc_addr_i`, `dc_valid_i`, `dc_we_i`,
`dc_wdata_i`, `dc_wstrb_i`, `dc_rdata_o`, `dc_stall_o`) is unchanged.
`rv32i_pipeline_mem.sv` and `rv32i_cache_arbiter.sv` require no modifications.
`mem_cache_stall_o` in the pipeline continues to be driven by `dc_stall_i` exactly
as today.

**Rejected alternative — bypass mux in MEM stage / cache arbiter**: routing around
the D-cache in `rv32i_pipeline_mem.sv` would require a second AXI master port on
`rv32i_core.sv`, a second arbitration path through `rv32i_cache_arbiter.sv`, and
an `uncacheable` sideband signal propagating through the EX/MEM pipeline register.
This widens the blast radius to five modules and creates a new source of ID
conflicts on the crossbar master port. The in-cache bypass keeps all complexity
inside one module boundary.

**AXI4 burst fields for uncached accesses** (Decision 4 is satisfied here):
`ARLEN=0` / `AWLEN=0` (single beat). The `axi4_to_axilite` bridge at crossbar
slave S2 (SLV_PERIPH) already handles AWLEN=0 as a one-shot write and ARLEN=0 as
a one-shot read — no bridge changes needed.

---

### Decision 3 — Ordering and Hazards

**Chosen**: strong ordering, no FENCE required from firmware for normal
load/store sequences to peripheral registers.

The bypass states are synchronous and blocking: CS_UNCACHED_WR does not release
the pipeline stall until B response is received. Therefore a store to a peripheral
register is committed (acknowledged by the crossbar and the peripheral's write
port) before the next CPU instruction can issue. A subsequent load to the same
peripheral address is guaranteed to read post-store state at the peripheral.

The `axi4_to_axilite` bridge is depth-1 (one outstanding transaction), so no
reordering can occur between the CPU and the peripheral register file.

**FENCE.I**: not affected. FENCE.I is handled in the EX stage and flushes the
I-cache; D-cache bypass has no interaction with it.

**Firmware guidance** (to be documented in `docs/design/MEMORY_MAP.md` note):
A FENCE instruction is not required between MMIO stores and subsequent MMIO loads
to the same device, because the bypass guarantees B-before-AR ordering within a
single CPU thread. If a firmware sequence writes a DMA descriptor in SRAM and then
writes the DMA kick register (MMIO), the SRAM store may still be in cache; firmware
must either flush the cache line (via FENCE) or use the DMA engine's own
coherency protocol before writing the kick.

---

### Decision 4 — Single-Beat AXI Bursts to the Peripheral Bridge

Confirmed: uncached accesses use `ARLEN=0` / `AWLEN=0`.

`axi4_to_axilite.sv` (Phase 5 M8) already serialises multi-beat bursts by issuing
one AXI-Lite transaction per beat. With ARLEN=0 and AWLEN=0 the bridge loop
executes exactly once — it degenerates to a single AXI-Lite transaction with no
overhead beyond a one-cycle latch. The bridge comment explicitly states it handles
ARLEN up to the AXI4 maximum, so ARLEN=0 is always correct.

This also means the 4-beat refill machinery in `rv32i_dcache.sv` (`AXI_LEN_LINE`,
ARLEN=3) is never invoked for MMIO addresses, eliminating the previous bug where
a cache miss on a peripheral address would issue a 4-beat burst attempting to refill
a 16-byte cache line from a peripheral register — which is undefined behaviour for
FIFO-style hardware registers.

---

### Decision 5 — Blast Radius

**Modules changed (RTL)**:

| Module | File | Change |
|---|---|---|
| `rv32i_dcache` | `rtl/mem/rv32i_dcache.sv` | Add `uncached` decode in CS_IDLE; add `CS_UNCACHED_RD` and `CS_UNCACHED_WR` states; add single-beat AXI AR/R and AW/W/B paths |
| `soc_addr_map_pkg` | `rtl/soc/soc_addr_map_pkg.sv` | Add `MMIO_BASE = 32'h2000_0000` localparam |

**Modules unchanged**:

| Module | Reason unaffected |
|---|---|
| `rv32i_icache` | I-cache fetches only from code space (`0x0000_1000`–`0x0FFF_FFFF`); MMIO window is never a fetch target |
| `rv32i_cache_arbiter` | Sees only the AXI4 ports of the D-cache; ARLEN=0 and AWLEN=0 are already legal inputs |
| `rv32i_pipeline_mem` | `dc_addr_o`, `dc_valid_o`, `dc_we_o`, `dc_wdata_o`, `dc_wstrb_o`, `dc_stall_i` interface unchanged |
| `rv32i_core` | D-cache instantiation wiring unchanged |
| `rv32i_hazard_unit` | `mem_cache_stall_o` source unchanged |
| `axi4_to_axilite` | Already handles AWLEN=0/ARLEN=0 |
| `axi4_crossbar` | SLV_PERIPH decode unchanged |
| `axi_lite_interconnect` | Unchanged |
| All peripheral RTL | Unchanged |

**Timing risk**: the `uncached` comparator is `dc_addr_i >= 32'h2000_0000`, evaluated
combinationally in CS_IDLE before any SRAM chip-select. The D-cache is already
timing-sensitive at 780 ps (1282 MHz, Phase 5 M7 CPU standalone). The critical path
in CS_IDLE is the SRAM csb0 assignment which is already gated by `dc_valid_i`. The
uncached decode adds one 5-input comparator in series with `dc_valid_i` on the SRAM
chip-select enable. Estimated additional delay: 30–50 ps (one NAND2 + one AND2 in
ASAP7 RVT). This is within the +24 ps setup slack reported in M7. **Flag to PD**: if
STA shows the csb0 path degrades, the comparator can be registered one cycle earlier
by latching `uncached_q` from the previous-cycle address when the pipeline is stalled,
at zero timing cost (the address is stable during stall).

---

### Decision 6 — Verification Hook

The following regression must reach PASS before M9 is considered complete:

1. **`tb/cocotb/soc/test_periph_loopback.py`** (primary gate): this test already
   exercises CPU firmware MMIO stores and status-register loads. After the fix,
   the test must reach its `PASS_PC` sentinel without timeout.

2. **Phase 3 cache suite** (`sim/Makefile` targets `phase3_dcache`,
   `phase3_icache`, `phase3_all`): all 139 tests must remain green. The bypass
   path must not alter any cacheable-address behaviour.

3. **SoC boot test** (`tb/cocotb/soc/test_boot.py`): 100/100 pass baseline
   (established Phase 5 M9) must be maintained.

4. **No-regression**: `make soc_all` (all M9 cocotb tests) must complete with
   zero new failures.

**Additional targeted test cases** to add inside `test_periph_loopback.py`:
- Write to a peripheral register, read back same address, confirm no stale data
  (verifies no-allocate on read).
- Write to SRAM address just below `0x2000_0000`, then write to UART at
  `0x2000_2000`, confirm SRAM write went through D-cache (hit on read-back)
  and UART write reached peripheral (check tx-busy bit set).
- Confirm that a dirty SRAM line at a set that aliases `0x2000_2000` (index bits
  `[11:4]`) is not evicted by an MMIO access to `0x2000_2000` — the bypass must
  suppress all SRAM index computation for MMIO addresses.

---

## 4. Summary of Decisions

| # | Decision | Chosen |
|---|---|---|
| 1 | Window bounds | `addr >= 0x2000_0000` uncached; one constant in `soc_addr_map_pkg` |
| 2 | Bypass location | Inside `rv32i_dcache.sv`; two new FSM states; CPU interface unchanged |
| 3 | Ordering | Strong: B-before-release for stores; no FENCE needed for MMIO-to-MMIO sequences |
| 4 | Beat count | ARLEN=0 / AWLEN=0 always; bridge handles without modification |
| 5 | Blast radius | 2 modules changed; I-cache, arbiter, MEM stage, core, all peripherals unchanged |
| 6 | Verification | `test_periph_loopback.py` PASS_PC + Phase 3 suite + boot test + soc_all no-regression |

---

## D-Cache Maintenance (flush / invalidate) mechanism

**Date**: 2026-06-04
**Status**: APPROVED — spec for chip-design-rtl:rtl-design-orchestrator (implement together with Section 3 uncached MMIO)
**Problem verified in**: M9 DMA/GPU SoC co-simulation

---

### D1. Problem Statement

`rv32i_dcache.sv` has no software-invokable maintenance path. Eviction of dirty
lines happens only on capacity miss (CS_WRITEBACK on a dirty victim). No
flush-all, clean, or invalidate operation exists. No cache-control instruction
or CSR decode exists in any file under `rtl/cpu/`.

This creates two concrete failure modes in Phase 5:

**DMA source coherency (before DMA read):** Firmware writes a source buffer into
cacheable SRAM (`0x0000_2000`–`0x0FFF_FFFF`). The data lands in dirty D-cache
lines. The DMA engine reads SRAM via the AXI4 crossbar and sees stale byte values
because the dirty lines have not been written back. Without a clean/flush
primitive, firmware cannot guarantee the DMA engine reads correct data.

**CPU destination coherency (after DMA/GPU write):** The DMA engine or GPU writes
a result buffer to SRAM. The CPU subsequently reads from the same addresses.
Because the D-cache may hold a valid (but stale) cached copy of those lines from
a prior access, the CPU sees old data. Without an invalidate primitive, firmware
cannot force a re-fetch from SRAM.

Both paths are exercised in the M9 test suite:
`test_periph_loopback.py` (DMA loopback) and the future CPU-GPU kernel-launch test.
The CLAUDE.md Phase 5 coherency contract ("CPU flushes D-cache before GPU kernel
launch, invalidates after completion") has no RTL mechanism to back it.

---

### D2. Decision 1 — Interface: CSR-Mapped Cache Control (flush-all / invalidate-all)

**Chosen**: Two write-only custom CSRs in the M-mode custom read/write range:

| CSR addr | Name | Operation triggered on any write |
|---|---|---|
| `12'h7C0` | `dcache_flush` | Write-back all dirty lines; leave all lines valid |
| `12'h7C1` | `dcache_inval` | Invalidate all lines (clear valid bits, discard dirty data without writeback) |

A single write of any value (`CSRW dcache_flush, x0`) triggers the operation.
The CSR read-back is always zero (write-only semantics; no state is stored in
the CSR register itself).

**Rationale — flush-all, not per-line:** The D-cache is direct-mapped, 4 KB, 256
lines. A flush-all iterates 256 lines at worst — a bounded, fixed-cycle
operation. The only use cases in Phase 5 are: (a) before GPU/DMA launch (flush
all), and (b) after GPU/DMA write (invalidate all). No partial-line or address-
range operation is needed for these use cases. Per-line address-based ops
(Zicbom `cbo.clean` / `cbo.flush` / `cbo.inval`) require additional instruction
decode, a new operand register forwarding path through the EX stage, and a
base-address register in the dcache; this adds blast radius across five pipeline
stages for no M9 benefit. Defer Zicbom to Phase 6.

**Rationale — CSR vs FENCE overloading:** FENCE already has defined RISC-V
semantics (ordering hint, not a maintenance instruction). Overloading it would
create compliance confusion. CSR access reuses the existing Zicsr decode path
already implemented in the ID stage (`csr_access` signal), requires zero new
instruction encodings, and is trivially accessible from bare-metal firmware with
a single `CSRW`.

**Rejected alternative — Zicbom CBO instructions:** Standard and future-proof, but
requires new opcode decode (major opcode `MISC-MEM`, funct3 `0b010`), a register
file read forwarding path to deliver `rs1` as the cache address, and per-line FSM
logic in the dcache. No architectural benefit over flush-all for the 4 KB
direct-mapped geometry at this phase. Revisit for Phase 6 if a multi-way or
larger cache is introduced.

**Rejected alternative — FENCE semantics overloading:** Non-compliant; FENCE is an
ordering barrier, not a maintenance instruction in the RISC-V spec.

---

### D3. Decision 2 — D-Cache FSM Additions

Two new FSM states are added to `cache_state_t` in `rv32i_cache_pkg.sv`:

```
CS_FLUSH_SCAN   // walk all 256 lines; write back dirty ones via existing wb_buf/AXI path
CS_INVAL_SCAN   // walk all 256 lines; clear valid_array[] and dirty_array[] in bulk
```

A new 8-bit register `maint_idx_q` (range 0–255) tracks the current line being
processed.

**CS_FLUSH_SCAN behaviour (per cycle):**

The FSM enters `CS_FLUSH_SCAN` from `CS_IDLE` when the dcache receives
`dc_flush_i` (a 1-cycle pulse generated by the CSR write decode, see D4 below).
Each cycle the FSM inspects `valid_array[maint_idx_q]` and
`dirty_array[maint_idx_q]`:

- If the line is dirty: capture `data_dout_r[0..3]` — but `data_dout_r` is only
  valid after a SRAM read. The flush walker therefore issues a SRAM read for the
  current line (setting `tag_csb0=0`, `data_csb0[w]=0`, `tag_addr0=maint_idx_q`,
  `data_addr0[w]=maint_idx_q`) and advances to a sub-state that waits for
  `CS_SRAM_LATCH` latency, then loads `wb_buf_q[0..3]` from `data_dout_r[0..3]`
  and reconstructs `wb_addr_base` from `tag_dout_r[TAG_BITS-1:0]` concatenated
  with `maint_idx_q` and `4'b0000`. It then drives the existing AXI write path
  (the same `aw_done_q` / `w_done_q` / `axi_word_q` machine used by
  CS_WRITEBACK) exactly as a normal capacity writeback. After B-response,
  `dirty_array[maint_idx_q]` is cleared and `maint_idx_q` is incremented.
- If the line is clean or invalid: `maint_idx_q` increments immediately (1 cycle
  per clean line).
- When `maint_idx_q` wraps from 255 to 0: transition to `CS_IDLE`, assert
  `dc_maint_done_o` for 1 cycle.

Rather than a full separate sub-state machine, the implementation can reuse
`CS_WRITEBACK` by setting `state_q <= CS_WRITEBACK` for each dirty line and
returning to `CS_FLUSH_SCAN` (instead of `CS_REFILL`) on B-response, with a
`flush_mode_q` flag distinguishing a maintenance writeback from a miss writeback.
The `flush_mode_q` flag suppresses the `CS_REFILL` transition and instead
increments `maint_idx_q` and loops back to `CS_FLUSH_SCAN`. This avoids
duplicating the AXI write datapath.

**CS_INVAL_SCAN behaviour (per cycle):**

The FSM enters `CS_INVAL_SCAN` from `CS_IDLE` when `dc_inval_i` is received.
No SRAM or AXI activity occurs. Each cycle, `valid_array[maint_idx_q]` and
`dirty_array[maint_idx_q]` are cleared to 0 (the existing sequential
`valid_array` / `dirty_array` write port is used — one index per cycle, the same
port used for refill and writeback). `maint_idx_q` increments every cycle.
After 256 cycles the FSM returns to `CS_IDLE` and asserts `dc_maint_done_o`
for 1 cycle.

Note: `CS_INVAL_SCAN` deliberately discards dirty data without writeback. This
is the correct semantic when the CPU is about to read DMA/GPU results: any CPU-
dirty line over a region the DMA wrote is stale-on-the-CPU side and must be
dropped. If firmware needs a combined clean-then-invalidate, it issues
`CSRW dcache_flush` first (polls done), then `CSRW dcache_inval`.

**Worst-case cycle cost:**

| Operation | Best case | Worst case |
|---|---|---|
| `CS_INVAL_SCAN` | 256 cycles | 256 cycles (1 cycle/line, no AXI) |
| `CS_FLUSH_SCAN` (all clean) | 256 cycles | 256 cycles (1 cycle/line) |
| `CS_FLUSH_SCAN` (all dirty) | 256 × (2 SRAM + 1 AW + 4 W + 1 B) ≈ 256 × ~10 | ~2560 cycles at 1282 MHz ≈ 2 µs |

At 1282 MHz, worst-case flush (all 256 lines dirty) completes in approximately
2000–3000 cycles (~2 µs). This is acceptable for a one-time pre-launch fence in
firmware. Typical Phase 5 firmware buffers are small; most lines will be clean.

**AXI port note:** During `CS_FLUSH_SCAN` the same AXI write port used by
CS_WRITEBACK is active. The refill read port (`axi_ar*`) is idle — no R-beat
cancellation hazard exists (per the existing audit comment at dcache line 587,
which anticipated this exact addition and cross-references the
`cancel_ar_q` / `cancel_wait_r_q` fix from `rv32i_icache.sv`). Because the flush
does not issue AR transactions, the cancel-race does not apply.

---

### D4. Decision 3 — Ordering and Completion

**Chosen**: stall-until-done. The `dc_stall_o` signal is asserted for the entire
duration of `CS_FLUSH_SCAN` and `CS_INVAL_SCAN`. The `CSRW dcache_flush` or
`CSRW dcache_inval` instruction therefore stalls the pipeline until the operation
completes. The instruction following `CSRW` is guaranteed to execute only after
the cache is clean/invalid.

This is the simplest possible firmware model: no polling loop required. Firmware
writes the CSR and the subsequent instruction (e.g. the DMA kick store to
`0x2000_5000`) is automatically ordered after the maintenance operation.

```
# Firmware sequence — DMA source coherency (before DMA read)
csrw  dcache_flush, x0    # stalls pipeline ~2 µs worst case; returns when all dirty
                           # lines are written back to SRAM
sw    t0, DMA_SRC_ADDR(x0) # write DMA descriptor to MMIO (uncached bypass, Decision 2)
sw    t1, DMA_LEN(x0)
sw    t2, DMA_KICK(x0)    # kick DMA — guaranteed SRAM is coherent

# Firmware sequence — CPU destination coherency (after DMA/GPU write)
csrw  dcache_inval, x0    # stalls pipeline 256 cycles; drops all cached lines
lw    a0, RESULT_ADDR(x0) # guaranteed to fetch fresh data from SRAM
```

**Interaction with uncached MMIO path (Section 3 Decision 2):** The maintenance
CSR writes go through the normal Zicsr path in the EX stage and do not interact
with the uncached MMIO bypass. The DMA kick register at `0x2000_5000` is above
the MMIO boundary and follows the uncached path in all cases; it is never cached
and never needs to be flushed.

**`dc_maint_done_o` port:** A 1-cycle done pulse is added to the dcache port list
(alongside the existing `dc_miss_o`). The CSR file does not need to read this
signal; it is available for the M7 performance counter infrastructure to count
maintenance events if desired (optional, not required for M9).

---

### D5. Decision 4 — Minimal Op Set for M9 and CPU-GPU Launch

**Chosen**: implement exactly two operations now — **flush-all** (`dcache_flush`)
and **invalidate-all** (`dcache_inval`). No per-line addressing. No combined
clean-and-invalidate atomic CSR.

This is sufficient for:
- M9 DMA loopback: flush-all before DMA read; invalidate-all after DMA write.
- CPU-to-GPU launch: flush-all before kernel launch (ensures GPU reads coherent
  SRAM); invalidate-all after GPU writes results (ensures CPU reads fresh SRAM).
- Any future peripheral DMA or shared-memory test following the same pattern.

Per-line operations (Zicbom) are explicitly deferred to Phase 6, conditioned on
evidence that the 2 µs worst-case flush-all is a measurable bottleneck in a real
workload. For the 4 KB direct-mapped cache geometry at Phase 5, flush-all is
architecturally equivalent to Zicbom for all current use cases.

---

### D6. Decision 5 — Blast Radius and PPA

**Modules changed (RTL):**

| Module | File | Change |
|---|---|---|
| `rv32i_cache_pkg` | `rtl/mem/rv32i_cache_pkg.sv` | Add `CS_FLUSH_SCAN`, `CS_INVAL_SCAN` to `cache_state_t`; add `DCACHE_FLUSH_CSR = 12'h7C0`, `DCACHE_INVAL_CSR = 12'h7C1` localparams |
| `rv32i_dcache` | `rtl/mem/rv32i_dcache.sv` | Add `dc_flush_i`, `dc_inval_i` input ports; `dc_maint_done_o` output port; add `maint_idx_q` counter; add `flush_mode_q` flag; implement `CS_FLUSH_SCAN` / `CS_INVAL_SCAN` states; extend `dc_stall_o` to cover both new states |
| `rv32i_csr_file` | `rtl/cpu/core/rv32i_csr_file.sv` | Add `csr_dcache_flush_o`, `csr_dcache_inval_o` 1-cycle pulse outputs; decode `12'h7C0` write → assert `csr_dcache_flush_o`; decode `12'h7C1` write → assert `csr_dcache_inval_o`; both CSRs read as zero |
| `rv32i_core` | `rtl/cpu/core/rv32i_core.sv` | Wire `csr_dcache_flush_o` → `dc_flush_i` on `u_dcache`; wire `csr_dcache_inval_o` → `dc_inval_i` |

**Modules unchanged:**

| Module | Reason unaffected |
|---|---|
| `rv32i_icache` | I-cache has no dirty state; FENCE.I already handles I-cache invalidate via `ic_invalidate_i`; D-cache maintenance is orthogonal |
| `rv32i_pipeline_mem` | `dc_stall_o` → `mem_cache_stall_o` path unchanged; the new stall source is inside dcache behind the existing stall signal |
| `rv32i_hazard_unit` | `mem_cache_stall_o` source is unchanged; hazard unit stalls the pipeline on any dc_stall assertion regardless of cause |
| `rv32i_cache_arbiter` | Sees only AXI4 ports; maintenance writeback reuses existing AWVALID/WVALID signals, which are already arbitrated |
| All peripheral RTL | No interface changes |
| `axi4_crossbar` | AXI master port usage during flush writeback is identical to capacity writeback; no new IDs or channels |

**Timing risk:**

The `dc_flush_i` and `dc_inval_i` inputs arrive at the dcache from `rv32i_csr_file`
via `rv32i_core` wiring. They are registered 1-cycle pulses (set in the CSR write
always_ff block, same timing path as `fence_i_pulse` which is already implemented
and timed). They only affect the FSM transition out of `CS_IDLE`, which is not the
critical path (the CS_IDLE critical path is the SRAM csb0 enable, already
analysed in Decision 5 of Section 3 above). The new `maint_idx_q` counter is an
8-bit register with no fanout to timing-critical logic (its only load is the SRAM
address and the `valid_array` / `dirty_array` write index, both of which are
already multi-cycle paths).

The new states add two enum values to `cache_state_t`. The existing state register
is encoded by synthesis. Adding two values widens the one-hot or binary encoding
by at most 1 bit — negligible area impact (~1–2 flip-flops). The `maint_idx_q`
counter adds 8 flip-flops. Total estimated area delta: < 20 standard cells.

**PPA conclusion**: no timing risk to the 780 ps (1282 MHz) M7 CPU path.
The maintenance states are only active during explicit firmware-triggered
operations; they do not affect the normal cache hit/miss critical path at all.

---

### D7. Decision 6 — Firmware and Verification Impact

**Firmware (`tb/cocotb/soc/periph_fw/gen_periph_hex.py`):**

The DMA loopback firmware must be updated with the following protocol:

1. Write source buffer words to cacheable SRAM (`0x0000_2000` range) — these go
   through the D-cache as normal write-allocate stores.
2. Issue `CSRW dcache_flush, x0` — pipeline stalls until all dirty SRAM lines are
   written back. SRAM now holds the correct source data.
3. Write DMA source address, length, and destination address to DMA-ctrl MMIO
   registers (`0x2000_5000` range) via the uncached bypass path.
4. Write DMA kick register — DMA engine starts; it reads coherent SRAM.
5. Poll DMA-done interrupt or status register (MMIO, uncached bypass).
6. Issue `CSRW dcache_inval, x0` — pipeline stalls 256 cycles; all D-cache lines
   are invalidated.
7. Read destination buffer from cacheable SRAM — guaranteed to fetch fresh DMA
   results from SRAM rather than stale cached data.

The same flush-before-launch / invalidate-after-completion protocol applies to
the CPU-GPU kernel test (`test_cpu_gpu_integration.py` when it is written for M9).

**Verification acceptance gates (no-regression + new):**

1. **`test_periph_loopback.py` PASS_PC** — primary M9 DMA gate. The DMA loopback
   must complete correctly end-to-end, including the firmware flush/invalidate
   sequence. Timeout without PASS_PC = failure.

2. **Phase 3 cache suite** (`sim/Makefile` targets `phase3_dcache`, `phase3_icache`,
   `phase3_all`, 139 tests total) — must remain 139/139 green. The new FSM states
   must not perturb any cacheable-address hit/miss/writeback behaviour. In
   particular: `dc_flush_i` and `dc_inval_i` must be tied to 0 in the Phase 3
   testbench wrappers (or absent from the port list if left as `input logic` with
   default 0 when unconnected).

3. **SoC boot test** (`test_boot.py`, 100/100 baseline) — must be maintained.

4. **`make soc_all` no-regression** — zero new failures across all M9 cocotb tests.

5. **New targeted maintenance test cases** to add inside `test_periph_loopback.py`:
   - Write 4 words to cacheable SRAM, call `dcache_flush` CSR, read back via a
     second agent (or cache-bypass read) to confirm data reached SRAM.
   - Write 4 words to cacheable SRAM, call `dcache_inval` CSR, read back — confirm
     the read goes to SRAM (not cache), i.e. a miss occurs and data is fetched fresh.
   - Confirm that `dcache_inval` discards dirty data (write a line, call inval
     without flush, re-read — the pre-inval write must NOT be visible, confirming
     dirty discard rather than silent writeback).
   - Confirm that `dcache_flush` followed by `dcache_inval` leaves the cache empty
     with SRAM holding the flushed values (combined coherency sequence).

---

### D8. Summary of D-Cache Maintenance Decisions

| # | Decision | Chosen |
|---|---|---|
| D1 | Interface | Two write-only CSRs: `dcache_flush` @ `12'h7C0`, `dcache_inval` @ `12'h7C1`; read-as-zero |
| D2 | FSM additions | `CS_FLUSH_SCAN` (reuses `CS_WRITEBACK` AXI path via `flush_mode_q`); `CS_INVAL_SCAN` (256-cycle register walk, no AXI); `maint_idx_q` 8-bit counter |
| D3 | Completion | `dc_stall_o` held for full operation duration; no firmware polling needed; next instruction after CSRW is ordered after maintenance completes |
| D4 | Op set | Flush-all + Invalidate-all only; per-line Zicbom deferred to Phase 6 |
| D5 | Blast radius | 4 modules (`rv32i_cache_pkg`, `rv32i_dcache`, `rv32i_csr_file`, `rv32i_core`); I-cache, arbiter, MEM stage, hazard unit, peripherals, crossbar unchanged |
| D6 | Verification | `test_periph_loopback.py` PASS_PC + Phase 3 139/139 + boot 100/100 + soc_all no-regression + 4 new maintenance test cases |
