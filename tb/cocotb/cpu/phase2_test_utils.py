"""
Shared test infrastructure for Phase 2 cocotb tests.

Provides:
  - APBDebug     — APB3 debug helper (halt, GPR/CSR reads)
  - _init_inputs — clears all DUT input signals before reset
  - _setup_test  — standard test setup (clock + reset + AXI memory + APBDebug)

Imported by test_pipeline_hazards.py and test_interrupts.py.
test_debug_if.py uses APBDebugDriver from the pyuvm infra and is unchanged.
"""

import sys
from pathlib import Path

# Add project root so sub-imports (sim.riscv_encoder, tb.cocotb.*) resolve.
# Consolidated here so individual test files do not need their own sys.path line.
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ReadOnly, RisingEdge

from tb.cocotb.common.clock_reset import reset_dut
from tb.cocotb.cpu.axi_models import ConfigurableAXIMemory

# ============================================================================
# APB register offset constants (Phase 2)
# ============================================================================

DBG_CTRL = 0x000
DBG_STATUS = 0x004
DBG_PC = 0x008
# GPR window: 0x010 + reg_num * 4  (x0–x31 → 0x010–0x08C)
# CSR debug window (Phase 2 additions)
DBG_MSTATUS = 0x200
DBG_MIE_REG = 0x204
DBG_MTVEC = 0x208
DBG_MEPC = 0x20C
DBG_MCAUSE = 0x210
DBG_MIP = 0x214


# ============================================================================
# APBDebug helper
# ============================================================================


class APBDebug:
    """APB3 debug helper — halt, read GPRs and CSR debug registers.

    All constants for the APB register map are exposed as class attributes
    so callers can do ``APBDebug.DBG_MCAUSE`` without a live instance.
    """

    # Re-export module-level constants as class attributes for convenience
    DBG_CTRL = DBG_CTRL
    DBG_STATUS = DBG_STATUS
    DBG_PC = DBG_PC
    DBG_MSTATUS = DBG_MSTATUS
    DBG_MIE_REG = DBG_MIE_REG
    DBG_MTVEC = DBG_MTVEC
    DBG_MEPC = DBG_MEPC
    DBG_MCAUSE = DBG_MCAUSE
    DBG_MIP = DBG_MIP

    def __init__(self, dut):
        self.dut = dut

    # ------------------------------------------------------------------ #
    # Low-level APB transactions                                          #
    # ------------------------------------------------------------------ #

    async def _write(self, addr, data):
        """APB write: setup → enable → idle (3 clock cycles)."""
        await RisingEdge(self.dut.clk_i)
        self.dut.apb_psel_i.value = 1
        self.dut.apb_penable_i.value = 0
        self.dut.apb_pwrite_i.value = 1
        self.dut.apb_paddr_i.value = addr
        self.dut.apb_pwdata_i.value = data
        await RisingEdge(self.dut.clk_i)
        self.dut.apb_penable_i.value = 1
        await RisingEdge(self.dut.clk_i)
        self.dut.apb_psel_i.value = 0
        self.dut.apb_penable_i.value = 0
        self.dut.apb_pwrite_i.value = 0

    async def _read(self, addr):
        """APB read: setup → enable → wait for pready → sample → idle.

        GH #96 bead cyb: rv32i_cpu_top.apb_prdata_o is now a registered
        output and the slave inserts one APB3 wait state on reads (writes
        are unaffected — still single-cycle), so this polls apb_pready_o
        instead of assuming prdata is valid the cycle penable asserts.
        """
        await RisingEdge(self.dut.clk_i)
        self.dut.apb_psel_i.value = 1
        self.dut.apb_penable_i.value = 0
        self.dut.apb_pwrite_i.value = 0
        self.dut.apb_paddr_i.value = addr
        await RisingEdge(self.dut.clk_i)
        self.dut.apb_penable_i.value = 1
        await ReadOnly()
        while not self.dut.apb_pready_o.value:
            await RisingEdge(self.dut.clk_i)
            await ReadOnly()
        data = int(self.dut.apb_prdata_o.value)
        await RisingEdge(self.dut.clk_i)
        self.dut.apb_psel_i.value = 0
        self.dut.apb_penable_i.value = 0
        return data

    # ------------------------------------------------------------------ #
    # Halt / resume                                                       #
    # ------------------------------------------------------------------ #

    async def halt(self, timeout_cycles=300):
        """Assert halt and poll DBG_STATUS until halted.

        The pipeline drains (up to ~5 cycles) before halted is signalled.
        Each poll iteration costs 3 base APB clock cycles plus one extra
        wait-state cycle on the read (GH #96 bead cyb); `polls` below is
        sized off the pre-wait-state 3-cycle figure, which only shortens
        the effective timeout margin slightly — timeout_cycles is generous
        enough that this does not affect pass/fail.

        Args:
            timeout_cycles: Total clock cycles to poll before raising
                            RuntimeError.  Logs the last DBG_STATUS value
                            if the timeout is reached.
        """
        await self._write(DBG_CTRL, 0x1)
        polls = timeout_cycles // 3
        last_status = 0
        for _ in range(polls):
            last_status = await self._read(DBG_STATUS)
            if last_status & 0x1:
                return
            await RisingEdge(self.dut.clk_i)
        raise RuntimeError(
            f"CPU did not halt within {timeout_cycles} cycles (last DBG_STATUS=0x{last_status:08x})"
        )

    async def resume(self):
        """Deassert halt by writing DBG_CTRL.resume bit."""
        await self._write(DBG_CTRL, 0x2)

    async def wait_halted(self, timeout_cycles=600):
        """Poll DBG_STATUS until halted (e.g. after EBREAK).

        Args:
            timeout_cycles: Total clock cycles to poll before raising.
        """
        polls = timeout_cycles // 3
        last_status = 0
        for _ in range(polls):
            last_status = await self._read(DBG_STATUS)
            if last_status & 0x1:
                return
            await RisingEdge(self.dut.clk_i)
        raise RuntimeError(
            f"CPU did not halt within {timeout_cycles} cycles (last DBG_STATUS=0x{last_status:08x})"
        )

    # ------------------------------------------------------------------ #
    # Register reads                                                      #
    # ------------------------------------------------------------------ #

    async def read_gpr(self, reg_num):
        """Read GPR via APB debug window (0x010 + reg_num * 4)."""
        return await self._read(0x010 + reg_num * 4)

    async def read_csr(self, apb_offset):
        """Read a Phase 2 CSR debug register by its APB offset (0x200–0x214)."""
        return await self._read(apb_offset)

    async def read_mstatus(self):
        return await self._read(DBG_MSTATUS)

    async def read_mie(self):
        return await self._read(DBG_MIE_REG)

    async def read_mtvec(self):
        return await self._read(DBG_MTVEC)

    async def read_mepc(self):
        return await self._read(DBG_MEPC)

    async def read_mcause(self):
        return await self._read(DBG_MCAUSE)


