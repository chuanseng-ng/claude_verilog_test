"""
Debug interface tests for RV32I CPU

Tests:
- Halt and resume functionality
- Single-step execution
- Register read/write via debug interface
- Breakpoint functionality
- PC read/write
"""

import cocotb
from cocotb.triggers import ClockCycles
import sys
import os

# Add lib directory to path
test_dir = os.path.dirname(os.path.abspath(__file__))
lib_dir = os.path.join(os.path.dirname(test_dir), 'lib')
sys.path.insert(0, lib_dir)

from rv32i_env import RV32IEnvironment


@cocotb.test()
async def test_halt_resume(dut):
    """Test CPU halt and resume via debug interface"""
    # Create environment
    env = RV32IEnvironment(dut)
    env.build()

    # Reset
    await env.reset(duration_ns=100)

    # Load a simple program
    hex_file = os.path.join(os.path.dirname(test_dir), '..', 'tb', 'programs', 'simple_add.hex')
    env.load_program(hex_file)

    # Let CPU run for a few cycles
    await ClockCycles(env.clk, 10)

    # Halt the CPU
    env.log.info("Testing halt functionality")
    await env.apb_agent.halt_cpu()

    # Verify CPU is halted
    status = await env.apb_agent.driver.get_cpu_status()
    assert status['halted'], "CPU should be halted"
    env.log.info(f"CPU halted at PC=0x{status['pc']:08x}")

    # Resume the CPU
    env.log.info("Testing resume functionality")
    await env.apb_agent.resume_cpu()

    # Verify CPU is running
    status = await env.apb_agent.driver.get_cpu_status()
    assert status['running'], "CPU should be running"
    env.log.info("CPU resumed successfully")

    env.log.info("Test PASSED: Halt/Resume functionality")


@cocotb.test()
async def test_single_step(dut):
    """Test single-step execution"""
    # Create environment
    env = RV32IEnvironment(dut)
    env.build()

    # Reset
    await env.reset(duration_ns=100)

    # Load a simple program
    hex_file = os.path.join(os.path.dirname(test_dir), '..', 'tb', 'programs', 'simple_add.hex')
    env.load_program(hex_file)

    # Halt the CPU
    await env.apb_agent.halt_cpu()

    # Read initial PC
    pc_before = await env.apb_agent.driver.read_pc()
    env.log.info(f"Initial PC: 0x{pc_before:08x}")

    # Single step
    env.log.info("Executing single step")
    await env.apb_agent.step_cpu()

    # Wait a few cycles for step to complete
    await ClockCycles(env.clk, 10)

    # Read PC after step
    pc_after = await env.apb_agent.driver.read_pc()
    env.log.info(f"PC after step: 0x{pc_after:08x}")

    # PC should have changed (advanced by 4 for most instructions)
    assert pc_after != pc_before, "PC should have changed after single step"

    env.log.info("Test PASSED: Single-step execution")


@cocotb.test()
async def test_register_access(dut):
    """Test reading and writing registers via debug interface"""
    # Create environment
    env = RV32IEnvironment(dut)
    env.build()

    # Reset
    await env.reset(duration_ns=100)

    # Halt the CPU
    await env.apb_agent.halt_cpu()

    # Test writing and reading registers
    test_values = {
        1: 0x12345678,
        5: 0xDEADBEEF,
        10: 0xCAFEBABE,
        31: 0xFFFFFFFF
    }

    env.log.info("Testing register write/read")
    for reg, value in test_values.items():
        # Write register
        await env.apb_agent.write_gpr(reg, value)

        # Read back
        read_value = await env.apb_agent.read_gpr(reg)

        # Verify
        assert read_value == value, f"Register x{reg} mismatch: wrote 0x{value:08x}, read 0x{read_value:08x}"
        env.log.info(f"x{reg}: wrote 0x{value:08x}, read 0x{read_value:08x} - OK")

    # Test that x0 is always zero (should not be writable)
    await env.apb_agent.write_gpr(0, 0xDEADBEEF)
    x0_value = await env.apb_agent.read_gpr(0)
    assert x0_value == 0, f"x0 should always be 0, got 0x{x0_value:08x}"
    env.log.info("x0 correctly hardwired to 0")

    env.log.info("Test PASSED: Register access via debug interface")


