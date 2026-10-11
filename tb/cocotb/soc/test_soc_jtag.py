"""
test_soc_jtag.py -- bead claude_verilog_test-j41m.3 (DFT Stage 1b), SoC level.

DUT: tb_soc_pll -> soc_top (PLL_IMPL=STUB), driven through the new JTAG pins tck_i / tms_i / tdi_i /
trst_ni / tdo_o / tdo_oe_o, in the style of test_soc_dft_scan.py (Stage 1a, NOT modified and
keeps proving the pin path).  What is observable at a port is checked at the port (pll_locked_o,
cpu_pll_locked_o, tdo_o, tdo_oe_o, commit_valid_o); internal nets are read through hierarchy
(--public-flat-rw is on for every suite in this Makefile).

What this proves, and what it does not
  * PROVES  the TAP is wired into soc_top: IDCODE comes out of tdo_o with tdo_oe_o framing;
    selecting
    SCAN through the TAP gives the SAME clock/reset control as the 1a pins (PLL lock counters
    advance
    on the TAP-generated test clock with clk_i / cpu_clk_i stopped and are deaf to them, the four
    domain resets equal the scan reset and ignore the functional pins, the CPU clock gate is forced
    open, the crypto key read nets are masked); and that the TAP cannot disturb functional
    mode: with
    the TAP held in reset, with TRST_N high and TCK toggling in Test-Logic-Reset, and with arbitrary
    SCAN_SEL / SCAN_RST contents written while IR != SCAN, the CPU keeps committing and every
    DFT net
    stays at its functional value.
  * DOES NOT prove the structural all-nets claims (tools/dft/check_scan_clk_rst.py) or any chain
    behaviour: there are no chains until Stage 2.  The two 1a PMU-power-down scan tests are not
    re-run through the TAP: they exercise dft_rst_mux, which is driven by the same dft_scan_mode /
    dft_scan_rst_n nets proven here.

Timing contract (docs/design/DFT_ARCHITECTURE.md 15.4): the TAP's scan clock exists only on TCK
edges that end Capture-DR and Shift-DR, so "N test clocks" below means one DR scan of N-1 bits (1
capture + N-1 shifts), counted from the dft_test_clk net.

Tests
  test_jtag_idcode_and_oe_through_the_soc      IDCODE on tdo_o, tdo_oe_o framing, vs model
  test_boot_with_tap_held_in_reset             CPU commits, DFT nets functional (trst_ni = 0)
  test_boot_with_tck_toggling_in_tlr           trst_ni = 1, TCK toggling with TMS=1: same
  test_tdr_contents_cannot_disturb_functional_mode
                                               all SCAN_SEL x SCAN_RST values written with
                                               IR != SCAN while the CPU runs: clocks, resets, key
                                               mask unchanged, commits continue; negative control:
                                               IR=SCAN flips them; exit via TLR restores and the
                                               CPU re-boots
  test_tap_scan_runs_on_the_tap_test_clock_only
                                               clk_i/cpu_clk_i stopped: 11 test clocks leave both
                                               PLL lock counters short, 22 lock them
  test_tap_scan_ignores_functional_clocks      running clk_i/cpu_clk_i move nothing in TAP scan
  test_tap_parallel_select_uses_scan_clk_i     SCAN_SEL.PARALLEL: TCK ignored, scan_clk_i counts
  test_tap_scan_reset_follows_pin_and_tap      4 domain resets == scan_rst_ni AND NOT SCAN_RST
  test_cpu_clock_gate_forced_open_via_tap      gated CPU clock edges == test clock edges, enable 0
  test_crypto_key_mask_follows_tap_scan_mode   key_eff = 0 in TAP scan, key_q untouched, restored
  test_exit_scan_restores_functional_via_tlr_and_trst
                                               5xTMS, IR change and async TRST_N all hand the
                                               resets back to the functional pins
  test_serial_parallel_switching_is_glitch_free_in_the_soc
                                               serial <-> parallel x3 with scan_clk_i running: no
                                               short pulse on dft_test_clk (glitch-free switch)

Note on the glitch-free test-clock switch (dft_clk_switch, replaced the plain test_clk mux): no
count above had to change.  Every existing test either never goes serial -> parallel with the pin
clock counted afterwards, or enters PARALLEL from the reset state where the pin clock is already
selected, so the pin clock's first two rising edges are not consumed by a handshake.  The one
consequence that matters, for new tests: after serial -> parallel the pin clock needs about 3 cycles
before its first pulse reaches dft_test_clk (and with the pin clock stopped throughout, none is
consumed), so lock-counter tests count edges from the dft_test_clk log, not from pin toggles.
"""

