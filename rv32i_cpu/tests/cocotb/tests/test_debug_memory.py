"""
Debug test to check memory loading
"""

import cocotb
from cocotb.triggers import RisingEdge, ClockCycles
from cocotb.clock import Clock
import logging
import sys
import os

# Add lib directory to path
test_dir = os.path.dirname(os.path.abspath(__file__))
lib_dir = os.path.join(os.path.dirname(test_dir), 'lib')
sys.path.insert(0, lib_dir)

from rv32i_env import RV32IEnvironment


@cocotb.test()
async def test_memory_load(dut):
    """Test memory loading and reading"""
    # Create environment
    env = RV32IEnvironment(dut)
    env.build()

    # Find the hex file
    hex_file = os.path.join(os.path.dirname(test_dir), '..', '..', 'tb', 'programs', 'simple_add.hex')

    # Load program
    env.log.info("Loading program: simple_add.hex")
    env.load_program(hex_file, base_addr=0)

    # Check what's in memory
    driver = env.axi_agent.driver
    env.log.info(f"Memory dictionary has {len(driver.memory)} entries")
    env.log.info(f"First 10 memory entries:")
    for addr in range(40):
        if addr in driver.memory:
            env.log.info(f"  memory[{addr}] = 0x{driver.memory[addr]:02x}")

    # Try reading words from memory
    env.log.info("Reading words from memory using read_word:")
    for addr in [0x00, 0x04, 0x08, 0x0C]:
        word = driver.read_word(addr)
        env.log.info(f"  read_word(0x{addr:08x}) = 0x{word:08x}")

    env.log.info("Test completed")
