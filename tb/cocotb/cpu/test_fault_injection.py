"""
Fault Injection Tests for RV32I CPU

Tests coverage gaps in the RTL by triggering exception paths:
  1. test_misaligned_load       - LH to odd address → TRAP_LOAD_MISALIGNED  (cause=4)
  2. test_misaligned_store      - SW to non-4-aligned address → TRAP_STORE_MISALIGNED (cause=6)
  3. test_illegal_instruction   - Bad opcode / bad funct7 → TRAP_ILLEGAL_INSN (cause=2)
  4. test_axi_fetch_error_trap  - AXI RRESP SLVERR on fetch → TRAP_ILLEGAL_INSN (cause=2)

Trap signal names (rv32i_cpu_top.sv ports):
  trap_taken_o : 1-cycle pulse when trap fires (in TRAP state output logic)
  trap_cause_o : 4-bit cause code stable during TRAP state

Trap cause codes (rv32i_control.sv localparams):
  2 = TRAP_ILLEGAL_INSN      (illegal instruction, also used for AXI errors)
  4 = TRAP_LOAD_MISALIGNED   (load address misaligned)
  6 = TRAP_STORE_MISALIGNED  (store address misaligned)

Misalignment rules (from rv32i_core.sv):
  LH/LHU : ea[0]   must be 0  (2-byte aligned)
  LW     : ea[1:0] must be 0  (4-byte aligned)
  SH     : ea[0]   must be 0  (2-byte aligned)
  SW     : ea[1:0] must be 0  (4-byte aligned)
"""

import os
import sys

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from sim.riscv_encoder import ADDI, JAL, LH, SW
from tb.cocotb.common.clock_reset import reset_dut
from tb.cocotb.cpu.axi_models import ConfigurableAXIMemory

# Trap cause constants matching rv32i_control.sv localparams
TRAP_ILLEGAL_INSN     = 2
TRAP_LOAD_MISALIGNED  = 4
TRAP_STORE_MISALIGNED = 6

# EBREAK encoding (funct12=0x001, rs1=0, funct3=0, rd=0, opcode=SYSTEM=0x73)
EBREAK = 0x00100073

# OP_REG with illegal funct7=0b0110000 (neither ADD=0b0000000 nor SUB=0b0100000 family)
# Encoding: (funct7 << 25) | (rs2 << 20) | (rs1 << 15) | (funct3 << 12) | (rd << 7) | opcode
# rd=1, rs1=0, rs2=0, funct3=000, funct7=0b0110000, opcode=OP_REG=0b0110011
ILLEGAL_BAD_FUNCT7 = (0b0110000 << 25) | (1 << 7) | 0b0110011  # = 0x600000B3

# Module-level references for stale-task cleanup between tests
_prev_mem        = None
_prev_clock_task = None


# ===========================================================================
# Shared helpers
# ===========================================================================

async def _setup_fault_test(dut):
    """Start clock, reset DUT, return a fresh ConfigurableAXIMemory.

    Cancels any stale handlers and clock from the previous test to prevent
    bus contention (same pattern as test_axi_protocol.py).

    Returns:
        ConfigurableAXIMemory ready to serve AXI transactions
    """
    global _prev_mem, _prev_clock_task

    # Cancel stale background tasks from the previous test / sub-test
    if _prev_mem is not None:
        try:
            _prev_mem.stop()
        except Exception:
            pass
        _prev_mem = None
    if _prev_clock_task is not None:
        try:
            _prev_clock_task.cancel()
        except Exception:
            pass
        _prev_clock_task = None

    clock = Clock(dut.clk_i, 10, unit="ns")
    _prev_clock_task = cocotb.start_soon(clock.start())

    await reset_dut(dut)

    mem = ConfigurableAXIMemory(dut, ref_model=None, protocol_check=False)
    _prev_mem = mem

    return mem


async def _wait_for_trap(dut, max_cycles=200):
    """Poll trap_taken_o for up to max_cycles rising edges.

    Returns:
        tuple: (trap_taken: bool, trap_cause: int)
            trap_taken is True if the pulse was observed within max_cycles.
            trap_cause is the sampled trap_cause_o on the cycle trap_taken_o=1,
            or the last observed value on timeout.
    """
    for _ in range(max_cycles):
        await RisingEdge(dut.clk_i)
        if int(dut.trap_taken_o.value) == 1:
            return True, int(dut.trap_cause_o.value)
    # Timed out — sample cause for diagnostics
    try:
        cause = int(dut.trap_cause_o.value)
    except Exception:
        cause = -1
    return False, cause


# ===========================================================================
# Test 1: Misaligned Load
# ===========================================================================

