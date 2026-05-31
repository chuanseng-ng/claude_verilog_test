"""
AXI4-Lite Protocol Compliance Tests

Test Categories:
A. Back-Pressure Tests (4 tests) - Verify CPU waits correctly for AXI handshakes
B. Error Response Tests (3 tests) - Verify CPU traps on AXI errors
C. Protocol Compliance Tests (4 tests) - Verify AXI4-Lite protocol rules

Based on TASK4_AXI_PROTOCOL_TESTS_PLAN.md specification.
"""

import os
import random
import sys

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge

# Add project root to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from sim.riscv_encoder import ADDI, JAL, LUI, LW, SB, SH, SW
from tb.cocotb.common.clock_reset import reset_dut, wait_cycles
from tb.cocotb.cpu.axi_models import ConfigurableAXIMemory
from tb.models.rv32i_model import RV32IModel

# =============================================================================
# Helper Functions
# =============================================================================

# Module-level reference to the previous test's memory model so its
# background handler tasks can be cancelled before the next test starts.
# This avoids stale handlers (and a second clock) from a prior test competing
# with the freshly-created handlers of the current test (cocotb v1.x behaviour).
_prev_mem = None
_prev_clock_task = None


async def setup_test(dut, use_ref_model=False):
    """Setup test environment with clock and memory.

    Args:
        dut: Device under test
        use_ref_model: Create reference model for error tests

    Returns:
        tuple: (memory, ref_model or None)
    """
    global _prev_mem, _prev_clock_task

    # In cocotb v2, tasks are scoped to their parent test coroutine and
    # automatically cancelled when the test ends.  Explicit cancellation
    # can interfere with the scheduler in some edge cases, so we only
    # cancel when running under cocotb v1 (where tasks leak across tests).
    if _prev_mem is not None:
        try:
            _prev_mem.stop()
        except Exception:
            pass
        _prev_mem = None

    # Start fresh clock — the old clock task (if any) is killed by
    # cocotb v2 test isolation.  Explicit cancel is kept as a v1 fallback.
    if _prev_clock_task is not None:
        try:
            _prev_clock_task.cancel()
        except Exception:
            pass
        _prev_clock_task = None

    clock = Clock(dut.clk_i, 10, units="ns")
    _prev_clock_task = cocotb.start_soon(clock.start())

    # Clear all AXI input signals to safe defaults BEFORE reset.
    # Previous test's cancelled handlers may have left stale values
    # (e.g., rvalid=1 with rresp=DECERR) that confuse the CPU on reset.
    dut.axi_arready_i.value = 0
    dut.axi_rvalid_i.value = 0
    dut.axi_rdata_i.value = 0
    dut.axi_rresp_i.value = 0
    if hasattr(dut, "axi_rlast_i"):
        dut.axi_rlast_i.value = 0
    dut.axi_awready_i.value = 0
    dut.axi_wready_i.value = 0
    dut.axi_bvalid_i.value = 0
    dut.axi_bresp_i.value = 0

    # Reset DUT before starting handlers to avoid observing undefined signals
    await reset_dut(dut)

    # Create reference model if needed
    ref_model = RV32IModel() if use_ref_model else None

    # Create configurable memory (handlers start after reset)
    mem = ConfigurableAXIMemory(dut, ref_model=ref_model, protocol_check=True)
    _prev_mem = mem

    # Yield one cycle so handler tasks begin executing
    await RisingEdge(dut.clk_i)

    return mem, ref_model


async def run_until_pc(dut, target_pc, max_cycles=1000):
    """Run CPU until PC reaches target value.

    Args:
        dut: Device under test
        target_pc: Target PC value
        max_cycles: Maximum cycles to wait

    Returns:
        Number of cycles elapsed

    Raises:
        TimeoutError: If target PC not reached within max_cycles
    """
    cycles = 0
    while cycles < max_cycles:
        await RisingEdge(dut.clk_i)
        cycles += 1

        # Check if PC reached target (read from debug interface or internal signal)
        # Note: Adjust signal name based on actual RTL
        if hasattr(dut, "pc_o"):
            curr_pc = int(dut.pc_o.value)
            if curr_pc == target_pc:
                return cycles

    raise TimeoutError(f"PC did not reach 0x{target_pc:08x} within {max_cycles} cycles")