import sys
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, FallingEdge, ReadOnly, RisingEdge, Timer
from cocotb.utils import get_sim_time
from jtag_driver import (
    IDCODE_VAL,
    OP_BYPASS,
    OP_EXTEST,
    OP_IDCODE,
    OP_MBIST_CTRL,
    OP_SAMPLE,
    OP_SCAN,
    OP_SCAN_RST,
    OP_SCAN_SEL,
    EdgeLog,
    JtagDriver,
    check_enable_latches,
    check_handover,
    events_of,
    label_output_pulses,
    pulses_of,
)
from soc_clocks import drive_dft_inactive, drive_soc_reset, start_soc_clocks

_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from sim.riscv_encoder import ADDI, JAL  # noqa: E402

CLK_NS = 4  # clk_i == cpu_clk_i (1:1), coprime to TCK
TCK_NS = 11
PIN_CLK_NS = 3
LOCK_CYCLES = 16  # STUB_LOCK_CYCLES in soc_top
KEY = 0x2B7E151628AED2A6ABF7158809CF4F3C  # FIPS-197 Appendix B key (deposited, observability only)
SCAN_NETS = ("core_rst_n", "cpu_core_rst_n", "cpu_domain_rst_n", "gpu_domain_rst_n")


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _tap_probe(dut):
    return {
        "tdo": int(dut.tdo_o.value),
        "tdo_oe": int(dut.tdo_oe_o.value),
        "state": int(dut.u_soc.u_dft_ctrl.tap_state.value),
    }


def _make_driver(dut):
    return JtagDriver(
        dut.tck_i, dut.tms_i, dut.tdi_i, dut.trst_ni, dut.tdo_o, period_ns=TCK_NS,
        probe=lambda: _tap_probe(dut), name="soc_tap",
    )  # fmt: skip


async def _idle(dut):
    """Everything inactive, all clocks stopped; the TAP in reset (the idle value of every suite)."""
    drive_dft_inactive(dut)
    dut.clk_i.value = 0
    dut.cpu_clk_i.value = 0
    dut.rst_n_i.value = 1
    dut.cpu_rst_n_i.value = 1
    for name in ("apb_psel_i", "apb_penable_i", "apb_pwrite_i", "uart_rx_i", "spi_miso_i"):
        getattr(dut, name).value = 0
    dut.apb_paddr_i.value = 0
    dut.apb_pwdata_i.value = 0
    await Timer(2, units="ns")


def _load_loop_firmware(dut):
    """ADDI x1,x1,1 ; JAL x0,-4 at the reset PC: commits forever, no MMIO, no EBREAK."""
    mem = dut.u_soc.u_boot_rom.mem
    for i, w in enumerate((ADDI(1, 1, 1), JAL(0, -4))):
        mem[i].value = w


async def _boot_cpu(dut):
    """Reset, load the loop firmware, start both clocks 1:1, release reset, wait for the first
    commit.  TAP pins as left by drive_dft_inactive (held in reset) unless changed."""
    await _idle(dut)
    _load_loop_firmware(dut)
    drive_soc_reset(dut, True)
    tasks = start_soc_clocks(dut, CLK_NS)
    await ClockCycles(dut.clk_i, 6)
    drive_soc_reset(dut, False)
    return tasks


class _Monitor:
    """Counts commits and records functional-net violations, sampled every clk_i rising edge."""

    def __init__(self, dut, check=None):
        self.dut, self.check = dut, check
        self.commits = 0
        self.cycles = 0
        self.violations = []
        self._task = None

    async def _run(self):
        d = self.dut
        while True:
            await RisingEdge(d.clk_i)
            await ReadOnly()
            self.cycles += 1
            self.commits += int(d.commit_valid_o.value)
            if self.check is not None:
                self.violations.extend(self.check(d))

    def start(self):
        self._task = cocotb.start_soon(self._run())
        return self

    def stop(self):
        if self._task is not None:
            self._task.kill()
            self._task = None


