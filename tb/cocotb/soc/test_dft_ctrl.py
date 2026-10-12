"""
test_dft_ctrl.py -- bead claude_verilog_test-j41m.3 (DFT Stage 1b), suite for dft_ctrl.

DUT: tb_dft_ctrl -> dft_ctrl (jtag_tap + the unchanged 1a pin leg dft_ctrl_ports + TCK scan-clock
gate + combiner, docs/design/DFT_ARCHITECTURE.md section 15.4).  The wrapper also instantiates the
Stage 1a dft_ctrl_ports on the same four pins (outputs ref_*): the golden
"TAP idle == 1a" reference.

Section 15.4 combiner, which these tests check from the pins (independent of the RTL text):
    scan_mode_o, test_en_o = pin_scan_mode | tap_scan          (tap_scan = IR == SCAN)
    scan_rst_no            = pin_scan_rst_n & ~(tap_scan & SCAN_RST)
    scan_en_o              = serial ? tap_scan_en (Shift-DR only) : pin_scan_en
    test_clk_o             = serial ? TCK gated to Capture-DR/Shift-DR : pin_scan_clk
    serial = tap_scan & ~SCAN_SEL[0]

Tests
  test_pins_only_identical_to_dft_ctrl_ports   all 16 pin combinations x TAP held in reset / TAP in
                                              TLR with TCK toggling: outputs == pins == 1a module
  test_tap_serial_scan_entry                   IR=SCAN: scan_mode/test_en 1, scan_rst_no = pin AND
                                              NOT SCAN_RST (all 4 combos), scan_en_o only in
                                              Shift-DR, IDCODE through dft_ctrl's tdo/tdo_oe
  test_test_clk_pulses_only_for_capture_and_shift
                                              every test_clk_o pulse is a TCK rising edge ending
                                              Capture-DR or a Shift-DR cycle, and every such
                                              edge pulses (set equality), width = TCK high time;
                                              none in RTI/Pause/Exit/Update/IR states
  test_parallel_hands_clock_and_scan_en_to_the_pins
                                              SCAN_SEL.PARALLEL=1: test_clk_o == scan_clk_i and
                                              scan_en_o == scan_en_i, TCK never appears
  test_tap_idle_with_tck_toggling_changes_nothing
                                              TLR, RTI, IDCODE/BYPASS/SCAN_SEL traffic, every
                                              SCAN_SEL x SCAN_RST value written: outputs == 1a leg
                                              every cycle, test_clk_o never moves from TCK
  test_pin_path_works_in_every_tap_state       all 16 TAP states: pins reach the outputs (IR !=
                                              SCAN: identical to 1a; IR=SCAN parallel: clock/en)
  test_tap_wins_when_pins_and_tap_both_active  serial scan with scan_en_i=1, scan_mode_i=1 and a
                                              free-running scan_clk_i: TAP value of scan_en_o,
                                              pulses only from TCK; negative control: leave SCAN
                                              and the pins take over again

Glitch-free test-clock switch (dft_clk_switch replaced the plain test_clk mux; its own unit suite is
test_dft_clk_switch.py; here it is checked in situ with the same edge-time pulse analysis)
  test_serial_entry_minimal_path_*            IR=SCAN, then Update-IR -> Select-DR -> Capture-DR,
                                              NO Run-Test/Idle: the capture edge and every shift
                                              edge still reach test_clk_o.  The TAP leaves exactly
                                              two TCK rises for the cross-coupled handshake; en_a_q
                                              rises between the 2nd and the capture edge (zero
                                              margin, asserted).  Variants: scan_clk_i stopped /
                                              free-running x power-up reset state / after an
                                              asynchronous TRST_N cycle
  test_serial_entry_with_pin_clock_parked_high_limitation
                                              documented limitation: scan_clk_i parked HIGH blocks
                                              the switch; recovers once it is low
  test_pin_clock_propagates_edge_for_edge_with_tap_idle
                                              TAP in reset / TLR / RTI / IDCODE traffic, TCK
                                              running: test_clk_o == scan_clk_i edge for edge
  test_serial_parallel_serial_with_pin_clock_toggling
                                              serial <-> parallel switching 3x with scan_clk_i
                                              running: no runt, no extra edge, exact handover
  test_serial_parallel_with_pin_clock_stopped test_clk_o stays low and silent after serial ->
                                              parallel until scan_clk_i toggles; parallel -> serial
                                              needs no pin-clock edge
  test_trst_in_the_middle_of_a_scan_pulse     TRST_N inside an A pulse: pulses may merge, never
                                              shorten; scan_clk_i takes over
"""

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, Timer
from cocotb.utils import get_sim_time
from jtag_driver import (
    ENC,
    IDCODE_VAL,
    OP_BYPASS,
    OP_IDCODE,
    OP_SCAN,
    OP_SCAN_RST,
    OP_SCAN_SEL,
    STATES,
    EdgeLog,
    JtagDriver,
    check_enable_latches,
    check_handover,
    events_of,
    label_output_pulses,
    pulses_of,
)

TCK_NS = 11
PIN_CLK_NS = 3  # free-running pin scan clock, coprime to TCK
PIN_HALF = PIN_CLK_NS * 500  # ps; the shortest phase of either switch source is the pin clock's


def _probe(dut):
    return {
        "tdo": int(dut.tdo_o.value),
        "tdo_oe": int(dut.tdo_oe_o.value),
        "state": int(dut.tap_state_o.value),
        "serial": int(dut.tap_serial_o.value),
    }


def _pins(dut, mode=0, en=0, rst=1, clk=0):
    dut.scan_mode_i.value = mode
    dut.scan_en_i.value = en
    dut.scan_rst_ni.value = rst
    dut.scan_clk_i.value = clk


