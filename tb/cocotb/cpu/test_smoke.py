"""
Smoke tests for RV32I CPU — Phase 1

Basic functionality tests to verify CPU is operational.
Coverage metrics (instruction + FSM state) are collected across all tests
in this module and reported in the final test_coverage_report test.
"""

import sys
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, ReadOnly, RisingEdge

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from tb.cocotb.common.clock_reset import reset_dut, setup_clock
from tb.cocotb.common.coverage import CoverageReport
from tb.cocotb.common.scoreboard import CPUScoreboard
from tb.models.rv32i_model import RV32IModel

# ---------------------------------------------------------------------------
# Module-level coverage objects — accumulated across all tests in this module
# (cocotb runs @cocotb.test() functions sequentially in the same process)
# ---------------------------------------------------------------------------
_cov_report = CoverageReport()


# ---------------------------------------------------------------------------
# State monitor coroutine
# ---------------------------------------------------------------------------


async def monitor_state(dut, state_cov):
    """Sample debug_state_o every clock cycle and record in StateCoverage."""
    while True:
        await RisingEdge(dut.clk_i)
        state_cov.record(int(dut.debug_state_o.value))


# ---------------------------------------------------------------------------
# AXI memory model
# ---------------------------------------------------------------------------


class SimpleAXIMemory:
    """Minimal AXI4-Lite memory for smoke tests."""

    def __init__(self, dut, ref_model=None):
        self.dut = dut
        self.mem = {}
        self.ref_model = ref_model
        cocotb.start_soon(self._read_handler())
        cocotb.start_soon(self._write_handler())

    def write_word(self, addr, data):
        self.mem[addr & 0xFFFFFFFC] = data & 0xFFFFFFFF
        if self.ref_model is not None:
            self.ref_model.memory.write(addr & 0xFFFFFFFC, data & 0xFFFFFFFF, 4)

    def read_word(self, addr):
        return self.mem.get(addr & 0xFFFFFFFC, 0)

    async def _read_handler(self):
        while True:
            await RisingEdge(self.dut.clk_i)
            if self.dut.axi_arvalid_o.value == 1:
                self.dut.axi_arready_i.value = 1
                addr = int(self.dut.axi_araddr_o.value)
                data = self.read_word(addr)

                await RisingEdge(self.dut.clk_i)
                self.dut.axi_arready_i.value = 0
                self.dut.axi_rvalid_i.value = 1
                self.dut.axi_rdata_i.value = data
                self.dut.axi_rresp_i.value = 0

                while self.dut.axi_rready_o.value == 0:
                    await RisingEdge(self.dut.clk_i)

                await RisingEdge(self.dut.clk_i)
                self.dut.axi_rvalid_i.value = 0
            else:
                self.dut.axi_arready_i.value = 0

    async def _write_handler(self):
        while True:
            await RisingEdge(self.dut.clk_i)
            if (
                self.dut.axi_awvalid_o.value == 1
                and self.dut.axi_wvalid_o.value == 1
                and self.dut.axi_awready_i.value == 0
            ):
                self.dut.axi_awready_i.value = 1
                self.dut.axi_wready_i.value = 1
                addr = int(self.dut.axi_awaddr_o.value)
                data = int(self.dut.axi_wdata_o.value)

                await RisingEdge(self.dut.clk_i)
                self.dut.axi_awready_i.value = 0
                self.dut.axi_wready_i.value = 0
                self.write_word(addr, data)

                self.dut.axi_bvalid_i.value = 1
                self.dut.axi_bresp_i.value = 0

                while self.dut.axi_bready_o.value == 0:
                    await RisingEdge(self.dut.clk_i)

                await RisingEdge(self.dut.clk_i)
                self.dut.axi_bvalid_i.value = 0


# ---------------------------------------------------------------------------
# APB3 debug interface helper
# ---------------------------------------------------------------------------


