"""
Debug test to probe internal CPU signals directly
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
async def test_internal_signals(dut):
    """Probe internal CPU signals to debug the issue"""
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

    # Observe internal signals for 100 cycles or until halted
    env.log.info("Probing internal CPU signals")
    prev_pc = 0
    for cycle in range(100):
        await RisingEdge(dut.clk)

        # Try to read internal core signals
        try:
            # Access core PC
            core_pc = int(dut.u_core.pc_q.value)
            # Access core state
            core_state = int(dut.u_core.cpu_state.value)
            # Access core instruction
            core_instr = int(dut.u_core.instr_q.value)
            # Access halted signal
            core_halted = int(dut.u_core.halted.value)
            # Access internal debug signals at top level
            dbg_pc_rdata = int(dut.dbg_pc_rdata.value)
            dbg_halted = int(dut.dbg_halted.value)

            # Log when PC changes or when halted
            if core_pc != prev_pc or core_halted:
                env.log.info(f"Cycle {cycle}: PC=0x{core_pc:08x} instr=0x{core_instr:08x} state={core_state} halted={core_halted}")

            if core_halted:
                env.log.info(f"CPU HALTED at cycle {cycle}!")
                break

            prev_pc = core_pc

        except AttributeError as e:
            env.log.error(f"Could not access signal: {e}")
            break

    env.log.info("Test completed")
