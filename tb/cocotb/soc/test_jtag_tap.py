"""
test_jtag_tap.py -- bead claude_verilog_test-j41m.3 (DFT Stage 1b), unit suite for jtag_tap.

DUT: tb_jtag_tap -> jtag_tap (rtl/soc/dft/jtag_tap.sv) alone.
Specification: docs/design/DFT_ARCHITECTURE.md section 15 (15.2 TAP rules, 15.3 instruction map).

How the checking works
  Every test drives the TAP through jtag_driver.JtagDriver, which runs an independent spec model
  (jtag_driver.TapRef) in lock step and compares ALL outputs plus the state and the IR/TDR update
  registers against it at three instants of every TCK cycle: half a period after the falling edge
  with TMS/TDI already changed (pre_rise), 1 ps after the rising edge (post_rise: falling-edge
  outputs must NOT have moved) and 1 ps after the falling edge (post_fall).  So every directed
  test below is also a lock-step scoreboard run, and each test adds explicit, independently
  written assertions on the property it is named for (they do not read the model).

Every test is generated once per (TCK period, system clock period) pair in CFGS: the TAP is
exercised with a free-running 'system clock' toggling next to it whose period is coprime to TCK
(7/5, 13/3, 29/5 ns) to show that nothing in the TAP depends on any other clock.

Tests (each x3 configurations, suffix _tck_NNN)
  test_state_encodings_and_all_32_transitions   all 16 states reached, state_o == the standard
                                               encoding, both TMS edges out of each taken
  test_trst_is_asynchronous_from_every_state    TRST_N low with TCK stopped, in each of the 16
                                               states while in SCAN with nonzero TDRs: state and
                                               every output clear at once, TDRs/IR back to reset,
                                               release needs 2 TCK edges before the FSM moves
  test_trst_in_the_middle_of_a_cycle            TRST_N pulsed while TCK is high
  test_five_tms_ones_reach_tlr_from_every_state exactly the distance, never later than 5, 4 are
                                               not enough from Pause-DR (negative control)
  test_ir_capture_and_update_timing             Capture-IR = 0001 (LSB first); a shifted IR takes
                                               effect only on the FALLING edge of Update-IR;
                                               short/long IR shifts; all 16 opcodes round-trip
  test_bypass_is_a_one_bit_delay                BYPASS: capture 0, output = input delayed 1 bit
  test_idcode_after_reset_without_loading_ir    IDCODE readback after TRST_N and after 5xTMS,
                                               value 0x15C01001, LSB first, 32 bits
  test_tdr_write_and_readback                   SCAN_SEL (3b) and SCAN_RST (1b): updated at the
                                               falling edge of Update-DR, read back at Capture-DR
  test_tdrs_reset_by_tlr_and_trst               both TDRs return to 0 on TLR and on TRST_N
  test_scan_stub_is_a_one_bit_delay             SCAN data register: 1 bit, BYPASS timing
  test_every_opcode_decodes_as_specified        all 16 opcodes: DR length, capture value,
                                               unimplemented/reserved/unknown -> BYPASS
  test_tdo_and_oe_per_state                     tdo_oe_o == (Shift-IR | Shift-DR), TDO 0 elsewhere
  test_scan_mode_only_from_ir_scan              every SCAN_SEL x SCAN_RST value written with
                                               IR != SCAN leaves ALL outputs 0, every tick
  test_scan_outputs_per_spec                    serial/parallel/rst_assert/chain_grp/scan_en/
                                               shift_clk_en in every DR state, every TDR value
  test_outputs_change_only_on_tck_falling_edge  event log: falling-edge outputs only ever change
                                               at a TCK falling edge (or at the TRST_N instant);
                                               negative controls prove the log can fail
  test_random_walk_lock_step                    seeded random TMS/TDI incl. TRST_N pulses, model
                                               compared every cycle; coverage of states/edges
"""

import random

import cocotb
from cocotb.clock import Clock
from cocotb.regression import TestFactory
from cocotb.triggers import Timer
from jtag_driver import (
    DEC,
    ENC,
    IDCODE_VAL,
    IR_CAPTURE,
    NEXT,
    OP_BYPASS,
    OP_EXTEST,
    OP_IDCODE,
    OP_MBIST_CTRL,
    OP_MBIST_STATUS,
    OP_SAMPLE,
    OP_SCAN,
    OP_SCAN_RST,
    OP_SCAN_SEL,
    SHIFT_STATES,
    STATES,
    EdgeLog,
    JtagDriver,
    bits_of,
    int_of,
)

# (TCK period ns, system clock period ns): coprime pairs
CFGS = [(7, 5), (13, 3), (29, 5)]

OUT_NAMES = (
    "tdo",
    "tdo_oe",
    "scan_mode",
    "serial",
    "parallel",
    "rst_assert",
    "scan_en",
    "chain_grp",
)
CTRL_NAMES = ("scan_mode", "serial", "parallel", "rst_assert", "scan_en", "chain_grp")


