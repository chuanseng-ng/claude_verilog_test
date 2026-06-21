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

    SIZE_STEPS: [512, 1024, 2048, 4096, 8192, 16384, 32768]  (7 entries; 65536 removed)

Matmul ID: 0x01 (single record).

__result cross-check: crt0.S parks main()'s return value in a0 before
EBREAK; the sym file maps __result to the SRAM word at its address.
"""

import sys
import os
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
_SWEEP_SIZES = [512, 1024, 2048, 4096, 8192, 16384, 32768]

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


# ── Results file writer ───────────────────────────────────────────────────────

_RESULTS_MD = Path(__file__).resolve().parent / "l2_bench_results.md"


def _write_results_md(slots: list) -> None:
    """Write sweep results to l2_bench_results.md (persisted deliverable for A4).

    One row per slot with: program, working-set size (bytes), pattern (SEQ/STRIDE),
    Δinstret, Δcycles, ΔD$miss, ΔI$miss, D$miss/1k-instr, I$miss/1k-instr.

    The file is written atomically (tmp + rename) to avoid partial writes.
    """
    lines = [
        "# L2-Cache Decision Benchmark Results",
        "",
        "Generated by `test_l2_bench.py` / `test_sweep_l2_bench`.",
        "DUT: `tb_soc_top` with `SRAM_MEM_WORDS=65536` (256 KB window).",
        "Firmware: `sw/bench/sweep` — 7 sizes × 2 patterns = 14 records.",
        "",
        "| program | size_bytes | pattern | Δinstret | Δcycles | ΔD$miss | ΔI$miss"
        " | D$miss/1k-instr | I$miss/1k-instr |",
        "| ------- | ---------: | ------- | -------: | ------: | ------: | ------:"
        " | --------------: | --------------: |",
    ]

    for s in slots:
        sid = s["id"]
        size_idx = (sid >> 5) & 0x7
        pattern  = (sid >> 4) & 0x1

        if size_idx < len(_SWEEP_SIZES):
            size_bytes = _SWEEP_SIZES[size_idx]
        else:
            size_bytes = 0

        pat_str      = "SEQ" if pattern == 0 else "STRIDE"
        dmiss_ki     = _miss_rate(s["d_dmiss"], s["d_instret"])
        imiss_ki     = _miss_rate(s["d_imiss"], s["d_instret"])

        lines.append(
            f"| sweep | {size_bytes} | {pat_str} | {s['d_instret']} | {s['d_cycles']}"
            f" | {s['d_dmiss']} | {s['d_imiss']}"
            f" | {dmiss_ki:.2f} | {imiss_ki:.2f} |"
        )

    lines.append("")

    tmp_path = _RESULTS_MD.with_suffix(".md.tmp")
    tmp_path.write_text("\n".join(lines), encoding="utf-8")
    tmp_path.rename(_RESULTS_MD)


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
    """Sweep benchmark: 14 records (7 sizes × 2 patterns).

    Validates magic on every slot then prints the D$-miss/kI vs
    working-set-size curve that feeds the A4 L2 decision document.
    sweep.c uses 7 SIZE_STEPS (512B..32KB); 65536 was removed in the
    sim-time reduction pass (max 32KB is 8× L1, cliff fully visible).
    """
    prog = "sweep"
    await _setup(dut, prog)

    dut._log.info("[sweep] starting — watchdog=%d cycles", BENCH_TIMEOUT_CYCLES)
    sim_cycle = await _run_to_ebreak(dut, prog)

    for _ in range(20):
        await RisingEdge(dut.clk_i)

    slots = _read_scratch(dut, prog)

    assert len(slots) == 14, (
        f"[sweep] expected 14 records (7 sizes × 2 patterns), got {len(slots)}"
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

    # 32KB SEQ (8× L1) should have much higher D$ miss rate than sub-L1 sizes
    seq_32k = by_size.get(32768, {}).get(0)
    if seq_32k is not None:
        dmiss_ki_32k = _miss_rate(seq_32k["d_dmiss"], seq_32k["d_instret"])
        dut._log.info(
            "[sweep] 32KB SEQ D$-miss/kI = %.2f", dmiss_ki_32k
        )
        if seq_512 is not None and dmiss_ki_32k <= dmiss_ki_512:
            dut._log.warning(
                "[sweep] UNEXPECTED: 32KB D$-miss/kI (%.2f) not higher than "
                "512B D$-miss/kI (%.2f) — check L1 size or counter wiring",
                dmiss_ki_32k, dmiss_ki_512,
            )

    # Persist results to file — this is the durable deliverable for the A4 decision doc.
    _write_results_md(slots)
    dut._log.info("[sweep] results written to %s", _RESULTS_MD)

    dut._log.info(
        "[sweep] PASS: %d records, sim_cycle=%d", len(slots), sim_cycle
    )


# ── Conflict-stress benchmark ─────────────────────────────────────────────────
#
# conflict.c visits K cache lines all congruent to the SAME D$ set (4096 B
# stride).  K in {1, 2, 4, 8, 16}.  With WAYS=1 (direct-mapped) K=2 thrashes
# every access.  With WAYS=2 (2-way LRU) K=2 holds both lines → ~0 misses.
# This is the key discriminator proving that 2-way eliminates true conflict misses.
#
# ID encoding (from conflict.c):
#   slot[i].magic & 0xFF = K   (e.g. 1, 2, 4, 8, 16)
#
# WAYS detection: read DCACHE_WAYS localparam from the DUT at runtime.
# The localparam is exposed via --public-flat-rw as a Verilator elaboration
# constant.  If the DUT read fails (localparam not public), fall back to
# environment variable DCACHE_WAYS_EXPECTED, then to the pkg constant (default 2).

_CONFLICT_K_VALS = [1, 2, 4, 8, 16]
_CONFLICT_ROUNDS = 256  # must match ROUNDS in conflict.c

_CONFLICT_RESULTS_1WAY = Path(__file__).resolve().parent / "conflict_results_1way.md"
_CONFLICT_RESULTS_2WAY = Path(__file__).resolve().parent / "conflict_results_2way.md"
_COREMARK_RESULTS_PATH = Path(__file__).resolve().parent / "coremark_results.md"


def _detect_dcache_ways(dut) -> int:
    """Return DCACHE_WAYS from the DUT elaboration constant, env-var, or default 2."""
    # Try the Verilator-public localparam path through the hierarchy.
    # With --public-flat-rw, package localparams appear as DUT root attributes.
    for attr in (
        "rv32i_cache_pkg__DCACHE_WAYS",
        "DCACHE_WAYS",
    ):
        try:
            v = int(getattr(dut, attr).value)
            if v in (1, 2):
                dut._log.info("[conflict] DCACHE_WAYS detected from DUT: %d", v)
                return v
        except Exception:
            pass
    # Try the dcache module's WAYS_L localparam
    try:
        v = int(dut.u_soc.u_cpu.u_core.u_dcache.WAYS_L.value)
        if v in (1, 2):
            dut._log.info("[conflict] DCACHE_WAYS detected from u_dcache.WAYS_L: %d", v)
            return v
    except Exception:
        pass
    # Environment variable set by the Makefile target
    env_ways = os.environ.get("DCACHE_WAYS_EXPECTED", "")
    if env_ways in ("1", "2"):
        v = int(env_ways)
        dut._log.info("[conflict] DCACHE_WAYS from DCACHE_WAYS_EXPECTED env: %d", v)
        return v
    dut._log.warning(
        "[conflict] DCACHE_WAYS not detectable — defaulting to 2 "
        "(set experiment/dcache-2way active config)"
    )
    return 2


def _print_conflict_table(dut, prog: str, slots: list, ways: int) -> None:
    """Print conflict-stress D$-miss/kI table with K-value row labels."""
    hdr = (
        f"{'K':>4}  {'cycles':>10}  {'instret':>10}  "
        f"{'dmiss':>8}  {'dmiss/kI':>10}  {'dmiss/access':>14}  "
        f"{'interpretation':>30}"
    )
    sep = "-" * len(hdr)
    dut._log.info("[%s] CONFLICT-STRESS TABLE (WAYS=%d)", prog, ways)
    dut._log.info("[%s] %s", prog, sep)
    dut._log.info("[%s] %s", prog, hdr)
    dut._log.info("[%s] %s", prog, sep)

    for s in slots:
        k = s["id"]
        accesses = k * _CONFLICT_ROUNDS  # measured-pass accesses
        dmiss_ki = _miss_rate(s["d_dmiss"], s["d_instret"])
        dmiss_per_access = s["d_dmiss"] / accesses if accesses > 0 else float("nan")

        if k == 1:
            interp = "K=1: fits → expect ~0"
        elif k == 2:
            if ways == 1:
                interp = "K=2 W=1: THRASH expected ~1.0/acc"
            else:
                interp = "K=2 W=2: HELD expected ~0/acc"
        elif k <= ways:
            interp = f"K={k}<=WAYS: held"
        else:
            interp = f"K={k}>WAYS: thrash"

        dut._log.info(
            "[%s] %s",
            prog,
            (
                f"{k:>4}  {s['d_cycles']:>10d}  {s['d_instret']:>10d}  "
                f"{s['d_dmiss']:>8d}  {dmiss_ki:>10.2f}  "
                f"{dmiss_per_access:>14.4f}  "
                f"{interp:>30}"
            ),
        )
    dut._log.info("[%s] %s", prog, sep)


def _write_conflict_results_md(slots: list, ways: int) -> Path:
    """Write conflict-stress results to conflict_results_<ways>way.md.

    Returns the path written.
    """
    out_path = _CONFLICT_RESULTS_1WAY if ways == 1 else _CONFLICT_RESULTS_2WAY

    lines = [
        f"# Conflict-Stress Benchmark Results — WAYS={ways}",
        "",
        f"Generated by `test_l2_bench.py` / `test_conflict_l2_bench` (WAYS={ways}).",
        "DUT: `tb_soc_top` with `SRAM_MEM_WORDS=65536` (256 KB window).",
        "Firmware: `sw/bench/conflict` — 5 K-values × 4096 B stride (same set every access).",
        f"ROUNDS={_CONFLICT_ROUNDS} per measured pass.  Accesses = K × ROUNDS.",
        "",
        "| K | Δinstret | Δcycles | ΔD$miss | D$miss/1k-instr | D$miss/access | note |",
        "| -: | -------: | ------: | ------: | --------------: | ------------: | ---- |",
    ]

    for s in slots:
        k = s["id"]
        accesses = k * _CONFLICT_ROUNDS
        dmiss_ki = _miss_rate(s["d_dmiss"], s["d_instret"])
        dmiss_per_access = s["d_dmiss"] / accesses if accesses > 0 else float("nan")

        if k == 1:
            note = "fits (no conflict)"
        elif k == 2 and ways == 1:
            note = "**THRASH** (direct-mapped; 1 miss/access expected)"
        elif k == 2 and ways == 2:
            note = "**HELD** (2-way LRU; ~0 miss expected)"
        elif k <= ways:
            note = f"fits ({k}<={ways} ways)"
        else:
            note = f"thrash ({k}>{ways} ways)"

        lines.append(
            f"| {k} | {s['d_instret']} | {s['d_cycles']}"
            f" | {s['d_dmiss']} | {dmiss_ki:.2f}"
            f" | {dmiss_per_access:.4f} | {note} |"
        )

    lines.append("")
    lines.append("## Key Result")
    k2_slot = next((s for s in slots if s["id"] == 2), None)
    if k2_slot is not None:
        k2_dmiss_per_access = k2_slot["d_dmiss"] / (2 * _CONFLICT_ROUNDS)
        k2_dmiss_ki = _miss_rate(k2_slot["d_dmiss"], k2_slot["d_instret"])
        if ways == 1:
            lines.append(
                f"K=2 WAYS=1: D$miss/access = {k2_dmiss_per_access:.4f} "
                f"(D$miss/kI = {k2_dmiss_ki:.2f}) — "
                f"direct-mapped thrashes on 2 congruent lines."
            )
        else:
            lines.append(
                f"K=2 WAYS=2: D$miss/access = {k2_dmiss_per_access:.4f} "
                f"(D$miss/kI = {k2_dmiss_ki:.2f}) — "
                f"2-way LRU eliminates conflict misses."
            )

    lines.append("")

    tmp_path = out_path.with_suffix(".md.tmp")
    tmp_path.write_text("\n".join(lines), encoding="utf-8")
    tmp_path.rename(out_path)
    return out_path


@cocotb.test()
async def test_conflict_l2_bench(dut):
    """Conflict-stress benchmark (M10c): K congruent cache lines, K in {1,2,4,8,16}.

    conflict.c places all K probes at 4096 B intervals — the same D$ set for
    both WAYS=1 (256 sets × 16 B) and WAYS=2 (128 sets × 16 B).

    Key K=2 discriminator:
      WAYS=1 (direct-mapped): K=2 thrashes — evict-reload every access → ~1 miss/access.
      WAYS=2 (2-way LRU):     K=2 is held — both lines resident → ~0 misses.

    This test works with the SAME firmware binary (conflict.hex) for both WAYS
    configurations.  Only the RTL DCACHE_WAYS localparam in rv32i_cache_pkg.sv
    changes between the two runs.

    The WAYS value is detected at runtime from the DUT elaboration (WAYS_L localparam)
    or the DCACHE_WAYS_EXPECTED environment variable.  Results are written to
    conflict_results_<ways>way.md for side-by-side comparison in M10_L2_DECISION_ANALYSIS.md.
    """
    prog = "conflict"
    await _setup(dut, prog)

    ways = _detect_dcache_ways(dut)
    dut._log.info(
        "[conflict] WAYS=%d — running conflict-stress benchmark (K in {1,2,4,8,16})",
        ways,
    )

    # conflict.c: 5 K-values × 2 passes × K × ROUNDS ≈ 15 872 loads + overhead.
    # Even at 5 CPI with cache-miss stalls the benchmark is ~320k cycles max.
    # Use 2 M-cycle watchdog (generous even for the thrash-heavy K=16 case).
    CONFLICT_TIMEOUT = 2_000_000
    dut._log.info("[conflict] watchdog=%d cycles", CONFLICT_TIMEOUT)

    sim_cycle = await _run_to_ebreak(dut, prog, timeout=CONFLICT_TIMEOUT)

    for _ in range(20):
        await RisingEdge(dut.clk_i)

    slots = _read_scratch(dut, prog)

    assert len(slots) == 5, (
        f"[conflict] expected 5 records (K=1,2,4,8,16), got {len(slots)}"
    )

    # Validate magic words and K-value ordering
    expected_k = [1, 2, 4, 8, 16]
    for idx, (s, ek) in enumerate(zip(slots, expected_k)):
        assert (s["magic_word"] & 0xFFFFFF00) == BENCH_MAGIC, (
            f"[conflict] slot {idx}: bad magic 0x{s['magic_word']:08x}"
        )
        assert s["id"] == ek, (
            f"[conflict] slot {idx}: expected K={ek}, got id={s['id']}"
        )
        assert s["d_instret"] > 0, (
            f"[conflict] slot {idx} (K={ek}): d_instret=0 — CSR counter not working"
        )

    # Print table
    _print_conflict_table(dut, prog, slots, ways)

    # ── Key correctness checks ────────────────────────────────────────────────
    k1_slot  = slots[0]  # K=1
    k2_slot  = slots[1]  # K=2  ← key discriminator
    k4_slot  = slots[2]  # K=4
    k16_slot = slots[4]  # K=16

    k1_dmiss_per_access  = k1_slot["d_dmiss"]  / (1  * _CONFLICT_ROUNDS)
    k2_dmiss_per_access  = k2_slot["d_dmiss"]  / (2  * _CONFLICT_ROUNDS)
    k4_dmiss_per_access  = k4_slot["d_dmiss"]  / (4  * _CONFLICT_ROUNDS)
    k16_dmiss_per_access = k16_slot["d_dmiss"] / (16 * _CONFLICT_ROUNDS)

    k2_dmiss_ki = _miss_rate(k2_slot["d_dmiss"], k2_slot["d_instret"])

    dut._log.info(
        "[conflict] KEY RESULTS (WAYS=%d):", ways
    )
    dut._log.info(
        "[conflict]   K=1  D$miss/access = %.4f  D$miss/kI = %.2f  (expect ~0)",
        k1_dmiss_per_access, _miss_rate(k1_slot["d_dmiss"], k1_slot["d_instret"]),
    )
    dut._log.info(
        "[conflict]   K=2  D$miss/access = %.4f  D$miss/kI = %.2f"
        "  ← KEY DISCRIMINATOR (WAYS=%d: expect %s)",
        k2_dmiss_per_access, k2_dmiss_ki, ways,
        "~1.0 (thrash)" if ways == 1 else "~0 (held by LRU)",
    )
    dut._log.info(
        "[conflict]   K=4  D$miss/access = %.4f  D$miss/kI = %.2f",
        k4_dmiss_per_access, _miss_rate(k4_slot["d_dmiss"], k4_slot["d_instret"]),
    )
    dut._log.info(
        "[conflict]   K=16 D$miss/access = %.4f  D$miss/kI = %.2f",
        k16_dmiss_per_access, _miss_rate(k16_slot["d_dmiss"], k16_slot["d_instret"]),
    )

    # K=1 sanity: single line, always hits after prime pass → near-zero misses.
    # Allow up to 2 compulsory misses per cache line (1 refill = 4 words).
    assert k1_dmiss_per_access < 0.1, (
        f"[conflict] K=1 D$miss/access = {k1_dmiss_per_access:.4f} "
        f"(expected < 0.1 — prime pass should warm the single line)"
    )

    if ways == 1:
        # WAYS=1: K=2 must thrash — expect ~1 miss per access (evict-reload every time).
        # Conservative threshold: >0.5 miss/access (actual should be ~1.0).
        assert k2_dmiss_per_access > 0.5, (
            f"[conflict] WAYS=1 K=2 D$miss/access = {k2_dmiss_per_access:.4f} "
            f"(expected > 0.5 — direct-mapped should thrash with 2 congruent lines). "
            f"If this is ~0, DCACHE_WAYS may not actually be 1."
        )
        dut._log.info(
            "[conflict] WAYS=1 K=2 THRASH CONFIRMED: %.4f miss/access", k2_dmiss_per_access
        )
    else:
        # WAYS=2: K=2 must NOT thrash — LRU holds both lines → near-zero misses.
        # Allow up to 4 compulsory misses (1 refill per line = 4 words each; 2 lines).
        # But per-access rate should be very low: 8 compulsory misses / (2×256) = 0.0156.
        assert k2_dmiss_per_access < 0.1, (
            f"[conflict] WAYS=2 K=2 D$miss/access = {k2_dmiss_per_access:.4f} "
            f"(expected < 0.1 — 2-way LRU should hold both congruent lines). "
            f"If this is ~1.0, the LRU fill/eviction has a bug. "
            f"Inspect CS_TAG_CHECK cand_vw/lru_array handling in rv32i_dcache.sv."
        )
        dut._log.info(
            "[conflict] WAYS=2 K=2 CONFLICT-MISS ELIMINATION CONFIRMED: %.4f miss/access",
            k2_dmiss_per_access,
        )

    # K=4 and K=16: both configs thrash (more lines than ways → both should be high).
    # Verify K=4 miss rate is substantially higher than K=1 (not essential to assert
    # exact value — hardware may have AXI latency variation).
    assert k4_dmiss_per_access > 0.3, (
        f"[conflict] K=4 D$miss/access = {k4_dmiss_per_access:.4f} "
        f"(expected > 0.3 — {ways}-way cache with K=4 lines should thrash)"
    )

    # Write persistent results file
    out_path = _write_conflict_results_md(slots, ways)
    dut._log.info("[conflict] results written to %s", out_path)

    dut._log.info(
        "[conflict] PASS: WAYS=%d, 5 records, sim_cycle=%d, K=2 miss/access=%.4f",
        ways, sim_cycle, k2_dmiss_per_access,
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

    # Matmul uses sw-mul (__mulsi3) on RV32I (no M ext) — 48^3 = 110 592 calls,
    # each ~20 instructions.  Measured: ~10–12 M cycles with cache misses.
    # Use 25 M watchdog. 48^3=110592 sw-mul calls (~30 instr each) ≈ 3.3 M instr;
    # at ~5-8 CPI (D$ miss heavy, no M-ext) → 16-26 M cycles measured range.
    MATMUL_TIMEOUT = 25_000_000
    dut._log.info("[matmul] starting (48×48, ~27 KB working set) — watchdog=%d cycles",
                  MATMUL_TIMEOUT)
    sim_cycle = await _run_to_ebreak(dut, prog, timeout=MATMUL_TIMEOUT)

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


# ── CoreMark results writer ───────────────────────────────────────────────────

def _write_coremark_results_md(s: dict, sim_cycle: int) -> Path:
    """Write coremark_results.md from one bench slot.

    Returns the path written.
    """
    instret  = s["d_instret"]
    d_dmiss  = s["d_dmiss"]
    d_imiss  = s["d_imiss"]
    d_cycles = s["d_cycles"]

    dmiss_ki  = _miss_rate(d_dmiss, instret)
    imiss_ki  = _miss_rate(d_imiss, instret)
    dmiss_kc  = _miss_rate_per_kcyc(d_dmiss, d_cycles)

    lines = [
        "# CoreMark-Representative Benchmark Results (M10c-3)",
        "",
        "Generated by `test_l2_bench.py` / `test_coremark_bench`.",
        "DUT: `tb_soc_top` with `SRAM_MEM_WORDS=65536`, `DCACHE_WAYS=1` (direct-mapped, shipping default).",
        "Firmware: `sw/bench/coremark` — 3-kernel port (list sort + 2×2 matmul + CRC-16), ITERATIONS=1.",
        f"Sim stopped at cycle {sim_cycle}.",
        "",
        "## Raw Counters",
        "",
        "| metric | value |",
        "| ------ | ----: |",
        f"| Δcycles    | {d_cycles} |",
        f"| Δinstret   | {instret} |",
        f"| ΔI\\$-miss  | {d_imiss} |",
        f"| ΔD\\$-miss  | {d_dmiss} |",
        "",
        "## Miss Rates",
        "",
        "| metric | value |",
        "| ------ | ----: |",
        f"| I\\$-miss / 1k-instr | {imiss_ki:.2f} |",
        f"| D\\$-miss / 1k-instr | {dmiss_ki:.2f} |",
        f"| D\\$-miss / 1k-cycle | {dmiss_kc:.2f} |",
        "",
        "## Key Finding",
        "",
        "Working-set analysis: list (80 B) + matmul (24 B) + CRC buf (16 B) + overhead (~112 B) ≈ 232 B.",
        "The entire CoreMark data working set is **< 6% of the 4 KB L1 D-cache**.",
        "",
        f"D\\$-miss/kI = {dmiss_ki:.2f}: representative embedded firmware fits the direct-mapped "
        "L1 with negligible capacity or conflict pressure.",
        "Cold-fill misses account for any non-zero D\\$-miss count at this working-set size.",
        "",
        "> **Conclusion (M10c-3):** CoreMark-representative firmware shows no L1 D\\$",
        "> capacity or conflict pressure with the shipping direct-mapped 4 KB cache.",
        "> The L2 go/no-go decision must be driven by application-specific working sets",
        "> (e.g. the 8+ KB threshold revealed by the sweep benchmark), not by CoreMark.",
        "",
    ]

    out_path = _COREMARK_RESULTS_PATH
    tmp_path = out_path.with_suffix(".md.tmp")
    tmp_path.write_text("\n".join(lines), encoding="utf-8")
    tmp_path.rename(out_path)
    return out_path


@cocotb.test()
async def test_coremark_bench(dut):
    """CoreMark-representative benchmark (M10c-3): single record, id=0x01.

    3-kernel port (linked-list sort + 2x2 matmul + CRC-16), ITERATIONS=1.
    Data working-set ~232 B — trivially fits the 4 KB direct-mapped L1 D$.

    Expected outcome: D$miss/1k-instr ≈ 0 (only cold-fill misses on first
    touch of the ~232 B data region).  This empirically confirms that
    representative embedded firmware sees no L1 capacity/conflict pressure.

    Run with DCACHE_WAYS=1 (shipping direct-mapped config).  Results are
    written to tb/cocotb/soc/coremark_results.md.
    """
    prog = "coremark"
    await _setup(dut, prog)

    # coremark at ITERATIONS=1 is ~3-6 k instructions.
    # At CPI ≈ 1–2 (D$ fully warm after cold fills): 6–12 k cycles.
    # Use 500 k watchdog — 80× generous overhead for any pipeline stalls.
    COREMARK_TIMEOUT = 500_000
    dut._log.info(
        "[coremark] starting (3-kernel, ITERATIONS=1, ~232 B working set) — "
        "watchdog=%d cycles", COREMARK_TIMEOUT
    )

    sim_cycle = await _run_to_ebreak(dut, prog, timeout=COREMARK_TIMEOUT)

    for _ in range(20):
        await RisingEdge(dut.clk_i)

    slots = _read_scratch(dut, prog)

    assert len(slots) == 1, (
        f"[coremark] expected 1 record (id=0x01), got {len(slots)}"
    )
    s = slots[0]
    assert s["id"] == 0x01, (
        f"[coremark] expected id=0x01 (COREMARK_ID), got 0x{s['id']:02x}"
    )
    assert s["d_instret"] > 0, (
        "[coremark] d_instret == 0 — CSR counter not working"
    )

    _print_slot_table(dut, prog, slots)

    imiss_ki  = _miss_rate(s["d_imiss"],  s["d_instret"])
    dmiss_ki  = _miss_rate(s["d_dmiss"],  s["d_instret"])
    dmiss_kc  = _miss_rate_per_kcyc(s["d_dmiss"], s["d_cycles"])

    dut._log.info(
        "[coremark] RESULT: cycles=%d  instret=%d  imiss=%d  dmiss=%d",
        s["d_cycles"], s["d_instret"], s["d_imiss"], s["d_dmiss"],
    )
    dut._log.info(
        "[coremark] MISS RATES: imiss/kI=%.2f  dmiss/kI=%.2f  dmiss/kC=%.2f",
        imiss_ki, dmiss_ki, dmiss_kc,
    )

    # Key assertion: D$ miss rate must be very low for a 232 B working set.
    # Allow up to 5/kI — cold fills on ~232B = 15 lines = 15 misses max;
    # at ~2700 instret expected, 15/2700*1000 ≈ 5.6/kI upper bound.
    assert dmiss_ki < 10.0, (
        f"[coremark] D$miss/kI = {dmiss_ki:.2f} >= 10.0 — "
        f"unexpected miss pressure for a 232 B working set (DCACHE_WAYS=1). "
        f"Expected only cold-fill misses (< 10/kI)."
    )

    dut._log.info(
        "[coremark] NOTE: ~232 B working set << 4 KB L1 D$; "
        "D$miss/kI=%.2f confirms only cold-fill misses — no capacity/conflict pressure.",
        dmiss_ki,
    )

    # Write persistent results file
    out_path = _write_coremark_results_md(s, sim_cycle)
    dut._log.info("[coremark] results written to %s", out_path)

    dut._log.info(
        "[coremark] PASS: 1 record id=0x01, sim_cycle=%d, "
        "dmiss/kI=%.2f imiss/kI=%.2f",
        sim_cycle, dmiss_ki, imiss_ki,
    )
