"""
Pipeline hazard tests for RV32I CPU — Phase 2

Covers spec Section 7.2 Groups 2 (data hazards) and 3 (control hazards).

All tests use the commit interface (commit_valid_o / commit_pc_o) for
progress monitoring and the APB debug interface to halt the CPU and read
GPR values for correctness checking.  No internal pipeline signals are
accessed.
"""

import cocotb

from sim.riscv_encoder import (
    ADD,
    ADDI,
    LUI,
    LW,
    SW,
    JAL,
    JALR,
    BEQ,
    BNE,
    EBREAK,
)
from tb.cocotb.cpu.phase2_test_utils import APBDebug, _init_inputs, _setup_test


# ============================================================================
# Shared helpers
# ============================================================================

NOP = ADDI(0, 0, 0)


# ============================================================================
# Group 2: Data Hazard Tests
# ============================================================================


@cocotb.test()
async def test_raw_ex_ex_forwarding(dut):
    """RAW back-to-back: EX→EX forwarding path.

    ADD x1, x0, x0 produces x1=0+0=0, but we set x1 via ADDI first,
    then immediately use it with back-to-back dependent instructions.
    x2 and x3 must see the forwarded value (42), not a stale 0.
    """
    dut._log.info("=== Test: RAW EX→EX Forwarding ===")
    mem, dbg = await _setup_test(dut)

    program = [
        ADDI(1, 0, 42),  # x1 = 42
        ADD(2, 1, 0),  # x2 = x1 + 0 = 42  (EX→EX forward for x1)
        ADD(3, 2, 0),  # x3 = x2 + 0 = 42  (EX→EX forward for x2)
        EBREAK(),  # halt CPU
    ]
    for i, insn in enumerate(program):
        mem.write_word(i * 4, insn)

    await dbg.wait_halted()

    x2 = await dbg.read_gpr(2)
    x3 = await dbg.read_gpr(3)
    assert x2 == 42, f"EX→EX forward failed: x2={x2}, expected 42"
    assert x3 == 42, f"EX→EX forward failed: x3={x3}, expected 42"
    dut._log.info(f"x2={x2}, x3={x3} — PASS")


@cocotb.test()
async def test_raw_mem_ex_forwarding(dut):
    """RAW with one-instruction gap: MEM→EX forwarding path."""
    dut._log.info("=== Test: RAW MEM→EX Forwarding ===")
    mem, dbg = await _setup_test(dut)

    program = [
        ADDI(1, 0, 55),  # x1 = 55
        ADDI(10, 0, 0),  # gap (NOP-like, unrelated register)
        ADD(2, 1, 0),  # x2 = x1 = 55  (MEM→EX forward for x1)
        EBREAK(),
    ]
    for i, insn in enumerate(program):
        mem.write_word(i * 4, insn)

    await dbg.wait_halted()

    x2 = await dbg.read_gpr(2)
    assert x2 == 55, f"MEM→EX forward failed: x2={x2}, expected 55"
    dut._log.info(f"x2={x2} — PASS")


@cocotb.test()
async def test_raw_wb_regfile_path(dut):
    """RAW with two-instruction gap: WB write completes before ID reads.

    Note: with a 2-instruction gap, the WB write completes before ID reads.
    The regfile read-before-write mechanism may cover for a broken WB→EX
    forwarding path.  End-result verification is the test philosophy here
    (no internal signal checks).
    """
    dut._log.info("=== Test: RAW WB/Regfile Path ===")
    mem, dbg = await _setup_test(dut)

    program = [
        ADDI(1, 0, 77),  # x1 = 77
        ADDI(10, 0, 0),  # gap 1
        ADDI(11, 0, 0),  # gap 2
        ADD(2, 1, 0),  # x2 = x1 = 77  (from regfile after WB)
        EBREAK(),
    ]
    for i, insn in enumerate(program):
        mem.write_word(i * 4, insn)

    await dbg.wait_halted()

    x2 = await dbg.read_gpr(2)
    assert x2 == 77, f"WB/regfile path failed: x2={x2}, expected 77"
    dut._log.info(f"x2={x2} — PASS")


