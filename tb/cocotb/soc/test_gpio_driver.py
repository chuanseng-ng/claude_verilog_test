"""
test_gpio_driver.py -- Phase 6a GPIO DRIVER test. Proves sw/drivers/gpio.h works by RUNNING it on
the full SoC. It loads sw/bench/build/gpio_demo.hex onto tb_soc_top by the backdoor-load and
run-to-EBREAK technique of test_l2_bench.py. It scoreboards the three phases through commit_pc_o and
the tb_soc_top ports and nets at compiler-generated marker-function addresses (from
build/gpio_demo.sym). It is NOT a duplicate of test_soc_gpio.py: that suite proves the RTL through
the fabric, this one proves the driver API.
Phases: 1 OUTPUT: the test checks gpio_oe_o and gpio_out_o at marker_output_done(). 2 INPUT: the
test drives gpio_in_i at marker_input_ready() and the driver's bounded poll absorbs the synchroniser
latency. 3 INTERRUPT: the test raises the IRQ_PIN_IDX bit, watches commit_pc_o for gpio_isr's entry
(the CPU really took the trap), samples dut.u_soc.gpio_irq and ext_irq at trap entry (asserted),
then polls within DEASSERT_CHECK_WINDOW_CYCLES for both to deassert (gpio_irq_clear_edge() worked).
Window rule: do not check deassertion at one fixed point. A compiled ISR is slower than
hand-assembled code (the GCC `interrupt` prologue hits cold D$ lines, gpio_isr sits in a cold I$
region, and each early instruction waits for a fabric round trip). So the check polls across
DEASSERT_CHECK_WINDOW_CYCLES and still catches a "never clears" bug.
gpio_demo.c ends in crt0.S's halt sequence (D$ flush, FENCE, EBREAK) and reports through __result (0
= PASS), so there is no FAIL_PC watch. The test runs to FENCE, reads __result and g_isr_count from
SRAM, and cross-checks g_isr_count.
Firmware is pre-built by `make -C sw/bench`; this target consumes
sw/bench/build/gpio_demo.{hex,sym,dis} and does NOT rebuild the C code (the l2_bench contract). DUT:
tb_soc_top with SRAM_MEM_WORDS=65536 (as l2_bench): sw/bench/rv32i.ld puts the stack top at 0x41C00.
Run: make -C tb/cocotb/soc gpio_driver
Doc: tm:suite:soc-test-gpio-driver
"""

import sys
from pathlib import Path

import cocotb
from cocotb.triggers import RisingEdge, ReadOnly

from soc_clocks import drive_soc_reset, start_soc_clocks
from sram_backdoor import sram_mem

_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

_BENCH_BUILD = _ROOT / "sw" / "bench" / "build"
_TRAMPOLINE_HEX = _BENCH_BUILD / "trampoline.hex"
_PROG = "gpio_demo"

# ---------------------------------------------------------------------------
# Constants (mirror sw/bench/gpio_demo.c exactly)
# ---------------------------------------------------------------------------
CLK_PERIOD_NS = 2  # matches every other SoC suite
SRAM_BASE_ADDR = 0x2000

INPUT_PIN_A = 16
INPUT_PIN_B = 18
INPUT_MASK = (1 << INPUT_PIN_A) | (1 << INPUT_PIN_B)

IRQ_PIN_IDX = 24

TEST_DIR_VAL = 0x000000F0
TEST_DATA_VAL = 0x00000050

# Generous vs. ~20-30 full-fabric MMIO round trips plus two bounded
# POLL_LIMIT=4000 driver-side poll loops (each iteration a single MMIO read).
GPIO_DRIVER_TEST_TIMEOUT_CYCLES = 400_000
DRAIN_CYCLES = 200

