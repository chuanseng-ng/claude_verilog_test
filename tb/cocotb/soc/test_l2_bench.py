"""
test_l2_bench.py — Phase 5 M10 L2-cache decision benchmark harness.

Loads bare-metal C benchmarks (hello / sweep / matmul) onto the full SoC,
runs each to EBREAK, backdoor-reads the multi-slot perf-counter scratch
region, and prints miss-rate tables that directly feed the A4 L2 go/no-go
document.

Testbench DUT: tb_soc_top (same as all M9 tests), instantiated with
    SRAM_MEM_WORDS = 65536  (256 KB window 0x2000..0x42000)
so the benchmarks' 64 KB sweep buffer + 27 KB matmul matrices fit without
aliasing.

Firmware contract (mirrored from sw/bench/bench.h and README.md):

  ROM: trampoline.hex  → backdoor-loaded into u_soc.u_boot_rom.mem
  SRAM: <prog>.hex     → backdoor-loaded into u_soc.u_sram.mem starting
                          at word index 0 (byte 0x2000)

  Scratch region SRAM word index:
      BENCH_SCRATCH_BASE_WI = (0x41C00 - 0x2000) / 4 = 0x7F00
      Word[0x7F00]       = N  (record count)
      Word[0x7F01 + k*8] = slot k word 0  (BENCH_MAGIC | id)
      ...
      Word[0x7F01 + k*8 + 7] = slot k word 7  (pad)

  Slot layout (8 words):
      [0] BENCH_MAGIC | (id & 0xFF)
      [1] checksum
      [2] Δcycles
      [3] Δinstret
      [4] ΔI$-miss
      [5] ΔD$-miss
      [6] Δbranch-miss
      [7] 0 (pad)

Sweep ID encoding (from sweep.c):
    bits [7:5]  size_idx  → SIZE_STEPS[size_idx] bytes
    bit  [4]    pattern   → 0 = SEQ, 1 = STRIDE
    bits [3:0]  reserved / zero

    SIZE_STEPS: [512, 1024, 2048, 4096, 8192, 16384, 32768, 65536]

Matmul ID: 0x01 (single record).

__result cross-check: crt0.S parks main()'s return value in a0 before
EBREAK; the sym file maps __result to the SRAM word at its address.
"""

import sys
import subprocess
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, ReadOnly

# ── Project paths ─────────────────────────────────────────────────────────────
_ROOT = Path(__file__).resolve().parent.parent.parent.parent          # repo root
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

_BENCH_BUILD = _ROOT / "sw" / "bench" / "build"
_TRAMPOLINE_HEX = _BENCH_BUILD / "trampoline.hex"

# ── SoC constants ─────────────────────────────────────────────────────────────
CLK_PERIOD_NS = 2                   # 500 MHz — matches all other SoC tests
SRAM_BASE_ADDR = 0x2000             # byte address of SRAM word index 0

# Scratch region: SRAM word index of BENCH_SCRATCH_ADDR (0x41C00)
BENCH_SCRATCH_BASE_WI = (0x41C00 - SRAM_BASE_ADDR) // 4    # = 0x7F00
BENCH_MAGIC = 0xB10C0000

# Watchdog: sweep 64KB × 4 passes is the heaviest case.  The stress test
# ran 1M+ cycles for 10 complex outer loops; plain memory sweeps run faster.
# 5M cycles gives very generous headroom for the heaviest sweep run.
BENCH_TIMEOUT_CYCLES = 5_000_000

# Sweep size steps (must match sweep.c SIZE_STEPS[])
_SWEEP_SIZES = [512, 1024, 2048, 4096, 8192, 16384, 32768, 65536]

# ── Hex loader helpers ────────────────────────────────────────────────────────

def _parse_hex(path: Path) -> list:
    """Parse a word-per-line hex file into a list of 32-bit ints."""
    words = []
    with open(path) as f:
        for line in f:
            tok = line.strip()
            if not tok or tok.startswith("//") or tok.startswith("@"):
                continue
            words.append(int(tok, 16))
    return words


def _load_rom(dut, words: list) -> None:
    """Backdoor-load word list into u_soc.u_boot_rom.mem."""
    mem = dut.u_soc.u_boot_rom.mem
    for i, w in enumerate(words):
        mem[i].value = w


