"""
Phase 5 M7 — Performance counter directed tests for rv32i_cpu_top.

Subtests:
  a. test_a_mcycle_increments      — mcycle advances each cycle; frozen with mcountinhibit[0]
  b. test_b_minstret_counts_retires— minstret increments once per committed instruction
  c. test_c_mcountinhibit_freeze   — inhibit[0] freezes mcycle; inhibit[2] freezes minstret
  d. test_d_hpm3_icache_miss       — mhpmcounter3 counts I-cache misses (cold-start misses)
  e. test_e_hpm4_dcache_miss       — mhpmcounter4 counts D-cache misses (cold-start load misses)
  f. test_f_hpm5_branch_mispred    — mhpmcounter5 counts branch mispredictions
  g. test_g_mimpid_phase5          — mimpid reads 0x00000005 (Phase 5 implementation ID)

Observability: all counter values are captured into GPRs via CSRRS, then read back through
the APB debug window (0x010 + reg*4). No internal RTL signals are accessed directly.

Setup strategy: each test calls _setup_perf_test(dut, program) which:
  1. Starts the 10 ns clock
  2. Initialises DUT inputs (clears stale AXI/APB/IRQ values)
  3. Creates ConfigurableAXIMemory (starts AXI handlers)
  4. Writes the program into the AXI memory dict before reset fires
     — this guarantees the CPU fetches valid instructions from address 0x0000
       even for the very first fetch after reset deasserts.
  5. Resets the DUT (rst_n_i low for 10 cycles, then deasserts)
  6. Returns (mem, dbg) for use by the caller.

This is the only difference from phase2_test_utils._setup_test: program is in memory
before reset, so no race between reset deassert and first fetch.
"""

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge

from sim.riscv_encoder import (
    ADDI,
    BNE,
    CSRRC,
    CSRRW,
    CSRRS,
    EBREAK,
    JAL,
    LW,
    SW,
)
from tb.cocotb.common.clock_reset import reset_dut
from tb.cocotb.cpu.axi_models import ConfigurableAXIMemory
from tb.cocotb.cpu.phase2_test_utils import APBDebug, _init_inputs

# ── CSR addresses (Phase 5 M7 additions) ────────────────────────────────────
CSR_MCOUNTINHIBIT = 0x320
CSR_MCYCLE        = 0xB00
CSR_MCYCLEH       = 0xB80
CSR_MINSTRET      = 0xB02
CSR_MINSTRETH     = 0xB82
CSR_MHPMCOUNTER3  = 0xB03
CSR_MHPMCOUNTER4  = 0xB04
CSR_MHPMCOUNTER5  = 0xB05
CSR_MIMPID        = 0xF13

# Inhibit mask bit positions
INHIBIT_CYCLE   = 0x01   # bit 0
INHIBIT_INSTRET = 0x04   # bit 2
INHIBIT_HPM3    = 0x08   # bit 3
INHIBIT_HPM4    = 0x10   # bit 4
INHIBIT_HPM5    = 0x20   # bit 5

# ── Helpers ──────────────────────────────────────────────────────────────────

def _prog(insns, base=0x0000):
    """Return list of (byte_addr, word) pairs for a program starting at base."""
    return [(base + i * 4, insn) for i, insn in enumerate(insns)]


async def _setup_perf_test(dut, program_insns):
    """Set up a perf-counter test: load program before reset so no cold-fetch race.

    Steps:
      1. Start 10 ns clock
      2. _init_inputs() — clear stale AXI/APB/IRQ values
      3. Create ConfigurableAXIMemory (handlers start here)
      4. Write all program words into mem.mem dict (no await — synchronous)
      5. reset_dut() — CPU resets and starts fetching; program is already in mem
      6. Yield 1 rising edge to let handler tasks settle
      7. Return (mem, dbg)

    By writing to mem.mem before the first await after creation, the Python dict
    is fully populated before the AXI read handler coroutine can serve any read
    request, guaranteeing the CPU sees valid instructions from address 0.
    """
    cocotb.start_soon(Clock(dut.clk_i, 10, units="ns").start())
    _init_inputs(dut)

    mem = ConfigurableAXIMemory(dut, ref_model=None, protocol_check=False)

    # Write program to memory dict synchronously (no await) — must happen before
    # any RisingEdge yield so the AXI handler sees the words on the first fetch.
    for addr, word in program_insns:
        mem.write_word(addr, word)

    await reset_dut(dut)
    await RisingEdge(dut.clk_i)

    dbg = APBDebug(dut)
    return mem, dbg