@cocotb.test()
async def test_load_use_stall(dut):
    """Load-use hazard: LW immediately followed by dependent instruction.

    The hazard unit must insert 1 stall cycle.  The result must be correct
    despite the stall.
    """
    dut._log.info("=== Test: Load-Use Stall ===")
    mem, dbg = await _setup_test(dut)

    DATA_ADDR = 0x1000
    mem.write_word(DATA_ADDR, 100)  # pre-load data memory

    program = [
        LUI(1, 1),  # x1 = 0x1000
        LW(3, 1, 0),  # x3 = mem[0x1000] = 100
        ADD(4, 3, 0),  # x4 = x3  (load-use: 1 stall required)
        EBREAK(),
    ]
    for i, insn in enumerate(program):
        mem.write_word(i * 4, insn)

    await dbg.wait_halted()

    x3 = await dbg.read_gpr(3)
    x4 = await dbg.read_gpr(4)
    assert x3 == 100, f"Load result wrong: x3={x3}, expected 100"
    assert x4 == 100, f"Load-use stall failed: x4={x4}, expected 100"
    dut._log.info(f"x3={x3}, x4={x4} — PASS")


@cocotb.test()
async def test_load_no_stall_with_gap(dut):
    """Load followed by NOP then dependent instruction — no stall needed."""
    dut._log.info("=== Test: Load With NOP Gap (No Stall) ===")
    mem, dbg = await _setup_test(dut)

    DATA_ADDR = 0x1000
    mem.write_word(DATA_ADDR, 200)

    program = [
        LUI(1, 1),  # x1 = 0x1000
        LW(3, 1, 0),  # x3 = 200
        NOP,  # gap — MEM→EX forwarding covers this
        ADD(4, 3, 0),  # x4 = x3 = 200 (no stall needed)
        EBREAK(),
    ]
    for i, insn in enumerate(program):
        mem.write_word(i * 4, insn)

    await dbg.wait_halted()

    x4 = await dbg.read_gpr(4)
    assert x4 == 200, f"Load+gap path failed: x4={x4}, expected 200"
    dut._log.info(f"x4={x4} — PASS")


@cocotb.test()
async def test_store_after_load_forwarding(dut):
    """Store data forwarded from load result (load-use → store path)."""
    dut._log.info("=== Test: Store After Load Forwarding ===")
    mem, dbg = await _setup_test(dut)

    DATA_ADDR = 0x1000
    mem.write_word(DATA_ADDR, 999)

    # LW x3, 0(x1); SW x3, 4(x1) — store data must be forwarded
    program = [
        LUI(1, 1),  # x1 = 0x1000
        LW(3, 1, 0),  # x3 = 999
        SW(3, 1, 4),  # mem[0x1004] = x3 (fwd from load)
        LW(4, 1, 4),  # x4 = mem[0x1004] = 999 (verify)
        EBREAK(),
    ]
    for i, insn in enumerate(program):
        mem.write_word(i * 4, insn)

    await dbg.wait_halted()

    x4 = await dbg.read_gpr(4)
    assert x4 == 999, f"Store-after-load fwd failed: x4={x4}, expected 999"
    dut._log.info(f"x4={x4} — PASS")


@cocotb.test()
async def test_x0_forwarding(dut):
    """Write to x0 must not affect x0 (hardwired zero).

    ADD x0, x1, x2 must not update x0; subsequent read of x0 is still 0.
    """
    dut._log.info("=== Test: x0 Always Zero (Forwarding) ===")
    mem, dbg = await _setup_test(dut)

    program = [
        ADDI(1, 0, 50),  # x1 = 50
        ADD(0, 1, 1),  # x0 = 100 (should be discarded)
        ADD(2, 0, 1),  # x2 = x0 + x1 = 0 + 50 = 50 (x0 is still 0)
        EBREAK(),
    ]
    for i, insn in enumerate(program):
        mem.write_word(i * 4, insn)

    await dbg.wait_halted()

    x2 = await dbg.read_gpr(2)
    assert x2 == 50, f"x0 forwarding bug: x2={x2}, expected 50 (not 100)"
    dut._log.info(f"x2={x2} — PASS")


@cocotb.test()
async def test_multi_dependency_same_source(dut):
    """Both ALU operands forwarded from the same prior instruction."""
    dut._log.info("=== Test: Multi-Dependency (Both Ops Forwarded) ===")
    mem, dbg = await _setup_test(dut)

    program = [
        ADDI(1, 0, 7),  # x1 = 7
        ADD(2, 1, 1),  # x2 = x1 + x1 = 14  (both ops EX→EX forwarded)
        EBREAK(),
    ]
    for i, insn in enumerate(program):
        mem.write_word(i * 4, insn)

    await dbg.wait_halted()

    x2 = await dbg.read_gpr(2)
    assert x2 == 14, f"Multi-dep forwarding failed: x2={x2}, expected 14"
    dut._log.info(f"x2={x2} — PASS")


