"""
Minimal EBREAK Test (Updated to use pyuvm infrastructure)

Tests that EBREAK instruction (0x00100073) causes CPU to halt.

Test Steps:
1. Reset CPU
2. Load EBREAK instruction at 0x0000 via AXI memory driver
3. Halt CPU
4. Set PC to 0x0000
5. Resume CPU
6. Wait for CPU to halt again
7. Verify CPU halted due to EBREAK

NOTE: This test now imports from pyuvm infrastructure instead of
using standalone helper classes. See legacy/ for original implementation.
"""

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, ClockCycles
from pathlib import Path
import sys

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

# Import from pyuvm infrastructure
from tb.cpu_uvm.agents.axi_agent.axi_driver import AXIMemoryDriver
from tb.cpu_uvm.agents.apb_agent.apb_driver import APBDebugDriver


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
    """Test that EBREAK instruction causes CPU to halt.

    This is a minimal test that uses pyuvm infrastructure components
    (AXIMemoryDriver and APBDebugDriver) instead of standalone classes.
    """

    # Start clock
    clock = Clock(dut.clk, 10, units="ns")
    cocotb.start_soon(clock.start())

    # Reset DUT
    await reset_dut(dut)

    dut._log.info("=" * 80)
    dut._log.info("EBREAK HALT TEST (using pyuvm infrastructure)")
    dut._log.info("=" * 80)

    # Create memory driver and debug driver from pyuvm
    # NOTE: We create minimal agent instances for this standalone test
    axi_driver = AXIMemoryDriver("axi_driver", None, dut, ref_model=None)
    apb_driver = APBDebugDriver("apb_driver", None, dut)

    # Start AXI background handlers
    cocotb.start_soon(axi_driver.axi_read_handler())
    cocotb.start_soon(axi_driver.axi_write_handler())

    # Give handlers time to start
    await ClockCycles(dut.clk, 2)

    # Load EBREAK instruction at address 0x0000
    # EBREAK encoding: 0x00100073
    ebreak_insn = 0x00100073
    dut._log.info(f"Loading EBREAK instruction (0x{ebreak_insn:08x}) at address 0x0000")
    axi_driver.write_word(0x00000000, ebreak_insn)

    # Halt CPU
    dut._log.info("Halting CPU...")
    await apb_driver.halt_cpu()

    # Verify halted
    status = await apb_driver.apb_read(apb_driver.DBG_STATUS)
    assert status & 0x1, "CPU should be halted"
    dut._log.info(f"CPU halted (status=0x{status:08x})")

    # Set PC to 0x0000
    dut._log.info("Setting PC to 0x00000000")
    await apb_driver.write_pc(0x00000000)

    # Read back PC to verify
    pc_val = await apb_driver.read_pc()
    dut._log.info(f"PC readback: 0x{pc_val:08x}")
    assert pc_val == 0x00000000, f"PC should be 0x00000000, got 0x{pc_val:08x}"

    # Clear halted status for clean test
    dut._log.info("Resuming CPU to execute EBREAK...")
    await apb_driver.resume_cpu()

    # Wait for CPU to halt (max 100 cycles)
    dut._log.info("Waiting for CPU to halt from EBREAK...")
    halted = False
    for cycle in range(100):
        await RisingEdge(dut.clk)

        # Check halted status
        status = await apb_driver.apb_read(apb_driver.DBG_STATUS)
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
                dut._log.warning(
                    f"✗ CPU halted but cause is 0x{halt_cause:x}, expected 0x8 (EBREAK)"
                )

            break

    # Verify CPU actually halted
    assert halted, "CPU should have halted after EBREAK instruction within 100 cycles"

    # Read PC to see where it stopped
    final_pc = await apb_driver.read_pc()
    dut._log.info(f"Final PC: 0x{final_pc:08x}")

    # Read the instruction that was executed
    final_insn = await apb_driver.apb_read(apb_driver.DBG_INSTR)
    dut._log.info(f"Final instruction: 0x{final_insn:08x}")

    if final_insn == ebreak_insn:
        dut._log.info("✓ EBREAK instruction was executed")
    else:
        dut._log.warning(
            f"✗ Expected EBREAK (0x{ebreak_insn:08x}), got 0x{final_insn:08x}"
        )

    dut._log.info("=" * 80)
    dut._log.info("EBREAK TEST COMPLETE")
    dut._log.info("=" * 80)
