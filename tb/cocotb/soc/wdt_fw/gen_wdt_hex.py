#!/usr/bin/env python3
"""
gen_wdt_hex.py — generate wdt_fw.hex and wdt_rst_fw.hex for the Phase 6a-3 SoC-level
watchdog test (bead claude_verilog_test-f7vs.7 steps 4-5, docs/PHASE6_IP_EXPANSION_PLAN.md §10).

Modelled directly on pwm_fw/gen_pwm_hex.py (itself a copy of gpio_fw/gen_gpio_hex.py) — same
Assembler/lui_addi/CSRRW/MRET machinery, same commit_pc_o marker-PC synchronisation idiom. A
committed pure-Python hand-assembler, so the suite needs no riscv32 cross toolchain and is
CI-safe (a toolchain-dependent suite in soc_all_ci is what broke PR #195).

Path exercised (confirmed from soc_top.sv):
  CPU --AXI4--> axi4_crossbar --AXI4--> axi4_to_axilite --AXI-Lite-->
  axi_lite_interconnect --AXI-Lite--> axil_to_apb --APB4--> apb_interconnect
  --APB4--> APB_WDT slave 9 (watchdog_timer, base 0x2000_C000)

WDT register map (rtl/periph/watchdog_timer.sv, word indices):
  +0x00 WDT_CTRL     RW  [0] enable, [1] RST_EN, [2] window-mode enable
  +0x04 WDT_RELOAD   RW  reload value, in prescaled ticks
  +0x08 WDT_COUNT    RO  live down-counter
  +0x0C WDT_WINDOW   RW  closed-window threshold (unused here)
  +0x10 WDT_FEED     WO  0x5A5A_C0DE (pstrb 4'hF) feeds
  +0x14 WDT_PRESCALE RW  [15:0] divider; one tick = (PRESCALE+1) core_clk cycles
  +0x18 WDT_STATUS   RO  [0] bark, [1] bite, [2] window violation — sticky
  +0x1C WDT_IRQ_CLR  W1C against WDT_STATUS

Two images are emitted:

=========================================================================================
IMAGE A — wdt_fw.hex — feed, then starve: bark and bite through the real fabric, RST_EN = 0
=========================================================================================
  IRQ_READY   mtvec/IRQ_MASK bit 7 (WDT)/MEIE/MIE armed BEFORE the dog is enabled, so the
              period measured from CONFIG_DONE is not eaten by interrupt set-up MMIO.
  CONFIG_DONE PRESCALE/RELOAD/CTRL(EN) written; the dog is counting.
              Firmware polls WDT_COUNT (an MMIO READ through the fabric) until it has fallen to
              half the reload, then
  FED         writes the magic to WDT_FEED and reads COUNT straight back: it must be back near
              the reload value — proof the FEED write crossed the fabric and reloaded the
              counter, not just that a bit somewhere changed. STATUS must still read 0.
  From FED on firmware never feeds again. The dog barks (IRQ -> interrupt_controller[7] ->
  CPU MEIP -> ISR #1), the ISR clears what it saw, the counter runs a second full period, and
  the dog BITES (wdt_rst_req_o at the SoC boundary; IRQ again -> ISR #2). Bite is terminal.

  ISR design — clear-what-you-saw. The ISR reads WDT_STATUS into a register and writes THAT
  value to WDT_IRQ_CLR, rather than clearing a fixed mask or disabling the peripheral. Every
  MMIO access here crosses the full fabric, so a status bit that becomes set between the read
  and the clear (a bark racing the ISR) survives the clear instead of being silently swallowed,
  and a bit that was never seen can never be cleared. This is what the PWM L2 suite's race
  taught (it cleared status and then masked in two separate writes, leaving a window in which
  the condition could re-fire); here there is no second write for a race to slip between, and
  the ISR's last action is a WDT_STATUS read-back whose fabric round trip both proves the clear
  landed and lets the level-held IRQ drain through the 2-FF ext_irq synchroniser before MRET
  re-enables MIE (otherwise a stale ext_irq would re-vector). Exactly TWO traps are expected —
  bark, then bite — and firmware checks ISR_COUNT == 2, LOG[0] == 0x1 (bark only) and
  LOG[1] == 0x2 (bark already cleared by ISR #1, bite set).

  Register allocation (MAIN):
    x2 = WDT_BASE  x3 = IRQ_CTRL_BASE  x4 = ISR_BASE_ADDR (SRAM: count, log0, log1)
    x5 = write staging  x14/x15 = poll counter/limit  x16-x21 = scratch  x31 = result marker
  Register allocation (ISR, at ISR_PC = ROM_BASE + 4):
    x28 = WDT_BASE  x29 = STATUS seen  x30 = ISR_BASE_ADDR  x31 = &log[count]  x1 = count

==========================================================================================
IMAGE B — wdt_rst_fw.hex — RST_EN = 1: the bite resets the CPU domain, and only that domain
==========================================================================================
  Enables the dog with CTRL = EN | RST_EN and a short period, then spins in a two-instruction
  loop that commits LOOP_PC forever. Interrupts stay off. After the bite the CPU is held in
  reset for good (wdt_rst_req_o is level-held until an external reset), so this image never
  reaches a PASS marker — the cocotb test scores it from the boundary instead: cpu_domain_rst_n
  falls, commits stop, while core_rst_n / cpu_core_rst_n stay high and the level-held
  wdt_rst_req_o proves the WDT itself was NOT reset.
"""