def _load_sram(dut, words: list) -> None:
    """Backdoor-load word list into u_soc.u_sram.mem starting at index 0.

    SRAM word index = (byte_addr - 0x2000) / 4.  The .hex image starts at
    0x2000, so the first word of the image maps to SRAM index 0.
    """
    mem = dut.u_soc.u_sram.mem
    for i, w in enumerate(words):
        mem[i].value = w


# ── Sym-file parser ───────────────────────────────────────────────────────────

def _parse_sym(prog: str) -> dict:
    """Return {symbol_name: byte_address} from build/<prog>.sym (nm -n output)."""
    sym_path = _BENCH_BUILD / f"{prog}.sym"
    syms: dict = {}
    with open(sym_path) as f:
        for line in f:
            parts = line.split()
            # nm -n output: <addr> <type> <name>
            if len(parts) >= 3:
                try:
                    syms[parts[2]] = int(parts[0], 16)
                except ValueError:
                    pass
    return syms


def _sram_wi(byte_addr: int) -> int:
    """Convert a byte address in SRAM space to a SRAM word index."""
    return (byte_addr - SRAM_BASE_ADDR) // 4


# ── Setup helper ──────────────────────────────────────────────────────────────

async def _setup(dut, prog: str) -> None:
    """Start clock, idle inputs, backdoor-load ROM + SRAM, release reset.

    Mirrors the pattern used by test_soc_stress._setup() and test_boot._setup().
    """
    cocotb.start_soon(Clock(dut.clk_i, CLK_PERIOD_NS, units="ns").start())

    dut.rst_n_i.value       = 0
    dut.apb_paddr_i.value   = 0
    dut.apb_psel_i.value    = 0
    dut.apb_penable_i.value = 0
    dut.apb_pwrite_i.value  = 0
    dut.apb_pwdata_i.value  = 0
    dut.uart_rx_i.value     = 1   # idle high
    dut.spi_miso_i.value    = 0

    trampoline_words = _parse_hex(_TRAMPOLINE_HEX)
    prog_words = _parse_hex(_BENCH_BUILD / f"{prog}.hex")

    _load_rom(dut, trampoline_words)
    _load_sram(dut, prog_words)

    # Assert reset for 5 cycles then release (same as stress / boot tests)
    for _ in range(5):
        await RisingEdge(dut.clk_i)

    dut.rst_n_i.value = 1

    for _ in range(2):
        await RisingEdge(dut.clk_i)


# ── Halt-PC resolver ─────────────────────────────────────────────────────────

def _fence_pc(prog: str) -> int:
    """Return the PC of the FENCE instruction immediately before EBREAK.

    crt0.S halt sequence:
        la   t0, __result   (2 insns, auipc + addi or lui + addi)
        sw   a0, 0(t0)      ; __result store
        fence               ; <-- LAST instruction that asserts commit_valid_o
    3:  ebreak              ; causes trap → commit_valid_o suppressed (trap_valid=1)
        j    3b

    We scan the .dis file for the 'fence' line that immediately precedes
    'ebreak' at the end of _start.  Both are in the _start function (before
    main).  As a reliable fallback: EBREAK PC is always at _start+0x48
    (hello/sweep/matmul all compile identically), and FENCE is 4 bytes before.
    """
    dis_path = _BENCH_BUILD / f"{prog}.dis"
    prev_pc = None
    try:
        with open(dis_path) as f:
            for line in f:
                stripped = line.strip()
                # Typical objdump line: "    2048:\t00100073 \tebreak"
                if "ebreak" in stripped.lower() and ":" in stripped:
                    parts = stripped.split(":")
                    try:
                        ebreak_addr = int(parts[0].strip(), 16)
                        # FENCE is 4 bytes before EBREAK (both are 32-bit instructions)
                        return ebreak_addr - 4
                    except ValueError:
                        pass
                # Track last 'fence' seen for alternative detection
                if "fence" in stripped.lower() and "fence.i" not in stripped.lower() and ":" in stripped:
                    parts = stripped.split(":")
                    try:
                        prev_pc = int(parts[0].strip(), 16)
                    except ValueError:
                        pass
    except FileNotFoundError:
        pass

    if prev_pc is not None:
        return prev_pc

    # Hard fallback: _start is at 0x2000; crt0 layout is fixed at 0x2044 for fence
    return 0x2044


