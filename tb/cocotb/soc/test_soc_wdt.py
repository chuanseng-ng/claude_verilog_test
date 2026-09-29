"""
test_soc_wdt.py — Phase 6a-3 SoC-level watchdog test (bead claude_verilog_test-f7vs.7
steps 4-5, docs/PHASE6_IP_EXPANSION_PLAN.md §10).

`test_wdt` (tb_wdt.sv / Makefile `wdt` target) drives watchdog_timer's APB4 face directly and has
never exercised it through the real fabric path:

  CPU -> axi4_crossbar -> axi4_to_axilite -> axi_lite_interconnect ->
  axil_to_apb -> apb_interconnect -> APB slave 9 (APB_WDT, 0x2000_C000)

nor the two things that only exist once the WDT is inside soc_top: its IRQ into
interrupt_controller bit 7, and its bite feeding the CPU-domain reset. Firmware comes from a
committed pure-Python hand-assembler (wdt_fw/gen_wdt_hex.py) — no riscv32 cross toolchain, so the
suite is CI-safe. Synchronisation and scoring are by commit_pc_o marker PCs, the technique
test_soc_pwm.py / test_soc_gpio.py use.

Two tests, one image each:

test_soc_wdt  (image A, RST_EN = 0 — the reset default)
  Firmware arms the interrupt path, enables the dog, polls WDT_COUNT over the fabric until it has
  halved, FEEDS it, reads COUNT straight back (must be a reload) — then stops feeding. The dog
  barks, IRQ -> interrupt_controller[7] -> CPU MEIP -> ISR #1; the counter runs a second full
  period; the dog bites, wdt_rst_req_o rises at the SoC boundary, ISR #2. Scored here, from the
  boundary, independently of the firmware's own self-checks:
    * wdt_irq / wdt_rst_req_o stay LOW through the feed and until the (fed) bark. The bark lands
      about a full period after the FEED, not after the enable — i.e. the un-fed deadline was
      really passed and survived. Timing of the bark relative to the feed pins the FEED write
      having reached slave 9 through the whole fabric.
    * bark -> bite is exactly (PRESCALE+1)*RELOAD + 1 core_clk edges, the RTL contract at the
      SoC boundary — which pins the PRESCALE and RELOAD writes too.
    * the CPU takes EXACTLY TWO traps (ISR_PC commits twice): the first with wdt_irq/ext_irq
      asserted and wdt_rst_req_o low, the second with wdt_rst_req_o high. After each, wdt_irq and
      ext_irq deassert (clear-what-you-saw ISR; see the generator header), and no third trap
      follows (a stale level-held IRQ would produce one).
    * wdt_rst_req_o is level-held after the bite (the WDT was not reset, and W1C of STATUS[1]
      does not drop it).
    * THE RST_EN = 0 CLAIM: with a bite having happened, cpu_domain_rst_n never falls, and the
      internal reset-request flop and the RST_EN shadow stay 0 — the new reset path is inert by
      default, so it cannot have perturbed any other suite.
    * backdoor SRAM read: ISR_COUNT == 2, LOG[0] == 0x1 (bark only), LOG[1] == 0x2 (bite only).

test_soc_wdt_rst_en  (image B, RST_EN = 1)
  Firmware enables the dog with CTRL = EN | RST_EN and spins committing LOOP_PC. Scored here:
    * before the bite the CPU commits normally and cpu_domain_rst_n is high;
    * once wdt_rst_req_o rises, cpu_domain_rst_n falls within a few cycles and the CPU stops
      committing for good;
    * the reset is CPU-DOMAIN-ONLY: core_rst_n and cpu_core_rst_n never fall, and wdt_rst_req_o
      stays high — a whole-SoC reset would have cleared the WDT and dropped it;
    * this is a bite, not a bark: nothing happens at the bark.

GOLDEN-MODEL NOTE (same as test_soc_gpio / test_soc_pwm): SoCModel cannot be used here since it
rejects 0x2000_xxxx MMIO. Image A is self-checking and the testbench scoreboards commit_pc_o for
the marker PCs / PASS_PC / FAIL_PC.
"""