import os
import sys

_PROJ_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))
if _PROJ_ROOT not in sys.path:
    sys.path.insert(0, _PROJ_ROOT)

from sim.riscv_encoder import (
    LUI, ADDI, SW, LW, BNE, BLT, JAL, EBREAK, ADD, SLLI,
)


def CSRRW(rd: int, csr: int, rs1: int) -> int:
    """CSRRW rd, csr, rs1"""
    return ((csr & 0xFFF) << 20) | (rs1 << 15) | (0x1 << 12) | (rd << 7) | 0x73


def MRET() -> int:
    """MRET — return from machine-mode trap (restores PC from mepc, MIE from MPIE)"""
    return 0x30200073


# ---------------------------------------------------------------------------
# ROM layout
# ---------------------------------------------------------------------------
ROM_BASE   = 0x0000_1000
ROM_WORDS  = 1024
NOP        = 0x00000013   # ADDI x0, x0, 0

# Word 0 = reset-vector trampoline (JAL x0, MAIN); word 1 = ISR start.
ISR_OFFSET_WORDS = 1
MAIN_START_WORDS = 20   # ISR measures well under this; padded generously.

# ---------------------------------------------------------------------------
# Address map
# ---------------------------------------------------------------------------
WDT_BASE            = 0x2000_C000
WDT_OFF_CTRL        = 0x00
WDT_OFF_RELOAD      = 0x04
WDT_OFF_COUNT       = 0x08
WDT_OFF_FEED        = 0x10
WDT_OFF_PRESCALE    = 0x14
WDT_OFF_STATUS      = 0x18
WDT_OFF_IRQ_CLR     = 0x1C

IRQ_CTRL_BASE       = 0x2000_6000
IRQ_OFF_MASK        = 0x004
WDT_IRQ_MASK_BIT    = 0x80   # interrupt_controller.irq_src_i[7] = WDT slot

FEED_MAGIC          = 0x5A5A_C0DE

SRAM_BASE           = 0x0000_2000
ISR_COUNT_WI        = 310   # SRAM word 310 = byte 0x0000_24D8
ISR_LOG0_WI         = 311   # STATUS seen by ISR #1
ISR_LOG1_WI         = 312   # STATUS seen by ISR #2
ISR_BASE_ADDR       = SRAM_BASE + ISR_COUNT_WI * 4

# ---------------------------------------------------------------------------
# Timing constants — image A
# ---------------------------------------------------------------------------
PRESCALE_VAL   = 1      # one tick = 2 core_clk cycles
RELOAD_VAL     = 400    # ticks per period
PERIOD_CYCLES  = RELOAD_VAL * (PRESCALE_VAL + 1)   # 800 core_clk cycles per period
FEED_AT_COUNT  = RELOAD_VAL // 2                   # poll until COUNT has fallen to here
# After the feed COUNT must read back above this. Pre-feed COUNT is <= FEED_AT_COUNT (200) and
# falling, so anything above it can only be a reload. The margin below RELOAD_VAL (400) is 120
# ticks = 240 core_clk cycles for the fabric round trip between the feed landing and the
# read-back.
FED_MIN_COUNT  = 280

