"""
Basic CPU testbench using cocotb.

This testbench will be used in Phase 1+ when RTL exists.
For now, it serves as a template showing the verification approach.
"""

import cocotb
from cocotb.triggers import RisingEdge, Timer
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from tb.cocotb.common.clock_reset import setup_clock, reset_dut, wait_cycles
from tb.cocotb.common.scoreboard import CPUScoreboard
from tb.cocotb.bfm.axi4lite_master import AXI4LiteMaster
from tb.cocotb.bfm.apb3_master import APB3Master, APB3DebugInterface
from tb.models.rv32i_model import RV32IModel


@cocotb.test()
async def test_simple_add(dut):
    """
    Test simple ADD instruction.

    This is a template test - will work once RTL exists in Phase 1.
    """
    log = dut._log

    # Setup clock (100 MHz)
    await setup_clock(dut, clock_period_ns=10)

    # Apply reset
    await reset_dut(dut)

    log.info("Test started: Simple ADD instruction")

    # Initialize reference model
    ref_model = RV32IModel()

    # Load simple program into memory
    # Program: ADD x3, x1, x2 (assuming x1=10, x2=20)
    program = {
        0x0000: 0x002081B3,  # add x3, x1, x2
    }

    # TODO: Load program into RTL memory via AXI interface
    # (This will be implemented when RTL exists)

    # Set up initial register state via debug interface
    # apb = APB3Master(dut, "apb_", dut.clk, dut.rst_n)
    # debug = APB3DebugInterface(apb)
    # await debug.halt_cpu()
    # await debug.write_gpr(1, 10)  # x1 = 10
    # await debug.write_gpr(2, 20)  # x2 = 20
    # await debug.resume_cpu()

    # Wait for instruction to execute
    await wait_cycles(dut, 10)

    # Check result via debug interface
    # await debug.halt_cpu()
    # x3_value = await debug.read_gpr(3)
    # assert x3_value == 30, f"Expected x3=30, got {x3_value}"

    log.info("Test completed: Simple ADD instruction")


@cocotb.test()
async def test_branch_instruction(dut):
    """
    Test branch instruction (BEQ).

    Template test for Phase 1+.
    """
    log = dut._log

    # Setup clock
    await setup_clock(dut, clock_period_ns=10)

    # Apply reset
    await reset_dut(dut)

    log.info("Test started: Branch instruction")

    # Initialize reference model
    ref_model = RV32IModel()

    # Load program
    program = {
        0x0000: 0x00000093,  # addi x1, x0, 0
        0x0004: 0x00000113,  # addi x2, x0, 0
        0x0008: 0x00208463,  # beq x1, x2, 8  (branch if equal)
        0x000C: 0x00100193,  # addi x3, x0, 1  (skipped if branch taken)
        0x0014: 0x00200213,  # addi x4, x0, 2  (branch target)
    }

    # TODO: Load program and execute

    log.info("Test completed: Branch instruction")


@cocotb.test()
async def test_load_store(dut):
    """
    Test load and store instructions.

    Template test for Phase 1+.
    """
    log = dut._log

    # Setup clock
    await setup_clock(dut, clock_period_ns=10)

    # Apply reset
    await reset_dut(dut)

    log.info("Test started: Load/Store instructions")

    # Initialize reference model
    ref_model = RV32IModel()

    # Load program
    program = {
        0x0000: 0x100000B7,  # lui x1, 0x10000  (x1 = 0x10000000)
        0x0004: 0x12300113,  # addi x2, x0, 0x123
        0x0008: 0x0020A023,  # sw x2, 0(x1)     (store to memory)
        0x000C: 0x0000A183,  # lw x3, 0(x1)     (load from memory)
    }

    # TODO: Load program and execute

    log.info("Test completed: Load/Store instructions")


@cocotb.test()
async def test_random_instructions(dut):
    """
    Test random instruction sequence.

    Uses reference model scoreboard for comparison.
    Template test for Phase 1+.
    """
    log = dut._log

    # Setup clock
    await setup_clock(dut, clock_period_ns=10)

    # Apply reset
    await reset_dut(dut)

    log.info("Test started: Random instruction sequence")

    # Initialize reference model and scoreboard
    ref_model = RV32IModel()
    scoreboard = CPUScoreboard(ref_model, log)

    # TODO: Generate and execute random instructions
    # Monitor commit signals and check against scoreboard

    # For each committed instruction:
    # rtl_commit = {
    #     'pc': dut.commit_pc.value,
    #     'insn': dut.commit_insn.value,
    #     'rd': dut.commit_rd.value,
    #     'rd_value': dut.commit_rd_data.value,
    # }
    # scoreboard.check_commit(rtl_commit)

    # Generate report
    # passed = scoreboard.report()
    # assert passed, "Scoreboard detected mismatches"

    log.info("Test completed: Random instruction sequence")


# NOTE: These tests are templates for Phase 1+
# They show the structure but won't run until RTL exists
# To make them runnable now, you would need to:
# 1. Create a mock DUT with the expected signals
# 2. Or wait until Phase 1 RTL implementation