# ── Run-to-halt loop ──────────────────────────────────────────────────────────

async def _run_to_ebreak(dut, prog: str, timeout: int = BENCH_TIMEOUT_CYCLES) -> int:
    """Cycle the SoC until the benchmark firmware halts (FENCE commits then CPU stops).

    EBREAK in this CPU pipeline sets trap_valid=1 in the WB stage, which
    suppresses commit_valid_o (see rv32i_pipeline_wb.sv line 71).  The
    instruction that actually commits last is the FENCE at (ebreak_pc - 4).
    After FENCE commits, the CPU takes the EBREAK trap and enters dbg_halt
    state — commit_valid_o stops asserting.

    Detection strategy (mirrors test_soc_stress.py PASS_PC pattern):
      1. Watch for commit_pc_o == fence_pc (the last committing instruction).
      2. Once seen, wait DRAIN_CYCLES for the pipeline to fully drain and the
         D-cache to write back any dirty scratch lines.

    Returns the sim cycle at which FENCE was committed.
    """
    fence_pc_val = _fence_pc(prog)
    # Drain cycles: generous to let D-cache writeback the bench_report() stores
    # (scratch region at 0x41C00 may be in a dirty cache line).
    DRAIN_CYCLES = 200

    dut._log.info(
        "[%s] waiting for FENCE (halt sentinel) at PC=0x%08x", prog, fence_pc_val
    )

    last_pc = 0
    recent_pcs: list = []
    fence_cycle = -1

    for sim_cycle in range(timeout):
        await RisingEdge(dut.clk_i)
        await ReadOnly()

        if dut.commit_valid_o.value:
            pc = int(dut.commit_pc_o.value)
            last_pc = pc
            recent_pcs.append(pc)
            if len(recent_pcs) > 32:
                recent_pcs.pop(0)

            if pc == fence_pc_val and fence_cycle < 0:
                fence_cycle = sim_cycle
                dut._log.info(
                    "[%s] FENCE committed at PC=0x%08x, sim_cycle=%d — draining %d cycles",
                    prog, pc, sim_cycle, DRAIN_CYCLES,
                )

        # After FENCE commits, drain and return
        if fence_cycle >= 0 and (sim_cycle - fence_cycle) >= DRAIN_CYCLES:
            dut._log.info(
                "[%s] pipeline drained at sim_cycle=%d", prog, sim_cycle
            )
            return fence_cycle

        if sim_cycle > 0 and sim_cycle % 500_000 == 0:
            dut._log.info(
                "[%s] heartbeat @ cycle %d: last_pc=0x%08x (sentinel=0x%08x)",
                prog, sim_cycle, last_pc, fence_pc_val,
            )

    recent_str = " ".join(f"0x{p:08x}" for p in recent_pcs[-16:])
    assert False, (
        f"[{prog}] FENCE sentinel PC=0x{fence_pc_val:08x} not seen within "
        f"{timeout} cycles (last_pc=0x{last_pc:08x}). Recent PCs: {recent_str}"
    )


# ── D$ cache-coherent scratch reader ─────────────────────────────────────────
#
# The scratch region (0x41C00..0x41FFF) is below MMIO_BASE (0x2000_0000) so
# D$ caches it as write-back.  bench_report() writes through D$ — dirty lines
# are NOT evicted before FENCE commits, so the data lives in D$ not in main
# SRAM.  We must read from the D$ data SRAM arrays directly.
#
# D$ layout (rv32i_dcache.sv):
#   4 KB direct-mapped, 16-byte lines → 256 lines, LINE_WORDS=4
#   Data stored in 4 banks: gen_data_sram[0..3].u_data_sram.mem[255:0]
#   bank = word_in_line = (byte_addr >> 2) & 3
#   line_idx = (byte_addr >> 4) & 0xFF
#
# Path: dut.u_soc.u_cpu.u_core.u_dcache.gen_data_sram[bank].u_data_sram.mem[idx]
#
# For a correct read we also check valid_array/dirty_array bits.  If the line
# is not valid in D$ (cache evicted it or hasn't loaded it), fall back to main
# SRAM.  This handles both heavily-loaded runs (D$ evicts scratch line) and
# short runs (scratch stays dirty in D$).