CTRL_EN        = 0x1
CTRL_RST_EN    = 0x2

WFI_POLL_LIMIT = 4000

# ---------------------------------------------------------------------------
# Timing constants — image B
# ---------------------------------------------------------------------------
B_PRESCALE_VAL  = 0
B_RELOAD_VAL    = 100   # bark ~102 edges after enable, bite ~101 edges later
B_PERIOD_CYCLES = B_RELOAD_VAL * (B_PRESCALE_VAL + 1)


def lui_addi(rd: int, value32: int):
    """Return (lui_word, addi_word) to load a 32-bit constant into rd."""
    lower12 = value32 & 0xFFF
    lower_signed = lower12 if lower12 < 0x800 else lower12 - 0x1000
    upper20 = (value32 >> 12) & 0xFFFFF
    if lower12 & 0x800:
        upper20 = (upper20 + 1) & 0xFFFFF
    reconstructed = ((upper20 << 12) + lower_signed) & 0xFFFF_FFFF
    assert reconstructed == (value32 & 0xFFFF_FFFF), (
        f"lui_addi({rd}, 0x{value32:08x}): upper=0x{upper20:05x} "
        f"lower_signed={lower_signed} -> 0x{reconstructed:08x}"
    )
    if upper20 == 0 and lower_signed == 0:
        return ADDI(rd, 0, 0), ADDI(rd, 0, 0)
    if upper20 == 0:
        return NOP, ADDI(rd, 0, lower_signed)
    return LUI(rd, upper20), ADDI(rd, rd, lower_signed)


class Assembler:
    """Two-pass label assembler.  Labels resolve to byte PCs; ROM_BASE is the origin."""
    def __init__(self, origin: int = ROM_BASE):
        self._origin = origin
        self._items  = []
        self.labels  = {}

    def emit(self, word: int):
        self._items.append(('word', word & 0xFFFF_FFFF))

    def nop(self):
        self._items.append(('word', NOP))

    def label(self, name: str):
        self._items.append(('label', name))

    def thunk(self, fn):
        """Emit a word whose encoding depends on resolved label addresses."""
        self._items.append(('thunk', fn))

    def pad_to_word(self, word_idx: int):
        """Pad with NOPs until we are at word_idx."""
        cur = sum(1 for t, _ in self._items if t != 'label')
        assert cur <= word_idx, (
            f"pad_to_word({word_idx}): already at word {cur}"
        )
        while cur < word_idx:
            self.nop()
            cur += 1

    def resolve(self):
        self.labels = {}
        idx = 0
        for typ, val in self._items:
            if typ == 'label':
                self.labels[val] = self._origin + idx * 4
            else:
                idx += 1
        words = []
        idx = 0
        for typ, val in self._items:
            if typ == 'label':
                continue
            cur_pc = self._origin + idx * 4
            w = val(self.labels, cur_pc) & 0xFFFF_FFFF if typ == 'thunk' else val
            words.append(w)
            idx += 1
        return words


def _emit_li(asm: Assembler, rd: int, value32: int) -> None:
    lo, hi = lui_addi(rd, value32)
    asm.emit(lo)
    asm.emit(hi)


