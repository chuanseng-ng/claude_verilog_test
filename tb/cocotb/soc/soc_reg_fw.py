"""
soc_reg_fw.py -- CPU firmware for the SoC-level register walk (bead claude_verilog_test-7ovx).

The unit-level walks (reg_walk.py) drive each peripheral's APB face directly.  This module builds
the same walk as RV32I firmware so every access travels the real path

  CPU -> axi4_crossbar -> axi4_to_axilite -> axi_lite_interconnect -> axil_to_apb
      -> apb_interconnect (-> apb_cdc_bridge for the PLLs) -> peripheral

and the fabric data and address buses (soc_bus, axil, apb) see the walking-ones / alternating
patterns and every peripheral window address, which no existing SoC test does (they write small
values to a few offsets).

The firmware is GENERATED at test time from the SAME `reg_maps` tables the unit walks use and
loaded into the boot ROM through the testbench backdoor, exactly like the hex images of the other
SoC suites; there is no committed binary, so nothing can go stale against the register map.

Per table entry [addr, drive, wmask, check] (4 words), for each pattern p:
    w = p & drive;  *addr = w;  rb = *addr;
    model = ((model & ~wmask) | (w & wmask)) & check;   fail if (rb ^ model) & check
model is seeded from the first read of the register (the unit suites already proved the reset
values; here the question is whether the value survives the fabric).  Entries flagged "lanes" are
also walked with SB stores, so the AXI4/AXI-Lite wstrb and APB pstrb lanes toggle.  Every register
is restored to the value first read.

Result protocol (self-checking, same as the other SoC firmware): x31 = 1 at PASS_PC, -1 at FAIL_PC
(both EBREAK, which halts the CPU so the testbench can read the registers over the debug APB):
    x30 = number of failing checks
    x26..x29 = first failure: address, value written, value read, value expected
"""

from __future__ import annotations

import os
import sys

_PROJ_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if _PROJ_ROOT not in sys.path:
    sys.path.insert(0, _PROJ_ROOT)

from sim.riscv_encoder import (  # noqa: E402
    ADDI, AND, BEQ, BNE, EBREAK, JAL, JALR, LUI, LW, OR, SB, SW, XOR, XORI,
)
from tb.cocotb.soc.gpio_fw.gen_gpio_hex import Assembler, lui_addi  # noqa: E402

import reg_maps  # noqa: E402
from reg_walk import M32, SHORT_PATTERNS, WALKING_ONES, CONST_PATTERNS  # noqa: E402

ROM_BASE = 0x0000_1000
ROM_WORDS = 1024
UNMAPPED_OFFSETS = (0x100, 0x400, 0x800, 0xFFC)


def _br(asm, op, rs1, rs2, target):
    asm.thunk(lambda lbl, pc, op=op, a=rs1, b=rs2, t=target: op(a, b, lbl[t] - pc))


def _jmp(asm, target):
    asm.thunk(lambda lbl, pc, t=target: JAL(0, lbl[t] - pc))


def _li(asm, rd, value):
    lo, hi = lui_addi(rd, value)
    asm.emit(lo)
    asm.emit(hi)


def _la(asm, rd, label):
    """rd = absolute address of `label` (always two words so label offsets are stable)."""
    def upper(lbl, pc, rd=rd, label=label):
        v = lbl[label]
        up = ((v + 0x800) >> 12) & 0xFFFFF
        return LUI(rd, up)

    def lower(lbl, pc, rd=rd, label=label):
        v = lbl[label]
        lo = v & 0xFFF
        lo = lo - 0x1000 if lo >= 0x800 else lo
        return ADDI(rd, rd, lo)

    asm.thunk(upper)
    asm.thunk(lower)