import sys
from pathlib import Path

import cocotb
from cocotb.triggers import RisingEdge, ReadOnly

from soc_clocks import drive_soc_reset, start_soc_clocks

_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from tb.cocotb.soc.wdt_fw.wdt_fw_addrs import (
    PASS_PC,
    FAIL_PC,
    ISR_PC,
    IRQ_READY_PC,
    CONFIG_DONE_PC,
    FED_PC,
    FEEDING_STOPPED_PC,
    PERIOD_CYCLES,
    ISR_COUNT_WI,
    ISR_LOG0_WI,
    ISR_LOG1_WI,
    B_CONFIG_DONE_PC,
    B_LOOP_PC,
    B_PERIOD_CYCLES,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
CLK_PERIOD_NS = 2  # 500 MHz — matches other SoC tests

_FW_DIR = Path(__file__).parent / "wdt_fw"
_FW_A_HEX = str(_FW_DIR / "wdt_fw.hex")
_FW_B_HEX = str(_FW_DIR / "wdt_rst_fw.hex")

# Image A: ~2 periods + fabric-latency MMIO set-up + the settle and D-cache-flush delay loops.
WDT_TEST_TIMEOUT_CYCLES = 60_000

# Cycles after an ISR entry before checking that the IRQ lines have deasserted. The ISR issues a
# STATUS read, an IRQ_CLR write and a STATUS read-back, each a full fabric round trip, before
# MRET; this is comfortably larger than that yet far below one period (800), so the bite cannot
# re-assert the line inside the window for the first trap.
DEASSERT_CHECK_DELAY_CYCLES = 400

# Bark -> bite: the RTL contract is (P+1)*R + 1 core_clk edges (watchdog_timer.sv header). Both
# events are core_clk flops sampled on the same clk_i, so this is exact at the boundary; +/-1
# only absorbs which side of the edge the ReadOnly sample falls.
BARK_TO_BITE_TOL = 1

# Feed -> bark: one full period from the moment the FEED write lands in the WDT, plus the
# (P+1)*R+2 timeout latency. The FED marker's commit_pc_o is not the write landing — it can lead
# or lag it by the fabric/commit latency (measured 791 for a period of 800) — so this is a
# +/-40 cycle window around one period. That pins "one period after the feed", far from the
# un-fed case (which would bark ~one period after the ENABLE, some 470 cycles earlier).
FEED_TO_BARK_MIN = PERIOD_CYCLES - 40
FEED_TO_BARK_MAX = PERIOD_CYCLES + 40

# Image B.
B_TEST_TIMEOUT_CYCLES = 6_000
# rst_req rises -> cpu_domain_rst_n falls: one core_clk flop (wdt_cpu_rst_req_q) then an ASYNC
# assert through cdc_reset_sync into an AND — a couple of cycles at most.
B_RESET_ASSERT_MAX_CYCLES = 4
# After the reset asserts, allow the in-flight commit(s) to drain (u_cpu's reset is synchronous
# on cpu_gated_clk) before demanding silence.
B_COMMIT_DRAIN_CYCLES = 8
B_SILENCE_WINDOW_CYCLES = 300

_active_tasks: list = []


def _kill_active_tasks() -> None:
    global _active_tasks
    for t in _active_tasks:
        t.kill()
    _active_tasks = []


def _read_hex(path: str) -> list:
    words: list = []
    with open(path) as f:
        for line in f:
            tok = line.strip()
            if not tok or tok.startswith("//") or tok.startswith("@"):
                continue
            words.append(int(tok, 16))
    return words


def _load_rom(dut, hex_path: str) -> None:
    mem = dut.u_soc.u_boot_rom.mem
    words = _read_hex(hex_path)
    assert len(words) <= len(mem), (
        f"Firmware image {hex_path} ({len(words)} words) exceeds boot ROM capacity "
        f"({len(mem)} words) — regenerate with wdt_fw/gen_wdt_hex.py"
    )
    for i, word in enumerate(words):
        mem[i].value = word


async def _setup(dut, hex_path: str) -> None:
    """Start clocks, idle inputs, backdoor-load firmware, apply + release reset."""
    _kill_active_tasks()

    clk_task, cpu_clk_task = start_soc_clocks(dut, CLK_PERIOD_NS)
    _active_tasks.append(clk_task)
    _active_tasks.append(cpu_clk_task)

    drive_soc_reset(dut, True)
    dut.apb_paddr_i.value   = 0
    dut.apb_psel_i.value    = 0
    dut.apb_penable_i.value = 0
    dut.apb_pwrite_i.value  = 0
    dut.apb_pwdata_i.value  = 0
    dut.uart_rx_i.value     = 1
    dut.spi_miso_i.value    = 0
    dut.gpio_in_i.value     = 0

    _load_rom(dut, hex_path)

    for _ in range(5):
        await RisingEdge(dut.clk_i)

    drive_soc_reset(dut, False)

    for _ in range(2):
        await RisingEdge(dut.clk_i)


def _i(sig) -> int:
    return int(sig.value)


@cocotb.test()
async def test_soc_wdt(dut):
    """Feed, starve, bark, bite through the real SoC fabric; RST_EN = 0 leaves the CPU alone."""
    await _setup(dut, _FW_A_HEX)

    seen = {"irq_ready": False, "config_done": False, "fed": False, "stopped": False}
    cfg_cycle = fed_cycle = None
    bark_cycle = bite_cycle = None
    isr_entries: list = []          # (cycle, wdt_irq, ext_irq, rst_req) at each ISR_PC commit
    deassert_checked = [False, False]
    saw_pass = False
    prev_irq = 0
    prev_req = 0
    cpu_reset_dips = 0              # cpu_core_rst_n high but cpu_domain_rst_n low (must stay 0)
    wdt_term_low = 0                # cpu_core_rst_n high but the WDT reset term low (must stay 0)
    path_inert_violations = 0       # wdt_cpu_rst_req_q / wdt_rst_en_w ever high

    last_pc = 0
    recent: list = []

    for cycle_idx in range(WDT_TEST_TIMEOUT_CYCLES):
        await RisingEdge(dut.clk_i)
        await ReadOnly()

        wdt_irq = _i(dut.u_soc.wdt_irq)
        ext_irq = _i(dut.u_soc.ext_irq)
        rst_req = _i(dut.wdt_rst_req_o)

        # Boundary edges, independent of commit_pc_o.
        if wdt_irq and not prev_irq and bark_cycle is None:
            bark_cycle = cycle_idx
        if rst_req and not prev_req and bite_cycle is None:
            bite_cycle = cycle_idx
        if prev_req and not rst_req:
            raise AssertionError("wdt_rst_req_o dropped after the bite — it must be level-held")
        prev_irq, prev_req = wdt_irq, rst_req

        # Not yet fed-and-starved: nothing may fire early. Before the FED marker (and, for the
        # bite, before the bark) the lines must be quiet.
        if seen["config_done"] and bark_cycle is None:
            assert rst_req == 0, "wdt_rst_req_o asserted before the bark"
        # The RST_EN = 0 claim, checked from COLD BOOT rather than from some later point: as soon
        # as this domain's own reset (cpu_core_rst_n) is released, the WDT term must already be
        # high and cpu_domain_rst_n must already equal it — i.e. the new AND-in term never
        # holds the CPU in reset one cycle longer than it was held before the WDT existed.
        if _i(dut.u_soc.cpu_core_rst_n):
            if _i(dut.u_soc.cpu_domain_rst_n) == 0:
                cpu_reset_dips += 1
                assert False, (
                    f"cpu_domain_rst_n fell at cycle {cycle_idx} while cpu_core_rst_n was high, "
                    f"with RST_EN == 0 (wdt_rst_req_o={rst_req}) — the WDT reset path is not "
                    f"inert by default"
                )
            if _i(dut.u_soc.wdt_cpu_rst_n_cpu_sync) == 0:
                wdt_term_low += 1
                assert False, (
                    f"wdt_cpu_rst_n_cpu_sync low at cycle {cycle_idx} while cpu_core_rst_n was "
                    f"high, with RST_EN == 0 — the WDT term delayed the CPU-domain reset release"
                )
        # wdt_rst_en_w is watchdog_timer's rst_en_o port (bead f7vs.14 replaced the
        # earlier bus-snooped wdt_rst_en_shadow_q with a real port; the assertion's
        # intent -- the WDT reset term stays inert with RST_EN == 0 -- is unchanged).
        if _i(dut.u_soc.wdt_cpu_rst_req_q) or _i(dut.u_soc.wdt_rst_en_w):
            path_inert_violations += 1

        if dut.commit_valid_o.value:
            pc = int(dut.commit_pc_o.value)
            last_pc = pc
            recent.append(pc)
            if len(recent) > 16:
                recent.pop(0)

            assert pc != FAIL_PC, (
                f"firmware reached FAIL_PC at 0x{pc:08x} — a WDT SoC-level check failed "
                f"(or a bounded poll timed out)"
            )

            if pc == IRQ_READY_PC and not seen["irq_ready"]:
                seen["irq_ready"] = True
            if pc == CONFIG_DONE_PC and not seen["config_done"]:
                seen["config_done"] = True
                cfg_cycle = cycle_idx
                assert wdt_irq == 0 and rst_req == 0, "WDT already firing at CONFIG_DONE"
            if pc == FED_PC and not seen["fed"]:
                seen["fed"] = True
                fed_cycle = cycle_idx
                assert bark_cycle is None, (
                    f"the dog barked (cycle {bark_cycle}) BEFORE the feed committed at {cycle_idx} "
                    f"— firmware fed too late, or COUNT is not what the feed poll thinks"
                )
            if pc == FEEDING_STOPPED_PC and not seen["stopped"]:
                seen["stopped"] = True
                assert bark_cycle is None, "bark before feeding stopped: the feed did not take"

            if pc == ISR_PC:
                assert len(isr_entries) < 2, (
                    f"CPU took a THIRD trap (ISR_PC committed at cycle {cycle_idx}) — a stale "
                    f"level-held WDT/ext IRQ re-vectored after MRET"
                )
                isr_entries.append((cycle_idx, wdt_irq, ext_irq, rst_req))
                n = len(isr_entries)
                assert wdt_irq == 1, f"trap #{n}: CPU vectored but u_soc.wdt_irq is not asserted"
                assert ext_irq == 1, f"trap #{n}: CPU vectored but u_soc.ext_irq is not asserted"
                if n == 1:
                    assert rst_req == 0, "trap #1 (bark) but wdt_rst_req_o already high"
                else:
                    assert rst_req == 1, "trap #2 (bite) but wdt_rst_req_o is not high"

            if pc == PASS_PC:
                saw_pass = True
                break

        for k, (ecyc, _, _, _) in enumerate(isr_entries):
            if not deassert_checked[k] and cycle_idx >= ecyc + DEASSERT_CHECK_DELAY_CYCLES:
                deassert_checked[k] = True
                assert wdt_irq == 0, (
                    f"u_soc.wdt_irq still asserted {DEASSERT_CHECK_DELAY_CYCLES} cycles after ISR "
                    f"#{k + 1} — the W1C clear did not deassert the source"
                )
                assert ext_irq == 0, (
                    f"u_soc.ext_irq still asserted {DEASSERT_CHECK_DELAY_CYCLES} cycles after "
                    f"ISR #{k + 1}"
                )

    if not saw_pass:
        dut._log.info(
            "last_pc=0x%08x; recent committed PCs: %s",
            last_pc, " ".join(f"0x{p:08x}" for p in recent),
        )

    assert saw_pass, (
        f"PASS_PC (0x{PASS_PC:08x}) never committed within {WDT_TEST_TIMEOUT_CYCLES} cycles"
    )
    for name, ok in seen.items():
        assert ok, f"marker {name} was never committed"
    assert len(isr_entries) == 2, f"expected exactly 2 traps (bark, bite), got {len(isr_entries)}"
    assert all(deassert_checked), f"deassert windows not all reached: {deassert_checked}"

    # ---- boundary timing ------------------------------------------------------------------
    assert bark_cycle is not None, "wdt_irq never rose"
    assert bite_cycle is not None, "wdt_rst_req_o never rose"
    feed_to_bark = bark_cycle - fed_cycle
    cfg_to_bark = bark_cycle - cfg_cycle
    bark_to_bite = bite_cycle - bark_cycle
    dut._log.info(
        f"timing: cfg->fed={fed_cycle - cfg_cycle} feed->bark={feed_to_bark} "
        f"cfg->bark={cfg_to_bark} bark->bite={bark_to_bite} (period={PERIOD_CYCLES})"
    )
    assert cfg_to_bark > PERIOD_CYCLES + PERIOD_CYCLES // 4, (
        f"bark came {cfg_to_bark} cycles after the enable — within the UN-FED deadline "
        f"(~{PERIOD_CYCLES}); the feed did not reload the counter"
    )
    assert FEED_TO_BARK_MIN <= feed_to_bark <= FEED_TO_BARK_MAX, (
        f"bark {feed_to_bark} cycles after the feed, expected one period "
        f"[{FEED_TO_BARK_MIN}, {FEED_TO_BARK_MAX}]"
    )
    expect_gap = PERIOD_CYCLES + 1
    assert abs(bark_to_bite - expect_gap) <= BARK_TO_BITE_TOL, (
        f"bark->bite = {bark_to_bite} cycles, RTL contract is (P+1)*R+1 = {expect_gap}"
    )

    # ---- RST_EN = 0: the reset path is inert --------------------------------------------------
    assert cpu_reset_dips == 0, (
        f"cpu_domain_rst_n was low for {cpu_reset_dips} cycle(s) while cpu_core_rst_n was high, "
        f"with RST_EN == 0 — the WDT reset path is not inert by default"
    )
    assert wdt_term_low == 0, (
        f"wdt_cpu_rst_n_cpu_sync was low for {wdt_term_low} cycle(s) while cpu_core_rst_n was "
        f"high, with RST_EN == 0 — the WDT term delayed the CPU-domain reset release"
    )
    assert path_inert_violations == 0, (
        f"wdt_cpu_rst_req_q / wdt_rst_en_w went high {path_inert_violations} time(s) "
        f"with RST_EN == 0"
    )
    assert _i(dut.wdt_rst_req_o) == 1, "wdt_rst_req_o is not level-held at PASS"

    # ---- backdoor SRAM ------------------------------------------------------------------------
    sram = dut.u_soc.u_sram.mem
    count = int(sram[ISR_COUNT_WI].value)
    log0 = int(sram[ISR_LOG0_WI].value)
    log1 = int(sram[ISR_LOG1_WI].value)
    assert count == 2, f"backdoor SRAM: ISR_COUNT = {count}, expected exactly 2"
    assert log0 == 0x1, f"backdoor SRAM: LOG[0] = 0x{log0:x}, expected 0x1 (bark only)"
    assert log1 == 0x2, f"backdoor SRAM: LOG[1] = 0x{log1:x}, expected 0x2 (bite only)"