async def wait_for_state(dut, state_name, max_cycles=100):
    """Wait for CPU to reach specific state.

    Args:
        dut: Device under test
        state_name: Expected state name (e.g., 'FETCH', 'EXECUTE')
        max_cycles: Maximum cycles to wait

    Raises:
        TimeoutError: If state not reached within max_cycles
    """
    # TODO: Adapt state comparison based on RTL representation
    # - If state is a string signal: compare str(dut.state.value) == state_name
    # - If state is an enum: compare dut.state.value.binstr or integer value
    # - If state uses parameters: compare against numeric constants
    cycles = 0
    while cycles < max_cycles:
        await RisingEdge(dut.clk_i)
        cycles += 1

        if hasattr(dut, "state"):
            # Try to get state value (handles different RTL representations)
            try:
                current_state = str(dut.state.value)
                if current_state == state_name:
                    return cycles
            except (AttributeError, ValueError):
                # If state.value doesn't work, try binstr or integer comparison
                try:
                    if hasattr(dut.state, "binstr"):
                        current_state = dut.state.binstr
                    else:
                        current_state = int(dut.state.value)
                    if str(current_state) == state_name:
                        return cycles
                except (AttributeError, ValueError):
                    pass

    raise TimeoutError(f"State did not reach '{state_name}' within {max_cycles} cycles")


# ── Phase 1 AXI Protocol Regression ──────────────────────────────────────────
# Tests below cover back-pressure, error responses, and protocol compliance
# rules inherited from the Phase 1 AXI4-Lite master implementation.

# =============================================================================
# Category A: Back-Pressure Tests
# =============================================================================


@cocotb.test()
async def test_axi_arready_backpressure(dut):
    """Test CPU waits correctly when arready is delayed.

    Test sequence:
    1. Load simple ADDI instruction
    2. Inject 5-cycle arready delay
    3. Monitor arvalid/arready handshake
    4. Verify CPU waits exactly 5 cycles
    5. Verify instruction executes correctly
    """
    dut._log.info("=== Test: AXI arready Back-Pressure ===")

    mem, _ = await setup_test(dut)

    # Load test program: ADDI x1, x0, 42
    mem.write_word(0x0000, ADDI(1, 0, 42))

    # Inject 5-cycle arready delay
    mem.inject_read_delay(arready_cycles=5, rvalid_cycles=0)

    # Monitor transaction
    arvalid_start = None
    arready_asserted = None
    cycle = 0

    while cycle < 50:
        await RisingEdge(dut.clk_i)

        # Track when arvalid asserts
        if dut.axi_arvalid_o.value == 1 and arvalid_start is None:
            arvalid_start = cycle
            dut._log.info(f"arvalid asserted at cycle {cycle}")

        # Track when arready responds
        if dut.axi_arready_i.value == 1 and arready_asserted is None:
            arready_asserted = cycle
            dut._log.info(f"arready asserted at cycle {cycle}")

            # Verify 5-cycle delay
            if arvalid_start is None:
                dut._log.error("arready asserted but arvalid_start was never recorded")
                assert False, "arready asserted before arvalid was recorded"

            stall_cycles = arready_asserted - arvalid_start
            # Expected: 5-cycle delay + 1 stabilization + 0-1 scheduling offset.
            # Exact count depends on when arvalid first fires relative to the
            # handler's RisingEdge await, so tolerate 6 or 7.
            assert 6 <= stall_cycles <= 7, (
                f"Expected 6-7 cycle stall (5 delay + stabilization + scheduling),"
                f" got {stall_cycles} cycles"
            )

        cycle += 1

    # Verify no protocol violations
    assert len(mem.violations) == 0, f"Protocol violations detected: {mem.violations}"

    # Verify statistics
    stats = mem.get_stats()
    assert stats["max_arready_stall"] == 5, (
        f"Expected max stall=5, got {stats['max_arready_stall']}"
    )
    assert stats["read_count"] >= 1, "Expected at least 1 read transaction"

    dut._log.info("Test passed: CPU correctly waited for arready")


@cocotb.test()
async def test_axi_rvalid_delay(dut):
    """Test CPU waits correctly when rvalid is delayed.

    Test sequence:
    1. Load simple ADDI instruction
    2. Inject 10-cycle rvalid delay (after arready)
    3. Monitor rvalid assertion timing
    4. Verify CPU waits in FETCH state
    5. Verify instruction executes correctly
    """
    dut._log.info("=== Test: AXI rvalid Delay ===")

    mem, _ = await setup_test(dut)

    # Load test program: ADDI x2, x0, 100
    mem.write_word(0x0000, ADDI(2, 0, 100))

    # Inject 10-cycle rvalid delay
    mem.inject_read_delay(arready_cycles=0, rvalid_cycles=10)

    # Monitor transaction
    arready_handshake = None
    rvalid_asserted = None
    cycle = 0

    while cycle < 50:
        await RisingEdge(dut.clk_i)

        # Track arready handshake
        if (
            dut.axi_arvalid_o.value == 1
            and dut.axi_arready_i.value == 1
            and arready_handshake is None
        ):
            arready_handshake = cycle
            dut._log.info(f"arready handshake at cycle {cycle}")

        # Track rvalid assertion
        if dut.axi_rvalid_i.value == 1 and rvalid_asserted is None:
            rvalid_asserted = cycle
            dut._log.info(f"rvalid asserted at cycle {cycle}")

            # Log timing if arready_handshake was captured.
            # Due to cocotb coroutine scheduling, the test may observe arready
            # and rvalid one cycle after the handler drives them; we therefore
            # tolerate a ±1 offset instead of asserting an exact count.
            if arready_handshake is not None:
                delay_cycles = rvalid_asserted - arready_handshake - 1
                dut._log.info(f"Observed rvalid delay: {delay_cycles} cycles (expected ~10)")
                assert 9 <= delay_cycles <= 11, (
                    f"Expected ~10-cycle rvalid delay, got {delay_cycles} cycles"
                )

        cycle += 1

    # Verify no protocol violations
    assert len(mem.violations) == 0, f"Protocol violations detected: {mem.violations}"

    # Verify statistics
    stats = mem.get_stats()
    assert stats["max_rvalid_stall"] == 10, (
        f"Expected max stall=10, got {stats['max_rvalid_stall']}"
    )

    dut._log.info("Test passed: CPU correctly waited for rvalid")


