# Memory Map Specification

Complete address space allocation for RV32I SoC

Document status: Frozen
Last updated: 2026-09-20

## Overview

This document defines the memory map for all phases of the project, from single-CPU (Phase 1)
through full SoC integration (Phase 5).

## Address Space (32-bit)

Total addressable space: 4 GB (0x0000_0000 to 0xFFFF_FFFF)

## Minimum Address Region

The minimum or smallest memory region should be 4 KB
This restriction is due to Ubuntu's page size being 4 KB

### Global Memory Map (Phase 5 SoC)

| Address Range              | Size    | Region              | Description                 |
|:--------------------------:|:-------:|:-------------------:|:---------------------------:|
| 0x0000_0000 - 0x0000_0FFF  | 4 KB    | Reset & Traps       | Reset vector, trap handlers |
| 0x0000_1000 - 0x0000_1FFF  | 4 KB    | Boot ROM            | Initial boot code           |
| 0x0000_2000 - 0x0FFF_FFFF  | ~256 MB | Main Memory (RAM)   | Instruction and data        |
| 0x1000_0000 - 0x1FFF_FFFF  | 256 MB  | Reserved            | Future memory expansion     |
| 0x2000_0000 - 0x2000_0FFF  | 4 KB    | CPU Debug (APB3)    | CPU debug registers (only remaining APB3 block) |
| 0x2000_1000 - 0x2000_1FFF  | 4 KB    | GPU Control (AXI-Lite) | GPU registers            |
| 0x2000_2000 - 0x2000_2FFF  | 4 KB    | UART (AXI-Lite)     | UART peripheral             |
| 0x2000_3000 - 0x2000_3FFF  | 4 KB    | SPI (AXI-Lite)      | SPI master                  |
| 0x2000_4000 - 0x2000_4FFF  | 4 KB    | Timer (AXI-Lite)    | System timer                |
| 0x2000_5000 - 0x2000_5FFF  | 4 KB    | DMA Control (AXI-Lite) | DMA engine control registers |
| 0x2000_6000 - 0x2000_6FFF  | 4 KB    | IRQ Control (AXI-Lite) | Interrupt controller registers |
| 0x2000_7000 - 0x2000_7FFF  | 4 KB    | PLL Control (APB4)  | PLL subsystem config/status (`pll_apb_regs`) |
| 0x2000_8000 - 0x2000_8FFF  | 4 KB    | PMU Control (APB4)  | Power-mode sequencer registers (`pmu.sv`, GH #98/#99/#100) |
| 0x2000_9000 - 0x2000_9FFF  | 4 KB    | PLL2 Control (APB4) | Second PLL subsystem config/status, CPU-domain reference clock (`pll_apb_regs`, GH #92) |
| 0x2000_A000 - 0x2000_AFFF  | 4 KB    | GPIO (APB4)         | 32-pin GPIO controller (`gpio_controller.sv`, Phase 6a) |
| 0x2000_B000 - 0x2000_BFFF  | 4 KB    | PWM (APB4)          | 4-channel PWM controller (`pwm_controller.sv`, Phase 6a-2) |
| 0x2000_C000 - 0x2000_CFFF  | 4 KB    | WDT (APB4)          | Watchdog timer with bark/bite (`watchdog_timer.sv`, Phase 6a-3) |
| 0x2000_D000 - 0x2000_DFFF  | 4 KB    | TRNG (APB4)         | True-random-number generator; LFSR entropy arm by default, always flags `INSECURE` (`trng.sv`, Phase 6a-4) |
| 0x2000_E000 - 0x2000_EFFF  | 4 KB    | I2C (APB4)          | I2C master controller, open-drain, external pull-ups required (`i2c_controller.sv`, Phase 6a-5) |
| 0x2000_F000 - 0x2000_FFFF  | 4 KB    | CRYPTO (APB4)       | AES-128 (ECB/CTR) + SHA-256 accelerator; **not production cryptography** (`crypto_accel.sv`, Phase 6b) |
| 0x2001_0000 - 0x2FFF_FFFF  | ~256 MB | Reserved            | Future peripherals (0x2001_0000 NPU slot pre-allocated, not yet built) |
| 0x3000_0000 - 0x7FFF_FFFF  | 1.25 GB | Reserved            | Future use                  |
| 0x8000_0000 - 0xFFFF_FFFF  | 2 GB    | External Memory     | Off-chip memory/devices     |

> **Phase 5 peripheral ring (APB migration PR-7, updated GH #92):**
> peripherals attach to a CPU-driven **AXI4-Lite control interconnect**
> (`rtl/soc/axi_lite_interconnect.sv`) whose APB-bridge ring slot (slave 1,
> `0x2000_2000-0x2001_0FFF`) fans out through `axil_to_apb` + `apb_interconnect`
> into a genuine **APB4 sub-tree of 13 slaves** (UART, SPI, Timer, IRQ, PLL, PMU, PLL2,
> GPIO, PWM, WDT, TRNG, I2C, CRYPTO; `rtl/soc/soc_periph_map_pkg.sv` APB_UART..APB_CRYPTO). GPU/DMA control remain
> AXI-Lite-direct ring slaves (0 and 2). APB3 also survives standalone on the
> CPU debug slot (0x2000_0000–0FFF), unrelated to this APB4 sub-tree. Address
> map is frozen in `rtl/soc/soc_periph_map_pkg.sv` (`decode_axil_slave()`);
> unmapped accesses within 0x2000_xxxx return DECERR.

## Phase-Specific Maps

### Phase 0-1: Single CPU (No SoC Integration)

In Phases 0-1, only the CPU exists. The AXI4-Lite master connects directly to a simple memory model.

**AXI4-Lite address space**:

| Address Range              | Size    | Description                 |
|:--------------------------:|:-------:|:---------------------------:|
| 0x0000_0000 - 0x0000_0FFF  | 4 KB    | Reset & trap vectors        |
| 0x0000_1000 - 0x0000_FFFF  | 60 KB   | Program memory              |
| 0x0001_0000 - 0xFFFF_FFFF  | ~4 GB   | Data memory                 |

**APB3 debug interface** (CPU-local, 12-bit address):

See CPU Debug Registers section below.

### Phase 2-3: Pipelined CPU with Caches

Same as Phase 1, but with cache between CPU and memory.

**Cache configuration**:

- I-Cache: 4 KB, direct-mapped
- D-Cache: 4 KB, direct-mapped
- No cache coherence (single CPU)

### Phase 4: CPU + GPU (Pre-SoC Integration)

**AXI address space** (shared between CPU and GPU):

| Address Range              | Size    | Description                 |
|:--------------------------:|:-------:|:---------------------------:|
| 0x0000_0000 - 0x0FFF_FFFF  | 256 MB  | Shared memory (CPU+GPU)     |
| 0x2000_0000 - 0x2000_0FFF  | 4 KB    | CPU Debug registers         |
| 0x2000_1000 - 0x2000_1FFF  | 4 KB    | GPU Control registers       |

### Phase 5: Full SoC

See Global Memory Map above.

## Detailed Register Maps

### CPU Debug Registers (APB3 Slave)

**Base address**: 0x2000_0000 (in SoC), local offset 0x000 (APB3 12-bit addressing)

**Address width**: 12 bits (4 KB space, but only ~400 bytes used)

#### Control and Status Registers

| Offset | Name           | Access | Reset Value | Description                              |
|:------:|:--------------:|:------:|:-----------:|:----------------------------------------:|
| 0x000  | DBG_CTRL       | RW     | 0x0000_0000 | Debug control                            |
| 0x004  | DBG_STATUS     | RO     | 0x0000_0002 | Debug status                             |
| 0x008  | DBG_PC         | RW*    | 0x0000_0000 | Program counter                          |
| 0x00C  | DBG_INSTR      | RO     | 0x0000_0000 | Current instruction word                 |

*Writable only when CPU is halted

**DBG_CTRL (0x000)**: Debug Control Register

| Bit   | Name       | Access | Description                                    |
|:-----:|:----------:|:------:|:----------------------------------------------:|
| 31:4  | Reserved   | RO     | Reserved, read as 0                            |
| 3     | RESET_REQ  | W1     | Write 1 to reset CPU (self-clearing)           |
| 2     | STEP_REQ   | W1     | Write 1 to single-step (self-clearing)         |
| 1     | RESUME_REQ | W1     | Write 1 to resume execution (self-clearing)    |
| 0     | HALT_REQ   | W1     | Write 1 to halt execution (self-clearing)      |

**DBG_STATUS (0x004)**: Debug Status Register

| Bit   | Name       | Access | Description                                    |
|:-----:|:----------:|:------:|:----------------------------------------------:|
| 31:8  | Reserved   | RO     | Reserved, read as 0                            |
| 7:4   | HALT_CAUSE | RO     | Halt reason (see encoding below)               |
| 3:2   | Reserved   | RO     | Reserved, read as 0                            |
| 1     | RUNNING    | RO     | 1 = CPU running, 0 = CPU halted                |
| 0     | HALTED     | RO     | 1 = CPU halted, 0 = CPU running                |

**HALT_CAUSE encoding**:

- `4'b0000`: Not halted
- `4'b0001`: Debug halt request (via DBG_CTRL)
- `4'b0010`: Breakpoint 0 hit
- `4'b0011`: Breakpoint 1 hit
- `4'b0100`: Single-step complete
- `4'b1000`: EBREAK instruction executed
- Others: Reserved

#### General Purpose Registers

| Offset      | Name         | Access | Description                              |
|:-----------:|:------------:|:------:|:----------------------------------------:|
| 0x010       | DBG_GPR0     | RO     | x0 (always 0)                            |
| 0x014       | DBG_GPR1     | RW*    | x1 (ra - return address)                 |
| 0x018       | DBG_GPR2     | RW*    | x2 (sp - stack pointer)                  |
| 0x01C       | DBG_GPR3     | RW*    | x3 (gp - global pointer)                 |
| 0x020       | DBG_GPR4     | RW*    | x4 (tp - thread pointer)                 |
| 0x024-0x038 | DBG_GPR5-9   | RW*    | x5-x9 (t0-t4 - temporaries)              |
| 0x03C-0x044 | DBG_GPR10-11 | RW*    | x10-x11 (a0-a1 - args/return values)     |
| 0x048-0x05C | DBG_GPR12-15 | RW*    | x12-x15 (a2-a5 - arguments)              |
| 0x060-0x074 | DBG_GPR16-19 | RW*    | x16-x19 (a6-a7, s2-s3 - args/saved)      |
| 0x078-0x08C | DBG_GPR20-31 | RW*    | x20-x31 (s4-s11, t3-t6 - saved/temps)    |

*Writable only when CPU is halted

**Register offsets**:

- DBG_GPR[n] is at offset `0x010 + (n * 4)`
- Example: x15 (a5) is at offset 0x010 + (15 * 4) = 0x04C

#### Breakpoint Registers

| Offset | Name         | Access | Reset Value | Description                              |
|:------:|:------------:|:------:|:-----------:|:----------------------------------------:|
| 0x100  | DBG_BP0_ADDR | RW     | 0x0000_0000 | Breakpoint 0 address                     |
| 0x104  | DBG_BP0_CTRL | RW     | 0x0000_0000 | Breakpoint 0 control                     |
| 0x108  | DBG_BP1_ADDR | RW     | 0x0000_0000 | Breakpoint 1 address                     |
| 0x10C  | DBG_BP1_CTRL | RW     | 0x0000_0000 | Breakpoint 1 control                     |

**DBG_BPn_CTRL format**:

| Bit   | Name       | Access | Description                                    |
|:-----:|:----------:|:------:|:----------------------------------------------:|
| 31:1  | Reserved   | RO     | Reserved, read as 0                            |
| 0     | ENABLE     | RW     | 1 = Breakpoint enabled, 0 = disabled           |

**Breakpoint behavior**:

- When PC matches `DBG_BPn_ADDR` and `DBG_BPn_CTRL[0] = 1`, CPU halts
- `DBG_STATUS[7:4]` set to indicate which breakpoint triggered
- Instruction at breakpoint address NOT executed before halt

#### Reserved Space

| Offset        | Description                              |
|:-------------:|:----------------------------------------:|
| 0x110-0xFFF   | Reserved for future debug features       |

### GPU Control Registers (APB3 Slave)

**Base address**: 0x2000_1000 (in SoC), local offset 0x000

**Phase**: Phase 4+

#### GPU Core Registers

| Offset | Name             | Access | Reset Value | Description                              |
|:------:|:----------------:|:------:|:-----------:|:----------------------------------------:|
| 0x000  | GPU_CTRL         | RW     | 0x0000_0000 | GPU control                              |
| 0x004  | GPU_STATUS       | RO     | 0x0000_0001 | GPU status                               |
| 0x008  | GPU_KERNEL_ADDR  | RW     | 0x0000_0000 | Kernel start address                     |
| 0x00C  | GPU_GRID_DIM_X   | RW     | 0x0000_0000 | Grid dimension X                         |
| 0x010  | GPU_GRID_DIM_Y   | RW     | 0x0000_0000 | Grid dimension Y                         |
| 0x014  | GPU_GRID_DIM_Z   | RW     | 0x0000_0000 | Grid dimension Z                         |
| 0x018  | GPU_BLOCK_DIM_X  | RW     | 0x0000_0000 | Block dimension X                        |
| 0x01C  | GPU_BLOCK_DIM_Y  | RW     | 0x0000_0000 | Block dimension Y                        |
| 0x020  | GPU_BLOCK_DIM_Z  | RW     | 0x0000_0000 | Block dimension Z                        |
| 0x024  | GPU_WARP_SIZE    | RO     | 0x0000_0008 | Warp size (fixed at 8 in Phase 4)        |
| 0x028  | GPU_NUM_WARPS    | RO     | 0x0000_0004 | Number of warps (implementation-defined) |
| 0x02C  | GPU_PC           | RO     | 0x0000_0000 | Current kernel PC (debug)                |

**GPU_CTRL (0x000)**: GPU Control Register

| Bit   | Name       | Access | Description                                    |
|:-----:|:----------:|:------:|:----------------------------------------------:|
| 31:2  | Reserved   | RO     | Reserved, read as 0                            |
| 1     | RESET      | W1     | Write 1 to reset GPU (self-clearing)           |
| 0     | START      | W1     | Write 1 to start kernel (self-clearing)        |

**GPU_STATUS (0x004)**: GPU Status Register

| Bit   | Name       | Access | Description                                    |
|:-----:|:----------:|:------:|:----------------------------------------------:|
| 31:3  | Reserved   | RO     | Reserved, read as 0                            |
| 2     | ERROR      | RO     | 1 = Error occurred                             |
| 1     | DONE       | RO     | 1 = Kernel complete, 0 = not done              |
| 0     | IDLE       | RO     | 1 = GPU idle, 0 = GPU busy                     |

**Kernel launch sequence**:

1. Write `GPU_KERNEL_ADDR` with kernel instruction address
2. Write `GPU_GRID_DIM_*` and `GPU_BLOCK_DIM_*` with dimensions
3. Write `GPU_CTRL[0] = 1` to start execution
4. Poll `GPU_STATUS[1]` or wait for interrupt to detect completion

### Peripheral Registers (Phase 5)

#### UART Registers

**Base address**: 0x2000_2000

| Offset | Name        | Access | Description                              |
|:------:|:-----------:|:------:|:----------------------------------------:|
| 0x000  | UART_TX     | WO     | Transmit data register                   |
| 0x004  | UART_RX     | RO     | Receive data register                    |
| 0x008  | UART_STATUS | RO     | Status register                          |
| 0x00C  | UART_CTRL   | RW     | Control register                         |
| 0x010  | UART_BAUD   | RW     | Baud rate divisor                        |

#### SPI Registers

**Base address**: 0x2000_3000

| Offset | Name        | Access | Description                              |
|:------:|:-----------:|:------:|:----------------------------------------:|
| 0x000  | SPI_TX      | WO     | Transmit data register                   |
| 0x004  | SPI_RX      | RO     | Receive data register                    |
| 0x008  | SPI_STATUS  | RO     | Status register                          |
| 0x00C  | SPI_CTRL    | RW     | Control register                         |
| 0x010  | SPI_CLK_DIV | RW     | Clock divisor                            |
| 0x014  | SPI_CS_CTRL | RW     | Chip select control                      |

#### Timer Registers

**Base address**: 0x2000_4000

| Offset | Name         | Access | Description                              |
|:------:|:------------:|:------:|:----------------------------------------:|
| 0x000  | TMR_COUNTER  | RO     | Current counter value                    |
| 0x004  | TMR_COMPARE  | RW     | Compare value (triggers interrupt)       |
| 0x008  | TMR_CTRL     | RW     | Timer control                            |
| 0x00C  | TMR_PRESCALE | RW     | Clock prescaler                          |

#### GPIO Registers (Phase 6a)

**Base address**: 0x2000_A000 — `rtl/periph/gpio_controller.sv`, APB4, 32 pins.

| Offset | Name          | Access | Description                                        |
|:------:|:-------------:|:------:|:--------------------------------------------------:|
| 0x000  | GPIO_DATA_IN  | RO     | Synchronised pin state (2-FF, one per pin)         |
| 0x004  | GPIO_DATA_OUT | RW     | Output drive value                                 |
| 0x008  | GPIO_DIR      | RW     | Direction: 1 = output enable (`gpio_oe_o`)         |
| 0x00C  | GPIO_IRQ_EN   | RW     | Per-pin interrupt enable (masks `irq_o` only)      |
| 0x010  | GPIO_IRQ_TYPE | RW     | 0 = level-sensitive, 1 = edge-sensitive            |
| 0x014  | GPIO_IRQ_POL  | RW     | 0 = low / falling, 1 = high / rising               |
| 0x018  | GPIO_IRQ_STAT | RO     | Pending: sticky in edge mode, live in level mode   |
| 0x01C  | GPIO_IRQ_CLR  | WO     | Write 1 to clear the matching `GPIO_IRQ_STAT` bit (edge pins only); reads 0 |

Pins are exposed as an unidirectional triplet on `soc_top` —
`gpio_out_o[31:0]` / `gpio_oe_o[31:0]` / `gpio_in_i[31:0]`. There is no tristate
anywhere in this RTL tree and the Sky130 SoC hardens as a core macro with no pad
ring, so the bidirectional merge is deliberately left to pad-ring integration.

`GPIO_IRQ_STAT` captures events regardless of `GPIO_IRQ_EN` — that register masks
`irq_o` only. Status is **edge-sticky / level-live**, following ARM PL061: an
edge-mode bit latches until software writes the matching bit of `GPIO_IRQ_CLR`,
and a set beats a same-cycle clear so an edge is never lost to a racing clear; a
level-mode bit tracks its condition live and ignores `GPIO_IRQ_CLR` entirely, so
a live level interrupt is silenced at the source or via `GPIO_IRQ_EN`, never by
clearing status.

Note the reset-default reading: with `GPIO_IRQ_TYPE` = 0 (level) and
`GPIO_IRQ_POL` = 0 (active-low) and pins undriven low, every pin's condition is
true, so `GPIO_IRQ_STAT` reads all-ones (masked to the implemented pins) a couple
of cycles out of reset. `GPIO_IRQ_EN` = 0 at reset keeps `irq_o` low regardless.

#### PWM Registers (Phase 6a-2)

**Base address**: 0x2000_B000 — `rtl/periph/pwm_controller.sv`, APB4, 4 channels.

| Offset | Name          | Access | Description                                        |
|:------:|:-------------:|:------:|:--------------------------------------------------:|
| 0x000  | PWM_CTRL      | RW     | [3:0] per-channel enable, [7:4] per-channel output polarity (0 = active-high, 1 = inverted) |
| 0x004  | PWM_PERIOD    | RW     | [15:0] shared period, in prescaled ticks           |
| 0x008  | PWM_PRESCALE  | RW     | [15:0] `core_clk` divider; one tick = (PRESCALE+1) `core_clk` cycles |
| 0x00C  | PWM_DUTY01    | RW     | [15:0] ch0 duty, [31:16] ch1 duty (prescaled ticks) |
| 0x010  | PWM_DUTY23    | RW     | [15:0] ch2 duty, [31:16] ch3 duty (prescaled ticks) |
| 0x014  | PWM_IRQ_EN    | RW     | [3:0] per-channel period-wrap interrupt enable (masks `irq_o` only) |
| 0x018  | PWM_IRQ_STAT  | RO     | [3:0] sticky per-channel period-wrap status        |
| 0x01C  | PWM_IRQ_CLR   | W1C    | Write 1 to clear the matching `PWM_IRQ_STAT` bit; always reads 0 |

`pwm_o[3:0]` is a push-pull output only (no output-enable, no async input, no
CDC). A channel's active condition is `tick_count < DUTY[ch]` while the channel
is enabled; `pwm_o[ch] = active_condition ^ PWM_CTRL[4+ch]`. Left/edge-aligned
only. `DUTY == 0` gives true 0%, `DUTY >= PERIOD` gives true 100%, and
`PERIOD == 0` forces the output inactive and suppresses the period-wrap event
entirely — see `rtl/periph/pwm_controller.sv` header for the full rationale.

#### WDT Registers (Phase 6a-3)

**Base address**: 0x2000_C000 — `rtl/periph/watchdog_timer.sv`, APB4, 32-bit down-counter.

| Offset | Name          | Access | Description                                        |
|:------:|:-------------:|:------:|:--------------------------------------------------:|
| 0x000  | WDT_CTRL      | RW     | [0] enable, [1] `RST_EN` (reset value 0), [2] window-mode enable |
| 0x004  | WDT_RELOAD    | RW     | Counter reload value, in prescaled ticks           |
| 0x008  | WDT_COUNT     | RO     | Live down-counter; stores are ignored              |
| 0x00C  | WDT_WINDOW    | RW     | Closed-window threshold; 0 disables the window check |
| 0x010  | WDT_FEED      | WO     | Write `0x5A5A_C0DE` (all four byte strobes) to feed; any other value is rejected; reads 0 |
| 0x014  | WDT_PRESCALE  | RW     | [15:0] `core_clk` divider; one tick = (PRESCALE+1) `core_clk` cycles |
| 0x018  | WDT_STATUS    | RO     | [0] bark, [1] bite, [2] window violation — all sticky |
| 0x01C  | WDT_IRQ_CLR   | W1C    | Write 1 to clear the matching `WDT_STATUS` bit; always reads 0 |

**Bark and bite.** The first timeout is the *bark*: `WDT_STATUS[0]` sets, `irq_o` (level-held,
`|WDT_STATUS[2:0]`) asserts into interrupt-controller bit 7, and the counter reloads for a second
full period. A second timeout with no valid feed is the *bite*: the top-level output
`wdt_rst_req_o` asserts and is **level-held until external reset** (W1C of `WDT_STATUS[1]` does not
drop it, and bite is terminal — a later feed or enable does not revive it). A valid feed reloads the
counter and clears the bark-to-bite escalation. Bark-to-bite is exactly `(PRESCALE+1)*RELOAD + 1`
`core_clk` edges. `RELOAD == 0` while enabled fails toward firing (bark within a couple of edges).
A window violation (valid feed while `COUNT > WINDOW`, with `CTRL[2]` set and `WINDOW != 0`) is a
status bit only and never escalates to a bite.

**`RST_EN` and the CPU-domain reset.** `wdt_rst_req_o` is asserted by a bite *regardless* of
`WDT_CTRL.RST_EN`. `RST_EN` (reset value 0) gates only the internal reset path: when set, a bite
also asserts `cpu_domain_rst_n`, through `cdc_reset_sync` (`u_cpu_wdt_rst_sync`, `core_clk` to
`cpu_core_clk`), mirroring the PMU's `u_cpu_pmu_rst_sync`. It resets the **CPU domain only** —
not the whole SoC, which would also reset the WDT itself and tear down the APB fabric
mid-transaction — and it does **not** go through `pmu.sv`. The CPU stays in reset until an external
reset, because the request is level-held. With `RST_EN == 0` (the default) the path is inert.

Limitation: the WDT is clocked from `core_clk` through its prescaler. This SoC has no independent
always-on oscillator, so a stuck or dead PLL cannot be barked at.

#### TRNG Registers (Phase 6a-4)

**Base address**: 0x2000_D000 — `rtl/periph/trng.sv`, APB4, 4-deep entropy FIFO. **No top-level
pins**: the entropy source is an `` `ifdef``-swapped sub-module (`trng_lfsr_entropy.sv` by default,
`trng_ro_sky130.sv` under `TRNG_RO_SKY130`), not a port.

| Offset | Name          | Access | Description                                        |
|:------:|:-------------:|:------:|:--------------------------------------------------:|
| 0x000  | TRNG_CTRL     | RW     | [0] enable, [1] IRQ enable, [5:2] FIFO threshold   |
| 0x004  | TRNG_STATUS   | RO     | [0] data ready, [1] FIFO full, [2] `health_fail` (sticky), [3] `INSECURE` |
| 0x008  | TRNG_DATA     | RO     | Head of the entropy FIFO; a read **pops** one 32-bit word (read-snoop) |
| 0x00C  | TRNG_SEED     | RW     | LFSR seed, reset `0xACE1_2345`; sampled at the `CTRL.EN` 0-to-1 edge |
| 0x010  | TRNG_IRQ_CLR  | WO     | Write 1 to bit 2 to clear `STATUS.health_fail`; reads 0 |

`N_REGS = 8`; 0x014-0x01C are reserved and read 0. Stores to `TRNG_STATUS` and `TRNG_DATA` are
ignored.

**`INSECURE` (`STATUS[3]`).** The default build is a deterministic generator: three LFSRs
(31/29/23-bit) XORed into a raw sample, then a von Neumann debiaser. Every word is a pure function
of `TRNG_SEED` (`tb/models/trng_lfsr_model.py` is the bit-exact model), so it is **not
cryptographic**. `STATUS[3]` reads 1 in that build and cannot be cleared or masked; it is the only
marker that distinguishes it from real entropy behind a register named TRNG. Under
`TRNG_RO_SKY130` it reads 0.

**Sessions and the FIFO.** A `CTRL.EN` 0-to-1 edge starts a session: the LFSRs load from
`TRNG_SEED`, the FIFO is cleared. Writing `TRNG_SEED` at any other time only updates the register.
Reading `TRNG_DATA` on an empty FIFO returns 0 with no error; `STATUS.data_ready` is the only
validity indicator. Backpressure is a stall, not a drop: while the FIFO is full the entropy arm is
not clocked, so the popped sequence depends on the seed alone, not on read timing.

**Health test and IRQ.** A NIST SP 800-90B repetition-count test (cutoff 21) runs on the raw,
pre-debias samples. A trip sets sticky `STATUS[2]`, flushes the FIFO and halts production until a
W1C of `TRNG_IRQ_CLR[2]`. `irq_o = CTRL[1] & ((fifo_level >= max(CTRL[5:2],1)) | health_fail)` and is
level-held into interrupt-controller bit 8; it drops by itself once software pops the FIFO below
the threshold.

#### I2C Registers (Phase 6a-5)

**Base address**: 0x2000_E000 — `rtl/periph/i2c_controller.sv`, APB4, master-only, 7-bit addressing,
repeated START, mandatory clock stretching, arbitration-loss *detection*, 8-byte TX and RX FIFOs.

> **PAD-RING CONTRACT — open-drain, external pull-up REQUIRED.** There is **no tristate** anywhere in
> this RTL tree. Each line is the GPIO-style unidirectional triplet
> `i2c_scl_o` / `i2c_scl_oe_o` / `i2c_scl_i` and `i2c_sda_o` / `i2c_sda_oe_o` / `i2c_sda_i`
> (top-level ports of `soc_top`).
>
> - `*_oe_o` is the real control: **1 drives the line low, 0 releases it.** Nothing on-chip ever drives
>   a line high; a released line is high only because the **external pull-up** makes it so. Integration
>   must provide one pull-up per line.
> - `*_o` is **hard-tied 1'b0 and dead.** It exists only for pad-ring symmetry with
>   `gpio_out_o`/`gpio_oe_o`/`gpio_in_i`. The pad cell must drive 0 when `oe = 1` and be high-Z when
>   `oe = 0`; do not use `*_o` as data.
> - The wired-AND of master and slaves lives **off-chip** (the physical bus). It is not modelled in the
>   RTL; a testbench must model it. (The internal loopback models it for its one internal slave only.)
> - `*_i` are the sensed pad levels and are **asynchronous**; each is synchronised inside the block by
>   its own single-bit `cdc_2ff_sync`.

| Offset | Name           | Access | Description                                        |
|:------:|:--------------:|:------:|:--------------------------------------------------:|
| 0x000  | I2C_CTRL       | RW     | [0] EN, [1] LOOPBACK, [11:8] RX_THR (0 behaves as 1; 9..15 never fire) |
| 0x004  | I2C_STATUS     | RO     | [0] busy, [1] txn_active, [2] nack, [3] arb_lost, [4] timeout (sticky), [5] SCL level, [6] SDA level |
| 0x008  | I2C_CLKDIV     | RW     | [15:0] tick divider, reset `0x00FF`; `f_scl = f_clk / (4*(CLKDIV+1))`; values below 3 are clamped to 3 |
| 0x00C  | I2C_ADDR       | RW     | [6:0] 7-bit slave address, [7] R/W (0 write, 1 read) |
| 0x010  | I2C_TX_DATA    | WO     | Write (pstrb[0]) pushes `pwdata[7:0]` into the TX FIFO; push into a full FIFO is dropped; reads 0 |
| 0x014  | I2C_RX_DATA    | RO     | RX FIFO head; a read **pops** it; empty returns 0 with no error |
| 0x018  | I2C_CMD        | WO     | [0] START, [1] WRITE, [2] READ, [3] STOP, [4] NACK_LAST, [15:8] COUNT; reads 0 |
| 0x01C  | I2C_FIFO_STAT  | RO     | [3:0] tx_level, [7:4] rx_level, [8] tx_full, [9] tx_empty, [10] rx_full, [11] rx_empty |
| 0x020  | I2C_TIMEOUT    | RW     | [15:0] stuck-wait limit in engine ticks, reset `0xFFFF`; 0 disables |
| 0x024  | I2C_IRQ_EN     | RW     | [4:0] masks `irq_o` only |
| 0x028  | I2C_IRQ_STAT   | RO     | [0] done, [1] nack, [2] arb_lost, [3] timeout (sticky); [4] rx_threshold (live level) |
| 0x02C  | I2C_IRQ_CLR    | WO     | W1C against `IRQ_STAT[3:0]`; reads 0 |

`N_REGS = 12`; 0x030-0xFFC read 0.

**Commands.** One `I2C_CMD` write runs one command in a fixed order: START (a *repeated* START if
`STATUS.txn_active`) plus the address byte `{ADDR[6:0], ADDR[7]}`, then `COUNT` data bytes (0 means 1;
WRITE wins if both WRITE and READ are set), then STOP. WRITE pops the TX FIFO, READ pushes the RX FIFO;
READ ACKs every byte except the last, which is NACKed iff `NACK_LAST`. A command is accepted only when
`CTRL.EN = 1`, the engine is idle (`STATUS.busy = 0`) and the command is legal (START, or `txn_active`
for WRITE/READ/STOP-only); otherwise the write is **ignored silently**. Software keeps `ADDR[7]`
consistent with the data op; the engine does not police it. Clearing `CTRL.EN` aborts the engine at
once (lines released, no event bit) and flushes both FIFOs on the 1-to-0 edge.

**Errors.** A NACK sets sticky `nack`, abandons the remaining data bytes and still sends STOP if
requested (otherwise the bus is held so software can STOP or repeated-START); `done` then sets.
**Arbitration loss** (this master released SDA to send a 1 but sensed 0) and **timeout** (any wait —
bus busy before START, stretched SCL, FIFO starvation — exceeded `I2C_TIMEOUT` ticks) each set their own
sticky bit, release both lines and return the engine to idle **instead of** `done`. There is no retry:
software re-issues. Clock stretching is mandatory: the engine does not advance out of SCL-high until the
*synchronised* `scl_i` reads high.

**Prescaler minimum.** The engine samples the synchronised lines (2-FF latency plus the oe register), so
a tick must exceed that latency. `CLKDIV_MIN = 3` is an elaboration-guarded parameter
(`CLKDIV_MIN >= SYNC_STAGES + 1`, a smaller override fails elaboration) and a smaller `CLKDIV` is clamped
in hardware; compare `SPI_CLK_DIV >= 7`, which SPI only documents.

**IRQ.** `irq_o = |(IRQ_STAT & IRQ_EN)`, level-held into interrupt-controller bit 9. The four event
bits are sticky with SET winning over a same-cycle clear; `rx_threshold` follows the RX FIFO level.

**Loopback (`CTRL[1]`).** Folds the master's own `oe` back through an internal ACKing slave instead of
the pins and forces the pad `oe_o` outputs released so a real bus is undisturbed. The slave ACKs any
address and every write byte, and a read returns the last byte written (reset `0xA5`). It never
stretches. Change it only while idle.

#### CRYPTO Registers (Phase 6b)

**Base address**: 0x2000_F000 — `rtl/periph/crypto_accel.sv` (wrapper over `aes128_core.sv` and
`sha256_core.sv`), APB4 slave index 12, `N_REGS = 32`, `core_clk` domain, interrupt-controller bit 10.
Register-only: no top-level pins and no asynchronous inputs, so no CDC synchroniser and no SDC
`set_false_path` apply. The `EN_AES` / `EN_SHA` parameters drop a core from the build (default both 1).

> **NOT PRODUCTION CRYPTOGRAPHY.** No side-channel or DPA resistance, no fault-injection hardening, no
> certification (no FIPS 140 / Common Criteria / CAVP); correctness is established by known-answer
> vectors in simulation only. Operation *duration* is fixed by construction (no early exit, no
> data-dependent control), but no claim is made about power, EM or glitch behaviour.
>
> **Any bus master can write, replace and use the key, and read the results.** The key itself is *not*
> readable over the bus — `KEY0-3` read 0 forever and `key_q` reaches no output — but that buys little:
> there is no privilege or secure/non-secure split (M0 CPU, M1/M2 GPU and M3 DMA all decode to the APB
> ring, and `axil_to_apb` ignores `AxPROT`), so any master can substitute its **own** key between a
> victim's key load and its start and then read `DOUT`. In CTR that gives `E_attacker(IV) ^ msg_q`,
> recovering the victim's plaintext despite `DIN` also reading 0; in SHA it gives `H(victim_msg)`.
> Treat this as an unprotected shared oracle, not as key storage.
>
> **No key lifecycle:** no zeroisation command, no lock bit, and `key_valid` never drops once set — the
> only clear is `core_rst_n` (a whole-SoC reset, which also fires on a PLL unlock). **Residual state
> survives a context switch:** `key_q`, `rk_q` (the round-10 key, which inverts to the master key),
> `msg_q`, `DOUT`, `DIGEST` and `IV` all persist, so a second user writing fewer than four KEY words —
> or using partial strobes — silently runs on the first user's key with `key_valid` still 1, and
> `DOUT`/`DIGEST` stay readable (in CTR decrypt, that is the previous user's *plaintext*). Software must
> rewrite all four KEY words with `pstrb = 0xF` on every switch.
>
> **Nonce/IV management is entirely software's job:** `IV` resets to 0, nothing enforces uniqueness, and
> `IV` is the one register with no busy-time protection, so a mid-operation write to `IV3` re-bases the
> next counter block and can cause counter reuse. **No integrity, no decrypt datapath:** ECB leaks
> plaintext patterns block-for-block, CTR is unauthenticated and malleable, and there is no MAC or AEAD.
>
> **Everything in this block is exposed through scan** once DFT insertion is applied — `key_q`, the AES
> state and round key, the message shadow, the SHA working registers, and the bank flops holding `DOUT`,
> `DIGEST` and `IV` — so **DFT access must be treated as key access**, as must any debug path that can
> observe flop state.

**Byte order.** FIPS-197 / FIPS 180-4 big-endian throughout. For a 128-bit block `B[0..15]`, word 0
carries `B0` in bits [31:24]: `DIN0[31:24] = B0 ... DIN3[7:0] = B15`, and the same for KEY, IV and DOUT.
`DIGEST0[31:24]` is the most significant byte of H0. FIPS-197 App. B/C vectors and `hashlib.sha256`
therefore line up with no byte swap.

| Offset | Name             | Access | Description                                        |
|:------:|:----------------:|:------:|:--------------------------------------------------:|
| 0x000  | CRYPTO_CTRL      | RW     | [1:0] mode (0 ECB, 1 CTR, 2 SHA, 3 reserved), [2] **start (W1P, reads 0)**, [3] IRQ enable, [4] SHA_CONT; [31:5] reserved |
| 0x004  | CRYPTO_STATUS    | RO     | [0] busy, [1] done (sticky), [2] key_valid, [3] key_write_rejected (sticky) |
| 0x008  | CRYPTO_KEY0-3    | WO     | AES-128 key, 4 words at 0x008-0x014; **always reads 0** (no readback path exists) |
| 0x018  | CRYPTO_IV0-3     | RW     | CTR counter block, 0x018-0x024; IV3 (0x024) is the INC32 word |
| 0x028  | CRYPTO_DIN0-3    | WO     | **4-word aperture** onto one 512-bit shift register, 0x028-0x034; reads 0 |
| 0x038  | CRYPTO_DOUT0-3   | RO     | AES output block, 0x038-0x044 |
| 0x048  | CRYPTO_DIGEST0-7 | RO     | SHA-256 digest, 0x048-0x064; **also the SHA chaining value** |
| 0x068  | CRYPTO_IRQ_STAT  | RO     | [0] sticky done (the same flop as `STATUS[1]`) |
| 0x06C  | CRYPTO_IRQ_CLR   | WO     | W1C by write-snoop: [0] clears done, [1] clears `STATUS.key_write_rejected`; reads 0 |

0x070-0x07C are reserved and read 0; 0x080-0xFFC are outside the 32-register bank and also read 0.

**Start.** `CTRL[2]` is not stored: it reads 0 forever and acts as a write-snoop pulse. **Start while busy
is silently ignored** (no status bit, no `pslverr`). **Software contract: write the mode and `SHA_CONT`
first, then START in a *later* transfer.** Mode, `SHA_CONT` and the legality check read the bank's CTRL
register, which still holds its pre-write value during the ACCESS cycle of the write carrying START, so a
single write that both changes the mode and sets START runs the **old** mode. Latency from the start
write's ACCESS phase to done: 11 clk (ECB/CTR, `SBOX_PARALLEL=16`), 41 clk (`SBOX_PARALLEL=4`), 66 clk
(SHA), 2 clk (illegal op).

**Illegal or disabled mode is hang-free.** An operation is legal iff (mode 0/1, `EN_AES`, `key_valid`) or
(mode 2, `EN_SHA`); mode 3 is always illegal. An illegal start completes in 2 clk: busy pulses, `done` /
`IRQ_STAT` set (and the IRQ fires if enabled), with **no** DOUT / DIGEST / IV writeback. **Done does not
imply valid data**: software must check `key_valid` and that the requested mode is built.

**Key.** Written word by word in any order; partial byte strobes merge. Key writes are **rejected while
`STATUS.busy`** and latch the sticky `STATUS[3]` (cleared by reset, `IRQ_CLR[1]`, or an accepted key
write). A key write with `pstrb == 0` selects no byte lane and is not a key write at all: it counts toward
neither `key_valid` nor `key_write_rejected`. `key_valid` is set once all four words have been written and
is cleared **only by reset**, so a partial rewrite leaves it 1 over a mixed key. With `EN_AES = 0` the bit
carries no information.

**DIN.** Only the fact that a write hit DIN0..3 matters, not which word; **write order is the contract**,
most significant word first (16 words for SHA, M0 first; 4 words for AES, B0..B3 first). A partial-strobe
write is **dropped**. Pushes are **rejected while busy**, with no status bit, a deliberate asymmetry with
`key_write_rejected` because CTR consumes the plaintext at the completion edge.

**AES modes.** ECB: `DOUT = AES(key, DIN)`. CTR: the core encrypts the counter block IV and the XOR with
DIN happens at writeback. CTR decrypt is bit-identical to CTR encrypt (no decrypt mode, no inverse S-box).
After each CTR block `IV3` is incremented (SP 800-38A B.1 INC32: low 32 bits only, carry discarded; IV0-2
are never hardware-written); software must not run one counter past a 2^32-block wrap. IV lives in the
bank, so a software write to IV during a CTR operation corrupts the counter, and a same-cycle write to IV3
beats the hardware increment (correct for a re-seed).

**SHA chaining.** `CTRL[4] SHA_CONT = 0` starts from the FIPS 180-4 H0 constants; 1 continues from the
current DIGEST. Multi-block: write 16 words, start with `SHA_CONT = 0`, poll done, write the next 16,
start with `SHA_CONT = 1`, ..., read DIGEST. Padding and length encoding are software's job.

**CTRL written while busy** is unsupported but safe in these respects: the operation in flight completes
with the mode it *started* with (mode, `SHA_CONT`, the CTR choice and the chaining value are latched at the
start edge), so DOUT / DIGEST / IV3 are not corrupted, and the IRQ enable takes effect immediately. The new
mode applies to the *next* start, and a START bit in such a write is ignored.

**DOUT / DIGEST validity.** Written on each operation's completion edge, so they are never garbage:
either current, or one operation stale (a read during a new operation returns the previous result). Gate
reads on `done` anyway.

**IRQ.** `irq_o = done & CTRL[3]`, **level-held, never a pulse** (every IRQ source crosses `core_clk` to
`cpu_core_clk` through a plain 2-FF synchroniser that can miss a pulse). The `done` next-state is
`(done & ~IRQ_CLR[0]) | done_set`, so a **set beats a same-cycle clear** and a completion is never lost to
a racing W1C. `STATUS[1]` and `IRQ_STAT[0]` are the same flop mirrored into two words.

## Reset and Trap Vectors

### Reset Vector

**Address**: 0x0000_0000

**Behavior**: PC loads this address on reset. Typically contains a jump to boot ROM.

**Example boot code**:

```assembly
0x0000_0000:  jal x0, 0x100    # Jump to trap handler setup
```

### Trap Vector

**Address**: 0x0000_0100 (TRAP_VECTOR constant in PHASE0_ARCHITECTURE_SPEC.md)

**Behavior**: PC loads this address on any trap (illegal instruction in Phase 1).

**Example trap handler**:

```assembly
0x0000_0100:  # Trap handler entry
              # Save context
              # Determine trap cause
              # Handle or abort
```

## Address Alignment Requirements

All addresses must be naturally aligned:

| Access Size   | Alignment Requirement | Valid addr[1:0] |
|:-------------:|:---------------------:|:---------------:|
| Byte (8-bit)  | 1-byte aligned        | Any             |
| Half (16-bit) | 2-byte aligned        | 00, 10          |
| Word (32-bit) | 4-byte aligned        | 00              |

**Misaligned accesses**: Phase 1 treats misaligned accesses as illegal instruction traps.

## Memory Access Permissions (Future)

Phase 1 has no memory protection. Future phases may add:

- Read/write/execute permissions
- Privileged vs user mode access
- Memory protection unit (MPU)

## SoC Interconnect (Phase 5)

As implemented in `rtl/soc/soc_top.sv` (M8):

**Data plane** — AXI4 crossbar (`axi4_crossbar.sv`), 4 masters × 3 slaves:

| Port | Agent |
| :--- | :---- |
| M0 | CPU (rv32i_cpu_top AXI4 master) |
| M1 | GPU ifetch (axilite_to_axi4 read-only adapter) |
| M2 | GPU data (gpu_top `m_axi_*`) |
| M3 | DMA engine |
| S0 | Boot ROM (0x0000_1000 – 0x0000_1FFF) |
| S1 | SRAM controller (0x0000_2000 – 0x0FFF_FFFF) |
| S2 | Peripheral bridge → AXI-Lite ring (0x2000_1000 – 0x2000_AFFF) |

**Control plane** — `axi4_to_axilite` → `axi_lite_interconnect`, 6 AXI-Lite slaves:
GPU(0), UART(1), SPI(2), TIMER(3), DMA(4), IRQ(5).

**Debug plane** — APB3 debug slave exposed at top-level ports (no APB bridge on
the data path; the Phase 1–4 AXI-Lite-crossbar/APB-bridge description is obsolete).

**Interconnect assumptions** (violating these voids the deadlock-free guarantee):

- The AXI-Lite control ring is **single-master** (CPU config access only); the
  interconnect has no arbitration. A second master (e.g. DMA-to-peripheral in
  Phase 6) requires an interconnect upgrade.
- The AXI4 crossbar locks a slave to one master per transaction (depth-1
  outstanding per direction). Masters must **not** hold overlapping AR + AW
  to the same slave expecting ordering between them.

### Interrupt Hierarchy (Phase 5)

Two interrupt lines reach the CPU (priority: **MEIP > MTIP**, per
`rv32i_interrupt_ctrl.sv`):

| CPU input | mcause | Source |
| :-------- | :----- | :----- |
| `ext_irq_i` (MEIP) | 0x8000_000B | `interrupt_controller.irq_o` — aggregated, 2-FF-synchronised, mask/status registers at 0x2000_6000 |
| `timer_irq_i` (MTIP) | 0x8000_0007 | Timer `irq_o`, wired **directly** (not via the IRQ controller; its bit 2 is tied 0) |

IRQ controller source bits (`N_SOURCES=12`, Phase 6, bead claude_verilog_test-f7vs.2):
`{NPU[11], CRYPTO[10], I2C[9], TRNG[8], WDT[7], PWM[6], GPIO[5], GPU[4], DMA[3],
TIMER[2]=0, SPI[1], UART[0]}`. Bit 6 (PWM) is live as of Phase 6a-2 (bead
claude_verilog_test-f7vs.6), bit 7 (WDT, bark and bite) as of Phase 6a-3 (bead
claude_verilog_test-f7vs.7) and bit 8 (TRNG) as of Phase 6a-4 (bead
claude_verilog_test-f7vs.8), bit 9 (I2C) as of Phase 6a-5 (bead
claude_verilog_test-f7vs.9) and bit 10 (CRYPTO, done) as of Phase 6b (bead
claude_verilog_test-f7vs.10); bit 11 remains tied 0 until the NPU lands. On a MEIP trap, software reads `IRQ_STATUS` (0x2000_6000 block) to disambiguate
the peripheral source; bit priority within the controller does not reorder
delivery — all enabled sources share the single MEIP line.

## Testing Recommendations

### Address Decode Testing

- Verify all valid addresses return correct data
- Verify invalid addresses return AXI DECERR or APB pslverr
- Test boundary addresses (e.g., 0x0FFF_FFFC, 0x1000_0000)

### Alignment Testing

- Test misaligned accesses trigger traps
- Test all valid alignments work correctly

### Debug Register Testing

- Test halt/resume/step sequences
- Test breakpoint triggers
- Test register read/write when halted
- Test writes ignored when running

## References

- PHASE0_ARCHITECTURE_SPEC.md: Reset and trap behavior
- PHASE1_ARCHITECTURE_SPEC.md: CPU debug interface details
- PHASE4_GPU_ARCHITECTURE_SPEC.md: GPU register specifications
- RTL_DEFINITION.md: Interface signal definitions
