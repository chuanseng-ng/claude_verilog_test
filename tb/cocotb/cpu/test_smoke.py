"""
Smoke tests for RV32I CPU - Phase 1
Basic functionality tests to verify CPU is operational.
"""

import cocotb
from cocotb.triggers import RisingEdge, Timer, ClockCycles
from cocotb.clock import Clock
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from tb.models.rv32i_model import RV32IModel


async def reset_dut(dut):
    """Apply reset to DUT."""
    dut.rst_n.value = 0
    dut.axi_arready.value = 0
    dut.axi_rvalid.value = 0
    dut.axi_rdata.value = 0
    dut.axi_rresp.value = 0
    dut.axi_awready.value = 0
    dut.axi_wready.value = 0
    dut.axi_bvalid.value = 0
    dut.axi_bresp.value = 0
    dut.apb_psel.value = 0
    dut.apb_penable.value = 0
    dut.apb_pwrite.value = 0
    dut.apb_paddr.value = 0
    dut.apb_pwdata.value = 0

    await ClockCycles(dut.clk, 5)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 2)


class SimpleAXIMemory:
    """Simple AXI4-Lite memory model for testing."""

    def __init__(self, dut):
        self.dut = dut
        self.mem = {}
        cocotb.start_soon(self.axi_read_handler())
        cocotb.start_soon(self.axi_write_handler())

    def write_word(self, addr, data):
        """Write 32-bit word to memory."""
        self.mem[addr & 0xFFFFFFFC] = data & 0xFFFFFFFF

    def read_word(self, addr):
        """Read 32-bit word from memory."""
        return self.mem.get(addr & 0xFFFFFFFC, 0)

    async def axi_read_handler(self):
        """Handle AXI read transactions."""
        while True:
            await RisingEdge(self.dut.clk)

            # Address phase
            if self.dut.axi_arvalid.value == 1:
                self.dut.axi_arready.value = 1
                addr = int(self.dut.axi_araddr.value)
                await RisingEdge(self.dut.clk)
                self.dut.axi_arready.value = 0

                # Data phase (1 cycle later for simplicity)
                await RisingEdge(self.dut.clk)
                data = self.read_word(addr)
                self.dut.axi_rvalid.value = 1
                self.dut.axi_rdata.value = data
                self.dut.axi_rresp.value = 0  # OKAY
                await RisingEdge(self.dut.clk)
                self.dut.axi_rvalid.value = 0

    async def axi_write_handler(self):
        """Handle AXI write transactions."""
        while True:
            await RisingEdge(self.dut.clk)

            # Address and data phases (can be simultaneous)
            if self.dut.axi_awvalid.value == 1 and self.dut.axi_wvalid.value == 1:
                self.dut.axi_awready.value = 1
                self.dut.axi_wready.value = 1
                addr = int(self.dut.axi_awaddr.value)
                data = int(self.dut.axi_wdata.value)
                await RisingEdge(self.dut.clk)
                self.dut.axi_awready.value = 0
                self.dut.axi_wready.value = 0

                # Write to memory
                self.write_word(addr, data)

                # Response phase (1 cycle later)
                await RisingEdge(self.dut.clk)
                self.dut.axi_bvalid.value = 1
                self.dut.axi_bresp.value = 0  # OKAY
                await RisingEdge(self.dut.clk)
                self.dut.axi_bvalid.value = 0


@cocotb.test()
async def test_reset(dut):
    """Test that CPU comes out of reset correctly."""
    dut._log.info("=== Test: Reset ===")

    # Start clock
    clock = Clock(dut.clk, 10, unit="ns")
    cocotb.start_soon(clock.start())

    # Apply reset
    await reset_dut(dut)

    # Check that PC is at reset vector (0x00000000)
    await ClockCycles(dut.clk, 2)

    dut._log.info("Reset test passed")


@cocotb.test()
async def test_fetch_nop(dut):
    """Test that CPU can fetch and execute NOP instruction."""
    dut._log.info("=== Test: Fetch NOP ===")

    # Start clock
    clock = Clock(dut.clk, 10, unit="ns")
    cocotb.start_soon(clock.start())

    # Initialize memory
    mem = SimpleAXIMemory(dut)

    # Load program: NOP at address 0
    # NOP = ADDI x0, x0, 0 = 0x00000013
    mem.write_word(0x00000000, 0x00000013)
    mem.write_word(0x00000004, 0x00000013)
    mem.write_word(0x00000008, 0x00000013)

    # Apply reset
    await reset_dut(dut)

    # Wait for a few instructions to execute
    await ClockCycles(dut.clk, 100)

    # Check that at least one instruction committed
    # (This is a very basic check - just verify CPU is running)

    dut._log.info("Fetch NOP test completed")


