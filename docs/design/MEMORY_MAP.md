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
| 0x2000_E000 - 0x2FFF_FFFF  | ~256 MB | Reserved            | Future peripherals          |
| 0x3000_0000 - 0x7FFF_FFFF  | 1.25 GB | Reserved            | Future use                  |
| 0x8000_0000 - 0xFFFF_FFFF  | 2 GB    | External Memory     | Off-chip memory/devices     |

> **Phase 5 peripheral ring (APB migration PR-7, updated GH #92):**
> peripherals attach to a CPU-driven **AXI4-Lite control interconnect**
> (`rtl/soc/axi_lite_interconnect.sv`) whose APB-bridge ring slot (slave 1,
> `0x2000_2000-0x2001_0FFF`) fans out through `axil_to_apb` + `apb_interconnect`
> into a genuine **APB4 sub-tree of 11 slaves** (UART, SPI, Timer, IRQ, PLL, PMU, PLL2,
> GPIO, PWM, WDT, TRNG; `rtl/soc/soc_periph_map_pkg.sv` APB_UART..APB_TRNG). GPU/DMA control remain
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
claude_verilog_test-f7vs.8); bits 9-11 remain tied 0 until their peripheral
lands. On a MEIP trap, software reads `IRQ_STATUS` (0x2000_6000 block) to disambiguate
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