async def _wait_commits(dut, mon, n, timeout_cycles=4000):
    start = mon.commits
    for _ in range(timeout_cycles):
        if mon.commits - start >= n:
            return
        await RisingEdge(dut.clk_i)
    raise AssertionError(
        f"CPU committed only {mon.commits - start}/{n} instructions in {timeout_cycles} cycles"
    )


async def _deposit_key(dut):
    """Deposit the observability key into key_q and PROVE it is visible on key_eff_w before any
    monitor looks (a deposit is not applied until the next simulator phase, and a monitor that
    samples first would report a mask that is not there)."""
    # _boot_cpu returns right after reset release; the peripheral reset synchronisers are still
    # asserting for a few cycles and would clear a deposit made now, so let them release first.
    await ClockCycles(dut.clk_i, 30)
    dut.u_soc.u_crypto.key_q.value = KEY
    await Timer(1, units="ns")
    got = int(dut.u_soc.u_crypto.key_eff_w.value)
    assert got == KEY, f"precondition: key_eff_w={got:#x} after depositing key_q"


# The loop firmware is two instructions with a taken JAL, so the CPU retires about 0.28
# instructions per clock (measured: 85 commits / 300 cycles, 118 / ~420). The floor is a
# stalled-CPU detector, not a performance claim: half that rate, over whatever window ran.
_MIN_IPC = 0.14


def _assert_commit_rate(mon, c0, cy0, what):
    commits, cycles = mon.commits - c0, mon.cycles - cy0
    assert cycles > 0 and commits >= _MIN_IPC * cycles, (
        f"CPU stalled ({what}): {commits} commits in {cycles} clk_i cycles"
    )


def _functional_nets(dut):
    """DFT nets that must sit at their functional value; returns violation strings."""
    soc, bad = dut.u_soc, []
    if int(soc.dft_scan_mode.value):
        bad.append("dft_scan_mode=1")
    if int(soc.dft_test_en.value):
        bad.append("dft_test_en=1")
    if int(soc.dft_scan_en.value):
        bad.append("dft_scan_en=1")
    if not int(soc.dft_scan_rst_n.value):
        bad.append("dft_scan_rst_n=0")
    if int(soc.dft_test_clk.value):
        bad.append("dft_test_clk=1")
    if int(soc.u_crypto.key_eff_w.value) != KEY:
        bad.append("crypto key mask active")
    return bad


async def _tap_power_up(dut):
    drv = _make_driver(dut)
    await drv.start()
    return drv


async def _enter_scan_released(drv, dut, sel=0):
    """Reach IR=SCAN with the scan reset RELEASED, via the TAP only: first assert it (SCAN_RST=1
    under IR=SCAN: counters/resets clear, as 1a does with scan_rst_ni=0), then leave scan, clear
    SCAN_RST and re-enter."""
    await drv.enter_scan(sel=sel, rst=1)
    assert int(dut.u_soc.dft_scan_mode.value) == 1 and int(dut.u_soc.dft_scan_rst_n.value) == 0, (
        "precondition: TAP scan with SCAN_RST=1 must assert the scan reset"
    )
    await drv.write_tdr(OP_SCAN_RST, 0, 1)
    await drv.load_ir(OP_SCAN)
    assert int(dut.u_soc.dft_scan_mode.value) == 1 and int(dut.u_soc.dft_scan_rst_n.value) == 1


async def _toggle(sig, n, half_ns=5):
    for _ in range(n):
        sig.value = 1
        await Timer(half_ns, units="ns")
        sig.value = 0
        await Timer(half_ns, units="ns")