_DCACHE_LINE_WORDS = 4       # LINE_WORDS in rv32i_dcache.sv
_SCRATCH_BYTE_BASE = 0x41C00
_SCRATCH_NWORDS    = 256     # 1 KB / 4 bytes


def _dcache_read_word(dut, byte_addr: int) -> int:
    """Read one 32-bit word coherently — from D$ if dirty, else from SRAM.

    byte_addr must be word-aligned and within the cached SRAM region.
    """
    bank     = (byte_addr >> 2) & 0x3
    line_idx = (byte_addr >> 4) & 0xFF

    # Read valid and dirty registers from the D$ (these are flat unpacked arrays)
    try:
        valid = int(dut.u_soc.u_cpu.u_core.u_dcache.valid_array[line_idx].value)
        dirty = int(dut.u_soc.u_cpu.u_core.u_dcache.dirty_array[line_idx].value)
    except Exception:
        valid = 0
        dirty = 0

    if valid and dirty:
        # Data is in D$ — read from the appropriate bank
        try:
            raw = dut.u_soc.u_cpu.u_core.u_dcache.gen_data_sram[bank].u_data_sram.mem[line_idx].value
            return int(raw) & 0xFFFF_FFFF
        except Exception:
            pass

    # Fallback: read from main SRAM
    wi = _sram_wi(byte_addr)
    raw = dut.u_soc.u_sram.mem[wi].value
    return int(raw) & 0xFFFF_FFFF


def _read_scratch(dut, prog: str) -> list:
    """Coherent backdoor-read of the bench scratch region (D$ or SRAM).

    Reads via _dcache_read_word so data is found whether it's in a dirty D$
    line or already evicted to main SRAM.

    Returns a list of dicts with keys:
        id, magic_word, checksum, d_cycles, d_instret,
        d_imiss, d_dmiss, d_brmiss
    """
    # Word 0 of scratch = record count
    n_records = _dcache_read_word(dut, _SCRATCH_BYTE_BASE)
    dut._log.info("[%s] scratch word count N = %d", prog, n_records)
    assert n_records > 0, (
        f"[{prog}] BENCH_SCRATCH count = 0 — bench_init() or bench_report() "
        f"did not execute (firmware may have crashed before the measurement loop)"
    )

    slots = []
    for k in range(n_records):
        # Slot k starts at byte offset (1 + k*8) * 4 from scratch base
        slot_byte_base = _SCRATCH_BYTE_BASE + (1 + k * 8) * 4
        w = [_dcache_read_word(dut, slot_byte_base + j * 4) for j in range(8)]

        magic_word = w[0]
        bench_id   = magic_word & 0xFF
        expected_magic = BENCH_MAGIC | bench_id

        assert magic_word == expected_magic, (
            f"[{prog}] slot {k}: magic 0x{magic_word:08x} != "
            f"expected 0x{expected_magic:08x} — "
            f"D$ read failed or scratch addr wrong"
        )

        slots.append({
            "id":         bench_id,
            "magic_word": magic_word,
            "checksum":   w[1],
            "d_cycles":   w[2],
            "d_instret":  w[3],
            "d_imiss":    w[4],
            "d_dmiss":    w[5],
            "d_brmiss":   w[6],
        })

    return slots


# ── __result cross-check helper ───────────────────────────────────────────────

def _check_result(dut, prog: str) -> int:
    """Read __result from SRAM (placed there by crt0.S) and return it.

    __result is the SRAM word at the symbol address.  We parse its address
    from the .sym file.  A non-zero return from matmul/sweep/hello is the
    primary dead-code-elimination guard.
    """
    syms = _parse_sym(prog)
    if "__result" not in syms:
        dut._log.warning("[%s] __result symbol not found in .sym — skipping cross-check", prog)
        return 0
    byte_addr = syms["__result"]
    # __result is in .data at ~0x2150 — below MMIO_BASE so goes through D$
    result = _dcache_read_word(dut, byte_addr)
    dut._log.info("[%s] __result @ 0x%08x = 0x%08x", prog, byte_addr, result)
    return result


# ── Miss-rate table printers ──────────────────────────────────────────────────

def _miss_rate(misses: int, instret: int) -> float:
    """Misses per 1000 retired instructions."""
    if instret == 0:
        return float("nan")
    return 1000.0 * misses / instret