# ── Test a: mcycle increments ─────────────────────────────────────────────────

@cocotb.test()
async def test_a_mcycle_increments(dut):
    """mcycle advances by at least 20 when 20 NOPs run between two reads.

    Program:
      0x00: CSRRS x1, mcycle, x0   (read mcycle before; rs1=x0 → no write)
      0x04..0x50: 20x ADDI x0,x0,0 (NOPs)
      0x54: CSRRS x2, mcycle, x0   (read mcycle after)
      0x58: EBREAK
    """
    nops = [ADDI(0, 0, 0)] * 20
    program = (
        [CSRRS(1, CSR_MCYCLE, 0)]
        + nops
        + [CSRRS(2, CSR_MCYCLE, 0), EBREAK()]
    )
    mem, dbg = await _setup_perf_test(dut, _prog(program))
    await dbg.wait_halted(timeout_cycles=800)

    x1 = await dbg.read_gpr(1)
    x2 = await dbg.read_gpr(2)
    delta = (x2 - x1) & 0xFFFFFFFF

    assert x1 > 0, (
        f"mcycle before NOPs must be > 0 (reset takes several cycles), got {x1}"
    )
    assert delta >= 20, (
        f"mcycle delta after 20 NOPs must be >= 20, got {delta} "
        f"(before={x1}, after={x2})"
    )


# ── Test b: minstret counts retirements ──────────────────────────────────────

@cocotb.test()
async def test_b_minstret_counts_retires(dut):
    """minstret increments once per committed instruction.

    Program (5-iteration countdown loop):
      0x00: CSRRS x1, minstret, x0  (snapshot before)
      0x04: ADDI  x3, x0, 5
      0x08: ADDI  x3, x3, -1        (loop body, runs 5x)
      0x0C: BNE   x3, x0, -8        (taken 4x, fall-through 1x)
      0x10: CSRRS x2, minstret, x0  (snapshot after)
      0x14: EBREAK

    Between x1 and x2 (exclusive/inclusive of the second CSRRS):
      ADDI-init(1) + loop-body(5) + BNE-taken(4) + BNE-fall(1) + CSRRS-after(1) = 12
    Allow [8, 16] to tolerate pipeline-drain timing on second CSRRS.
    """
    program = [
        CSRRS(1, CSR_MINSTRET, 0),    # 0x00
        ADDI(3, 0, 5),                # 0x04
        ADDI(3, 3, -1),               # 0x08 loop body
        BNE(3, 0, -4),                # 0x0C branch back to 0x08
        CSRRS(2, CSR_MINSTRET, 0),    # 0x10
        EBREAK(),                     # 0x14
    ]
    mem, dbg = await _setup_perf_test(dut, _prog(program))
    await dbg.wait_halted(timeout_cycles=800)

    x1 = await dbg.read_gpr(1)
    x2 = await dbg.read_gpr(2)
    delta = (x2 - x1) & 0xFFFFFFFF

    assert 8 <= delta <= 16, (
        f"minstret delta for 5-iter loop expected 8..16, got {delta} "
        f"(before={x1}, after={x2})"
    )


# ── Test c: mcountinhibit freezes counters ────────────────────────────────────