def _probe(dut):
    return {
        "tdo": int(dut.tdo_o.value),
        "tdo_oe": int(dut.tdo_oe_o.value),
        "state": int(dut.state_o.value),
        "scan_mode": int(dut.scan_mode_o.value),
        "serial": int(dut.serial_o.value),
        "parallel": int(dut.parallel_o.value),
        "rst_assert": int(dut.rst_assert_o.value),
        "scan_en": int(dut.scan_en_o.value),
        "chain_grp": int(dut.chain_grp_o.value),
        "shift_clk_en": int(dut.shift_clk_en_o.value),
        "ir_q": int(dut.ir_q_o.value),
        "scan_sel_q": int(dut.scan_sel_q_o.value),
        "scan_rst_q": int(dut.scan_rst_q_o.value),
        "mbist_wr": int(dut.mbist_wr_o.value),
        "mbist_force": int(dut.mbist_force_o.value),
        "mb_ctl_q": int(dut.mbist_ctl_o.value),
    }


def _ctrl(dut):
    return {k: v for k, v in _probe(dut).items() if k in CTRL_NAMES}


async def _setup(dut, cfg, release=True):
    """Start the free-running system clock, bring the TAP to TLR (optionally then hold TRST_N)."""
    tck_ns, sys_ns = cfg
    dut.sys_clk_i.value = 0
    # Idle MBIST inputs (control-word FIFO ready, status 0): undriven they are X in a 4-state simulator,
    # whereas Verilator reads an undriven input as 0.
    dut.mbist_not_ready_i.value = 0
    dut.mbist_status_i.value = 0
    cocotb.start_soon(Clock(dut.sys_clk_i, sys_ns, units="ns").start())
    drv = JtagDriver(
        dut.tck_i, dut.tms_i, dut.tdi_i, dut.trst_ni, dut.tdo_o, period_ns=tck_ns,
        probe=lambda: _probe(dut), name=f"tap_{tck_ns}ns",
    )  # fmt: skip
    await drv.start(hold_reset=not release)
    return drv


def _assert_idle_outputs(dut, why):
    got = _probe(dut)
    for k in OUT_NAMES:
        assert got[k] == 0, f"{why}: {k} = {got[k]:#x}, must be 0"
    assert got["shift_clk_en"] == 0, f"{why}: shift_clk_en must be 0"


# ---------------------------------------------------------------------------
async def t_state_encodings_and_all_32_transitions(dut, cfg):
    drv = await _setup(dut, cfg)
    n_edges = 0
    for s in STATES:
        for tms in (0, 1):
            await drv.reset_tms()
            await drv.goto(s)
            assert int(dut.state_o.value) == ENC[s], (
                f"{s}: state_o={int(dut.state_o.value):#x}, standard encoding {ENC[s]:#x}"
            )
            await drv.tick(tms)
            dst = NEXT[s][tms]
            assert int(dut.state_o.value) == ENC[dst], (
                f"{s} --TMS={tms}--> state_o={int(dut.state_o.value):#x}, "
                f"expected {dst} = {ENC[dst]:#x}"
            )
            n_edges += 1
    assert n_edges == 32
    assert len({int(v) for v in ENC.values()}) == 16, "encodings must be 16 distinct values"
    assert sorted(DEC) == list(range(16))


# ---------------------------------------------------------------------------
async def t_trst_is_asynchronous_from_every_state(dut, cfg):
    drv = await _setup(dut, cfg)
    scan_states = 0
    for s in STATES:
        await drv.reset_tms()
        # SCAN_SEL = 0b101 (PARALLEL=1, CHAIN_GRP=2), SCAN_RST = 1, IR = SCAN: all controls high.
        await drv.enter_scan(sel=0b101, rst=1)
        await drv.goto(s)
        pre = _probe(dut)
        if pre["scan_mode"]:
            scan_states += 1
            assert pre["parallel"] == 1 and pre["rst_assert"] == 1 and pre["chain_grp"] == 2, (
                f"{s}: precondition: scan outputs high before TRST_N, got {pre}"
            )
        # TCK is stopped low.  Assert TRST_N: everything must clear with NO clock edge.
        await drv.assert_trst(settle_ps=1)
        got = _probe(dut)
        assert got["state"] == 0xF, f"{s}: TRST_N did not force Test-Logic-Reset: {got['state']:#x}"
        _assert_idle_outputs(dut, f"{s}: after TRST_N")
        assert got["ir_q"] == OP_IDCODE and got["scan_sel_q"] == 0 and got["scan_rst_q"] == 0, (
            f"{s}: IR/TDR update registers not reset: {got}"
        )
        # Held in reset: TCK edges do nothing.
        for _ in range(3):
            await drv.tick(0)
        assert int(dut.state_o.value) == 0xF, f"{s}: FSM moved while TRST_N was low"
        # Release: the 2-stage synchroniser swallows two rising edges, the third one moves the FSM.
        await drv.release_trst()
        await drv.tick(0)
        assert int(dut.state_o.value) == 0xF, f"{s}: FSM moved on TCK edge 1 after TRST_N release"
        await drv.tick(0)
        assert int(dut.state_o.value) == 0xF, f"{s}: FSM moved on TCK edge 2 after TRST_N release"
        await drv.tick(0)
        assert int(dut.state_o.value) == ENC["RTI"], f"{s}: FSM did not leave TLR on edge 3"
        # TDRs and IR really reset: IDCODE selected, SCAN_SEL/SCAN_RST read 0.
        assert await drv.shift_dr(0, 32) == IDCODE_VAL, f"{s}: IR not back at IDCODE after TRST_N"
        await drv.load_ir(OP_SCAN_SEL)
        assert await drv.shift_dr(0, 3) == 0, f"{s}: SCAN_SEL not cleared by TRST_N"
        await drv.load_ir(OP_SCAN_RST)
        assert await drv.shift_dr(0, 1) == 0, f"{s}: SCAN_RST not cleared by TRST_N"
    assert scan_states >= 10, f"vacuity guard: only {scan_states}/16 states started in scan mode"