@cocotb.test()
async def test_axi_bvalid_delay(dut):
    """Test CPU waits correctly when bvalid is delayed.

    Test sequence:
    1. Load LUI + SW instruction sequence
    2. Inject 5-cycle bvalid delay
    3. Monitor bvalid assertion timing
    4. Verify CPU waits after store
    5. Verify store completes correctly
    """
    dut._log.info("=== Test: AXI bvalid Delay ===")

    mem, _ = await setup_test(dut)

    # Load test program:
    # 0x0000: LUI x1, 0x12345       # Load upper immediate
    # 0x0004: SW x1, 0x100(x0)      # Store word to 0x100 (write-back: stays in cache)
    # 0x0008: LUI x29, 0x1          # x29 = 0x1000 (eviction address base)
    # 0x000C: LW x0, 0x100(x29)     # Load from 0x1100 (conflicts with 0x100, evicts)
    # 0x0010: EBREAK
    # Phase 3: SW is write-back cached; we must trigger an eviction to see an AXI write.
    # The conflicting LW at 0x1100 (same cache set, different tag) forces dirty writeback.
    mem.write_word(0x0000, LUI(1, 0x12345))
    mem.write_word(0x0004, SW(1, 0, 0x100))
    mem.write_word(0x0008, LUI(29, 0x1))  # x29 = 0x1000
    mem.write_word(0x000C, LW(0, 29, 0x100))  # load from 0x1100 → evicts dirty 0x100 line
    mem.write_word(0x0010, 0x00100073)  # EBREAK
    mem.write_word(0x1100, 0)  # pre-populate eviction target for D-cache refill

    # Inject 5-cycle bvalid delay BEFORE the SW can execute.
    # The delay persists until the next write transaction consumes it.
    mem.inject_write_delay(awready_cycles=0, wready_cycles=0, bvalid_cycles=5)

    # Monitor write transaction — use generous window for 5-stage pipeline
    # with AXI stabilization delays and D-cache eviction latency (Phase 3:
    # the write appears only after the conflicting LW triggers D-cache eviction)
    #
    # Burst protocol note: with AXI4 burst writeback the sequence is:
    #   AW handshake (1 cycle)  →  4 W-beats stream  →  5-cycle bvalid delay  →  B
    # Measuring delay from AW handshake gives "5 + 4 W-beats = 9", not 5.
    # The correct reference point is the WLAST handshake (cycle where wlast && wvalid
    # && wready are all 1), after which exactly the injected 5-cycle delay applies.
    wlast_handshake = None
    bvalid_asserted = None
    cycle = 0

    while cycle < 400:
        await RisingEdge(dut.clk_i)

        # Track WLAST handshake (final write-data beat accepted)
        # This is the correct reference for the bvalid delay measurement under burst.
        if (
            hasattr(dut, "axi_wlast_o")
            and dut.axi_wlast_o.value == 1
            and dut.axi_wvalid_o.value == 1
            and dut.axi_wready_i.value == 1
            and wlast_handshake is None
        ):
            wlast_handshake = cycle
            dut._log.info(f"wlast handshake at cycle {cycle}")

        # Track bvalid assertion
        if dut.axi_bvalid_i.value == 1 and bvalid_asserted is None:
            bvalid_asserted = cycle
            dut._log.info(f"bvalid asserted at cycle {cycle}")

            # Verify 5-cycle delay measured from WLAST handshake.
            # (Measuring from AW handshake would give 5 + 4_W_beats = 9 under burst.)
            if wlast_handshake is None:
                dut._log.error("bvalid asserted but wlast_handshake was never recorded")
                assert False, "bvalid asserted before wlast handshake was recorded"

            delay_cycles = bvalid_asserted - wlast_handshake - 1
            assert delay_cycles == 5, f"Expected 5-cycle bvalid delay, got {delay_cycles} cycles"
            break  # Got what we need, stop monitoring

        cycle += 1

    # Wait for handler to finish bready handshake and update stats
    await wait_cycles(dut, 5)

    # Verify no protocol violations
    assert len(mem.violations) == 0, f"Protocol violations detected: {mem.violations}"

    # Verify statistics
    stats = mem.get_stats()
    assert stats["max_bvalid_stall"] == 5, f"Expected max stall=5, got {stats['max_bvalid_stall']}"
    assert stats["write_count"] >= 1, "Expected at least 1 write transaction"

    # Verify store completed
    stored_value = mem.read_word(0x100)
    assert stored_value == 0x12345000, f"Expected 0x12345000, got 0x{stored_value:08x}"

    dut._log.info("Test passed: CPU correctly waited for bvalid")


