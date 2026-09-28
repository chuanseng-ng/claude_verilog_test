#!/usr/bin/env python3
"""
gen_pwm_hex.py — generate pwm_fw.hex for the Phase 6a-2 SoC-level PWM test
(bead claude_verilog_test-f7vs.6 item 5, docs/PHASE6_IP_EXPANSION_PLAN.md §10).

Modelled directly on gpio_fw/gen_gpio_hex.py — same Assembler/lui_addi/CSRRW/MRET
machinery, same commit_pc_o marker-PC synchronisation idiom, same ISR register
convention (x28-x31, x1 scratch). See that file's header for the general pattern;
this header covers only what differs for PWM.

Path exercised (confirmed from soc_top.sv):
  CPU --AXI4--> axi4_crossbar --AXI4--> axi4_to_axilite --AXI-Lite-->
  axi_lite_interconnect --AXI-Lite--> axil_to_apb --APB4--> apb_interconnect
  --APB4--> APB_PWM slave 8 (pwm_controller, base 0x2000_B000)

PWM register map (rtl/periph/pwm_controller.sv, word indices):
  +0x00 PWM_CTRL      RW  [3:0] per-channel enable, [7:4] per-channel polarity
  +0x04 PWM_PERIOD    RW  [15:0] shared period, in prescaled ticks
  +0x08 PWM_PRESCALE  RW  [15:0] core_clk divider; one tick = (PRESCALE+1) cycles
  +0x0C PWM_DUTY01    RW  [15:0] ch0 duty, [31:16] ch1 duty
  +0x10 PWM_DUTY23    RW  [15:0] ch2 duty, [31:16] ch3 duty
  +0x14 PWM_IRQ_EN    RW  [3:0] per-channel period-wrap IRQ enable
  +0x18 PWM_IRQ_STAT  RO  [3:0] sticky per-channel period-wrap
  +0x1C PWM_IRQ_CLR   W1C always reads 0
  +0x20 first out-of-range word (N_REGS=8) — read must return 0

Unlike gpio_fw, PWM needs no cocotb-driven stimulus at all: pwm_o is a pure
push-pull output (no oe, no async input — see pwm_controller.sv header), and
the period-wrap interrupt is generated entirely by the peripheral's own free-
running counters once channel 0 is configured and enabled. So there is only
one cocotb synchronisation point instead of gpio_fw's three:

  Phase 1 (CONFIG): firmware programs PRESCALE/PERIOD/DUTY01/CTRL (channel 0
    enabled, active-high) then commits CONFIG_DONE_PC. From that point on,
    pwm_o[0] free-runs at the SoC boundary with period
    PERIOD_VAL * (PRESCALE_VAL + 1) core_clk cycles — cocotb watches this
    directly on the tb_soc_top port with no firmware/testbench handshake
    needed, unlike gpio_fw's OUTPUT_DONE_PC single-sample check.

  Phase 2 (INTERRUPT, end to end): firmware unmasks the channel-0 period-wrap
    IRQ (PWM_IRQ_EN bit 0), unmasks bit 6 (PWM) in interrupt_controller's
    IRQ_MASK (base 0x2000_6000), enables MEIE/MIE, commits IRQ_READY_PC, and
    enters a bounded WFI-style poll loop on an ISR_FLAG word in SRAM — the
    period-wrap event fires on its own; no cocotb stimulus is required. The
    ISR (installed at mtvec = ISR_PC) FIRST disables channel 0 entirely
    (PWM_CTRL = 0), which stops the free-running counters from ever wrapping
    again, THEN clears PWM_IRQ_CLR bit 0. Disabling the channel before
    clearing status (rather than just clearing IRQ_EN, which only masks
    irq_o) closes a real race: every MMIO access in this firmware crosses the
    full fabric (CPU -> crossbar -> axi4_to_axilite -> axi_lite_interconnect
    -> axil_to_apb -> apb_interconnect), so two back-to-back peripheral
    writes can together take longer than one PWM_PERIOD_CYCLES period
    (80 cycles here) — a naive "clear status, then mask enable" order was
    observed to let a second period-wrap re-set PWM_IRQ_STAT before the
    enable-mask write landed, re-asserting irq_o. Disabling the channel makes
    a second wrap structurally impossible regardless of write latency. The
    ISR then increments ISR_COUNT, sets ISR_FLAG, and MRETs. Firmware then
    teeth-checks ISR_COUNT == 1 exactly and PWM_IRQ_STAT bit 0 == 0 (cleared
    by the ISR's PWM_IRQ_CLR write). The cocotb test independently watches
    commit_pc_o for ISR_PC (proof the CPU actually took the trap) and
    directly samples the internal pwm_irq / ext_irq nets before and after the
    ISR runs (proof of deassertion at the RTL level, not just firmware
    self-report) — same technique as test_soc_gpio.py.

  Phase 3 (register-bank policy, cheap teeth checks): PWM_IRQ_CLR always
  reads 0; a read at word index 8 (first out-of-range offset, +0x20) returns
  0 (apb4_register_bank's documented drop/return-0 OOR policy).

Both PWM_BASE and IRQ_CTRL_BASE have bits[11:0]=0, so no LUI sign-extension
compensation is needed for them (see gpio_fw's header) — lui_addi() handles
the general case regardless.

Register allocation (MAIN):
  x1  = scratch (LUI/ADDI temporaries, CSR value staging)
  x2  = PWM_BASE         0x2000_B000
  x3  = IRQ_CTRL_BASE    0x2000_6000
  x4  = ISR_FLAG_ADDR    (SRAM, word ISR_FLAG_WI)
  x5  = scratch (write patterns)
  x11 = channel-0 mask (1) — held live for the post-ISR teeth check
  x13 = scratch (IRQ_MASK bit-6 value)
  x14 = poll counter (WFI loop)
  x15 = poll limit (WFI loop)
  x16 = scratch (ISR_FLAG readback)
  x17 = scratch (ISR_COUNT readback)
  x18 = scratch (expected constant for ISR_COUNT compare)
  x19 = scratch (PWM_IRQ_STAT readback / masked)
  x20 = scratch (PWM_IRQ_CLR readback)
  x21 = scratch (out-of-range readback)
  x31 = result marker (1 = pass, -1 = fail)

Register allocation (ISR, at ISR_PC = ROM_BASE + 4):
  x28 = PWM_BASE (reconstructed independently of MAIN's x2, matching gpio_fw's
        convention — ISR runs with MIE cleared, but MAIN's registers are still
        architecturally live; rebuilding is defensive)
  x29 = scratch (channel-0 mask / IRQ_CLR write value)
  x30 = SRAM ISR_FLAG_ADDR (rebuilt in the ISR)
  x31 = scratch (constant 1 / ISR_COUNT staging)
  x1  = scratch (ISR_COUNT readback)
"""