async def _setup(dut, hold_reset=False):
    _pins(dut)
    drv = JtagDriver(
        dut.tck_i, dut.tms_i, dut.tdi_i, dut.trst_ni, dut.tdo_o, period_ns=TCK_NS,
        probe=lambda: _probe(dut), name="dft_ctrl",
    )  # fmt: skip
    await drv.start(hold_reset=hold_reset)
    return drv


def _outs(dut):
    return {
        "scan_mode": int(dut.scan_mode_o.value),
        "scan_en": int(dut.scan_en_o.value),
        "scan_rst_n": int(dut.scan_rst_no.value),
        "test_en": int(dut.test_en_o.value),
        "test_clk": int(dut.test_clk_o.value),
    }


def _ref(dut):
    return {
        "scan_mode": int(dut.ref_scan_mode_o.value),
        "scan_en": int(dut.ref_scan_en_o.value),
        "scan_rst_n": int(dut.ref_scan_rst_no.value),
        "test_en": int(dut.ref_test_en_o.value),
        "test_clk": int(dut.ref_test_clk_o.value),
    }


def _assert_is_1a(dut, why):
    got, ref = _outs(dut), _ref(dut)
    assert got == ref, f"{why}: dft_ctrl {got} != Stage 1a dft_ctrl_ports {ref}"
    return got


def _expected_pulse_times(drv, first_tick=0):
    """Rising-edge times at which test_clk_o must pulse: TCK rising edges that end Capture-DR or
    a Shift-DR cycle while the TAP is in serial scan.
    tick_log[i] = (state_before, ..., t, serial)."""
    return [
        t for (s, _m, _d, _o, t, serial) in drv.tick_log[first_tick:]
        if serial and s in ("CAPDR", "SHDR")
    ]  # fmt: skip


async def _free_clock(sig, period_ns):
    task = cocotb.start_soon(Clock(sig, period_ns, units="ns").start())
    return task


# ---------------------------------------------------------------------------
@cocotb.test()
async def test_pins_only_identical_to_dft_ctrl_ports(dut):
    """TAP idle: every pin combination, TAP held in reset and TAP in TLR with TCK toggling."""
    drv = await _setup(dut, hold_reset=True)
    n = 0
    for phase in ("trst_low", "tlr_tck_toggling"):
        if phase == "tlr_tck_toggling":
            await drv.release_trst()
            for _ in range(5):
                await drv.tick(1)
            assert drv.ref.state == "TLR"
        for code in range(16):
            m, e, r, c = (code >> 3) & 1, (code >> 2) & 1, (code >> 1) & 1, code & 1
            _pins(dut, mode=m, en=e, rst=r, clk=c)
            if phase == "tlr_tck_toggling":
                await drv.tick(1)  # TCK edges between the pin changes
            await Timer(1, "ns")
            got = _assert_is_1a(dut, f"{phase} pins={code:04b}")
            want = {"scan_mode": m, "scan_en": e, "scan_rst_n": r, "test_en": m, "test_clk": c}
            assert got == want, f"{phase} pins={code:04b}: outputs {got} are not the pins {want}"
            n += 1
    assert n == 32
    # negative control: the comparison is able to fail -- a TAP in scan mode differs from the 1a leg
    _pins(dut)
    await drv.enter_scan(sel=0, rst=0)
    assert _outs(dut)["scan_mode"] == 1 and _ref(dut)["scan_mode"] == 0, (
        "control: TAP scan must differ"
    )


# ---------------------------------------------------------------------------
@cocotb.test()
async def test_tap_serial_scan_entry(dut):
    drv = await _setup(dut)
    # IDCODE through dft_ctrl's tdo/tdo_oe (TAP wired through)
    assert await drv.shift_dr(0, 32) == IDCODE_VAL, "IDCODE not visible on dft_ctrl.tdo_o"
    o = _assert_is_1a(dut, "TAP idle")
    assert o["scan_mode"] == 0 and o["test_en"] == 0 and o["scan_rst_n"] == 1
    for tap_rst in (0, 1):
        await drv.enter_scan(sel=0, rst=tap_rst)
        for pin_rst in (1, 0):
            _pins(dut, rst=pin_rst)
            await Timer(1, "ns")
            o = _outs(dut)
            assert o["scan_mode"] == 1 and o["test_en"] == 1, (
                f"IR=SCAN must give scan_mode/test_en: {o}"
            )
            want = pin_rst & (1 - tap_rst)
            assert o["scan_rst_n"] == want, (
                f"SCAN_RST={tap_rst} pin scan_rst_ni={pin_rst}: scan_rst_no={o['scan_rst_n']}, "
                f"expected {want} (pin AND NOT SCAN_RST)"
            )
            assert o["test_clk"] == 0 and o["scan_en"] == 0, "no pulse / no shift outside a DR scan"
        _pins(dut)
    # scan_en_o only in Shift-DR (pins quiet): per-state, through a full DR tour
    await drv.enter_scan(sel=0, rst=0)
    tour = [1, 0, 0, 0, 0, 1, 0, 0, 1, 0, 0, 1, 1, 0]  # SELDR CAPDR SHDR... PAUDR ... UPDR RTI
    n_shift = 0
    for tms in tour:
        await drv.tick(tms)
        in_shift = drv.ref.state == "SHDR"
        n_shift += in_shift
        assert int(dut.scan_en_o.value) == int(in_shift), (
            f"scan_en_o={int(dut.scan_en_o.value)} in {drv.ref.state}: "
            "must be 1 exactly in Shift-DR"
        )
        assert int(dut.scan_mode_o.value) == 1
    assert n_shift >= 3
    # leaving SCAN returns everything to the pins
    await drv.load_ir(OP_BYPASS)
    o = _assert_is_1a(dut, "after leaving SCAN")
    assert o["scan_mode"] == 0 and o["test_en"] == 0


