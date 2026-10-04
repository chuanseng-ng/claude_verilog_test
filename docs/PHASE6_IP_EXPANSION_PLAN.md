# Phase 6 — IP Expansion Plan (golden spec)

**Status:** Groundwork in progress (bead `f7vs`, 2026-09-28). Phase 6a GPIO ✅ complete.
**Scope:** every remaining Phase 6 item — the four unbuilt 6a peripherals, the 6b crypto
accelerator, and the 6c NPU.
**Supersedes for planning purposes:** the 24-line sketch at `docs/ROADMAP.md:429-453`, which
remains the roadmap-level summary. Where the two disagree, this document is authoritative.

This is the Phase 6 equivalent of `docs/PHASE5_SOC_INTEGRATION_PLAN.md` and
`docs/PHASE7_MIXED_SIGNAL_PLL_PLAN.md`. Phase 6 previously had no such document, which is why
its scope existed only as a table of filenames.

---

## 1. Numbering — reconciled

The repo carried two incompatible readings of "Phase 6a". Resolved as follows, and the
sub-phase letters below are now the only ones used:

| Sub-phase | Scope | Status |
|:---------:|:------|:-------|
| **6a** | All APB4 register peripherals: GPIO, PWM, WDT, TRNG, I2C | ✅ complete 2026-10-03 |
| **6b** | AES-128 + SHA-256 accelerator (`crypto_accel`) | ✅ 2026-10-03 (`f7vs.10`) |
| **6c** | Minimal INT8 NPU (`npu_top`) | ✅ 2026-10-04 (`f7vs.11`) |

`docs/ROADMAP.md:398` already used this reading. `CLAUDE.md:31`'s "6a GPIO ✅ done; 6b+ not
started" treated 6a as GPIO-only; that wording is corrected to "6a GPIO done, 6a remainder +
6b + 6c planned".

Items numbered **6a-2 … 6a-5** below are the remaining 6a peripherals, in implementation order.

---

## 2. Bus decision — APB4 for everything, including crypto and the NPU

`docs/PERIPHERAL_BUS_EVALUATION.md` (bead `ahe`, GO) settled the peripheral-bus standard as
**APB4 behind `apb4_register_bank`**, and named the Phase 6 set — "GPIO/I2C/PWM/WDT/TRNG/AES-SHA"
— as the reason to settle it before scaling. Every peripheral in this document is therefore an
APB4 slave on the existing `axil_to_apb` → `apb_interconnect` sub-tree.

**`docs/ROADMAP.md:431`'s "AXI4-Lite slave" for AES/SHA is stale** — a survivor of the
pre-2026-09-20 text, the same wording the bus correction fixed for the 6a heading but not for 6b.
Corrected in the same PR as this document.

### Bulk-data paths are an explicit non-goal

Neither crypto nor the NPU gets an AXI4 master or a crossbar slave port in Phase 6. Both use
**programmed I/O over APB**.

Reusing `rtl/periph/dma_engine.sv` was considered and **rejected as not a real mechanism**: it is
an AXI4 burst master whose destination must be an AXI4 *slave address*, so feeding crypto with it
would require giving crypto an AXI4 slave data port — `SOC_N_SLAVES` 3 → 4
(`rtl/soc/soc_addr_map_pkg.sv:33`), touching `axi4_crossbar`, which already had an AR/AW
handshake and arbitration defect (bead `7fs`) — in exchange for a throughput number nothing in
this repo measures.

⚠️ **Consequence for the roadmap's figures.** `docs/ROADMAP.md:437-439` quotes ~75 MB/s (Sky130),
~400 MB/s (FreePDK45) and ~1 GB/s (ASAP7) for AES. Those describe the **deferred AXI4-master
version**, not what Phase 6b lands. An APB single-beat register feed is far slower. The roadmap
is annotated accordingly; do not quote those numbers against the delivered RTL.

Follow-up: **Phase 6b-2** — AXI4 bulk data path for crypto and/or the NPU. Not scheduled.

---

## 3. The `apb4_register_bank` static-WMASK pattern (read before designing any register map)

`rtl/soc/apb4_register_bank.sv:31` declares:

```systemverilog
parameter logic [31:0] WMASK [N_REGS] = '{default: '1}
```

**`WMASK` is a parameter, not a runtime input.** The bank's only other write path, `hw_wen_i` /
`hw_wdata_i` (`:51-52`), *bypasses* WMASK entirely, and on a same-cycle collision the SW write
wins (`:94-109`). `prdata` is purely combinational off `regs_o[idx]` (`:117-122`).

Three consequences that decide register-map questions across this phase:

1. **No register can claim dynamic SW-write protection from the bank.** "Writable only while
   idle", "locked until reset", "writable only in supervisor mode" — none of these are
   expressible. Emulating one with a same-cycle HW writeback leaves a one-cycle window in which
   the protected value is wrong.
2. **A true write-only register is impossible inside the bank**, because the read path is
   combinational off the stored word.
3. **The workaround is a shadow register outside the bank**, loaded by APB write-snoop (the
   `gpio_controller.sv:281-301` idiom, or the `spi_controller` TX-push idiom), with the bank's
   corresponding word left at `WMASK = 32'h0` and never HW-written — so it reads 0 forever while
   the real value lives in the shadow flop.

Applied below to: the AES key registers (pattern 3 + a `busy` guard), and the WDT register lock
(dropped outright rather than half-implemented).

**RTL-review checklist item:** no register in a Phase 6 peripheral may document dynamic SW-write
protection as being enforced by the bank.

---

## 4. Address map — pre-allocated in full

Final APB sub-tree: **14 slaves**. Every BASE/LIMIT pair, plus the final window limits and the
testbench's `BAD_HIGH`, is allocated in **one commit** (bead `f7vs.2`) rather than six times over.

This is safe because `rtl/soc/apb_interconnect.sv:104-110` returns `pready=1, pslverr=1` for an
in-window address that no slave claims — a DECERR equivalent, **not a hang**. A reserved-but-unbuilt
slot is therefore a well-defined SLVERR, and bead `f7vs.2` adds a test asserting exactly that.

| Address range | Peripheral | APB idx | IRQ bit | Landed in |
|:--------------|:-----------|:-------:|:-------:|:----------|
| `0x2000_2000-2FFF` | UART | 0 | 0 | Phase 5 |
| `0x2000_3000-3FFF` | SPI | 1 | 1 | Phase 5 |
| `0x2000_4000-4FFF` | Timer | 2 | 2 (tied 0 — MTIP direct) | Phase 5 |
| `0x2000_5000-5FFF` | *(DMA — AXI-Lite ring slave 2; last-match wins inside the bridge window)* | — | 3 | Phase 5 |
| `0x2000_6000-6FFF` | IRQ controller | 3 | — | Phase 5 |
| `0x2000_7000-7FFF` | PLL | 4 | — | Phase 7 M-c |
| `0x2000_8000-8FFF` | PMU | 5 | — | GH #100 |
| `0x2000_9000-9FFF` | PLL2 | 6 | — | GH #92 |
| `0x2000_A000-AFFF` | GPIO | 7 | 5 | 6a ✅ `ckc` |
| **`0x2000_B000-BFFF`** | **PWM** | **8** | **6** | 6a-2 |
| **`0x2000_C000-CFFF`** | **WDT** | **9** | **7** | 6a-3 |
| **`0x2000_D000-DFFF`** | **TRNG** | **10** | **8** | 6a-4 |
| **`0x2000_E000-EFFF`** | **I2C** | **11** | **9** | 6a-5 |
| **`0x2000_F000-FFFF`** | **CRYPTO** | **12** | **10** | 6b |
| **`0x2001_0000-0FFF`** | **NPU** | **13** | **11** | 6c |

- `AXIL_APB_LIMIT` (`rtl/soc/soc_periph_map_pkg.sv:52`) = `PERIPH_LIMIT`
  (`rtl/soc/soc_addr_map_pkg.sv:50`) = **`0x2001_0FFF`**, set once.
- `BAD_HIGH` (`tb/cocotb/soc/test_axil_interconnect.py:57`) = **`0x2001_1000`**, set once.
- `APB_N_SLAVES` and the per-peripheral index constants grow **one at a time** as each item
  lands — the unpacked `APB_SLV_BASE`/`APB_SLV_LIMIT` array literals must have exactly
  `APB_N_SLAVES` contiguous entries, so that edit is irreducible (and cheap).

### The window crosses out of `0x2000_xxxx` — verified inert

At the 14th slave the APB window extends past `0x2000_FFFF` into `0x2001_0FFF`. This is
functionally fine: `paddr` is **32 bits end to end** — `axil_to_apb` is instantiated with
`.ADDR_W(32)` and `apb_interconnect` with `.ADDR_W(32)` (`rtl/soc/soc_bus.sv:608,652`) — and each
peripheral consumes only `paddr[11:0]`. Documented in `soc_periph_map_pkg.sv`'s header.

### `0x2000_5000` is not reusable

It is a hole *inside* the APB bridge window, owned by DMA through the AXI-Lite last-match rule
(`rtl/soc/soc_periph_map_pkg.sv:10-13`). Do not allocate a peripheral there.

---

## 5. Interrupt allocation — pre-allocated in full

