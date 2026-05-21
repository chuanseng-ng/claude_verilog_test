"""
Smoke tests for RV32I CPU — Phase 3 (pipelined)

Basic functionality tests to verify CPU is operational.
Coverage metrics (instruction + pipeline events) are collected across all tests
in this module and reported in the final test_coverage_report test.
"""

import sys
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, ReadOnly, RisingEdge

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from sim.riscv_encoder import (
    ADD,
    ADDI,
    AND,
    ANDI,
    AUIPC,
    BEQ,
    BGE,
    BGEU,
    BLT,
    BLTU,
    BNE,
    EBREAK,
    JAL,
    JALR,
    LB,
    LBU,
    LH,
    LHU,
    LUI,
    LW,
    OR,
    ORI,
    SB,
    SH,
    SLL,
    SLLI,
    SLT,
    SLTI,
    SLTIU,
    SLTU,
    SRA,
    SRAI,
    SRL,
    SRLI,
    SUB,
    SW,
    XOR,
    XORI,
)
from tb.cocotb.common.clock_reset import reset_dut
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
    """Sample Phase 3 pipeline events every clock cycle and record in StateCoverage.

    Encoding (matches coverage.STATE_NAMES):
      0 = STALL          — commit_valid low, CPU not in reset
      1 = COMMIT         — instruction retired at WB
      2 = BRANCH_REDIRECT — branch/jump redirect (pipeline flush)
      3 = TRAP           — exception or interrupt taken
      4 = EBREAK         — EBREAK instruction

    Multiple events may be asserted in one cycle; all are recorded.
    """
    while True:
        await RisingEdge(dut.clk_i)
        try:
            commit   = int(dut.commit_valid_o.value)
            redirect = int(dut.debug_take_branch_jump_o.value)
            trap     = int(dut.trap_taken_o.value)
            ebreak   = int(dut.debug_ebreak_o.value)
            rst_n    = int(dut.rst_n_i.value)
        except ValueError:
            # Signal has X/Z bits (unresolved); skip this cycle
            continue

        if not rst_n:
            continue  # Skip reset cycles

        if ebreak:
            state_cov.record(4)  # EBREAK
        if trap:
            state_cov.record(3)  # TRAP
        if redirect:
            state_cov.record(2)  # BRANCH_REDIRECT
        if commit:
            state_cov.record(1)  # COMMIT
        if not (commit or ebreak or trap):
            state_cov.record(0)  # STALL


# ---------------------------------------------------------------------------
# AXI memory model
# ---------------------------------------------------------------------------