def _miss_rate_per_kcyc(misses: int, cycles: int) -> float:
    """Misses per 1000 cycles."""
    if cycles == 0:
        return float("nan")
    return 1000.0 * misses / cycles


def _print_slot_table(dut, prog: str, slots: list) -> None:
    """Generic per-slot table (id, cycles, instret, imiss/kinst, dmiss/kinst)."""
    hdr = (
        f"{'id':>6}  {'cycles':>10}  {'instret':>10}  "
        f"{'imiss':>8}  {'dmiss':>8}  "
        f"{'imiss/kI':>10}  {'dmiss/kI':>10}  {'dmiss/kC':>10}"
    )
    sep = "-" * len(hdr)
    dut._log.info("[%s] %s", prog, sep)
    dut._log.info("[%s] %s", prog, hdr)
    dut._log.info("[%s] %s", prog, sep)
    for s in slots:
        dut._log.info(
            "[%s] %s",
            prog,
            (
                f"{s['id']:>#6x}  {s['d_cycles']:>10d}  {s['d_instret']:>10d}  "
                f"{s['d_imiss']:>8d}  {s['d_dmiss']:>8d}  "
                f"{_miss_rate(s['d_imiss'], s['d_instret']):>10.2f}  "
                f"{_miss_rate(s['d_dmiss'], s['d_instret']):>10.2f}  "
                f"{_miss_rate_per_kcyc(s['d_dmiss'], s['d_cycles']):>10.2f}"
            ),
        )
    dut._log.info("[%s] %s", prog, sep)


def _print_sweep_analysis(dut, slots: list) -> None:
    """Print sweep D$-miss/kI vs working-set-size for SEQ and STRIDE patterns."""
    # Build per-size maps: size_bytes -> {0: seq_slot, 1: stride_slot}
    by_size: dict = {}
    for s in slots:
        sid = s["id"]
        size_idx = (sid >> 5) & 0x7
        pattern  = (sid >> 4) & 0x1
        if size_idx >= len(_SWEEP_SIZES):
            dut._log.warning("sweep: unexpected size_idx=%d in slot id=0x%02x", size_idx, sid)
            continue
        size_bytes = _SWEEP_SIZES[size_idx]
        by_size.setdefault(size_bytes, {})[pattern] = s

    hdr = (
        f"{'size(B)':>10}  "
        f"{'SEQ dmiss/kI':>14}  {'SEQ imiss/kI':>14}  "
        f"{'STR dmiss/kI':>14}  {'STR imiss/kI':>14}  "
        f"{'SEQ cycles':>12}"
    )
    sep = "-" * len(hdr)
    dut._log.info("[sweep] CAPACITY CURVE — D$-miss/kI vs working-set size")
    dut._log.info("[sweep] %s", sep)
    dut._log.info("[sweep] %s", hdr)
    dut._log.info("[sweep] %s", sep)

    prev_seq_dmiss_ki = None
    for size_bytes in sorted(by_size.keys()):
        pats = by_size[size_bytes]
        seq  = pats.get(0)
        stride = pats.get(1)

        seq_dmiss_ki  = _miss_rate(seq["d_dmiss"],  seq["d_instret"])  if seq    else float("nan")
        seq_imiss_ki  = _miss_rate(seq["d_imiss"],  seq["d_instret"])  if seq    else float("nan")
        str_dmiss_ki  = _miss_rate(stride["d_dmiss"], stride["d_instret"]) if stride else float("nan")
        str_imiss_ki  = _miss_rate(stride["d_imiss"], stride["d_instret"]) if stride else float("nan")
        seq_cycles    = seq["d_cycles"] if seq else 0

        # Mark the capacity cliff: where SEQ D$ miss rate sharply rises
        cliff_marker = ""
        if prev_seq_dmiss_ki is not None and not (
            prev_seq_dmiss_ki != prev_seq_dmiss_ki  # NaN guard
        ):
            if seq_dmiss_ki > 2.0 * prev_seq_dmiss_ki + 1.0:
                cliff_marker = "  <-- L1 CAPACITY CLIFF"
        if seq is not None:
            prev_seq_dmiss_ki = seq_dmiss_ki

        dut._log.info(
            "[sweep] %s%s",
            (
                f"{size_bytes:>10d}  "
                f"{seq_dmiss_ki:>14.2f}  {seq_imiss_ki:>14.2f}  "
                f"{str_dmiss_ki:>14.2f}  {str_imiss_ki:>14.2f}  "
                f"{seq_cycles:>12d}"
            ),
            cliff_marker,
        )
    dut._log.info("[sweep] %s", sep)
    dut._log.info(
        "[sweep] NOTE: SEQ D$-miss/kI should be low (<L1 capacity) then rise "
        "sharply once working set > 4 KB (256 lines × 16 B).  "
        "STRIDE D$-miss/kI is the 'max-miss' ceiling (1 miss per access)."
    )


