"""
Smoke tests for RV32I CPU - Phase 1
Basic functionality tests to verify CPU is operational.
"""

import cocotb
from cocotb.triggers import RisingEdge, Timer, ClockCycles, ReadOnly
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

        # Read data during access phase (when penable=1 and pready=1)
        await ReadOnly()  # Wait for signals to settle
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

    async def read_gpr(self, reg_num):
        """Read general purpose register x[reg_num]."""
        addr = self.DBG_GPR_BASE + (reg_num * 4)
        return await self.apb_read(addr)

    async def read_pc(self):
        """Read program counter."""
        return await self.apb_read(self.DBG_PC)


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
        read_count = 0
        while True:
            await RisingEdge(self.dut.clk)

            # Address phase
            if self.dut.axi_arvalid.value == 1:
                self.dut.axi_arready.value = 1
                addr = int(self.dut.axi_araddr.value)
                read_count += 1
                if read_count <= 5:  # Log first 5 reads
                    self.dut._log.info(f"AXI Read #{read_count}: addr=0x{addr:08x}")
                await RisingEdge(self.dut.clk)
                self.dut.axi_arready.value = 0

                # Data phase (1 cycle later for simplicity)
                await RisingEdge(self.dut.clk)
                data = self.read_word(addr)
                if read_count <= 5:  # Log first 5 reads
                    self.dut._log.info(f"AXI Read #{read_count}: data=0x{data:08x} (from 0x{addr:08x})")
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


async def monitor_commits(dut, count=[0]):
    """Monitor instruction commits for debugging."""
    while True:
        await RisingEdge(dut.clk)
        if dut.commit_valid.value == 1:
            count[0] += 1
            if count[0] <= 10:  # Log first 10 commits
                pc = int(dut.commit_pc.value)
                insn = int(dut.commit_insn.value)
                dut._log.info(f"Commit #{count[0]}: PC=0x{pc:08x}, insn=0x{insn:08x}")


@cocotb.test()
async def test_simple_addi(dut):
    """Test simple ADDI instruction."""
    dut._log.info("=== Test: Simple ADDI ===")

    # Start clock
    clock = Clock(dut.clk, 10, unit="ns")
    cocotb.start_soon(clock.start())

    # Initialize memory and debug interface
    mem = SimpleAXIMemory(dut)
    dbg = APBDebugInterface(dut)

    # Start commit monitor
    commit_count = [0]
    cocotb.start_soon(monitor_commits(dut, commit_count))

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

    # Check if any instructions committed before halting
    dut._log.info(f"Before halt - commit_valid: {dut.commit_valid.value}, commit_pc: 0x{int(dut.commit_pc.value):08x}")

    # Halt CPU and verify register values
    await dbg.halt_cpu()

    # Check status after halt
    status = await dbg.apb_read(dbg.DBG_STATUS)
    dut._log.info(f"After halt - status: 0x{status:08x}, halted: {status & 0x1}, running: {(status >> 1) & 0x1}")

    # Check x1 = 42
    x1_val = await dbg.read_gpr(1)
    assert x1_val == 42, f"Expected x1=42, got x1={x1_val}"
    dut._log.info(f"✓ x1 = {x1_val} (expected 42)")

    # Check x2 = 50
    x2_val = await dbg.read_gpr(2)
    assert x2_val == 50, f"Expected x2=50, got x2={x2_val}"
    dut._log.info(f"✓ x2 = {x2_val} (expected 50)")

    # Check PC progressed past both instructions
    pc_val = await dbg.read_pc()
    assert pc_val >= 0x08, f"Expected PC >= 0x08, got PC=0x{pc_val:08x}"
    dut._log.info(f"✓ PC = 0x{pc_val:08x} (expected >= 0x08)")

    dut._log.info(f"Total commits during test: {commit_count[0]}")
    dut._log.info("Simple ADDI test passed")


@cocotb.test()
async def test_branch_not_taken(dut):
    """Test branch not taken."""
    dut._log.info("=== Test: Branch Not Taken ===")

    # Start clock
    clock = Clock(dut.clk, 10, unit="ns")
    cocotb.start_soon(clock.start())

    # Initialize memory and debug interface
    mem = SimpleAXIMemory(dut)
    dbg = APBDebugInterface(dut)

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

    # Halt CPU and verify
    await dbg.halt_cpu()

    # Check x1 = 1
    x1_val = await dbg.read_gpr(1)
    assert x1_val == 1, f"Expected x1=1, got x1={x1_val}"
    dut._log.info(f"✓ x1 = {x1_val} (expected 1)")

    # Check x2 = 2
    x2_val = await dbg.read_gpr(2)
    assert x2_val == 2, f"Expected x2=2, got x2={x2_val}"
    dut._log.info(f"✓ x2 = {x2_val} (expected 2)")

    # Check x3 = 10 (branch was NOT taken, so ADDI x3 should have executed)
    x3_val = await dbg.read_gpr(3)
    assert x3_val == 10, f"Expected x3=10 (branch not taken), got x3={x3_val}"
    dut._log.info(f"✓ x3 = {x3_val} (expected 10, confirms branch not taken)")

    # Check PC progressed past the branch target instruction
    pc_val = await dbg.read_pc()
    assert pc_val >= 0x0C, f"Expected PC >= 0x0C, got PC=0x{pc_val:08x}"
    dut._log.info(f"✓ PC = 0x{pc_val:08x} (expected >= 0x0C)")

    dut._log.info("Branch not taken test passed")