`interrupt_controller` goes `N_SOURCES` **6 → 12** in bead `f7vs.2`, with bits 6-11 tied `1'b0`
until their peripheral lands. This is the idiom already in the tree: `rtl/soc/soc_top.sv:1725`
deliberately ties bit 2 (TIMER) to `1'b0` because the timer IRQ goes straight to CPU MTIP.

| Bit | Source | Condition |
|:---:|:-------|:----------|
| 0 | UART | existing |
| 1 | SPI | existing |
| 2 | *(tied 0)* | timer routes to MTIP directly |
| 3 | DMA | existing |
| 4 | GPU | existing |
| 5 | GPIO | existing (6a) |
| 6 | PWM | period wrap, per-channel sticky |
| 7 | WDT | bark (first timeout) |
| 8 | TRNG | FIFO threshold reached, or health-test failure |
| 9 | I2C | done / NACK / arbitration lost / timeout, OR-reduced |
| 10 | CRYPTO | operation complete |
| 11 | NPU | inference complete |

Final concatenation:

```systemverilog
.irq_src_i ({npu_irq, crypto_irq, i2c_irq, trng_irq, wdt_irq, pwm_irq,
             gpio_irq, gpu_irq_o, dma_irq, 1'b0, spi_irq, uart_irq})
```

All six new `logic <name>_irq;` declarations are added in the same commit, driven from `1'b0`, so
the use-before-declare hazard (declaration must sit after `soc_top.sv:625` and **before**
`u_ext_irq_sync` at `:637` — yosys-slang strict mode, bead `q7n`) also collapses to one event.

⚠️ **`test_irq` is the expected breakage.**
`WMASK[REG_IRQ_MASK] = 32'(({32{1'b1}} >> (32 - N_SOURCES)))` widens from `0x3F` to `0xFFF`. That
test's mask expectation is checked first and its fix ships in the same commit as the widening.

**Every `irq_o` must be level-held, never a single-cycle pulse** — each source crosses
`core_clk → cpu_core_clk` through a plain 2-FF `cdc_2ff_sync` (`rtl/soc/soc_top.sv:637-644`),
which can miss a pulse. W1C status clears are done by APB write-snoop, not through WMASK.

---

## 6. Implementation order

Groundwork first, then ascending difficulty. The groundwork PRs front-load the risk, so after
them each item is close to pure RTL + test, and ordering by ascending difficulty maximises the
number of items that land per unit of debugging.

| # | Item | Bead | Rationale for position |
|:-:|:-----|:-----|:-----------------------|
| G1 | This document + ROADMAP corrections | `f7vs.1` | Settles the bus conflict and the numbering before any RTL |
| G2 | Address window + IRQ pre-allocation | `f7vs.2` | Collapses 6 rounds of window-growth churn into 1 |
| G3 | `tb_soc_top.sv` ports + SDC exceptions | `f7vs.3` | Collapses the Verilator cache-stale hazard to 1 event |
| G4 | Filelist checker + `apb_interconnect` suite | `f7vs.4` | Automates the one hazard cocotb cannot catch |
| G5 | `PHASE_STATUS.md` Phase 6 section | `f7vs.5` | De-stales the project status |
| 6a-2 | **PWM** | `f7vs.6` | Cheapest payload: no async input, no CDC, no FSM, no FIFO. Validates G2–G4 |
| 6a-3 | **WDT** | `f7vs.7` | Tiny RTL, but carries the reset-tree decision — do it while the diff is small |
| 6a-4 | **TRNG** | `f7vs.8` | Trivial under the `ifdef` entropy design; settles randomness-scoreboarding methodology cheaply |
| 6a-5 | **I2C** | `f7vs.9` | Highest-risk 6a item: protocol FSM, open-drain, clock stretching, new BFM |
| — | *Gate B — batched Sky130 harden* | — | After all of 6a, not per item |
| 6b | **CRYPTO** | `f7vs.10` | Largest datapath; first real area question |
| 6c | **NPU** | `f7vs.11` | Biggest; SRAM-macro decision; most deferrable |

---

## 7. Per-item specification

Every peripheral follows the `rtl/periph/gpio_controller.sv` skeleton: `ADDR_W = 12`,
`clk`/`rst_n` port names (not `pclk`/`presetn`), the 9-signal APB4 slave face,
`apb4_register_bank` with `RESET_VAL[]`/`WMASK[]`, synchronous active-low reset, a bare `$fatal`
elaboration guard inside a generate scope, and a named `endmodule : <name>`.

### 6a-2 — PWM (`rtl/periph/pwm_controller.sv`)

4 channels (`parameter N_CH = 4`, guarded 1-8). 16-bit period + 16-bit duty + 16-bit prescaler —
16 bits at 40 MHz gives a 610 Hz floor, ample for LED and motor use; 32 bits is dead area.
**Shared period, per-channel duty**: per-channel period is 4× the registers for nothing, and a
shared period is what makes multi-channel phase relationships meaningful. Left/edge-aligned only —
centre-alignment needs an up/down counter and only earns its keep alongside dead-time.

**Non-goal: dead-time generation.** It implies complementary output pairs and a shoot-through
safety story that no consumer in this SoC has.

Pins: `pwm_o[3:0]` only. PWM is push-pull, so there is no `oe`, no async input and **no CDC at
all** — only a `-to` false path, per the `uart_tx_o` convention.

| Offset | Name | Access | Description |
|:------:|:-----|:------:|:------------|
| 0x000 | PWM_CTRL | RW | `[3:0]` per-channel enable, `[7:4]` per-channel output polarity |
| 0x004 | PWM_PERIOD | RW | `[15:0]` shared period, in prescaled ticks |
| 0x008 | PWM_PRESCALE | RW | `[15:0]` core_clk divider; tick = (PRESCALE+1) clocks |
| 0x00C | PWM_DUTY01 | RW | `[15:0]` ch0 duty, `[31:16]` ch1 duty |
| 0x010 | PWM_DUTY23 | RW | `[15:0]` ch2 duty, `[31:16]` ch3 duty |
| 0x014 | PWM_IRQ_EN | RW | `[3:0]` per-channel period-wrap IRQ enable (masks `irq_o` only) |
| 0x018 | PWM_IRQ_STAT | RO | `[3:0]` sticky per-channel period-wrap |
| 0x01C | PWM_IRQ_CLR | WO | W1C against `PWM_IRQ_STAT`; reads 0 |

`N_REGS = 8`, mirroring GPIO's proven size.

**Required tests:** `duty == 0` is a true 0 % with no one-cycle glitch; `duty >= period` is a true
100 %; `period == 0` behaviour is defined and documented; a prescaler change mid-period is
well-behaved; polarity inversion; per-channel independence; IRQ stickiness and W1C.

### 6a-3 — WDT (`rtl/periph/watchdog_timer.sv`)

32-bit down-counter. A feed requires writing the magic value `0x5A5A_C0DE` to `WDT_FEED`,
snoop-decoded; any other value is rejected, so a wild-pointer store cannot accidentally pet the
dog. **Windowed mode is included but default-disabled** (`WINDOW == 0` → a feed is accepted at any
time): it is one comparator plus one register, and it is what makes this a watchdog rather than a
timer.

**Register lock: dropped, not deferred.** Per §3, the bank cannot suppress SW writes, and a
same-cycle HW-writeback emulation leaves a one-cycle window in which the locked value is wrong.

#### Bark and bite

- **Bark** — first timeout → sticky `WDT_STATUS.bark` → level-held `irq_o` → IRQ bit 7.
- **Bite** — a second full period with no feed →
  1. assert the new top-level output `wdt_rst_req_o`, level-held until external reset; **and**
  2. when `WDT_CTRL.RST_EN == 1`, AND into **`cpu_domain_rst_n` only**, through a
     `cdc_reset_sync` mirroring `u_cpu_pmu_rst_sync` (`core_clk` → `cpu_core_clk`).

`RST_EN` **resets to 0**, so the existing regression stays bit-identical until a test opts in.

**Why CPU-domain-only.** A full-SoC reset would also reset the WDT — producing a self-clearing
pulse that no cocotb test can scoreboard — and would tear down the APB fabric mid-transaction. The
CPU is what hung. `rtl/soc/soc_top.sv:440` already provides the AND-in point:
`cpu_domain_rst_n = cpu_core_rst_n & pmu_cpu_rst_n_cpu_sync`, with `u_cpu_pmu_rst_sync` as the
`cdc_reset_sync` precedent.

**Do not route the bite through `pmu.sv`.** Its 9-state-per-domain FSM only re-samples its target
while settled at ON or OFF, so an emergency request would need a new priority path through a
verified FSM for no benefit — and `pmu.sv` is precisely where bead `2k8` was deliberately *not*
fixed, because its sequencing order is UPF-mandated.

⚠️ **Documented limitation.** The WDT is clocked from `core_clk` through its prescaler. No
independent always-on oscillator exists in this SoC, so **a stuck PLL cannot be barked at**. This
must be stated in the module header rather than implied away.