# ---------------------------------------------------------------------------
@cocotb.test()
async def test_jtag_idcode_and_oe_through_the_soc(dut):
    """The TAP is wired to the top: IDCODE on tdo_o, framed by tdo_oe_o, model-checked."""
    await _idle(dut)
    drv = await _tap_power_up(dut)
    oe_seen = []
    drv.post_tick_hooks.append(lambda d: oe_seen.append(int(dut.tdo_oe_o.value)))
    assert await drv.shift_dr(0, 32) == IDCODE_VAL, "IDCODE did not come out of tdo_o"
    assert drv.last_bits[0] == 1
    assert sum(oe_seen) >= 32 and 0 in oe_seen, (
        "tdo_oe_o must be high during Shift-DR and low outside"
    )
    assert await drv.shift_ir(OP_BYPASS) == 0b0001, "IR capture pattern on tdo_o"


# ---------------------------------------------------------------------------
@cocotb.test()
async def test_boot_with_tap_held_in_reset(dut):
    """TAP held in reset (trst_ni=0, tck=0, tms=1): the CPU runs, every DFT net is functional."""
    await _boot_cpu(dut)
    await _deposit_key(dut)
    mon = _Monitor(dut, _functional_nets).start()
    log = EdgeLog({"test_clk": dut.u_soc.dft_test_clk}, dut.tck_i).start()
    await _wait_commits(dut, mon, 50)
    c0, cy0 = mon.commits, mon.cycles
    await ClockCycles(dut.clk_i, 300)
    _assert_commit_rate(mon, c0, cy0, "TAP held in reset")
    assert not mon.violations, f"DFT net left its functional value: {mon.violations[:5]}"
    assert (
        int(dut.trst_ni.value) == 0 and int(dut.tdo_oe_o.value) == 0 and int(dut.tdo_o.value) == 0
    )
    assert int(dut.pll_locked_o.value) == 1 and int(dut.cpu_pll_locked_o.value) == 1
    assert log.count("test_clk") == 0
    mon.stop()
    log.stop()


@cocotb.test()
async def test_boot_with_tck_toggling_in_tlr(dut):
    """trst_ni=1, TMS=1, TCK toggling (coprime to the core clock): TAP in TLR, SoC unaffected."""
    await _boot_cpu(dut)
    await _deposit_key(dut)
    mon = _Monitor(dut, _functional_nets).start()
    log = EdgeLog({"test_clk": dut.u_soc.dft_test_clk}, dut.tck_i).start()
    await _wait_commits(dut, mon, 50)
    drv = await _tap_power_up(dut)  # trst_ni -> 1, TCK toggling with TMS=1
    c0, cy0 = mon.commits, mon.cycles
    for _ in range(150):
        await drv.tick(1)
        assert int(dut.u_soc.u_dft_ctrl.tap_state.value) == 0xF
    assert drv.n_ticks >= 150 and drv.ref.state == "TLR"
    _assert_commit_rate(mon, c0, cy0, "TCK toggling in TLR")
    assert not mon.violations, f"DFT net disturbed by TCK in TLR: {mon.violations[:5]}"
    assert log.count("test_clk") == 0, "TCK reached the scan clock in Test-Logic-Reset"
    mon.stop()
    log.stop()