# ============================================================================
# Group 3: Control Hazard Tests
# ============================================================================


@cocotb.test()
async def test_branch_taken_flush(dut):
    """Branch taken: 2-cycle flush; instructions in IF and ID are squashed."""
    dut._log.info("=== Test: Branch Taken Flush ===")
    mem, dbg = await _setup_test(dut)

    # Layout:
    #   0x00: ADDI x1, x0, 5
    #   0x04: ADDI x2, x0, 5
    #   0x08: BEQ x1, x2, +16  (taken → 0x18)
    #   0x0C: ADDI x3, x0, 99  (flushed by branch)
    #   0x10: ADDI x3, x0, 99  (flushed by branch)
    #   0x14: ADDI x3, x0, 99  (should NOT execute)
    #   0x18: ADDI x4, x0, 42  (branch target — must execute)
    #   0x1C: EBREAK
    program = [
        ADDI(1, 0, 5),  # 0x00
        ADDI(2, 0, 5),  # 0x04
        BEQ(1, 2, 16),  # 0x08 → taken → 0x18
        ADDI(3, 0, 99),  # 0x0C — flushed
        ADDI(3, 0, 99),  # 0x10 — flushed
        ADDI(3, 0, 99),  # 0x14 — should not run
        ADDI(4, 0, 42),  # 0x18 — branch target
        EBREAK(),  # 0x1C
    ]
    for i, insn in enumerate(program):
        mem.write_word(i * 4, insn)

    await dbg.wait_halted()

    x3 = await dbg.read_gpr(3)
    x4 = await dbg.read_gpr(4)
    assert x3 == 0, f"Branch flush failed: x3={x3}, expected 0 (flushed)"
    assert x4 == 42, f"Branch target failed: x4={x4}, expected 42"
    dut._log.info(f"x3={x3}, x4={x4} — PASS")


@cocotb.test()
async def test_branch_not_taken(dut):
    """Branch not taken: no flush; sequential execution continues."""
    dut._log.info("=== Test: Branch Not Taken ===")
    mem, dbg = await _setup_test(dut)

    program = [
        ADDI(1, 0, 3),  # x1 = 3
        ADDI(2, 0, 7),  # x2 = 7
        BEQ(1, 2, 16),  # not taken (3 ≠ 7)
        ADDI(3, 0, 42),  # sequential — must execute
        EBREAK(),
    ]
    for i, insn in enumerate(program):
        mem.write_word(i * 4, insn)

    await dbg.wait_halted()

    x3 = await dbg.read_gpr(3)
    assert x3 == 42, f"Branch not-taken failed: x3={x3}, expected 42"
    dut._log.info(f"x3={x3} — PASS")


@cocotb.test()
async def test_branch_with_raw_hazard(dut):
    """Branch comparator receives forwarded value (RAW hazard into branch).

    ADDI x1 → ADD x2 (depends on x1) → BEQ x2, x1 (branch using forwarded x2).
    Branch should be TAKEN because forwarding delivers the correct x2.
    """
    dut._log.info("=== Test: Branch With RAW Hazard ===")
    mem, dbg = await _setup_test(dut)

    # Layout:
    #   0x00: ADDI x1, x0, 10
    #   0x04: ADD  x2, x1, x0   (x2 = x1 via EX→EX/MEM→EX forward)
    #   0x08: BEQ  x2, x1, +12  (taken if x2==x1==10; 1 instr gap → MEM→EX)
    #   0x0C: ADDI x3, x0, 99   (flushed)
    #   0x10: ADDI x3, x0, 99   (flushed)
    #   0x14: ADDI x4, x0, 77   (branch target)
    #   0x18: EBREAK
    program = [
        ADDI(1, 0, 10),  # 0x00
        ADD(2, 1, 0),  # 0x04
        BEQ(2, 1, 12),  # 0x08 → taken if forwarding is correct
        ADDI(3, 0, 99),  # 0x0C — flushed
        ADDI(3, 0, 99),  # 0x10 — flushed
        ADDI(4, 0, 77),  # 0x14 — branch target
        EBREAK(),  # 0x18
    ]
    for i, insn in enumerate(program):
        mem.write_word(i * 4, insn)

    await dbg.wait_halted()

    x3 = await dbg.read_gpr(3)
    x4 = await dbg.read_gpr(4)
    assert x3 == 0, f"RAW→branch flush failed: x3={x3}, expected 0 (flushed)"
    assert x4 == 77, f"RAW→branch target failed: x4={x4}, expected 77"
    dut._log.info(f"x3={x3}, x4={x4} — PASS")