| Offset | Name | Access | Description |
|:------:|:-----|:------:|:------------|
| 0x000 | WDT_CTRL | RW | `[0]` enable, `[1]` RST_EN (reset value 0), `[2]` window mode enable |
| 0x004 | WDT_RELOAD | RW | Counter reload value, in prescaled ticks |
| 0x008 | WDT_COUNT | RO | Live counter value |
| 0x00C | WDT_WINDOW | RW | Closed-window threshold; 0 disables the window check |
| 0x010 | WDT_FEED | WO | Write `0x5A5A_C0DE` to feed; any other value rejected. Reads 0 |
| 0x014 | WDT_PRESCALE | RW | `[15:0]` core_clk divider |
| 0x018 | WDT_STATUS | RO | `[0]` bark, `[1]` bite, `[2]` window violation — all sticky |
| 0x01C | WDT_IRQ_CLR | WO | W1C against `WDT_STATUS`; reads 0 |

`N_REGS = 8`.

### 6a-4 — TRNG (`rtl/periph/trng.sv`)

**Key structural decision: the peripheral is 100 % portable, and Sky130-exclusivity is confined
to a swappable entropy sub-module selected by `ifdef` — not by a top-level port.**

```
`ifdef TRNG_RO_SKY130  → rtl/periph/trng_ro_sky130.sv   (ring oscillator + blackbox stub)
`else                  → rtl/periph/trng_lfsr_entropy.sv (default)
```

The stub pattern mirrors `sky130_sram_4kbyte_1rw1r_32x1024_8_stub.sv` and
`rv32i_cpu_top_stub.sv`. The default arm is three LFSRs on distinct primitive polynomials
(31/29/23-bit) XOR-combined through a von Neumann debiaser — **deterministic and explicitly not
cryptographic**, which it must advertise by forcing `TRNG_STATUS.INSECURE = 1`.

This removes the entire "keep a non-portable peripheral out of the ASAP7 file lists" problem:
`trng.sv` has **zero top-level ports**, sits in every file list and every PD flow, needs no
conditional SoC-level instantiation and no tied-off slot, and keeps the G4 filelist checker
simple. What is Sky130-exclusive is the **entropy-quality claim**, not the RTL.

`docs/ROADMAP.md:411-413`'s TRNG row is corrected to: *"✅ RTL portable (LFSR entropy source);
ring-oscillator entropy Sky130-only."*

Health tests: **repetition-count only** (NIST SP 800-90B), with a sticky `STATUS.health_fail`.
Adaptive-proportion deferred. `TRNG_DATA` pops the FIFO via read-snoop (the `SPI_RX` idiom).
FIFO depth 4. IRQ when `fifo_level >= threshold` or on `health_fail`.

| Offset | Name | Access | Description |
|:------:|:-----|:------:|:------------|
| 0x000 | TRNG_CTRL | RW | `[0]` enable, `[1]` IRQ enable, `[5:2]` FIFO threshold |
| 0x004 | TRNG_STATUS | RO | `[0]` data ready, `[1]` FIFO full, `[2]` health_fail (sticky), `[3]` INSECURE |
| 0x008 | TRNG_DATA | RO | Pops one 32-bit word from the entropy FIFO (read-snoop) |
| 0x00C | TRNG_SEED | RW | LFSR seed; ignored when the ring-oscillator source is compiled in |
| 0x010 | TRNG_IRQ_CLR | WO | W1C against `STATUS.health_fail`; reads 0 |

`N_REGS = 8` (three reserved).

**Verification approach.** The LFSR path is deterministic from `TRNG_SEED`, so golden-vector the
first N words against a new `tb/models/trng_lfsr_model.py`, then layer distribution sanity checks:
bit balance within ±5 % over 4096 bits, no 32-word repeat, and the debiaser discarding the
expected fraction.

The Sky130 ring oscillator is a **separate analog deliverable**, via the `analog-design-*`
orchestrators reusing `analog/pll_clkgen/circuit/ring_vco.sp`. It is **deferred out of this
phase's DoD** — it is analog/PD work, and the DoD stops before PD.

### 6a-5 — I2C (`rtl/periph/i2c_controller.sv`)

**Master-only**, but arbitration loss is *detected* (comparing driven-high against sensed SDA) and
reported as an error status bit; there is no retry FSM. Full multi-master roughly doubles the FSM
for a SoC with one master, while detection falls out of the open-drain model for free and buys a
real error path to test.

**Clock stretching is mandatory**: the bit engine only advances out of SCL-high once `scl_i` reads
high. Paired with an `I2C_TIMEOUT` counter and a sticky timeout status bit — without the timeout a
stuck slave hangs the FSM and a cocotb failure gives no diagnosis.

7-bit addressing; **repeated-START included** (required for register reads); 10-bit deferred.
Standard 100 kHz and Fast 400 kHz via a 16-bit `I2C_CLKDIV`, not a mode enum — one register covers
both, and Fm+/Hs need pad rise-time specs this tree does not model. TX and RX FIFOs of 8 bytes
each, covering the register-address-plus-7-byte-payload EEPROM/sensor pattern.

#### Open-drain with no tristate in the tree

Reuse the GPIO triplet convention verbatim: `i2c_scl_o` / `i2c_scl_oe_o` / `i2c_scl_i` and the SDA
equivalents. `*_o` is **hard-tied `1'b0`** and `*_oe_o` is the real control — drive-low is
`oe = 1`; release is `oe = 0`, and the external pull-up makes the line high. The dead `_o` port is
kept anyway for pad-ring symmetry with GPIO, and documented as such.

The wired-AND is modelled **in the testbench, not the RTL**: the cocotb slave BFM computes
`sda_bus = (oe ? o : 1) & slave_drive` and drives `i2c_sda_i`. The pad-ring contract — open-drain
buffers plus external pull-ups — goes in the module header **and** `docs/design/MEMORY_MAP.md`, so
it cannot be lost at integration.

Both `_i` signals are asynchronous and **single-bit**, so two separate
`cdc_2ff_sync #(.WIDTH(1))` instances are correct and the multi-bit prohibition does not apply.

⚠️ The bit-timing FSM must sample the **synchronised** SCL, and the minimum `I2C_CLKDIV` must
exceed the 2-cycle synchroniser latency. This is the identical lesson already recorded at
`rtl/periph/spi_controller.sv:28-33` (`SPI_CLK_DIV >= 7` for a real external slave; 0 or 1 is
unsafe). It needs an explicit elaboration or runtime guard here, not merely a comment.

#### L2 testability

Add an internal loopback / self-test mode, following the `SPI_CTRL[4]` loopback precedent, folding
`*_oe_o` back to `*_i` through a simple internal ACKing slave model. At the SoC suites'
`CLK_PERIOD_NS = 2`, driving a full protocol BFM over thousands of cycles is expensive and
brittle — so keep full protocol coverage at L1 with the real BFM, and prove the *fabric path* at
L2 cheaply through loopback.

| Offset | Name | Access | Description |
|:------:|:-----|:------:|:------------|
| 0x000 | I2C_CTRL | RW | `[0]` enable, `[1]` loopback, `[2]` IRQ enable, `[3]` ACK-on-read |
| 0x004 | I2C_STATUS | RO | `[0]` busy, `[1]` done, `[2]` NACK, `[3]` arb_lost, `[4]` timeout — sticky |
| 0x008 | I2C_CLKDIV | RW | `[15:0]` SCL half-period divider; guarded minimum |
| 0x00C | I2C_ADDR | RW | `[6:0]` slave address, `[7]` R/W direction |
| 0x010 | I2C_TX_DATA | WO | Push a byte to the TX FIFO (write-snoop); reads 0 |
| 0x014 | I2C_RX_DATA | RO | Pop a byte from the RX FIFO (read-snoop) |
| 0x018 | I2C_CMD | WO | `[0]` START, `[1]` STOP, `[2]` repeated-START, `[3]` read-N (snoop pulse) |
| 0x01C | I2C_FIFO_STAT | RO | TX/RX occupancy and full/empty flags |
| 0x020 | I2C_TIMEOUT | RW | Clock-stretch timeout, in SCL ticks; 0 disables |
| 0x024 | I2C_IRQ_EN | RW | Per-condition IRQ enable (masks `irq_o` only) |
| 0x028 | I2C_IRQ_STAT | RO | Sticky per-condition pending |
| 0x02C | I2C_IRQ_CLR | WO | W1C against `I2C_IRQ_STAT`; reads 0 |

`N_REGS = 12`.

**New shared deliverable:** `tb/cocotb/bfm/i2c_slave.py`, alongside the existing
`tb/cocotb/bfm/apb4_master.py`.

### 6b — CRYPTO (`rtl/periph/crypto_accel.sv` + `aes128_core.sv` + `sha256_core.sv`)

**Two cores, one wrapper, one APB slot**, with `parameter bit EN_AES = 1, EN_SHA = 1` generate
guards so a PD run can drop one core. This halves interconnect churn and IRQ budget against
shipping them as two peripherals.

**AES-128: encrypt-only datapath, exposing ECB *and* CTR.** CTR turns an encrypt-only core into a
complete cipher in both directions, whereas a decrypt datapath needs a separate inverse S-box and
inverse key schedule — very nearly a second core. Architecture: iterative, 128-bit datapath, 16
parallel S-boxes, one round per cycle → **11 cycles/block**, beating the roadmap's 100-cycle
projection.

⚠️ **Area risk is real** (16 × 256×8 lookup). Hold **fold to 4 S-boxes / 4 cycles per round** as a
pre-documented fallback, so that if Gate A (§8) says it does not fit, the response is a parameter
change rather than a redesign.