# ---------------------------------------------------------------------------
@cocotb.test()
async def test_tdr_contents_cannot_disturb_functional_mode(dut):
    """TDR contents written through the TAP with IR != SCAN change nothing; SCAN does."""
    await _boot_cpu(dut)
    soc = dut.u_soc
    await _deposit_key(dut)
    mon = _Monitor(dut, _functional_nets).start()
    log = EdgeLog({"test_clk": soc.dft_test_clk, "gclk": soc.cpu_gated_clk}, dut.tck_i).start()
    await _wait_commits(dut, mon, 50)
    drv = await _tap_power_up(dut)
    others = (OP_IDCODE, OP_BYPASS, OP_EXTEST, OP_SAMPLE, OP_MBIST_CTRL)
    writes = 0
    for sel in range(8):
        for rst in (0, 1):
            c0 = mon.commits
            await drv.write_tdr(OP_SCAN_SEL, sel, 3)
            await drv.write_tdr(OP_SCAN_RST, rst, 1)
            await drv.load_ir(others[(sel + rst) % len(others)])
            writes += 1
            assert mon.commits - c0 > 20, (
                f"CPU stopped committing during TAP traffic (sel={sel} rst={rst})"
            )
            assert int(soc.u_dft_ctrl.u_tap.scan_sel_q.value) == sel, (
                "precondition: SCAN_SEL really written"
            )
            assert int(soc.u_dft_ctrl.u_tap.scan_rst_q.value) == rst
    assert writes == 16 and mon.cycles > 1500
    assert not mon.violations, f"TDR contents disturbed functional mode: {mon.violations[:5]}"
    assert log.count("test_clk") == 0, "scan test clock moved with IR != SCAN"
    assert log.count("gclk") > 1000, (
        "vacuity guard: the CPU clock gate must be toggling functionally"
    )
    # negative control: the same monitor condition DOES fire once IR = SCAN is loaded (sel=7, rst=1
    # are still in the TDRs): SCAN_RST asserts the scan reset, scan_mode masks the key
    mon.stop()
    await drv.load_ir(OP_SCAN)
    assert int(soc.dft_scan_mode.value) == 1 and int(soc.dft_test_en.value) == 1
    assert int(soc.dft_scan_rst_n.value) == 0, "SCAN_RST=1 under IR=SCAN must assert the scan reset"
    assert int(soc.u_crypto.key_eff_w.value) == 0 and int(soc.u_crypto.key_q.value) == KEY
    assert _functional_nets(dut), "control: the functional-net check must see the scan state"
    # exit through Test-Logic-Reset: functional nets back, CPU re-boots and commits again
    await drv.reset_tms()
    # SCAN_RST=1 under SCAN really reset the crypto block (that is the scrub), so key_q is 0 now:
    # put the observability key back, after the scan reset has released, before judging the mask.
    await _deposit_key(dut)
    assert not _functional_nets(dut), (
        f"TLR did not restore functional mode: {_functional_nets(dut)}"
    )
    mon2 = _Monitor(dut, _functional_nets).start()
    await _wait_commits(dut, mon2, 50, timeout_cycles=6000)
    assert not mon2.violations
    mon2.stop()
    log.stop()


# ---------------------------------------------------------------------------
@cocotb.test()
async def test_tap_scan_runs_on_the_tap_test_clock_only(dut):
    """clk_i / cpu_clk_i stopped: the lock counters advance only on TAP-generated test clocks."""
    await _idle(dut)
    drv = await _tap_power_up(dut)
    await _enter_scan_released(drv, dut)
    soc = dut.u_soc
    assert int(dut.pll_locked_o.value) == 0 and int(dut.cpu_pll_locked_o.value) == 0, (
        "precondition: scan reset cleared both PLL lock counters"
    )
    log = EdgeLog({"test_clk": soc.dft_test_clk}, dut.tck_i, dut.trst_ni).start()
    await drv.shift_dr(0, 10)  # 1 capture + 10 shift edges = 11 test clocks
    n1 = sum(1 for e in log.events if e[0] == "test_clk" and e[3] == 1)
    assert n1 == 11, f"expected 11 test-clock pulses for a 10-bit DR scan, got {n1}"
    assert int(dut.pll_locked_o.value) == 0 and int(dut.cpu_pll_locked_o.value) == 0, (
        f"lock after only {n1} < {LOCK_CYCLES} test clocks"
    )
    await drv.shift_dr(0, 11)  # 12 more -> 23 in total
    n2 = sum(1 for e in log.events if e[0] == "test_clk" and e[3] == 1)
    assert n2 == 23
    assert int(dut.pll_locked_o.value) == 1, (
        "fabric PLL reference did not run on the TAP test clock"
    )
    assert int(dut.cpu_pll_locked_o.value) == 1, (
        "CPU PLL reference did not run on the TAP test clock"
    )
    log.stop()


@cocotb.test()
async def test_tap_scan_ignores_functional_clocks(dut):
    """TAP scan, clk_i and cpu_clk_i running: nothing advances; then a TAP DR scan does."""
    await _idle(dut)
    drv = await _tap_power_up(dut)
    await _enter_scan_released(drv, dut)
    assert int(dut.pll_locked_o.value) == 0 and int(dut.cpu_pll_locked_o.value) == 0
    t1 = cocotb.start_soon(Clock(dut.clk_i, CLK_NS, units="ns").start())
    t2 = cocotb.start_soon(Clock(dut.cpu_clk_i, CLK_NS, units="ns").start())
    await ClockCycles(dut.clk_i, 4 * LOCK_CYCLES)
    assert int(dut.pll_locked_o.value) == 0, "clk_i advanced the lock counter in TAP scan mode"
    assert int(dut.cpu_pll_locked_o.value) == 0, (
        "cpu_clk_i advanced the lock counter in TAP scan mode"
    )
    await drv.shift_dr(0, 22)  # negative control: the TAP test clock does lock them
    assert int(dut.pll_locked_o.value) == 1 and int(dut.cpu_pll_locked_o.value) == 1
    t1.kill()
    t2.kill()