# ---------------------------------------------------------------------------
@cocotb.test()
async def test_test_clk_pulses_only_for_capture_and_shift(dut):
    drv = await _setup(dut)
    log = EdgeLog({"test_clk": dut.test_clk_o}, dut.tck_i, dut.trst_ni).start()
    await drv.enter_scan(sel=0, rst=0)
    assert log.count("test_clk") == 0, "test_clk_o pulsed while IR != SCAN / loading the TDRs"
    first = len(drv.tick_log)
    # One transaction with every kind of state in it, IR=SCAN (serial) throughout:
    for _ in range(3):
        await drv.tick(0)  # Run-Test/Idle with TCK running: no edge to the scanned flops
    await drv.walk([1, 0, 0])  # SELDR CAPDR SHDR  (capture edge ends CAPDR)
    await drv.walk([0, 0, 0, 1])  # 3 more shifts, leave to EX1DR
    await drv.walk([0, 0, 0, 1])  # PAUDR x3, EX2DR
    await drv.walk([0, 0, 1, 1, 0, 0])  # SHDR x2, EX1DR, UPDR, RTI, RTI
    await drv.shift_ir(OP_SCAN)  # an IR scan while serial: IR states must not pulse either
    await drv.shift_dr(0, 7)  # a plain DR scan: 1 capture + 7 shift pulses
    await drv.walk([0, 0])
    expected = _expected_pulse_times(drv, first)
    got_rise = [t for (n, t, old, new) in log.events if n == "test_clk" and new == 1]
    got_fall = [t for (n, t, old, new) in log.events if n == "test_clk" and new == 0]
    assert got_rise == expected, (
        f"test_clk_o pulses {len(got_rise)} != expected capture+shift edges {len(expected)}\n"
        f" extra: {sorted(set(got_rise) - set(expected))}\n"
        f" missing: {sorted(set(expected) - set(got_rise))}"
    )
    # vacuity guard: the transaction contained plenty of edges that must NOT pulse
    n_ticks = len(drv.tick_log) - first
    n_shift = sum(1 for e in drv.tick_log[first:] if e[0] == "SHDR")
    n_cap = sum(1 for e in drv.tick_log[first:] if e[0] == "CAPDR")
    assert n_cap == 2 and n_shift >= 12 and len(expected) == n_cap + n_shift
    assert n_ticks - len(expected) > 20, "transaction did not contain enough non-pulse edges"
    non_pulse_states = {
        e[0] for e in drv.tick_log[first:] if e[5] and e[0] not in ("CAPDR", "SHDR")
    }
    assert {"RTI", "PAUDR", "EX1DR", "EX2DR", "UPDR", "SHIR", "CAPIR", "UPIR"} <= non_pulse_states
    # each pulse is exactly the TCK high time: no runt, no stretch
    assert len(got_fall) == len(got_rise)
    for r, f in zip(got_rise, got_fall):
        assert f - r == drv.H, f"pulse at {r} ps is {f - r} ps wide, TCK high time is {drv.H} ps"
    log.stop()


# ---------------------------------------------------------------------------
@cocotb.test()
async def test_parallel_hands_clock_and_scan_en_to_the_pins(dut):
    drv = await _setup(dut)
    log = EdgeLog({"test_clk": dut.test_clk_o}, dut.tck_i, dut.trst_ni).start()
    await drv.enter_scan(sel=0b001, rst=0)  # PARALLEL=1, then IR=SCAN
    assert int(dut.scan_mode_o.value) == 1 and int(dut.test_en_o.value) == 1, (
        "TAP still supplies scan_mode"
    )
    assert int(dut.tap_serial_o.value) == 0
    # (a) scan_clk_i low: a complete DR scan with TCK running must not move test_clk_o
    tour = [1, 0, 0, 0, 0, 1, 0, 1, 0, 0, 1, 1, 0]
    pin_en = 0
    for tms in tour:
        pin_en ^= 1  # scan_en_i toggles every cycle: scan_en_o must follow the PIN, not Shift-DR
        _pins(dut, en=pin_en)
        await drv.tick(tms)
        assert int(dut.scan_en_o.value) == pin_en, (
            f"PARALLEL: scan_en_o={int(dut.scan_en_o.value)} in {drv.ref.state}, scan_en_i={pin_en}"
        )
        assert int(dut.test_clk_o.value) == 0
    assert log.count("test_clk") == 0, "TCK leaked onto test_clk_o in PARALLEL mode"
    # (b) scan_clk_i toggling freely, TCK idle and TCK running: test_clk_o is exactly scan_clk_i
    pin_log = EdgeLog({"pin": dut.scan_clk_i}, dut.tck_i).start()
    clk_task = await _free_clock(dut.scan_clk_i, PIN_CLK_NS)
    for tms in (0, 0, 1, 0, 0, 0, 1, 1, 0):
        await drv.tick(tms)
        assert int(dut.test_clk_o.value) == int(dut.scan_clk_i.value)
    await Timer(40, "ns")  # TCK stopped, pin clock still running
    assert int(dut.test_clk_o.value) == int(dut.scan_clk_i.value)
    clk_task.kill()
    dut.scan_clk_i.value = 0
    await Timer(1, "ns")
    n_pin = pin_log.count("pin")
    assert n_pin > 20 and log.count("test_clk") == n_pin, (
        f"test_clk_o toggled {log.count('test_clk')}x for {n_pin} scan_clk_i toggles"
    )
    assert [e[1] for e in log.events if e[0] == "test_clk"] == [e[1] for e in pin_log.events], (
        "test_clk_o edges are not simultaneous with scan_clk_i edges"
    )
    log.stop()
    pin_log.stop()


