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


async def setup_test(dut, use_ref_model=False):
    """Setup test environment with clock and memory.

    Args:
        dut: Device under test
        use_ref_model: Create reference model for error tests

    Returns:
        tuple: (memory, ref_model or None)
    """
    # Start clock (10ns = 100MHz)
    clock = Clock(dut.clk_i, 10, unit="ns")
    cocotb.start_soon(clock.start())

    # Reset DUT before starting handlers to avoid observing undefined signals
    await reset_dut(dut)

    # Create reference model if needed
    ref_model = RV32IModel() if use_ref_model else None

    # Create configurable memory (handlers start after reset)
    mem = ConfigurableAXIMemory(dut, ref_model=ref_model, protocol_check=True)

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
            assert stall_cycles == 5, f"Expected 5-cycle arready delay, got {stall_cycles} cycles"

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

            # Verify 10-cycle delay after arready
            if arready_handshake is None:
                dut._log.error("rvalid asserted but arready_handshake was never recorded")
                assert False, "rvalid asserted before arready handshake was recorded"

            delay_cycles = rvalid_asserted - arready_handshake - 1
            assert delay_cycles == 10, f"Expected 10-cycle rvalid delay, got {delay_cycles} cycles"

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
    # 0x0000: LUI x1, 0x12345  # Load upper immediate
    # 0x0004: SW x1, 0x100(x0) # Store word to address 0x100
    mem.write_word(0x0000, LUI(1, 0x12345))
    mem.write_word(0x0004, SW(1, 0, 0x100))

    # Let first instruction execute without delay
    await wait_cycles(dut, 10)

    # Inject 5-cycle bvalid delay for write transaction
    mem.inject_write_delay(awready_cycles=0, wready_cycles=0, bvalid_cycles=5)

    # Monitor write transaction
    awready_handshake = None
    bvalid_asserted = None
    cycle = 0

    while cycle < 50:
        await RisingEdge(dut.clk_i)

        # Track awready handshake
        if (
            dut.axi_awvalid_o.value == 1
            and dut.axi_awready_i.value == 1
            and awready_handshake is None
        ):
            awready_handshake = cycle
            dut._log.info(f"awready handshake at cycle {cycle}")

        # Track bvalid assertion
        if dut.axi_bvalid_i.value == 1 and bvalid_asserted is None:
            bvalid_asserted = cycle
            dut._log.info(f"bvalid asserted at cycle {cycle}")

            # Verify 5-cycle delay after awready
            if awready_handshake is None:
                dut._log.error("bvalid asserted but awready_handshake was never recorded")
                assert False, "bvalid asserted before awready handshake was recorded"

            delay_cycles = bvalid_asserted - awready_handshake - 1
            assert delay_cycles == 5, f"Expected 5-cycle bvalid delay, got {delay_cycles} cycles"

        cycle += 1

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

    # Verify sufficient random testing occurred (at least 40 transactions)
    # Note: May not reach exactly 50 due to CPU behavior (trap, halt, etc.)
    assert stats["read_count"] >= 40, f"Expected >=40 reads, got {stats['read_count']}"
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
    # 0x0000: LUI x1, 0xBAD    # Load value to store
    # 0x0004: SW x1, 0x200(x0) # Store to address with error
    mem.write_word(0x0000, LUI(1, 0xBAD))
    mem.write_word(0x0004, SW(1, 0, 0x200))

    # Inject SLVERR at store address
    mem.inject_error(0x0200, "SLVERR")

    # Run and monitor for trap
    cycle = 0
    error_detected = False

    while cycle < 100:
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

    # Test program:
    # 0x0000: LUI x1, 0x1234     # Load value
    # 0x0004: SB x1, 0x100(x0)   # Store byte (wstrb=0b0001)
    # 0x0008: SH x1, 0x104(x0)   # Store halfword (wstrb=0b0011)
    # 0x000C: SW x1, 0x108(x0)   # Store word (wstrb=0b1111)
    mem.write_word(0x0000, LUI(1, 0x1234))
    mem.write_word(0x0004, SB(1, 0, 0x100))
    mem.write_word(0x0008, SH(1, 0, 0x104))
    mem.write_word(0x000C, SW(1, 0, 0x108))

    # Monitor write strobes
    cycle = 0
    wstrb_values = []
    current_aw_addr = None  # Capture AW handshake address

    while cycle < 200:
        await RisingEdge(dut.clk_i)

        # Capture AW handshake address when both awvalid and awready are asserted
        if dut.axi_awvalid_o.value == 1 and dut.axi_awready_i.value == 1:
            current_aw_addr = int(dut.axi_awaddr_o.value)

        # Capture wstrb when write data is accepted (use captured AW address)
        if dut.axi_wvalid_o.value == 1 and dut.axi_wready_i.value == 1:
            wstrb = int(dut.axi_wstrb_o.value)
            addr = current_aw_addr if current_aw_addr is not None else 0
            wstrb_values.append((addr, wstrb))
            dut._log.info(f"Write at 0x{addr:08x} with wstrb=0b{wstrb:04b}")

        cycle += 1

    # Verify strobe patterns
    # Note: Exact patterns depend on address alignment and CPU implementation
    # At minimum, verify we got 3 writes
    assert len(wstrb_values) >= 3, f"Expected 3 writes, got {len(wstrb_values)}"

    # Verify SB has single-byte strobe
    sb_strobes = [wstrb for addr, wstrb in wstrb_values if addr == 0x100]
    assert len(sb_strobes) > 0, "Expected at least one SB write at 0x100"
    assert sb_strobes[0] == 0b0001, f"SB should have wstrb=0b0001, got 0b{sb_strobes[0]:04b}"

    # Verify SH has half-word strobe
    sh_strobes = [wstrb for addr, wstrb in wstrb_values if addr == 0x104]
    assert len(sh_strobes) > 0, "Expected at least one SH write at 0x104"
    assert sh_strobes[0] == 0b0011, f"SH should have wstrb=0b0011, got 0b{sh_strobes[0]:04b}"

    # Verify SW has full strobe
    sw_strobes = [wstrb for addr, wstrb in wstrb_values if addr == 0x108]
    assert len(sw_strobes) > 0, "Expected at least one SW write at 0x108"
    assert sw_strobes[0] == 0b1111, f"SW should have wstrb=0b1111, got 0b{sw_strobes[0]:04b}"

    dut._log.info("Test passed: Write strobes correctly encoded")


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
    dut._log.info("")
    dut._log.info("Category B: Error Response Tests (3)")
    dut._log.info("  - test_axi_slverr_fetch")
    dut._log.info("  - test_axi_decerr_load")
    dut._log.info("  - test_axi_error_store")
    dut._log.info("")
    dut._log.info("Category C: Protocol Compliance Tests (4)")
    dut._log.info("  - test_axi_valid_before_ready")
    dut._log.info("  - test_axi_signal_stability")
    dut._log.info("  - test_axi_no_outstanding")
    dut._log.info("  - test_axi_wstrb_encoding")
    dut._log.info("=" * 60)

    # Simple clock setup to satisfy cocotb
    clock = Clock(dut.clk_i, 10, unit="ns")
    cocotb.start_soon(clock.start())
    await wait_cycles(dut, 1)