# ---------------------------------------------------------------------------
# Image A — feed, then starve (RST_EN = 0)
# ---------------------------------------------------------------------------
def build_firmware_a(asm: Assembler) -> None:
    # WORD 0 (0x1000): reset-vector trampoline
    asm.thunk(lambda lbl, pc: JAL(0, lbl["MAIN"] - pc))

    # WORD 1 (0x1004): ISR — mtvec set to here by MAIN (MODE=Direct)
    asm.label("ISR")
    _emit_li(asm, 28, WDT_BASE)
    asm.emit(LW(29, 28, WDT_OFF_STATUS))           # x29 = what this trap can see
    asm.emit(SW(29, 28, WDT_OFF_IRQ_CLR))          # W1C exactly that, nothing else
    _emit_li(asm, 30, ISR_BASE_ADDR)
    asm.emit(LW(1, 30, 0))                         # x1 = ISR_COUNT
    asm.emit(SLLI(31, 1, 2))
    asm.emit(ADD(31, 31, 30))                      # x31 = &ISR_COUNT + 4*count
    asm.emit(SW(29, 31, 4))                        # log[count] = STATUS seen
    asm.emit(ADDI(1, 1, 1))
    asm.emit(SW(1, 30, 0))                         # ISR_COUNT += 1
    # Read-back: a fabric round trip that proves the clear landed and lets the level-held IRQ
    # drain through the ext_irq 2-FF synchroniser before MRET re-enables MIE.
    asm.emit(LW(29, 28, WDT_OFF_STATUS))
    asm.emit(MRET())

    asm.pad_to_word(MAIN_START_WORDS)

    # MAIN
    asm.label("MAIN")
    _emit_li(asm, 2, WDT_BASE)
    _emit_li(asm, 3, IRQ_CTRL_BASE)
    _emit_li(asm, 4, ISR_BASE_ADDR)

    # MTVEC -> ISR
    _emit_li(asm, 1, ROM_BASE + ISR_OFFSET_WORDS * 4)
    asm.emit(CSRRW(0, 0x305, 1))   # csrw mtvec, x1

    # Zero ISR_COUNT / LOG0 / LOG1 so the teeth checks below are reliable.
    asm.emit(SW(0, 4, 0))
    asm.emit(SW(0, 4, 4))
    asm.emit(SW(0, 4, 8))

    # Arm the interrupt path BEFORE the dog is enabled.
    asm.emit(ADDI(13, 0, WDT_IRQ_MASK_BIT))
    asm.emit(SW(13, 3, IRQ_OFF_MASK))              # IRQ_MASK bit 7 (WDT)
    _emit_li(asm, 1, 0x800)
    asm.emit(CSRRW(0, 0x304, 1))                   # csrw mie, x1   (MEIE)
    asm.emit(ADDI(1, 0, 8))
    asm.emit(CSRRW(0, 0x300, 1))                   # csrw mstatus, x1 (MIE)

    asm.label("IRQ_READY")
    asm.nop()

    # CONFIGURE and enable the dog. CTRL is written last: enabling loads COUNT from RELOAD.
    asm.emit(ADDI(5, 0, PRESCALE_VAL))
    asm.emit(SW(5, 2, WDT_OFF_PRESCALE))
    asm.emit(ADDI(5, 0, RELOAD_VAL))
    asm.emit(SW(5, 2, WDT_OFF_RELOAD))
    asm.emit(ADDI(5, 0, CTRL_EN))
    asm.emit(SW(5, 2, WDT_OFF_CTRL))

    asm.label("CONFIG_DONE")
    asm.nop()

    # Poll COUNT until it has fallen to FEED_AT_COUNT (bounded).
    asm.emit(ADDI(14, 0, 0))
    asm.emit(ADDI(15, 0, WFI_POLL_LIMIT))
    asm.emit(ADDI(17, 0, FEED_AT_COUNT))
    asm.label("COUNT_POLL")
    asm.emit(LW(16, 2, WDT_OFF_COUNT))
    asm.thunk(lambda lbl, pc: BLT(17, 16, lbl["COUNT_POLL_NEXT"] - pc))   # FEED_AT < COUNT: keep polling
    asm.thunk(lambda lbl, pc: JAL(0, lbl["DO_FEED"] - pc))
    asm.label("COUNT_POLL_NEXT")
    asm.emit(ADDI(14, 14, 1))
    asm.thunk(lambda lbl, pc: BNE(14, 15, lbl["COUNT_POLL"] - pc))
    asm.thunk(lambda lbl, pc: JAL(0, lbl["FAIL"] - pc))     # COUNT never fell: counter stuck

    asm.label("DO_FEED")
    _emit_li(asm, 5, FEED_MAGIC)
    asm.emit(SW(5, 2, WDT_OFF_FEED))
    asm.label("FED")
    asm.nop()

    # The feed must have reloaded the counter: COUNT was <= FEED_AT_COUNT, so a read-back above
    # FED_MIN_COUNT can only be a reload.
    asm.emit(LW(16, 2, WDT_OFF_COUNT))
    asm.emit(ADDI(17, 0, FED_MIN_COUNT))
    asm.thunk(lambda lbl, pc: BLT(16, 17, lbl["FAIL"] - pc))
    # ... and no bark has been raised.
    asm.emit(LW(19, 2, WDT_OFF_STATUS))
    asm.thunk(lambda lbl, pc: BNE(19, 0, lbl["FAIL"] - pc))

    asm.label("FEEDING_STOPPED")
    asm.nop()

    # Wait (bounded) for both traps: bark, then bite.
    asm.emit(ADDI(14, 0, 0))
    asm.emit(ADDI(15, 0, WFI_POLL_LIMIT))
    asm.emit(ADDI(18, 0, 2))
    asm.label("TRAP_WAIT")
    asm.emit(LW(16, 4, 0))
    asm.thunk(lambda lbl, pc: BLT(16, 18, lbl["TRAP_WAIT_NEXT"] - pc))   # count < 2: keep waiting
    asm.thunk(lambda lbl, pc: JAL(0, lbl["TRAPS_DONE"] - pc))
    asm.label("TRAP_WAIT_NEXT")
    asm.emit(ADDI(14, 14, 1))
    asm.thunk(lambda lbl, pc: BNE(14, 15, lbl["TRAP_WAIT"] - pc))
    asm.thunk(lambda lbl, pc: JAL(0, lbl["FAIL"] - pc))     # dog never bit

    asm.label("TRAPS_DONE")
    # Settle: a spurious third trap (stale level-held IRQ) would land in this window.
    asm.emit(ADDI(14, 0, 0))
    asm.emit(ADDI(15, 0, 600))
    asm.label("SETTLE")
    asm.emit(ADDI(14, 14, 1))
    asm.thunk(lambda lbl, pc: BNE(14, 15, lbl["SETTLE"] - pc))

    # Teeth: exactly two traps, bark-only then bite-only.
    asm.emit(LW(17, 4, 0))
    asm.emit(ADDI(18, 0, 2))
    asm.thunk(lambda lbl, pc: BNE(17, 18, lbl["FAIL"] - pc))
    asm.emit(LW(17, 4, 4))
    asm.emit(ADDI(18, 0, 1))
    asm.thunk(lambda lbl, pc: BNE(17, 18, lbl["FAIL"] - pc))
    asm.emit(LW(17, 4, 8))
    asm.emit(ADDI(18, 0, 2))
    asm.thunk(lambda lbl, pc: BNE(17, 18, lbl["FAIL"] - pc))
    # Both W1C clears landed: STATUS reads 0 (bite is a separate terminal flop, not STATUS).
    asm.emit(LW(19, 2, WDT_OFF_STATUS))
    asm.thunk(lambda lbl, pc: BNE(19, 0, lbl["FAIL"] - pc))

    # Flush D-cache so the backdoor SRAM read at the end of the test sees the ISR's stores.
    asm.emit(CSRRW(0, 0x7C0, 0))
    asm.emit(ADDI(14, 0, 0))
    asm.emit(ADDI(15, 0, 2000))
    asm.label("FLUSH_WAIT")
    asm.emit(ADDI(14, 14, 1))
    asm.thunk(lambda lbl, pc: BNE(14, 15, lbl["FLUSH_WAIT"] - pc))

    asm.thunk(lambda lbl, pc: JAL(0, lbl["PASS"] - pc))

    asm.label("FAIL")
    asm.emit(ADDI(31, 0, -1))
    asm.emit(EBREAK())

    asm.label("PASS")
    asm.emit(ADDI(31, 0, 1))
    asm.emit(EBREAK())