# ---------------------------------------------------------------------------
@cocotb.test()
async def test_tap_idle_with_tck_toggling_changes_nothing(dut):
    drv = await _setup(dut)
    log = EdgeLog(
        {"test_clk": dut.test_clk_o, "scan_en": dut.scan_en_o}, dut.tck_i, dut.trst_ni
    ).start()
    ticks = {"n": 0}

    def hook(_d):
        ticks["n"] += 1
        _assert_is_1a(dut, f"tick {ticks['n']} state {drv.ref.state} ir {drv.ref.ir:#x}")

    drv.post_tick_hooks.append(hook)
    for pins in ((0, 0, 1, 0), (1, 1, 0, 0)):  # quiet pins, then mode/en high and reset asserted
        _pins(dut, *pins)
        await drv.reset_tms()
        for _ in range(20):
            await drv.tick(1)  # TLR with TCK toggling
        for _ in range(20):
            await drv.walk([0])  # RTI
        await drv.shift_dr(0, 32)  # IDCODE
        await drv.load_ir(OP_BYPASS)
        await drv.shift_dr(0b1011, 4)
        for sel in range(8):  # every SCAN_SEL value, every SCAN_RST value, IR != SCAN
            await drv.write_tdr(OP_SCAN_SEL, sel, 3)
            for rst in (0, 1):
                await drv.write_tdr(OP_SCAN_RST, rst, 1)
        assert not drv.ref.ir == OP_SCAN
    assert ticks["n"] > 1000, "vacuity guard"
    assert log.count("test_clk") == 0, "test_clk_o moved with the TAP idle and scan_clk_i low"
    # negative control: the same log sees scan_clk_i-driven edges when the pin clock runs
    clk_task = await _free_clock(dut.scan_clk_i, PIN_CLK_NS)
    await Timer(40, "ns")
    clk_task.kill()
    assert log.count("test_clk") > 10, (
        "control: test_clk_o must follow scan_clk_i with the TAP idle"
    )
    log.stop()


# ---------------------------------------------------------------------------
@cocotb.test()
async def test_pin_path_works_in_every_tap_state(dut):
    drv = await _setup(dut)
    gray = [g ^ (g >> 1) for g in range(16)]
    visited = set()
    # (a) IR != SCAN (IDCODE after reset): all five outputs equal the 1a leg in all 16 TAP states
    for s in STATES:
        await drv.reset_tms()
        await drv.goto(s)
        for g in gray:
            _pins(dut, mode=(g >> 3) & 1, en=(g >> 2) & 1, rst=(g >> 1) & 1, clk=g & 1)
            await Timer(1, "ns")
            o = _assert_is_1a(dut, f"IR=IDCODE state={s} pins={g:04b}")
            assert o["scan_mode"] == (g >> 3) & 1 and o["test_clk"] == g & 1
        visited.add(s)
        _pins(dut)
    assert visited == set(STATES)
    # (b) IR = SCAN with PARALLEL=1: scan_en_o/test_clk_o are the pins in every state, scan_rst_no
    # is the pin (SCAN_RST=0), scan_mode_o is 1 whatever the pin says.  Two states need care:
    # Test-Logic-Reset always returns IR to IDCODE (so there the outputs must be the 1a leg again),
    # and Update-IR must be reached with SCAN shifted in (otherwise the capture pattern 0001 is
    # what gets updated and SCAN is left).
    for s in STATES:
        await drv.reset_tms()
        await drv.enter_scan(sel=0b001, rst=0)
        if s == "UPIR":
            await drv.goto("RTI")
            await drv.walk([1, 1, 0, 0])
            for i in range(4):
                await drv.tick(1 if i == 3 else 0, (OP_SCAN >> i) & 1)
            await drv.tick(1)
        else:
            await drv.goto(s)
        assert drv.ref.state == s
        if s == "TLR":
            for g in gray:
                _pins(dut, mode=(g >> 3) & 1, en=(g >> 2) & 1, rst=(g >> 1) & 1, clk=g & 1)
                await Timer(1, "ns")
                _assert_is_1a(dut, f"TLR after SCAN state pins={g:04b}")
            _pins(dut)
            continue
        assert int(dut.scan_mode_o.value) == 1 or s == "UPIR", f"precondition: scan mode in {s}"
        for g in gray:
            m, e, r, c = (g >> 3) & 1, (g >> 2) & 1, (g >> 1) & 1, g & 1
            _pins(dut, mode=m, en=e, rst=r, clk=c)
            await Timer(1, "ns")
            o = _outs(dut)
            assert o["scan_en"] == e and o["test_clk"] == c and o["scan_rst_n"] == r, (
                f"PARALLEL state={s} pins={g:04b}: {o}"
            )
            assert o["scan_mode"] == 1 and o["test_en"] == 1, f"PARALLEL state={s}: {o}"
        _pins(dut)
    assert ENC  # (import used)