@cocotb.test()
async def test_tap_parallel_select_uses_scan_clk_i(dut):
    """SCAN_SEL.PARALLEL: TCK activity no longer reaches the scan clock; scan_clk_i does."""
    await _idle(dut)
    drv = await _tap_power_up(dut)
    await _enter_scan_released(drv, dut, sel=0b001)
    soc = dut.u_soc
    assert int(soc.dft_scan_mode.value) == 1 and int(dut.pll_locked_o.value) == 0
    await drv.shift_dr(0, 30)  # TCK-driven DR scan with PARALLEL=1: no test clock
    assert int(dut.pll_locked_o.value) == 0 and int(dut.cpu_pll_locked_o.value) == 0, (
        "TCK leaked onto the scan clock in PARALLEL mode"
    )
    await _toggle(dut.scan_clk_i, LOCK_CYCLES + 6)
    assert int(dut.pll_locked_o.value) == 1 and int(dut.cpu_pll_locked_o.value) == 1, (
        "scan_clk_i did not drive the scan clock in PARALLEL mode"
    )


# ---------------------------------------------------------------------------
@cocotb.test()
async def test_tap_scan_reset_follows_pin_and_tap(dut):
    """In TAP scan every domain reset == scan_rst_ni AND NOT SCAN_RST, functional pins ignored."""
    await _idle(dut)
    drv = await _tap_power_up(dut)
    soc = dut.u_soc
    seen = set()
    for tap_rst in (0, 1):
        await drv.enter_scan(sel=0, rst=tap_rst)
        assert int(soc.dft_scan_mode.value) == 1
        for pin_rst in (1, 0, 1, 0):
            dut.scan_rst_ni.value = pin_rst
            want = pin_rst & (1 - tap_rst)
            # functional pins disagree with the scan reset on purpose
            dut.rst_n_i.value = 1 - want
            dut.cpu_rst_n_i.value = 1 - want
            await Timer(2, units="ns")
            for name in SCAN_NETS:
                got = int(getattr(soc, name).value)
                assert got == want, (
                    f"SCAN_RST={tap_rst} scan_rst_ni={pin_rst}: {name}={got}, expected {want}"
                )
            seen.add((tap_rst, pin_rst, want))
    assert {w for (_t, _p, w) in seen} == {0, 1}, (
        "vacuity guard: both reset levels must be observed"
    )
    dut.scan_rst_ni.value = 1
    dut.rst_n_i.value = 1
    dut.cpu_rst_n_i.value = 1


@cocotb.test()
async def test_cpu_clock_gate_forced_open_via_tap(dut):
    """TAP scan opens u_cpu_cg although its functional enable is 0; functional mode does not."""
    await _idle(dut)
    soc = dut.u_soc
    # closed-gate baseline: functional mode, CPU domain held in reset, cpu_clk_i running
    dut.cpu_rst_n_i.value = 0
    cpu_clk = cocotb.start_soon(Clock(dut.cpu_clk_i, CLK_NS, units="ns").start())
    glog = EdgeLog({"gclk": soc.cpu_gated_clk}, dut.cpu_clk_i).start()
    await ClockCycles(dut.cpu_clk_i, 10)
    # Informational baseline: asserted only when the functional enable really is 0 (it depends
    # on the PMU/reset history left by earlier tests); the closed-gate case proper is
    # test_clock_gate_scan's.
    if int(soc.cpu_gated_clk_en.value) == 0:
        assert glog.count("gclk") == 0, "baseline: gated clock must be closed with the enable low"
    cpu_clk.kill()
    dut.cpu_clk_i.value = 0
    glog.stop()
    # TAP scan with the scan reset asserted (functional enable deterministically 0), test
    # clocks via a DR scan
    drv = await _tap_power_up(dut)
    await drv.enter_scan(sel=0, rst=1)
    assert int(soc.dft_scan_rst_n.value) == 0 and int(soc.cpu_gated_clk_en.value) == 0
    log = EdgeLog({"gclk": soc.cpu_gated_clk, "tclk": soc.dft_test_clk}, dut.tck_i).start()
    await drv.shift_dr(0, 9)  # 10 test clocks
    gr = sum(1 for e in log.events if e[0] == "gclk" and e[3] == 1)
    tr = sum(1 for e in log.events if e[0] == "tclk" and e[3] == 1)
    assert tr == 10, f"expected 10 test clocks, got {tr}"
    assert gr == tr, (
        f"cpu_gated_clk rose {gr}x for {tr} test clocks: gate not forced open in scan mode"
    )
    assert int(soc.cpu_gated_clk_en.value) == 0, "enable must have stayed 0 throughout"
    log.stop()


