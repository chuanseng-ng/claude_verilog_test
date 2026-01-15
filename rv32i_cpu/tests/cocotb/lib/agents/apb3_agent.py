"""
APB3 Master Agent for Debug Interface

Provides a cocotb-based APB3 master agent with:
- Read/write operations for debug registers
- CPU control functions (halt, resume, step, reset)
- Register access utilities
- Transaction monitoring
"""

import cocotb
from cocotb.triggers import RisingEdge, ReadOnly
from typing import Optional
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from utils.base_components import BaseTransaction, BaseDriver, BaseMonitor, BaseAgent

# Debug register addresses (from CLAUDE.md)
DBG_CTRL = 0x000
DBG_STATUS = 0x004
DBG_PC = 0x008
DBG_INSTR = 0x00C
DBG_GPR_BASE = 0x010  # GPR[0] at 0x010, GPR[31] at 0x08C
DBG_BP0_ADDR = 0x100
DBG_BP0_CTRL = 0x104
DBG_BP1_ADDR = 0x108
DBG_BP1_CTRL = 0x10C

# Control register bit positions
CTRL_HALT = 0
CTRL_RESUME = 1
CTRL_STEP = 2
CTRL_RESET = 3

# Status register bit positions
STATUS_HALTED = 0
STATUS_RUNNING = 1


class APB3Transaction(BaseTransaction):
    """APB3 transaction item"""

    def __init__(self, name: str = "apb3_txn"):
        super().__init__(name)
        self.paddr: int = 0
        self.pwrite: bool = False
        self.pwdata: int = 0
        self.prdata: int = 0
        self.psel: bool = False
        self.penable: bool = False
        self.pready: bool = False

    def copy(self) -> 'APB3Transaction':
        """Create a copy of this transaction"""
        txn = APB3Transaction(self.name)
        txn.paddr = self.paddr
        txn.pwrite = self.pwrite
        txn.pwdata = self.pwdata
        txn.prdata = self.prdata
        txn.psel = self.psel
        txn.penable = self.penable
        txn.pready = self.pready
        return txn

    def __str__(self) -> str:
        if self.pwrite:
            return f"APB3 WR: addr=0x{self.paddr:03x} data=0x{self.pwdata:08x}"
        else:
            return f"APB3 RD: addr=0x{self.paddr:03x} data=0x{self.prdata:08x}"