# ---------------------------------------------------------------------------
@cocotb.test()
async def test_tap_wins_when_pins_and_tap_both_active(dut):
    drv = await _setup(dut)
    log = EdgeLog({"test_clk": dut.test_clk_o}, dut.tck_i, dut.trst_ni).start()
    await drv.enter_scan(sel=0, rst=0)  # serial; pin scan_clk_i is low while the IR changed
    assert int(dut.tap_serial_o.value) == 1
    first = len(drv.tick_log)
    # Both active: scan_mode_i=1, scan_en_i=1 held high, scan_clk_i free-running
    _pins(dut, mode=1, en=1, rst=1, clk=0)
    clk_task = await _free_clock(dut.scan_clk_i, PIN_CLK_NS)
    n_shift = 0
    for tms in [0, 1, 0, 0, 0, 0, 1, 0, 1, 0, 0, 1, 1, 0]:
        await drv.tick(tms)
        in_shift = drv.ref.state == "SHDR"
        n_shift += in_shift
        assert int(dut.scan_en_o.value) == int(in_shift), (
            f"serial TAP must win scan_en_o: {int(dut.scan_en_o.value)} in {drv.ref.state} "
            "although scan_en_i=1"
        )
        assert int(dut.scan_mode_o.value) == 1 and int(dut.test_en_o.value) == 1
    # pulses only at TCK edges ending Capture-DR/Shift-DR; scan_clk_i edges (3 ns) do not show
    expected = _expected_pulse_times(drv, first)
    got_rise = [t for (n, t, old, new) in log.events if n == "test_clk" and new == 1]
    assert got_rise == expected, (
        f"test_clk_o pulses {got_rise} != TCK capture/shift edges {expected} "
        "(a pin clock edge leaked through, or a TCK edge was lost)"
    )
    assert n_shift >= 5 and len(expected) == 6, (n_shift, len(expected))  # 1 capture + 5 shifts
    clk_task.kill()
    dut.scan_clk_i.value = 0
    await Timer(1, "ns")
    # negative control: leave SCAN (pin clock quiet while the IR changes), the pins take over again
    _pins(dut, mode=1, en=1, rst=1, clk=0)
    await drv.load_ir(OP_IDCODE)
    assert int(dut.scan_en_o.value) == 1, "after leaving SCAN scan_en_o must be the pin again"
    n0 = log.count("test_clk")
    clk_task = await _free_clock(dut.scan_clk_i, PIN_CLK_NS)
    # serial -> parallel through the glitch-free switch: the pin clock's first two rising edges
    # (6 ns here) are consumed by the enable handshake and pass from the 3rd, so the window is
    # 60 ns rather than the 30 ns of the plain-mux version (which passed pin edges at once)
    await Timer(60, "ns")
    clk_task.kill()
    assert log.count("test_clk") - n0 > 25, (
        "after leaving SCAN test_clk_o must follow scan_clk_i again"
    )
    log.stop()


# ===========================================================================
# Glitch-free test-clock switch (dft_clk_switch), in situ
# ===========================================================================
class _SwLog:
    """Edge-time log of the switch: sources (A = the TAP's gated TCK, B = scan_clk_i), output
    (test_clk_o), select (the TAP's serial flop), raw TCK and the two enable latches."""

    def __init__(self, dut):
        self.dut = dut
        self.init_a, self.init_b = int(dut.en_a_o.value), int(dut.en_b_o.value)
        self.log = EdgeLog(
            {
                "out": dut.test_clk_o,
                "a": dut.tck_gated_o,
                "b": dut.scan_clk_i,
                "tck": dut.tck_i,
                "en_a": dut.en_a_o,
                "en_b": dut.en_b_o,
                "sel": dut.tap_serial_o,
            },
            dut.tck_i,
            dut.trst_ni,
        ).start()

    def finish(self):
        self.log.stop()
        ev = self.log.events
        self.t_end = int(get_sim_time("ps"))
        self.out, self.a, self.b = (pulses_of(ev, n) for n in ("out", "a", "b"))
        self.tck = pulses_of(ev, "tck")
        self.tck_rises = [r for r, _f in self.tck]
        self.en_a, self.en_b = events_of(ev, "en_a"), events_of(ev, "en_b")
        self.sel = events_of(ev, "sel")
        assert int(self.dut.test_clk_o.value) == 0, "test_clk_o ends high"
        return self

    def out_rises(self, t0=0):
        return [r for r, _f in self.out if r >= t0]

    def labels(self, loose=False, gap_skip=()):
        return label_output_pulses(
            self.out, self.a, self.b, PIN_HALF, loose=loose, gap_skip=gap_skip
        )

    def latch_problems(self, skip=()):
        return check_enable_latches(
            self.en_a, self.en_b, self.tck, self.b, self.init_a, self.init_b, skip
        )

    def check(self, tck_period, pin_running=True):
        """Whole-pulse rule, handover rules for every select change, latch rules."""
        labels, probs = self.labels()
        ub_a = (PIN_HALF if pin_running else 0) + 3 * tck_period + 1
        ub_b = tck_period // 2 + 3 * PIN_CLK_NS * 1000 + 1 if pin_running else 10**15
        for k, (t, v) in enumerate(self.sel):
            t_next = self.sel[k + 1][0] if k + 1 < len(self.sel) else self.t_end
            hp, _info = check_handover(
                self.out, labels, self.a, self.b, self.tck_rises, t, "A" if v else "B", t_next,
                ub_a if v else ub_b,
            )  # fmt: skip
            probs += [f"[select -> {'A' if v else 'B'} at {t} ps] {x}" for x in hp]
        return probs + self.latch_problems()


async def _stop_pin_clock(dut, task):
    """Stop a free-running pin clock on a LOW level, so no source pulse is shortened by the stop."""
    await FallingEdge(dut.scan_clk_i)
    task.kill()


def _assert_clean(problems, what):
    assert not problems, f"{what}: {len(problems)} problem(s): " + "; ".join(problems[:6])