@cocotb.test()
async def test_c_mcountinhibit_freeze(dut):
    """Writing mcountinhibit[0]=1 freezes mcycle; [2]=1 freezes minstret.

    Program:
      0x00: ADDI  x4, x0, 5           (INHIBIT_CYCLE | INHIBIT_INSTRET = 0x05)
      0x04: CSRRW x0, mcountinhibit, x4
      0x08: CSRRS x1, mcycle, x0      (snapshot mcycle — now frozen)
      0x0C..0x30: 10x NOP
      0x34: CSRRS x2, mcycle, x0      (re-read — should still equal x1)
      0x38: CSRRS x3, minstret, x0    (snapshot minstret — frozen)
      0x3C..0x4C: 5x NOP
      0x50: CSRRS x5, minstret, x0    (re-read — should still equal x3)
      0x54: EBREAK
    """
    inhibit_val = INHIBIT_CYCLE | INHIBIT_INSTRET   # 0x05
    program = (
        [
            ADDI(4, 0, inhibit_val),
            CSRRW(0, CSR_MCOUNTINHIBIT, 4),
            CSRRS(1, CSR_MCYCLE, 0),
        ]
        + [ADDI(0, 0, 0)] * 10
        + [
            CSRRS(2, CSR_MCYCLE, 0),
            CSRRS(3, CSR_MINSTRET, 0),
        ]
        + [ADDI(0, 0, 0)] * 5
        + [
            CSRRS(5, CSR_MINSTRET, 0),
            EBREAK(),
        ]
    )
    mem, dbg = await _setup_perf_test(dut, _prog(program))
    await dbg.wait_halted(timeout_cycles=800)

    x1 = await dbg.read_gpr(1)
    x2 = await dbg.read_gpr(2)
    x3 = await dbg.read_gpr(3)
    x5 = await dbg.read_gpr(5)

    assert x1 == x2, (
        f"mcycle must be frozen by mcountinhibit[0]: "
        f"snapshot={x1:#010x} re-read={x2:#010x}"
    )
    assert x3 == x5, (
        f"minstret must be frozen by mcountinhibit[2]: "
        f"snapshot={x3:#010x} re-read={x5:#010x}"
    )


# ── Test d: mhpmcounter3 counts I-cache misses ────────────────────────────────

@cocotb.test()
async def test_d_hpm3_icache_miss(dut):
    """mhpmcounter3 is >= 2 after executing from a cold I-cache.

    Program (24 instructions = 96 bytes = 6 I-cache lines of 16 bytes each).
    Every fetch from a cold cache line triggers one ic_miss_o pulse. We expect
    at least 2 miss pulses (likely 6 for 6 cold lines).

    mcycle and minstret are inhibited to reduce noise.
    """
    inhibit_val = INHIBIT_CYCLE | INHIBIT_INSTRET
    program = (
        [
            ADDI(4, 0, inhibit_val),
            CSRRW(0, CSR_MCOUNTINHIBIT, 4),
        ]
        + [ADDI(0, 0, 0)] * 20
        + [
            CSRRS(1, CSR_MHPMCOUNTER3, 0),
            EBREAK(),
        ]
    )
    mem, dbg = await _setup_perf_test(dut, _prog(program))
    await dbg.wait_halted(timeout_cycles=1200)

    x1 = await dbg.read_gpr(1)
    # 24 instructions span 6 cache lines of 16 bytes; each cold → 1 miss pulse.
    assert x1 >= 2, (
        f"mhpmcounter3 (I-cache misses) must be >= 2 after 24-insn cold program, "
        f"got {x1}"
    )


# ── Test e: mhpmcounter4 counts D-cache misses ────────────────────────────────