import os
import sys

_PROJ_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))
if _PROJ_ROOT not in sys.path:
    sys.path.insert(0, _PROJ_ROOT)

from sim.riscv_encoder import (
    LUI, ADDI, SW, LW, BNE, JAL, EBREAK, AND,
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
PWM_BASE            = 0x2000_B000
PWM_OFF_CTRL         = 0x00
PWM_OFF_PERIOD       = 0x04
PWM_OFF_PRESCALE     = 0x08
PWM_OFF_DUTY01       = 0x0C
PWM_OFF_DUTY23       = 0x10
PWM_OFF_IRQ_EN       = 0x14
PWM_OFF_IRQ_STAT     = 0x18
PWM_OFF_IRQ_CLR      = 0x1C
PWM_OFF_OOR          = 0x20   # word index 8 — first out-of-range offset (N_REGS=8)

IRQ_CTRL_BASE       = 0x2000_6000
IRQ_OFF_STATUS      = 0x000
IRQ_OFF_MASK        = 0x004
IRQ_OFF_PENDING     = 0x008
PWM_IRQ_MASK_BIT    = 0x40   # interrupt_controller.irq_src_i[6] = PWM slot

SRAM_BASE           = 0x0000_2000
ISR_FLAG_WI         = 310   # SRAM word 310 = byte 0x0000_24D8
ISR_COUNT_WI        = 311   # SRAM word 311 = byte 0x0000_24DC
ISR_FLAG_ADDR       = SRAM_BASE + ISR_FLAG_WI * 4

# ---------------------------------------------------------------------------
# Test-pattern constants (all fit as small positive 12-bit ADDI immediates,
# so no lui_addi() is needed for any of them)
# ---------------------------------------------------------------------------
PRESCALE_VAL = 3    # one tick = 4 core_clk cycles
PERIOD_VAL   = 20   # ticks per period
DUTY_VAL     = 8    # ch0 duty, in ticks (40% of PERIOD_VAL)
CTRL_VAL     = 0x01 # channel 0 enabled, active-high (polarity bit4 = 0)
IRQ_EN_VAL   = 0x01 # channel 0 period-wrap IRQ enabled

PERIOD_CYCLES = PERIOD_VAL * (PRESCALE_VAL + 1)   # full period, in core_clk cycles

WFI_POLL_LIMIT = 4000  # generous vs. several period-wrap waits (80 cycles/period)


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


# ---------------------------------------------------------------------------
# Firmware
# ---------------------------------------------------------------------------
def build_firmware(asm: Assembler) -> None:
    # =========================================================================
    # WORD 0 (0x1000): reset-vector trampoline
    # =========================================================================
    asm.thunk(lambda lbl, pc: JAL(0, lbl["MAIN"] - pc))

    # =========================================================================
    # WORD 1 (0x1004): ISR — mtvec set to here by MAIN (MODE=Direct)
    # =========================================================================
    asm.label("ISR")

    l28, a28 = lui_addi(28, PWM_BASE)
    asm.emit(l28); asm.emit(a28)

    # Disable channel 0 FIRST (write 0 to PWM_CTRL) — stops the free-running
    # counters from ever wrapping again, so there is no window in which a
    # second wrap can re-set PWM_IRQ_STAT while this ISR's own MMIO writes
    # are still in flight across the fabric (see header rationale). Must
    # come before the PWM_IRQ_CLR write below, not after.
    asm.emit(SW(0, 28, PWM_OFF_CTRL))

    asm.emit(ADDI(29, 0, 1))                       # x29 = channel-0 mask

    # Clear the sticky wrap-event status bit for channel 0.
    asm.emit(SW(29, 28, PWM_OFF_IRQ_CLR))

    l30, a30 = lui_addi(30, ISR_FLAG_ADDR)
    asm.emit(l30); asm.emit(a30)

    # ISR_FLAG = 1
    asm.emit(ADDI(31, 0, 1))
    asm.emit(SW(31, 30, 0))

    # ISR_COUNT += 1  (word at ISR_FLAG_ADDR + 4)
    asm.emit(LW(1, 30, 4))
    asm.emit(ADDI(1, 1, 1))
    asm.emit(SW(1, 30, 4))

    asm.emit(MRET())

    asm.pad_to_word(MAIN_START_WORDS)

    # =========================================================================
    # MAIN FIRMWARE
    # =========================================================================
    asm.label("MAIN")

    l2, a2 = lui_addi(2, PWM_BASE)
    asm.emit(l2); asm.emit(a2)

    l3, a3 = lui_addi(3, IRQ_CTRL_BASE)
    asm.emit(l3); asm.emit(a3)

    l4, a4 = lui_addi(4, ISR_FLAG_ADDR)
    asm.emit(l4); asm.emit(a4)

    # ── MTVEC: point at the ISR (word 1 = ROM_BASE+4, MODE=0 Direct) ─────────
    ISR_PC_VAL = ROM_BASE + ISR_OFFSET_WORDS * 4
    l1, a1 = lui_addi(1, ISR_PC_VAL)
    asm.emit(l1); asm.emit(a1)
    asm.emit(CSRRW(0, 0x305, 1))   # csrw mtvec, x1

    # Zero ISR_FLAG / ISR_COUNT so the teeth checks below are reliable.
    asm.emit(SW(0, 4, 0))
    asm.emit(SW(0, 4, 4))

    # x11 = channel-0 mask, held live for the post-ISR teeth check below.
    asm.emit(ADDI(11, 0, 1))

    # =========================================================================
    # PHASE 1 — CONFIGURE (period/prescale/duty/enable channel 0)
    # =========================================================================
    asm.emit(ADDI(5, 0, PRESCALE_VAL))
    asm.emit(SW(5, 2, PWM_OFF_PRESCALE))
    asm.emit(ADDI(5, 0, PERIOD_VAL))
    asm.emit(SW(5, 2, PWM_OFF_PERIOD))
    asm.emit(ADDI(5, 0, DUTY_VAL))
    asm.emit(SW(5, 2, PWM_OFF_DUTY01))
    asm.emit(ADDI(5, 0, CTRL_VAL))
    asm.emit(SW(5, 2, PWM_OFF_CTRL))

    asm.label("CONFIG_DONE")
    asm.nop()

    # =========================================================================
    # PHASE 2 — INTERRUPT PATH, end to end (channel 0 free-runs; no cocotb
    # stimulus needed — the period-wrap event is entirely peripheral-internal)
    # =========================================================================
    asm.emit(ADDI(5, 0, IRQ_EN_VAL))
    asm.emit(SW(5, 2, PWM_OFF_IRQ_EN))

    # Unmask bit 6 (PWM) in interrupt_controller's IRQ_MASK
    asm.emit(ADDI(13, 0, PWM_IRQ_MASK_BIT))
    asm.emit(SW(13, 3, IRQ_OFF_MASK))

    # Enable MEIE (mie bit 11) and MIE (mstatus bit 3)
    l1b, a1b = lui_addi(1, 0x800)
    asm.emit(l1b); asm.emit(a1b)
    asm.emit(CSRRW(0, 0x304, 1))   # csrw mie, x1
    asm.emit(ADDI(1, 0, 8))
    asm.emit(CSRRW(0, 0x300, 1))   # csrw mstatus, x1

    asm.label("IRQ_READY")
    asm.nop()

    # WFI-style bounded poll on ISR_FLAG (x4 = ISR_FLAG_ADDR)
    asm.emit(ADDI(14, 0, 0))
    asm.emit(ADDI(15, 0, WFI_POLL_LIMIT))

    asm.label("WFI_LOOP")
    asm.emit(LW(16, 4, 0))
    asm.thunk(lambda lbl, pc: BNE(16, 0, lbl["ISR_DONE"] - pc))
    asm.emit(ADDI(14, 14, 1))
    asm.thunk(lambda lbl, pc: BNE(14, 15, lbl["WFI_LOOP"] - pc))
    asm.thunk(lambda lbl, pc: JAL(0, lbl["FAIL"] - pc))   # ISR never fired

    asm.label("ISR_DONE")

    # Teeth check 1: ISR_COUNT must be exactly 1 — a stuck-asserted interrupt
    # (IRQ_EN not really cleared, or a deassertion bug) would immediately
    # re-vector after MRET re-enables MIE, incrementing ISR_COUNT again
    # before firmware gets here.
    asm.emit(LW(17, 4, 4))
    asm.emit(ADDI(18, 0, 1))
    asm.thunk(lambda lbl, pc: BNE(17, 18, lbl["FAIL"] - pc))

    # Teeth check 2: PWM_IRQ_STAT bit 0 must read 0 (cleared by the ISR's
    # PWM_IRQ_CLR write; the ISR disabled channel 0 via PWM_CTRL first, so
    # no further wrap event can ever set the bit again).
    asm.emit(LW(19, 2, PWM_OFF_IRQ_STAT))
    asm.emit(AND(19, 19, 11))
    asm.thunk(lambda lbl, pc: BNE(19, 0, lbl["FAIL"] - pc))

    # =========================================================================
    # PHASE 3 — register-bank policy checks
    # =========================================================================
    # PWM_IRQ_CLR always reads 0 (WMASK=0, no hw_wen path — see pwm_controller.sv)
    asm.emit(LW(20, 2, PWM_OFF_IRQ_CLR))
    asm.thunk(lambda lbl, pc: BNE(20, 0, lbl["FAIL"] - pc))

    # First out-of-range word (index 8, N_REGS=8) reads 0 per
    # apb4_register_bank.sv's documented OOR policy.
    asm.emit(LW(21, 2, PWM_OFF_OOR))
    asm.thunk(lambda lbl, pc: BNE(21, 0, lbl["FAIL"] - pc))

    # Flush D-cache: the ISR's SW to ISR_COUNT (SRAM, a cached region) may
    # still be dirty in the D-cache, invisible to cocotb's backdoor SRAM-array
    # read at the end of the test. Same rationale as gpio_fw's flush.
    asm.emit(CSRRW(0, 0x7C0, 0))
    asm.emit(ADDI(14, 0, 0))
    asm.emit(ADDI(15, 0, 2000))
    asm.label("FLUSH_WAIT")
    asm.emit(ADDI(14, 14, 1))
    asm.thunk(lambda lbl, pc: BNE(14, 15, lbl["FLUSH_WAIT"] - pc))

    asm.thunk(lambda lbl, pc: JAL(0, lbl["PASS"] - pc))

    # ── FAIL ──────────────────────────────────────────────────────────────────
    asm.label("FAIL")
    asm.emit(ADDI(31, 0, -1))
    asm.emit(EBREAK())

    # ── PASS ──────────────────────────────────────────────────────────────────
    asm.label("PASS")
    asm.emit(ADDI(31, 0, 1))
    asm.emit(EBREAK())


def main():
    out_dir = os.path.dirname(os.path.abspath(__file__))

    asm = Assembler(origin=ROM_BASE)
    build_firmware(asm)
    words = asm.resolve()
    labels = asm.labels

    assert len(words) <= ROM_WORDS, (
        f"Firmware too large: {len(words)} words > {ROM_WORDS}"
    )

    for req in ('ISR', 'MAIN', 'FAIL', 'PASS', 'CONFIG_DONE', 'IRQ_READY',
                'WFI_LOOP', 'ISR_DONE'):
        assert req in labels, f"Label {req!r} not found in: {list(labels)}"

    pass_pc         = labels['PASS']
    fail_pc         = labels['FAIL']
    isr_pc          = labels['ISR']
    main_pc         = labels['MAIN']
    config_done_pc  = labels['CONFIG_DONE']
    irq_ready_pc    = labels['IRQ_READY']

    print(f"ISR_PC          = 0x{isr_pc:08x}")
    print(f"MAIN_PC         = 0x{main_pc:08x}")
    print(f"CONFIG_DONE_PC  = 0x{config_done_pc:08x}")
    print(f"IRQ_READY_PC    = 0x{irq_ready_pc:08x}")
    print(f"FAIL_PC         = 0x{fail_pc:08x}")
    print(f"PASS_PC         = 0x{pass_pc:08x}")

    padded_fw = list(words) + [NOP] * (ROM_WORDS - len(words))
    fw_path = os.path.join(out_dir, 'pwm_fw.hex')
    with open(fw_path, 'w') as f:
        for w in padded_fw:
            f.write(f'{w:08x}\n')
    print(f"\nWrote {len(padded_fw)} words to {fw_path}")

    addrs_path = os.path.join(out_dir, 'pwm_fw_addrs.py')
    with open(addrs_path, 'w') as f:
        f.write("# Auto-generated by gen_pwm_hex.py — do not edit.\n")
        f.write(f"PASS_PC         = 0x{pass_pc:08x}\n")
        f.write(f"FAIL_PC         = 0x{fail_pc:08x}\n")
        f.write(f"ISR_PC          = 0x{isr_pc:08x}\n")
        f.write(f"CONFIG_DONE_PC  = 0x{config_done_pc:08x}\n")
        f.write(f"IRQ_READY_PC    = 0x{irq_ready_pc:08x}\n")
        f.write(f"PRESCALE_VAL    = {PRESCALE_VAL}\n")
        f.write(f"PERIOD_VAL      = {PERIOD_VAL}\n")
        f.write(f"DUTY_VAL        = {DUTY_VAL}\n")
        f.write(f"CTRL_VAL        = 0x{CTRL_VAL:08x}\n")
        f.write(f"PERIOD_CYCLES   = {PERIOD_CYCLES}\n")
        f.write(f"ISR_FLAG_WI     = {ISR_FLAG_WI}\n")
        f.write(f"ISR_COUNT_WI    = {ISR_COUNT_WI}\n")
        f.write(f"WFI_POLL_LIMIT  = {WFI_POLL_LIMIT}\n")
    print(f"Wrote {addrs_path}")


if __name__ == '__main__':
    main()
