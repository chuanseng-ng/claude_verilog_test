"""
ISA Compliance Tests for RV32I - pyuvm Implementation.

This module tests all 37 RV32I base integer instructions in isolation using
the pyuvm verification infrastructure. Each instruction is tested with various
operands and edge cases, validated against the Python reference model.

Migration Status: Phase E.3 - ISA test migration to pyuvm
Priority 1: Load/Store instructions (LW, SW, LB, LBU, LH, LHU, SB, SH)
Priority 2: Arithmetic/Logical instructions (TBD)
Priority 3: Control flow instructions (TBD)
Priority 4: Shift/Upper immediate instructions (TBD)
"""

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).resolve().parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from tb.cpu_uvm.tests.base_test import BaseTest  # noqa: E402
from tb.cpu_uvm.sequences.isa_sequences import (  # noqa: E402
    # Priority 1: Load/Store
    LWSequence, SWSequence,
    LBSequence, LBUSequence,
    LHSequence, LHUSequence,
    SBSequence, SHSequence,
    # Priority 2: Arithmetic/Logical
    ADDSequence, SUBSequence, ANDSequence, ORSequence, XORSequence,
    SLTSequence, SLTUSequence,
    ADDISequence, SLTISequence, SLTIUSequence,
    ANDISequence, ORISequence, XORISequence,
    # Priority 3: Shift
    SLLSequence, SRLSequence, SRASequence,
    SLLISequence, SRLISequence, SRAISequence,
    # Priority 4: Branch
    BEQSequence, BNESequence, BLTSequence, BGESequence,
    BLTUSequence, BGEUSequence,
    # Priority 5: Jump
    JALSequence, JALRSequence,
    # Priority 6: Upper Immediate
    LUISequence, AUIPCSequence,
)


async def run_isa_test(dut, sequence_class, sequence_args, test_name="isa_test"):
    """
    Helper function to run an ISA test with minimal boilerplate.

    This function handles all the common setup for ISA tests:
    - Clock creation
    - Test instantiation and UVM phase execution
    - Background task management
    - Sequence execution
    - Result validation

    Args:
        dut: Device under test (cocotb handle)
        sequence_class: ISA sequence class to instantiate
        sequence_args: Dict of arguments to pass to sequence constructor
        test_name: Name for the test instance

    Raises:
        AssertionError: If scoreboard detects mismatches
    """
    # Start clock
    clock = Clock(dut.clk, 10, unit="ns")
    cocotb.start_soon(clock.start())

    # Create test
    test = BaseTest(test_name, None, dut)
    test.build_phase()
    test.connect_phase()
    test.end_of_elaboration_phase()

    # Create sequence with the test's environment
    seq = sequence_class(**sequence_args, env=test.env)

    # Reset and halt CPU FIRST, before starting any background tasks
    # This ensures the CPU is stopped before it can fetch garbage
    dut._log.info("Applying reset")
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 5)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 2)

    # Immediately halt CPU after reset, before it can fetch
    apb_driver = test.env.apb_agent.driver
    await apb_driver.halt_cpu()
    dut._log.info("CPU halted immediately after reset")

    # NOW start background tasks
    cocotb.start_soon(test.env.axi_agent.driver.axi_read_handler())
    cocotb.start_soon(test.env.axi_agent.driver.axi_write_handler())
    cocotb.start_soon(test.env.commit_monitor.run_phase())
    cocotb.start_soon(test.env.scoreboard.run_phase())

    # Give background tasks a chance to start
    await ClockCycles(dut.clk, 2)

    # Run the sequence - CPU is already halted, program will be loaded
    dut._log.info(f"Running sequence: {seq.get_name()}")
    await seq.body()

    # Small delay for any final commits
    await ClockCycles(dut.clk, 5)

    # Report results
    test.env.scoreboard.report_phase()

    # Verify no mismatches
    assert test.env.scoreboard.mismatches == 0, \
        f"Scoreboard detected {test.env.scoreboard.mismatches} mismatches"

    dut._log.info(f"✓ {test_name} passed")


# =============================================================================
# Priority 1: Load/Store Instructions (Memory Operations)
# =============================================================================

@cocotb.test()
async def test_isa_lw_basic_uvm(dut):
    """
    Test LW (Load Word) instruction - basic case.

    Test: LW x5, 0(x1) where mem[0x1000] = 0xDEADBEEF
    Expected: x5 = 0xDEADBEEF
    """
    dut._log.info("=== Test: LW Basic ===")

    await run_isa_test(
        dut,
        LWSequence,
        {
            "name": "lw_basic",
            "rd": 5,               # Load into x5
            "rs1": 1,              # Base address in x1
            "offset": 0,           # Offset = 0
            "base_addr": 0x1000,   # x1 = 0x1000
            "mem_value": 0xDEADBEEF,  # mem[0x1000] = 0xDEADBEEF
            "expected_value": 0xDEADBEEF
        },
        "test_isa_lw_basic"
    )


@cocotb.test()
async def test_isa_lw_offset_uvm(dut):
    """
    Test LW with positive offset.

    Test: LW x6, 8(x2) where mem[0x2008] = 0x12345678
    Expected: x6 = 0x12345678
    """
    dut._log.info("=== Test: LW with Offset ===")

    await run_isa_test(
        dut,
        LWSequence,
        {
            "name": "lw_offset",
            "rd": 6,
            "rs1": 2,
            "offset": 8,
            "base_addr": 0x2000,
            "mem_value": 0x12345678,
            "expected_value": 0x12345678
        },
        "test_isa_lw_offset"
    )