async def t_trst_in_the_middle_of_a_cycle(dut, cfg):
    drv = await _setup(dut, cfg)
    for s in ("SHDR", "SHIR", "UPIR", "EX1DR", "PAUIR", "CAPDR"):
        await drv.reset_tms()
        await drv.enter_scan(sel=0, rst=1)
        await drv.goto(s)
        assert int(dut.scan_mode_o.value) == 1 or s in ("UPIR", "PAUIR"), f"precondition {s}"
        # The next rising edge moves the FSM (TMS=0 is a move out of every one of these but
        # Shift/Pause), then TRST_N pulses while TCK is high.
        await drv.tick(0, trst_in_high_ps=drv.H // 3)
        got = _probe(dut)
        assert got["state"] == 0xF, f"{s}: state {got['state']:#x} after mid-cycle TRST_N"
        _assert_idle_outputs(dut, f"{s}: after mid-cycle TRST_N")
        # after the pulse the TAP needs 2 more edges, then works again
        for _ in range(4):
            await drv.tick(1)
        assert await drv.shift_dr(0, 32) == IDCODE_VAL


# ---------------------------------------------------------------------------
def _dist_to_tlr(s):
    n = 0
    while s != "TLR":
        s = NEXT[s][1]
        n += 1
    return n


async def t_five_tms_ones_reach_tlr_from_every_state(dut, cfg):
    drv = await _setup(dut, cfg)
    worst = 0
    scan_states = 0
    for s in STATES:
        await drv.reset_tms()
        await drv.enter_scan(sel=0b010, rst=1)
        await drv.goto(s)
        if int(dut.scan_mode_o.value):
            scan_states += 1
        d = _dist_to_tlr(s)
        worst = max(worst, d)
        for k in range(1, 6):
            await drv.tick(1)
            at_tlr = int(dut.state_o.value) == ENC["TLR"]
            assert at_tlr == (k >= d), (
                f"{s}: after {k} TMS=1 edges at_tlr={at_tlr}, spec distance is {d}"
            )
        assert int(dut.state_o.value) == ENC["TLR"], f"{s}: not in TLR after 5 x TMS=1"
        # Entering TLR returns IR to IDCODE and clears every output/TDR at the next falling edge.
        _assert_idle_outputs(dut, f"{s}: after 5xTMS")
        assert int(dut.ir_q_o.value) == OP_IDCODE
        assert int(dut.scan_sel_q_o.value) == 0 and int(dut.scan_rst_q_o.value) == 0
    # negative control: the worst case really is 5, i.e. 4 edges are NOT enough from Pause-DR
    assert worst == 5 and _dist_to_tlr("PAUDR") == 5
    await drv.goto("PAUDR")
    await drv.walk([1, 1, 1, 1])
    assert int(dut.state_o.value) != ENC["TLR"], "4 x TMS=1 from Pause-DR must not reach TLR"
    assert scan_states >= 8, f"vacuity guard: only {scan_states} states started in scan mode"


# ---------------------------------------------------------------------------
async def t_ir_capture_and_update_timing(dut, cfg):
    drv = await _setup(dut, cfg)
    # --- capture pattern ---------------------------------------------------
    cap = await drv.shift_ir(OP_IDCODE)
    assert cap == IR_CAPTURE, f"Capture-IR shifted out {cap:#06b}, must be 0b0001 (LSB first)"
    # --- update timing: IR = SCAN shifted in, effect only at the falling edge of Update-IR -------
    await drv.goto("RTI")
    await drv.walk([1, 1, 0, 0])  # SELDR SELIR CAPIR SHIR
    assert drv.ref.state == "SHIR"
    for i in range(4):
        await drv.tick(1 if i == 3 else 0, (OP_SCAN >> i) & 1)
        assert int(dut.ir_q_o.value) == OP_IDCODE, "IR update register changed during Shift-IR"
        assert int(dut.scan_mode_o.value) == 0, "scan_mode_o rose before Update-IR"
    assert int(dut.state_o.value) == ENC["EX1IR"]
    await drv.tick(1)  # -> Update-IR
    assert int(dut.state_o.value) == ENC["UPIR"]
    assert drv.snaps["rise"]["ir_q"] == OP_IDCODE and drv.snaps["rise"]["scan_mode"] == 0, (
        "IR / scan_mode_o changed on the RISING edge into Update-IR; spec: falling edge"
    )
    assert drv.snaps["fall"]["ir_q"] == OP_SCAN and drv.snaps["fall"]["scan_mode"] == 1, (
        "IR / scan_mode_o did not change on the falling edge of Update-IR"
    )
    await drv.tick(0)
    assert int(dut.ir_q_o.value) == OP_SCAN and int(dut.scan_mode_o.value) == 1
    # --- bit order and length of the IR shift register ----------------------------
    await drv.reset_tms()
    for v in range(16):
        await drv.shift_ir(v)
        assert int(dut.ir_q_o.value) == v, f"opcode {v:#x} loaded as {int(dut.ir_q_o.value):#x}"
    # 2-bit shift: TDI enters the MSB, so the result is {b1, b0, cap[3:2]} = {b1, b0, 0, 0}
    for b0, b1 in ((0, 0), (1, 0), (0, 1), (1, 1)):
        await drv.shift_ir(b0 | (b1 << 1), n=2)
        assert int(dut.ir_q_o.value) == (b1 << 3) | (b0 << 2), "2-bit Shift-IR result wrong"
    # 6-bit shift: only the last four bits shifted in remain
    stream = [1, 1, 0, 1, 0, 0]
    await drv.shift_ir(int_of(stream), n=6)
    assert int(dut.ir_q_o.value) == int_of(stream[2:]), "6-bit Shift-IR must keep the last 4 bits"
    # IR holds through DR scans and Run-Test/Idle
    await drv.shift_ir(OP_SCAN_SEL)
    await drv.shift_dr(0b101, 3)
    for _ in range(5):
        await drv.tick(0)
    assert int(dut.ir_q_o.value) == OP_SCAN_SEL


# ---------------------------------------------------------------------------
async def t_bypass_is_a_one_bit_delay(dut, cfg):
    drv = await _setup(dut, cfg)
    await drv.load_ir(OP_BYPASS)
    assert await drv.measure_dr_length() == 1, "BYPASS must be a 1-bit register"
    rng = random.Random(0xB1)
    for trial in range(4):
        pattern = [rng.getrandbits(1) for _ in range(20)]
        pattern[3] = 1  # make sure there are ones to delay
        await drv.shift_dr(0, len(pattern), stream=pattern)
        out = drv.last_bits
        assert out[0] == 0, "BYPASS must capture 0"
        assert out[1:] == pattern[:-1], f"BYPASS output is not the input delayed one bit (t{trial})"
    # capture is re-done at every Capture-DR: a 1 left in the register is not returned
    await drv.shift_dr(1, 1)
    await drv.shift_dr(0, 4)
    assert drv.last_bits[0] == 0, "BYPASS did not re-capture 0"


# ---------------------------------------------------------------------------
async def t_idcode_after_reset_without_loading_ir(dut, cfg):
    drv = await _setup(dut, cfg)
    for how in ("trst", "tms", "trst2"):
        if how == "tms":
            await drv.load_ir(OP_BYPASS)
            await drv.reset_tms()
        else:
            await drv.load_ir(OP_BYPASS)
            await drv.assert_trst()
            await drv.release_trst()
            await drv.walk([1] * 5)
        assert int(dut.ir_q_o.value) == OP_IDCODE, f"{how}: IR not IDCODE after reset"
        val = await drv.shift_dr(0, 32)  # NO IR load in between
        assert val == IDCODE_VAL == 0x15C0_1001, f"{how}: IDCODE read {val:#010x}"
        bits = drv.last_bits
        assert bits[0] == 1, "IDCODE bit 0 (first out) must be 1"
        assert bits == bits_of(IDCODE_VAL, 32), f"{how}: IDCODE not shifted out LSB first"
        # recaptured at every Capture-DR, whatever was shifted in
        assert await drv.shift_dr(0xFFFF_FFFF, 32) == IDCODE_VAL
        assert await drv.shift_dr(0, 32) == IDCODE_VAL
    assert await drv.measure_dr_length() == 32
    # explicit selection works too
    await drv.load_ir(OP_BYPASS)
    await drv.load_ir(OP_IDCODE)
    assert await drv.shift_dr(0, 32) == IDCODE_VAL
    # fields: version 1, part 0x5C01, manufacturer 0 (non-JEDEC placeholder), LSB 1
    assert IDCODE_VAL >> 28 == 0x1 and (IDCODE_VAL >> 12) & 0xFFFF == 0x5C01
    assert (IDCODE_VAL >> 1) & 0x7FF == 0 and IDCODE_VAL & 1 == 1


# ---------------------------------------------------------------------------
async def t_tdr_write_and_readback(dut, cfg):
    drv = await _setup(dut, cfg)
    assert await drv.measure_dr_length() == 32  # IDCODE selected after reset; sanity
    # --- SCAN_SEL, 3 bits -----------------------------------------------------------
    await drv.load_ir(OP_SCAN_SEL)
    assert await drv.measure_dr_length() == 3, "SCAN_SEL must be 3 bits"
    prev = 0  # the measurement flushed zeros in
    for v in (5, 2, 7, 0, 1, 4, 3, 6):
        got_prev = await drv.shift_dr(v, 3)
        assert got_prev == prev, f"Capture-DR returned {got_prev}, SCAN_SEL held {prev}"
        assert int(dut.scan_sel_q_o.value) == v, f"SCAN_SEL update register {v} not loaded"
        assert await drv.shift_dr(v, 3) == v, "readback differs from what was written"
        assert int(dut.scan_sel_q_o.value) == v
        prev = v
    # --- update only at the falling edge of Update-DR ----------------------------------
    await drv.shift_dr(0, 3)
    await drv.goto("RTI")
    await drv.walk([1, 0, 0])  # SELDR CAPDR SHDR
    for i, b in enumerate((1, 0, 1)):
        await drv.tick(1 if i == 2 else 0, b)
        assert int(dut.scan_sel_q_o.value) == 0, "SCAN_SEL changed during Shift-DR"
    await drv.tick(1)  # Exit1 -> Update-DR
    assert drv.ref.state == "UPDR"
    assert drv.snaps["rise"]["scan_sel_q"] == 0, (
        "SCAN_SEL updated on the rising edge into Update-DR"
    )
    assert drv.snaps["fall"]["scan_sel_q"] == 0b101, (
        "SCAN_SEL not updated on the Update-DR falling edge"
    )
    await drv.tick(0)
    # --- SCAN_RST, 1 bit -------------------------------------------------------------
    await drv.load_ir(OP_SCAN_RST)
    assert await drv.measure_dr_length() == 1, "SCAN_RST must be 1 bit"
    prev = 0
    for v in (1, 0, 1, 1, 0):
        assert await drv.shift_dr(v, 1) == prev
        assert int(dut.scan_rst_q_o.value) == v
        assert await drv.shift_dr(v, 1) == v
        prev = v
    # a TDR is only written by its own IR: SCAN_SEL untouched by the SCAN_RST traffic
    assert int(dut.scan_sel_q_o.value) == 0b101


async def t_tdrs_reset_by_tlr_and_trst(dut, cfg):
    drv = await _setup(dut, cfg)
    for how in ("tms", "trst"):
        await drv.write_tdr(OP_SCAN_SEL, 0b110, 3)
        await drv.write_tdr(OP_SCAN_RST, 1, 1)
        assert int(dut.scan_sel_q_o.value) == 0b110 and int(dut.scan_rst_q_o.value) == 1, (
            "precondition: TDRs nonzero"
        )
        if how == "tms":
            await drv.reset_tms()
        else:
            await drv.assert_trst()
            await drv.release_trst()
            await drv.walk([1] * 5)
        assert int(dut.scan_sel_q_o.value) == 0 and int(dut.scan_rst_q_o.value) == 0, (
            f"TDR not cleared by {how}"
        )
        await drv.load_ir(OP_SCAN_SEL)
        assert await drv.shift_dr(0, 3) == 0
        await drv.load_ir(OP_SCAN_RST)
        assert await drv.shift_dr(0, 1) == 0


# ---------------------------------------------------------------------------
async def t_scan_stub_is_a_one_bit_delay(dut, cfg):
    drv = await _setup(dut, cfg)
    await drv.load_ir(OP_SCAN)
    assert int(dut.scan_mode_o.value) == 1, "precondition: IR = SCAN"
    assert await drv.measure_dr_length() == 1, "SCAN data register stub must be 1 bit"
    pattern = [1, 0, 1, 1, 0, 0, 1, 0, 1, 1, 1, 0]
    await drv.shift_dr(0, len(pattern), stream=pattern)
    assert drv.last_bits[0] == 0, "SCAN stub must capture 0 (BYPASS timing)"
    assert drv.last_bits[1:] == pattern[:-1], "SCAN stub is not a 1-bit delay"


# ---------------------------------------------------------------------------
_EXPECT_LEN = {OP_IDCODE: 32, OP_SCAN_SEL: 3, OP_MBIST_CTRL: 29, OP_MBIST_STATUS: 140}
_UNIMPLEMENTED = (
    OP_EXTEST,
    OP_SAMPLE,
    8,
    9,
    10,
    11,
    12,
    13,
    14,
    OP_BYPASS,
)


async def t_every_opcode_decodes_as_specified(dut, cfg):
    drv = await _setup(dut, cfg)
    rng = random.Random(0x0C0DE)
    for op in range(16):
        await drv.load_ir(op)
        assert int(dut.ir_q_o.value) == op
        assert int(dut.scan_mode_o.value) == int(op == OP_SCAN), (
            f"scan_mode_o wrong for opcode {op:#x}"
        )
        want = _EXPECT_LEN.get(op, 1)
        got = await drv.measure_dr_length(cap_bits=141 if op == OP_MBIST_STATUS else 33)
        assert got == want, f"opcode {op:#x}: DR length {got}, spec {want}"
        await drv.load_ir(op)  # measure_dr_length shifted zeros into the TDRs; reselect
        if op in _UNIMPLEMENTED or op == OP_SCAN:
            pattern = [rng.getrandbits(1) for _ in range(16)]
            pattern[5] = 1
            await drv.shift_dr(0, 16, stream=pattern)
            out = drv.last_bits
            assert out[0] == 0 and out[1:] == pattern[:-1], (
                f"opcode {op:#x} must behave as BYPASS (capture 0, 1-bit delay); got {out}"
            )
        elif op == OP_IDCODE:
            assert await drv.shift_dr(0, 32) == IDCODE_VAL
        else:  # SCAN_SEL / SCAN_RST: capture = the current update register (0 after the flush)
            assert await drv.shift_dr(0, want) == 0
    # an opcode that is not SCAN must never raise scan_mode_o: checked per opcode above; and the
    # nominally "unimplemented" ones left every SoC-facing output at 0
    for op in _UNIMPLEMENTED:
        await drv.load_ir(op)
        _assert_idle_outputs(dut, f"opcode {op:#x}")


# ---------------------------------------------------------------------------
async def t_tdo_and_oe_per_state(dut, cfg):
    drv = await _setup(dut, cfg)
    for ir in (OP_IDCODE, OP_BYPASS):
        await drv.load_ir(ir)
        for s in STATES:
            await drv.reset_tms()
            if ir != OP_IDCODE:
                await drv.load_ir(ir)
            await drv.goto(s)
            snap = drv.snaps["fall"]
            assert snap["state"] == ENC[s]
            in_shift = s in SHIFT_STATES
            assert snap["tdo_oe"] == int(in_shift), (
                f"{s}: tdo_oe_o={snap['tdo_oe']}, must be {int(in_shift)} "
                "(1 exactly in Shift-IR/DR)"
            )
            if not in_shift:
                assert snap["tdo"] == 0, f"{s}: TDO must be 0 outside Shift-IR/Shift-DR"
            elif s == "SHIR":
                assert snap["tdo"] == 1, "first Shift-IR bit is the IR capture LSB, 1"
            else:
                want = 1 if ir == OP_IDCODE else 0  # IDCODE LSB / BYPASS capture
                assert snap["tdo"] == want, f"Shift-DR first bit {snap['tdo']}, expected {want}"
    # leaving a shift state drops TDO and OE at the falling edge, not at the rising one
    await drv.reset_tms()
    await drv.load_ir(OP_IDCODE)
    await drv.goto("SHDR")
    assert drv.snaps["fall"]["tdo"] == 1 and drv.snaps["fall"]["tdo_oe"] == 1
    await drv.tick(1)  # -> Exit1-DR
    assert drv.snaps["rise"]["tdo"] == 1 and drv.snaps["rise"]["tdo_oe"] == 1, (
        "TDO/OE moved on the rising edge; they are falling-edge flops"
    )
    assert drv.snaps["fall"]["tdo"] == 0 and drv.snaps["fall"]["tdo_oe"] == 0


# ---------------------------------------------------------------------------
async def t_scan_mode_only_from_ir_scan(dut, cfg):
    drv = await _setup(dut, cfg)
    ticks = {"n": 0}

    def hook(_drv):
        ticks["n"] += 1
        if drv.ref.ir != OP_SCAN:  # explicit, independent of the model's outputs
            got = _ctrl(dut)
            assert not any(got.values()), f"IR={drv.ref.ir:#x} != SCAN but outputs {got}"

    drv.post_tick_hooks.append(hook)
    others = (OP_IDCODE, OP_BYPASS, OP_EXTEST, OP_SAMPLE, OP_MBIST_CTRL, OP_MBIST_STATUS, 9, 14)
    for sel in range(8):
        for rst in (0, 1):
            await drv.write_tdr(OP_SCAN_SEL, sel, 3)
            await drv.write_tdr(OP_SCAN_RST, rst, 1)
            assert int(dut.scan_sel_q_o.value) == sel and int(dut.scan_rst_q_o.value) == rst
            for op in others[(sel + rst) % 3 :: 3]:  # a different subset of other opcodes each time
                await drv.load_ir(op)
                assert not any(_ctrl(dut).values())
            # run-test idle and DR traffic with the TDRs loaded
            await drv.walk([0, 0, 1, 0, 0, 0, 1, 1, 0])
    assert ticks["n"] > 1000, "vacuity guard: expected a long run"
    # negative control: SCAN with the last TDR values (sel=7, rst=1) raises the controls ...
    await drv.load_ir(OP_SCAN)
    got = _ctrl(dut)
    assert got == {
        "scan_mode": 1,
        "serial": 0,
        "parallel": 1,
        "rst_assert": 1,
        "scan_en": 0,
        "chain_grp": 3,
    }, got
    # ... and any other IR drops them again although both TDRs still hold nonzero values
    await drv.load_ir(OP_BYPASS)
    assert not any(_ctrl(dut).values())
    assert int(dut.scan_sel_q_o.value) == 7 and int(dut.scan_rst_q_o.value) == 1, (
        "TDRs must persist"
    )
    # TLR clears the TDRs
    await drv.reset_tms()
    assert int(dut.scan_sel_q_o.value) == 0 and int(dut.scan_rst_q_o.value) == 0


# ---------------------------------------------------------------------------
async def t_scan_outputs_per_spec(dut, cfg):
    drv = await _setup(dut, cfg)
    seen_scan_en = 0
    seen_shift_en = 0
    for sel in range(8):
        for rst in (0, 1):
            await drv.enter_scan(sel=sel, rst=rst)
            parallel = sel & 1
            want = {
                "scan_mode": 1,
                "serial": 1 - parallel,
                "parallel": parallel,
                "rst_assert": rst,
                "chain_grp": sel >> 1,
            }
            # walk a DR scan through every DR state; record the outputs in each state
            tour = [
                (1, "SELDR"), (0, "CAPDR"), (0, "SHDR"), (0, "SHDR"), (1, "EX1DR"),
                (0, "PAUDR"), (1, "EX2DR"), (0, "SHDR"), (1, "EX1DR"), (1, "UPDR"), (0, "RTI"),
            ]  # fmt: skip
            prev_scan_en = 0
            for tms, state in tour:
                await drv.tick(tms)
                assert drv.ref.state == state
                s = drv.snaps["fall"]
                for k, v in want.items():
                    assert s[k] == v, f"sel={sel} rst={rst} state={state}: {k}={s[k]}, expected {v}"
                en = int(state == "SHDR" and not parallel)
                assert s["scan_en"] == en, (
                    f"sel={sel} state={state}: scan_en_o={s['scan_en']}, expected {en} "
                    "(1 only in Shift-DR and only for the serial TAP path)"
                )
                gate = int(state in ("CAPDR", "SHDR") and not parallel)
                assert s["shift_clk_en"] == gate, (
                    f"sel={sel} state={state}: shift_clk_en_o={s['shift_clk_en']}, expected {gate}"
                )
                # falling-edge property: at 1 ps after the rising edge scan_en_o is still the
                # previous state's value
                assert drv.snaps["rise"]["scan_en"] == prev_scan_en, (
                    f"scan_en_o changed on the RISING edge into {state}"
                )
                prev_scan_en = en
                seen_scan_en += en
                seen_shift_en += gate
            # leaving scan mode (any other IR) clears every control
            await drv.load_ir(OP_BYPASS)
            assert not any(_ctrl(dut).values())
    # 4 serial SCAN_SEL values x 2 SCAN_RST values = 8 serial combinations; each tour has 3
    # Shift-DR cycles and 1 Capture-DR + 3 Shift-DR clock-gate-enable cycles
    assert seen_scan_en == 8 * 3 and seen_shift_en == 8 * 4, (
        f"vacuity guard: scan_en observed {seen_scan_en}x, shift_clk_en {seen_shift_en}x"
    )


# ---------------------------------------------------------------------------
async def t_outputs_change_only_on_tck_falling_edge(dut, cfg):
    sigs = {
        "tdo": dut.tdo_o, "tdo_oe": dut.tdo_oe_o, "scan_mode": dut.scan_mode_o,
        "serial": dut.serial_o, "parallel": dut.parallel_o, "rst_assert": dut.rst_assert_o,
        "scan_en": dut.scan_en_o, "chain_grp": dut.chain_grp_o, "state": dut.state_o,
        "shift_clk_en": dut.shift_clk_en_o, "ir_q": dut.ir_q_o, "scan_sel_q": dut.scan_sel_q_o,
        "scan_rst_q": dut.scan_rst_q_o,
    }  # fmt: skip
    log = EdgeLog(sigs, dut.tck_i, dut.trst_ni).start()
    drv = await _setup(dut, cfg)
    sys0 = int(dut.sys_cnt_o.value)
    # serial scan, parallel scan, IR/DR traffic, resets
    await drv.enter_scan(sel=0b010, rst=1)
    await drv.shift_dr(0, 9)
    await drv.enter_scan(sel=0b111, rst=0)
    await drv.shift_dr(0, 5)
    await drv.load_ir(OP_IDCODE)
    await drv.shift_dr(0, 32)
    await drv.enter_scan(sel=0b001, rst=1)
    await drv.assert_trst()
    await drv.release_trst()
    await drv.walk([1] * 5)
    rng = random.Random(7)
    for _ in range(300):
        await drv.tick(rng.getrandbits(1), rng.getrandbits(1))
    falling_names = (
        "tdo", "tdo_oe", "scan_mode", "serial", "parallel", "rst_assert",
        "scan_en", "chain_grp", "ir_q", "scan_sel_q", "scan_rst_q",
    )  # fmt: skip
    falling = {k: "fall" for k in falling_names}
    rule = dict(falling, state="rise")
    bad = log.violations(rule)
    assert not bad, f"outputs changed at a time that is not their TCK edge: {bad[:6]}"
    # shift_clk_en_o is combinational but may only move at a TCK edge (or TRST_N), never between
    edge_times = set(log.rise_t) | set(log.fall_t) | set(log.trst_fall_t)
    stray = [e for e in log.events if e[0] == "shift_clk_en" and e[1] not in edge_times]
    assert not stray, f"shift_clk_en_o changed between TCK edges: {stray[:4]}"
    # vacuity guards: every checked output really moved, several times
    for name in ("tdo", "tdo_oe", "scan_mode", "serial", "parallel", "rst_assert", "scan_en",
                 "chain_grp", "state", "shift_clk_en", "ir_q", "scan_sel_q"):  # fmt: skip
        assert log.count(name) >= 4, f"{name} changed only {log.count(name)}x: test is vacuous"
    # negative controls: the same log MUST report violations under the wrong rule
    assert log.violations({"state": "fall"}), (
        "state_o changes at rising edges: wrong rule must fail"
    )
    assert log.violations({"tdo": "rise"}), "tdo_o changes at falling edges: wrong rule must fail"
    assert log.violations({"scan_mode": "rise"}), "scan_mode_o changes at falling edges"
    log.stop()
    assert int(dut.sys_cnt_o.value) != sys0, "system clock did not run during the test"


# ---------------------------------------------------------------------------
async def t_random_walk_lock_step(dut, cfg):
    drv = await _setup(dut, cfg)
    rng = random.Random(0x7A9 + cfg[0])
    visited = set()
    edges = set()
    irs = set()
    scan_cycles = 0
    for i in range(3000):
        if i % 100 == 50:  # periodic directed traffic so SCAN / the TDRs are really exercised
            op = rng.choice(
                [
                    OP_SCAN,
                    OP_SCAN,
                    OP_SCAN_SEL,
                    OP_SCAN_RST,
                    OP_IDCODE,
                    OP_BYPASS,
                    rng.randrange(16),
                ]
            )
            await drv.shift_ir(op)
            if op in (OP_SCAN_SEL, OP_SCAN_RST):
                n = 3 if op == OP_SCAN_SEL else 1
                await drv.shift_dr(rng.getrandbits(n), n)
            irs.add(drv.ref.ir)
            scan_cycles += 10 * int(drv.ref.out["scan_mode"])
        r = rng.random()
        if r < 0.004:  # asynchronous TRST_N pulse between cycles, TCK low
            await drv.assert_trst()
            await Timer(rng.randrange(100, 2 * drv.T), "ps")
            await drv.release_trst()
            await Timer(rng.randrange(1, drv.H - 2), "ps")
            continue
        s0 = drv.ref.state
        tms = rng.getrandbits(1)
        tdi = rng.getrandbits(1)
        if r < 0.008:  # TRST_N pulse in the middle of a cycle, TCK high
            await drv.tick(tms, tdi, trst_in_high_ps=rng.randrange(50, drv.H // 2))
        else:
            # bias towards DR/IR traffic: dwell in the shift states more often than uniform
            if s0 in ("SHDR", "SHIR") and rng.random() < 0.6:
                tms = 0
            await drv.tick(tms, tdi)
        visited.add(s0)
        edges.add((s0, tms))
        irs.add(drv.ref.ir)
        scan_cycles += int(drv.ref.out["scan_mode"])
    assert visited == set(STATES), f"random walk missed states {set(STATES) - visited}"
    assert len(edges) >= 30, f"random walk covered only {len(edges)}/32 transitions"
    assert len(irs) >= 8, f"random walk loaded only {len(irs)} distinct opcodes"
    assert scan_cycles > 100, "random walk spent too little time in SCAN"


# ---------------------------------------------------------------------------
# One generated test per (TCK period, system clock period) configuration.
for _fn in (
    t_state_encodings_and_all_32_transitions,
    t_trst_is_asynchronous_from_every_state,
    t_trst_in_the_middle_of_a_cycle,
    t_five_tms_ones_reach_tlr_from_every_state,
    t_ir_capture_and_update_timing,
    t_bypass_is_a_one_bit_delay,
    t_idcode_after_reset_without_loading_ir,
    t_tdr_write_and_readback,
    t_tdrs_reset_by_tlr_and_trst,
    t_scan_stub_is_a_one_bit_delay,
    t_every_opcode_decodes_as_specified,
    t_tdo_and_oe_per_state,
    t_scan_mode_only_from_ir_scan,
    t_scan_outputs_per_spec,
    t_outputs_change_only_on_tck_falling_edge,
    t_random_walk_lock_step,
):
    _fn.__name__ = _fn.__qualname__ = "test_" + _fn.__name__[2:]
    _tf = TestFactory(_fn)
    _tf.add_option("cfg", CFGS)
    _tf.generate_tests(postfix="_tck")