async def _minimal_serial_entry(dut, drv, with_pin_clock):
    """The tightest legal sequence into a serial DR scan, no Run-Test/Idle anywhere between
    Update-IR and Capture-DR:  Exit1-IR -TMS1-> Update-IR -TMS1-> Select-DR -TMS0-> Capture-DR
    -TMS0-> Shift-DR.  The select (serial) rises on the falling edge after the rising edge that
    entered Update-IR, so exactly TWO TCK rising edges (the ones leaving Update-IR and Select-DR)
    exist for the cross-coupled handshake before the third, the capture edge."""
    sw = _SwLog(dut)
    clk_task = await _free_clock(dut.scan_clk_i, PIN_CLK_NS) if with_pin_clock else None
    if with_pin_clock:
        await Timer(40, "ns")  # the pin clock passes through the output for a while first
    await drv.goto("RTI")
    await drv.walk([1, 1, 0, 0])  # SELDR SELIR CAPIR SHIR
    assert drv.ref.state == "SHIR"
    for i in range(4):
        await drv.tick(1 if i == 3 else 0, (OP_SCAN >> i) & 1)
    await drv.tick(1)  # Update-IR: IR = SCAN, serial rises on the falling edge
    first = len(drv.tick_log)
    await drv.walk([1, 0, 0])  # Select-DR, Capture-DR, Shift-DR: the 3rd rise is the capture edge
    await drv.walk([0] * 8 + [1])  # 9 shift edges (the last one leaves Shift-DR)
    await drv.walk([1, 0])  # Update-DR, Run-Test/Idle
    if clk_task is not None:
        await _stop_pin_clock(dut, clk_task)
    await Timer(5, "ns")
    sw.finish()
    return sw, first


async def _serial_entry_variant(dut, after_trst, with_pin_clock):
    drv = await _setup(dut)
    if after_trst:  # the switch's own reset state: async TRST_N cycle, TCK-synchronous release
        await drv.assert_trst()
        await Timer(20, "ns")
        await drv.release_trst()
        await drv.settle()
        await drv.reset_tms()
    sw, first = await _minimal_serial_entry(dut, drv, with_pin_clock)
    expected = _expected_pulse_times(drv, first)
    assert len(expected) == 10, (
        f"1 capture + 9 shift edges expected, the model says {len(expected)}"
    )
    t_sw = [t for t, v in sw.sel if v][0]
    got = sw.out_rises(t_sw)
    assert got == expected, (
        f"capture/shift edges at test_clk_o {got} != TCK capture/shift edges {expected}\n"
        f" missing: {sorted(set(expected) - set(got))}  extra: {sorted(set(got) - set(expected))}"
    )
    for r, f in sw.out:
        if r >= t_sw:
            assert f - r == drv.H, f"pulse [{r},{f}] is not one whole TCK high time ({drv.H} ps)"
    # zero margin, documented: en_a_q rises in the low phase of the Capture-DR cycle, i.e. after
    # the 2nd TCK rise that follows the select change and before the capture edge itself
    t_r2, t_r3 = drv.tick_log[first + 1][4], drv.tick_log[first + 2][4]
    assert [t for t, v in sw.en_a if v and t_r2 < t < t_r3], (
        f"en_a_q did not rise between the 2nd TCK rise ({t_r2}) and the capture edge ({t_r3}): "
        f"{[t for t, v in sw.en_a if v]}"
    )
    _assert_clean(sw.check(drv.T, pin_running=with_pin_clock), "serial entry")
    if with_pin_clock:  # vacuity: the pin clock ran and reached the output before the select rose
        assert len(sw.b) > 20 and [r for r in sw.out_rises() if r < t_sw]


@cocotb.test()
async def test_serial_entry_minimal_path_pin_clock_stopped(dut):
    """From the power-up reset state, scan_clk_i STOPPED low (the usual tester state)."""
    await _serial_entry_variant(dut, after_trst=False, with_pin_clock=False)


@cocotb.test()
async def test_serial_entry_minimal_path_pin_clock_stopped_after_trst(dut):
    """Same, after an asynchronous TRST_N assertion/release (the switch's own reset state)."""
    await _serial_entry_variant(dut, after_trst=True, with_pin_clock=False)


@cocotb.test()
async def test_serial_entry_minimal_path_pin_clock_running(dut):
    """Same with scan_clk_i free-running at 3 ns: the pin clock is retired before the first TCK
    rise (its enable drops in the next low phase), no pin pulse reaches the scan flops."""
    await _serial_entry_variant(dut, after_trst=False, with_pin_clock=True)


@cocotb.test()
async def test_serial_entry_minimal_path_pin_clock_running_after_trst(dut):
    await _serial_entry_variant(dut, after_trst=True, with_pin_clock=True)


# ---------------------------------------------------------------------------
@cocotb.test()
async def test_serial_entry_with_pin_clock_parked_high_limitation(dut):
    """DOCUMENTED LIMITATION (dft_clk_switch.sv, contract point 2): scan_clk_i parked HIGH while the
    TAP enters serial scan keeps the pin clock's enable latch opaque, so the switch cannot hand
    over: the output stays at the pin clock's (high) level and NO TCK scan pulse appears, however
    many DR scans run.  Once scan_clk_i is brought LOW the handover completes and the next DR scan
    gets its capture edge and every shift edge.  The tester must park scan_clk_i low."""
    drv = await _setup(dut, hold_reset=True)  # the switch starts from its RESET state (B on)
    await drv.release_trst()
    await drv.settle()
    sw = _SwLog(dut)
    dut.scan_clk_i.value = 1  # parked high (a B pulse starts and does not end)
    await Timer(30, "ns")
    t_hi = int(get_sim_time("ps"))
    await drv.enter_scan(sel=0, rst=0)
    await drv.shift_dr(0, 10)
    assert int(dut.tap_serial_o.value) == 1, "precondition: the TAP is in serial scan"
    assert int(dut.test_clk_o.value) == 1, "the output must still sit at the parked pin level"
    assert not [e for e in sw.log.events if e[0] == "out" and e[1] > t_hi], (
        "test_clk_o moved while scan_clk_i was parked high: a TCK pulse leaked through"
    )
    dut.scan_clk_i.value = 0  # park low: the handshake can now finish
    await Timer(2, "ns")
    await drv.walk([0] * 6)  # a few TCK cycles in Run-Test/Idle
    first2 = len(drv.tick_log)
    await drv.shift_dr(0, 10)
    expected = _expected_pulse_times(drv, first2)
    sw.finish()
    got = sw.out_rises(drv.tick_log[first2][4] - 1)
    assert len(expected) == 11 and got == expected, (
        f"after scan_clk_i went low the next DR scan must pass whole: {got} vs {expected}"
    )
    _labels, probs = sw.labels()
    _assert_clean(probs + sw.latch_problems(), "parked-high pin clock")