# ============================================================================
# Signal initialisation
# ============================================================================


def _init_inputs(dut):
    """Set all DUT input signals to their safe/inactive defaults.

    Called before reset on every test to clear stale signal values left
    by cancelled background handlers from the previous test.
    See project memory: 'Stale AXI Signals Between cocotb Tests (2026-02-16)'.
    """
    # AXI read channel
    dut.axi_arready_i.value = 0
    dut.axi_rvalid_i.value = 0
    dut.axi_rdata_i.value = 0
    dut.axi_rresp_i.value = 0
    if hasattr(dut, "axi_rlast_i"):
        dut.axi_rlast_i.value = 0
    # AXI write channel
    dut.axi_awready_i.value = 0
    dut.axi_wready_i.value = 0
    dut.axi_bvalid_i.value = 0
    dut.axi_bresp_i.value = 0
    # APB debug interface
    dut.apb_psel_i.value = 0
    dut.apb_penable_i.value = 0
    dut.apb_pwrite_i.value = 0
    dut.apb_paddr_i.value = 0
    dut.apb_pwdata_i.value = 0
    # Interrupt inputs
    dut.ext_irq_i.value = 0
    dut.timer_irq_i.value = 0


# ============================================================================
# Standard test setup
# ============================================================================


async def _setup_test(dut):
    """Common Phase 2 test setup.

    Steps:
      1. Start 10 ns clock
      2. _init_inputs() — clear stale AXI/APB/IRQ values from previous test
      3. reset_dut() — assert rst_n_i low for a few cycles then deassert
      4. Create ConfigurableAXIMemory — starts read/write handler tasks in __init__
      5. Yield one rising edge so handler tasks begin executing

    ConfigurableAXIMemory starts its handler tasks in __init__ (axi_models.py:72-73).
    cocotb 2.0 cancels them automatically at test end.  _init_inputs() clears
    stale signal values between tests (project memory: Stale AXI Signals 2026-02-16).
    mem.stop() is available if a test needs to cancel handlers mid-test (axi_models.py:75).

    Returns:
        (mem, dbg) tuple — ConfigurableAXIMemory instance and APBDebug instance.
    """
    cocotb.start_soon(Clock(dut.clk_i, 10, units="ns").start())
    _init_inputs(dut)

    # Signal clears take effect on the first clock edge inside reset
    await reset_dut(dut)

    # Create memory handlers AFTER reset so they start with a clean DUT state
    mem = ConfigurableAXIMemory(dut, ref_model=None, protocol_check=False)
    dbg = APBDebug(dut)

    # Yield one cycle so handler tasks begin executing
    await RisingEdge(dut.clk_i)

    return mem, dbg