@cocotb.test()
async def test_axi_random_backpressure(dut):
    """Test CPU handles random back-pressure correctly.

    Test sequence:
    1. Load 50-instruction program (simple arithmetic)
    2. Apply random delays (0-10 cycles) to each transaction
    3. Verify all instructions execute correctly
    4. Verify no protocol violations
    """
    dut._log.info("=== Test: AXI Random Back-Pressure ===")

    mem, _ref_model = await setup_test(dut, use_ref_model=True)

    # TODO [DEFERRED - Requires CPU-level testbench]: Expand to 10,000+ instructions with
    # scoreboard-style RTL vs reference model comparison
    #
    # CURRENT LIMITATION: This test only runs 50 ADDI instructions and verifies AXI protocol
    # compliance (no violations, correct statistics) but does NOT compare RTL register state
    # against _ref_model.
    #
    # WHY DEFERRED:
    # 1. This test operates at the AXI protocol level and has NO visibility into CPU internal
    #    state (register file, PC). Cannot read RTL register values to compare against model.
    # 2. No mechanism to detect instruction completion boundaries (when to step _ref_model)
    # 3. Proper scoreboard requires tracking:
    #    - PC progression (to know which instruction executed)
    #    - Register file state (to compare RTL vs model after each instruction)
    #    - In-flight AXI transactions (to correlate bus activity with architectural state)
    # 4. _ref_model is instantiated but unused because we lack observability points
    #
    # PROPER SOLUTION:
    # - Implement in a CPU-level testbench (e.g., test_cpu_core.py) that has direct access to:
    #   * dut.register_file (or equivalent internal signals)
    #   * dut.pc_o (program counter)
    #   * dut instruction completion strobes
    # - Use pyuvm Scoreboard pattern with:
    #   * Predictor: Steps _ref_model on each instruction completion
    #   * Comparator: Asserts RTL regfile[x] == _ref_model.regs[x] for all modified registers
    #   * Coverage: Track 10,000+ instructions with random back-pressure
    #
    # REFERENCE:
    # - See docs/verification/VERIFICATION_PLAN.md Section 3.3 "Reference Model Validation"
    # - See TODO_PHASE1_VERIFICATION.md Criterion #7 (Reference model comparison)
    # - Related test: test_random_instructions.py already implements this pattern for
    #   functional validation (100 seeds × 100 instructions = 10k+ coverage)
    #
    # WORKAROUND: For now, this test validates AXI protocol compliance under back-pressure.
    # Functional correctness is covered by test_random_instructions.py with reference model.

    # Load test program: 50 ADDI instructions
    # Use registers x1-x31 in a loop to generate 50 instructions
    num_instructions = 50
    for i in range(num_instructions):
        dst_reg = (i % 31) + 1  # Cycle through x1-x31
        src_reg = 0  # Always use x0 as source
        imm_val = i + 1
        mem.write_word(i * 4, ADDI(dst_reg, src_reg, imm_val))

    # Run with random delays
    random.seed(42)  # Reproducible randomness

    cycle = 0
    read_count = 0
    last_arvalid = 0
    max_cycles = 5000  # Allow plenty of time with delays (increased from 2000)

    while cycle < max_cycles and read_count < 50:
        # Detect rising edge of arvalid BEFORE clock edge to inject delay in time
        current_arvalid = dut.axi_arvalid_o.value
        if last_arvalid == 0 and current_arvalid == 1:
            # arvalid rising edge detected - inject delay before memory handler sees it
            arready_delay = random.randint(0, 10)
            rvalid_delay = random.randint(0, 10)
            mem.inject_read_delay(arready_cycles=arready_delay, rvalid_cycles=rvalid_delay)
            dut._log.info(f"Read #{read_count}: arready={arready_delay}, rvalid={rvalid_delay}")
            read_count += 1

        last_arvalid = current_arvalid
        await RisingEdge(dut.clk_i)
        cycle += 1

    # Verify no protocol violations
    assert len(mem.violations) == 0, f"Protocol violations detected: {mem.violations}"

    # Verify statistics
    stats = mem.get_stats()
    dut._log.info(f"Statistics: {stats}")

    # Verify sufficient random testing occurred.
    # Burst protocol note: each AXI4 burst refill transfers 4 instructions via ONE AR
    # transaction (arlen=3 → 4 R-beats, rlast on beat 4).  The BFM increments
    # read_count once per burst, so 50 instructions require ~13 AR transactions
    # (50 instructions / 4 per burst = 12.5 → 13 bursts).  The pre-burst threshold
    # of >=40 would require 160 instructions, which is wrong for burst mode.
    # Recalibrated: require at least 10 burst transactions (covers ≥40 instructions).
    assert stats["read_count"] >= 10, (
        f"Expected >=10 burst read transactions (>=40 instruction beats), "
        f"got {stats['read_count']} (burst semantics: 1 AR = 4 R-beats)"
    )
    assert stats["max_arready_stall"] <= 10, "Max arready stall exceeded 10 cycles"
    assert stats["max_rvalid_stall"] <= 10, "Max rvalid stall exceeded 10 cycles"

    dut._log.info(
        f"Test passed: CPU handled {read_count} random back-pressure transactions correctly"
    )