@cocotb.test()
async def test_isa_sw_basic_uvm(dut):
    """
    Test SW (Store Word) instruction - basic case.

    Test: SW x3, 0(x1) where x1=0x1000, x3=0xCAFEBABE
    Expected: mem[0x1000] = 0xCAFEBABE
    """
    dut._log.info("=== Test: SW Basic ===")

    await run_isa_test(
        dut,
        SWSequence,
        {
            "name": "sw_basic",
            "rs1": 1,              # Base address in x1
            "rs2": 3,              # Source data in x3
            "offset": 0,           # Offset = 0
            "base_addr": 0x1000,   # x1 = 0x1000
            "store_value": 0xCAFEBABE  # x3 = 0xCAFEBABE
        },
        "test_isa_sw_basic"
    )


@cocotb.test()
async def test_isa_sw_offset_uvm(dut):
    """
    Test SW with positive offset.

    Test: SW x4, 12(x2) where x2=0x2000, x4=0xAAAAAAAA
    Expected: mem[0x200C] = 0xAAAAAAAA
    """
    dut._log.info("=== Test: SW with Offset ===")

    await run_isa_test(
        dut,
        SWSequence,
        {
            "name": "sw_offset",
            "rs1": 2,
            "rs2": 4,
            "offset": 12,
            "base_addr": 0x2000,
            "store_value": 0xAAAAAAAA
        },
        "test_isa_sw_offset"
    )


@cocotb.test()
async def test_isa_lb_positive_uvm(dut):
    """
    Test LB (Load Byte, sign-extended) - positive byte.

    Test: LB x5, 0(x1) where mem[0x1000] = 0x0000007F
    Expected: x5 = 0x0000007F (positive, no sign extension)
    """
    dut._log.info("=== Test: LB Positive ===")

    await run_isa_test(
        dut,
        LBSequence,
        {
            "name": "lb_positive",
            "rd": 5,
            "rs1": 1,
            "offset": 0,
            "base_addr": 0x1000,
            "mem_value": 0x0000007F,  # Byte = 0x7F (positive)
            "expected_value": 0x0000007F
        },
        "test_isa_lb_positive"
    )


@cocotb.test()
async def test_isa_lb_negative_uvm(dut):
    """
    Test LB (Load Byte, sign-extended) - negative byte.

    Test: LB x5, 0(x1) where mem[0x1000] = 0x000000FF
    Expected: x5 = 0xFFFFFFFF (sign-extended from 0xFF)
    """
    dut._log.info("=== Test: LB Negative (Sign Extension) ===")

    await run_isa_test(
        dut,
        LBSequence,
        {
            "name": "lb_negative",
            "rd": 5,
            "rs1": 1,
            "offset": 0,
            "base_addr": 0x1000,
            "mem_value": 0x000000FF,  # Byte = 0xFF (negative)
            "expected_value": 0xFFFFFFFF  # Sign-extended
        },
        "test_isa_lb_negative"
    )


@cocotb.test()
async def test_isa_lbu_uvm(dut):
    """
    Test LBU (Load Byte Unsigned) - no sign extension.

    Test: LBU x5, 0(x1) where mem[0x1000] = 0x000000FF
    Expected: x5 = 0x000000FF (zero-extended, not sign-extended)
    """
    dut._log.info("=== Test: LBU (Zero Extension) ===")

    await run_isa_test(
        dut,
        LBUSequence,
        {
            "name": "lbu_basic",
            "rd": 5,
            "rs1": 1,
            "offset": 0,
            "base_addr": 0x1000,
            "mem_value": 0x000000FF,
            "expected_value": 0x000000FF  # Zero-extended
        },
        "test_isa_lbu"
    )


@cocotb.test()
async def test_isa_lh_positive_uvm(dut):
    """
    Test LH (Load Halfword, sign-extended) - positive halfword.

    Test: LH x5, 0(x1) where mem[0x1000] = 0x00007FFF
    Expected: x5 = 0x00007FFF (positive, no sign extension)
    """
    dut._log.info("=== Test: LH Positive ===")

    await run_isa_test(
        dut,
        LHSequence,
        {
            "name": "lh_positive",
            "rd": 5,
            "rs1": 1,
            "offset": 0,
            "base_addr": 0x1000,
            "mem_value": 0x00007FFF,  # Halfword = 0x7FFF (positive)
            "expected_value": 0x00007FFF
        },
        "test_isa_lh_positive"
    )


@cocotb.test()
async def test_isa_lh_negative_uvm(dut):
    """
    Test LH (Load Halfword, sign-extended) - negative halfword.

    Test: LH x5, 0(x1) where mem[0x1000] = 0x0000FFFF
    Expected: x5 = 0xFFFFFFFF (sign-extended from 0xFFFF)
    """
    dut._log.info("=== Test: LH Negative (Sign Extension) ===")

    await run_isa_test(
        dut,
        LHSequence,
        {
            "name": "lh_negative",
            "rd": 5,
            "rs1": 1,
            "offset": 0,
            "base_addr": 0x1000,
            "mem_value": 0x0000FFFF,  # Halfword = 0xFFFF (negative)
            "expected_value": 0xFFFFFFFF  # Sign-extended
        },
        "test_isa_lh_negative"
    )