class APBDebugInterface:
    DBG_CTRL = 0x000
    DBG_STATUS = 0x004
    DBG_PC = 0x008
    DBG_GPR_BASE = 0x010

    def __init__(self, dut):
        self.dut = dut

    async def _apb_write(self, addr, data):
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

    async def _apb_read(self, addr):
        await RisingEdge(self.dut.clk_i)
        self.dut.apb_psel_i.value = 1
        self.dut.apb_penable_i.value = 0
        self.dut.apb_pwrite_i.value = 0
        self.dut.apb_paddr_i.value = addr

        await RisingEdge(self.dut.clk_i)
        self.dut.apb_penable_i.value = 1

        await ReadOnly()
        data = int(self.dut.apb_prdata_o.value)

        await RisingEdge(self.dut.clk_i)
        self.dut.apb_psel_i.value = 0
        self.dut.apb_penable_i.value = 0
        return data

    async def halt_cpu(self):
        await self._apb_write(self.DBG_CTRL, 0x1)
        for _ in range(10):
            status = await self._apb_read(self.DBG_STATUS)
            if status & 0x1:
                return
            await RisingEdge(self.dut.clk_i)
        raise RuntimeError("CPU did not halt")

    async def read_gpr(self, reg_num):
        return await self._apb_read(self.DBG_GPR_BASE + reg_num * 4)

    async def read_pc(self):
        return await self._apb_read(self.DBG_PC)


# ---------------------------------------------------------------------------
# Commit monitor
# ---------------------------------------------------------------------------


async def monitor_commits(dut, scoreboard=None, count=None):
    """Monitor instruction commits and optionally validate with scoreboard."""
    if count is None:
        count = [0]
    while True:
        await RisingEdge(dut.clk_i)
        if dut.commit_valid_o.value == 1:
            count[0] += 1
            pc = int(dut.commit_pc_o.value)
            insn = int(dut.commit_insn_o.value)
            if count[0] <= 10:
                dut._log.info(f"Commit #{count[0]}: PC=0x{pc:08x}, insn=0x{insn:08x}")
            if scoreboard is not None:
                rtl_commit = {
                    "pc": pc,
                    "insn": insn,
                    "rd": None,
                    "rd_value": None,
                    "mem_addr": None,
                    "mem_data": None,
                    "mem_write": None,
                }
                scoreboard.check_commit(rtl_commit)


# ---------------------------------------------------------------------------
# Helper: initialise DUT AXI/APB inputs to safe idle values
# ---------------------------------------------------------------------------


def _init_inputs(dut):
    dut.axi_arready_i.value = 0
    dut.axi_rvalid_i.value = 0
    dut.axi_rdata_i.value = 0
    dut.axi_rresp_i.value = 0
    dut.axi_awready_i.value = 0
    dut.axi_wready_i.value = 0
    dut.axi_bvalid_i.value = 0
    dut.axi_bresp_i.value = 0
    dut.apb_psel_i.value = 0
    dut.apb_penable_i.value = 0
    dut.apb_pwrite_i.value = 0
    dut.apb_paddr_i.value = 0
    dut.apb_pwdata_i.value = 0


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@cocotb.test()
async def test_reset(dut):
    """Test that CPU comes out of reset correctly."""
    dut._log.info("=== Test: Reset ===")
    cocotb.start_soon(Clock(dut.clk_i, 10, units="ns").start())
    _init_inputs(dut)
    cocotb.start_soon(monitor_state(dut, _cov_report.state_cov))
    await reset_dut(dut)
    await ClockCycles(dut.clk_i, 2)
    dut._log.info("Reset test passed")


@cocotb.test()
async def test_fetch_nop(dut):
    """Test that CPU can fetch and execute NOP instructions."""
    dut._log.info("=== Test: Fetch NOP ===")
    cocotb.start_soon(Clock(dut.clk_i, 10, units="ns").start())
    _init_inputs(dut)

    ref_model = RV32IModel()
    scoreboard = CPUScoreboard(ref_model, log=dut._log, coverage=_cov_report)
    mem = SimpleAXIMemory(dut, ref_model=ref_model)
    count = [0]
    cocotb.start_soon(monitor_commits(dut, scoreboard=scoreboard, count=count))
    cocotb.start_soon(monitor_state(dut, _cov_report.state_cov))

    # NOP = ADDI x0, x0, 0
    mem.write_word(0x00000000, 0x00000013)
    mem.write_word(0x00000004, 0x00000013)
    mem.write_word(0x00000008, 0x00000013)

    await reset_dut(dut)
    await ClockCycles(dut.clk_i, 100)

    dut._log.info(f"Total commits: {count[0]}")
    passed = scoreboard.report()
    assert passed, "Scoreboard validation failed"
    dut._log.info("Fetch NOP test passed")


