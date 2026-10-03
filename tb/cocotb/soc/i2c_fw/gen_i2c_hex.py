#!/usr/bin/env python3
"""
gen_i2c_hex.py — generate i2c_fw.hex and i2c_fw_addrs.py for the Phase 6a-5 SoC-level I2C FABRIC
test (bead claude_verilog_test-f7vs.9, docs/PHASE6_IP_EXPANSION_PLAN.md §7 "6a-5 -- I2C" / L2).

Scope, deliberately small. The L1 suite (test_i2c.py, `make i2c`) owns every protocol behaviour,
with a real bus BFM. At the SoC suites' CLK_PERIOD_NS = 2 a full protocol BFM over thousands of
cycles is expensive and brittle, so this image only proves the FABRIC PATH, using the DUT's internal
loopback (I2C_CTRL[1], the SPI_CTRL[4] precedent). No bus BFM, no protocol traffic at this level.

Path exercised (soc_top.sv):
  CPU --AXI4--> axi4_crossbar --AXI4--> axi4_to_axilite --AXI-Lite-->
  axi_lite_interconnect --AXI-Lite--> axil_to_apb --APB4--> apb_interconnect
  --APB4--> APB_I2C slave 11 (i2c_controller, base 0x2000_E000)
  i2c_controller.irq_o --> interrupt_controller.irq_src_i[9] --> ext_irq --> CPU MEIP

Reuses the pure-Python hand-assembler of trng_fw/gen_trng_hex.py (same Assembler / lui_addi /
CSRRW / MRET machinery) — no riscv32 cross toolchain, so the suite is CI-safe (a toolchain-dependent
suite in soc_all_ci is what broke PR #195). Synchronisation and scoring are by commit_pc_o marker
PCs.

I2C register map (rtl/periph/i2c_controller.sv, word indices):
  +0x00 CTRL (EN[0] LOOPBACK[1])  +0x04 STATUS  +0x08 CLKDIV (reset 0xFF)  +0x0C ADDR ([7] R/W)
  +0x10 TX_DATA (push)  +0x14 RX_DATA (pop)  +0x18 CMD  +0x1C FIFO_STAT (reset 0xA00)
  +0x20 TIMEOUT (reset 0xFFFF)  +0x24 IRQ_EN  +0x28 IRQ_STAT  +0x2C IRQ_CLR (W1C)

PHASE 1 — polled, I2C_IRQ_EN = 0 (the interrupt path is ARMED, so any trap is a gate failure)
  * read the reset values through the fabric: CTRL 0, CLKDIV 0xFF, TIMEOUT 0xFFFF, FIFO_STAT 0xA00,
    and a reserved word (0x030) 0. These distinguish slot 11 from every neighbouring slot, so a
    mis-decoded APB index fails here.
  * CLKDIV = 3 (read back), ADDR = 0x2A, CTRL = EN | LOOPBACK, push 0x5A, CMD = START|WRITE|STOP
    (count 1); poll IRQ_STAT.done; IRQ_STAT must be exactly `done`.
  * W1C, ADDR = 0x2A | 0x80, CMD = START|READ|STOP|NACK_LAST (count 1); poll done; RX_DATA must
    read back the byte written (the loopback slave returns the last byte written): 0x5A.
  The test scores i2c_irq / ext_irq LOW for the whole phase while `done` is pending — the
  IRQ_EN gate crossing the fabric — and the pad oe pins quiet for the whole run (loopback must not
  disturb a real bus).

PHASE 2 — interrupt driven
  * W1C, IRQ_EN = done, push 0x77, CMD = START|WRITE|STOP. done -> i2c_irq -> irq_ctrl[9] -> CPU.
  * ISR: read IRQ_STAT and the interrupt controller's PENDING_MASKED (bit 9 must be set — the
    controller really received irq_src_i[9]), then ONE write, IRQ_CLR = done, which drops the
    level-held source in a single access (nothing to race), then a read-back round trip so the
    level drains through the ext_irq synchroniser before MRET re-enables MIE. Exactly ONE trap.

Result area (SRAM word indices from RES_BASE_WI):
   0 ISR_COUNT  1 ISR_I2C_STAT  2 ISR_IRQC_PENDING  3 CTRL_RESET  4 CLKDIV_RESET  5 TIMEOUT_RESET
   6 FIFO_STAT_RESET  7 RESERVED_READ  8 CLKDIV_READBACK  9 P1_WRITE_STAT  10 P1_READ_STAT
   11 P1_RX_DATA  12 P1_STATUS

Register allocation (MAIN): x2 = I2C_BASE  x3 = IRQ_CTRL_BASE  x4 = RES_BASE_ADDR  x5 = staging
  x13 = scratch  x14/x15 = poll counter/limit  x16-x18 = scratch.  x1 is clobbered by the ISR.
Register allocation (ISR, at ISR_PC = ROM_BASE + 4): x26 x27 x28 x29 x30 x31 and x1.
"""