@cocotb.test()
async def test_isa_lhu_uvm(dut):
    """
    Test LHU (Load Halfword Unsigned) - no sign extension.

    Test: LHU x5, 0(x1) where mem[0x1000] = 0x0000FFFF
    Expected: x5 = 0x0000FFFF (zero-extended, not sign-extended)
    """
    dut._log.info("=== Test: LHU (Zero Extension) ===")

    await run_isa_test(
        dut,
        LHUSequence,
        {
            "name": "lhu_basic",
            "rd": 5,
            "rs1": 1,
            "offset": 0,
            "base_addr": 0x1000,
            "mem_value": 0x0000FFFF,
            "expected_value": 0x0000FFFF  # Zero-extended
        },
        "test_isa_lhu"
    )


@cocotb.test()
async def test_isa_sb_uvm(dut):
    """
    Test SB (Store Byte) instruction.

    Test: SB x3, 0(x1) where x1=0x1000, x3=0xDEADBEEF
    Expected: mem[0x1000] byte = 0xEF (only lowest byte stored)
    """
    dut._log.info("=== Test: SB ===")

    await run_isa_test(
        dut,
        SBSequence,
        {
            "name": "sb_basic",
            "rs1": 1,
            "rs2": 3,
            "offset": 0,
            "base_addr": 0x1000,
            "store_value": 0xDEADBEEF  # Only 0xEF should be stored
        },
        "test_isa_sb"
    )


@cocotb.test()
async def test_isa_sh_uvm(dut):
    """
    Test SH (Store Halfword) instruction.

    Test: SH x3, 0(x1) where x1=0x1000, x3=0xDEADBEEF
    Expected: mem[0x1000] halfword = 0xBEEF (only lowest halfword stored)
    """
    dut._log.info("=== Test: SH ===")

    await run_isa_test(
        dut,
        SHSequence,
        {
            "name": "sh_basic",
            "rs1": 1,
            "rs2": 3,
            "offset": 0,
            "base_addr": 0x1000,
            "store_value": 0xDEADBEEF  # Only 0xBEEF should be stored
        },
        "test_isa_sh"
    )


# =============================================================================
# Priority 2: Arithmetic/Logical Instructions
# =============================================================================

@cocotb.test()
async def test_isa_add_basic_uvm(dut):
    """
    Test ADD (Add) instruction - basic case.

    Test: ADD x5, x1, x2 where x1=10, x2=20
    Expected: x5 = 30
    """
    dut._log.info("=== Test: ADD Basic ===")

    await run_isa_test(
        dut,
        ADDSequence,
        {
            "name": "add_basic",
            "rd": 5,
            "rs1": 1,
            "rs2": 2,
            "rs1_val": 10,
            "rs2_val": 20,
            "expected_value": 30
        },
        "test_isa_add_basic"
    )


@cocotb.test()
async def test_isa_add_overflow_uvm(dut):
    """
    Test ADD instruction - overflow case.

    Test: ADD x5, x1, x2 where x1=0x7FFFFFFF, x2=1
    Expected: x5 = 0x80000000 (overflow wraps)
    """
    dut._log.info("=== Test: ADD Overflow ===")

    await run_isa_test(
        dut,
        ADDSequence,
        {
            "name": "add_overflow",
            "rd": 5,
            "rs1": 1,
            "rs2": 2,
            "rs1_val": 0x7FFFFFFF,
            "rs2_val": 1,
            "expected_value": 0x80000000
        },
        "test_isa_add_overflow"
    )


@cocotb.test()
async def test_isa_sub_basic_uvm(dut):
    """
    Test SUB (Subtract) instruction - basic case.

    Test: SUB x5, x1, x2 where x1=50, x2=20
    Expected: x5 = 30
    """
    dut._log.info("=== Test: SUB Basic ===")

    await run_isa_test(
        dut,
        SUBSequence,
        {
            "name": "sub_basic",
            "rd": 5,
            "rs1": 1,
            "rs2": 2,
            "rs1_val": 50,
            "rs2_val": 20,
            "expected_value": 30
        },
        "test_isa_sub_basic"
    )


@cocotb.test()
async def test_isa_sub_underflow_uvm(dut):
    """
    Test SUB instruction - underflow case.

    Test: SUB x5, x1, x2 where x1=0, x2=1
    Expected: x5 = 0xFFFFFFFF (underflow wraps)
    """
    dut._log.info("=== Test: SUB Underflow ===")

    await run_isa_test(
        dut,
        SUBSequence,
        {
            "name": "sub_underflow",
            "rd": 5,
            "rs1": 1,
            "rs2": 2,
            "rs1_val": 0,
            "rs2_val": 1,
            "expected_value": 0xFFFFFFFF
        },
        "test_isa_sub_underflow"
    )


@cocotb.test()
async def test_isa_and_uvm(dut):
    """
    Test AND (Bitwise AND) instruction.

    Test: AND x5, x1, x2 where x1=0xFF00, x2=0x0FF0
    Expected: x5 = 0x0F00
    """
    dut._log.info("=== Test: AND ===")

    await run_isa_test(
        dut,
        ANDSequence,
        {
            "name": "and_basic",
            "rd": 5,
            "rs1": 1,
            "rs2": 2,
            "rs1_val": 0xFF00,
            "rs2_val": 0x0FF0,
            "expected_value": 0x0F00
        },
        "test_isa_and"
    )


@cocotb.test()
async def test_isa_or_uvm(dut):
    """
    Test OR (Bitwise OR) instruction.

    Test: OR x5, x1, x2 where x1=0xFF00, x2=0x00FF
    Expected: x5 = 0xFFFF
    """
    dut._log.info("=== Test: OR ===")

    await run_isa_test(
        dut,
        ORSequence,
        {
            "name": "or_basic",
            "rd": 5,
            "rs1": 1,
            "rs2": 2,
            "rs1_val": 0xFF00,
            "rs2_val": 0x00FF,
            "expected_value": 0xFFFF
        },
        "test_isa_or"
    )