# ---------------------------------------------------------------------------
@cocotb.test()
async def test_pin_clock_propagates_edge_for_edge_with_tap_idle(dut):
    """Pin path with scan_clk_i toggling and the TAP in reset (TCK stopped, then toggling while
    TRST_N is still low), in Test-Logic-Reset, Run-Test/Idle and IDCODE/BYPASS/SCAN_SEL traffic:
    test_clk_o is scan_clk_i, edge for edge, from the very first pulse, and every output equals the
    1a leg at every tick.  Propagation only: no handshake, no dropped pulse, no delay."""
    drv = await _setup(dut, hold_reset=True)
    sw = _SwLog(dut)
    drv.post_tick_hooks.append(lambda d: _assert_is_1a(dut, f"tick {d.n_ticks}"))
    clk_task = await _free_clock(dut.scan_clk_i, PIN_CLK_NS)
    await Timer(200, "ns")  # TAP in reset, TCK stopped
    for _ in range(8):
        await drv.tick(1)  # TCK toggling, TRST_N still low (the TAP ignores it)
    await drv.release_trst()
    await drv.settle()
    for _ in range(12):
        await drv.tick(1)  # Test-Logic-Reset
    for _ in range(10):
        await drv.walk([0])  # Run-Test/Idle
    assert await drv.shift_dr(0, 32) == IDCODE_VAL
    await drv.load_ir(OP_BYPASS)
    await drv.shift_dr(0b1011, 4)
    await drv.write_tdr(
        OP_SCAN_SEL, 0b110, 3
    )  # SCAN_SEL traffic with IR != SCAN: still the pin path
    await drv.load_ir(OP_IDCODE)
    await _stop_pin_clock(dut, clk_task)
    await Timer(5, "ns")
    sw.finish()
    assert len(sw.b) > 250, "vacuity guard: the pin clock ran for the whole sequence"
    assert sw.out == sw.b, "test_clk_o is not scan_clk_i edge for edge with the TAP idle"
    assert not sw.sel, "the select must never move with IR != SCAN"
    _assert_clean(sw.check(drv.T), "TAP idle")


# ---------------------------------------------------------------------------
@cocotb.test()
async def test_serial_parallel_serial_with_pin_clock_toggling(dut):
    """serial -> parallel -> serial three times with scan_clk_i free-running (3 ns, coprime to TCK):
    across every select change the output has no runt and no extra edge, the old source stops at
    once, the new one passes from the 3rd handshake-clock rise and then every pulse, whole.  In the
    serial windows test_clk_o is exactly the TCK capture/shift edges, in the parallel windows it is
    scan_clk_i edge for edge once the handover is through."""
    drv = await _setup(dut)
    sw = _SwLog(dut)
    clk_task = await _free_clock(dut.scan_clk_i, PIN_CLK_NS)
    await Timer(30, "ns")
    for _round in range(3):
        await drv.enter_scan(sel=0, rst=0)  # serial: the select rises
        await drv.shift_dr(0, 10)  # 1 capture + 10 shift edges through the switch
        await drv.write_tdr(OP_SCAN_SEL, 1, 3)  # IR leaves SCAN (select falls), PARALLEL=1
        await drv.load_ir(OP_SCAN)  # IR=SCAN again, parallel: the select stays low
        await drv.shift_dr(0, 10)  # a TCK-driven DR scan in parallel: no TCK pulse at test_clk_o
        await Timer(60, "ns")
        await drv.write_tdr(OP_SCAN_SEL, 0, 3)  # PARALLEL back to 0 with IR != SCAN
    await _stop_pin_clock(dut, clk_task)
    await Timer(5, "ns")
    sw.finish()
    sel_up = [t for t, v in sw.sel if v]
    sel_dn = [t for t, v in sw.sel if not v]
    assert len(sel_up) == 3 and len(sel_dn) == 3, (sel_up, sel_dn)
    _assert_clean(sw.check(drv.T), "serial/parallel switching")
    all_expected = _expected_pulse_times(drv, 0)
    for k, t_up in enumerate(sel_up):
        t_dn = [t for t in sel_dn if t > t_up][0]
        exp = [t for t in all_expected if t_up < t < t_dn]
        got = [r for r, _f in sw.out if t_up < r < t_dn]
        assert got == exp and len(exp) == 11, f"serial window {k}: {got} vs {exp}"
    ub_b = drv.T // 2 + 3 * PIN_CLK_NS * 1000 + 1
    for k, t_dn in enumerate(sel_dn):
        t_up = ([t for t in sel_up if t > t_dn] + [sw.t_end])[0]
        win_o = [x for x in sw.out if t_dn + ub_b <= x[0] < t_up]
        win_b = [x for x in sw.b if t_dn + ub_b <= x[0] < t_up]
        assert win_o == win_b and len(win_b) > 10, f"parallel window {k}: {len(win_o)}/{len(win_b)}"


