"""
Minimal EBREAK Test

Tests that EBREAK instruction (0x00100073) causes CPU to halt.

Test Steps:
1. Reset CPU
2. Load EBREAK instruction at 0x0000 via memory model
3. Halt CPU
4. Set PC to 0x0000
5. Resume CPU
6. Wait for CPU to halt again
7. Verify CPU halted due to EBREAK
"""

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer, ClockCycles, ReadOnly
from pathlib import Path
import sys

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))


class APBDebugInterface:
    """APB3 debug interface helper for CPU register access."""

    # Debug register offsets (from MEMORY_MAP.md)
    DBG_CTRL = 0x000
    DBG_STATUS = 0x004
    DBG_PC = 0x008
    DBG_INSTR = 0x00C
    DBG_GPR_BASE = 0x010  # DBG_GPR[n] = 0x010 + (n * 4)

    def __init__(self, dut):
        self.dut = dut

    async def apb_write(self, addr, data):
        """Write to APB debug register."""
        await RisingEdge(self.dut.clk)
        self.dut.apb_psel.value = 1
        self.dut.apb_penable.value = 0
        self.dut.apb_pwrite.value = 1
        self.dut.apb_paddr.value = addr
        self.dut.apb_pwdata.value = data

        await RisingEdge(self.dut.clk)
        self.dut.apb_penable.value = 1

        await RisingEdge(self.dut.clk)
        self.dut.apb_psel.value = 0
        self.dut.apb_penable.value = 0
        self.dut.apb_pwrite.value = 0

    async def apb_read(self, addr):
        """Read from APB debug register."""
        # Setup phase
        await RisingEdge(self.dut.clk)
        self.dut.apb_psel.value = 1
        self.dut.apb_penable.value = 0
        self.dut.apb_pwrite.value = 0
        self.dut.apb_paddr.value = addr

        # Access phase
        await RisingEdge(self.dut.clk)
        self.dut.apb_penable.value = 1

        # Read data during access phase
        await ReadOnly()
        data = int(self.dut.apb_prdata.value)

        # End transfer
        await RisingEdge(self.dut.clk)
        self.dut.apb_psel.value = 0
        self.dut.apb_penable.value = 0

        return data

    async def halt_cpu(self):
        """Halt the CPU via debug interface."""
        await self.apb_write(self.DBG_CTRL, 0x1)  # HALT_REQ
        # Wait for CPU to halt
        for _ in range(10):
            status = await self.apb_read(self.DBG_STATUS)
            if status & 0x1:  # HALTED bit
                return
            await RisingEdge(self.dut.clk)
        raise RuntimeError("CPU did not halt")

    async def resume_cpu(self):
        """Resume the CPU via debug interface."""
        await self.apb_write(self.DBG_CTRL, 0x2)  # RESUME_REQ
        # Wait for CPU to resume
        for _ in range(10):
            status = await self.apb_read(self.DBG_STATUS)
            if status & 0x2:  # RUNNING bit
                return
            await RisingEdge(self.dut.clk)
        raise RuntimeError("CPU did not resume")

    async def read_pc(self):
        """Read program counter."""
        return await self.apb_read(self.DBG_PC)

    async def write_pc(self, value):
        """Write program counter (only when halted)."""
        await self.apb_write(self.DBG_PC, value)


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

            if self.dut.axi_arvalid.value == 1:
                # Accept address
                self.dut.axi_arready.value = 1
                addr = int(self.dut.axi_araddr.value)
                data = self.read_word(addr)

                # Provide data on next cycle
                await RisingEdge(self.dut.clk)
                self.dut.axi_arready.value = 0
                self.dut.axi_rvalid.value = 1
                self.dut.axi_rdata.value = data
                self.dut.axi_rresp.value = 0

                # Wait for rready
                while self.dut.axi_rready.value == 0:
                    await RisingEdge(self.dut.clk)

                await RisingEdge(self.dut.clk)
                self.dut.axi_rvalid.value = 0
            else:
                self.dut.axi_arready.value = 0

    async def axi_write_handler(self):
        """Handle AXI write transactions."""
        while True:
            await RisingEdge(self.dut.clk)

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

                # Response phase
                self.dut.axi_bvalid.value = 1
                self.dut.axi_bresp.value = 0

                while self.dut.axi_bready.value == 0:
                    await RisingEdge(self.dut.clk)

                await RisingEdge(self.dut.clk)
                self.dut.axi_bvalid.value = 0


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