@cocotb.test()
async def test_isa_xor_uvm(dut):
    """
    Test XOR (Bitwise XOR) instruction.

    Test: XOR x5, x1, x2 where x1=0xFFFF, x2=0x0F0F
    Expected: x5 = 0xF0F0
    """
    dut._log.info("=== Test: XOR ===")

    await run_isa_test(
        dut,
        XORSequence,
        {
            "name": "xor_basic",
            "rd": 5,
            "rs1": 1,
            "rs2": 2,
            "rs1_val": 0xFFFF,
            "rs2_val": 0x0F0F,
            "expected_value": 0xF0F0
        },
        "test_isa_xor"
    )


@cocotb.test()
async def test_isa_slt_true_uvm(dut):
    """
    Test SLT (Set Less Than, signed) instruction - true case.

    Test: SLT x5, x1, x2 where x1=-10 (signed), x2=20
    Expected: x5 = 1 (true, -10 < 20)
    """
    dut._log.info("=== Test: SLT True ===")

    await run_isa_test(
        dut,
        SLTSequence,
        {
            "name": "slt_true",
            "rd": 5,
            "rs1": 1,
            "rs2": 2,
            "rs1_val": 0xFFFFFFF6,  # -10 in two's complement
            "rs2_val": 20,
            "expected_value": 1
        },
        "test_isa_slt_true"
    )


@cocotb.test()
async def test_isa_sltu_false_uvm(dut):
    """
    Test SLTU (Set Less Than Unsigned) instruction - false case.

    Test: SLTU x5, x1, x2 where x1=0xFFFFFFF6, x2=20 (unsigned)
    Expected: x5 = 0 (false, 0xFFFFFFF6 > 20 unsigned)
    """
    dut._log.info("=== Test: SLTU False ===")

    await run_isa_test(
        dut,
        SLTUSequence,
        {
            "name": "sltu_false",
            "rd": 5,
            "rs1": 1,
            "rs2": 2,
            "rs1_val": 0xFFFFFFF6,
            "rs2_val": 20,
            "expected_value": 0
        },
        "test_isa_sltu_false"
    )


@cocotb.test()
async def test_isa_addi_positive_uvm(dut):
    """
    Test ADDI (Add Immediate) instruction - positive immediate.

    Test: ADDI x5, x1, 100 where x1=50
    Expected: x5 = 150
    """
    dut._log.info("=== Test: ADDI Positive ===")

    await run_isa_test(
        dut,
        ADDISequence,
        {
            "name": "addi_positive",
            "rd": 5,
            "rs1": 1,
            "imm": 100,
            "rs1_val": 50,
            "expected_value": 150
        },
        "test_isa_addi_positive"
    )


@cocotb.test()
async def test_isa_slti_true_uvm(dut):
    """
    Test SLTI (Set Less Than Immediate, signed) instruction - true case.

    Test: SLTI x5, x1, 100 where x1=50
    Expected: x5 = 1 (true, 50 < 100)
    """
    dut._log.info("=== Test: SLTI True ===")

    await run_isa_test(
        dut,
        SLTISequence,
        {
            "name": "slti_true",
            "rd": 5,
            "rs1": 1,
            "imm": 100,
            "rs1_val": 50,
            "expected_value": 1
        },
        "test_isa_slti_true"
    )


@cocotb.test()
async def test_isa_sltiu_false_uvm(dut):
    """
    Test SLTIU (Set Less Than Immediate Unsigned) instruction - false case.

    Test: SLTIU x5, x1, 50 where x1=100
    Expected: x5 = 0 (false, 100 > 50)
    """
    dut._log.info("=== Test: SLTIU False ===")

    await run_isa_test(
        dut,
        SLTIUSequence,
        {
            "name": "sltiu_false",
            "rd": 5,
            "rs1": 1,
            "imm": 50,
            "rs1_val": 100,
            "expected_value": 0
        },
        "test_isa_sltiu_false"
    )


@cocotb.test()
async def test_isa_andi_uvm(dut):
    """
    Test ANDI (AND Immediate) instruction.

    Test: ANDI x5, x1, 0x0FF where x1=0x1FF
    Expected: x5 = 0x0FF
    """
    dut._log.info("=== Test: ANDI ===")

    await run_isa_test(
        dut,
        ANDISequence,
        {
            "name": "andi_basic",
            "rd": 5,
            "rs1": 1,
            "imm": 0x0FF,
            "rs1_val": 0x1FF,
            "expected_value": 0x0FF
        },
        "test_isa_andi"
    )


@cocotb.test()
async def test_isa_ori_uvm(dut):
    """
    Test ORI (OR Immediate) instruction.

    Test: ORI x5, x1, 0x0FF where x1=0xF00
    Expected: x5 = 0xFFF
    """
    dut._log.info("=== Test: ORI ===")

    await run_isa_test(
        dut,
        ORISequence,
        {
            "name": "ori_basic",
            "rd": 5,
            "rs1": 1,
            "imm": 0x0FF,
            "rs1_val": 0xF00,
            "expected_value": 0xFFF
        },
        "test_isa_ori"
    )


@cocotb.test()
async def test_isa_xori_uvm(dut):
    """
    Test XORI (XOR Immediate) instruction.

    Test: XORI x5, x1, 0xFFF where x1=0xAAA
    Expected: x5 = 0x555
    """
    dut._log.info("=== Test: XORI ===")

    await run_isa_test(
        dut,
        XORISequence,
        {
            "name": "xori_basic",
            "rd": 5,
            "rs1": 1,
            "imm": 0xFFF,
            "rs1_val": 0xAAA,
            "expected_value": 0x555
        },
        "test_isa_xori"
    )


