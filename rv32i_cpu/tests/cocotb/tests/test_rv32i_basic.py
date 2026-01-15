"""
Basic directed tests for RV32I CPU

Tests:
- Simple ALU operations (simple_add.hex)
- Load/Store operations (load_store.hex)
- Branch operations (branch_test.hex)
"""

import cocotb
import sys
import os

# Add lib directory to path
test_dir = os.path.dirname(os.path.abspath(__file__))
lib_dir = os.path.join(os.path.dirname(test_dir), 'lib')
sys.path.insert(0, lib_dir)

from rv32i_env import RV32IEnvironment


@cocotb.test()
async def test_simple_add(dut):
    """Test basic ALU operations using simple_add.hex"""
    # Create environment
    env = RV32IEnvironment(dut)
    env.build()

    # Reset
    await env.reset(duration_ns=100)

    # Start monitors
    env.start_monitors()

    # Find the hex file
    hex_file = os.path.join(os.path.dirname(test_dir), '..', 'tb', 'programs', 'simple_add.hex')

    # Load and run program
    env.log.info("Running simple_add test")
    success = await env.run_program(hex_file, max_cycles=1000)

    if success:
        # Dump final state
        state = await env.dump_state()
        env.print_state(state)
        env.log.info("Test PASSED: simple_add completed")
    else:
        env.log.error("Test FAILED: simple_add timed out")
        raise AssertionError("Test timed out")

    # Stop monitors
    env.stop_monitors()


@cocotb.test()
async def test_load_store(dut):
    """Test memory load/store operations using load_store.hex"""
    # Create environment
    env = RV32IEnvironment(dut)
    env.build()

    # Reset
    await env.reset(duration_ns=100)

    # Start monitors
    env.start_monitors()

    # Find the hex file
    hex_file = os.path.join(os.path.dirname(test_dir), '..', 'tb', 'programs', 'load_store.hex')

    # Load and run program
    env.log.info("Running load_store test")
    success = await env.run_program(hex_file, max_cycles=2000)

    if success:
        # Dump final state
        state = await env.dump_state()
        env.print_state(state)
        env.log.info("Test PASSED: load_store completed")
    else:
        env.log.error("Test FAILED: load_store timed out")
        raise AssertionError("Test timed out")

    # Stop monitors
    env.stop_monitors()


@cocotb.test()
async def test_branch(dut):
    """Test branch operations using branch_test.hex"""
    # Create environment
    env = RV32IEnvironment(dut)
    env.build()

    # Reset
    await env.reset(duration_ns=100)

    # Start monitors
    env.start_monitors()

    # Find the hex file
    hex_file = os.path.join(os.path.dirname(test_dir), '..', 'tb', 'programs', 'branch_test.hex')

    # Load and run program
    env.log.info("Running branch_test")
    success = await env.run_program(hex_file, max_cycles=2000)

    if success:
        # Dump final state
        state = await env.dump_state()
        env.print_state(state)
        env.log.info("Test PASSED: branch_test completed")
    else:
        env.log.error("Test FAILED: branch_test timed out")
        raise AssertionError("Test timed out")

    # Stop monitors
    env.stop_monitors()


@cocotb.test()
async def test_reset(dut):
    """Test basic reset functionality"""
    # Create environment
    env = RV32IEnvironment(dut)
    env.build()

    # Reset
    await env.reset(duration_ns=100)

    # Check initial state
    state = await env.dump_state()

    # PC should be 0 after reset
    assert state['status']['pc'] == 0, f"PC should be 0 after reset, got 0x{state['status']['pc']:08x}"

    # All registers should be 0 (except potentially x0 which is hardwired)
    for i in range(32):
        reg_val = state['registers'][f'x{i}']
        if reg_val != 0:
            env.log.warning(f"Register x{i} = 0x{reg_val:08x} after reset (expected 0)")

    env.log.info("Test PASSED: Reset verification")