# ---------------------------------------------------------------------------
# Image B — RST_EN = 1, spin until the bite resets the CPU domain
# ---------------------------------------------------------------------------
def build_firmware_b(asm: Assembler) -> None:
    asm.thunk(lambda lbl, pc: JAL(0, lbl["MAIN"] - pc))
    asm.pad_to_word(MAIN_START_WORDS)

    asm.label("MAIN")
    _emit_li(asm, 2, WDT_BASE)

    asm.emit(ADDI(5, 0, B_PRESCALE_VAL))
    asm.emit(SW(5, 2, WDT_OFF_PRESCALE))
    asm.emit(ADDI(5, 0, B_RELOAD_VAL))
    asm.emit(SW(5, 2, WDT_OFF_RELOAD))
    asm.emit(ADDI(5, 0, CTRL_EN | CTRL_RST_EN))
    asm.emit(SW(5, 2, WDT_OFF_CTRL))

    asm.label("CONFIG_DONE")
    asm.nop()

    # Spin. Every iteration commits LOOP_PC; the commit stream stopping is the CPU-domain reset.
    asm.emit(ADDI(14, 0, 0))
    asm.label("LOOP")
    asm.emit(ADDI(14, 14, 1))
    asm.thunk(lambda lbl, pc: JAL(0, lbl["LOOP"] - pc))