@cocotb.test()
async def test_jal_flush(dut):
    """JAL: 1-cycle flush (only the next fetched instruction is squashed)."""
    dut._log.info("=== Test: JAL 1-Cycle Flush ===")
    mem, dbg = await _setup_test(dut)

    # Layout:
    #   0x00: JAL x1, +12  (→ 0x0C; x1 = 0x04)
    #   0x04: ADDI x2, x0, 99  (fetched concurrently, must be flushed)
    #   0x08: ADDI x2, x0, 99  (not fetched — beyond the single flush)
    #   0x0C: ADDI x3, x0, 42  (jump target)
    #   0x10: EBREAK
    program = [
        JAL(1, 12),  # 0x00 → 0x0C; x1=0x04
        ADDI(2, 0, 99),  # 0x04 — flushed (was in IF when JAL resolved)
        ADDI(2, 0, 99),  # 0x08 — not reached
        ADDI(3, 0, 42),  # 0x0C — target
        EBREAK(),  # 0x10
    ]
    for i, insn in enumerate(program):
        mem.write_word(i * 4, insn)

    await dbg.wait_halted()

    x1 = await dbg.read_gpr(1)
    x2 = await dbg.read_gpr(2)
    x3 = await dbg.read_gpr(3)
    assert x1 == 0x4, f"JAL link addr wrong: x1=0x{x1:x}, expected 0x4"
    assert x2 == 0, f"JAL flush failed: x2={x2}, expected 0 (flushed)"
    assert x3 == 42, f"JAL target failed: x3={x3}, expected 42"
    dut._log.info(f"x1=0x{x1:x}, x2={x2}, x3={x3} — PASS")


@cocotb.test()
async def test_jalr_flush(dut):
    """JALR: 2-cycle flush (EX stage resolution, flushes IF and ID)."""
    dut._log.info("=== Test: JALR 2-Cycle Flush ===")
    mem, dbg = await _setup_test(dut)

    HANDLER = 0x40  # jump target
    # Layout:
    #   0x00: ADDI x1, x0, 0x40   (x1 = HANDLER address)
    #   0x04: JALR x2, x1, 0      (→ 0x40; x2 = 0x08)
    #   0x08: ADDI x3, x0, 99     (flushed — in ID when JALR in EX)
    #   0x0C: ADDI x3, x0, 99     (flushed — in IF when JALR in EX)
    #   0x40: ADDI x4, x0, 88     (jump target)
    #   0x44: EBREAK
    program_base = [
        ADDI(1, 0, HANDLER),  # 0x00
        JALR(2, 1, 0),  # 0x04 → 0x40; x2=0x08
        ADDI(3, 0, 99),  # 0x08 — flushed
        ADDI(3, 0, 99),  # 0x0C — flushed
    ]
    for i, insn in enumerate(program_base):
        mem.write_word(i * 4, insn)

    # Handler at 0x40
    mem.write_word(HANDLER + 0, ADDI(4, 0, 88))
    mem.write_word(HANDLER + 4, EBREAK())

    await dbg.wait_halted()

    x2 = await dbg.read_gpr(2)
    x3 = await dbg.read_gpr(3)
    x4 = await dbg.read_gpr(4)
    assert x2 == 0x8, f"JALR link addr wrong: x2=0x{x2:x}, expected 0x8"
    assert x3 == 0, f"JALR 2-cycle flush failed: x3={x3}, expected 0"
    assert x4 == 88, f"JALR target failed: x4={x4}, expected 88"
    dut._log.info(f"x2=0x{x2:x}, x3={x3}, x4={x4} — PASS")