import os
import sys

_PROJ_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
if _PROJ_ROOT not in sys.path:
    sys.path.insert(0, _PROJ_ROOT)

from sim.riscv_encoder import ADDI, AND, ANDI, BLT, BNE, EBREAK, JAL, LW, SW  # noqa: E402
from tb.cocotb.soc.trng_fw.gen_trng_hex import (  # noqa: E402
    CSRRW,
    MRET,
    NOP,
    ROM_BASE,
    ROM_WORDS,
    Assembler,
    lui_addi,
)

ISR_OFFSET_WORDS = 1
MAIN_START_WORDS = 24

# ---------------------------------------------------------------------------
# Address map
# ---------------------------------------------------------------------------
I2C_BASE = 0x2000_E000
I2C_OFF_CTRL = 0x00
I2C_OFF_STATUS = 0x04
I2C_OFF_CLKDIV = 0x08
I2C_OFF_ADDR = 0x0C
I2C_OFF_TX = 0x10
I2C_OFF_RX = 0x14
I2C_OFF_CMD = 0x18
I2C_OFF_FIFO_STAT = 0x1C
I2C_OFF_TIMEOUT = 0x20
I2C_OFF_IRQ_EN = 0x24
I2C_OFF_IRQ_STAT = 0x28
I2C_OFF_IRQ_CLR = 0x2C
I2C_OFF_RESERVED = 0x30

IRQ_CTRL_BASE = 0x2000_6000
IRQ_OFF_MASK = 0x004
IRQ_OFF_PENDING = 0x008
I2C_IRQ_MASK_BIT = 0x200  # interrupt_controller.irq_src_i[9] = I2C slot

SRAM_BASE = 0x0000_2000
RES_BASE_WI = 300  # SRAM word 300 = byte 0x0000_24B0
RES_BASE_ADDR = SRAM_BASE + RES_BASE_WI * 4
RES_ISR_COUNT = 0
RES_ISR_I2C_STAT = 1
RES_ISR_IRQC_PEND = 2
RES_CTRL_RESET = 3
RES_CLKDIV_RESET = 4
RES_TIMEOUT_RESET = 5
RES_FIFO_RESET = 6
RES_RESERVED_READ = 7
RES_CLKDIV_READBK = 8
RES_P1_WRITE_STAT = 9
RES_P1_READ_STAT = 10
RES_P1_RX_DATA = 11
RES_P1_STATUS = 12
RES_WORDS = 16

# ---------------------------------------------------------------------------
# Test parameters
# ---------------------------------------------------------------------------
SLAVE_ADDR = 0x2A
BYTE1 = 0x5A  # phase 1: written then read back through the loopback slave
BYTE2 = 0x77  # phase 2: written, completes with an interrupt
CLKDIV_RUN = 3  # hardware minimum: fastest legal tick, keeps the SoC test short
CTRL_RUN = 0x3  # EN | LOOPBACK
IRQ_DONE = 0x1
IRQ_STICKY = 0xF
CMD_WRITE_STOP = 0x10B  # START | WRITE | STOP, COUNT = 1
CMD_READ_STOP = 0x11D  # START | READ | STOP | NACK_LAST, COUNT = 1
POLL_LIMIT = 4000