@cocotb.test()
async def test_misaligned_load(dut):
    """LH to odd effective address triggers TRAP_LOAD_MISALIGNED (cause=4).

    Program:
      0x0000: ADDI x1, x0, 1   # x1 = 1 (odd address)
      0x0004: LH x2, 0(x1)     # EA = x1 + 0 = 1, LH requires ea[0]==0 → trap
      0x0008: EBREAK            # not reached

    RTL detects misaligned_load in rv32i_core.sv and signals rv32i_control.sv,
    which latches TRAP_LOAD_MISALIGNED = 4'b0100 before entering TRAP state.
    """
    dut._log.info("=" * 70)
    dut._log.info("TEST: Misaligned Load (LH to odd address → trap_cause=4)")
    dut._log.info("=" * 70)

    mem = await _setup_fault_test(dut)

    mem.write_word(0x0000, ADDI(1, 0, 1))  # ADDI x1, x0, 1  → x1 = 1
    mem.write_word(0x0004, LH(2, 1, 0))   # LH  x2, 0(x1)   → EA = 1 (misaligned)
    mem.write_word(0x0008, EBREAK)
    dut._log.info("  0x0000: ADDI x1, x0, 1  (x1 = 1)")
    dut._log.info("  0x0004: LH x2, 0(x1)   (EA=1, misaligned)")
    dut._log.info("  0x0008: EBREAK")

    trap_taken, trap_cause = await _wait_for_trap(dut, max_cycles=200)

    dut._log.info(f"Result: trap_taken_o={trap_taken}, trap_cause_o={trap_cause}")
    assert trap_taken, \
        "trap_taken_o never went high within 200 cycles (expected misaligned LH trap)"
    assert trap_cause == TRAP_LOAD_MISALIGNED, (
        f"Expected trap_cause_o={TRAP_LOAD_MISALIGNED} (TRAP_LOAD_MISALIGNED), "
        f"got {trap_cause}"
    )

    dut._log.info("TEST PASSED: test_misaligned_load")
    dut._log.info("=" * 70)


# ===========================================================================
# Test 2: Misaligned Store
# ===========================================================================

@cocotb.test()
async def test_misaligned_store(dut):
    """SW to non-4-aligned effective address triggers TRAP_STORE_MISALIGNED (cause=6).

    Program:
      0x0000: ADDI x1, x0, 3   # x1 = 3
      0x0004: SW x2, 0(x1)     # EA = x1 + 0 = 3, SW requires ea[1:0]==0 → trap
      0x0008: EBREAK            # not reached

    RTL detects misaligned_store in rv32i_core.sv and signals rv32i_control.sv,
    which latches TRAP_STORE_MISALIGNED = 4'b0110 before entering TRAP state.
    """
    dut._log.info("=" * 70)
    dut._log.info("TEST: Misaligned Store (SW to non-aligned address → trap_cause=6)")
    dut._log.info("=" * 70)

    mem = await _setup_fault_test(dut)

    mem.write_word(0x0000, ADDI(1, 0, 3))  # ADDI x1, x0, 3  → x1 = 3
    mem.write_word(0x0004, SW(2, 1, 0))    # SW   x2, 0(x1)  → EA = 3 (misaligned)
    mem.write_word(0x0008, EBREAK)
    dut._log.info("  0x0000: ADDI x1, x0, 3  (x1 = 3)")
    dut._log.info("  0x0004: SW x2, 0(x1)   (EA=3, misaligned)")
    dut._log.info("  0x0008: EBREAK")

    trap_taken, trap_cause = await _wait_for_trap(dut, max_cycles=200)

    dut._log.info(f"Result: trap_taken_o={trap_taken}, trap_cause_o={trap_cause}")
    assert trap_taken, \
        "trap_taken_o never went high within 200 cycles (expected misaligned SW trap)"
    assert trap_cause == TRAP_STORE_MISALIGNED, (
        f"Expected trap_cause_o={TRAP_STORE_MISALIGNED} (TRAP_STORE_MISALIGNED), "
        f"got {trap_cause}"
    )

    dut._log.info("TEST PASSED: test_misaligned_store")
    dut._log.info("=" * 70)


# ===========================================================================
# Test 3: Illegal Instruction
# ===========================================================================

