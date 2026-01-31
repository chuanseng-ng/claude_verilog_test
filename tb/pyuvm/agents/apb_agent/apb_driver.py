"""APB3 Debug Interface Driver for pyuvm.

This module implements a UVM driver for the APB3 debug interface.
It replaces the duplicate APBDebugInterface classes found in multiple test files.

Features:
- High-level debug operations (halt/resume/step)
- Register read/write when CPU is halted
- PC read/write
- Breakpoint control
- Unified implementation (eliminates duplication)
"""

import cocotb
from cocotb.triggers import RisingEdge, ReadOnly
from pyuvm import uvm_driver


class APBDebugDriver(uvm_driver):
    """UVM driver for APB3 debug interface.

    This driver provides high-level debug operations for the RV32I CPU.
    It abstracts the low-level APB3 protocol into convenient methods like
    halt_cpu(), resume_cpu(), write_gpr(), etc.

    The driver can operate in two modes:
    1. Direct mode: Direct APB signal manipulation (current implementation)
    2. BFM mode: Use APB3Master BFM (future enhancement)

    Attributes:
        dut: Device under test (DUT) handle

    Debug Register Map:
        0x000: DBG_CTRL - Control register
        0x004: DBG_STATUS - Status register
        0x008: DBG_PC - Program counter
        0x00C: DBG_INSTR - Current instruction (read-only)
        0x010-0x08C: DBG_GPR[0:31] - General purpose registers
        0x100: DBG_BP0_ADDR - Breakpoint 0 address
        0x104: DBG_BP0_CTRL - Breakpoint 0 control
    """

    # Debug register addresses
    DBG_CTRL = 0x000
    DBG_STATUS = 0x004
    DBG_PC = 0x008
    DBG_INSTR = 0x00C
    DBG_GPR_BASE = 0x010
    DBG_BP0_ADDR = 0x100
    DBG_BP0_CTRL = 0x104
    DBG_BP1_ADDR = 0x108
    DBG_BP1_CTRL = 0x10C

    def __init__(self, name, parent, dut):
        """Initialize APB debug driver.

        Args:
            name: Component name in UVM hierarchy
            parent: Parent UVM component
            dut: Device under test handle
        """
        super().__init__(name, parent)
        self.dut = dut

    def build_phase(self):
        """UVM build phase - called by framework."""
        super().build_phase()
        self.logger.info(f"Building {self.get_full_name()}")

    async def run_phase(self):
        """UVM run phase - APB driver is command-driven (no background tasks).

        Unlike the AXI driver which has background handlers, the APB driver
        is synchronous - it only acts when methods are called.
        """
        self.logger.info("APB debug driver ready")
        # APB driver is passive - just wait for test to call methods
        await cocotb.triggers.NullTrigger()

    async def apb_write(self, addr, data):
        """Write to APB debug register.

        APB Write Protocol:
        1. Assert psel + pwrite, set paddr + pwdata, penable=0
        2. Next cycle: Assert penable
        3. Next cycle: De-assert psel + penable

        Args:
            addr: Register address
            data: 32-bit data to write
        """
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
        """Read from APB debug register.

        APB Read Protocol:
        1. Assert psel, clear pwrite, set paddr, penable=0
        2. Next cycle: Assert penable
        3. Sample prdata at ReadOnly()
        4. Next cycle: De-assert psel + penable

        Args:
            addr: Register address

        Returns:
            32-bit data value read from register
        """
        await RisingEdge(self.dut.clk)
        self.dut.apb_psel.value = 1
        self.dut.apb_penable.value = 0
        self.dut.apb_pwrite.value = 0
        self.dut.apb_paddr.value = addr

        await RisingEdge(self.dut.clk)
        self.dut.apb_penable.value = 1

        await ReadOnly()
        data = int(self.dut.apb_prdata.value)

        await RisingEdge(self.dut.clk)
        self.dut.apb_psel.value = 0
        self.dut.apb_penable.value = 0

        return data

    async def halt_cpu(self):
        """Halt the CPU via debug interface.

        Writes halt bit (bit 0) to DBG_CTRL and polls DBG_STATUS
        until CPU confirms halted state.

        Raises:
            RuntimeError: If CPU does not halt within 10 cycles
        """
        await self.apb_write(self.DBG_CTRL, 0x1)

        # Poll status until halted (bit 0 of DBG_STATUS)
        for _ in range(10):
            status = await self.apb_read(self.DBG_STATUS)
            if status & 0x1:
                self.logger.info("CPU halted successfully")
                return
            await RisingEdge(self.dut.clk)

        raise RuntimeError("CPU did not halt within timeout")

    async def resume_cpu(self):
        """Resume the CPU via debug interface.

        Writes resume bit (bit 1) to DBG_CTRL and polls DBG_STATUS
        until CPU confirms running state.

        Raises:
            RuntimeError: If CPU does not resume within 10 cycles
        """
        await self.apb_write(self.DBG_CTRL, 0x2)

        # Poll status until running (bit 1 of DBG_STATUS)
        for _ in range(10):
            status = await self.apb_read(self.DBG_STATUS)
            if status & 0x2:
                self.logger.info("CPU resumed successfully")
                return
            await RisingEdge(self.dut.clk)

        raise RuntimeError("CPU did not resume within timeout")

    async def step_cpu(self):
        """Single-step the CPU (execute one instruction).

        Writes step bit (bit 2) to DBG_CTRL.
        CPU executes one instruction and returns to halted state.

        Note: CPU must be halted before calling this method.
        """
        await self.apb_write(self.DBG_CTRL, 0x4)
        self.logger.debug("CPU single-step executed")

    async def reset_cpu(self):
        """Reset the CPU via debug interface.

        Writes reset bit (bit 3) to DBG_CTRL.
        """
        await self.apb_write(self.DBG_CTRL, 0x8)
        self.logger.info("CPU reset via debug interface")

    async def write_gpr(self, reg_num, value):
        """Write general purpose register.

        Args:
            reg_num: Register number (0-31)
            value: 32-bit value to write

        Note: CPU must be halted for register writes to take effect.
              Writing to x0 has no effect (hardwired to zero).
        """
        if not (0 <= reg_num <= 31):
            raise ValueError(f"Invalid register number: {reg_num} (must be 0-31)")

        addr = self.DBG_GPR_BASE + (reg_num * 4)
        await self.apb_write(addr, value)
        self.logger.debug(f"Wrote x{reg_num} = 0x{value:08x}")

    async def read_gpr(self, reg_num):
        """Read general purpose register.

        Args:
            reg_num: Register number (0-31)

        Returns:
            32-bit register value

        Note: CPU must be halted for stable register reads.
        """
        if not (0 <= reg_num <= 31):
            raise ValueError(f"Invalid register number: {reg_num} (must be 0-31)")

        addr = self.DBG_GPR_BASE + (reg_num * 4)
        value = await self.apb_read(addr)
        self.logger.debug(f"Read x{reg_num} = 0x{value:08x}")
        return value

    async def write_pc(self, value):
        """Write program counter.

        Args:
            value: 32-bit PC value

        Note: CPU must be halted for PC writes to take effect.
        """
        await self.apb_write(self.DBG_PC, value)
        self.logger.debug(f"Wrote PC = 0x{value:08x}")

    async def read_pc(self):
        """Read program counter.

        Returns:
            32-bit PC value

        Note: CPU must be halted for stable PC reads.
        """
        value = await self.apb_read(self.DBG_PC)
        self.logger.debug(f"Read PC = 0x{value:08x}")
        return value

    async def read_current_instruction(self):
        """Read current instruction at PC.

        Returns:
            32-bit instruction word

        Note: This is read-only. CPU must be halted for stable reads.
        """
        value = await self.apb_read(self.DBG_INSTR)
        return value

    async def set_breakpoint(self, bp_num, addr, enable=True):
        """Set or clear a breakpoint.

        Args:
            bp_num: Breakpoint number (0 or 1)
            addr: Breakpoint address
            enable: True to enable, False to disable

        Raises:
            ValueError: If bp_num is not 0 or 1
        """
        if bp_num == 0:
            await self.apb_write(self.DBG_BP0_ADDR, addr)
            await self.apb_write(self.DBG_BP0_CTRL, 0x1 if enable else 0x0)
        elif bp_num == 1:
            await self.apb_write(self.DBG_BP1_ADDR, addr)
            await self.apb_write(self.DBG_BP1_CTRL, 0x1 if enable else 0x0)
        else:
            raise ValueError(f"Invalid breakpoint number: {bp_num} (must be 0 or 1)")

        action = "enabled" if enable else "disabled"
        self.logger.info(f"Breakpoint {bp_num} {action} at 0x{addr:08x}")

    async def clear_breakpoint(self, bp_num):
        """Clear a breakpoint.

        Args:
            bp_num: Breakpoint number (0 or 1)
        """
        await self.set_breakpoint(bp_num, 0, enable=False)