# Bounded window (from gpio_isr's own entry-PC commit) within which dut.u_soc.gpio_irq / ext_irq
# must deassert.
# The compiled gpio_demo.c ISR needs far more cycles than test_soc_gpio.py's hand-assembled firmware
# (see the window rule in this file's module docstring). 500 cycles leave about 3x headroom over the
# measured latency without materially lengthening the suite.
DEASSERT_CHECK_WINDOW_CYCLES = 500


# ---------------------------------------------------------------------------
# Hex/sym helpers (mirrors test_l2_bench.py)
# ---------------------------------------------------------------------------
def _parse_hex(path: Path) -> list:
    words = []
    with open(path) as f:
        for line in f:
            tok = line.strip()
            if not tok or tok.startswith("//") or tok.startswith("@"):
                continue
            words.append(int(tok, 16))
    return words


def _load_rom(dut, words: list) -> None:
    mem = dut.u_soc.u_boot_rom.mem
    for i, w in enumerate(words):
        mem[i].value = w


def _load_sram(dut, words: list) -> None:
    mem = sram_mem(dut)
    for i, w in enumerate(words):
        mem[i].value = w


def _parse_sym(prog: str) -> dict:
    """Return {symbol_name: byte_address} from build/<prog>.sym (nm -n output)."""
    sym_path = _BENCH_BUILD / f"{prog}.sym"
    syms: dict = {}
    with open(sym_path) as f:
        for line in f:
            parts = line.split()
            if len(parts) >= 3:
                try:
                    syms[parts[2]] = int(parts[0], 16)
                except ValueError:
                    pass
    return syms


def _sram_wi(byte_addr: int) -> int:
    return (byte_addr - SRAM_BASE_ADDR) // 4


def _fence_pc(prog: str) -> int:
    """Return the PC of the FENCE instruction immediately before EBREAK.

    Identical technique to test_l2_bench.py's _fence_pc: crt0.S's halt
    sequence always ends FENCE; EBREAK — regardless of gpio_demo.c's return
    value, so this sentinel fires whether the firmware self-reports PASS or
    FAIL.
    """
    dis_path = _BENCH_BUILD / f"{prog}.dis"
    prev_pc = None
    with open(dis_path) as f:
        for line in f:
            stripped = line.strip()
            if "ebreak" in stripped.lower() and ":" in stripped:
                parts = stripped.split(":")
                try:
                    ebreak_addr = int(parts[0].strip(), 16)
                    return ebreak_addr - 4
                except ValueError:
                    pass
            if "fence" in stripped.lower() and "fence.i" not in stripped.lower() and ":" in stripped:
                parts = stripped.split(":")
                try:
                    prev_pc = int(parts[0].strip(), 16)
                except ValueError:
                    pass
    if prev_pc is not None:
        return prev_pc
    return 0x2058  # hard fallback, matches the layout observed at build time


def _dcache_read_word(dut, byte_addr: int) -> int:
    """Coherent read after halt: crt0.S's CSRW 0x7C0 flush (before FENCE) has
    already write-backed every dirty D$ line to main SRAM by the time this is
    called, so a plain SRAM read is sufficient. Kept as its own helper (name
    matches test_l2_bench.py's) so a future caller that reads BEFORE halt
    does not silently get stale data without a reminder to add the D$-aware
    path back.
    """
    wi = _sram_wi(byte_addr)
    raw = sram_mem(dut)[wi].value
    return int(raw) & 0xFFFF_FFFF


# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------
async def _setup(dut) -> None:
    start_soc_clocks(dut, CLK_PERIOD_NS)

    drive_soc_reset(dut, True)
    dut.apb_paddr_i.value = 0
    dut.apb_psel_i.value = 0
    dut.apb_penable_i.value = 0
    dut.apb_pwrite_i.value = 0
    dut.apb_pwdata_i.value = 0
    dut.uart_rx_i.value = 1
    dut.spi_miso_i.value = 0
    dut.gpio_in_i.value = 0

    trampoline_words = _parse_hex(_TRAMPOLINE_HEX)
    prog_words = _parse_hex(_BENCH_BUILD / f"{_PROG}.hex")

    _load_rom(dut, trampoline_words)
    _load_sram(dut, prog_words)

    for _ in range(5):
        await RisingEdge(dut.clk_i)

    drive_soc_reset(dut, False)

    for _ in range(2):
        await RisingEdge(dut.clk_i)