def _emit_li(asm: Assembler, rd: int, value32: int) -> None:
    lo, hi = lui_addi(rd, value32)
    asm.emit(lo)
    asm.emit(hi)


def _fail_if_ne(asm: Assembler, ra: int, rb: int) -> None:
    asm.thunk(lambda lbl, pc: BNE(ra, rb, lbl["FAIL"] - pc))


def _rd_check(asm: Assembler, off: int, res_idx: int, expect: int, mask: int = 0xFFFF_FFFF) -> None:
    """x16 = I2C[off]; store to result slot; (x16 & mask) must equal `expect`."""
    asm.emit(LW(16, 2, off))
    asm.emit(SW(16, 4, res_idx * 4))
    if mask != 0xFFFF_FFFF:
        _emit_li(asm, 18, mask)
        asm.emit(AND(16, 16, 18))
    _emit_li(asm, 17, expect)
    _fail_if_ne(asm, 16, 17)


def _wr(asm: Assembler, off: int, value: int) -> None:
    _emit_li(asm, 5, value)
    asm.emit(SW(5, 2, off))


def _poll_done(asm: Assembler, tag: str) -> None:
    """Poll I2C_IRQ_STAT.done, bounded; FAIL if it never sets."""
    asm.emit(ADDI(14, 0, 0))
    asm.emit(ADDI(15, 0, POLL_LIMIT))
    asm.label(f"{tag}_POLL")
    asm.emit(LW(16, 2, I2C_OFF_IRQ_STAT))
    asm.emit(ANDI(16, 16, IRQ_DONE))
    asm.thunk(lambda lbl, pc: BNE(16, 0, lbl[f"{tag}_OK"] - pc))
    asm.emit(ADDI(14, 14, 1))
    asm.thunk(lambda lbl, pc: BNE(14, 15, lbl[f"{tag}_POLL"] - pc))
    asm.thunk(lambda lbl, pc: JAL(0, lbl["FAIL"] - pc))  # never completed
    asm.label(f"{tag}_OK")