**SHA-256:** single block-compress core, 64 rounds at one per cycle, 16 × 32-bit rolling message
schedule. **Padding and message length are software's responsibility**, per the standard.

**Key handling.** Keys live in a **shadow register outside the bank**, loaded by APB write-snoop on
`KEY0-3`, with the bank's KEY words at `WMASK = 0` and never HW-written so they read 0 forever
(§3, pattern 3). Additionally, **key writes are rejected while `STATUS.busy`** — also dynamic
protection the bank cannot express, hence also a shadow-side check.

| Offset | Name | Access | Description |
|:------:|:-----|:------:|:------------|
| 0x000 | CRYPTO_CTRL | RW | `[1:0]` mode (0 ECB, 1 CTR, 2 SHA, 3 reserved), `[2]` start (**W1P, reads 0**), `[3]` IRQ enable, `[4]` SHA_CONT |
| 0x004 | CRYPTO_STATUS | RO | `[0]` busy, `[1]` done, `[2]` key_valid, `[3]` key_write_rejected |
| 0x008-0x014 | CRYPTO_KEY0-3 | WO | AES-128 key, shadow-registered; **always reads 0** |
| 0x018-0x024 | CRYPTO_IV0-3 | RW | CBC IV / CTR counter block |
| 0x028-0x034 | CRYPTO_DIN0-3 | WO | **4-word aperture onto one 512-bit shift register**; write-snoop push, order is the contract |
| 0x038-0x044 | CRYPTO_DOUT0-3 | RO | Output block |
| 0x048-0x064 | CRYPTO_DIGEST0-7 | RO | SHA-256 digest |
| 0x068 | CRYPTO_IRQ_STAT | RO | Sticky done |
| 0x06C | CRYPTO_IRQ_CLR | WO | W1C; reads 0. `[0]` clears sticky done, `[1]` clears `STATUS.key_write_rejected` |

`N_REGS = 32` (one 128-byte window; remainder reserved). A power-of-two `N_REGS` is fine —
`apb4_register_bank.sv:66`'s `IDXW` idiom already handles it, and GPIO proves the `N_REGS = 8`
case.

**Golden models, with no new pip dependency:** `hashlib.sha256` from the standard library for SHA;
FIPS-197 Appendix B and C known-answer vectors hardcoded, plus a new `tb/models/aes128_model.py`
for the CTR cross-check. This mirrors `tb/models/rv32i_model.py` and leaves `requirements.txt`
untouched.

⚠️ **Mandatory `security-reviewer` pass**, and the module header must state the non-goals outright:
**no side-channel or DPA resistance, no fault-injection hardening, not certified, not validated
against any scheme.** Without that, someone will eventually treat this as production crypto.

**Register-map corrections (2026-10-03, bead `f7vs.10` microarchitecture review).** Four entries in
the table above are not implementable against `apb4_register_bank`'s actual semantics as literally
written. All four resolutions stay inside fields the table left reserved, so none of them changes
the address map, the slot, the IRQ bit or `N_REGS`:

1. **`CTRL[2]` start cannot be a stored RW bit.** Clearing it with a same-cycle `hw_wen` writeback
   is exactly the "one-cycle window in which the protected value is wrong" failure of §3
   consequence 1 — and the collision rule makes the SW `1` beat the HW clear anyway
   (`apb4_register_bank.sv:91-118`). It is therefore **masked out of `WMASK` and decoded as a
   write-snoop pulse**: W1P, reads 0 forever, self-clearing by construction with no window.
2. **DIN cannot hold a SHA block.** SHA-256 needs 512 bits and the map provides four words, so
   `DIN0-3` are a **4-word aperture onto a single 512-bit shift register**: which of the four
   addresses is written is irrelevant, the **write order** is the contract (16 words for SHA, 4 for
   AES, most-significant first). A partial-strobe write is dropped, and pushes are rejected while
   busy because CTR consumes the plaintext at the *completion* edge.
3. **Multi-block SHA chaining was impossible as specified** — `DIGEST0-7` are RO and no `H` input
   register exists, so software had no way to supply the chaining value. Resolved with
   **`CTRL[4] = SHA_CONT`** (0 = start from the FIPS-180-4 `H0` constants, 1 = continue from the
   current `DIGEST` contents). Because the `DIGEST` words are `WMASK = 0` and HW-written only, they
   *are* the chain register — `DIGEST` stays RO exactly as the table says and no 256-bit register is
   added. Making `DIGEST` RW was rejected: it contradicts a stated access type and lets a stray
   store corrupt a hash in progress.
4. **`STATUS[3] key_write_rejected` had no documented clear.** It clears on reset, on `IRQ_CLR[1]`,
   and on an accepted key write, so the natural recovery sequence (see rejected → wait idle →
   rewrite the key) needs no extra register access.

Also recorded rather than left implicit: **`STATUS[1] done` and `IRQ_STAT[0]` are the same flop**
mirrored into two words (the `i2c_controller.sv:680-695` pattern), not two pieces of state; and
**`IV` is the one register whose busy-time protection cannot be enforced** — it lives inside the
bank, so unlike KEY and DIN there is no shadow-side check to add, and writing it mid-operation
corrupts the CTR counter. That is software's responsibility and is documented as such, which
satisfies §3's review-checklist item because nothing claims the bank enforces it.

**Acceptance criteria** (bead `f7vs.10`; this list is what the PR is reviewed against):

1. **No new runtime-indexed mux**, the same explicit criterion 6c carries below. The AES S-box is a
   constant-index `case`/ROM, the SHA-256 `K` table a constant-index lookup, and the message
   schedule a shift register — so the proven Synlig `OPT_MUXTREE` miscompile class (bead `ma7`) is
   side-stepped by construction rather than by luck. An RTL-review gate.
2. **ECB bit-exact against the FIPS-197 Appendix B and C known-answer vectors**, asserted both in
   `tb/models/aes128_model.py`'s own `selftest()` and again in the cocotb suite — the double-pin
   `tb/models/trng_lfsr_model.py` / `test_trng.py:787` established, so a silent model edit cannot
   move the target the suite chases.
3. **CTR round-trip bit-exact**: encrypting a block and then re-running the ciphertext through the
   same keystream returns the plaintext, cross-checked against the model. This is what makes an
   encrypt-only datapath a complete cipher in both directions.