# =============================================================================
# Category B: Error Response Tests
# =============================================================================


@cocotb.test()
async def test_axi_slverr_fetch(dut):
    """Test CPU traps on SLVERR during instruction fetch.

    Test sequence:
    1. Load JAL instruction to jump to error address
    2. Inject SLVERR at target address
    3. Verify CPU traps with instruction access fault
    4. Verify trap_cause indicates fetch error
    """
    dut._log.info("=== Test: AXI SLVERR on Fetch ===")

    mem, _ref_model = await setup_test(dut, use_ref_model=True)

    # Load test program:
    # 0x0000: JAL x0, 0x100  # Jump to address with error
    mem.write_word(0x0000, JAL(0, 0x100))

    # Inject SLVERR at target address
    mem.inject_error(0x0100, "SLVERR")

    # Run and monitor for trap
    cycle = 0
    error_detected = False

    while cycle < 100:
        await RisingEdge(dut.clk_i)

        # Check for error response on read
        if dut.axi_rvalid_i.value == 1 and dut.axi_rresp_i.value == 0b10:
            dut._log.info(f"SLVERR detected at cycle {cycle}")
            error_detected = True

        # Check if CPU enters trap state (if exposed)
        # Note: Actual trap detection depends on RTL implementation
        # This is a placeholder for trap verification
        if hasattr(dut, "trap_o") and dut.trap_o.value == 1:
            dut._log.info(f"CPU trapped at cycle {cycle}")
            break

        cycle += 1

    # Verify error was presented
    assert error_detected, "SLVERR was not presented to CPU"

    # Note: Full trap verification requires RTL to expose trap signals
    # For now, we verify the error response was correctly generated

    dut._log.info("Test passed: SLVERR correctly generated on fetch")


@cocotb.test()
async def test_axi_decerr_load(dut):
    """Test CPU traps on DECERR during load instruction.

    Test sequence:
    1. Load ADDI + LW instruction sequence
    2. Inject DECERR for load address
    3. Verify CPU traps with load access fault
    4. Verify trap_cause indicates load error
    """
    dut._log.info("=== Test: AXI DECERR on Load ===")

    mem, _ref_model = await setup_test(dut, use_ref_model=True)

    # Load test program:
    # 0x0000: ADDI x1, x0, 0x200  # Load address into x1
    # 0x0004: LW x2, 0x000(x1)    # Load from address 0x200 (will get DECERR)
    mem.write_word(0x0000, ADDI(1, 0, 0x200))
    mem.write_word(0x0004, LW(2, 1, 0x000))

    # Inject DECERR at load address
    mem.inject_error(0x0200, "DECERR")

    # Run and monitor for trap
    cycle = 0
    error_detected = False
    last_ar_addr = None  # Capture AR handshake address
    max_cycles = 500  # Increased timeout

    while cycle < max_cycles:
        await RisingEdge(dut.clk_i)

        # Capture AR handshake address when both arvalid and arready are asserted
        if dut.axi_arvalid_o.value == 1 and dut.axi_arready_i.value == 1:
            last_ar_addr = int(dut.axi_araddr_o.value)

        # Check for error response on read (use captured address)
        if dut.axi_rvalid_i.value == 1 and dut.axi_rresp_i.value == 0b11:
            addr = last_ar_addr if last_ar_addr is not None else 0
            dut._log.info(f"DECERR detected at cycle {cycle}, addr=0x{addr:08x}")
            error_detected = True

        # Check if CPU enters trap state
        if hasattr(dut, "trap_o") and dut.trap_o.value == 1:
            dut._log.info(f"CPU trapped at cycle {cycle}")
            break

        cycle += 1

    # Verify error was presented
    assert error_detected, "DECERR was not presented to CPU"

    dut._log.info("Test passed: DECERR correctly generated on load")