class APB3MasterDriver(BaseDriver):
    """APB3 Master Driver for Debug Interface"""

    def __init__(self, dut, clk, name: str = "apb3_master"):
        super().__init__(dut, clk, name)

    async def reset(self) -> None:
        """Reset all APB signals"""
        self.dut.apb_paddr.value = 0
        self.dut.apb_psel.value = 0
        self.dut.apb_penable.value = 0
        self.dut.apb_pwrite.value = 0
        self.dut.apb_pwdata.value = 0

    async def write(self, addr: int, data: int, timeout_cycles: int = 1000) -> None:
        """Perform an APB3 write transaction"""
        self.log.debug(f"APB3 Write: addr=0x{addr:03x} data=0x{data:08x}")

        # Setup phase
        await RisingEdge(self.clk)
        self.dut.apb_paddr.value = addr
        self.dut.apb_pwrite.value = 1
        self.dut.apb_pwdata.value = data
        self.dut.apb_psel.value = 1
        self.dut.apb_penable.value = 0

        # Access phase
        await RisingEdge(self.clk)
        self.dut.apb_penable.value = 1

        # Wait for ready with timeout
        for _cycle in range(timeout_cycles):
            if int(self.dut.apb_pready.value):
                break
            await RisingEdge(self.clk)
        else:
            self.log.error(f"APB3 write timeout at addr=0x{addr:03x}")
            raise TimeoutError(f"APB3 write timeout waiting for pready at addr=0x{addr:03x}")

        # End transaction
        await RisingEdge(self.clk)
        self.dut.apb_psel.value = 0
        self.dut.apb_penable.value = 0
        self.dut.apb_pwrite.value = 0

    async def read(self, addr: int, timeout_cycles: int = 1000) -> int:
        """Perform an APB3 read transaction"""
        # Setup phase
        await RisingEdge(self.clk)
        self.dut.apb_paddr.value = addr
        self.dut.apb_pwrite.value = 0
        self.dut.apb_psel.value = 1
        self.dut.apb_penable.value = 0

        # Access phase
        await RisingEdge(self.clk)
        self.dut.apb_penable.value = 1

        # Wait for ready with timeout
        for _cycle in range(timeout_cycles):
            if int(self.dut.apb_pready.value):
                break
            await RisingEdge(self.clk)
        else:
            self.log.error(f"APB3 read timeout at addr=0x{addr:03x}")
            raise TimeoutError(f"APB3 read timeout waiting for pready at addr=0x{addr:03x}")

        # Capture data
        data = int(self.dut.apb_prdata.value)

        # End transaction
        await RisingEdge(self.clk)
        self.dut.apb_psel.value = 0
        self.dut.apb_penable.value = 0

        self.log.debug(f"APB3 Read: addr=0x{addr:03x} data=0x{data:08x}")
        return data

    async def halt_cpu(self) -> None:
        """Halt the CPU via debug interface"""
        self.log.info("Halting CPU")
        await self.write(DBG_CTRL, 1 << CTRL_HALT)

        # Wait for halted status
        for _ in range(100):
            status = await self.read(DBG_STATUS)
            if status & (1 << STATUS_HALTED):
                self.log.info("CPU halted successfully")
                return
            await RisingEdge(self.clk)

        self.log.error("CPU failed to halt")
        raise TimeoutError(f"CPU failed to halt after 100 cycles (last status: 0x{status:08x})")

    async def resume_cpu(self) -> None:
        """Resume the CPU from halt"""
        self.log.info("Resuming CPU")
        await self.write(DBG_CTRL, 1 << CTRL_RESUME)

        # Wait for running status
        for _ in range(100):
            status = await self.read(DBG_STATUS)
            if status & (1 << STATUS_RUNNING):
                self.log.info("CPU resumed successfully")
                return
            await RisingEdge(self.clk)

        self.log.error("CPU failed to resume")
        raise TimeoutError(f"CPU failed to resume after 100 cycles (last status: 0x{status:08x})")

    async def step_cpu(self) -> None:
        """Execute a single instruction"""
        self.log.info("Stepping CPU")
        await self.write(DBG_CTRL, 1 << CTRL_STEP)
        await RisingEdge(self.clk)

    async def reset_cpu(self) -> None:
        """Reset the CPU via debug interface"""
        self.log.info("Resetting CPU via debug")
        await self.write(DBG_CTRL, 1 << CTRL_RESET)
        await RisingEdge(self.clk)

    async def read_pc(self) -> int:
        """Read the program counter"""
        return await self.read(DBG_PC)

    async def write_pc(self, value: int) -> None:
        """Write the program counter (only when halted)"""
        await self.write(DBG_PC, value)

    async def read_gpr(self, reg: int) -> int:
        """Read a general purpose register (0-31)"""
        if reg < 0 or reg > 31:
            raise ValueError(f"Invalid register number: {reg}")
        return await self.read(DBG_GPR_BASE + (reg * 4))

    async def write_gpr(self, reg: int, value: int) -> None:
        """Write a general purpose register (only when halted)"""
        if reg < 0 or reg > 31:
            raise ValueError(f"Invalid register number: {reg}")
        await self.write(DBG_GPR_BASE + (reg * 4), value)

    async def read_instruction(self) -> int:
        """Read the current instruction"""
        return await self.read(DBG_INSTR)

    async def set_breakpoint(self, bp_num: int, addr: int, enable: bool = True) -> None:
        """Set a hardware breakpoint (0 or 1)"""
        if bp_num not in [0, 1]:
            raise ValueError(f"Invalid breakpoint number: {bp_num}")

        base_addr = DBG_BP0_ADDR if bp_num == 0 else DBG_BP1_ADDR
        ctrl_addr = DBG_BP0_CTRL if bp_num == 0 else DBG_BP1_CTRL

        await self.write(base_addr, addr)
        await self.write(ctrl_addr, 1 if enable else 0)
        self.log.info(f"Breakpoint {bp_num} set at 0x{addr:08x}, enabled={enable}")

    async def clear_breakpoint(self, bp_num: int) -> None:
        """Clear a hardware breakpoint"""
        if bp_num not in [0, 1]:
            raise ValueError(f"Invalid breakpoint number: {bp_num}")

        ctrl_addr = DBG_BP0_CTRL if bp_num == 0 else DBG_BP1_CTRL
        await self.write(ctrl_addr, 0)
        self.log.info(f"Breakpoint {bp_num} cleared")

    async def get_cpu_status(self) -> dict:
        """Get comprehensive CPU status"""
        status_reg = await self.read(DBG_STATUS)
        pc = await self.read_pc()
        instr = await self.read_instruction()

        return {
            'halted': bool(status_reg & (1 << STATUS_HALTED)),
            'running': bool(status_reg & (1 << STATUS_RUNNING)),
            'pc': pc,
            'instruction': instr,
            'status_reg': status_reg
        }

    async def dump_registers(self) -> dict:
        """Dump all general purpose registers"""
        regs = {}
        for i in range(32):
            regs[f"x{i}"] = await self.read_gpr(i)
        return regs