@cocotb.test()
async def test_pc_access(dut):
    """Test reading and writing PC via debug interface"""
    # Create environment
    env = RV32IEnvironment(dut)
    env.build()

    # Reset
    await env.reset(duration_ns=100)

    # Halt the CPU
    await env.apb_agent.halt_cpu()

    # Read initial PC (should be 0 or small value after reset)
    pc_initial = await env.apb_agent.driver.read_pc()
    env.log.info(f"Initial PC: 0x{pc_initial:08x}")

    # Write a new PC value
    new_pc = 0x1000
    await env.apb_agent.driver.write_pc(new_pc)

    # Read back PC
    pc_read = await env.apb_agent.driver.read_pc()
    env.log.info(f"PC after write: 0x{pc_read:08x}")

    # Verify
    assert pc_read == new_pc, f"PC mismatch: wrote 0x{new_pc:08x}, read 0x{pc_read:08x}"

    env.log.info("Test PASSED: PC access via debug interface")


@cocotb.test()
async def test_breakpoint(dut):
    """Test hardware breakpoint functionality"""
    # Create environment
    env = RV32IEnvironment(dut)
    env.build()

    # Reset
    await env.reset(duration_ns=100)

    # Load a program
    hex_file = os.path.join(os.path.dirname(test_dir), '..', 'tb', 'programs', 'simple_add.hex')
    env.load_program(hex_file)

    # Set a breakpoint at a specific address
    bp_addr = 0x0010  # Set breakpoint at PC=0x10
    env.log.info(f"Setting breakpoint 0 at address 0x{bp_addr:08x}")
    await env.apb_agent.set_breakpoint(0, bp_addr, enable=True)

    # Let the CPU run
    env.log.info("Running CPU until breakpoint")

    # Wait for CPU to halt at breakpoint (with timeout)
    for _cycle in range(1000):
        await ClockCycles(env.clk, 1)
        status = await env.apb_agent.driver.get_cpu_status()

        if status['halted']:
            pc = status['pc']
            env.log.info(f"CPU halted at PC=0x{pc:08x}")

            # Check if we're near the breakpoint address
            if abs(pc - bp_addr) <= 4:  # Within one instruction
                env.log.info("Test PASSED: Breakpoint hit successfully")
                await env.apb_agent.driver.clear_breakpoint(0)
                return

    env.log.error("Test FAILED: Breakpoint not hit within timeout")
    raise AssertionError("Breakpoint not hit")


@cocotb.test()
async def test_full_debug_sequence(dut):
    """Test a complete debug sequence: load, halt, inspect, modify, resume"""
    # Create environment
    env = RV32IEnvironment(dut)
    env.build()

    # Reset
    await env.reset(duration_ns=100)

    # Load program
    hex_file = os.path.join(os.path.dirname(test_dir), '..', 'tb', 'programs', 'simple_add.hex')
    env.load_program(hex_file)

    # Let it run for a bit
    env.log.info("Running program")
    await ClockCycles(env.clk, 20)

    # Halt
    env.log.info("Halting CPU")
    await env.apb_agent.halt_cpu()

    # Dump state
    state = await env.dump_state()
    env.print_state(state)

    # Modify a register
    env.log.info("Modifying register x5")
    await env.apb_agent.write_gpr(5, 0xABCDEF00)

    # Verify modification
    x5_val = await env.apb_agent.read_gpr(5)
    assert x5_val == 0xABCDEF00, "Register modification failed"

    # Single step a few instructions
    for i in range(3):
        env.log.info(f"Single step {i+1}")
        await env.apb_agent.step_cpu()
        await ClockCycles(env.clk, 10)
        pc = await env.apb_agent.driver.read_pc()
        env.log.info(f"  PC = 0x{pc:08x}")

    # Resume
    env.log.info("Resuming CPU")
    await env.apb_agent.resume_cpu()

    # Let it run more
    await ClockCycles(env.clk, 50)

    # Halt again and dump final state
    await env.apb_agent.halt_cpu()
    final_state = await env.dump_state()
    env.print_state(final_state)

    env.log.info("Test PASSED: Full debug sequence completed")