def build_firmware(asm: Assembler) -> None:
    # WORD 0 (0x1000): reset-vector trampoline
    asm.thunk(lambda lbl, pc: JAL(0, lbl["MAIN"] - pc))

    # WORD 1 (0x1004): ISR — mtvec set to here by MAIN (MODE=Direct)
    asm.label("ISR")
    _emit_li(asm, 28, I2C_BASE)
    _emit_li(asm, 27, IRQ_CTRL_BASE)
    asm.emit(LW(29, 28, I2C_OFF_IRQ_STAT))  # what the trap can see
    asm.emit(LW(26, 27, IRQ_OFF_PENDING))  # interrupt controller PENDING_MASKED
    asm.emit(ADDI(31, 0, IRQ_DONE))
    asm.emit(SW(31, 28, I2C_OFF_IRQ_CLR))  # ONE write: W1C done, source drops
    _emit_li(asm, 30, RES_BASE_ADDR)
    asm.emit(LW(1, 30, RES_ISR_COUNT * 4))
    asm.emit(ADDI(1, 1, 1))
    asm.emit(SW(1, 30, RES_ISR_COUNT * 4))  # ISR_COUNT += 1
    asm.emit(SW(29, 30, RES_ISR_I2C_STAT * 4))
    asm.emit(SW(26, 30, RES_ISR_IRQC_PEND * 4))
    # Read-back: a fabric round trip that proves the clear landed and lets the level-held IRQ drain
    # through the ext_irq synchroniser before MRET re-enables MIE.
    asm.emit(LW(29, 28, I2C_OFF_IRQ_STAT))
    asm.emit(MRET())

    asm.pad_to_word(MAIN_START_WORDS)

    # MAIN
    asm.label("MAIN")
    _emit_li(asm, 2, I2C_BASE)
    _emit_li(asm, 3, IRQ_CTRL_BASE)
    _emit_li(asm, 4, RES_BASE_ADDR)

    _emit_li(asm, 1, ROM_BASE + ISR_OFFSET_WORDS * 4)
    asm.emit(CSRRW(0, 0x305, 1))  # csrw mtvec, x1

    for w in range(RES_WORDS):  # zero the result area
        asm.emit(SW(0, 4, w * 4))

    # Arm the interrupt path. I2C_IRQ_EN stays 0 until phase 2, so no trap may occur before then.
    _emit_li(asm, 13, I2C_IRQ_MASK_BIT)
    asm.emit(SW(13, 3, IRQ_OFF_MASK))  # IRQ_MASK bit 9 (I2C)
    _emit_li(asm, 1, 0x800)
    asm.emit(CSRRW(0, 0x304, 1))  # csrw mie, x1   (MEIE)
    asm.emit(ADDI(1, 0, 8))
    asm.emit(CSRRW(0, 0x300, 1))  # csrw mstatus, x1 (MIE)

    asm.label("IRQ_READY")
    asm.nop()

    # ---- PHASE 1: polled, loopback ---------------------------------------------------------
    _rd_check(asm, I2C_OFF_CTRL, RES_CTRL_RESET, 0x0)
    _rd_check(asm, I2C_OFF_CLKDIV, RES_CLKDIV_RESET, 0xFF)
    _rd_check(asm, I2C_OFF_TIMEOUT, RES_TIMEOUT_RESET, 0xFFFF)
    _rd_check(asm, I2C_OFF_FIFO_STAT, RES_FIFO_RESET, 0xA00)
    _rd_check(asm, I2C_OFF_RESERVED, RES_RESERVED_READ, 0x0)

    _wr(asm, I2C_OFF_CLKDIV, CLKDIV_RUN)
    _rd_check(asm, I2C_OFF_CLKDIV, RES_CLKDIV_READBK, CLKDIV_RUN)
    _wr(asm, I2C_OFF_ADDR, SLAVE_ADDR)
    _wr(asm, I2C_OFF_CTRL, CTRL_RUN)
    _wr(asm, I2C_OFF_TX, BYTE1)
    _wr(asm, I2C_OFF_CMD, CMD_WRITE_STOP)
    asm.label("P1_CMD")
    asm.nop()
    _poll_done(asm, "W")
    _rd_check(asm, I2C_OFF_IRQ_STAT, RES_P1_WRITE_STAT, IRQ_DONE, mask=IRQ_STICKY)

    _wr(asm, I2C_OFF_IRQ_CLR, IRQ_STICKY)
    _wr(asm, I2C_OFF_ADDR, SLAVE_ADDR | 0x80)
    _wr(asm, I2C_OFF_CMD, CMD_READ_STOP)
    _poll_done(asm, "R")
    _rd_check(asm, I2C_OFF_IRQ_STAT, RES_P1_READ_STAT, IRQ_DONE, mask=IRQ_STICKY)
    _rd_check(asm, I2C_OFF_RX, RES_P1_RX_DATA, BYTE1)
    _rd_check(asm, I2C_OFF_STATUS, RES_P1_STATUS, 0x0, mask=0x1F)
    asm.label("P1_DONE")
    asm.nop()

    # ---- PHASE 2: interrupt driven ---------------------------------------------------------
    _wr(asm, I2C_OFF_IRQ_CLR, IRQ_STICKY)
    _wr(asm, I2C_OFF_IRQ_EN, IRQ_DONE)
    _wr(asm, I2C_OFF_ADDR, SLAVE_ADDR)
    _wr(asm, I2C_OFF_TX, BYTE2)
    _wr(asm, I2C_OFF_CMD, CMD_WRITE_STOP)
    asm.label("P2_ARMED")
    asm.nop()

    asm.emit(ADDI(14, 0, 0))
    asm.emit(ADDI(15, 0, POLL_LIMIT))
    asm.emit(ADDI(18, 0, 1))
    asm.label("TRAP_WAIT")
    asm.emit(LW(16, 4, RES_ISR_COUNT * 4))
    asm.thunk(lambda lbl, pc: BLT(16, 18, lbl["TRAP_WAIT_NEXT"] - pc))  # count < 1: keep waiting
    asm.thunk(lambda lbl, pc: JAL(0, lbl["TRAP_DONE"] - pc))
    asm.label("TRAP_WAIT_NEXT")
    asm.emit(ADDI(14, 14, 1))
    asm.thunk(lambda lbl, pc: BNE(14, 15, lbl["TRAP_WAIT"] - pc))
    asm.thunk(lambda lbl, pc: JAL(0, lbl["FAIL"] - pc))  # IRQ never arrived

    asm.label("TRAP_DONE")
    # Settle: a spurious second trap (stale level-held IRQ) lands here.
    asm.emit(ADDI(14, 0, 0))
    asm.emit(ADDI(15, 0, 600))
    asm.label("SETTLE")
    asm.emit(ADDI(14, 14, 1))
    asm.thunk(lambda lbl, pc: BNE(14, 15, lbl["SETTLE"] - pc))

    # Teeth: exactly one trap; the ISR saw `done`; the interrupt controller saw bit 9.
    asm.emit(LW(17, 4, RES_ISR_COUNT * 4))
    asm.emit(ADDI(18, 0, 1))
    _fail_if_ne(asm, 17, 18)
    asm.emit(LW(17, 4, RES_ISR_I2C_STAT * 4))
    asm.emit(ANDI(17, 17, IRQ_DONE))
    _fail_if_ne(asm, 17, 18)
    asm.emit(LW(17, 4, RES_ISR_IRQC_PEND * 4))
    _emit_li(asm, 18, I2C_IRQ_MASK_BIT)
    asm.emit(AND(17, 17, 18))
    _fail_if_ne(asm, 17, 18)

    # Flush D-cache so the backdoor SRAM read at the end of the test sees the stores.
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