@cocotb.test()
async def test_gpio_driver(dut):
    """Run gpio_demo.c on the full SoC and independently verify all 3 phases."""
    await _setup(dut)

    syms = _parse_sym(_PROG)
    for name in ("gpio_isr", "marker_output_done", "marker_input_ready",
                 "marker_irq_ready", "__result", "g_isr_count"):
        assert name in syms, (
            f"symbol '{name}' not found in build/{_PROG}.sym — "
            f"rebuild sw/bench (nix develop ...#bench --command make -C sw/bench)"
        )

    isr_pc = syms["gpio_isr"]
    output_done_pc = syms["marker_output_done"]
    input_ready_pc = syms["marker_input_ready"]
    irq_ready_pc = syms["marker_irq_ready"]
    fence_pc_val = _fence_pc(_PROG)

    result_wi = _sram_wi(syms["__result"])
    isr_count_wi = _sram_wi(syms["g_isr_count"])

    dut._log.info(
        "gpio_demo symbols: gpio_isr=0x%08x output_done=0x%08x input_ready=0x%08x "
        "irq_ready=0x%08x fence=0x%08x",
        isr_pc, output_done_pc, input_ready_pc, irq_ready_pc, fence_pc_val,
    )

    seen_output_done = False
    seen_input_ready = False
    seen_irq_ready = False
    seen_isr_pc = False
    checked_deassert = False

    isr_seen_at_cycle = None
    fence_cycle = -1
    pending_action = None

    last_pc = 0
    recent: list = []

    for cycle_idx in range(GPIO_DRIVER_TEST_TIMEOUT_CYCLES):
        await RisingEdge(dut.clk_i)

        # Write-permitted phase: apply any action queued from the previous
        # cycle's ReadOnly observation.
        if pending_action == "drive_input":
            dut.gpio_in_i.value = INPUT_MASK
            pending_action = None
        elif pending_action == "drive_irq_edge":
            dut.gpio_in_i.value = INPUT_MASK | (1 << IRQ_PIN_IDX)
            pending_action = None

        await ReadOnly()

        if dut.commit_valid_o.value:
            pc = int(dut.commit_pc_o.value)
            last_pc = pc
            recent.append(pc)
            if len(recent) > 16:
                recent.pop(0)

            if pc == output_done_pc and not seen_output_done:
                seen_output_done = True
                oe = int(dut.gpio_oe_o.value)
                out = int(dut.gpio_out_o.value)
                assert oe == TEST_DIR_VAL, (
                    f"gpio_oe_o = 0x{oe:08x}, expected 0x{TEST_DIR_VAL:08x} "
                    f"after gpio_dir_write() — driver write did not reach "
                    f"the gpio_controller pads through the fabric"
                )
                assert out == TEST_DATA_VAL, (
                    f"gpio_out_o = 0x{out:08x}, expected 0x{TEST_DATA_VAL:08x} "
                    f"after gpio_out_write()"
                )

            if pc == input_ready_pc and not seen_input_ready:
                seen_input_ready = True
                pending_action = "drive_input"

            if pc == irq_ready_pc and not seen_irq_ready:
                seen_irq_ready = True
                pending_action = "drive_irq_edge"

            if pc == isr_pc and not seen_isr_pc:
                seen_isr_pc = True
                isr_seen_at_cycle = cycle_idx
                irq_at_trap = int(dut.u_soc.gpio_irq.value)
                ext_irq_at_trap = int(dut.u_soc.ext_irq.value)
                assert irq_at_trap == 1, (
                    "CPU vectored to gpio_isr but dut.u_soc.gpio_irq is not "
                    "asserted — trap entry inconsistent with an asserted "
                    "GPIO interrupt source"
                )
                assert ext_irq_at_trap == 1, (
                    "CPU vectored to gpio_isr but dut.u_soc.ext_irq is not asserted"
                )

            if pc == fence_pc_val and fence_cycle < 0:
                fence_cycle = cycle_idx
                dut._log.info(
                    "FENCE committed at PC=0x%08x, cycle=%d — draining %d cycles",
                    pc, cycle_idx, DRAIN_CYCLES,
                )

        # Bounded poll for eventual deassertion (see the ROOT-CAUSE NOTE in
        # this file's module docstring). Checked every cycle from ISR entry
        # so a fast deassertion still passes immediately; only a source that
        # NEVER clears within DEASSERT_CHECK_WINDOW_CYCLES is a failure.
        if seen_isr_pc and not checked_deassert:
            irq_now = int(dut.u_soc.gpio_irq.value)
            ext_irq_now = int(dut.u_soc.ext_irq.value)
            delta = cycle_idx - isr_seen_at_cycle
            if irq_now == 0 and ext_irq_now == 0:
                checked_deassert = True
                dut._log.info(
                    "dut.u_soc.gpio_irq/ext_irq deasserted %d cycles after "
                    "gpio_isr entry (window=%d)",
                    delta, DEASSERT_CHECK_WINDOW_CYCLES,
                )
            elif delta >= DEASSERT_CHECK_WINDOW_CYCLES:
                assert False, (
                    f"dut.u_soc.gpio_irq/ext_irq still asserted "
                    f"{DEASSERT_CHECK_WINDOW_CYCLES} cycles after gpio_isr ran "
                    f"(gpio_irq={irq_now}, ext_irq={ext_irq_now}) — "
                    f"gpio_irq_clear_edge() did not deassert the source"
                )

        if fence_cycle >= 0 and (cycle_idx - fence_cycle) >= DRAIN_CYCLES:
            break
    else:
        recent_str = " ".join(f"0x{p:08x}" for p in recent[-16:])
        assert False, (
            f"FENCE sentinel PC=0x{fence_pc_val:08x} not seen within "
            f"{GPIO_DRIVER_TEST_TIMEOUT_CYCLES} cycles (last_pc=0x{last_pc:08x}). "
            f"Recent PCs: {recent_str}"
        )

    assert seen_output_done, "marker_output_done was never committed"
    assert seen_input_ready, "marker_input_ready was never committed"
    assert seen_irq_ready, "marker_irq_ready was never committed"
    assert seen_isr_pc, "gpio_isr entry was never committed — CPU never took the GPIO trap"
    assert checked_deassert, "post-ISR deassertion window was never reached"

    # A few extra settle cycles for AXI write-back to fully drain (mirrors
    # test_l2_bench.py's post-_run_to_ebreak settle window) before the
    # backdoor SRAM read.
    for _ in range(20):
        await RisingEdge(dut.clk_i)

    result = _dcache_read_word(dut, syms["__result"])
    isr_count = _dcache_read_word(dut, syms["g_isr_count"])

    dut._log.info(
        "gpio_demo halted: __result=0x%08x (word %d), g_isr_count=%d (word %d)",
        result, result_wi, isr_count, isr_count_wi,
    )

    assert result == 0, (
        f"gpio_demo.c self-report FAILED: __result=0x{result:08x} "
        f"(0 = PASS; see gpio_demo.c FAIL_* codes for the failing phase)"
    )

    # Independent backdoor cross-check: exactly one ISR entry, matching both
    # the firmware's own self-check and this test's own commit_pc_o/gpio_irq
    # observation above.
    assert isr_count == 1, (
        f"backdoor SRAM read: g_isr_count (word {isr_count_wi}) = {isr_count}, "
        f"expected exactly 1"
    )

    dut._log.info("test_gpio_driver PASS")