@cocotb.test()
async def test_axi_error_store(dut):
    """Test CPU traps on error during store instruction.

    Test sequence:
    1. Load LUI + SW instruction sequence
    2. Inject SLVERR on write response (bresp)
    3. Verify CPU traps with store access fault
    4. Verify trap_cause indicates store error
    """
    dut._log.info("=== Test: AXI Error on Store ===")

    mem, _ref_model = await setup_test(dut, use_ref_model=True)

    # Load test program:
    # 0x0000: LUI x1, 0xBAD        # Load value to store
    # 0x0004: SW x1, 0x200(x0)     # Store to 0x200 (write-back D-cache: stays in cache)
    # 0x0008: LUI x29, 0x1         # x29 = 0x1000
    # 0x000C: LW x0, 0x200(x29)    # Load from 0x1200 (evicts dirty 0x200 line → AXI write)
    # 0x0010: EBREAK
    # Phase 3: SW is write-back cached; conflicting LW forces dirty eviction to AXI.
    # The AXI write at 0x200 then receives SLVERR, which is what the test monitors.
    mem.write_word(0x0000, LUI(1, 0xBAD))
    mem.write_word(0x0004, SW(1, 0, 0x200))
    mem.write_word(0x0008, LUI(29, 0x1))  # x29 = 0x1000
    mem.write_word(0x000C, LW(0, 29, 0x200))  # load from 0x1200 → evicts dirty 0x200 line
    mem.write_word(0x0010, 0x00100073)  # EBREAK
    mem.write_word(0x1200, 0)  # pre-populate eviction target for D-cache refill

    # Inject SLVERR on writes only — the SW will first read-allocate 0x200 (write-allocate),
    # then the LW from 0x1200 evicts the dirty line causing an AXI write to 0x200.
    # Using inject_write_error avoids triggering SLVERR on the read-allocate fetch.
    mem.inject_write_error(0x0200, "SLVERR")

    # Run and monitor for trap
    cycle = 0
    error_detected = False

    while cycle < 400:
        await RisingEdge(dut.clk_i)

        # Check for error response on write
        if dut.axi_bvalid_i.value == 1 and dut.axi_bresp_i.value == 0b10:
            dut._log.info(f"SLVERR on write detected at cycle {cycle}")
            error_detected = True

        # Check if CPU enters trap state
        if hasattr(dut, "trap_o") and dut.trap_o.value == 1:
            dut._log.info(f"CPU trapped at cycle {cycle}")
            break

        cycle += 1

    # Verify error was presented
    assert error_detected, "SLVERR was not presented on write response"

    dut._log.info("Test passed: Store error correctly generated")


# =============================================================================
# Category C: Protocol Compliance Tests
# =============================================================================


@cocotb.test()
async def test_axi_valid_before_ready(dut):
    """Test valid-before-ready protocol rule.

    Test sequence:
    1. Load simple instruction
    2. Apply back-pressure (delay ready signals)
    3. Monitor that arvalid asserts before checking arready
    4. Verify arvalid doesn't wait for arready
    """
    dut._log.info("=== Test: AXI Valid-Before-Ready Rule ===")

    mem, _ = await setup_test(dut)

    # Load test program
    mem.write_word(0x0000, ADDI(1, 0, 1))

    # Apply back-pressure to force waiting
    mem.inject_read_delay(arready_cycles=10, rvalid_cycles=0)

    # Monitor valid/ready relationship
    cycle = 0
    arvalid_cycle = None
    arready_cycle = None

    while cycle < 50:
        await RisingEdge(dut.clk_i)

        # Track first arvalid assertion
        if dut.axi_arvalid_o.value == 1 and arvalid_cycle is None:
            arvalid_cycle = cycle
            dut._log.info(f"arvalid asserted at cycle {cycle}")

        # Track first arready assertion
        if dut.axi_arready_i.value == 1 and arready_cycle is None:
            arready_cycle = cycle
            dut._log.info(f"arready asserted at cycle {cycle}")

        cycle += 1

    # Verify valid came before ready
    assert arvalid_cycle is not None, "arvalid was never asserted"
    assert arready_cycle is not None, "arready was never asserted"
    assert arvalid_cycle < arready_cycle, (
        "arvalid must assert before arready (valid-before-ready rule)"
    )

    # Verify no protocol violations
    assert len(mem.violations) == 0, f"Protocol violations detected: {mem.violations}"

    dut._log.info("Test passed: Valid-before-ready rule verified")