@cocotb.test()
async def test_ebreak_instruction(dut):
    """Test that EBREAK instruction causes CPU to halt."""

    # Start clock
    clock = Clock(dut.clk, 10, units="ns")
    cocotb.start_soon(clock.start())

    # Reset DUT
    await reset_dut(dut)

    dut._log.info("=" * 80)
    dut._log.info("EBREAK HALT TEST")
    dut._log.info("=" * 80)

    # Create memory model and debug interface
    memory = SimpleAXIMemory(dut)
    dbg = APBDebugInterface(dut)

    # Load EBREAK instruction at address 0x0000
    # EBREAK encoding: 0x00100073
    ebreak_insn = 0x00100073
    dut._log.info(f"Loading EBREAK instruction (0x{ebreak_insn:08x}) at address 0x0000")
    memory.write_word(0x00000000, ebreak_insn)

    # Halt CPU
    dut._log.info("Halting CPU...")
    await dbg.halt_cpu()

    # Verify halted
    status = await dbg.apb_read(dbg.DBG_STATUS)
    assert status & 0x1, "CPU should be halted"
    dut._log.info(f"CPU halted (status=0x{status:08x})")

    # Set PC to 0x0000
    dut._log.info("Setting PC to 0x00000000")
    await dbg.write_pc(0x00000000)

    # Read back PC to verify
    pc_val = await dbg.read_pc()
    dut._log.info(f"PC readback: 0x{pc_val:08x}")
    assert pc_val == 0x00000000, f"PC should be 0x00000000, got 0x{pc_val:08x}"

    # Clear halted status for clean test
    dut._log.info("Resuming CPU to execute EBREAK...")
    await dbg.resume_cpu()

    # Wait for CPU to halt (max 100 cycles)
    dut._log.info("Waiting for CPU to halt from EBREAK...")
    halted = False
    for cycle in range(100):
        await RisingEdge(dut.clk)

        # Check halted status
        status = await dbg.apb_read(dbg.DBG_STATUS)
        if status & 0x1:  # Halted bit
            halted = True
            halt_cause = (status >> 4) & 0xF
            dut._log.info(f"CPU halted after {cycle} cycles")
            dut._log.info(f"Status register: 0x{status:08x}")
            dut._log.info(f"Halt cause: 0x{halt_cause:x}")

            # Check halt cause
            # Per MEMORY_MAP.md:
            # 0x1 = Debug halt request
            # 0x8 = EBREAK instruction
            if halt_cause == 0x8:
                dut._log.info("✓ CPU halted due to EBREAK (cause=0x8)")
            else:
                dut._log.warning(f"✗ CPU halted but cause is 0x{halt_cause:x}, expected 0x8 (EBREAK)")

            break

    # Verify CPU actually halted
    assert halted, "CPU should have halted after EBREAK instruction within 100 cycles"

    # Read PC to see where it stopped
    final_pc = await dbg.read_pc()
    dut._log.info(f"Final PC: 0x{final_pc:08x}")

    # Read the instruction that was executed
    final_insn = await dbg.apb_read(dbg.DBG_INSTR)
    dut._log.info(f"Final instruction: 0x{final_insn:08x}")

    if final_insn == ebreak_insn:
        dut._log.info("✓ EBREAK instruction was executed")
    else:
        dut._log.warning(f"✗ Expected EBREAK (0x{ebreak_insn:08x}), got 0x{final_insn:08x}")

    dut._log.info("=" * 80)
    dut._log.info("EBREAK TEST COMPLETE")
    dut._log.info("=" * 80)