@cocotb.test()
async def test_crypto_key_mask_follows_tap_scan_mode(dut):
    """key_eff = key_q in functional mode, 0 in TAP scan mode (flop untouched), restored on exit."""
    await _idle(dut)
    soc = dut.u_soc
    soc.u_crypto.key_q.value = KEY
    drv = await _tap_power_up(dut)
    await Timer(1, units="ns")
    assert int(soc.u_crypto.key_eff_w.value) == KEY, "precondition: key visible in functional mode"
    for exit_how in ("tms", "ir", "trst"):
        await drv.enter_scan(sel=0, rst=0)
        assert int(soc.dft_scan_mode.value) == 1
        assert int(soc.u_crypto.key_eff_w.value) == 0, f"key not masked in TAP scan ({exit_how})"
        assert int(soc.u_crypto.key_q.value) == KEY, "the mask must not touch the flop"
        if exit_how == "tms":
            await drv.reset_tms()
        elif exit_how == "ir":
            await drv.load_ir(OP_BYPASS)
        else:
            await drv.assert_trst()
            await Timer(1, units="ns")
            assert int(soc.u_crypto.key_eff_w.value) == KEY, "async TRST_N must unmask at once"
            await drv.release_trst()
            await drv.settle()
        assert int(soc.u_crypto.key_eff_w.value) == KEY, f"key not restored after {exit_how}"
        assert int(soc.dft_scan_mode.value) == 0


@cocotb.test()
async def test_exit_scan_restores_functional_via_tlr_and_trst(dut):
    """Leaving TAP scan (5xTMS, IR change, async TRST_N) hands the resets back to the pins."""
    await _idle(dut)
    soc = dut.u_soc
    drv = await _tap_power_up(dut)
    for how in ("tms", "ir", "trst"):
        await drv.enter_scan(sel=0, rst=0)
        dut.rst_n_i.value = 0
        await Timer(2, units="ns")
        assert int(soc.dft_scan_mode.value) == 1
        assert int(soc.core_rst_n.value) == 1, "scan mode must ignore rst_n_i"
        if how == "tms":
            await drv.reset_tms()
        elif how == "ir":
            await drv.load_ir(OP_IDCODE)
        else:
            await drv.assert_trst()
            await Timer(2, units="ns")
        assert int(soc.dft_scan_mode.value) == 0
        assert int(soc.core_rst_n.value) == 0, f"functional rst_n_i did not regain control ({how})"
        dut.rst_n_i.value = 1
        if how == "trst":
            await drv.release_trst()
            await drv.settle()
    await Timer(2, units="ns")