@cocotb.test()
async def test_e_hpm4_dcache_miss(dut):
    """mhpmcounter4 counts cold D-cache misses (4 LWs to 4 distinct cold lines).

    Base address 0x1000 — well above the program, within the AXI slave range.
    Each cache line is 16 bytes. Offsets 0, 16, 32, 48 hit 4 distinct lines.
    ConfigurableAXIMemory returns 0 for unwritten addresses, so LWs succeed.

    Expected: exactly 4 D-cache misses (allow [3, 5] for refill-overlap).
    """
    inhibit_val = INHIBIT_CYCLE | INHIBIT_INSTRET
    program = [
        ADDI(4, 0, inhibit_val),
        CSRRW(0, CSR_MCOUNTINHIBIT, 4),
        ADDI(6, 0, 0x100),     # x6 = 0x400 (ADDI uses sign-extend; 0x100 = 256 decimal)
        ADDI(6, 6, 0x100),     # x6 = 0x200
        ADDI(6, 6, 0x200),     # x6 = 0x400 — base address for loads
        LW(7, 6, 0),           # load from 0x400 (cold line)
        LW(7, 6, 16),          # load from 0x410 (cold line)
        LW(7, 6, 32),          # load from 0x420 (cold line)
        LW(7, 6, 48),          # load from 0x430 (cold line)
        CSRRS(1, CSR_MHPMCOUNTER4, 0),
        EBREAK(),
    ]
    mem, dbg = await _setup_perf_test(dut, _prog(program))
    await dbg.wait_halted(timeout_cycles=1200)

    x1 = await dbg.read_gpr(1)
    assert 3 <= x1 <= 5, (
        f"mhpmcounter4 (D-cache misses) expected 3..5 for 4 cold LWs, got {x1}"
    )


# ── Test f: mhpmcounter5 counts branch mispredictions ────────────────────────

@cocotb.test()
async def test_f_hpm5_branch_mispred(dut):
    """mhpmcounter5 increments on every taken branch (predict-not-taken CPU).

    4-iteration countdown loop: BNE taken 3×, fall-through 1×.
    Between baseline snapshot (x3) and post-loop snapshot (x2): delta = 3 taken branches.
    Allow [2, 5] to accommodate any branch taken during inhibit-write pipeline drain.
    """
    inhibit_val = INHIBIT_CYCLE | INHIBIT_INSTRET
    program = [
        ADDI(4, 0, inhibit_val),
        CSRRW(0, CSR_MCOUNTINHIBIT, 4),       # 0x04 freeze cycle+instret
        CSRRS(3, CSR_MHPMCOUNTER5, 0),        # 0x08 baseline
        ADDI(5, 0, 4),                        # 0x0C loop counter = 4
        ADDI(5, 5, -1),                       # 0x10 loop body
        BNE(5, 0, -4),                        # 0x14 branch back to 0x10 (taken 3×)
        CSRRS(2, CSR_MHPMCOUNTER5, 0),        # 0x18 post-loop
        EBREAK(),                             # 0x1C
    ]
    mem, dbg = await _setup_perf_test(dut, _prog(program))
    await dbg.wait_halted(timeout_cycles=800)

    x2 = await dbg.read_gpr(2)
    x3 = await dbg.read_gpr(3)
    delta = (x2 - x3) & 0xFFFFFFFF

    assert 2 <= delta <= 5, (
        f"mhpmcounter5 delta expected 2..5 for 4-iter BNE loop (3 taken), "
        f"got delta={delta} (baseline={x3}, after={x2})"
    )


# ── Test g: mimpid reads Phase 5 ID ───────────────────────────────────────────

@cocotb.test()
async def test_g_mimpid_phase5(dut):
    """mimpid CSR reads as 0x00000005 (Phase 5 implementation ID).

    CSRRS rd, csr, x0 is the canonical CSR read (rs1=x0 → no side-effect).
    """
    program = [
        CSRRS(1, CSR_MIMPID, 0),
        EBREAK(),
    ]
    mem, dbg = await _setup_perf_test(dut, _prog(program))
    await dbg.wait_halted(timeout_cycles=400)

    x1 = await dbg.read_gpr(1)
    assert x1 == 0x00000005, (
        f"mimpid must read 0x00000005 (Phase 5), got 0x{x1:08x}"
    )