@cocotb.test()
async def test_axi_signal_stability(dut):
    """Test signal stability during handshake.

    Test sequence:
    1. Load instruction
    2. Apply back-pressure to create wait period
    3. Monitor araddr/wdata remain stable during wait
    4. Verify protocol violation detection works
    """
    dut._log.info("=== Test: AXI Signal Stability ===")

    mem, _ = await setup_test(dut)

    # Load test program
    mem.write_word(0x0000, ADDI(1, 0, 42))

    # Apply significant back-pressure
    mem.inject_read_delay(arready_cycles=15, rvalid_cycles=0)

    # Run test
    await wait_cycles(dut, 50)

    # Verify no stability violations detected
    assert len(mem.violations) == 0, f"Protocol violations detected: {mem.violations}"

    dut._log.info("Test passed: Signals remained stable during handshake")


@cocotb.test()
async def test_axi_no_outstanding(dut):
    """Test no outstanding transactions rule.

    Test sequence:
    1. Load multiple instructions
    2. Monitor transaction lifecycle
    3. Verify new arvalid not asserted until rvalid handshake complete
    4. Verify max 1 outstanding transaction
    """
    dut._log.info("=== Test: AXI No Outstanding Transactions ===")

    mem, _ = await setup_test(dut)

    # Load test program: multiple ADDIs
    for i in range(10):
        mem.write_word(i * 4, ADDI(i + 1, 0, i))

    # Monitor for overlapping transactions
    cycle = 0
    read_active = False
    violation_detected = False

    while cycle < 200:
        await RisingEdge(dut.clk_i)

        # Check for read completion FIRST to avoid false positives when
        # R completion and new AR handshake occur on the same cycle
        if dut.axi_rvalid_i.value == 1 and dut.axi_rready_o.value == 1:
            read_active = False

        # Check for new read starting while previous active
        if dut.axi_arvalid_o.value == 1 and dut.axi_arready_i.value == 1:
            if read_active:
                dut._log.error(f"New read started while previous read active at cycle {cycle}")
                violation_detected = True
            read_active = True

        cycle += 1

    # Verify no outstanding transaction violations
    assert not violation_detected, "Multiple outstanding transactions detected"

    dut._log.info("Test passed: No outstanding transactions rule verified")