@cocotb.test()
async def test_simple_addi(dut):
    """Test simple ADDI instructions with register value verification."""
    dut._log.info("=== Test: Simple ADDI ===")
    cocotb.start_soon(Clock(dut.clk_i, 10, units="ns").start())
    _init_inputs(dut)

    ref_model = RV32IModel()
    scoreboard = CPUScoreboard(ref_model, log=dut._log, coverage=_cov_report)
    mem = SimpleAXIMemory(dut, ref_model=ref_model)
    dbg = APBDebugInterface(dut)
    count = [0]
    cocotb.start_soon(monitor_commits(dut, scoreboard=scoreboard, count=count))
    cocotb.start_soon(monitor_state(dut, _cov_report.state_cov))

    # addi x1, x0, 42  →  x1 = 42
    # addi x2, x1, 8   →  x2 = 50
    # nop loop
    mem.write_word(0x00000000, 0x02A00093)
    mem.write_word(0x00000004, 0x00808113)
    mem.write_word(0x00000008, 0x00000013)

    await reset_dut(dut)
    await ClockCycles(dut.clk_i, 200)

    await dbg.halt_cpu()

    x1_val = await dbg.read_gpr(1)
    assert x1_val == 42, f"Expected x1=42, got {x1_val}"
    dut._log.info(f"x1 = {x1_val} (expected 42)")

    x2_val = await dbg.read_gpr(2)
    assert x2_val == 50, f"Expected x2=50, got {x2_val}"
    dut._log.info(f"x2 = {x2_val} (expected 50)")

    pc_val = await dbg.read_pc()
    assert pc_val >= 0x08, f"Expected PC >= 0x08, got 0x{pc_val:08x}"
    dut._log.info(f"PC = 0x{pc_val:08x}")

    passed = scoreboard.report()
    assert passed, "Scoreboard validation failed"
    dut._log.info("Simple ADDI test passed")


@cocotb.test()
async def test_branch_not_taken(dut):
    """Test branch not taken path."""
    dut._log.info("=== Test: Branch Not Taken ===")
    cocotb.start_soon(Clock(dut.clk_i, 10, units="ns").start())
    _init_inputs(dut)

    ref_model = RV32IModel()
    scoreboard = CPUScoreboard(ref_model, log=dut._log, coverage=_cov_report)
    mem = SimpleAXIMemory(dut, ref_model=ref_model)
    dbg = APBDebugInterface(dut)
    count = [0]
    cocotb.start_soon(monitor_commits(dut, scoreboard=scoreboard, count=count))
    cocotb.start_soon(monitor_state(dut, _cov_report.state_cov))

    mem.write_word(0x00000000, 0x00100093)  # addi x1, x0, 1
    mem.write_word(0x00000004, 0x00200113)  # addi x2, x0, 2
    mem.write_word(0x00000008, 0x00208663)  # beq x1, x2, 12  (not taken)
    mem.write_word(0x0000000C, 0x00A00193)  # addi x3, x0, 10
    mem.write_word(0x00000010, 0x00000013)  # nop

    await reset_dut(dut)
    await ClockCycles(dut.clk_i, 300)

    await dbg.halt_cpu()

    x3_val = await dbg.read_gpr(3)
    assert x3_val == 10, f"Expected x3=10 (branch not taken), got {x3_val}"
    dut._log.info(f"x3 = {x3_val} (expected 10)")

    passed = scoreboard.report()
    assert passed, "Scoreboard validation failed"
    dut._log.info("Branch not taken test passed")


