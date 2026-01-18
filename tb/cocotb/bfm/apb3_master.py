"""
APB3 Master BFM (Bus Functional Model)

Provides an APB3 master interface for testbenches.
Used for CPU debug interface access per MEMORY_MAP.md.
"""

import cocotb
from cocotb.triggers import RisingEdge
from typing import Optional


class APB3Master:
    """
    APB3 Master Bus Functional Model.

    Implements an APB3 master for accessing debug registers and peripherals.

    Per MEMORY_MAP.md:
    - Address width: 12 bits (4 KB space)
    - Data width: 32 bits
    - Simple two-cycle protocol (SETUP, ACCESS)
    """

    def __init__(self, dut, name, clock, reset=None):
        """
        Initialize APB3 master.

        Args:
            dut: Device under test
            name: Prefix for signal names (e.g., 'apb_')
            clock: Clock signal
            reset: Reset signal (optional)
        """
        self.dut = dut
        self.clock = clock
        self.reset = reset

        # APB3 signals
        self.paddr = getattr(dut, f"{name}paddr")
        self.psel = getattr(dut, f"{name}psel")
        self.penable = getattr(dut, f"{name}penable")
        self.pwrite = getattr(dut, f"{name}pwrite")
        self.pwdata = getattr(dut, f"{name}pwdata")
        self.prdata = getattr(dut, f"{name}prdata")
        self.pready = getattr(dut, f"{name}pready")
        self.pslverr = getattr(dut, f"{name}pslverr")

        # Initialize signals
        self._init_signals()

    def _init_signals(self):
        """Initialize all master outputs to idle state."""
        self.paddr.value = 0
        self.psel.value = 0
        self.penable.value = 0
        self.pwrite.value = 0
        self.pwdata.value = 0

    async def write(self, addr: int, data: int) -> bool:
        """
        Perform APB3 write transaction.

        Args:
            addr: Address (12-bit for debug interface)
            data: 32-bit data to write

        Returns:
            True if successful, False if slave error
        """
        # SETUP phase
        self.paddr.value = addr
        self.psel.value = 1
        self.pwrite.value = 1
        self.pwdata.value = data
        self.penable.value = 0

        await RisingEdge(self.clock)

        # ACCESS phase
        self.penable.value = 1

        # Wait for pready
        while not self.pready.value:
            await RisingEdge(self.clock)

        # Check for slave error
        error = bool(self.pslverr.value)

        # Return to IDLE
        self.psel.value = 0
        self.penable.value = 0
        self.pwrite.value = 0

        await RisingEdge(self.clock)

        return not error

    async def read(self, addr: int) -> tuple[int, bool]:
        """
        Perform APB3 read transaction.

        Args:
            addr: Address (12-bit for debug interface)

        Returns:
            Tuple of (data, success)
            - data: 32-bit read data
            - success: True if successful, False if slave error
        """
        # SETUP phase
        self.paddr.value = addr
        self.psel.value = 1
        self.pwrite.value = 0
        self.penable.value = 0

        await RisingEdge(self.clock)

        # ACCESS phase
        self.penable.value = 1

        # Wait for pready
        while not self.pready.value:
            await RisingEdge(self.clock)

        # Sample data and error
        data = int(self.prdata.value)
        error = bool(self.pslverr.value)

        # Return to IDLE
        self.psel.value = 0
        self.penable.value = 0

        await RisingEdge(self.clock)

        return (data, not error)

    async def reset_master(self, duration_cycles: int = 10):
        """
        Assert reset and initialize master.

        Args:
            duration_cycles: Number of clock cycles to hold reset
        """
        if self.reset is None:
            return

        self.reset.value = 0  # Active-low reset
        self._init_signals()

        for _ in range(duration_cycles):
            await RisingEdge(self.clock)

        self.reset.value = 1  # Deassert reset
        await RisingEdge(self.clock)


class APB3DebugInterface:
    """
    High-level debug interface using APB3 Master.

    Provides convenient methods for accessing CPU debug registers
    per MEMORY_MAP.md register map.
    """

    # Debug register offsets (from MEMORY_MAP.md)
    DBG_CTRL = 0x000
    DBG_STATUS = 0x004
    DBG_PC = 0x008
    DBG_INSTR = 0x00C
    DBG_GPR_BASE = 0x010  # GPR0-GPR31 at 0x010-0x08C
    DBG_BP0_ADDR = 0x100
    DBG_BP0_CTRL = 0x104
    DBG_BP1_ADDR = 0x108
    DBG_BP1_CTRL = 0x10C

    # Control register bits
    CTRL_HALT_REQ = 0x1
    CTRL_RESUME_REQ = 0x2
    CTRL_STEP_REQ = 0x4
    CTRL_RESET_REQ = 0x8

    # Status register bits
    STATUS_HALTED = 0x1
    STATUS_RUNNING = 0x2

    def __init__(self, apb_master: APB3Master):
        """
        Initialize debug interface.

        Args:
            apb_master: APB3Master instance
        """
        self.apb = apb_master

    async def halt_cpu(self):
        """Request CPU halt."""
        await self.apb.write(self.DBG_CTRL, self.CTRL_HALT_REQ)

    async def resume_cpu(self):
        """Request CPU resume."""
        await self.apb.write(self.DBG_CTRL, self.CTRL_RESUME_REQ)

    async def step_cpu(self):
        """Request CPU single-step."""
        await self.apb.write(self.DBG_CTRL, self.CTRL_STEP_REQ)

    async def reset_cpu(self):
        """Request CPU reset."""
        await self.apb.write(self.DBG_CTRL, self.CTRL_RESET_REQ)

    async def is_halted(self) -> bool:
        """Check if CPU is halted."""
        data, _ = await self.apb.read(self.DBG_STATUS)
        return bool(data & self.STATUS_HALTED)

    async def read_pc(self) -> int:
        """Read program counter."""
        data, _ = await self.apb.read(self.DBG_PC)
        return data

    async def write_pc(self, value: int):
        """Write program counter (only when halted)."""
        await self.apb.write(self.DBG_PC, value)

    async def read_gpr(self, reg_num: int) -> int:
        """
        Read general purpose register.

        Args:
            reg_num: Register number (0-31)

        Returns:
            Register value
        """
        assert 0 <= reg_num <= 31, "Register number must be 0-31"
        addr = self.DBG_GPR_BASE + (reg_num * 4)
        data, _ = await self.apb.read(addr)
        return data

    async def write_gpr(self, reg_num: int, value: int):
        """
        Write general purpose register (only when halted).

        Args:
            reg_num: Register number (0-31)
            value: Value to write
        """
        assert 0 <= reg_num <= 31, "Register number must be 0-31"
        addr = self.DBG_GPR_BASE + (reg_num * 4)
        await self.apb.write(addr, value)

    async def set_breakpoint(self, bp_num: int, addr: int, enable: bool = True):
        """
        Set breakpoint.

        Args:
            bp_num: Breakpoint number (0 or 1)
            addr: Breakpoint address
            enable: Enable breakpoint
        """
        assert bp_num in [0, 1], "Breakpoint number must be 0 or 1"

        if bp_num == 0:
            await self.apb.write(self.DBG_BP0_ADDR, addr)
            await self.apb.write(self.DBG_BP0_CTRL, 1 if enable else 0)
        else:
            await self.apb.write(self.DBG_BP1_ADDR, addr)
            await self.apb.write(self.DBG_BP1_CTRL, 1 if enable else 0)