# =============================================================================
# Priority 3: Shift Instructions
# =============================================================================

@cocotb.test()
async def test_isa_sll_basic_uvm(dut):
    """
    Test SLL (Shift Left Logical) instruction - basic case.

    Test: SLL x5, x1, x2 where x1=0x00000001, x2=4
    Expected: x5 = 0x00000010 (1 << 4)
    """
    dut._log.info("=== Test: SLL Basic ===")

    await run_isa_test(
        dut,
        SLLSequence,
        {
            "name": "sll_basic",
            "rd": 5,
            "rs1": 1,
            "rs2": 2,
            "rs1_val": 0x00000001,
            "rs2_val": 4,
            "expected_value": 0x00000010
        },
        "test_isa_sll_basic"
    )


@cocotb.test()
async def test_isa_sll_max_shift_uvm(dut):
    """
    Test SLL with maximum shift amount (31).

    Test: SLL x5, x1, x2 where x1=0x00000001, x2=31
    Expected: x5 = 0x80000000 (1 << 31)
    """
    dut._log.info("=== Test: SLL Max Shift ===")

    await run_isa_test(
        dut,
        SLLSequence,
        {
            "name": "sll_max",
            "rd": 5,
            "rs1": 1,
            "rs2": 2,
            "rs1_val": 0x00000001,
            "rs2_val": 31,
            "expected_value": 0x80000000
        },
        "test_isa_sll_max"
    )


@cocotb.test()
async def test_isa_slli_basic_uvm(dut):
    """
    Test SLLI (Shift Left Logical Immediate) instruction.

    Test: SLLI x5, x1, 8 where x1=0x000000FF
    Expected: x5 = 0x0000FF00 (0xFF << 8)
    """
    dut._log.info("=== Test: SLLI Basic ===")

    await run_isa_test(
        dut,
        SLLISequence,
        {
            "name": "slli_basic",
            "rd": 5,
            "rs1": 1,
            "shamt": 8,
            "rs1_val": 0x000000FF,
            "expected_value": 0x0000FF00
        },
        "test_isa_slli_basic"
    )


@cocotb.test()
async def test_isa_srl_basic_uvm(dut):
    """
    Test SRL (Shift Right Logical) instruction - basic case.

    Test: SRL x5, x1, x2 where x1=0x80000000, x2=4
    Expected: x5 = 0x08000000 (logical right shift, zero-fill)
    """
    dut._log.info("=== Test: SRL Basic ===")

    await run_isa_test(
        dut,
        SRLSequence,
        {
            "name": "srl_basic",
            "rd": 5,
            "rs1": 1,
            "rs2": 2,
            "rs1_val": 0x80000000,
            "rs2_val": 4,
            "expected_value": 0x08000000
        },
        "test_isa_srl_basic"
    )


@cocotb.test()
async def test_isa_srli_basic_uvm(dut):
    """
    Test SRLI (Shift Right Logical Immediate) instruction.

    Test: SRLI x5, x1, 8 where x1=0xFF000000
    Expected: x5 = 0x00FF0000 (logical right shift by 8)
    """
    dut._log.info("=== Test: SRLI Basic ===")

    await run_isa_test(
        dut,
        SRLISequence,
        {
            "name": "srli_basic",
            "rd": 5,
            "rs1": 1,
            "shamt": 8,
            "rs1_val": 0xFF000000,
            "expected_value": 0x00FF0000
        },
        "test_isa_srli_basic"
    )


@cocotb.test()
async def test_isa_sra_basic_uvm(dut):
    """
    Test SRA (Shift Right Arithmetic) instruction - negative number.

    Test: SRA x5, x1, x2 where x1=0x80000000, x2=4
    Expected: x5 = 0xF8000000 (arithmetic right shift, sign-extend)
    """
    dut._log.info("=== Test: SRA Basic (Negative) ===")

    await run_isa_test(
        dut,
        SRASequence,
        {
            "name": "sra_negative",
            "rd": 5,
            "rs1": 1,
            "rs2": 2,
            "rs1_val": 0x80000000,
            "rs2_val": 4,
            "expected_value": 0xF8000000
        },
        "test_isa_sra_negative"
    )


@cocotb.test()
async def test_isa_srai_basic_uvm(dut):
    """
    Test SRAI (Shift Right Arithmetic Immediate) instruction.

    Test: SRAI x5, x1, 8 where x1=0xFF000000
    Expected: x5 = 0xFFFF0000 (arithmetic right shift, sign-extend)
    """
    dut._log.info("=== Test: SRAI Basic ===")

    await run_isa_test(
        dut,
        SRAISequence,
        {
            "name": "srai_basic",
            "rd": 5,
            "rs1": 1,
            "shamt": 8,
            "rs1_val": 0xFF000000,
            "expected_value": 0xFFFF0000
        },
        "test_isa_srai_basic"
    )


# =============================================================================
# Priority 4: Branch Instructions
# =============================================================================

@cocotb.test()
async def test_isa_beq_taken_uvm(dut):
    """
    Test BEQ (Branch if Equal) instruction - branch taken.

    Test: BEQ x1, x2, 8 where x1=10, x2=10
    Expected: Branch taken (PC jumps forward by 8 bytes)
    """
    dut._log.info("=== Test: BEQ Taken ===")

    await run_isa_test(
        dut,
        BEQSequence,
        {
            "name": "beq_taken",
            "rs1": 1,
            "rs2": 2,
            "rs1_val": 10,
            "rs2_val": 10,
            "branch_target_offset": 8,
            "expect_branch_taken": True
        },
        "test_isa_beq_taken"
    )