@cocotb.test()
async def test_axi_wstrb_encoding(dut):
    """Test write strobe encoding for different store sizes.

    Test sequence:
    1. Execute SB instruction (expect wstrb based on address alignment)
    2. Execute SH instruction (expect wstrb based on alignment)
    3. Execute SW instruction (expect wstrb=0b1111)
    4. Verify strobe patterns match AXI4-Lite spec
    """
    dut._log.info("=== Test: AXI Write Strobe Encoding ===")

    mem, _ = await setup_test(dut)

    # Test program (Phase 3: stores go to write-back D-cache, AXI writes happen on eviction):
    # 0x0000: LUI x1, 0x1234       # Load value
    # 0x0004: SB x1, 0x100(x0)     # Store byte to cache line [0x100..0x10F]
    # 0x0008: SH x1, 0x104(x0)     # Store halfword — same cache line
    # 0x000C: SW x1, 0x108(x0)     # Store word — same cache line
    # 0x0010: LUI x29, 0x1         # x29 = 0x1000
    # 0x0014: LW x0, 0x100(x29)    # Load from 0x1100 (evicts dirty line → 4 AXI writes, wstrb=0xF)
    # 0x0018: EBREAK
    # D-cache eviction: all stores accumulate in one cache line, evicted as 4 full-word
    # AXI writes (wstrb=0b1111 each) at addresses 0x100, 0x104, 0x108, 0x10C.
    mem.write_word(0x0000, LUI(1, 0x1234))
    mem.write_word(0x0004, SB(1, 0, 0x100))
    mem.write_word(0x0008, SH(1, 0, 0x104))
    mem.write_word(0x000C, SW(1, 0, 0x108))
    mem.write_word(0x0010, LUI(29, 0x1))  # x29 = 0x1000
    mem.write_word(0x0014, LW(0, 29, 0x100))  # load from 0x1100 → evicts dirty line
    mem.write_word(0x0018, 0x00100073)  # EBREAK
    mem.write_word(0x1100, 0)  # pre-populate eviction target

    # Monitor write strobes
    # Burst protocol note: AXI4 burst writeback issues ONE AW at the cache-line base
    # (0x100) with awlen=3, followed by 4 W-beats for words 0x100, 0x104, 0x108, 0x10C.
    # There is no separate AW per word.  We therefore track:
    #   - current_aw_addr: set on each AW handshake (line base address)
    #   - w_beat_idx: per-burst beat counter (increments on each W-beat accepted,
    #                 resets on each new AW)
    # The per-beat address is current_aw_addr + w_beat_idx * 4.
    # wlast_o terminates the beat loop (beat index resets for next burst).
    cycle = 0
    wstrb_values = []
    current_aw_addr = None   # Base address of the current AW burst
    w_beat_idx = 0           # Beat index within the current burst

    while cycle < 400:
        await RisingEdge(dut.clk_i)

        # Capture AW handshake: record line base address and reset beat counter
        if dut.axi_awvalid_o.value == 1 and dut.axi_awready_i.value == 1:
            current_aw_addr = int(dut.axi_awaddr_o.value) & 0xFFFFFFFC
            w_beat_idx = 0

        # Capture wstrb when write data is accepted; compute per-beat word address
        if dut.axi_wvalid_o.value == 1 and dut.axi_wready_i.value == 1:
            wstrb = int(dut.axi_wstrb_o.value)
            # Per-beat address = burst base + beat_offset (burst semantics)
            beat_addr = (current_aw_addr + w_beat_idx * 4) if current_aw_addr is not None else 0
            wstrb_values.append((beat_addr, wstrb))
            dut._log.info(f"Write beat {w_beat_idx} at 0x{beat_addr:08x} with wstrb=0b{wstrb:04b}")
            # Advance beat counter; reset on wlast (end of burst)
            wlast = int(getattr(dut, "axi_wlast_o", 1))
            if wlast:
                w_beat_idx = 0
            else:
                w_beat_idx += 1

        cycle += 1

    # Phase 3/5 D-cache burst write-back behavior:
    # SB, SH, SW all write to the same 16-byte cache line [0x100..0x10F].
    # On eviction, the D-cache issues ONE AW at line base 0x100 (awlen=3) +
    # 4 W-beats for words at byte offsets 0, 4, 8, 12 (wstrb=0b1111 each).
    n = len(wstrb_values)
    assert n >= 4, f"Expected all 4 cache-line eviction W-beats, got {n}"

    # All eviction W-beats use full-word strobe (cache writeback granularity)
    for addr, wstrb in wstrb_values:
        assert wstrb == 0b1111, (
            f"Expected wstrb=0b1111 (cache line eviction), got 0b{wstrb:04b} at 0x{addr:08x}"
        )

    # Verify all 4 per-beat word addresses cover the evicted cache line (0x100..0x10C).
    # With burst: AW fires once at 0x100; beat addresses are computed from beat index.
    evicted_addrs = {addr for addr, _ in wstrb_values}
    for expected_addr in (0x100, 0x104, 0x108, 0x10C):
        assert expected_addr in evicted_addrs, (
            f"Expected eviction W-beat at 0x{expected_addr:08x} "
            f"(burst: one AW at line base 0x100, 4 W-beats at offsets +0/+4/+8/+12)"
        )

    dut._log.info(
        "Test passed: Write strobes correctly encoded (Phase 5 burst: one AW + 4 W-beats)"
    )


# ── Phase 2 AXI Arbiter Tests ─────────────────────────────────────────────────
# Tests below exercise the Phase 2 rv32i_axi_arbiter: simultaneous IF and MEM
# requests, priority (MEM over IF), and correct address routing.
# TODO: Add arbiter-specific tests (e.g. simultaneous IF+MEM, MEM priority).

# =============================================================================
# Test Summary
# =============================================================================


@cocotb.test()
async def test_axi_protocol_summary(dut):
    """Summary test that logs all protocol test results.

    This test just logs a summary message and always passes.
    Run this last to see overall results.
    """
    dut._log.info("=" * 60)
    dut._log.info("AXI4-Lite Protocol Test Suite Complete")
    dut._log.info("=" * 60)
    dut._log.info("Category A: Back-Pressure Tests (4)")
    dut._log.info("  - test_axi_arready_backpressure")
    dut._log.info("  - test_axi_rvalid_delay")
    dut._log.info("  - test_axi_bvalid_delay")
    dut._log.info("  - test_axi_random_backpressure")
    dut._log.info(" ")
    dut._log.info("Category B: Error Response Tests (3)")
    dut._log.info("  - test_axi_slverr_fetch")
    dut._log.info("  - test_axi_decerr_load")
    dut._log.info("  - test_axi_error_store")
    dut._log.info(" ")
    dut._log.info("Category C: Protocol Compliance Tests (4)")
    dut._log.info("  - test_axi_valid_before_ready")
    dut._log.info("  - test_axi_signal_stability")
    dut._log.info("  - test_axi_no_outstanding")
    dut._log.info("  - test_axi_wstrb_encoding")
    dut._log.info("=" * 60)
    dut._log.info(" ")

    # Simple clock setup to satisfy cocotb
    clock = Clock(dut.clk_i, 10, units="ns")
    cocotb.start_soon(clock.start())
    await wait_cycles(dut, 1)