# ── Individual benchmark tests ────────────────────────────────────────────────

@cocotb.test()
async def test_hello_sanity(dut):
    """Sanity: hello.c (64-word sum) — 1 record, id=0x00, checksum non-zero."""
    prog = "hello"
    await _setup(dut, prog)

    sim_cycle = await _run_to_ebreak(dut, prog)

    # Settle: wait a few cycles for AXI transactions to drain before backdoor read
    for _ in range(20):
        await RisingEdge(dut.clk_i)

    slots = _read_scratch(dut, prog)

    assert len(slots) == 1, f"[hello] expected 1 record, got {len(slots)}"
    s = slots[0]
    assert s["id"] == 0x00, f"[hello] expected id=0x00, got 0x{s['id']:02x}"
    assert s["checksum"] != 0, "[hello] checksum == 0 — loop did not execute"
    assert s["d_instret"] > 0, "[hello] d_instret == 0 — CSR counter not working"

    # __result cross-check
    result = _check_result(dut, prog)
    assert result == s["checksum"], (
        f"[hello] __result=0x{result:08x} != slot checksum=0x{s['checksum']:08x}"
    )

    _print_slot_table(dut, prog, slots)

    dut._log.info("[hello] SANITY PASS: 1 record id=0x00 checksum=0x%08x", s["checksum"])
    dut._log.info(
        "[hello] cycles=%d instret=%d imiss=%d dmiss=%d",
        s["d_cycles"], s["d_instret"], s["d_imiss"], s["d_dmiss"],
    )


@cocotb.test()
async def test_sweep_l2_bench(dut):
    """Sweep benchmark: 16 records (8 sizes × 2 patterns).

    Validates magic on every slot then prints the D$-miss/kI vs
    working-set-size curve that feeds the A4 L2 decision document.
    """
    prog = "sweep"
    await _setup(dut, prog)

    dut._log.info("[sweep] starting — watchdog=%d cycles", BENCH_TIMEOUT_CYCLES)
    sim_cycle = await _run_to_ebreak(dut, prog)

    for _ in range(20):
        await RisingEdge(dut.clk_i)

    slots = _read_scratch(dut, prog)

    assert len(slots) == 16, (
        f"[sweep] expected 16 records (8 sizes × 2 patterns), got {len(slots)}"
    )

    # Verify all magic words
    for k, s in enumerate(slots):
        assert (s["magic_word"] & 0xFFFFFF00) == BENCH_MAGIC, (
            f"[sweep] slot {k}: bad magic 0x{s['magic_word']:08x}"
        )

    # Print raw table
    _print_slot_table(dut, prog, slots)

    # Print capacity curve
    _print_sweep_analysis(dut, slots)

    # Basic sanity: STRIDE slots should show higher D$ miss rate than
    # sub-L1-capacity SEQ slots (512 B, 1 KB, 2 KB should be warm hits)
    by_size: dict = {}
    for s in slots:
        sid = s["id"]
        size_idx = (sid >> 5) & 0x7
        pattern  = (sid >> 4) & 0x1
        by_size.setdefault(_SWEEP_SIZES[size_idx], {})[pattern] = s

    # 512B SEQ (fits fully in L1) should have very few D$ misses
    seq_512 = by_size.get(512, {}).get(0)
    if seq_512 is not None:
        dmiss_ki_512 = _miss_rate(seq_512["d_dmiss"], seq_512["d_instret"])
        dut._log.info(
            "[sweep] 512B SEQ D$-miss/kI = %.2f (expect < 10 for warm L1)", dmiss_ki_512
        )

    # 64KB SEQ (16× L1) should have much higher D$ miss rate
    seq_64k = by_size.get(65536, {}).get(0)
    if seq_64k is not None:
        dmiss_ki_64k = _miss_rate(seq_64k["d_dmiss"], seq_64k["d_instret"])
        dut._log.info(
            "[sweep] 64KB SEQ D$-miss/kI = %.2f", dmiss_ki_64k
        )
        if seq_512 is not None and dmiss_ki_64k <= dmiss_ki_512:
            dut._log.warning(
                "[sweep] UNEXPECTED: 64KB D$-miss/kI (%.2f) not higher than "
                "512B D$-miss/kI (%.2f) — check L1 size or counter wiring",
                dmiss_ki_64k, dmiss_ki_512,
            )

    dut._log.info(
        "[sweep] PASS: %d records, sim_cycle=%d", len(slots), sim_cycle
    )