class APB3Monitor(BaseMonitor):
    """APB3 Monitor for transaction observation"""

    def __init__(self, dut, clk, name: str = "apb3_mon"):
        super().__init__(dut, clk, name)

    async def _monitor_loop(self) -> None:
        """Monitor APB3 transactions"""
        while True:
            await RisingEdge(self.clk)
            await ReadOnly()

            # Detect transaction completion (psel && penable && pready)
            if (int(self.dut.apb_psel.value) and
                int(self.dut.apb_penable.value) and
                int(self.dut.apb_pready.value)):

                txn = APB3Transaction()
                txn.paddr = int(self.dut.apb_paddr.value)
                txn.pwrite = bool(int(self.dut.apb_pwrite.value))

                if txn.pwrite:
                    txn.pwdata = int(self.dut.apb_pwdata.value)
                else:
                    txn.prdata = int(self.dut.apb_prdata.value)

                self.log.debug(str(txn))
                self._notify_callbacks(txn)


class APB3Agent(BaseAgent):
    """APB3 Agent combining driver and monitor"""

    def __init__(self, dut, clk, name: str = "apb3_agent"):
        super().__init__(dut, clk, name)
        self.driver = APB3MasterDriver(dut, clk, f"{name}_driver")
        self.monitor = APB3Monitor(dut, clk, f"{name}_monitor")

    # Convenience methods that delegate to driver
    async def write(self, addr: int, data: int) -> None:
        """Write to APB3"""
        await self.driver.write(addr, data)

    async def read(self, addr: int) -> int:
        """Read from APB3"""
        return await self.driver.read(addr)

    async def halt_cpu(self) -> None:
        """Halt CPU"""
        await self.driver.halt_cpu()

    async def resume_cpu(self) -> None:
        """Resume CPU"""
        await self.driver.resume_cpu()

    async def step_cpu(self) -> None:
        """Step CPU"""
        await self.driver.step_cpu()

    async def read_gpr(self, reg: int) -> int:
        """Read GPR"""
        return await self.driver.read_gpr(reg)

    async def write_gpr(self, reg: int, value: int) -> None:
        """Write GPR"""
        await self.driver.write_gpr(reg, value)

    async def set_breakpoint(self, bp_num: int, addr: int, enable: bool = True) -> None:
        """Set breakpoint"""
        await self.driver.set_breakpoint(bp_num, addr, enable)

    async def clear_breakpoint(self, bp_num: int) -> None:
        """Clear breakpoint"""
        await self.driver.clear_breakpoint(bp_num)
