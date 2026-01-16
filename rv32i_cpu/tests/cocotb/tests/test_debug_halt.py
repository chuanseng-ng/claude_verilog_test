"""
Debug test to check if EBREAK halts the CPU
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
async def test_halt_detection(dut):
    """Test if EBREAK instruction halts the CPU"""
    # Enable DEBUG logging for debug agent
    logging.getLogger("cocotb.apb3_agent_driver").setLevel(logging.DEBUG)

    # Create environment
    env = RV32IEnvironment(dut)
    env.build()

    # Find the hex file
    hex_file = os.path.join(os.path.dirname(test_dir), '..', '..', 'tb', 'programs', 'simple_add.hex')

    # Load program
    env.log.info("Loading program: simple_add.hex")
    env.load_program(hex_file, base_addr=0)

    # Reset
    await env.reset(duration_ns=100)

    # Start monitors
    env.start_monitors()

    # Wait many cycles and check for halt every 10 cycles
    env.log.info("Monitoring CPU for halt signal")
    for cycle in range(0, 200, 10):
        await ClockCycles(dut.clk, 10)

        # Check CPU status via debug interface
        try:
            status = await env.apb_agent.driver.get_cpu_status()
            env.log.info(f"Cycle {cycle}: halted={status['halted']} running={status['running']} PC=0x{status['pc']:08x}")

            if status['halted']:
                env.log.info(f"CPU halted at cycle {cycle}!")
                env.stop_monitors()
                return
        except Exception as e:
            env.log.error(f"Failed to read CPU status: {e}")

    env.log.warning("CPU never halted after 200 cycles")
    env.stop_monitors()