class SimpleAXIMemory:
    """Minimal AXI4-Lite memory for smoke tests."""

    def __init__(self, dut, ref_model=None):
        self.dut = dut
        self.mem = {}
        self.ref_model = ref_model
        self._read_task = cocotb.start_soon(self._read_handler())
        self._write_task = cocotb.start_soon(self._write_handler())

    def stop(self):
        """Cancel background handler tasks to prevent stale handlers across tests."""
        self._read_task.cancel()
        self._write_task.cancel()

    def write_word(self, addr, data):
        self.mem[addr & 0xFFFFFFFC] = data & 0xFFFFFFFF
        if self.ref_model is not None:
            self.ref_model.memory.write(addr & 0xFFFFFFFC, data & 0xFFFFFFFF, 4)

    def read_word(self, addr):
        return self.mem.get(addr & 0xFFFFFFFC, 0)

    async def _read_handler(self):
        while True:
            await RisingEdge(self.dut.clk_i)
            # During reset: deassert all outputs and discard any in-flight state.
            # The async reset holds arbiter in IDLE (FF can't transition to IF_READ),
            # so any arready we asserted was never registered — clean up and restart.
            if int(self.dut.rst_n_i.value) == 0:
                self.dut.axi_arready_i.value = 0
                self.dut.axi_rvalid_i.value = 0
                continue
            if self.dut.axi_arvalid_o.value == 1:
                # Wait 1 cycle for pipeline/arbiter to settle before reading
                # address.  Prevents race where arbiter switches IF→MEM between
                # the cycle we sample araddr and the cycle arready takes effect.
                await RisingEdge(self.dut.clk_i)
                if int(self.dut.rst_n_i.value) == 0:
                    self.dut.axi_arready_i.value = 0
                    self.dut.axi_rvalid_i.value = 0
                    continue
                if self.dut.axi_arvalid_o.value != 1:
                    self.dut.axi_arready_i.value = 0
                    continue

                addr = int(self.dut.axi_araddr_o.value)
                data = self.read_word(addr)
                self.dut.axi_arready_i.value = 1

                await RisingEdge(self.dut.clk_i)
                self.dut.axi_arready_i.value = 0
                self.dut.axi_rvalid_i.value = 1
                self.dut.axi_rdata_i.value = data
                self.dut.axi_rresp_i.value = 0

                # Wait for rready handshake; abort cleanly if reset fires mid-transaction.
                while self.dut.axi_rready_o.value == 0:
                    if int(self.dut.rst_n_i.value) == 0:
                        self.dut.axi_rvalid_i.value = 0
                        break
                    await RisingEdge(self.dut.clk_i)
                else:
                    # Normal completion: hold rvalid for one cycle after handshake.
                    await RisingEdge(self.dut.clk_i)
                    self.dut.axi_rvalid_i.value = 0
            else:
                self.dut.axi_arready_i.value = 0

    async def _write_handler(self):
        while True:
            await RisingEdge(self.dut.clk_i)
            # During reset: deassert all outputs.
            if int(self.dut.rst_n_i.value) == 0:
                self.dut.axi_awready_i.value = 0
                self.dut.axi_wready_i.value = 0
                self.dut.axi_bvalid_i.value = 0
                continue
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
                    if int(self.dut.rst_n_i.value) == 0:
                        self.dut.axi_bvalid_i.value = 0
                        break
                    await RisingEdge(self.dut.clk_i)
                else:
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

    async def halt_cpu(self, timeout=100):
        """Halt CPU and wait for pipeline to drain (Phase 2 needs ~15-20 cycles)."""
        await self._apb_write(self.DBG_CTRL, 0x1)
        for i in range(timeout):
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
                # Phase 2: use WB-stage register file write port signals
                reg_wr = int(dut.u_core.rf_wr_en.value)
                rtl_commit = {
                    "pc": pc,
                    "insn": insn,
                    "rd": int(dut.u_core.rf_wr_addr.value) & 0x1F if reg_wr else None,
                    "rd_value": int(dut.u_core.rf_wr_data.value) & 0xFFFFFFFF if reg_wr else None,
                    # Memory address not directly observable at WB in Phase 2
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
    # Phase 2: interrupt inputs (keep deasserted during Phase 1 regression)
    dut.ext_irq_i.value = 0
    dut.timer_irq_i.value = 0


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
    try:
        count = [0]
        cocotb.start_soon(monitor_commits(dut, scoreboard=scoreboard, count=count))
        cocotb.start_soon(monitor_state(dut, _cov_report.state_cov))

        # NOP = ADDI x0, x0, 0; then self-loop so the CPU doesn't run into unmapped
        # memory (which returns 0x0 = illegal insn → trap → mtvec=0x0 → loop).
        mem.write_word(0x00000000, 0x00000013)
        mem.write_word(0x00000004, 0x00000013)
        mem.write_word(0x00000008, 0x00000013)
        mem.write_word(0x0000000C, JAL(0, 0))  # infinite self-loop

        await reset_dut(dut)
        await ClockCycles(dut.clk_i, 100)

        dut._log.info(f"Total commits: {count[0]}")
        passed = scoreboard.report()
        assert passed, "Scoreboard validation failed"
        dut._log.info("Fetch NOP test passed")
    finally:
        mem.stop()


@cocotb.test()
async def test_simple_addi(dut):
    """Test simple ADDI instructions with register value verification."""
    dut._log.info("=== Test: Simple ADDI ===")
    cocotb.start_soon(Clock(dut.clk_i, 10, units="ns").start())
    _init_inputs(dut)

    ref_model = RV32IModel()
    scoreboard = CPUScoreboard(ref_model, log=dut._log, coverage=_cov_report)
    mem = SimpleAXIMemory(dut, ref_model=ref_model)
    try:
        dbg = APBDebugInterface(dut)
        count = [0]
        cocotb.start_soon(monitor_state(dut, _cov_report.state_cov))

        # addi x1, x0, 42  →  x1 = 42
        # addi x2, x1, 8   →  x2 = 50
        # nop, then self-loop
        mem.write_word(0x00000000, 0x02A00093)
        mem.write_word(0x00000004, 0x00808113)
        mem.write_word(0x00000008, 0x00000013)
        mem.write_word(0x0000000C, JAL(0, 0))  # infinite self-loop

        await reset_dut(dut)
        # Start commit monitor after reset so stale commits from the prior test
        # (CPU was spinning in a JAL self-loop) are not captured by the scoreboard.
        # With the deeper EX1c pipeline stage, the first commit after reset takes
        # one more cycle, which shifts the timing window and exposes a pre-existing
        # race between monitor startup and in-flight commits.
        cocotb.start_soon(monitor_commits(dut, scoreboard=scoreboard, count=count))
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
    finally:
        mem.stop()


@cocotb.test()
async def test_branch_not_taken(dut):
    """Test branch not taken path."""
    dut._log.info("=== Test: Branch Not Taken ===")
    cocotb.start_soon(Clock(dut.clk_i, 10, units="ns").start())
    _init_inputs(dut)

    ref_model = RV32IModel()
    scoreboard = CPUScoreboard(ref_model, log=dut._log, coverage=_cov_report)
    mem = SimpleAXIMemory(dut, ref_model=ref_model)
    try:
        dbg = APBDebugInterface(dut)
        count = [0]
        cocotb.start_soon(monitor_commits(dut, scoreboard=scoreboard, count=count))
        cocotb.start_soon(monitor_state(dut, _cov_report.state_cov))

        mem.write_word(0x00000000, 0x00100093)  # addi x1, x0, 1
        mem.write_word(0x00000004, 0x00200113)  # addi x2, x0, 2
        mem.write_word(0x00000008, 0x00208663)  # beq x1, x2, 12  (not taken → fall to 0xC)
        mem.write_word(0x0000000C, 0x00A00193)  # addi x3, x0, 10
        mem.write_word(0x00000010, 0x00000013)  # nop
        mem.write_word(0x00000014, JAL(0, 0))  # infinite self-loop

        await reset_dut(dut)
        await ClockCycles(dut.clk_i, 300)

        await dbg.halt_cpu()

        x3_val = await dbg.read_gpr(3)
        assert x3_val == 10, f"Expected x3=10 (branch not taken), got {x3_val}"
        dut._log.info(f"x3 = {x3_val} (expected 10)")

        passed = scoreboard.report()
        assert passed, "Scoreboard validation failed"
        dut._log.info("Branch not taken test passed")
    finally:
        mem.stop()


@cocotb.test()
async def test_branch_taken(dut):
    """Test branch taken path."""
    dut._log.info("=== Test: Branch Taken ===")
    cocotb.start_soon(Clock(dut.clk_i, 10, units="ns").start())
    _init_inputs(dut)

    ref_model = RV32IModel()
    scoreboard = CPUScoreboard(ref_model, log=dut._log, coverage=_cov_report)
    mem = SimpleAXIMemory(dut, ref_model=ref_model)
    try:
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
        mem.write_word(0x00000018, JAL(0, 0))  # infinite self-loop

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
    finally:
        mem.stop()


@cocotb.test()
async def test_jal(dut):
    """Test JAL (Jump and Link) instruction."""
    dut._log.info("=== Test: JAL ===")
    cocotb.start_soon(Clock(dut.clk_i, 10, units="ns").start())
    _init_inputs(dut)

    ref_model = RV32IModel()
    scoreboard = CPUScoreboard(ref_model, log=dut._log, coverage=_cov_report)
    mem = SimpleAXIMemory(dut, ref_model=ref_model)
    try:
        dbg = APBDebugInterface(dut)
        count = [0]
        cocotb.start_soon(monitor_commits(dut, scoreboard=scoreboard, count=count))
        cocotb.start_soon(monitor_state(dut, _cov_report.state_cov))

        mem.write_word(0x00000000, 0x00C000EF)  # jal x1, 12
        mem.write_word(0x00000004, 0x06300113)  # addi x2, x0, 99 (skipped)
        mem.write_word(0x00000008, 0x05800193)  # addi x3, x0, 88 (skipped)
        mem.write_word(0x0000000C, 0x01400213)  # addi x4, x0, 20
        mem.write_word(0x00000010, 0x00000013)  # nop
        mem.write_word(0x00000014, JAL(0, 0))  # infinite self-loop

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
    finally:
        mem.stop()


@cocotb.test()
async def test_isa_coverage(dut):
    """Exercise all 37 RV32I instructions and cover cache-stall pipeline events."""
    dut._log.info("=== Test: ISA Coverage ===")
    cocotb.start_soon(Clock(dut.clk_i, 10, units="ns").start())
    _init_inputs(dut)

    ref_model = RV32IModel()
    scoreboard = CPUScoreboard(ref_model, log=dut._log, coverage=_cov_report)
    mem = SimpleAXIMemory(dut, ref_model=ref_model)
    dbg = APBDebugInterface(dut)
    count = [0]
    cocotb.start_soon(monitor_commits(dut, scoreboard=scoreboard, count=count))
    cocotb.start_soon(monitor_state(dut, _cov_report.state_cov))

    # Program layout (word index → address = index × 4):
    #   [0]  0x000  LUI  x1, 1          x1 = 0x1000  (data memory base)
    #   [1]  0x004  ADDI x2, x0, 16     x2 = 16
    #   [2]  0x008  AUIPC x3, 0         x3 = 0x0008  (used later by JALR)
    #   [3]  0x00C  ADDI x4, x0, 5      x4 = 5
    #   [4]  0x010  ADDI x5, x0, -5     x5 = -5
    #   [5]  0x014  SW  x2, 0(x1)       mem[0x1000] = 16  (MEM_WAIT)
    #   [6]  0x018  SH  x2, 4(x1)       mem[0x1004] = 16  (MEM_WAIT)
    #   [7]  0x01C  SB  x2, 8(x1)       mem[0x1008] = 16  (MEM_WAIT)
    #   [8]  0x020  LW  x6, 0(x1)       x6 = 16           (MEM_WAIT)
    #   [9]  0x024  LH  x7, 4(x1)       x7 = 16           (MEM_WAIT)
    #  [10]  0x028  LB  x8, 8(x1)       x8 = 16           (MEM_WAIT)
    #  [11]  0x02C  LHU x9, 4(x1)       x9 = 16           (MEM_WAIT)
    #  [12]  0x030  LBU x10, 8(x1)      x10 = 16          (MEM_WAIT)
    #  [13]  0x034  ADD  x11, x6, x4    x11 = 21
    #  [14]  0x038  SUB  x11, x6, x4    x11 = 11
    #  [15]  0x03C  SLL  x11, x4, x4    x11 = 160
    #  [16]  0x040  SLT  x11, x4, x6    x11 = 1
    #  [17]  0x044  SLTU x11, x4, x6    x11 = 1
    #  [18]  0x048  XOR  x11, x4, x6    x11 = 21
    #  [19]  0x04C  SRL  x11, x6, x4    x11 = 0
    #  [20]  0x050  SRA  x11, x5, x4    x11 = -1
    #  [21]  0x054  OR   x11, x4, x6    x11 = 21
    #  [22]  0x058  AND  x11, x4, x6    x11 = 0
    #  [23]  0x05C  SLTI  x11, x4, 10   x11 = 1
    #  [24]  0x060  SLTIU x11, x4, 10   x11 = 1
    #  [25]  0x064  XORI  x11, x4, 255  x11 = 250
    #  [26]  0x068  ORI   x11, x4, 240  x11 = 245
    #  [27]  0x06C  ANDI  x11, x4, 15   x11 = 5
    #  [28]  0x070  SLLI  x11, x4, 2    x11 = 20
    #  [29]  0x074  SRLI  x11, x6, 1    x11 = 8
    #  [30]  0x078  SRAI  x11, x5, 1    x11 = -3
    #  [31]  0x07C  BEQ  x6, x6, +8    taken → 0x084
    #  [32]  0x080  NOP (skipped)
    #  [33]  0x084  BNE  x4, x6, +8    taken → 0x08C
    #  [34]  0x088  NOP (skipped)
    #  [35]  0x08C  BLT  x4, x6, +8    taken → 0x094
    #  [36]  0x090  NOP (skipped)
    #  [37]  0x094  BGE  x6, x4, +8    taken → 0x09C
    #  [38]  0x098  NOP (skipped)
    #  [39]  0x09C  BLTU x4, x6, +8    taken → 0x0A4
    #  [40]  0x0A0  NOP (skipped)
    #  [41]  0x0A4  BGEU x6, x4, +8    taken → 0x0AC
    #  [42]  0x0A8  NOP (skipped)
    #  [43]  0x0AC  JAL  x0, +12       → 0x0B8
    #  [44]  0x0B0  NOP (skipped)
    #  [45]  0x0B4  NOP (skipped)
    #  [46]  0x0B8  JALR x0, x3, 0xB4  → x3+0xB4 = 0x0008+0xB4 = 0x00BC
    #  [47]  0x0BC  JAL  x0, 0          infinite loop (all 37 insns done)
    NOP = ADDI(0, 0, 0)
    program = [
        LUI(1, 1),
        ADDI(2, 0, 16),
        AUIPC(3, 0),
        ADDI(4, 0, 5),
        ADDI(5, 0, -5),
        SW(2, 1, 0),
        SH(2, 1, 4),
        SB(2, 1, 8),
        LW(6, 1, 0),
        LH(7, 1, 4),
        LB(8, 1, 8),
        LHU(9, 1, 4),
        LBU(10, 1, 8),
        ADD(11, 6, 4),
        SUB(11, 6, 4),
        SLL(11, 4, 4),
        SLT(11, 4, 6),
        SLTU(11, 4, 6),
        XOR(11, 4, 6),
        SRL(11, 6, 4),
        SRA(11, 5, 4),
        OR(11, 4, 6),
        AND(11, 4, 6),
        SLTI(11, 4, 10),
        SLTIU(11, 4, 10),
        XORI(11, 4, 0xFF),
        ORI(11, 4, 0xF0),
        ANDI(11, 4, 0x0F),
        SLLI(11, 4, 2),
        SRLI(11, 6, 1),
        SRAI(11, 5, 1),
        BEQ(6, 6, 8),
        NOP,
        BNE(4, 6, 8),
        NOP,
        BLT(4, 6, 8),
        NOP,
        BGE(6, 4, 8),
        NOP,
        BLTU(4, 6, 8),
        NOP,
        BGEU(6, 4, 8),
        NOP,
        JAL(0, 12),
        NOP,
        NOP,
        JALR(0, 3, 0xB4),
        JAL(0, 0),  # infinite loop — all 37 instructions executed
    ]
    for i, insn in enumerate(program):
        mem.write_word(i * 4, insn)

    await reset_dut(dut)
    await ClockCycles(dut.clk_i, 800)

    await dbg.halt_cpu()

    dut._log.info(f"Total commits: {count[0]}")
    passed = scoreboard.report()
    mem.stop()
    assert passed, "Scoreboard validation failed"
    dut._log.info("ISA coverage test passed")


@cocotb.test()
async def test_random_10k_instructions(dut):
    """Randomized test: execute 10k+ RV32I arithmetic instructions vs reference model.

    Generates 10001 randomly chosen R-type and I-type arithmetic instructions
    (no branches/jumps/memory) followed by a JAL-to-self infinite loop.
    The RNG seed is fixed for reproducibility; change SEED to explore new sequences.
    """
    import random

    SEED = 42
    NUM_INSNS = 10001

    dut._log.info(f"=== Test: Random 10k Instructions (seed={SEED}) ===")
    random.seed(SEED)

    cocotb.start_soon(Clock(dut.clk_i, 10, units="ns").start())
    _init_inputs(dut)

    ref_model = RV32IModel()
    scoreboard = CPUScoreboard(ref_model, log=dut._log, coverage=_cov_report)
    mem = SimpleAXIMemory(dut, ref_model=ref_model)
    count = [0]
    cocotb.start_soon(monitor_commits(dut, scoreboard=scoreboard, count=count))
    cocotb.start_soon(monitor_state(dut, _cov_report.state_cov))

    r_ops = [ADD, SUB, AND, OR, XOR, SLL, SRL, SRA, SLT, SLTU]
    i_ops = [ADDI, ANDI, ORI, XORI, SLTI, SLTIU]
    sh_ops = [SLLI, SRLI, SRAI]

    program = []
    for _ in range(NUM_INSNS):
        rd = random.randint(1, 31)  # x1–x31 (never write x0)
        rs1 = random.randint(0, 31)
        choice = random.randint(0, 2)
        if choice == 0:  # R-type
            rs2 = random.randint(0, 31)
            program.append(random.choice(r_ops)(rd, rs1, rs2))
        elif choice == 1:  # I-type arithmetic
            imm = random.randint(-2048, 2047)
            program.append(random.choice(i_ops)(rd, rs1, imm))
        else:  # Shift immediate
            shamt = random.randint(0, 31)
            program.append(random.choice(sh_ops)(rd, rs1, shamt))

    program.append(JAL(0, 0))  # infinite loop — all instructions done

    for i, insn in enumerate(program):
        mem.write_word(i * 4, insn)

    await reset_dut(dut)
    await ClockCycles(dut.clk_i, NUM_INSNS * 10 + 2000)

    dut._log.info(f"Total commits: {count[0]}")
    assert count[0] >= NUM_INSNS, f"Expected {NUM_INSNS}+ commits, got {count[0]} (seed={SEED})"
    passed = scoreboard.report()
    mem.stop()
    assert passed, f"Scoreboard validation failed (seed={SEED})"
    dut._log.info(f"Random 10k instructions test passed (seed={SEED})")


@cocotb.test()
async def test_ebreak_halt(dut):
    """EBREAK instruction: covers EBREAK (EX) and TRAP (WB) pipeline events.

    Pipeline trace for EBREAK at PC=0x0:
      Cycle ~3 (EX):  debug_ebreak_o=1  -> EBREAK coverage bin
      Cycle ~5 (WB):  trap_taken_o=1    -> TRAP coverage bin  (trap_valid propagates)
    No scoreboard: trap instructions don't assert commit_valid_o.
    """
    dut._log.info("=== Test: EBREAK Halt ===")
    cocotb.start_soon(Clock(dut.clk_i, 10, units="ns").start())
    _init_inputs(dut)

    mem = SimpleAXIMemory(dut)
    cocotb.start_soon(monitor_state(dut, _cov_report.state_cov))

    # EBREAK at reset vector; CPU halts after this — JAL is unreachable
    mem.write_word(0x00000000, EBREAK())
    mem.write_word(0x00000004, JAL(0, 0))

    await reset_dut(dut)
    # 60 cycles: I-cache miss refill ~15 cycles + 5 pipeline stages + margin
    await ClockCycles(dut.clk_i, 60)

    mem.stop()
    dut._log.info("EBREAK halt test passed")


@cocotb.test()
async def test_illegal_insn_trap(dut):
    """Illegal instruction causes trap_taken_o: explicit TRAP pipeline event test.

    0xFFFFFFFF at reset vector decodes as illegal. EX redirects to mtvec=0x0,
    CPU re-traps on same address forever (expected: mtvec default = 0x0).
    TRAP event fires at WB ~cycle 5.  No scoreboard needed.
    """
    dut._log.info("=== Test: Illegal Instruction Trap ===")
    cocotb.start_soon(Clock(dut.clk_i, 10, units="ns").start())
    _init_inputs(dut)

    mem = SimpleAXIMemory(dut)
    cocotb.start_soon(monitor_state(dut, _cov_report.state_cov))

    # Illegal instruction at reset vector; mtvec=0x0 → re-traps (expected)
    mem.write_word(0x00000000, 0xFFFFFFFF)

    await reset_dut(dut)
    # 60 cycles: I-cache miss refill ~15 cycles + 5 pipeline stages + margin
    await ClockCycles(dut.clk_i, 60)

    mem.stop()
    dut._log.info("Illegal instruction trap test passed")


@cocotb.test()
async def test_hello_world(dut):
    """Write 'Hello, World!' into a memory buffer and read it back.

    A small RV32I program uses LUI/ADDI/SW to store the 13 ASCII bytes into
    a 4-word buffer at 0x100, then LW to load them back into x1-x4.  The test
    halts the CPU via the APB debug port and reconstructs the string from the
    register values, exercising the full store→D-cache→load path.
    """
    dut._log.info("=== Test: Hello World ===")
    cocotb.start_soon(Clock(dut.clk_i, 10, units="ns").start())
    _init_inputs(dut)

    ref_model = RV32IModel()
    scoreboard = CPUScoreboard(ref_model, log=dut._log, coverage=_cov_report)
    mem = SimpleAXIMemory(dut, ref_model=ref_model)
    try:
        dbg = APBDebugInterface(dut)
        count = [0]
        cocotb.start_soon(monitor_state(dut, _cov_report.state_cov))

        # Materialize a 32-bit constant using LUI+ADDI (RISC-V li pseudo-instruction).
        # Applies the standard sign-correction when bits[11] of the low 12 are set.
        def li(rd, val):
            hi = (val + 0x800) >> 12 & 0xFFFFF
            lo = val & 0xFFF
            if hi == 0:
                return [ADDI(rd, 0, lo - (0x1000 if lo & 0x800 else 0))]
            instrs = [LUI(rd, hi)]
            if lo:
                instrs.append(ADDI(rd, rd, lo - (0x1000 if lo & 0x800 else 0)))
            return instrs

        # "Hello, World!" packed as 4 little-endian 32-bit words
        WORDS = [0x6C6C6548, 0x57202C6F, 0x646C726F, 0x00000021]
        #         "Hell"       "o, W"       "orld"       "!\0\0\0"
        BUF = 0x100  # data buffer base address (mapped in the AXI memory model)
        T = 11       # temp register used to build each constant before storing

        program = []
        program.append(ADDI(10, 0, BUF))        # x10 = 0x100

        for i, word in enumerate(WORDS):
            program.extend(li(T, word))          # x11 = word[i]
            program.append(SW(T, 10, i * 4))     # mem[x10 + i*4] = x11

        for i in range(4):
            program.append(LW(i + 1, 10, i * 4))  # x1..x4 = mem[x10 + i*4]

        program.append(JAL(0, 0))               # spin forever

        for pc_idx, instr in enumerate(program):
            mem.write_word(pc_idx * 4, instr)

        await reset_dut(dut)
        cocotb.start_soon(monitor_commits(dut, scoreboard=scoreboard, count=count))
        # 600 cycles: 17 instructions + I$/D$ cold-miss refills (4 AXI beats each) + margin
        await ClockCycles(dut.clk_i, 600)

        await dbg.halt_cpu()

        x1 = await dbg.read_gpr(1)
        x2 = await dbg.read_gpr(2)
        x3 = await dbg.read_gpr(3)
        x4 = await dbg.read_gpr(4)

        # Reconstruct the byte string from four little-endian 32-bit values
        raw = bytearray()
        for v in (x1, x2, x3, x4):
            raw += bytes([v & 0xFF, (v >> 8) & 0xFF, (v >> 16) & 0xFF, (v >> 24) & 0xFF])
        decoded = raw.rstrip(b"\x00").decode("ascii")

        dut._log.info(f"Memory buffer contains: {repr(decoded)}")
        assert decoded == "Hello, World!", f"Expected 'Hello, World!', got {repr(decoded)}"

        passed = scoreboard.report()
        assert passed, "Scoreboard validation failed"
        dut._log.info("Hello World test passed!")
    finally:
        mem.stop()


@cocotb.test()
async def test_coverage_report(dut):
    """Generate and log coverage report for all smoke tests."""
    dut._log.info("=== Coverage Report ===")

    report = _cov_report.generate(output_path="reports/coverage_summary.txt")

    for line in report.splitlines():
        dut._log.info(line if line else " ")

    dut._log.info("Coverage report written to reports/coverage_summary.txt")