4. **SHA-256 digests bit-exact against `hashlib.sha256`** over multiple chained blocks, with
   padding and message length supplied by the testbench (software's job, per the standard).
5. **`KEY0-3` read 0 forever** — bank words at `WMASK = 32'h0` and never HW-written — and a key
   write attempted while `STATUS.busy` is rejected and latches `STATUS[3]`.
6. **`irq_o` is level-held**, `IRQ_STAT.done` is sticky with set winning over a same-cycle
   `IRQ_CLR` W1C, and `IRQ_STAT` is HW-written with the next-state value so a read one transfer
   after completion is not stale.
7. **Both generate arms elaborate and lint clean**: `EN_AES = 0` and `EN_SHA = 0` each build, and a
   mode selecting an absent core reports cleanly instead of hanging the FSM.
8. **Gate A (§8) has been run and its cell count / area recorded in the bead**, with
   `SBOX_PARALLEL` set from that measurement rather than assumed.
9. **`security-reviewer` has passed** and the module header carries the non-goals paragraph above.

### 6c — NPU (`rtl/npu/npu_top.sv`, `npu_mac_array.sv`, `npu_weight_mem.sv`)

**Hand RTL, not HLS.** `docs/CPP_TO_RTL_HLS_EVALUATION.md:14-18` does name the Phase 6 INT8 NPU as
an HLS target, but the same document records (a) the **proven** Synlig `OPT_MUXTREE` miscompile of
runtime-indexed muxes that corrupted the CPU's branch comparator through the regfile read ports
(bead `ma7`), and (b) that the `USE_SYNLIG:false` + sv2v remedy measurably worsened `valu_hls` PPA
and left the CPU macro stuck in a 108716-DRC routing regression (bead `lxv`). Adding a second
netlist provenance to a systolic array — the structure dataflow HLS expresses worst without heavy
pragmas — buys nothing at 4×4, which is roughly 120 lines of genvar-nested RTL. **Keep the Python
golden model** (`tb/models/npu_model.py`); that is the real value HLS was proxying for.

**Acceptance criterion, explicit: the NPU introduces no new runtime-indexed mux.** The systolic
grid is genvar-structural, the weight address goes to an SRAM macro rather than a mux, and the only
read multiplexer is `apb4_register_bank`'s, which is already present in every netlist. This is an
RTL-review gate, so the `ma7` defect class is sidestepped by construction rather than by luck.

**Bus face:** APB4, a single 4 KB slot, **no memory-mapped SRAM aperture**. Weights arrive via
`NPU_WADDR` (auto-incrementing) plus `NPU_WDATA` pushes; activations via an `NPU_AIN` FIFO; results
leave via `NPU_AOUT` pops. This keeps the 4 KB-per-slot uniformity and avoids both a 16 KB window
and a new crossbar slave.

**Weight SRAM: `parameter WEIGHT_WORDS = 1024` (4 KB) by default, not 16 KB.** 4 KB is *exactly
one* `sky130_sram_4kbyte_1rw1r_32x1024_8` — a macro already in this flow with a proven stub, LEF,
`macro_placement.cfg` entry and `PDN_MACRO_CONNECTIONS` pattern. 16 KB is four macros, new
placement work, and 4× the OOM exposure on a host that already OOM-kills GPU PD. A 4×4 INT8 array
at 40 MHz cannot stream 16 KB fast enough for the extra capacity to be measurable, and
keyword-spotting demos fit in 4 KB. **16 KB remains a parameter bump, not a redesign.** SRAM
instantiation reuses the per-PDK `ifdef` wrapper pattern verbatim from
`rtl/mem/rv32i_icache.sv:99-117`.

**Dataflow:** weight-stationary 4×4 INT8 grid, INT8 × INT8 → INT32 accumulators, plus a **shared
requantize stage** (×16-bit scale, right shift, saturate to INT8, optional ReLU, one output per
cycle drain). Without requantization it is a MAC array, not an NPU.

**Escape hatch:** `parameter bit EN_NPU` plus a generate guard, so the Sky130 SoC config can tie it
off exactly as `pnr/sky130/soc/gpu_top_tieoff.sv` does for the GPU. If Gate A says it does not fit,
that is a config change rather than a rewrite.

**Non-goals:** INT4, sparsity, tiling, the 16 KB weight SRAM, keyword-spotting demo firmware, and
an L3 software driver.

#### Register map — NPU, base `0x2001_0000`, `N_REGS = 16`, `ADDR_W = 12`

PIO only: **no memory-mapped SRAM aperture**, same philosophy as CRYPTO. The weight SRAM is
reachable exclusively through `WADDR`/`WDATA`.

| Off | Name | Access | Contents |
|:----|:-----|:-------|:---------|
| `0x00` | `CTRL` | RW + W1P | `[0]` `RELU_EN`; `[2]` `START` (**W1P, reads 0** — decoded as a write-snoop pulse); `[3]` `IRQ_EN` |
| `0x04` | `STATUS` | RO, live mirror | `[0]` `busy`, `[1]` `done`, `[2]` `ain_full`, `[3]` `ain_empty`, `[4]` `aout_valid`, `[5]` `aout_full`, `[6]` `cfg_rejected` (sticky) |
| `0x08` | `WADDR` | RW | `[9:0]` weight-SRAM word address; **auto-increments on every `WDATA` write** |
| `0x0C` | `WDATA` | WO (snoop) | 4 packed INT8 weights → SRAM`[WADDR]`. Reads 0 forever |
| `0x10` | `TILEBASE` | RW | `[9:0]` SRAM word address of the first weight word of the next inference |
| `0x14` | `KLEN` | RW | `[5:0]` number of 4-element chunks, **1..63** (see below). Each chunk consumes 4 SRAM words + 1 `AIN` word |
| `0x18` | `SCALE` | RW | `[15:0]` requantize multiplier, `[20:16]` right shift |
| `0x1C` | `AIN` | WO (snoop) | 4 packed INT8 activations → AIN FIFO. Reads 0 forever |
| `0x20` | `AOUT` | RO + pop-on-read | Live mirror of the AOUT FIFO head (4 packed INT8 results). **A read pops** |
| `0x24` | `IRQ_STAT` | RO, sticky | `[0]` `done` |
| `0x28` | `IRQ_CLR` | WO W1C (snoop) | `[0]` clears `done`; `[1]` clears `cfg_rejected` |
| `0x2C`–`0x3C` | *reserved* | RO 0 | `WMASK = 0` and never HW-written |

`WMASK`: `CTRL` = `32'h0000_0009` — **bit 2 is masked out**, because a stored `START` cleared by a
same-cycle `hw_wen` is exactly the §3 one-cycle window, and the bead-`6o8w` collision rule would
let a software `1` beat the hardware clear. `WADDR`/`TILEBASE` = `32'h0000_03FF`, `KLEN` =
`32'h0000_003F`, `SCALE` = `32'h001F_FFFF`; every other word is `32'h0000_0000`.

`hw_wen` discipline follows `crypto_accel.sv:71-79`: **always-1 = live mirror** (`STATUS`, `AOUT`,
`IRQ_STAT`); **pulse = the bank word *is* the storage element** (`WADDR` auto-increment). So, as
with CRYPTO, the NPU has **no result register of its own** — the bank word is the result register.

**Dataflow, concretely.** `y[j] = requant(Σ_chunks Σ_{i=0..3} W[chunk][i][j] × a[chunk][i])` for
`j = 0..3`. One chunk = one `AIN` word (4 INT8 activations) plus 4 consecutive SRAM words (the
4×4 INT8 weight tile, one word per row). `TILEBASE` is the first tile's word address and advances
by 4 per chunk; the 4 INT32 accumulators are cleared at `START` and accumulate across all `KLEN`
chunks. On the final chunk the shared requantizer drains **one lane per cycle** over 4 cycles,
packs the 4 INT8 results into one word, pushes it to `AOUT`, and sets `done`.

⚠️ **Spec defect found and fixed during step 2 (bead `f7vs.11`): `KLEN` is 1..63, not 1..64.**
A 6-bit field holds 0..63, so a written 64 stores 0, which is an illegal start. The alternative —
encoding `KLEN-1` so the field spans 1..64 — was rejected: it buys one extra chunk, makes `KLEN = 0`
mean "1 chunk" and so destroys the natural illegal-start check, and every driver would have to
remember the bias. 63 chunks is 252 activations against a 4×4 grid, far past anything this block is
for. The field is therefore a plain count with maximum 63.

⚠️ **The weight memory must not hardcode a read latency.** The committed behavioural models
disagree: `sim/sky130_sram_4kbyte_1rw1r_32x1024_8.sv` registers its inputs at `posedge` and reads
at `negedge` (2 edges to a posedge consumer), while `sim/sram_1rw_256x32_verilator.v` — the
FreePDK45 model every default cocotb build uses — reads on the `posedge` itself (1 cycle). The
wrapper must present one timing to `npu_top` across all three arms, so `npu_weight_mem.sv` owns
that normalisation (register the Sky130/ASAP7 `dout` once more, or hold the address an extra cycle)
and `npu_top` must consume a single declared latency. This is exactly the `CS_SRAM_LATCH` problem
`rv32i_icache.sv` already solves for itself.

**Software contract — hard guarantees:**

1. An **illegal `START`** (`KLEN == 0`, or `TILEBASE + 4×KLEN > 1024`) takes a **2-cycle
   zero-length path** that sets `done` with no writeback and latches `STATUS[6]`, so a
   `while (!done);` driver can never hang — but **`done` does not imply valid data**, exactly as
   for CRYPTO.
2. A `WADDR` or `WDATA` write **while `STATUS.busy`** is rejected and latches `STATUS[6]`.
   `STATUS[6]` clears on reset, on `IRQ_CLR[1]`, or on an accepted weight write.
3. `irq_o = done_q & CTRL[3]`, **level-held, never a pulse** — every IRQ crosses
   `core_clk → cpu_core_clk` through a plain `cdc_2ff_sync` in `soc_top.sv`, which can miss a
   pulse. `done_d = (done_q & ~clr) | set`, so a **set beats a same-cycle `IRQ_CLR` W1C** and a
   completion is never lost to a racing clear. `STATUS[1]` and `IRQ_STAT[0]` are the same flop
   mirrored into two words.
4. **No CDC anywhere in this block** — stated on purpose rather than omitted. **No top-level
   pins**: the NPU is register-only, like CRYPTO, so `f7vs.3` correctly pre-allocated none.

#### Weight-SRAM instantiation — 3-way, all-macro

⚠️ Correction to the paragraph above: the `ifdef` *pattern* comes from `rv32i_icache.sv:78-116`,
but that file's Sky130 arm uses the **1 KB** `sky130_sram_1kbyte_1rw1r_32x256_8`. The 4 KB macro
this block wants is the one wired up by `rtl/soc/sram_controller.sv:856-881`.

```systemverilog
`ifdef SRAM_SKY130
    sky130_sram_4kbyte_1rw1r_32x1024_8 u_sram_macro ( /* 1 x 1024x32 */ );
`elsif SRAM_ASAP7
    rv32i_clock_gate u_cg ( ... );                      // per bank, en = !csb0
    sram_1rw_256x32_asap7     u_sram_macro ( /* 4 banks of 256x32 */ );
`else
    sram_1rw_256x32_freepdk45 u_sram_macro ( /* 4 banks of 256x32 */ );
`endif
```

**Every arm is a hard macro; there is no behavioural array in the RTL at all**, so no branch can
infer flops. The `sram_controller.sv` 2-way shape (`ifdef SRAM_SKY130` / `else` flat array) is
deliberately **not** copied: it would give the non-Sky130 nodes a *second* 32 768-flop array on top
of the one bead `rvb` proved makes the ASAP7 post-CTS resizer non-terminating.

Consequences, all verified:

- **No new PD asset.** `MACROS` in `pnr/sky130/soc/config.json:66-73` is keyed by **module**, not
  instance, and the views are committed at `pnr/sky130/soc/macro/` (`.lef`, `.lib` TT_1p8V_25C,
  `.gds`, `.sp`). A second *instance* needs no `MACROS`/`EXTRA_LEFS`/`EXTRA_LIBS`/`EXTRA_GDS_FILES`
  edit. The ASAP7 stub, LEF and LIB are likewise already registered (and until now unused).
- **One Makefile edit is required.** `pnr/Makefile:1549`'s `SOC_SV2V_DEFINES` must gain
  `--define=SRAM_ASAP7`, and the comment at `:1541-1543` ("no file in `SOC_SV_FILES` branches on
  it") must be corrected — the NPU makes it the first file that does. sv2v resolves `ifdef`
  **itself, before Yosys**, so `config.json`'s `VERILOG_DEFINES` is too late: without this edit the
  ASAP7 SoC netlist would instantiate `sram_1rw_256x32_freepdk45`, which has no ASAP7 LEF, and
  would be **silently blackboxed** — unplaced, unconstrained, and invisible to every cocotb suite.
- **Port 0 only**; port 1 is tied off (`csb1=1'b1, addr1='0, dout1=()`) as `rv32i_icache.sv:91-94`
  does, so all three arms present the same single-ported 1024×32 face. **Read latency is 2 clocks**
  on every arm (inputs registered at `posedge`, array accessed at `negedge`), absorbed by a latch
  state the way the icache uses `CS_SRAM_LATCH` + `tag_dout_r`. `USE_POWER_PINS` stays undefined —
  PG comes from the LEF plus `PDN_MACRO_CONNECTIONS`.
- **The macro instance must be named `u_sram_macro`.** `PDN_MACRO_CONNECTIONS`'s second entry is
  the regex `.*u_sram_macro.*`, matched against the leaf instance name, so reusing the name means
  **zero config change**; any other name silently leaves vccd1/vssd1 unconnected, which is the
  PSM-0069 class this flow already fought.
- **Elaboration guard**, mirroring `sram_controller.sv:129-148`: a bare `$fatal` in a generate
  scope (fires under `--lint-only`, unlike `initial $error`) unless `WEIGHT_WORDS == 1024`, so a
  parameter sweep cannot silently fall back to flops.
- **Gate A must be run with `SRAM_SKY130` defined** plus the blackbox stub, or the probe itself
  infers 32 768 flops and reports a meaningless number.

Deferred to **Gate B** (§8), documented here so they are not rediscovered: one new
`macro_placement.cfg` line, whose x/y origins must be exact multiples of **6.9 µm** (the GRT GCell
pitch — the discipline that fixed GRT-0118) and whose dot-separated instance path must be **read
from a `Yosys.Synthesis`-only probe, not guessed**. Free span right of the existing SRAM is
x ∈ [4910.64, 6680], i.e. 1769 µm for a 701.64 × 673.335 µm macro.

#### Behaviours fixed during implementation (step 3)

Not stated in the register map above; chosen by the RTL, ratified here so they are decisions rather
than accidents:

- A result that completes into a **full `AOUT` FIFO is dropped silently** (as an `AIN` write into a
  full FIFO already is, test D-series).
- **Only an accepted `WDATA` write** clears `STATUS[6] cfg_rejected` — an accepted `WADDR` write
  does not.
- **Partial-strobe** `WDATA` and `AIN` writes (`pstrb != 4'hF`) are dropped.
- `SCALE` and `CTRL[0] RELU_EN` are sampled **live during the drain**, not latched at `START`;
  software must not change them while `busy`.
- A `WADDR` write while `busy` is blocked by gating `penable` into the bank for that single
  transfer, because `apb4_register_bank` cannot protect a word dynamically; `WADDR`'s `WMASK`
  therefore stays `32'h0000_03FF` as written.
- **Read latency is 2 cycles on every SRAM arm**, normalised by one capture flop in
  `npu_weight_mem.sv`; `npu_top` depends only on that.

#### Acceptance criteria — 6c NPU

1. **No new runtime-indexed mux**, proven not asserted, on the **coarse-grain** netlist
   (`synth -run :fine`, before `techmap` lowers `$shiftx`/`$pmux` and makes any count read zero):
   **zero `$shiftx`, zero `$pmux`, zero `$mem*` in the three `rtl/npu` modules** when synthesised
   *without* `-flatten`. The flat count is not the criterion and cannot be 0 — `apb4_register_bank`
   contributes 4 `$shiftx` + 2 `$shift` of its own and is already in every netlist. Note also that a
   constant-label `case` is **not** sufficient — yosys `proc` turns every `case` into a `$pmux` — so
   the runtime selects use 2:1 ternary trees and one-hot AND-OR instead. The grid is genvar
   structural, the requantizer's lane select and the non-Sky130 banks' read mux are
   constant-label `case`, the AIN/AOUT FIFOs are **depth-4 positional shift registers** (a
   pointer-indexed FIFO is `array[runtime_ptr]`, precisely the `ma7` idiom), and the only read
   multiplexer is `apb4_register_bank`'s, already in every netlist.
2. **`tb/models/npu_model.py` exists**, standard-library only with `requirements.txt` untouched,
   models the arithmetic and not the handshake, has an explicit byte-order and saturation
   contract, and carries its own pytest self-test under `tb/tests/`.
3. **Both generate arms elaborate and lint clean**: `EN_NPU = 0` builds and constant-folds away.
4. **All three SRAM arms elaborate**: `make -C sim lint_soc` (FreePDK45) and
   `make -C sim lint_soc_sky130` (`SRAM_SKY130`, the 4 KB macro) are both clean, and both
   `sky130-soc-sv2v` and `asap7-soc-sv2v` regenerate with the NPU present and the *right* SRAM
   module instantiated in each.
5. **`irq_o` is level-held** and `IRQ_STAT.done` is sticky with set winning over a same-cycle
   `IRQ_CLR`; the SoC test proves `irq_src_i == npu_irq << 11` **exclusively**, per cycle.
6. **An illegal `START` cannot hang the bus** — the 2-cycle zero-length path is tested directly.
7. **Gate A (§8) has been run** with `SRAM_SKY130` defined, and its cell count / area / % of SoC /
   setup slack at ss are recorded in bead `f7vs.11`.
8. **A mutation campaign has run** on the RTL, as `f7vs.10` did, with every survivor shown to be
   provably equivalent.

---

## 8. Physical design — two gates, not one

Per-item PD is **out of scope**. But a single batched harden after all six items risks discovering
at the very end that crypto or the NPU does not fit `DIE_AREA [0,0,6700,3100]` at
`CLOCK_PERIOD 25.0`. So:

### Gate A — per-item synthesis probe (not physical design)

After each item's RTL lands, run a **synthesis-only** area / cell-count / critical-path estimate
via `chip-design-synthesis:logic-synthesis` — yosys plus the Sky130 liberty, with **no** floorplan,
placement, routing or RCX. Minutes, not hours.

This is the highest-value risk control in the phase: it catches "the 16-parallel-S-box AES is 40 %
of the SoC" while the fold-to-4 fallback is still a cheap parameter change, instead of after five
more items have piled on top. Record the cell delta in the item's bead.

#### Gate A results — CRYPTO, 2026-10-03 (bead `f7vs.10`)

First Gate A probe actually run (it was skipped for PWM/WDT/TRNG/I2C — bead `f7vs.13`). Method:
`sv2v` + `yosys` from the cache `tools/cdc/fetch_cdc_tools.sh` already populates under
`sim/build/cdc/`, mapped to `sky130_fd_sc_hd__tt_025C_1v80.lib`, plus OpenSTA at the SoC's real
`CLOCK_PERIOD 25.0`. No floorplan, placement, routing, RCX or PDN.

| Configuration | Cells | Area µm² | % of SoC stdcell ⚠️ **wrong ~10×, see correction below** | Setup slack @ ss |
|:--------------|------:|---------:|-----------------:|-----------------:|
| `crypto_accel`, `SBOX_PARALLEL=16` (default) | 24 227 | 277 875 | **3.59 %** | **+14.042 ns MET** |
| `crypto_accel`, `SBOX_PARALLEL=4` (fallback) | 20 569 | 237 279 | 3.06 % | +14.098 ns MET |
| `crypto_accel`, 16, datapath resets dropped | 23 074 | 265 814 | 3.43 % | — |
| `aes128_core` @16 | — | 130 320 | 1.68 % | +17.332 ns MET |
| `aes128_core` @4 | 6 411 | 69 555 | 0.90 % | +17.457 ns MET |
| `sha256_core` | 8 033 | 88 232 | 1.14 % | +14.065 ns MET |
| `apb4_register_bank` alone | 7 562 | 88 126 | 1.14 % | — |

Denominator is the Sky130 SoC's own `design__instance__area` = **7 744 600 µm²** at ~38 %
utilisation (run `RUN_2026-09-26_07-34-03`), *not* the die area. Flop count 3 168
(`dfxtp_2`).

**Decision: `SBOX_PARALLEL` stays 16.** This gate exists to catch the case quoted above — "the
16-parallel-S-box AES is 40 % of the SoC". It is **3.59 %**, an order of magnitude away. Folding to
4 would save 40 596 µm², which is **0.52 percentage points** of the SoC, gain nothing in timing
(+14.098 vs +14.042 ns at ss is noise), and cost 3.7× the AES latency (11 → 41 cycles/block). The
pre-documented fallback therefore stays documented and unused, still a one-parameter change if a
future floorplan ever needs it. The datapath-reset lever would save a further 0.16 pp and is also
not taken: X-free deterministic reset is worth more than that.

⚠️ These are **pre-layout** numbers by design — the slack is against estimated, not extracted,
parasitics. 14 ns of margin on a 25 ns period is wide for a block this size, but Gate B remains the
real physical gate.

#### ⚠️ Correction — the CRYPTO denominator above was stdcell **plus macro** area (found 2026-10-04, bead `f7vs.11`)

`design__instance__area` is **not** a stdcell figure. Read from the same run's own metrics
(`RUN_2026-09-26_07-34-03`, final stage `62-misc-reportmanufacturability`):

| Metric | µm² |
|:-------|----:|
| `design__instance__area` (final) | 7 945 080 |
| `design__instance__area__stdcell` | **992 638** |
| `design__instance__area__macros` | 6 952 440 (CPU macro + the 4 KB SRAM) |
| `design__core__area` | 20 359 700 |

The 7 744 600 used above is the same sum at the post-tap stage (792 157 stdcell + 6 952 440
macro). Hard macros are **88 %** of it, so every "% of SoC stdcell" in the CRYPTO table is
understated roughly **10×**. Restated against stdcell alone, `crypto_accel` at
`SBOX_PARALLEL=16` is **~28 %** of the final stdcell area (35 % of the post-tap figure), not 3.59 %.

**The decision survives; its stated reason does not.** "An order of magnitude away from 40 %" was
false. What actually decides fit on a macro-dominated die is **core utilisation**, and that is
comfortable: the run sits at 7 945 080 / 20 359 700 = **39.0 %**, and adding CRYPTO (277 875) plus
the NPU's stdcells (203 179) and its 4 KB macro (472 439) gives ~8 899 000 = **~43.7 %**. The
fold-to-4 fallback would save 40 596 µm² = **0.2 pp of core utilisation**, still nowhere near worth
3.7× the AES latency. `SBOX_PARALLEL` stays 16.

What the corrected number *does* change: Phase 6b + 6c together grow the SoC's **stdcell** logic by
~**48 %** (992 638 → ~1 474 000), all in the `core_clk` domain. That is the honest input to Gate B,
in particular to bead `e45j`'s post-RCX slew/cap counts, which scale with stdcell count and net
length rather than with die utilisation.

#### Gate A results — NPU, 2026-10-04 (bead `f7vs.11`; discharges `f7vs.13`'s NPU obligation)

Same tools as CRYPTO, plus one method fix: synthesis mirrors the SoC flow's own
`04-yosys-synthesis` step — its `no_synth.cells` exclusions plus `*lpflow*`/`*edfxtp*`, the run's
`DELAY_0.abc` script and `synthesis.abc.sdc`, `-D 25000`. **The OOM guard was checked before any
number was read**: sv2v with `--define=SRAM_SKY130`, the `(* blackbox *)` stub read first, and the
mapped netlist contains **exactly 1** `sky130_sram_4kbyte_1rw1r_32x1024_8` and **1 105 flops** —
not ~33 000. Stdcells at ss (`sky130_fd_sc_hd__ss_100C_1v60`), macro timing from its TT-only
`.lib` (the single-corner limitation of bead `o1i`).

| Configuration | Cells | Stdcell µm² | Flops | % of final SoC stdcell (992 638) | Setup slack @ ss, 25 ns |
|:--------------|------:|------------:|------:|------:|-----------------:|
| `npu_top`, flow-faithful mapping (**primary**) | 19 603 | **203 179** | 1 105 | **20.5 %** | **+1.841 ns MET** |
| `npu_top`, plain `abc -liberty`, no exclusions | 12 641 | 109 803 | 1 105 | 11.1 % | −5.013 ns VIOLATED |
| `npu_top`, plain + `*lpflow*` excluded | 12 660 | 110 569 | 1 105 | 11.1 % | −5.280 ns VIOLATED |
| `npu_top`, `EN_NPU = 0` | 2 (`conb_1`) | 7.5 | 0 | ~0 % | — |
| 4 KB weight-SRAM macro (separate, from the LEF) | 1 | 472 439 | — | *(macro, not stdcell)* | — |

Hierarchical breakdown (unflattened, so its 225 k total exceeds the flat 203 k): `npu_mac_array`
137 881, `npu_top` remainder (requantizer, FIFOs, control) 58 261, `apb4_register_bank` 28 388,
`npu_weight_mem` 848.

**Critical path — the MAC array, not the requantizer.** `ain_q[0][8]` (AIN FIFO head, a
fanout-129 unbuffered launch flop, 2.847 ns clk→Q) → INT8 multiply → column adder tree → 32-bit
accumulate → `acc_w[31]`, all in one cycle: arrival 22.177 ns vs. required 24.018 ns. The
requantizer's 16×32 → 49-bit multiply has +5.888 ns; every other endpoint group is above +4.5 ns.

**Decision: ship as is, and name the Gate B watch item.** +1.84 ns pre-layout is thin next to
CRYPTO's +14, and the two plain-mapping rows show the slack depends heavily on ABC restructuring
the ripple-carry chains (~35 `maj3_1` in series otherwise). Two reasons it is still acceptable now:
the primary row uses the SoC flow's own synthesis recipe, so it is the one Gate B will actually
see; and the fanout-129 launch flop is exactly what placement-stage repair buffers. **If Gate B goes
negative here**, the pre-identified fallback is to register the column sums before the accumulate —
4 × 18 flops and one cycle of latency, no interface change. Not taken pre-emptively, because Gate A
cannot price it against real wires.

⚠️ CRYPTO's +14.042 ns did not record its ABC recipe, so it is **not** directly comparable with
the NPU's primary row: the same NPU netlist moves from +1.8 ns to −5.0 ns on recipe alone.
Future Gate A probes should use the flow-faithful recipe above and state it.

Reproduction: `sv2v --define=__pnr__ --define=SRAM_SKY130` over the blackbox stub,
`rv32i_clock_gate.sv`, `apb4_register_bank.sv` and the three `rtl/npu` files; yosys
`synth -flatten -top npu_top; dfflibmap; abc -script DELAY_0.abc -constr synthesis.abc.sdc
-D 25000` with the exclusions above; OpenSTA 2.7.0 against the ss liberty plus the macro `.lib`,
25.0 ns ideal clock, 0.300/0.150 ns setup/hold uncertainty, 20 %/5 % I/O delays, mirroring
`pnr/sky130/soc/constraints/`.

### Gate B — one batched Sky130 harden after all six land

Via `chip-design-pd:physical-design-orchestrator`, using `make librelane-sky130-soc-noklayout`
(KLayout DRC peaks at 8.5 GB and sits before Netgen LVS in LibreLane's Classic flow, so on this
~15 GB host the full target loses LVS — the most important physical gate this node has).

Expect: a possible `DIE_AREA` bump; validation of the G3-pre-added `set_false_path` lines against
real ports; a new `macro_placement.cfg` entry if the NPU weight SRAM is a macro; and a
re-measurement of bead `e45j`'s post-RCX slew/cap counts.

⚠️ **`e45j` will get worse with every peripheral added** — 8357 max-slew / 329 max-cap today, with
both checkers `--skip`-ped and no post-RCX repair stage existing in LibreLane. Gate B records the
new numbers. **Closing `e45j` is explicitly not a Phase 6 exit criterion**, but shipping six more
peripherals on top of skipped checkers without a number is not acceptable either.

### ASAP7 is out of scope for all of Phase 6

Triple-blocked: bead `ma7` (proven Synlig `OPT_MUXTREE` miscompile; the macro views in
`pnr/asap7/soc/macro/` are still the old corrupt ones), bead `lxv` (108716-DRC routing congestion
regression against a 2045-violation best-ever baseline), and bead `2kn` (needs ≥32 GB; this host
has ~15 GB). **No item's DoD may include an ASAP7 run.**

Every new peripheral nevertheless goes into the ASAP7 sv2v list at `pnr/Makefile:1471`, enforced by
the G4 checker, so eventual unblocking is a re-run rather than a porting exercise.

Bead `8qn4` item 3 (the ASAP7 SoC has never been run with GPIO) is unresolvable inside Phase 6 and
is re-scoped onto the `ma7`/`lxv`/`2kn` chain rather than counted against these items.

---

## 9. Per-item workflow and acceptance criteria

**Definition of done, per item: RTL + cocotb verification + SoC integration.** Physical design is
excluded (§8).

TDD is mandatory and the ordering is explicit: **the verification orchestrator runs before the RTL
orchestrator.** Step 2's tests must exist and fail — or fail to elaborate — before step 3 writes
the module.

| Step | Owner | Deliverables |
|:----:|:------|:-------------|
| 1 | *(plan edit)* | Register map + acceptance criteria appended here. Slot, IRQ bit and pins already reserved by G2/G3 |
| 2 | `chip-design-verification:verification-orchestrator` | `tb/cocotb/soc/tb_<name>.sv` wrapper; `test_<name>.py` (`CLK_PERIOD_NS = 10`, `bfm/apb4_master.py`, `_peek()`, `_kill_active_tasks()`); any new BFM or golden model; Makefile source list, `<name>_lint` and `<name>` targets (both with `-Wno-SYNCASYNCNET`); `.PHONY` entry |
| 3 | `chip-design-rtl:rtl-design-orchestrator` | `rtl/periph/<name>.sv` per the mechanical checklist (§10). `verilator -Wall -Wno-IMPORTSTAR` clean, 0 errors 0 warnings. L1 green |
| 4 | `chip-design-soc:soc-integration` | `APB_<NAME>` index, `APB_N_SLAVES`++, both array literal appends; `soc_bus.sv` comments; `soc_top.sv` instantiation, replacing the G3 port tie and the G2 `1'b0` IRQ tie; `interrupt_controller.sv` header; all five file lists; G4 checker green |
| 5 | `verification-orchestrator` | `test_soc_<name>.py` on `tb_soc_top` (`CLK_PERIOD_NS = 2`, reusing `SOC_BOOT_SOURCES`); firmware from a committed pure-Python generator in `<name>_fw/gen_<name>_hex.py` emitting the hex plus an `addrs.py` of marker PCs (the `gpio_fw` pattern). **CI-safe** → belongs in `soc_all_ci` |
| 6 | `chip-design-firmware:firmware-orchestrator` *(selected items)* | `sw/drivers/<name>.h`, header-only, all `static inline`; `sw/bench/<name>_demo.c`; `test_<name>_driver.py` scoreboarding against `.sym` markers. **`soc_all` only, never `soc_all_ci`** |
| 7 | *(close-out)* | `MEMORY_MAP.md`, `CLAUDE.md`, `ROADMAP.md`, `PHASE_STATUS.md`, `README.md`; `soc_all_ci` from clean; raise `PASS_FLOOR` to the **measured** number |

L3 drivers are **outside the chosen DoD** for this phase. When they are scheduled, prioritise I2C
and CRYPTO — they are what firmware actually drives, and a compiled-C system test is genuinely
different evidence. Skip TRNG (a single register read; fold it into another demo) and the NPU (a
keyword-spotting model plus quantization pipeline is a project of its own).

### Expected test counts and `PASS_FLOOR` trajectory

Estimates only — **measure, then raise the floor**.

| Item | L1 | L2 | CI-safe added | Cumulative `PASS_FLOOR` |
|:-----|:--:|:--:|:-------------:|:-----------------------:|
| *(today)* | — | — | — | 215 (218 passing / 28 suites) |
| G2 + G4 | ~10 | ~1 | ~11 | ~226 |
| PWM | ~14 | ~3 | ~17 | ~243 |
| WDT | ~16 | ~3 | ~19 | ~262 |
| TRNG | ~12 | ~2 | ~14 | ~276 |
| I2C | ~22 | ~3 | ~25 | ~301 |
| CRYPTO | ~28 | ~3 | ~31 | ~332 |
| NPU | ~18 | ~3 | ~21 | ~353 |

---

## 10. Mechanical checklist — adding an APB4 peripheral

Derived from the Phase 6a GPIO landing (bead `ckc`, PR #185). Reuse it rather than rediscovering
it. After groundwork G2/G3, items 4, 5, 11 and parts of 7 are already done for every peripheral.

1. **`rtl/periph/<name>.sv`** — module per the GPIO skeleton: ~80-line header comment block with
   the register map, CDC rationale, IRQ level-hold rationale, reset convention, APB4 phase
   contract, and a closing `// Lint target:` line.
2. **Async inputs** → *N* separate `cdc_2ff_sync #(.WIDTH(1))` in a genvar loop, **never** one wide
   instance (the primitive's own scope warning forbids multi-bit binary buses, because bits resolve
   metastability on different edges and produce a word no source cycle ever drove). A genuinely
   coherent async word needs `cdc_gray_fifo` / `async_axi_fifo` instead.
3. **`irq_o` level-held, never a pulse** (`rtl/soc/soc_top.sv:637-644`). W1C clears via APB
   write-snoop (`gpio_controller.sv:281-301`), not via WMASK.
4. **`rtl/soc/soc_periph_map_pkg.sv`** — header prose `:4-25`; new `APB_<NAME>` index after `:78`;
   `APB_N_SLAVES` `:80`; BASE/LIMIT pair after `:101`; both unpacked arrays `:104-109`.
   *(`AXIL_APB_LIMIT` `:52` is pre-set by G2.)*
5. **`rtl/soc/soc_addr_map_pkg.sv`** — header prose `:11-12`. *(`PERIPH_LIMIT` `:50` pre-set by G2.)*
6. **`rtl/soc/soc_bus.sv`** — comments only (`:9`, `:188-189`, `:207`, `:646-648`); the ports are
   already `[APB_N_SLAVES]` arrays.
7. **`rtl/soc/soc_top.sv`** — header `:20-31` and `:147`; instantiation after `:1702`; replace the
   G3 port tie and the G2 `1'b0` IRQ tie; `interrupt_controller` comment `:1706-1708`.
   ⚠️ A new `logic` declaration must sit after `:625` and **before** `u_ext_irq_sync` at `:637`
   (yosys-slang strict mode, bead `q7n`) — pre-done by G2.
8. **`rtl/periph/interrupt_controller.sv`** — header comment `:11-12` only; the module is fully
   parameterised.
9. **`rtl/soc/apb_interconnect.sv`** — **no edit.** `SEL_W = $clog2(N+1)` /
   `IDXW = (N>1) ? $clog2(N) : 1`, with the response mux sliced to `sel_idx[IDXW-1:0]`, is correct
   at every `N` (verified 7-17). The historical `WIDTHTRUNC` at `N = 8` was fixed generally, not
   for that value.
10. **File lists — five of them.** `tb/cocotb/soc/Makefile` (`:252` and `:322`), `sim/Makefile:369`,
    `pnr/Makefile:754` (`SKY130_SOC_SV_FILES`) **and** `pnr/Makefile:1471` (ASAP7 sv2v),
    `tb/cocotb/soc/tb_soc_top.sv`. ⚠️ **sv2v silently blackboxes a missing module and cocotb can
    never catch it** — this is what the G4 checker exists to prevent.
11. **`pnr/sky130/soc/constraints/sky130_soc.sdc:312-322`** — `set_false_path -from [get_ports …]`
    for async top-level inputs. This closed the last 3 Sky130 hold violations in bead `00ef`.
    *(Pre-added by G3.)*
12. **`docs/design/MEMORY_MAP.md`** — global table `:24-43`; ring prose `:45-54`; a new register
    table modelled on GPIO's `:282-314`; interrupt hierarchy `:395-406`.
13. **Docs** — `CLAUDE.md` (GPIO's consolidated paragraph is item 13), `docs/ROADMAP.md:405-427`,
    `docs/PHASE_STATUS.md`, `README.md`.
14. **Suite registration** — `.PHONY` at `tb/cocotb/soc/Makefile:452`; `soc_all_ci` `:931-957`;
    `soc_all` `:928-929`; `PASS_FLOOR` at `.github/workflows/cocotb.yml:165`.

### Operational hazards

- **Growing `tb_soc_top.sv`'s port list stales six suites' Verilator caches**, producing a corrupt
  `Vtop` and a double-free. G3 pre-adds every planned port tied off so this fires exactly once.
- **Never run two `soc_all` invocations concurrently** — they corrupt the `sim_build_*`
  directories and report a false pass count.
- **Driver suites need the riscv32 cross toolchain** and therefore belong in `soc_all` only, never
  `soc_all_ci`. This is what broke PR #195.

---

## 11. Non-goals for Phase 6

Recorded so they are decisions rather than omissions:

| Item | Non-goal | Why |
|:-----|:---------|:----|
| CRYPTO | AES decrypt datapath | CTR mode covers both directions; a decrypt path is nearly a second core |
| CRYPTO | AES-192 / AES-256, hardware HMAC, SHA-1 | Not in the roadmap |
| CRYPTO / NPU | AXI4 master + bulk DMA | `SOC_N_SLAVES` 3→4 churn for an unmeasured number — Phase 6b-2 |
| I2C | Multi-master arbitration and retry, 10-bit addressing, Fm+/Hs, SMBus timeouts | FSM cost without a stated requirement |
| PWM | Centre-alignment, dead-time | Implies complementary pairs and a shoot-through safety story |
| WDT | Register lock | Structurally impossible in `apb4_register_bank` (§3) |
| WDT | Independent always-on oscillator | No such clock exists in this SoC |
| TRNG | Adaptive-proportion health test, ring-oscillator silicon | Deferred; the latter is analog/PD work |
| NPU | INT4, sparsity, tiling, 16 KB SRAM, demo firmware | Roadmap already scopes these to FreePDK45/ASAP7 |
| All | UVM or formal verification | cocotb only, matching Phase 5 and 6a |
| All | Real pad ring, tristate resolution for I2C/GPIO open-drain | Pad-ring integration concern |
| All | ASAP7 runs | Triple-blocked (§8) |
| All | L3 software drivers | Outside this phase's DoD |

---

## 12. Related documents

| Document | Relationship |
|:---------|:-------------|
| `docs/ROADMAP.md` §Phase 6+ | Roadmap-level summary; this document is authoritative where they differ |
| `docs/PERIPHERAL_BUS_EVALUATION.md` | The APB4 decision this phase implements |
| `docs/PHASE_STATUS.md` | Per-item live status |
| `docs/design/MEMORY_MAP.md` | Address and register reference, updated per item |
| `docs/CPP_TO_RTL_HLS_EVALUATION.md` | HLS-vs-hand-RTL evidence behind the 6c decision |
| `docs/SKY130_REAL_DRC_LVS_EVALUATION.md` | Gate B context |
| `docs/development/CODING_GUIDELINES.md` | SystemVerilog house style for all new RTL |