@cocotb.test()
async def test_isa_beq_not_taken_uvm(dut):
    """
    Test BEQ (Branch if Equal) instruction - branch not taken.

    Test: BEQ x1, x2, 8 where x1=10, x2=20
    Expected: Branch not taken (PC increments by 4)
    """
    dut._log.info("=== Test: BEQ Not Taken ===")

    await run_isa_test(
        dut,
        BEQSequence,
        {
            "name": "beq_not_taken",
            "rs1": 1,
            "rs2": 2,
            "rs1_val": 10,
            "rs2_val": 20,
            "branch_target_offset": 8,
            "expect_branch_taken": False
        },
        "test_isa_beq_not_taken"
    )


@cocotb.test()
async def test_isa_bne_taken_uvm(dut):
    """
    Test BNE (Branch if Not Equal) instruction - branch taken.

    Test: BNE x1, x2, 8 where x1=10, x2=20
    Expected: Branch taken
    """
    dut._log.info("=== Test: BNE Taken ===")

    await run_isa_test(
        dut,
        BNESequence,
        {
            "name": "bne_taken",
            "rs1": 1,
            "rs2": 2,
            "rs1_val": 10,
            "rs2_val": 20,
            "branch_target_offset": 8,
            "expect_branch_taken": True
        },
        "test_isa_bne_taken"
    )


@cocotb.test()
async def test_isa_bne_not_taken_uvm(dut):
    """
    Test BNE (Branch if Not Equal) instruction - branch not taken.

    Test: BNE x1, x2, 8 where x1=10, x2=10
    Expected: Branch not taken
    """
    dut._log.info("=== Test: BNE Not Taken ===")

    await run_isa_test(
        dut,
        BNESequence,
        {
            "name": "bne_not_taken",
            "rs1": 1,
            "rs2": 2,
            "rs1_val": 10,
            "rs2_val": 10,
            "branch_target_offset": 8,
            "expect_branch_taken": False
        },
        "test_isa_bne_not_taken"
    )


@cocotb.test()
async def test_isa_blt_taken_uvm(dut):
    """
    Test BLT (Branch if Less Than, signed) instruction - branch taken.

    Test: BLT x1, x2, 8 where x1=-10, x2=20
    Expected: Branch taken (signed: -10 < 20)
    """
    dut._log.info("=== Test: BLT Taken ===")

    await run_isa_test(
        dut,
        BLTSequence,
        {
            "name": "blt_taken",
            "rs1": 1,
            "rs2": 2,
            "rs1_val": 0xFFFFFFF6,  # -10 in two's complement
            "rs2_val": 20,
            "branch_target_offset": 8,
            "expect_branch_taken": True
        },
        "test_isa_blt_taken"
    )


@cocotb.test()
async def test_isa_blt_not_taken_uvm(dut):
    """
    Test BLT (Branch if Less Than, signed) instruction - branch not taken.

    Test: BLT x1, x2, 8 where x1=20, x2=10
    Expected: Branch not taken (signed: 20 >= 10)
    """
    dut._log.info("=== Test: BLT Not Taken ===")

    await run_isa_test(
        dut,
        BLTSequence,
        {
            "name": "blt_not_taken",
            "rs1": 1,
            "rs2": 2,
            "rs1_val": 20,
            "rs2_val": 10,
            "branch_target_offset": 8,
            "expect_branch_taken": False
        },
        "test_isa_blt_not_taken"
    )


@cocotb.test()
async def test_isa_bge_taken_uvm(dut):
    """
    Test BGE (Branch if Greater or Equal, signed) instruction - branch taken.

    Test: BGE x1, x2, 8 where x1=20, x2=10
    Expected: Branch taken (signed: 20 >= 10)
    """
    dut._log.info("=== Test: BGE Taken ===")

    await run_isa_test(
        dut,
        BGESequence,
        {
            "name": "bge_taken",
            "rs1": 1,
            "rs2": 2,
            "rs1_val": 20,
            "rs2_val": 10,
            "branch_target_offset": 8,
            "expect_branch_taken": True
        },
        "test_isa_bge_taken"
    )


@cocotb.test()
async def test_isa_bge_not_taken_uvm(dut):
    """
    Test BGE (Branch if Greater or Equal, signed) instruction - branch not taken.

    Test: BGE x1, x2, 8 where x1=-10, x2=20
    Expected: Branch not taken (signed: -10 < 20)
    """
    dut._log.info("=== Test: BGE Not Taken ===")

    await run_isa_test(
        dut,
        BGESequence,
        {
            "name": "bge_not_taken",
            "rs1": 1,
            "rs2": 2,
            "rs1_val": 0xFFFFFFF6,  # -10 in two's complement
            "rs2_val": 20,
            "branch_target_offset": 8,
            "expect_branch_taken": False
        },
        "test_isa_bge_not_taken"
    )


@cocotb.test()
async def test_isa_bltu_taken_uvm(dut):
    """
    Test BLTU (Branch if Less Than, unsigned) instruction - branch taken.

    Test: BLTU x1, x2, 8 where x1=10, x2=20
    Expected: Branch taken (unsigned: 10 < 20)
    """
    dut._log.info("=== Test: BLTU Taken ===")

    await run_isa_test(
        dut,
        BLTUSequence,
        {
            "name": "bltu_taken",
            "rs1": 1,
            "rs2": 2,
            "rs1_val": 10,
            "rs2_val": 20,
            "branch_target_offset": 8,
            "expect_branch_taken": True
        },
        "test_isa_bltu_taken"
    )