def _write_image(out_dir: str, name: str, asm: Assembler, required):
    words = asm.resolve()
    labels = asm.labels
    assert len(words) <= ROM_WORDS, f"{name}: firmware too large: {len(words)} words > {ROM_WORDS}"
    for req in required:
        assert req in labels, f"{name}: label {req!r} not found in {list(labels)}"
    padded = list(words) + [NOP] * (ROM_WORDS - len(words))
    path = os.path.join(out_dir, name)
    with open(path, 'w') as f:
        for w in padded:
            f.write(f'{w:08x}\n')
    print(f"Wrote {len(padded)} words to {path}")
    return labels


def main():
    out_dir = os.path.dirname(os.path.abspath(__file__))

    asm_a = Assembler(origin=ROM_BASE)
    build_firmware_a(asm_a)
    la = _write_image(out_dir, 'wdt_fw.hex', asm_a,
                      ('ISR', 'MAIN', 'FAIL', 'PASS', 'IRQ_READY', 'CONFIG_DONE', 'FED',
                       'FEEDING_STOPPED'))

    asm_b = Assembler(origin=ROM_BASE)
    build_firmware_b(asm_b)
    lb = _write_image(out_dir, 'wdt_rst_fw.hex', asm_b, ('MAIN', 'CONFIG_DONE', 'LOOP'))

    addrs_path = os.path.join(out_dir, 'wdt_fw_addrs.py')
    with open(addrs_path, 'w') as f:
        f.write("# Auto-generated by gen_wdt_hex.py — do not edit.\n")
        f.write("# ---- image A: wdt_fw.hex (feed, then starve; RST_EN = 0) ----\n")
        f.write(f"PASS_PC         = 0x{la['PASS']:08x}\n")
        f.write(f"FAIL_PC         = 0x{la['FAIL']:08x}\n")
        f.write(f"ISR_PC          = 0x{la['ISR']:08x}\n")
        f.write(f"IRQ_READY_PC    = 0x{la['IRQ_READY']:08x}\n")
        f.write(f"CONFIG_DONE_PC  = 0x{la['CONFIG_DONE']:08x}\n")
        f.write(f"FED_PC          = 0x{la['FED']:08x}\n")
        f.write(f"FEEDING_STOPPED_PC = 0x{la['FEEDING_STOPPED']:08x}\n")
        f.write(f"PRESCALE_VAL    = {PRESCALE_VAL}\n")
        f.write(f"RELOAD_VAL      = {RELOAD_VAL}\n")
        f.write(f"PERIOD_CYCLES   = {PERIOD_CYCLES}\n")
        f.write(f"ISR_COUNT_WI    = {ISR_COUNT_WI}\n")
        f.write(f"ISR_LOG0_WI     = {ISR_LOG0_WI}\n")
        f.write(f"ISR_LOG1_WI     = {ISR_LOG1_WI}\n")
        f.write("# ---- image B: wdt_rst_fw.hex (RST_EN = 1; bite resets the CPU domain) ----\n")
        f.write(f"B_CONFIG_DONE_PC = 0x{lb['CONFIG_DONE']:08x}\n")
        f.write(f"B_LOOP_PC        = 0x{lb['LOOP']:08x}\n")
        f.write(f"B_PERIOD_CYCLES  = {B_PERIOD_CYCLES}\n")
    print(f"Wrote {addrs_path}")


if __name__ == '__main__':
    main()