@cocotb.test()
async def test_consecutive_branches(dut):
    """Back-to-back branches: each taken branch flushes and refetches correctly."""
    dut._log.info("=== Test: Consecutive Branches ===")
    mem, dbg = await _setup_test(dut)

    # Layout:
    #   0x00: ADDI x1, x0, 1
    #   0x04: ADDI x2, x0, 2
    #   0x08: BEQ x1, x1, +16   (always taken → 0x18)
    #   0x0C: ADDI x3, x0, 99   (flushed)
    #   0x10: ADDI x3, x0, 99   (flushed)
    #   0x14: ADDI x3, x0, 99   (not reached)
    #   0x18: BNE x1, x2, +16   (taken, 1≠2 → 0x28)
    #   0x1C: ADDI x4, x0, 99   (flushed)
    #   0x20: ADDI x4, x0, 99   (flushed)
    #   0x24: ADDI x4, x0, 99   (not reached)
    #   0x28: ADDI x5, x0, 77   (final target)
    #   0x2C: EBREAK
    program = [
        ADDI(1, 0, 1),  # 0x00
        ADDI(2, 0, 2),  # 0x04
        BEQ(1, 1, 16),  # 0x08 → 0x18 (always taken: x1==x1)
        ADDI(3, 0, 99),  # 0x0C — flushed
        ADDI(3, 0, 99),  # 0x10 — flushed
        ADDI(3, 0, 99),  # 0x14 — not reached
        BNE(1, 2, 16),  # 0x18 → 0x28 (taken: 1≠2)
        ADDI(4, 0, 99),  # 0x1C — flushed
        ADDI(4, 0, 99),  # 0x20 — flushed
        ADDI(4, 0, 99),  # 0x24 — not reached
        ADDI(5, 0, 77),  # 0x28 — final target
        EBREAK(),  # 0x2C
    ]
    for i, insn in enumerate(program):
        mem.write_word(i * 4, insn)

    await dbg.wait_halted()

    x3 = await dbg.read_gpr(3)
    x4 = await dbg.read_gpr(4)
    x5 = await dbg.read_gpr(5)
    assert x3 == 0, f"Branch 1 flush failed: x3={x3}, expected 0"
    assert x4 == 0, f"Branch 2 flush failed: x4={x4}, expected 0"
    assert x5 == 77, f"Final target failed: x5={x5}, expected 77"
    dut._log.info(f"x3={x3}, x4={x4}, x5={x5} — PASS")


@cocotb.test()
async def test_back_to_back_stores(dut):
    """Back-to-back SW instructions complete without stall (Group 2, item 7).

    SW x1, 0(x0); SW x2, 4(x0) — both stores must complete correctly.
    Verify by loading the stored values back and checking results.
    """
    dut._log.info("=== Test: Back-to-Back Stores ===")
    mem, dbg = await _setup_test(dut)

    DATA_ADDR = 0x1000
    program = [
        ADDI(1, 0, 11),  # x1 = 11
        ADDI(2, 0, 22),  # x2 = 22
        LUI(5, DATA_ADDR >> 12),  # x5 = 0x1000
        SW(1, 5, 0),  # mem[0x1000] = 11
        SW(2, 5, 4),  # mem[0x1004] = 22  (back-to-back store)
        LW(3, 5, 0),  # x3 = mem[0x1000] = 11
        LW(4, 5, 4),  # x4 = mem[0x1004] = 22
        EBREAK(),
    ]
    for i, insn in enumerate(program):
        mem.write_word(i * 4, insn)

    await dbg.wait_halted()

    x3 = await dbg.read_gpr(3)
    x4 = await dbg.read_gpr(4)
    assert x3 == 11, f"First store lost: x3={x3}, expected 11"
    assert x4 == 22, f"Second store lost: x4={x4}, expected 22"
    dut._log.info(f"x3={x3}, x4={x4} — PASS")


@cocotb.test()
async def test_jal_rd_dependency(dut):
    """JAL link register is available to the immediately following instruction (Group 3, item 7).

    JAL x1, +8  writes return address (0x4) to x1.
    ADDI x2, x1, 0  must read the forwarded x1 (not stale 0).
    x2 must equal 0x4 (the JAL link address).
    """
    dut._log.info("=== Test: JAL rd Dependency ===")
    mem, dbg = await _setup_test(dut)

    # Layout:
    #   0x00: JAL x1, +8   (x1 = 0x04, jump to 0x08)
    #   0x04: ---           (flushed — in IF when JAL resolved)
    #   0x08: ADDI x2, x1, 0   (x2 = x1 = 0x04; JAL rd forwarded)
    #   0x0C: EBREAK
    program = [
        JAL(1, 8),  # 0x00 → 0x08; x1 = 0x04
        NOP,  # 0x04 — flushed
        ADDI(2, 1, 0),  # 0x08 — x2 = x1 = 0x04
        EBREAK(),  # 0x0C
    ]
    for i, insn in enumerate(program):
        mem.write_word(i * 4, insn)

    await dbg.wait_halted()

    x1 = await dbg.read_gpr(1)
    x2 = await dbg.read_gpr(2)
    assert x1 == 0x4, f"JAL link addr wrong: x1=0x{x1:x}, expected 0x4"
    assert x2 == 0x4, f"JAL rd dependency failed: x2=0x{x2:x}, expected 0x4"
    dut._log.info(f"x1=0x{x1:x}, x2=0x{x2:x} — PASS")