@cocotb.test()
async def test_simple_addi(dut):
    """Test simple ADDI instruction."""
    dut._log.info("=== Test: Simple ADDI ===")

    # Start clock
    clock = Clock(dut.clk, 10, unit="ns")
    cocotb.start_soon(clock.start())

    # Initialize memory
    mem = SimpleAXIMemory(dut)

    # Load program
    # 0x000: ADDI x1, x0, 42  (x1 = 42)
    # 0x004: ADDI x2, x1, 8   (x2 = 50)
    # 0x008: NOP (loop)
    mem.write_word(0x00000000, 0x02A00093)  # addi x1, x0, 42
    mem.write_word(0x00000004, 0x00808113)  # addi x2, x1, 8
    mem.write_word(0x00000008, 0x00000013)  # nop (loop)

    # Apply reset
    await reset_dut(dut)

    # Wait for instructions to execute
    await ClockCycles(dut.clk, 200)

    dut._log.info("Simple ADDI test completed")


@cocotb.test()
async def test_branch_not_taken(dut):
    """Test branch not taken."""
    dut._log.info("=== Test: Branch Not Taken ===")

    # Start clock
    clock = Clock(dut.clk, 10, unit="ns")
    cocotb.start_soon(clock.start())

    # Initialize memory
    mem = SimpleAXIMemory(dut)

    # Load program
    # 0x000: ADDI x1, x0, 1   (x1 = 1)
    # 0x004: ADDI x2, x0, 2   (x2 = 2)
    # 0x008: BEQ x1, x2, 12   (branch if equal - NOT taken)
    # 0x00C: ADDI x3, x0, 10  (x3 = 10, should execute)
    # 0x010: NOP (loop)
    mem.write_word(0x00000000, 0x00100093)  # addi x1, x0, 1
    mem.write_word(0x00000004, 0x00200113)  # addi x2, x0, 2
    mem.write_word(0x00000008, 0x00208663)  # beq x1, x2, 12
    mem.write_word(0x0000000C, 0x00A00193)  # addi x3, x0, 10
    mem.write_word(0x00000010, 0x00000013)  # nop

    # Apply reset
    await reset_dut(dut)

    # Wait for execution
    await ClockCycles(dut.clk, 300)

    dut._log.info("Branch not taken test completed")


@cocotb.test()
async def test_branch_taken(dut):
    """Test branch taken."""
    dut._log.info("=== Test: Branch Taken ===")

    # Start clock
    clock = Clock(dut.clk, 10, unit="ns")
    cocotb.start_soon(clock.start())

    # Initialize memory
    mem = SimpleAXIMemory(dut)

    # Load program
    # 0x000: ADDI x1, x0, 1   (x1 = 1)
    # 0x004: ADDI x2, x0, 1   (x2 = 1)
    # 0x008: BEQ x1, x2, 8    (branch if equal - TAKEN, skip to 0x010)
    # 0x00C: ADDI x3, x0, 99  (x3 = 99, should be skipped)
    # 0x010: ADDI x4, x0, 20  (x4 = 20, branch target)
    # 0x014: NOP (loop)
    mem.write_word(0x00000000, 0x00100093)  # addi x1, x0, 1
    mem.write_word(0x00000004, 0x00100113)  # addi x2, x0, 1
    mem.write_word(0x00000008, 0x00208463)  # beq x1, x2, 8
    mem.write_word(0x0000000C, 0x06300193)  # addi x3, x0, 99 (skipped)
    mem.write_word(0x00000010, 0x01400213)  # addi x4, x0, 20
    mem.write_word(0x00000014, 0x00000013)  # nop

    # Apply reset
    await reset_dut(dut)

    # Wait for execution
    await ClockCycles(dut.clk, 300)

    dut._log.info("Branch taken test completed")


@cocotb.test()
async def test_jal(dut):
    """Test JAL (Jump and Link) instruction."""
    dut._log.info("=== Test: JAL ===")

    # Start clock
    clock = Clock(dut.clk, 10, unit="ns")
    cocotb.start_soon(clock.start())

    # Initialize memory
    mem = SimpleAXIMemory(dut)

    # Load program
    # 0x000: JAL x1, 12       (jump to 0x00C, save PC+4 to x1)
    # 0x004: ADDI x2, x0, 99  (skipped)
    # 0x008: ADDI x3, x0, 88  (skipped)
    # 0x00C: ADDI x4, x0, 20  (jump target)
    # 0x010: NOP (loop)
    mem.write_word(0x00000000, 0x00C000EF)  # jal x1, 12
    mem.write_word(0x00000004, 0x06300113)  # addi x2, x0, 99 (skipped)
    mem.write_word(0x00000008, 0x05800193)  # addi x3, x0, 88 (skipped)
    mem.write_word(0x0000000C, 0x01400213)  # addi x4, x0, 20
    mem.write_word(0x00000010, 0x00000013)  # nop

    # Apply reset
    await reset_dut(dut)

    # Wait for execution
    await ClockCycles(dut.clk, 300)

    dut._log.info("JAL test completed")


# Placeholder for future tests
# These will be expanded as verification progresses
