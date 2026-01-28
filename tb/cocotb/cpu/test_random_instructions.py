"""
Random instruction tests for RV32I CPU - Phase 1 Task #3
Executes 10,000+ random instructions with scoreboard validation.
"""

import cocotb
from cocotb.triggers import RisingEdge, ClockCycles, ReadOnly
from cocotb.clock import Clock
import sys
import os
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from tb.models.rv32i_model import RV32IModel
from tb.cocotb.common.scoreboard import CPUScoreboard
from tb.generators.rv32i_instr_gen import RV32IInstructionGenerator

# Import infrastructure from test_smoke.py
from tb.cocotb.cpu.test_smoke import (
    reset_dut, APBDebugInterface, SimpleAXIMemory, monitor_commits
)


async def run_single_seed(dut, seed, num_instructions):
    """
    Run a single random instruction test with given seed.

    Steps:
    1. Generate random program
    2. Initialize reference model and memory
    3. Initialize CPU registers via debug interface
    4. Load program into memory
    5. Resume CPU
    6. Monitor commits with scoreboard
    7. Wait for EBREAK (halted state)
    8. Verify scoreboard has 0 mismatches

    Args:
        dut: Device under test
        seed: Random seed for reproducibility
        num_instructions: Number of instructions to generate

    Raises:
        RuntimeError: If timeout or scoreboard validation fails
    """
    dut._log.info(f"Seed {seed}: Generating {num_instructions} instructions...")

    # Generate program
    gen = RV32IInstructionGenerator(seed=seed)
    program = gen.generate_program(num_instructions)
    init_regs = gen.get_register_init_values()

    # Initialize reference model
    ref_model = RV32IModel()
    scoreboard = CPUScoreboard(ref_model, log=dut._log)

    # Initialize memory (syncs with reference model)
    mem = SimpleAXIMemory(dut, ref_model=ref_model)

    # Load program into memory
    dut._log.info(f"Seed {seed}: Loading {len(program)} instructions into memory...")
    for addr, insn in program:
        mem.write_word(addr, insn)

    # Reset CPU
    await reset_dut(dut)

    # Initialize debug interface
    dbg = APBDebugInterface(dut)

    # Halt CPU first (in case it's running after reset)
    await dbg.halt_cpu()

    dut._log.info(f"Seed {seed}: Initializing registers...")
    for reg_num, value in init_regs.items():
        await dbg.write_gpr(reg_num, value)
        ref_model.regs[reg_num] = value  # Sync reference model

    # Set PC to program start
    await dbg.apb_write(dbg.DBG_PC, gen.config.instr_mem_base)
    ref_model.pc = gen.config.instr_mem_base

    # Start commit monitor (store task handle for cleanup)
    commit_count = [0]
    monitor_task = cocotb.start_soon(monitor_commits(dut, scoreboard=scoreboard, count=commit_count))

    # Resume CPU
    dut._log.info(f"Seed {seed}: Resuming CPU...")
    await dbg.resume_cpu()

    # Wait for program to complete (detect EBREAK/halted)
    timeout_cycles = num_instructions * 20  # Conservative timeout
    dut._log.info(f"Seed {seed}: Waiting for completion (timeout={timeout_cycles} cycles)...")

    for cycle in range(timeout_cycles):
        await RisingEdge(dut.clk)

        # Check if CPU halted (EBREAK reached)
        status = await dbg.apb_read(dbg.DBG_STATUS)
        if status & 0x1:  # HALTED bit
            dut._log.info(f"Seed {seed}: CPU halted after {cycle} cycles")
            break
    else:
        # Cancel monitor before raising exception
        monitor_task.kill()
        raise RuntimeError(f"Seed {seed}: CPU did not halt (timeout after {timeout_cycles} cycles)")

    # Give scoreboard time to process final commits
    await ClockCycles(dut.clk, 5)

    # Cancel monitor task to prevent orphaned tasks accumulating
    monitor_task.kill()

    # Verify scoreboard
    dut._log.info(f"Seed {seed}: Verifying scoreboard ({commit_count[0]} commits)...")
    passed = scoreboard.report()

    if not passed:
        raise RuntimeError(f"Seed {seed}: Scoreboard validation failed")

    dut._log.info(f"Seed {seed}: PASSED ({commit_count[0]} instructions committed)")