@cocotb.test()
async def test_illegal_instruction(dut):
    """Bad instruction encoding triggers TRAP_ILLEGAL_INSN (cause=2).

    Sub-test 3a: 0xFFFFFFFF — opcode=0b1111111 is not a valid RV32I opcode.
    Sub-test 3b: OP_REG (0b0110011) with funct7=0b0110000 — invalid funct7
                 (neither 0b0000000 for ADD/logical nor 0b0100000 for SUB/SRA).

    Both must assert trap_taken_o=1 with trap_cause_o=2 (TRAP_ILLEGAL_INSN).
    The decoder's 'illegal' branch in rv32i_decode.sv is exercised by 3b.
    """
    dut._log.info("=" * 70)
    dut._log.info("TEST: Illegal Instruction (trap_cause=2)")
    dut._log.info("=" * 70)

    # ------------------------------------------------------------------
    # Sub-test 3a: all-ones encoding (bad opcode 0b1111111)
    # ------------------------------------------------------------------
    dut._log.info("--- Sub-test 3a: 0xFFFFFFFF (bad opcode) ---")
    mem = await _setup_fault_test(dut)

    mem.write_word(0x0000, 0xFFFFFFFF)  # invalid opcode → TRAP_ILLEGAL_INSN
    mem.write_word(0x0004, EBREAK)
    dut._log.info("  0x0000: 0xFFFFFFFF  (opcode=0b1111111, always illegal)")

    trap_taken, trap_cause = await _wait_for_trap(dut, max_cycles=200)

    dut._log.info(f"  trap_taken_o={trap_taken}, trap_cause_o={trap_cause}")
    assert trap_taken, \
        "trap_taken_o never went high within 200 cycles (0xFFFFFFFF should be illegal)"
    assert trap_cause == TRAP_ILLEGAL_INSN, (
        f"Expected trap_cause_o={TRAP_ILLEGAL_INSN} (TRAP_ILLEGAL_INSN), "
        f"got {trap_cause}"
    )
    dut._log.info("  Sub-test 3a PASSED")

    # ------------------------------------------------------------------
    # Sub-test 3b: OP_REG with bad funct7 (exercises rv32i_decode.sv
    #              illegal branch inside the R-type decode block)
    # ------------------------------------------------------------------
    dut._log.info(f"--- Sub-test 3b: 0x{ILLEGAL_BAD_FUNCT7:08x} (OP_REG, funct7=0b0110000) ---")
    mem = await _setup_fault_test(dut)

    mem.write_word(0x0000, ILLEGAL_BAD_FUNCT7)  # OP_REG, invalid funct7
    mem.write_word(0x0004, EBREAK)
    dut._log.info(f"  0x0000: 0x{ILLEGAL_BAD_FUNCT7:08x}  (OP_REG funct7=0b0110000, invalid)")

    trap_taken, trap_cause = await _wait_for_trap(dut, max_cycles=200)

    dut._log.info(f"  trap_taken_o={trap_taken}, trap_cause_o={trap_cause}")
    assert trap_taken, (
        f"trap_taken_o never went high within 200 cycles "
        f"(OP_REG funct7=0b0110000 should be illegal, insn=0x{ILLEGAL_BAD_FUNCT7:08x})"
    )
    assert trap_cause == TRAP_ILLEGAL_INSN, (
        f"Expected trap_cause_o={TRAP_ILLEGAL_INSN} (TRAP_ILLEGAL_INSN), "
        f"got {trap_cause}"
    )
    dut._log.info("  Sub-test 3b PASSED")

    dut._log.info("TEST PASSED: test_illegal_instruction")
    dut._log.info("=" * 70)


# ===========================================================================
# Test 4: AXI Fetch Error Trap
# ===========================================================================

@cocotb.test()
async def test_axi_fetch_error_trap(dut):
    """AXI fetch RRESP=SLVERR causes trap_taken_o=1 (cause=2).

    Covers rv32i_control.sv path: RRESP != 2'b00 in FETCH/WAIT_RVALID state
    causes a trap. AXI errors are treated as TRAP_ILLEGAL_INSN (cause=2).

    Program:
      0x0000: JAL x0, +0x100   # jump to 0x0100
      0x0100: (SLVERR injected) # AXI returns RRESP=0b10, no valid instruction

    Expected: trap_taken_o=1, trap_cause_o=2.
    """
    dut._log.info("=" * 70)
    dut._log.info("TEST: AXI Fetch Error Trap (RRESP=SLVERR → trap_cause=2)")
    dut._log.info("=" * 70)

    mem = await _setup_fault_test(dut)

    # JAL x0, +0x100: from PC=0x0000, target = 0x0000 + 0x100 = 0x0100
    mem.write_word(0x0000, JAL(0, 0x100))
    # Inject SLVERR at 0x0100: AXI read handler returns RRESP=2'b10
    mem.inject_error(0x0100, "SLVERR")

    dut._log.info(f"  0x0000: JAL x0, +0x100  (0x{JAL(0, 0x100):08x})  → jump to 0x0100")
    dut._log.info("  0x0100: SLVERR injected  (AXI RRESP=0b10)")

    trap_taken, trap_cause = await _wait_for_trap(dut, max_cycles=200)

    dut._log.info(f"Result: trap_taken_o={trap_taken}, trap_cause_o={trap_cause}")
    assert trap_taken, \
        "trap_taken_o never went high within 200 cycles (expected AXI SLVERR trap)"
    assert trap_cause == TRAP_ILLEGAL_INSN, (
        f"Expected trap_cause_o={TRAP_ILLEGAL_INSN} (TRAP_ILLEGAL_INSN — AXI errors "
        f"use this code per rv32i_control.sv), got {trap_cause}"
    )

    dut._log.info("TEST PASSED: test_axi_fetch_error_trap")
    dut._log.info("=" * 70)