# ---------------------------------------------------------------------------
@cocotb.test()
async def test_serial_parallel_switching_is_glitch_free_in_the_soc(dut):
    """serial <-> parallel through the TAP with scan_clk_i free-running, observed on the SoC net
    dft_test_clk: no output pulse shorter than a source phase, every pulse a whole TCK-gated or pin
    pulse, no extra edge, exact handover per select change (old source stops at once, the new one
    passes from the 3rd handshake-clock rise).  The test clock is glitch-free here because
    u_dft_ctrl.u_clk_sw (dft_clk_switch) replaced the plain mux.

    Consequence for any test that goes serial -> parallel and then COUNTS pin edges (the PLL lock
    counters count dft_test_clk edges): the pin clock must have toggled about 3 cycles before its
    first pulse reaches the counters (its first two rising edges are consumed by the enable
    handshake once it ran while the TAP clock was on).  The counts below therefore come from the
    edge log of dft_test_clk, never from the number of pin toggles applied."""
    await _idle(dut)
    drv = await _tap_power_up(dut)
    soc = dut.u_soc
    cs = soc.u_dft_ctrl
    await _enter_scan_released(drv, dut, sel=0)  # serial, scan reset released, counters at 0
    assert int(dut.pll_locked_o.value) == 0 and int(dut.cpu_pll_locked_o.value) == 0
    handles = {
        "out": soc.dft_test_clk,
        "a": cs.tck_scan_gated,
        "b": dut.scan_clk_i,
        "tck": dut.tck_i,
        "en_a": cs.u_clk_sw.en_a_q,
        "en_b": cs.u_clk_sw.en_b_q,
        "sel": cs.tap_serial,
    }
    init_a, init_b = int(cs.u_clk_sw.en_a_q.value), int(cs.u_clk_sw.en_b_q.value)
    log = EdgeLog(handles, dut.tck_i, dut.trst_ni).start()
    clk_task = cocotb.start_soon(Clock(dut.scan_clk_i, PIN_CLK_NS, units="ns").start())
    await Timer(30, units="ns")
    for rnd in range(3):
        await drv.shift_dr(0, 3)  # serial: capture + 3 shift edges through the switch
        if rnd == 0:
            assert int(dut.pll_locked_o.value) == 0, "only 4 test clocks so far: not locked"
        await drv.write_tdr(OP_SCAN_SEL, 1, 3)  # IR leaves SCAN: select falls; PARALLEL=1
        await drv.load_ir(OP_SCAN)  # IR=SCAN, parallel: scan_clk_i is the test clock
        await drv.shift_dr(0, 3)  # TCK-driven scan in parallel: no TCK pulse on dft_test_clk
        await Timer(40, units="ns")
        await drv.write_tdr(OP_SCAN_SEL, 0, 3)  # PARALLEL=0 with IR != SCAN
        await drv.load_ir(OP_SCAN)  # serial again: the select rises
    await FallingEdge(dut.scan_clk_i)
    clk_task.kill()
    await Timer(5, units="ns")
    log.stop()
    ev = log.events
    out, a, b, tck = (pulses_of(ev, n) for n in ("out", "a", "b", "tck"))
    sel = events_of(ev, "sel")
    t_end = int(get_sim_time("ps"))
    min_phase = PIN_CLK_NS * 500
    labels, problems = label_output_pulses(out, a, b, min_phase)
    ub_a = min_phase + 3 * drv.T + 1
    ub_b = drv.T // 2 + 3 * PIN_CLK_NS * 1000 + 1
    tck_rises = [r for r, _f in tck]
    for k, (t, v) in enumerate(sel):
        t_next = sel[k + 1][0] if k + 1 < len(sel) else t_end
        hp, _info = check_handover(
            out, labels, a, b, tck_rises, t, "A" if v else "B", t_next, ub_a if v else ub_b
        )
        problems += [f"[select -> {'A' if v else 'B'} at {t} ps] {x}" for x in hp]
    problems += check_enable_latches(
        events_of(ev, "en_a"), events_of(ev, "en_b"), tck, b, init_a, init_b
    )
    assert not problems, f"{len(problems)} problem(s): " + "; ".join(problems[:6])
    assert len([v for _t, v in sel if v]) == 3 and len([v for _t, v in sel if not v]) == 3
    assert min(f - r for r, f in out) >= min_phase, (
        "a pulse on dft_test_clk is shorter than a phase"
    )
    n_a = sum(1 for lab in labels if lab == "A")
    n_b = sum(1 for lab in labels if lab == "B")
    assert n_a == 3 * 4 and n_b > 30, f"serial pulses {n_a} (want 12), pin pulses {n_b}"
    # the counters saw both kinds of edges: 12 serial + the pin pulses of the parallel windows
    assert int(dut.pll_locked_o.value) == 1 and int(dut.cpu_pll_locked_o.value) == 1