@cocotb.test()
async def test_random_instructions_multi_seed(dut):
    """
    Execute 100 seeds × 100 instructions = 10,000 instructions.

    Each seed generates a unique random program and validates
    execution against the reference model via scoreboard.
    """
    # Start clock
    clock = Clock(dut.clk, 10, unit="ns")
    cocotb.start_soon(clock.start())

    # Configuration
    NUM_SEEDS = 100
    INSTRUCTIONS_PER_SEED = 100

    # Track results
    passing_seeds = []
    failing_seeds = []

    dut._log.info("="*70)
    dut._log.info(f"RANDOM INSTRUCTION TEST: {NUM_SEEDS} seeds × {INSTRUCTIONS_PER_SEED} instructions")
    dut._log.info("="*70)

    for seed in range(NUM_SEEDS):
        dut._log.info("="*70)
        dut._log.info(f"Running seed {seed+1}/{NUM_SEEDS} (seed={seed})")
        dut._log.info("="*70)

        try:
            # Run single seed test
            await run_single_seed(dut, seed, INSTRUCTIONS_PER_SEED)
            passing_seeds.append(seed)

        except Exception as e:
            failing_seeds.append((seed, str(e)))
            dut._log.error(f"Seed {seed} FAILED: {e}")
            # Continue to next seed (collect all failures)

    # Final report
    dut._log.info("="*70)
    dut._log.info("RANDOM INSTRUCTION TEST SUMMARY")
    dut._log.info("="*70)
    dut._log.info(f"Total seeds:     {NUM_SEEDS}")
    dut._log.info(f"Passing seeds:   {len(passing_seeds)} ({100*len(passing_seeds)/NUM_SEEDS:.1f}%)")
    dut._log.info(f"Failing seeds:   {len(failing_seeds)} ({100*len(failing_seeds)/NUM_SEEDS:.1f}%)")
    dut._log.info(f"Total instructions: {len(passing_seeds) * INSTRUCTIONS_PER_SEED}")

    if failing_seeds:
        dut._log.error("Failed seeds:")
        for seed, error in failing_seeds:
            dut._log.error(f"  Seed {seed}: {error}")

        # Write failing seeds to file for regression
        failing_seeds_file = Path(__file__).parent.parent.parent.parent / "failing_seeds.txt"
        with open(failing_seeds_file, "w") as f:
            f.write(f"# Failing seeds from random instruction test\n")
            f.write(f"# Re-run with: RANDOM_SEED=<seed> make test TEST_MODULE=tb.cocotb.cpu.test_random_instructions TEST=test_random_instructions_single_seed\n\n")
            for seed, error in failing_seeds:
                f.write(f"{seed}  # {error}\n")

        dut._log.error(f"Failing seeds written to: {failing_seeds_file}")

        assert False, f"{len(failing_seeds)}/{NUM_SEEDS} seeds failed"
    else:
        dut._log.info("ALL SEEDS PASSED")


@cocotb.test()
async def test_random_instructions_single_seed(dut):
    """
    Run a single seed for debugging purposes.
    Useful for reproducing failures from failing_seeds.txt.

    Usage:
        RANDOM_SEED=42 make test TEST_MODULE=tb.cocotb.cpu.test_random_instructions TEST=test_random_instructions_single_seed
    """
    # Start clock
    clock = Clock(dut.clk, 10, unit="ns")
    cocotb.start_soon(clock.start())

    # Get seed from environment variable
    SEED = int(os.environ.get("RANDOM_SEED", "42"))
    NUM_INSTRUCTIONS = int(os.environ.get("NUM_INSTRUCTIONS", "100"))

    dut._log.info("="*70)
    dut._log.info(f"SINGLE SEED DEBUG TEST: seed={SEED}, instructions={NUM_INSTRUCTIONS}")
    dut._log.info("="*70)

    await run_single_seed(dut, SEED, NUM_INSTRUCTIONS)

    dut._log.info("SINGLE SEED TEST PASSED")
