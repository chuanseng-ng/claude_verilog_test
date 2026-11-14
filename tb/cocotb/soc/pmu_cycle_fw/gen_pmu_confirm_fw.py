#!/usr/bin/env python3
"""
gen_pmu_confirm_fw.py -- firmware images for the PMU behaviour-confirmation tests of
test_soc_pmu_multiclock.py. The images are built in the test process by the Assembler of
gen_pmu_cycle_hex.py. No hex file and no cross toolchain is needed, so no binary is committed.
  quiet_image():  the CPU runs a loop of register instructions only. After the first fetch of its
                  line it creates no bus traffic. It stands for software that follows the
                  stop-traffic rule before a power-down request.
  noisy_image():  the CPU reads the PMU STATUS register in a loop. The register is not cached, so
                  every pass is one AXI read through the CPU bridge. It stands for software that
                  keeps bus traffic going.
  gpu_access_image(kind): GPU control register access with the GPU on, a request for GPU_OFF through
                  the PMU CTRL register, then one access (kind "read" or "write") with the GPU off,
                  then one PMU STATUS read. The labels mark where the test observes the commit PC.
Each builder returns (words, labels). The words start at ROM_BASE.
Doc: tm:suite:soc-test-soc-pmu-multiclock
"""

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

# Importing the reference generator also puts the repository root on sys.path.
import gen_pmu_cycle_hex as _ref  # noqa: E402

from sim.riscv_encoder import ADDI, BEQ, BNE, EBREAK, JAL, LW, SW  # noqa: E402

Assembler = _ref.Assembler
ROM_BASE = _ref.ROM_BASE
NOP = _ref.NOP

GPU_BASE = 0x2000_1000
GPU_OFF_KERNEL_PC = 0x008
PMU_BASE = 0x2000_8000
PMU_CTRL = 0x000
PMU_STATUS = 0x004
MODE_GPU_OFF = 0x2
STATUS_GPU_OFF = 0x1  # cpu on, gpu off, busy low, timeout flag low
SENTINEL = 0xC0DE_0001
POLL_LIMIT = 20000
DWELL_PASSES = 64


def _li(asm, rd, value):
    lo, hi = _ref.lui_addi(rd, value)
    asm.emit(lo)
    asm.emit(hi)


def _br(asm, op, rs1, rs2, target):
    asm.thunk(lambda lbl, pc, op=op, a=rs1, b=rs2, t=target: op(a, b, lbl[t] - pc))


def _jmp(asm, target):
    asm.thunk(lambda lbl, pc, t=target: JAL(0, lbl[t] - pc))


def _marker(asm, name):
    asm.label(name)
    asm.emit(NOP)


def _tail(asm):
    asm.label("FAIL")
    asm.emit(ADDI(31, 0, -1))
    asm.emit(EBREAK())
    asm.label("PASS")
    asm.emit(ADDI(31, 0, 1))
    asm.emit(EBREAK())


def _finish(asm):
    words = asm.resolve()
    assert len(words) <= _ref.ROM_WORDS, f"image too large: {len(words)} words"
    return words, dict(asm.labels)


def quiet_image():
    asm = Assembler()
    asm.emit(ADDI(9, 0, 0))
    asm.label("QUIET_LOOP")
    asm.emit(ADDI(9, 9, 1))
    _jmp(asm, "QUIET_LOOP")
    return _finish(asm)


def noisy_image():
    asm = Assembler()
    _li(asm, 5, PMU_BASE)
    asm.label("NOISY_LOOP")
    asm.emit(LW(9, 5, PMU_STATUS))
    _jmp(asm, "NOISY_LOOP")
    return _finish(asm)


def gpu_access_image(kind):
    assert kind in ("read", "write"), kind
    asm = Assembler()
    _li(asm, 6, GPU_BASE)
    _li(asm, 9, PMU_BASE)
    _li(asm, 7, SENTINEL)

    # With the GPU on: one write and one read back of the kernel PC register.
    asm.emit(SW(7, 6, GPU_OFF_KERNEL_PC))
    asm.emit(LW(10, 6, GPU_OFF_KERNEL_PC))
    _br(asm, BNE, 10, 7, "FAIL")
    _marker(asm, "ON_ACCESS_DONE")

    # Request GPU_OFF and poll STATUS until the GPU domain reads off and not busy.
    asm.emit(ADDI(8, 0, MODE_GPU_OFF))
    asm.emit(SW(8, 9, PMU_CTRL))
    _li(asm, 20, POLL_LIMIT)
    asm.emit(ADDI(21, 0, 0))
    asm.emit(ADDI(23, 0, STATUS_GPU_OFF))
    asm.label("OFF_POLL")
    asm.emit(LW(22, 9, PMU_STATUS))
    _br(asm, BEQ, 22, 23, "OFF_SEEN")
    asm.emit(ADDI(21, 21, 1))
    _br(asm, BNE, 21, 20, "OFF_POLL")
    _jmp(asm, "FAIL")
    _marker(asm, "OFF_SEEN")

    # A short dwell, so that the domain reset and the clock stop are settled.
    asm.emit(ADDI(16, 0, 0))
    asm.emit(ADDI(17, 0, DWELL_PASSES))
    asm.label("DWELL")
    asm.emit(ADDI(16, 16, 1))
    _br(asm, BNE, 16, 17, "DWELL")

    # The access under test, then one access to a register outside the GPU.
    _marker(asm, "ACCESS_BEGIN")
    if kind == "read":
        asm.emit(LW(10, 6, GPU_OFF_KERNEL_PC))
    else:
        asm.emit(SW(7, 6, GPU_OFF_KERNEL_PC))
    _marker(asm, "ACCESS_DONE")
    asm.emit(LW(11, 9, PMU_STATUS))
    _marker(asm, "NEXT_DONE")
    _jmp(asm, "PASS")
    _tail(asm)
    return _finish(asm)