@cocotb.test()
async def test_isa_bltu_not_taken_uvm(dut):
    """
    Test BLTU (Branch if Less Than, unsigned) instruction - branch not taken.

    Test: BLTU x1, x2, 8 where x1=0xFFFFFFF6, x2=20
    Expected: Branch not taken (unsigned: 0xFFFFFFF6 > 20)
    """
    dut._log.info("=== Test: BLTU Not Taken ===")

    await run_isa_test(
        dut,
        BLTUSequence,
        {
            "name": "bltu_not_taken",
            "rs1": 1,
            "rs2": 2,
            "rs1_val": 0xFFFFFFF6,
            "rs2_val": 20,
            "branch_target_offset": 8,
            "expect_branch_taken": False
        },
        "test_isa_bltu_not_taken"
    )


@cocotb.test()
async def test_isa_bgeu_taken_uvm(dut):
    """
    Test BGEU (Branch if Greater or Equal, unsigned) instruction - branch taken.

    Test: BGEU x1, x2, 8 where x1=0xFFFFFFF6, x2=20
    Expected: Branch taken (unsigned: 0xFFFFFFF6 > 20)
    """
    dut._log.info("=== Test: BGEU Taken ===")

    await run_isa_test(
        dut,
        BGEUSequence,
        {
            "name": "bgeu_taken",
            "rs1": 1,
            "rs2": 2,
            "rs1_val": 0xFFFFFFF6,
            "rs2_val": 20,
            "branch_target_offset": 8,
            "expect_branch_taken": True
        },
        "test_isa_bgeu_taken"
    )


@cocotb.test()
async def test_isa_bgeu_not_taken_uvm(dut):
    """
    Test BGEU (Branch if Greater or Equal, unsigned) instruction - branch not taken.

    Test: BGEU x1, x2, 8 where x1=10, x2=20
    Expected: Branch not taken (unsigned: 10 < 20)
    """
    dut._log.info("=== Test: BGEU Not Taken ===")

    await run_isa_test(
        dut,
        BGEUSequence,
        {
            "name": "bgeu_not_taken",
            "rs1": 1,
            "rs2": 2,
            "rs1_val": 10,
            "rs2_val": 20,
            "branch_target_offset": 8,
            "expect_branch_taken": False
        },
        "test_isa_bgeu_not_taken"
    )


# =============================================================================
# Priority 5: Jump Instructions
# =============================================================================

@cocotb.test()
async def test_isa_jal_basic_uvm(dut):
    """
    Test JAL (Jump and Link) instruction - basic forward jump.

    Test: JAL x1, 16 (jump forward 16 bytes)
    Expected: x1 = PC+4 (return address), PC jumps to PC+16
    """
    dut._log.info("=== Test: JAL Basic ===")

    await run_isa_test(
        dut,
        JALSequence,
        {
            "name": "jal_basic",
            "rd": 1,
            "jump_offset": 16,
            "expected_return_addr": 4  # PC of JAL (0x0000) + 4
        },
        "test_isa_jal_basic"
    )


@cocotb.test()
async def test_isa_jal_backward_uvm(dut):
    """
    Test JAL instruction - backward jump (negative offset).

    Test: JAL x2, -8 (jump backward 8 bytes)
    Expected: x2 = PC+4 (return address)
    """
    dut._log.info("=== Test: JAL Backward ===")

    await run_isa_test(
        dut,
        JALSequence,
        {
            "name": "jal_backward",
            "rd": 2,
            "jump_offset": -8,  # Negative offset (backward jump)
            "expected_return_addr": 4  # Still PC+4
        },
        "test_isa_jal_backward"
    )


@cocotb.test()
async def test_isa_jalr_basic_uvm(dut):
    """
    Test JALR (Jump and Link Register) instruction - basic case.

    Test: JALR x3, x1, 8 where x1=0x1000
    Expected: x3 = PC+4, PC = (x1 + 8) & ~1 = 0x1008
    """
    dut._log.info("=== Test: JALR Basic ===")

    await run_isa_test(
        dut,
        JALRSequence,
        {
            "name": "jalr_basic",
            "rd": 3,
            "rs1": 1,
            "offset": 8,
            "rs1_val": 0x1000,
            "expected_return_addr": 4  # PC of JALR (0x0000) + 4
        },
        "test_isa_jalr_basic"
    )


@cocotb.test()
async def test_isa_jalr_zero_offset_uvm(dut):
    """
    Test JALR instruction - zero offset (direct jump to rs1).

    Test: JALR x4, x2, 0 where x2=0x2000
    Expected: x4 = PC+4, PC = x2 & ~1 = 0x2000
    """
    dut._log.info("=== Test: JALR Zero Offset ===")

    await run_isa_test(
        dut,
        JALRSequence,
        {
            "name": "jalr_zero_offset",
            "rd": 4,
            "rs1": 2,
            "offset": 0,
            "rs1_val": 0x2000,
            "expected_return_addr": 4
        },
        "test_isa_jalr_zero"
    )


# =============================================================================
# Priority 6: Upper Immediate Instructions
# =============================================================================