@cocotb.test()
async def test_soc_wdt_rst_en(dut):
    """RST_EN = 1: the bite resets the CPU domain — and only the CPU domain."""
    await _setup(dut, _FW_B_HEX)

    config_done = False
    cfg_cycle = None
    bite_cycle = None
    fall_cycle = None
    last_commit_cycle = None
    loop_commits_before_bite = 0
    bark_seen = False
    prev_irq = 0
    window_end = None

    for cycle_idx in range(B_TEST_TIMEOUT_CYCLES):
        await RisingEdge(dut.clk_i)
        await ReadOnly()

        wdt_irq = _i(dut.u_soc.wdt_irq)
        rst_req = _i(dut.wdt_rst_req_o)
        dom_rst = _i(dut.u_soc.cpu_domain_rst_n)

        if wdt_irq and not prev_irq:
            bark_seen = True
        prev_irq = wdt_irq

        if dut.commit_valid_o.value:
            pc = int(dut.commit_pc_o.value)
            last_commit_cycle = cycle_idx
            if pc == B_CONFIG_DONE_PC and not config_done:
                config_done = True
                cfg_cycle = cycle_idx
            if pc == B_LOOP_PC and bite_cycle is None:
                loop_commits_before_bite += 1

        if bite_cycle is None:
            if config_done:
                assert dom_rst == 1, (
                    f"cpu_domain_rst_n low at cycle {cycle_idx} BEFORE any bite — the reset path "
                    f"fired early"
                )
            if rst_req:
                bite_cycle = cycle_idx
                assert config_done, "wdt_rst_req_o rose before firmware enabled the dog"
        else:
            # After the bite: the reset must assert promptly, and stay asserted.
            if fall_cycle is None:
                if dom_rst == 0:
                    fall_cycle = cycle_idx
                    window_end = cycle_idx + B_COMMIT_DRAIN_CYCLES + B_SILENCE_WINDOW_CYCLES
                else:
                    assert cycle_idx - bite_cycle <= B_RESET_ASSERT_MAX_CYCLES, (
                        f"cpu_domain_rst_n still high {cycle_idx - bite_cycle} cycles after "
                        f"wdt_rst_req_o rose — the bite is not resetting the CPU domain"
                    )
            else:
                assert dom_rst == 0, (
                    f"cpu_domain_rst_n released at cycle {cycle_idx} — the reset must be "
                    f"level-held until an external reset"
                )
                # CPU-DOMAIN ONLY: nothing else may reset, and the WDT itself must survive.
                assert _i(dut.u_soc.core_rst_n) == 1, "core_rst_n fell: whole-SoC/fabric reset"
                assert _i(dut.u_soc.cpu_core_rst_n) == 1, "cpu_core_rst_n fell: not CPU-domain only"
                assert rst_req == 1, (
                    "wdt_rst_req_o dropped — the WDT itself was reset (a whole-SoC reset), or "
                    "the level-held request was lost"
                )
                if cycle_idx >= fall_cycle + B_COMMIT_DRAIN_CYCLES:
                    assert not dut.commit_valid_o.value, (
                        f"CPU still committing at cycle {cycle_idx}, "
                        f"{cycle_idx - fall_cycle} cycles into its reset"
                    )
                if cycle_idx >= window_end:
                    break

    assert config_done, "B_CONFIG_DONE_PC was never committed"
    assert bite_cycle is not None, "wdt_rst_req_o never rose"
    assert fall_cycle is not None, "cpu_domain_rst_n never fell"
    assert window_end is not None and cycle_idx >= window_end, "silence window not completed"
    assert bark_seen, "the bark (wdt_irq) never appeared before the bite"
    assert loop_commits_before_bite > 10, (
        f"CPU committed the spin loop only {loop_commits_before_bite} times before the bite — "
        f"it was not really running"
    )
    dut._log.info(
        f"RST_EN path: cfg={cfg_cycle} bite={bite_cycle} cpu_domain_rst_n fell at {fall_cycle} "
        f"(+{fall_cycle - bite_cycle}); {loop_commits_before_bite} loop commits before the bite; "
        f"last commit at {last_commit_cycle} (period={B_PERIOD_CYCLES})"
    )