# ---------------------------------------------------------------------------------------------
# Entry construction
# ---------------------------------------------------------------------------------------------
def soc_entries():
    """Return (full, short): lists of (name, addr, drive, wmask, check, lanes).

    `full` entries get the full pattern set plus SB lane stores; `short` entries the short set.
    SoC-level adjustments to the unit tables are listed here, each with its reason:
      * interrupt_controller STATUS / PENDING_MASKED are live: at SoC level they mirror the
        other peripherals' IRQ lines, which the walk itself moves (GPIO_IRQ_EN, PWM_IRQ_EN ...).
        Their RO behaviour is checked at unit level.
      * PLL1 / PLL2 are the same pll_apb_regs, reached through the apb_cdc_bridge toggle
        handshake instead of directly.
    """
    banks = [
        ("timer", reg_maps.TIMER), ("uart", reg_maps.UART), ("spi", reg_maps.SPI),
        ("irq", reg_maps.irq_regs(12)), ("pll1", reg_maps.PLL), ("pmu", reg_maps.PMU),
        ("pll2", reg_maps.PLL), ("gpio", reg_maps.GPIO), ("pwm", reg_maps.PWM),
        ("wdt", reg_maps.WDT), ("trng", reg_maps.TRNG), ("i2c", reg_maps.I2C),
        ("crypto", reg_maps.CRYPTO), ("npu", reg_maps.NPU),
    ]
    full, short = [], []
    for bank, regs in banks:
        base = reg_maps.SOC_BASE[bank]
        for r in regs:
            if r.skip is not None:
                continue
            live = r.live
            if bank == "irq" and r.wmask == 0:
                live = M32
            check = ~live & M32
            ent = (f"{bank}.{r.name}", base + r.offset, r.drive, r.wmask, check, False)
            if r.name in reg_maps.SOC_FULL:
                assert r.drive == M32, f"{r.name}: lane stores need a fully driven register"
                full.append(ent[:5] + (True,))
            else:
                short.append(ent)
    # Unmapped words inside each 4 KB window (the banks hold 3..32 registers): reads must be 0 and
    # writes dropped.  Through the fabric these also toggle the high paddr bits [11:8], which no
    # mapped register offset reaches.
    for bank, _regs in banks:
        base = reg_maps.SOC_BASE[bank]
        for off in UNMAPPED_OFFSETS:
            short.append((f"{bank}.unmapped", base + off, M32, 0, M32, False))
    return full, short


# ---------------------------------------------------------------------------------------------
# Firmware
# ---------------------------------------------------------------------------------------------
def _emit_compare(asm, tag):
    """Compare x22 (read) against x19 (model) under x17 (check); on mismatch bump x30 and keep
    the first failure's evidence in x26..x29 (x21 = value written)."""
    asm.emit(XOR(24, 22, 19))
    asm.emit(AND(24, 24, 17))
    _br(asm, BEQ, 24, 0, f"{tag}_OK")
    asm.emit(ADDI(30, 30, 1))
    _br(asm, BNE, 26, 0, f"{tag}_OK")
    asm.emit(ADDI(26, 14, 0))
    asm.emit(ADDI(27, 21, 0))
    asm.emit(ADDI(28, 22, 0))
    asm.emit(ADDI(29, 19, 0))
    asm.label(f"{tag}_OK")


def _emit_model_update(asm):
    """x19 = ((x19 & ~x16) | (x21 & x16)) & x17."""
    asm.emit(XORI(23, 16, -1))
    asm.emit(AND(23, 19, 23))
    asm.emit(AND(24, 21, 16))
    asm.emit(OR(23, 23, 24))
    asm.emit(AND(19, 23, 17))