@cocotb.test()
async def test_isa_lui_basic_uvm(dut):
    """
    Test LUI (Load Upper Immediate) instruction - basic case.

    Test: LUI x5, 0x12345
    Expected: x5 = 0x12345000 (upper 20 bits loaded, lower 12 bits = 0)
    """
    dut._log.info("=== Test: LUI Basic ===")

    await run_isa_test(
        dut,
        LUISequence,
        {
            "name": "lui_basic",
            "rd": 5,
            "imm20": 0x12345,
            "expected_value": 0x12345000
        },
        "test_isa_lui_basic"
    )


@cocotb.test()
async def test_isa_lui_max_uvm(dut):
    """
    Test LUI instruction - maximum value.

    Test: LUI x6, 0xFFFFF
    Expected: x6 = 0xFFFFF000
    """
    dut._log.info("=== Test: LUI Max Value ===")

    await run_isa_test(
        dut,
        LUISequence,
        {
            "name": "lui_max",
            "rd": 6,
            "imm20": 0xFFFFF,
            "expected_value": 0xFFFFF000
        },
        "test_isa_lui_max"
    )


@cocotb.test()
async def test_isa_auipc_basic_uvm(dut):
    """
    Test AUIPC (Add Upper Immediate to PC) instruction - basic case.

    Test: AUIPC x7, 0x1000 (at PC=0x0000)
    Expected: x7 = 0x0000 + (0x1000 << 12) = 0x01000000
    """
    dut._log.info("=== Test: AUIPC Basic ===")

    await run_isa_test(
        dut,
        AUIPCSequence,
        {
            "name": "auipc_basic",
            "rd": 7,
            "imm20": 0x1000,
            "pc_at_auipc": 0x0000,  # PC when AUIPC executes
            "expected_value": 0x01000000  # 0x0000 + (0x1000 << 12)
        },
        "test_isa_auipc_basic"
    )


@cocotb.test()
async def test_isa_auipc_nonzero_pc_uvm(dut):
    """
    Test AUIPC instruction - non-zero PC.

    Test: AUIPC x8, 0x100 (at PC=0x1000)
    Expected: x8 = 0x1000 + (0x100 << 12) = 0x00101000
    """
    dut._log.info("=== Test: AUIPC Non-Zero PC ===")

    await run_isa_test(
        dut,
        AUIPCSequence,
        {
            "name": "auipc_nonzero_pc",
            "rd": 8,
            "imm20": 0x100,
            "pc_at_auipc": 0x1000,
            "expected_value": 0x00101000  # 0x1000 + (0x100 << 12)
        },
        "test_isa_auipc_nonzero"
    )


# =============================================================================
# ISA Compliance Test Summary - COMPLETE!
# =============================================================================
# All 37 RV32I base integer instructions now have pyuvm test coverage!
#
# Priority 1 - Load/Store (12 tests, 8 instructions): ✅ COMPLETE
#   - LW: 2 tests (basic, offset)
#   - SW: 2 tests (basic, offset)
#   - LB: 2 tests (positive byte, negative byte with sign extension)
#   - LBU: 1 test (zero extension)
#   - LH: 2 tests (positive halfword, negative halfword with sign extension)
#   - LHU: 1 test (zero extension)
#   - SB: 1 test
#   - SH: 1 test
#
# Priority 2 - Arithmetic/Logical (15 tests, 13 instructions): ✅ COMPLETE
#   - ADD: 2 tests (basic, overflow)
#   - SUB: 2 tests (basic, underflow)
#   - AND: 1 test
#   - OR: 1 test
#   - XOR: 1 test
#   - SLT: 1 test (signed comparison, true case)
#   - SLTU: 1 test (unsigned comparison, false case)
#   - ADDI: 1 test (positive immediate)
#   - SLTI: 1 test (signed comparison, true case)
#   - SLTIU: 1 test (unsigned comparison, false case)
#   - ANDI: 1 test
#   - ORI: 1 test
#   - XORI: 1 test
#
# Priority 3 - Shift Instructions (7 tests, 6 instructions): ✅ COMPLETE
#   - SLL: 2 tests (basic shift, max shift by 31)
#   - SLLI: 1 test (immediate shift left by 8)
#   - SRL: 1 test (logical right shift, zero-fill)
#   - SRLI: 1 test (immediate logical right shift by 8)
#   - SRA: 1 test (arithmetic right shift, sign-extend)
#   - SRAI: 1 test (immediate arithmetic right shift by 8)
#
# Priority 4 - Branch Instructions (12 tests, 6 instructions): ✅ COMPLETE
#   - BEQ: 2 tests (taken, not taken)
#   - BNE: 2 tests (taken, not taken)
#   - BLT: 2 tests (signed, taken and not taken)
#   - BGE: 2 tests (signed, taken and not taken)
#   - BLTU: 2 tests (unsigned, taken and not taken)
#   - BGEU: 2 tests (unsigned, taken and not taken)
#
# Priority 5 - Jump Instructions (4 tests, 2 instructions): ✅ COMPLETE
#   - JAL: 2 tests (forward jump, backward jump)
#   - JALR: 2 tests (with offset, zero offset)
#
# Priority 6 - Upper Immediate (4 tests, 2 instructions): ✅ COMPLETE
#   - LUI: 2 tests (basic, max value 0xFFFFF)
#   - AUIPC: 2 tests (from PC=0, from non-zero PC)
#
# =============================================================================
# TOTAL: 54 tests covering all 37 RV32I instructions
# Status: Phase E.3 ISA migration COMPLETE!
# Migration completed: 2026-02-01
# Previous status: 27 tests (21/37 instructions, 57% complete)
# New status: 54 tests (37/37 instructions, 100% COMPLETE!)
# Added: 27 tests for 16 missing instructions
# =============================================================================