@cocotb.test()
async def test_serial_parallel_with_pin_clock_stopped(dut):
    """Documented behaviour with scan_clk_i STOPPED low.  serial -> parallel: the pin clock is not
    available, so the output goes and stays low (no TCK pulse leaks even through full DR scans)
    until scan_clk_i toggles; then its first two rising edges are consumed by the handshake.
    parallel -> serial needs no pin-clock edge.  A short pin-clock burst while A is on (the
    WITNESS) loads the A->B synchroniser; without it the first pin pulse passes at once (see
    test_dft_clk_switch.test_serial_to_parallel_with_a_never_clocked_pin_clock)."""
    drv = await _setup(dut)
    sw = _SwLog(dut)
    await drv.enter_scan(sel=0, rst=0)
    first = len(drv.tick_log)
    await drv.shift_dr(0, 5)  # 6 TCK edges through the switch
    assert len(_expected_pulse_times(drv, first)) == 6
    t_w = int(get_sim_time("ps"))
    witness = await _free_clock(dut.scan_clk_i, PIN_CLK_NS)
    await Timer(4 * PIN_CLK_NS, "ns")
    await _stop_pin_clock(dut, witness)
    await Timer(1, "ns")
    await drv.write_tdr(OP_SCAN_SEL, 1, 3)  # the select falls at the Update-IR, PARALLEL=1
    await drv.load_ir(OP_SCAN)
    await drv.shift_dr(0, 12)  # a full TCK DR scan in parallel with no pin clock: silence
    await drv.walk([0] * 10)
    t_clk0 = int(get_sim_time("ps"))
    clk_task = await _free_clock(dut.scan_clk_i, PIN_CLK_NS)
    await Timer(60, "ns")
    await _stop_pin_clock(dut, clk_task)
    await Timer(1, "ns")
    await drv.write_tdr(OP_SCAN_SEL, 0, 3)  # back to serial with the pin clock stopped again
    await drv.load_ir(OP_SCAN)
    first2 = len(drv.tick_log)
    await drv.shift_dr(0, 8)
    sw.finish()
    sel_dn = [t for t, v in sw.sel if not v][0]
    assert len([r for r, _f in sw.b if t_w <= r < t_w + 14_000]) >= 4, "witness burst missing"
    assert not [r for r in sw.out_rises(t_w) if r < t_w + 14_000], "a witness pin pulse leaked"
    assert not [r for r in sw.out_rises(sel_dn) if r < t_clk0], (
        "test_clk_o moved after serial->parallel while scan_clk_i was stopped"
    )
    pin_rises = [r for r, _f in sw.b if t_clk0 <= r < t_clk0 + 60_000]
    after = [r for r in sw.out_rises(t_clk0) if r < t_clk0 + 60_000]
    assert len(pin_rises) > 15 and after == pin_rises[2:], (
        f"pin pulses must pass from the 3rd rise: out {after[:3]} pin {pin_rises[:4]}"
    )
    exp2 = _expected_pulse_times(drv, first2)
    got2 = sw.out_rises(drv.tick_log[first2][4] - 1)
    assert len(exp2) == 9 and got2 == exp2, "serial scan after parallel with the pin clock stopped"
    _assert_clean(sw.check(drv.T, pin_running=False), "stopped pin clock")


# ---------------------------------------------------------------------------
@cocotb.test()
async def test_trst_in_the_middle_of_a_scan_pulse(dut):
    """TRST_N pulsed low while TCK is high inside a serial scan pulse, scan_clk_i running.  The
    reset may MERGE pulses (both enables briefly on) but must not shorten one or create an edge
    from nothing; scan_clk_i then takes over edge for edge."""
    drv = await _setup(dut)
    sw = _SwLog(dut)
    clk_task = await _free_clock(dut.scan_clk_i, PIN_CLK_NS)
    await Timer(30, "ns")
    await drv.enter_scan(sel=0, rst=0)
    await drv.goto("RTI")
    await drv.walk([1, 0, 0])  # Capture-DR done, in Shift-DR
    await drv.walk([0, 0, 0])
    await drv.tick(0, trst_in_high_ps=1500)  # asynchronous reset inside the A pulse
    await drv.settle()
    for _ in range(8):
        await drv.tick(1)
    await Timer(80, "ns")
    await _stop_pin_clock(dut, clk_task)
    await Timer(5, "ns")
    sw.finish()
    assert sw.log.trst_fall_t, "vacuity guard: TRST_N was asserted"
    t_rst = sw.log.trst_fall_t[-1]
    win = [(t_rst, t_rst + 3 * drv.T)]
    labels, probs = sw.labels(loose=True, gap_skip=win)
    t_up = [t for t, v in sw.sel if v][0]
    hp, info = check_handover(
        sw.out, labels, sw.a, sw.b, sw.tck_rises, t_up, "A", t_rst - drv.T,
        PIN_HALF + 3 * drv.T + 1,
    )  # fmt: skip
    assert info["n_new"] >= 3, "vacuity guard: a serial scan ran before the reset"
    probs += hp
    hp, _info = check_handover(
        sw.out, labels, sw.a, sw.b, sw.tck_rises, t_rst + 3 * drv.T, "B", sw.t_end, 0, lower=0
    )
    probs += hp
    probs += sw.latch_problems(skip=win)
    _assert_clean(probs, "TRST_N inside a scan pulse")
    pin_after = [x for x in sw.b if x[0] >= t_rst + 60_000]
    out_after = [x for x in sw.out if x[0] >= t_rst + 60_000]
    assert out_after == pin_after and len(pin_after) > 15, "scan_clk_i must take over after TRST_N"
    assert [t for t, v in sw.sel if not v and t >= t_rst], "the select must fall with the reset"


# keep the opcode names referenced (documentation of which TDRs the tests touch)
_ = (OP_SCAN_RST, OP_SCAN_SEL)