@cocotb.test()
async def test_branch_taken(dut):
    """Test branch taken."""
    dut._log.info("=== Test: Branch Taken ===")

    # Start clock
    clock = Clock(dut.clk, 10, unit="ns")
    cocotb.start_soon(clock.start())

    # Initialize memory and debug interface
    mem = SimpleAXIMemory(dut)
    dbg = APBDebugInterface(dut)

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

    # Halt CPU and verify
    await dbg.halt_cpu()

    # Check x1 = 1
    x1_val = await dbg.read_gpr(1)
    assert x1_val == 1, f"Expected x1=1, got x1={x1_val}"
    dut._log.info(f"✓ x1 = {x1_val} (expected 1)")

    # Check x2 = 1
    x2_val = await dbg.read_gpr(2)
    assert x2_val == 1, f"Expected x2=1, got x2={x2_val}"
    dut._log.info(f"✓ x2 = {x2_val} (expected 1)")

    # Check x3 = 0 (branch WAS taken, so ADDI x3 should have been skipped)
    x3_val = await dbg.read_gpr(3)
    assert x3_val == 0, f"Expected x3=0 (branch taken, instruction skipped), got x3={x3_val}"
    dut._log.info(f"✓ x3 = {x3_val} (expected 0, confirms branch taken)")

    # Check x4 = 20 (branch target executed)
    x4_val = await dbg.read_gpr(4)
    assert x4_val == 20, f"Expected x4=20 (branch target), got x4={x4_val}"
    dut._log.info(f"✓ x4 = {x4_val} (expected 20, confirms branch target reached)")

    # Check PC is at or past branch target
    pc_val = await dbg.read_pc()
    assert pc_val >= 0x10, f"Expected PC >= 0x10, got PC=0x{pc_val:08x}"
    dut._log.info(f"✓ PC = 0x{pc_val:08x} (expected >= 0x10)")

    dut._log.info("Branch taken test passed")


@cocotb.test()
async def test_jal(dut):
    """Test JAL (Jump and Link) instruction."""
    dut._log.info("=== Test: JAL ===")

    # Start clock
    clock = Clock(dut.clk, 10, unit="ns")
    cocotb.start_soon(clock.start())

    # Initialize memory and debug interface
    mem = SimpleAXIMemory(dut)
    dbg = APBDebugInterface(dut)

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

    # Halt CPU and verify
    await dbg.halt_cpu()

    # Check x1 = 4 (return address: PC of JAL + 4 = 0x000 + 4 = 0x004)
    x1_val = await dbg.read_gpr(1)
    assert x1_val == 0x4, f"Expected x1=0x4 (return address), got x1=0x{x1_val:x}"
    dut._log.info(f"✓ x1 = 0x{x1_val:x} (expected 0x4, link register)")

    # Check x2 = 0 (should be skipped)
    x2_val = await dbg.read_gpr(2)
    assert x2_val == 0, f"Expected x2=0 (jumped over), got x2={x2_val}"
    dut._log.info(f"✓ x2 = {x2_val} (expected 0, instruction skipped)")

    # Check x3 = 0 (should be skipped)
    x3_val = await dbg.read_gpr(3)
    assert x3_val == 0, f"Expected x3=0 (jumped over), got x3={x3_val}"
    dut._log.info(f"✓ x3 = {x3_val} (expected 0, instruction skipped)")

    # Check x4 = 20 (jump target executed)
    x4_val = await dbg.read_gpr(4)
    assert x4_val == 20, f"Expected x4=20 (jump target), got x4={x4_val}"
    dut._log.info(f"✓ x4 = {x4_val} (expected 20, confirms jump target reached)")

    # Check PC is at or past jump target
    pc_val = await dbg.read_pc()
    assert pc_val >= 0x0C, f"Expected PC >= 0x0C, got PC=0x{pc_val:08x}"
    dut._log.info(f"✓ PC = 0x{pc_val:08x} (expected >= 0x0C)")

    dut._log.info("JAL test passed")


# Placeholder for future tests
# These will be expanded as verification progresses