@cocotb.test()
async def test_branch_taken(dut):
    """Test branch taken path."""
    dut._log.info("=== Test: Branch Taken ===")
    cocotb.start_soon(Clock(dut.clk_i, 10, units="ns").start())
    _init_inputs(dut)

    ref_model = RV32IModel()
    scoreboard = CPUScoreboard(ref_model, log=dut._log, coverage=_cov_report)
    mem = SimpleAXIMemory(dut, ref_model=ref_model)
    dbg = APBDebugInterface(dut)
    count = [0]
    cocotb.start_soon(monitor_commits(dut, scoreboard=scoreboard, count=count))
    cocotb.start_soon(monitor_state(dut, _cov_report.state_cov))

    mem.write_word(0x00000000, 0x00100093)  # addi x1, x0, 1
    mem.write_word(0x00000004, 0x00100113)  # addi x2, x0, 1
    mem.write_word(0x00000008, 0x00208463)  # beq x1, x2, 8   (taken → 0x010)
    mem.write_word(0x0000000C, 0x06300193)  # addi x3, x0, 99 (skipped)
    mem.write_word(0x00000010, 0x01400213)  # addi x4, x0, 20
    mem.write_word(0x00000014, 0x00000013)  # nop

    await reset_dut(dut)
    await ClockCycles(dut.clk_i, 300)

    await dbg.halt_cpu()

    x3_val = await dbg.read_gpr(3)
    assert x3_val == 0, f"Expected x3=0 (branch taken, instruction skipped), got {x3_val}"
    dut._log.info(f"x3 = {x3_val} (expected 0)")

    x4_val = await dbg.read_gpr(4)
    assert x4_val == 20, f"Expected x4=20 (branch target), got {x4_val}"
    dut._log.info(f"x4 = {x4_val} (expected 20)")

    passed = scoreboard.report()
    assert passed, "Scoreboard validation failed"
    dut._log.info("Branch taken test passed")


@cocotb.test()
async def test_jal(dut):
    """Test JAL (Jump and Link) instruction."""
    dut._log.info("=== Test: JAL ===")
    cocotb.start_soon(Clock(dut.clk_i, 10, units="ns").start())
    _init_inputs(dut)

    ref_model = RV32IModel()
    scoreboard = CPUScoreboard(ref_model, log=dut._log, coverage=_cov_report)
    mem = SimpleAXIMemory(dut, ref_model=ref_model)
    dbg = APBDebugInterface(dut)
    count = [0]
    cocotb.start_soon(monitor_commits(dut, scoreboard=scoreboard, count=count))
    cocotb.start_soon(monitor_state(dut, _cov_report.state_cov))

    mem.write_word(0x00000000, 0x00C000EF)  # jal x1, 12
    mem.write_word(0x00000004, 0x06300113)  # addi x2, x0, 99 (skipped)
    mem.write_word(0x00000008, 0x05800193)  # addi x3, x0, 88 (skipped)
    mem.write_word(0x0000000C, 0x01400213)  # addi x4, x0, 20
    mem.write_word(0x00000010, 0x00000013)  # nop

    await reset_dut(dut)
    await ClockCycles(dut.clk_i, 300)

    await dbg.halt_cpu()

    x1_val = await dbg.read_gpr(1)
    assert x1_val == 0x4, f"Expected x1=0x4 (link), got 0x{x1_val:x}"
    dut._log.info(f"x1 = 0x{x1_val:x} (expected 0x4)")

    x4_val = await dbg.read_gpr(4)
    assert x4_val == 20, f"Expected x4=20 (jump target), got {x4_val}"
    dut._log.info(f"x4 = {x4_val} (expected 20)")

    passed = scoreboard.report()
    assert passed, "Scoreboard validation failed"
    dut._log.info("JAL test passed")


@cocotb.test()
async def test_coverage_report(dut):
    """Generate and log coverage report for all smoke tests."""
    dut._log.info("=== Coverage Report ===")

    report = _cov_report.generate(output_path="reports/coverage_summary.txt")

    for line in report.splitlines():
        dut._log.info(line)

    dut._log.info("Coverage report written to reports/coverage_summary.txt")
