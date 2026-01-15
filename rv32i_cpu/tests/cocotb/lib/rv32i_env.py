"""
RV32I CPU Test Environment

Provides a complete test environment for the RV32I CPU with:
- AXI4-Lite memory agent
- APB3 debug agent
- Reset sequencing
- Test utilities
"""

import cocotb
from cocotb.triggers import RisingEdge, Timer, ClockCycles
from cocotb.clock import Clock
import logging
import sys
import os

# Add lib directory to path
sys.path.insert(0, os.path.dirname(__file__))
from agents.axi4lite_agent import AXI4LiteAgent
from agents.apb3_agent import APB3Agent


class RV32IEnvironment:
    """
    Main test environment for RV32I CPU
    Similar to UVM environment - contains all agents and provides test utilities
    """

    def __init__(self, dut, clk_period_ns: int = 10, mem_size: int = 64*1024):
        self.dut = dut
        self.clk_period_ns = clk_period_ns
        self.mem_size = mem_size
        self.log = logging.getLogger("cocotb.rv32i_env")

        # Clock will be started in build phase
        self.clk = None

        # Agents
        self.axi_agent: AXI4LiteAgent = None
        self.apb_agent: APB3Agent = None

    def build(self) -> None:
        """Build phase - create all components"""
        self.log.info("Building RV32I Environment")

        # Create clock
        self.clk = self.dut.clk
        cocotb.start_soon(Clock(self.clk, self.clk_period_ns, unit="ns").start())

        # Create agents
        self.axi_agent = AXI4LiteAgent(
            self.dut,
            self.clk,
            name="axi4lite_agent",
            mem_size=self.mem_size,
            read_latency=1,
            write_latency=1
        )

        self.apb_agent = APB3Agent(
            self.dut,
            self.clk,
            name="apb3_agent"
        )

        self.log.info("RV32I Environment built successfully")

    async def reset(self, duration_ns: int = 100) -> None:
        """Reset the DUT"""
        self.log.info(f"Asserting reset for {duration_ns}ns")

        # Assert reset
        self.dut.rst_n.value = 0

        # Reset agents
        await self.axi_agent.reset()
        await self.apb_agent.reset()

        # Wait for reset duration
        await Timer(duration_ns, unit="ns")

        # Deassert reset
        await RisingEdge(self.clk)
        self.dut.rst_n.value = 1

        # Wait a few clocks after reset
        await ClockCycles(self.clk, 5)

        self.log.info("Reset completed")

    def start_monitors(self) -> None:
        """Start all monitors"""
        self.log.info("Starting monitors")
        self.axi_agent.start_monitor()
        self.apb_agent.start_monitor()

    def stop_monitors(self) -> None:
        """Stop all monitors"""
        self.log.info("Stopping monitors")
        self.axi_agent.stop_monitor()
        self.apb_agent.stop_monitor()

    def load_program(self, hex_file: str, base_addr: int = 0) -> None:
        """Load a program into memory"""
        self.log.info(f"Loading program: {hex_file}")
        self.axi_agent.driver.load_program(hex_file, base_addr)

    async def wait_for_completion(self, max_cycles: int = 10000, check_halted: bool = True) -> bool:
        """
        Wait for program completion
        Returns True if completed successfully, False if timeout
        """
        for cycle in range(max_cycles):
            await RisingEdge(self.clk)

            if check_halted:
                # Check if CPU is halted (could be due to EBREAK or breakpoint)
                status = await self.apb_agent.driver.get_cpu_status()
                if status['halted']:
                    self.log.info(f"CPU halted after {cycle} cycles")
                    return True

        self.log.warning(f"Timeout after {max_cycles} cycles")
        return False

    async def run_program(self, hex_file: str, max_cycles: int = 10000,
                         base_addr: int = 0, check_halted: bool = True) -> bool:
        """
        Complete sequence to load and run a program

        Args:
            hex_file: Path to hex file
            max_cycles: Maximum cycles to wait
            base_addr: Base address to load program
            check_halted: Whether to check for halt condition

        Returns:
            True if program completed, False if timeout
        """
        # Load program
        self.load_program(hex_file, base_addr)

        # Wait for completion
        return await self.wait_for_completion(max_cycles, check_halted)

    async def verify_register(self, reg: int, expected: int, mask: int = 0xFFFFFFFF) -> bool:
        """
        Verify a register value

        Args:
            reg: Register number (0-31)
            expected: Expected value
            mask: Bit mask for comparison

        Returns:
            True if value matches, False otherwise
        """
        # Halt CPU if not already halted
        status = await self.apb_agent.driver.get_cpu_status()
        was_running = status['running']

        if was_running:
            await self.apb_agent.halt_cpu()

        # Read register
        actual = await self.apb_agent.read_gpr(reg)

        # Resume if it was running
        if was_running:
            await self.apb_agent.resume_cpu()

        # Compare
        if (actual & mask) == (expected & mask):
            self.log.info(f"Register x{reg} verified: 0x{actual:08x} == 0x{expected:08x}")
            return True
        else:
            self.log.error(f"Register x{reg} mismatch: got 0x{actual:08x}, expected 0x{expected:08x}")
            return False

    async def dump_state(self) -> dict:
        """Dump CPU state for debugging"""
        # Halt CPU if not already halted
        status = await self.apb_agent.driver.get_cpu_status()
        was_running = status['running']

        if was_running:
            await self.apb_agent.halt_cpu()
            # Re-read status after halting to get fresh halted state
            status = await self.apb_agent.driver.get_cpu_status()

        # Get all state
        state = {
            'status': status,
            'registers': await self.apb_agent.driver.dump_registers()
        }

        # Resume if it was running
        if was_running:
            await self.apb_agent.resume_cpu()

        return state

    def print_state(self, state: dict) -> None:
        """Print CPU state in a readable format"""
        self.log.info("=" * 60)
        self.log.info("CPU State Dump")
        self.log.info("=" * 60)
        self.log.info(f"PC: 0x{state['status']['pc']:08x}")
        self.log.info(f"Instruction: 0x{state['status']['instruction']:08x}")
        self.log.info(f"Halted: {state['status']['halted']}")
        self.log.info(f"Running: {state['status']['running']}")
        self.log.info("")
        self.log.info("Registers:")
        for i in range(0, 32, 4):
            line = ""
            for j in range(4):
                if i + j < 32:
                    reg_name = f"x{i+j}"
                    reg_val = state['registers'][reg_name]
                    line += f"  {reg_name:3s}=0x{reg_val:08x}"
            self.log.info(line)
        self.log.info("=" * 60)