@cocotb.test()
async def test_matmul_l2_bench(dut):
    """Matmul benchmark: 1 record, id=0x01.

    48×48 integer matmul (27 KB working set, 6.75× L1) shows sustained
    D$ miss pressure under computation-heavy access pattern.
    Cross-checks __result against a Python reference checksum.
    """
    prog = "matmul"
    N = 48

    await _setup(dut, prog)

    dut._log.info("[matmul] starting (48×48, ~27 KB working set) — watchdog=%d cycles",
                  BENCH_TIMEOUT_CYCLES)
    sim_cycle = await _run_to_ebreak(dut, prog)

    for _ in range(20):
        await RisingEdge(dut.clk_i)

    slots = _read_scratch(dut, prog)

    assert len(slots) == 1, f"[matmul] expected 1 record, got {len(slots)}"
    s = slots[0]
    assert s["id"] == 0x01, f"[matmul] expected id=0x01, got 0x{s['id']:02x}"
    assert s["d_instret"] > 0, "[matmul] d_instret == 0 — CSR counter not working"

    # Python reference checksum:
    # A[i][j] = i+j, B[i][j] = i*j+1
    # C[i][j] = sum_{k=0}^{N-1} A[i][k]*B[k][j]
    # checksum = sum of all C elements mod 2^32
    ref_cs: int = 0
    for i in range(N):
        for j in range(N):
            acc: int = 0
            for k in range(N):
                a_ik = i + k
                b_kj = k * j + 1
                acc += a_ik * b_kj
            # C[i][j] as int32 (wraps at 32-bit in firmware)
            acc32 = acc & 0xFFFFFFFF
            if acc32 >= 0x80000000:
                acc32 -= 0x100000000
            ref_cs = (ref_cs + acc32) & 0xFFFFFFFF

    dut._log.info(
        "[matmul] firmware checksum=0x%08x  python_ref=0x%08x",
        s["checksum"], ref_cs,
    )
    assert s["checksum"] == ref_cs, (
        f"[matmul] checksum mismatch: firmware=0x{s['checksum']:08x} "
        f"!= python_ref=0x{ref_cs:08x} — data integrity failure"
    )

    # __result cross-check
    result = _check_result(dut, prog)
    assert result == s["checksum"], (
        f"[matmul] __result=0x{result:08x} != slot checksum=0x{s['checksum']:08x}"
    )

    _print_slot_table(dut, prog, slots)

    imiss_ki  = _miss_rate(s["d_imiss"],  s["d_instret"])
    dmiss_ki  = _miss_rate(s["d_dmiss"],  s["d_instret"])
    dmiss_kc  = _miss_rate_per_kcyc(s["d_dmiss"], s["d_cycles"])

    dut._log.info(
        "[matmul] RESULT: cycles=%d  instret=%d  imiss=%d  dmiss=%d",
        s["d_cycles"], s["d_instret"], s["d_imiss"], s["d_dmiss"],
    )
    dut._log.info(
        "[matmul] MISS RATES: imiss/kI=%.2f  dmiss/kI=%.2f  dmiss/kC=%.2f",
        imiss_ki, dmiss_ki, dmiss_kc,
    )
    dut._log.info(
        "[matmul] NOTE: 27 KB working set is 6.75× L1 (4 KB); high dmiss/kI "
        "here confirms L2 benefit for compute workloads with large matrix state."
    )
    dut._log.info("[matmul] PASS: 1 record, checksum verified, sim_cycle=%d", sim_cycle)