ADDR_CONSTS = (
    "SLAVE_ADDR",
    "BYTE1",
    "BYTE2",
    "CLKDIV_RUN",
    "RES_BASE_WI",
    "RES_ISR_COUNT",
    "RES_ISR_I2C_STAT",
    "RES_ISR_IRQC_PEND",
    "RES_CTRL_RESET",
    "RES_CLKDIV_RESET",
    "RES_TIMEOUT_RESET",
    "RES_FIFO_RESET",
    "RES_RESERVED_READ",
    "RES_CLKDIV_READBK",
    "RES_P1_WRITE_STAT",
    "RES_P1_READ_STAT",
    "RES_P1_RX_DATA",
    "RES_P1_STATUS",
)


def main():
    out_dir = os.path.dirname(os.path.abspath(__file__))

    asm = Assembler(origin=ROM_BASE)
    build_firmware(asm)
    words = asm.resolve()
    labels = asm.labels
    assert len(words) <= ROM_WORDS, f"firmware too large: {len(words)} words > {ROM_WORDS}"
    for req in ("ISR", "MAIN", "FAIL", "PASS", "IRQ_READY", "P1_CMD", "P1_DONE", "P2_ARMED"):
        assert req in labels, f"label {req!r} not found in {list(labels)}"
    padded = list(words) + [NOP] * (ROM_WORDS - len(words))
    hex_path = os.path.join(out_dir, "i2c_fw.hex")
    with open(hex_path, "w") as f:
        for w in padded:
            f.write(f"{w:08x}\n")
    print(f"Wrote {len(padded)} words to {hex_path} ({len(words)} used)")

    addrs_path = os.path.join(out_dir, "i2c_fw_addrs.py")
    with open(addrs_path, "w") as f:
        f.write("# Auto-generated by gen_i2c_hex.py — do not edit.\n")
        for name, label in (
            ("PASS_PC", "PASS"),
            ("FAIL_PC", "FAIL"),
            ("ISR_PC", "ISR"),
            ("IRQ_READY_PC", "IRQ_READY"),
            ("P1_CMD_PC", "P1_CMD"),
            ("P1_DONE_PC", "P1_DONE"),
            ("P2_ARMED_PC", "P2_ARMED"),
        ):
            f.write(f"{name:<18} = 0x{labels[label]:08x}\n")
        for name in ADDR_CONSTS:
            f.write(f"{name:<18} = {globals()[name]}\n")
    print(f"Wrote {addrs_path}")


if __name__ == "__main__":
    main()