def build_firmware():
    """Return (words, labels, n_entries).  ROM image starting at ROM_BASE."""
    full, short = soc_entries()
    asm = Assembler(origin=ROM_BASE)

    # word 0: reset-vector trampoline; word 1: any trap is a failure.
    asm.thunk(lambda lbl, pc: JAL(0, lbl["MAIN"] - pc))
    asm.label("TRAP")
    asm.emit(ADDI(31, 0, -1))
    asm.emit(EBREAK())

    # ---- MAIN ---------------------------------------------------------------------------
    asm.label("MAIN")
    asm.emit(ADDI(30, 0, 0))
    asm.emit(ADDI(26, 0, 0))
    _la(asm, 10, "TAB_FULL")
    _la(asm, 11, "TAB_FULL_END")
    _la(asm, 12, "PAT_FULL")
    _la(asm, 13, "PAT_FULL_END")
    asm.emit(ADDI(9, 0, 1))                 # x9 = lane phase on
    asm.thunk(lambda lbl, pc: JAL(1, lbl["WALK"] - pc))
    _la(asm, 10, "TAB_SHORT")
    _la(asm, 11, "TAB_SHORT_END")
    _la(asm, 12, "PAT_SHORT")
    _la(asm, 13, "PAT_SHORT_END")
    asm.emit(ADDI(9, 0, 0))
    asm.thunk(lambda lbl, pc: JAL(1, lbl["WALK"] - pc))
    _br(asm, BNE, 30, 0, "FAIL")
    asm.label("PASS")
    asm.emit(ADDI(31, 0, 1))
    asm.emit(EBREAK())
    asm.label("FAIL")
    asm.emit(ADDI(31, 0, -1))
    asm.emit(EBREAK())

    # ---- WALK(x10 table, x11 table end, x12 patterns, x13 pattern end, x9 lanes) ---------------
    asm.label("WALK")
    asm.label("ENTRY")
    _br(asm, BEQ, 10, 11, "WALK_DONE")
    asm.emit(LW(14, 10, 0))                 # addr
    asm.emit(LW(15, 10, 4))                 # drive
    asm.emit(LW(16, 10, 8))                 # wmask
    asm.emit(LW(17, 10, 12))                # check
    asm.emit(LW(18, 14, 0))                 # first read
    asm.emit(AND(19, 18, 17))               # model
    asm.emit(ADDI(20, 12, 0))               # pattern pointer
    asm.label("PAT")
    _br(asm, BEQ, 20, 13, "PAT_DONE")
    asm.emit(LW(21, 20, 0))
    asm.emit(AND(21, 21, 15))               # w = p & drive
    asm.emit(SW(21, 14, 0))
    asm.emit(LW(22, 14, 0))
    _emit_model_update(asm)
    _emit_compare(asm, "PC")
    asm.emit(ADDI(20, 20, 4))
    _jmp(asm, "PAT")
    asm.label("PAT_DONE")
    # ---- byte lanes (fully driven registers only): SW 0, then SB 0xFF into each lane ----------
    _br(asm, BEQ, 9, 0, "LANES_DONE")
    asm.emit(ADDI(21, 0, 0))
    asm.emit(SW(21, 14, 0))
    asm.emit(LW(22, 14, 0))
    _emit_model_update(asm)
    _emit_compare(asm, "LZ")
    for k in range(4):
        asm.emit(ADDI(21, 0, 0xFF))
        asm.emit(SB(21, 14, k))
        asm.emit(LW(22, 14, 0))
        # model |= (0xFF << 8k) & wmask, kept inside check
        _li(asm, 23, 0xFF << (8 * k))
        asm.emit(AND(23, 23, 16))
        asm.emit(OR(19, 19, 23))
        asm.emit(AND(19, 19, 17))
        asm.emit(XOR(24, 22, 19))
        asm.emit(AND(24, 24, 17))
        _br(asm, BEQ, 24, 0, f"LB{k}_OK")
        asm.emit(ADDI(30, 30, 1))
        _br(asm, BNE, 26, 0, f"LB{k}_OK")
        asm.emit(ADDI(26, 14, k))
        asm.emit(ADDI(27, 21, 0))
        asm.emit(ADDI(28, 22, 0))
        asm.emit(ADDI(29, 19, 0))
        asm.label(f"LB{k}_OK")
    asm.label("LANES_DONE")
    asm.emit(AND(21, 18, 15))               # restore the first-read value (drive-masked)
    asm.emit(SW(21, 14, 0))
    asm.emit(ADDI(10, 10, 16))
    _jmp(asm, "ENTRY")
    asm.label("WALK_DONE")
    asm.emit(JALR(0, 1, 0))

    # ---- data ----------------------------------------------------------------------------
    asm.label("PAT_FULL")
    for p in WALKING_ONES + CONST_PATTERNS:
        asm.emit(p)
    asm.label("PAT_FULL_END")
    asm.label("PAT_SHORT")
    for p in SHORT_PATTERNS:
        asm.emit(p)
    asm.label("PAT_SHORT_END")
    asm.label("TAB_FULL")
    for _n, addr, drive, wmask, check, _l in full:
        for w in (addr, drive, wmask, check):
            asm.emit(w)
    asm.label("TAB_FULL_END")
    asm.label("TAB_SHORT")
    for _n, addr, drive, wmask, check, _l in short:
        for w in (addr, drive, wmask, check):
            asm.emit(w)
    asm.label("TAB_SHORT_END")

    words = asm.resolve()
    assert len(words) <= ROM_WORDS, f"image is {len(words)} words, ROM holds {ROM_WORDS}"
    return words, dict(asm.labels), len(full) + len(short)


def entry_name_for(addr: int) -> str:
    full, short = soc_entries()
    for n, a, *_ in full + short:
        if a == addr & ~3:
            return n + (f"+{addr & 3}" if addr & 3 else "")
    return f"0x{addr:08x}"


if __name__ == "__main__":
    w, lbl, n = build_firmware()
    print(f"{len(w)} words, {n} table entries, PASS=0x{lbl['PASS']:x} FAIL=0x{lbl['FAIL']:x}")
