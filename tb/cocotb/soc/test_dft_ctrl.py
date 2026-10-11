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
"""

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import Timer
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
)

TCK_NS = 11
PIN_CLK_NS = 3  # free-running pin scan clock, coprime to TCK


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
    await Timer(30, "ns")
    clk_task.kill()
    assert log.count("test_clk") - n0 > 10, (
        "after leaving SCAN test_clk_o must follow scan_clk_i again"
    )
    log.stop()


# keep the opcode names referenced (documentation of which TDRs the tests touch)
_ = (OP_SCAN_RST, OP_SCAN_SEL)
