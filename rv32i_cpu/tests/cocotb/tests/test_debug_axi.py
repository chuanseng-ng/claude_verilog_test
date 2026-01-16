"""
Debug test to check AXI interface behavior
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
async def test_axi_signals(dut):
    """Test AXI signal behavior during CPU operation"""
    # Enable DEBUG logging for AXI agent
    logging.getLogger("cocotb.axi4lite_agent_driver").setLevel(logging.DEBUG)
    logging.getLogger("cocotb.axi4lite_agent_monitor").setLevel(logging.DEBUG)

    # Create environment
    env = RV32IEnvironment(dut)
    env.build()

    # Find the hex file
    hex_file = os.path.join(os.path.dirname(test_dir), '..', '..', 'tb', 'programs', 'simple_add.hex')

    # Load program BEFORE releasing reset
    env.log.info("Loading program: simple_add.hex")
    env.load_program(hex_file, base_addr=0)

    # Reset - this will start the CPU
    await env.reset(duration_ns=100)

    # Start monitors
    env.start_monitors()

    # Wait a few cycles and observe signals
    env.log.info("Observing CPU signals for 20 cycles")
    for cycle in range(20):
        await RisingEdge(dut.clk)

        # Log AXI AR channel status
        arvalid = int(dut.m_axi_arvalid.value)
        arready = int(dut.m_axi_arready.value)
        if arvalid:
            araddr = int(dut.m_axi_araddr.value)
            env.log.info(f"Cycle {cycle}: AR arvalid={arvalid} arready={arready} araddr=0x{araddr:08x}")

        # Log AXI R channel status
        rvalid = int(dut.m_axi_rvalid.value)
        rready = int(dut.m_axi_rready.value)
        if rvalid:
            rdata = int(dut.m_axi_rdata.value)
            env.log.info(f"Cycle {cycle}: R rvalid={rvalid} rready={rready} rdata=0x{rdata:08x}")

    # Check CPU status
    status = await env.apb_agent.driver.get_cpu_status()
    env.log.info(f"After 20 cycles: PC=0x{status['pc']:08x}, status=0x{status['status_reg']:08x}")

    # Stop monitors
    env.stop_monitors()
