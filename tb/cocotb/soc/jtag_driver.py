"""
jtag_driver.py -- JTAG TAP driver, reference model and edge logger (bead j41m.3, DFT Stage 1b).

Shared by test_jtag_tap.py (module jtag_tap alone), test_dft_ctrl.py (dft_ctrl) and
test_soc_jtag.py (soc_top via tb_soc_pll).  Everything here is written from
docs/design/DFT_ARCHITECTURE.md section 15 (TAP rules 15.2, instruction map 15.3), NOT from the RTL,
so the reference model is an independent second implementation of the spec.

Pieces
  NEXT / ENC / OP_*      the IEEE 1149.1 state graph, the standard 4-bit state encodings, the
                         private opcode map of section 15.3
  TapRef                 cycle-accurate reference model: rise(tms, tdi) = TCK rising edge,
                         fall() = TCK falling edge, async_reset()/release() = TRST_N.  State and
                         shift registers move on the rising edge; the update registers, TDO and
                         every SoC-facing output move on the FALLING edge (section 15.2).
  JtagDriver             drives tck/tms/tdi/trst_n, runs TapRef in lock step, and after EVERY tick
                         compares whatever the bench's probe() returns (any subset of the TapRef
                         output names plus 'state') against the model at three instants:
                           pre_rise   half a period after the falling edge, with TMS/TDI already
                                      changed  -> catches any output that depends combinationally
                                      on TMS/TDI, or that drifts between edges
                           post_rise  1 ps after the rising edge -> the falling-edge outputs must
                                      NOT have moved; state/shift_clk_en must have
                           post_fall  1 ps after the falling edge -> everything has its new value
  EdgeLog                records every value change of a set of signals with its simulation time and
                         the times of every TCK rising/falling edge and TRST_N assertion, so a test
                         can prove "this output only ever changes at a TCK falling edge".

Timeline of one tick (period T, half H, all in ps):
  F   TCK falls (TMS/TDI of the next cycle are driven at F+1 ps, after the post_fall check)
  F+H TDO is sampled (this is the bit the tester would capture at this rising edge), TCK rises
  F+T TCK falls again
Resolution is 1 ps; Verilator under cocotb runs at 1 ps precision.
"""

import bisect
from collections import deque

import cocotb
from cocotb.triggers import Edge, Timer
from cocotb.utils import get_sim_time

# ---------------------------------------------------------------------------
# IEEE 1149.1 state graph (independent of the RTL)
# ---------------------------------------------------------------------------
# name: (next state if TMS=0, next state if TMS=1)
NEXT = {
    "TLR": ("RTI", "TLR"),
    "RTI": ("RTI", "SELDR"),
    "SELDR": ("CAPDR", "SELIR"),
    "CAPDR": ("SHDR", "EX1DR"),
    "SHDR": ("SHDR", "EX1DR"),
    "EX1DR": ("PAUDR", "UPDR"),
    "PAUDR": ("PAUDR", "EX2DR"),
    "EX2DR": ("SHDR", "UPDR"),
    "UPDR": ("RTI", "SELDR"),
    "SELIR": ("CAPIR", "TLR"),
    "CAPIR": ("SHIR", "EX1IR"),
    "SHIR": ("SHIR", "EX1IR"),
    "EX1IR": ("PAUIR", "UPIR"),
    "PAUIR": ("PAUIR", "EX2IR"),
    "EX2IR": ("SHIR", "UPIR"),
    "UPIR": ("RTI", "SELDR"),
}
ENC = {
    "TLR": 0xF,
    "RTI": 0xC,
    "SELDR": 0x7,
    "CAPDR": 0x6,
    "SHDR": 0x2,
    "EX1DR": 0x1,
    "PAUDR": 0x3,
    "EX2DR": 0x0,
    "UPDR": 0x5,
    "SELIR": 0x4,
    "CAPIR": 0xE,
    "SHIR": 0xA,
    "EX1IR": 0x9,
    "PAUIR": 0xB,
    "EX2IR": 0x8,
    "UPIR": 0xD,
}
DEC = {v: k for k, v in ENC.items()}
STATES = list(NEXT)  # 16 names

# Private opcode map, section 15.3
OP_EXTEST = 0x0
OP_IDCODE = 0x1
OP_SAMPLE = 0x2
OP_SCAN_SEL = 0x3
OP_SCAN = 0x4
OP_SCAN_RST = 0x5
OP_MBIST_CTRL = 0x6
OP_MBIST_STATUS = 0x7
OP_BYPASS = 0xF
IDCODE_VAL = 0x15C0_1001
IR_CAPTURE = 0b0001

# Output names of TapRef.out that change on the falling edge only (section 15.2)
FALLING_OUTS = (
    "tdo",
    "tdo_oe",
    "scan_mode",
    "serial",
    "parallel",
    "rst_assert",
    "scan_en",
    "chain_grp",
    "mbist_wr",
    "mbist_force",
)
MB_CTL_LEN = 29
MB_ST_LEN = 140
SHIFT_STATES = ("SHIR", "SHDR")


def path_to(src: str, dst: str):
    """Shortest TMS sequence from state `src` to state `dst` (BFS; [] if already there)."""
    if src == dst:
        return []
    seen = {src}
    q = deque([(src, [])])
    while q:
        s, p = q.popleft()
        for tms in (0, 1):
            n = NEXT[s][tms]
            if n in seen:
                continue
            if n == dst:
                return p + [tms]
            seen.add(n)
            q.append((n, p + [tms]))
    raise AssertionError(f"no path {src} -> {dst}")


def bits_of(value: int, n: int):
    """LSB-first list of n bits."""
    return [(value >> i) & 1 for i in range(n)]


def int_of(bits) -> int:
    """Inverse of bits_of (bits[0] is the LSB)."""
    return sum((b & 1) << i for i, b in enumerate(bits))


# ---------------------------------------------------------------------------
# Reference model
# ---------------------------------------------------------------------------
class TapRef:
    """Cycle-accurate model of the section-15 TAP. `out` holds the falling-edge outputs."""

    def __init__(self):
        self.held = True
        # Test-controlled inputs of the MBIST TDRs: the 139-bit status word presented to Capture-DR of
        # MBIST_STATUS and whether the control-word FIFO can accept a write.
        self.mb_status = 0
        self.mb_ready = True
        self.async_reset()

    def async_reset(self):
        """TRST_N asserted: every flop in its reset state, immediately."""
        self.held = True
        self.state = "TLR"
        self.ir_shift = IR_CAPTURE
        self.ir = OP_IDCODE
        self.dr = 0
        self.sel = 0  # SCAN_SEL update register
        self.rst = 0  # SCAN_RST update register
        self.rst_edges_left = 2
        self.mb_ctl = 0  # MBIST_CTRL update register
        self.mb_ovf = 0  # sticky control-word overflow
        self.tlr_prev = 0
        self.out = {k: 0 for k in FALLING_OUTS}

    def release(self):
        """TRST_N released: the release goes through a 2-stage TCK synchroniser, so the first two
        TCK rising edges after release still see the TAP in reset (section 15.2)."""
        self.held = False
        self.rst_edges_left = 2

    # -- DR geometry -------------------------------------------------------
    def dr_len(self, ir=None) -> int:
        ir = self.ir if ir is None else ir
        return {OP_IDCODE: 32, OP_SCAN_SEL: 3, OP_MBIST_CTRL: MB_CTL_LEN, OP_MBIST_STATUS: MB_ST_LEN}.get(ir, 1)

    def dr_capture(self) -> int:
        if self.ir == OP_IDCODE:
            return IDCODE_VAL
        if self.ir == OP_SCAN_SEL:
            return self.sel
        if self.ir == OP_SCAN_RST:
            return self.rst
        if self.ir == OP_MBIST_CTRL:
            return self.mb_ctl
        if self.ir == OP_MBIST_STATUS:
            return (self.mb_status << 1) | self.mb_ovf
        return 0  # BYPASS, SCAN stub, and every unimplemented/unknown opcode

    # -- TCK edges ----------------------------------------------------------
    def rise(self, tms: int, tdi: int):
        if self.held:
            return
        if self.rst_edges_left > 0:
            self.rst_edges_left -= 1
            return
        s = self.state
        if s == "CAPIR":
            self.ir_shift = IR_CAPTURE
        elif s == "SHIR":
            self.ir_shift = (self.ir_shift >> 1) | (tdi << 3)
        if s == "CAPDR":
            self.dr = self.dr_capture()
        elif s == "SHDR":
            n = self.dr_len()
            self.dr = (self.dr >> 1) | (tdi << (n - 1))
        # sticky overflow flag, sampled at the rising edge that the FIFO would write on
        if self.out["mbist_wr"]:
            if not self.mb_ready:
                self.mb_ovf = 1
            elif not (self.mb_ctl & 1):
                self.mb_ovf = 0
        self.state = NEXT[s][tms]

    def fall(self):
        if self.held:
            return
        s = self.state
        if s == "TLR":
            ir_d, sel_d, rst_d, mb_d = OP_IDCODE, 0, 0, 0
        else:
            ir_d = self.ir_shift if s == "UPIR" else self.ir
            sel_d = self.dr if (s == "UPDR" and self.ir == OP_SCAN_SEL) else self.sel
            rst_d = self.dr if (s == "UPDR" and self.ir == OP_SCAN_RST) else self.rst
            mb_d = self.dr if (s == "UPDR" and self.ir == OP_MBIST_CTRL) else self.mb_ctl
        tdo = 0
        if s == "SHIR":
            tdo = self.ir_shift & 1
        elif s == "SHDR":
            tdo = self.dr & 1
        scan = ir_d == OP_SCAN
        sel0 = sel_d & 1
        serial = int(scan and not sel0)
        self.out = {
            "tdo": tdo,
            "tdo_oe": int(s in SHIFT_STATES),
            "scan_mode": int(scan),
            "serial": serial,
            "parallel": int(scan and bool(sel0)),
            "rst_assert": int(scan and bool(rst_d & 1)),
            "scan_en": int(s == "SHDR" and bool(serial)),
            "chain_grp": ((sel_d >> 1) & 3) if scan else 0,
            "mbist_wr": int(
                self.rst_edges_left == 0
                and ((s == "UPDR" and self.ir == OP_MBIST_CTRL) or (s == "TLR" and not self.tlr_prev))
            ),
            "mbist_force": int((mb_d & 1) and bool((mb_d >> 28) & 1)),
        }
        if self.rst_edges_left == 0:  # the falling-edge flops are still in reset during the release window
            self.tlr_prev = int(s == "TLR")
        self.ir, self.sel, self.rst, self.mb_ctl = ir_d, sel_d, rst_d, mb_d

    # -- derived (combinational in the RTL) --------------------------------------
    @property
    def shift_clk_en(self) -> int:
        return int(bool(self.out["serial"]) and self.state in ("CAPDR", "SHDR"))

    def expected(self) -> dict:
        d = dict(self.out)
        d["state"] = ENC[self.state]
        d["shift_clk_en"] = self.shift_clk_en
        d["ir_q"] = self.ir  # update registers (falling edge of Update-IR / Update-DR / TLR)
        d["scan_sel_q"] = self.sel
        d["scan_rst_q"] = self.rst
        d["mb_ctl_q"] = self.mb_ctl
        d["mbist_ovf"] = self.mb_ovf
        return d


# ---------------------------------------------------------------------------
# Edge logger
# ---------------------------------------------------------------------------
class EdgeLog:
    """Logs every change of `sigs` ({name: handle}) with its simulation time, and the TCK
    rising/falling edge times and TRST_N falling times.  Start it BEFORE the stimulus."""

    def __init__(self, sigs, tck, trst_n=None):
        self.sigs = sigs
        self.tck = tck
        self.trst_n = trst_n
        self.events = []  # (name, t_ps, old, new)
        self.rise_t = []
        self.fall_t = []
        self.trst_fall_t = []
        self._tasks = []

    async def _watch(self, name, sig):
        prev = int(sig.value)
        while True:
            await Edge(sig)
            new = int(sig.value)
            self.events.append((name, int(get_sim_time("ps")), prev, new))
            prev = new

    async def _watch_tck(self):
        prev = int(self.tck.value)
        while True:
            await Edge(self.tck)
            new = int(self.tck.value)
            (self.rise_t if new and not prev else self.fall_t if prev and not new else []).append(
                int(get_sim_time("ps"))
            )
            prev = new

    async def _watch_trst(self):
        prev = int(self.trst_n.value)
        while True:
            await Edge(self.trst_n)
            new = int(self.trst_n.value)
            if prev and not new:
                self.trst_fall_t.append(int(get_sim_time("ps")))
            prev = new

    def start(self):
        for n, s in self.sigs.items():
            self._tasks.append(cocotb.start_soon(self._watch(n, s)))
        self._tasks.append(cocotb.start_soon(self._watch_tck()))
        if self.trst_n is not None:
            self._tasks.append(cocotb.start_soon(self._watch_trst()))
        return self

    def stop(self):
        for t in self._tasks:
            t.kill()
        self._tasks = []

    def count(self, name) -> int:
        return sum(1 for e in self.events if e[0] == name)

    def violations(self, rule):
        """rule: {name: 'fall' | 'rise' | 'any'}.  Returns events that happened at a time that is
        not allowed for their signal.  'fall' = a TCK falling edge, or the instant TRST_N was
        asserted (asynchronous reset); 'rise' = a TCK rising edge or a TRST_N assertion."""
        fall = set(self.fall_t) | set(self.trst_fall_t)
        rise = set(self.rise_t) | set(self.trst_fall_t)
        bad = []
        for name, t, old, new in self.events:
            r = rule.get(name, "any")
            if r == "fall" and t not in fall:
                bad.append((name, t, old, new))
            elif r == "rise" and t not in rise:
                bad.append((name, t, old, new))
        return bad


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------
class JtagDriver:
    """Drives one TAP port set and checks it against TapRef after every tick.

    probe: callable returning {name: int} for any subset of TapRef.expected() keys
           ('tdo','tdo_oe','state','scan_mode','serial','parallel','rst_assert','scan_en',
           'chain_grp','shift_clk_en','ir_q','scan_sel_q','scan_rst_q');
           compared at pre_rise / post_rise / post_fall.
           None = no checking (the bench has nothing to compare).
    """

    def __init__(self, tck, tms, tdi, trst_n, tdo, period_ns=10, probe=None, name="tap"):
        self.tck, self.tms, self.tdi, self.trst_n, self.tdo = tck, tms, tdi, trst_n, tdo
        self.T = int(round(period_ns * 1000))
        assert self.T >= 100 and self.T % 2 == 0, "period must be an even number of ps >= 100"
        self.H = self.T // 2
        self.probe = probe
        self.name = name
        self.ref = TapRef()
        self.snaps = {}  # 'pre', 'rise', 'fall' -> probe() dict at the last tick
        # (state_before_rising_edge, tms, tdi, tdo_sampled, rise_time_ps, serial_flag)
        self.tick_log = []
        self.n_ticks = 0
        self.post_tick_hooks = []  # callables(driver), run after every tick's post_fall check

    # -- checking ----------------------------------------------------------------
    def _compare(self, phase, strict_keys_only=False):
        if self.probe is None:
            return None
        got = self.probe()
        exp = self.ref.expected()
        for k, v in got.items():
            if strict_keys_only and k not in FALLING_OUTS and k != "state":
                continue
            assert k in exp, f"[{self.name}] probe key {k!r} unknown to the reference model"
            assert int(v) == int(exp[k]), (
                f"[{self.name}] {phase}: {k}={int(v):#x}, spec model says {int(exp[k]):#x} "
                f"(model state {self.ref.state}, ir {self.ref.ir:#x}, tick {self.n_ticks})"
            )
        return got

    # -- low-level pin control -------------------------------------------------------
    def idle_pins(self, trst_n=0):
        """TCK low, TMS=1, TDI=0, TRST_N as given (default: TAP held in reset)."""
        self.tck.value = 0
        self.tms.value = 1
        self.tdi.value = 0
        self.trst_n.value = trst_n
        if trst_n == 0:
            self.ref.async_reset()

    async def start(self, hold_reset=False):
        """Power-up sequence.  TRST_N is driven HIGH from time 0 and five TMS=1 cycles (plus one)
        bring the TAP to Test-Logic-Reset from whatever state the simulator initialised it to,
        exactly as a tester that has no TRST_N pin would do.  (Starting with TRST_N low from time
        0 would never create a falling edge on the reset net, so the asynchronous clear would not
        fire before the first TCK edge -- the spec's open question Q-TRST, power-up state.)
        The model is compared from the moment the TAP is known to be in TLR.
        hold_reset=True then asserts TRST_N (a real falling edge) and leaves it low."""
        probe, self.probe = self.probe, None
        self.tck.value = 0
        self.tms.value = 1
        self.tdi.value = 0
        self.trst_n.value = 1
        self.ref = TapRef()
        self.ref.held = False
        self.ref.rst_edges_left = 0
        await Timer(2 * self.T, "ps")
        for _ in range(6):
            await self.tick(1, 0)
        self.probe = probe
        self._compare("power-up Test-Logic-Reset")
        if hold_reset:
            await self.assert_trst()

    async def assert_trst(self, settle_ps=1):
        """Asynchronous TAP reset: TRST_N low, no clock needed."""
        self.trst_n.value = 0
        self.ref.async_reset()
        await Timer(settle_ps, "ps")
        self._compare("trst_assert")

    async def release_trst(self):
        """TRST_N high (at an arbitrary instant: caller decides where in the TCK cycle)."""
        self.trst_n.value = 1
        self.ref.release()
        await Timer(1, "ps")
        self._compare("trst_release")

    # -- one TCK cycle --------------------------------------------------------------
    async def tick(self, tms, tdi=0, trst_in_high_ps=None):
        """One full TCK cycle starting at a falling edge (TCK is low on entry).
        Returns the TDO value sampled just before the rising edge (the bit a tester captures).
        trst_in_high_ps: if set, TRST_N is pulsed low for that many ps shortly after the rising
        edge (TCK high), i.e. an asynchronous reset in the middle of a cycle."""
        self.tms.value = tms
        self.tdi.value = tdi
        await Timer(self.H - 1, "ps")
        sampled = int(self.tdo.value)
        self.snaps["pre"] = self._compare("pre_rise")
        state_before = self.ref.state
        serial_before = self.ref.out["serial"]
        self.tck.value = 1
        self.ref.rise(tms, tdi)
        t_rise = int(get_sim_time("ps"))
        await Timer(1, "ps")
        self.snaps["rise"] = self._compare("post_rise")
        self.tick_log.append((state_before, tms, tdi, sampled, t_rise, serial_before))
        remaining = self.H - 1
        if trst_in_high_ps is not None:
            assert 1 <= trst_in_high_ps < remaining - 2
            await self.assert_trst()
            await Timer(trst_in_high_ps, "ps")
            await self.release_trst()
            remaining -= trst_in_high_ps + 2
        await Timer(remaining, "ps")
        self.tck.value = 0
        self.ref.fall()
        await Timer(1, "ps")
        self.snaps["fall"] = self._compare("post_fall")
        self.n_ticks += 1
        for hook in self.post_tick_hooks:
            hook(self)
        return sampled

    async def walk(self, tms_bits, tdi_bits=None):
        """Apply a TMS sequence (TDI defaults to 0).  Returns the list of sampled TDO bits."""
        tdi_bits = tdi_bits if tdi_bits is not None else [0] * len(tms_bits)
        out = []
        for m, d in zip(tms_bits, tdi_bits):
            out.append(await self.tick(m, d))
        return out

    async def settle(self):
        """After a TRST_N release the TAP ignores the first two TCK edges (release synchroniser):
        burn them with TMS=1 (stays in Test-Logic-Reset) so register scans start from a live TAP."""
        assert not self.ref.held, "TRST_N is still asserted"
        while self.ref.rst_edges_left > 0:
            await self.tick(1, 0)

    async def goto(self, target):
        """Walk the shortest TMS path from the model's current state to `target`."""
        await self.settle()
        return await self.walk(path_to(self.ref.state, target))

    async def reset_tms(self):
        """Five TMS=1 cycles: Test-Logic-Reset from any state."""
        return await self.walk([1] * 5)

    # -- register scans --------------------------------------------------------------
    async def shift_ir(self, value, n=4, end="RTI"):
        """Load `value` into the IR (Capture-IR, n Shift-IR cycles, Update-IR).
        Returns the captured/shifted-out value (LSB first), i.e. the IR capture pattern."""
        await self.goto("RTI")
        await self.walk([1, 1, 0, 0])  # SELDR, SELIR, CAPIR, SHIR
        assert self.ref.state == "SHIR"
        out = []
        for i in range(n):
            out.append(await self.tick(1 if i == n - 1 else 0, (value >> i) & 1))
        await self.tick(1)  # UPIR
        if end == "RTI":
            await self.tick(0)
        return int_of(out)

    async def shift_dr(self, value, n, end="RTI", stream=None):
        """Capture-DR, n Shift-DR cycles (TDI = `value` LSB first, or an explicit `stream` list of
        bits), Update-DR.  Returns the shifted-out bits as an int (LSB first) and keeps the list
        in self.last_bits."""
        await self.goto("RTI")
        await self.walk([1, 0, 0])  # SELDR, CAPDR, SHDR
        assert self.ref.state == "SHDR"
        tdi_bits = stream if stream is not None else bits_of(value, n)
        assert len(tdi_bits) == n
        out = []
        for i in range(n):
            out.append(await self.tick(1 if i == n - 1 else 0, tdi_bits[i]))
        await self.tick(1)  # UPDR
        if end == "RTI":
            await self.tick(0)
        self.last_bits = out
        return int_of(out)

    async def load_ir(self, opcode):
        """shift_ir with an assertion on the IR capture pattern (...01, LSB first)."""
        cap = await self.shift_ir(opcode)
        assert cap == IR_CAPTURE, f"IR capture pattern {cap:#06b}, expected 0b0001"
        return cap

    async def write_tdr(self, opcode, value, n):
        """Select `opcode` then shift `value` (n bits) into its DR and update."""
        await self.load_ir(opcode)
        return await self.shift_dr(value, n)

    async def enter_scan(self, sel=0, rst=0):
        """Program SCAN_SEL=sel and SCAN_RST=rst (each with IR != SCAN), then select SCAN."""
        await self.write_tdr(OP_SCAN_SEL, sel, 3)
        await self.write_tdr(OP_SCAN_RST, rst, 1)
        await self.load_ir(OP_SCAN)

    async def measure_dr_length(self, cap_bits=33):
        """Length of the currently selected DR, measured by marker flush: cap_bits+7 zeros, a 1,
        cap_bits+16 zeros; the marker re-appears at output index (cap_bits+7) + length. Captured
        bits are all at index < cap_bits (default 33: the 32-bit IDCODE is the longest short DR)."""
        pre = cap_bits + 7
        stream = [0] * pre + [1] + [0] * (cap_bits + 16)
        await self.shift_dr(0, len(stream), stream=stream)
        out = self.last_bits
        idx = [i for i in range(cap_bits, len(out)) if out[i] == 1]
        assert len(idx) == 1, f"marker not found exactly once in the shifted-out stream: {out}"
        return idx[0] - pre


# ---------------------------------------------------------------------------
# Clock-pulse analysis for the glitch-free test-clock switch (dft_clk_switch)
# ---------------------------------------------------------------------------
# Used by test_dft_clk_switch.py (the switch alone), test_dft_ctrl.py and test_soc_jtag.py (the
# switch inside dft_ctrl / soc_top).  Everything works on EDGE-TIME LOGS (EdgeLog.events) of the two
# source clocks and the switch output, never on the RTL: a clock is a list of (rise_ps, fall_ps)
# pulses; all clocks idle low.  A healthy switch output is a SUBSET of the source pulses, every one
# passed WHOLE (same rise time AND same fall time as exactly one source pulse), never shortened,
# never merged with a pulse of the other source, never separated from the previous output pulse by
# less than the shortest phase of either source.


def events_of(events, name):
    """[(t_ps, new_value)] of one signal from EdgeLog.events."""
    return [(t, new) for (n, t, _old, new) in events if n == name]


def pulses_of(events, name, allow_open=False):
    """[(rise_ps, fall_ps)] from an EdgeLog event list (signal assumed low before its first
    event).  A signal that is still high at the end of the log is an error unless allow_open
    (then the open pulse has fall = None)."""
    out, rise = [], None
    for t, v in events_of(events, name):
        if v and rise is None:
            rise = t
        elif not v and rise is not None:
            out.append((rise, t))
            rise = None
    if rise is not None:
        assert allow_open, f"{name} is still high at the end of the log (rose at {rise} ps)"
        out.append((rise, None))
    return out


def level_at(pulses, t, rises=None):
    """Level of a pulse list at time t AFTER all events of that time step (a fall at t -> 0).
    rises: optional precomputed [p[0] for p in pulses] (avoids O(n) per call)."""
    rises = rises if rises is not None else [p[0] for p in pulses]
    i = bisect.bisect_right(rises, t) - 1
    return int(i >= 0 and (pulses[i][1] is None or t < pulses[i][1]))


def label_output_pulses(out, a, b, min_phase, loose=False, gap_skip=()):
    """Classify every output pulse against the source pulse lists.
    Returns (labels, problems): labels[i] is 'A' or 'B' (the output pulse equals ONE whole source
    pulse: same rise and same fall), 'AB' (identical in both sources: ambiguous), 'M' (loose mode
    only: a merge of overlapping source pulses -- rise is a source rise, fall is a source fall, and
    the whole interval is covered by source-high time), or None (a problem).
    problems: human-readable strings; also reported: output high pulses or low gaps shorter than
    min_phase (runts, the defect a plain mux has).  gap_skip: [(t0, t1)] windows (the async-reset
    merge window) inside which a low gap between two whole pulses is tolerated: with both enables
    briefly on, an A pulse in progress can be followed closely by a B pulse."""
    a_by_rise, b_by_rise = dict(a), dict(b)
    src_rise = set(a_by_rise) | set(b_by_rise)
    src_fall = {f for _r, f in a} | {f for _r, f in b}
    union = []  # merged source-high intervals
    for r, f in sorted(a + b):
        if union and r <= union[-1][1]:
            union[-1][1] = max(union[-1][1], f)
        else:
            union.append([r, f])
    labels, problems = [], []
    for r, f in out:
        la, lb = a_by_rise.get(r) == f, b_by_rise.get(r) == f
        w = f - r
        if w < min_phase:
            problems.append(f"runt-high [{r},{f}] width {w} ps < min phase {min_phase} ps")
        if la and lb:
            labels.append("AB")
        elif la:
            labels.append("A")
        elif lb:
            labels.append("B")
        else:
            covered = any(u0 <= r and f <= u1 for u0, u1 in union)
            if loose and r in src_rise and f in src_fall and covered and w >= min_phase:
                labels.append("M")
                continue
            if r in src_rise and f in src_fall and covered:
                why = "merge of overlapping A and B pulses"
            elif r in src_rise:
                why = "truncated: rises with a source edge, falls at no source fall"
            elif f in src_fall:
                why = "late start: falls with a source edge, rises at no source rise"
            else:
                why = "edges derived from no source edge"
            problems.append(f"bad pulse [{r},{f}] width {w} ps: {why}")
            labels.append(None)
    for (_r0, f0), (r1, _f1) in zip(out, out[1:]):
        if r1 - f0 < min_phase and not any(t0 <= f0 <= t1 for t0, t1 in gap_skip):
            problems.append(f"runt-low gap [{f0},{r1}] {r1 - f0} ps < min phase {min_phase} ps")
    return labels, problems


def check_enable_latches(en_a, en_b, tck_pulses, b_pulses, init_a=0, init_b=0, skip=()):
    """Latch-discipline and exclusion checks on the switch's two enable latches.
    en_a/en_b: [(t, value)] event lists (EdgeLog via events_of).  en_a_q may change only while the
    RAW tck_i is low, en_b_q only while clk_b_i is low (the latch is transparent only then; a change
    while the clock is high would put an edge or a runt on the output), and the two must never be
    high together.  skip: [(t0, t1)] windows (async reset assertion) where exclusion is not checked.
    Returns a list of problem strings."""
    problems = []
    for nm, ev, pul in (("en_a_q", en_a, tck_pulses), ("en_b_q", en_b, b_pulses)):
        rises = [p[0] for p in pul]
        for t, v in ev:
            if level_at(pul, t, rises):
                problems.append(f"{nm} changed to {v} at {t} ps while its clock is high")
    times = sorted({t for t, _v in en_a} | {t for t, _v in en_b})
    ia, ib = 0, 0
    a_cur, b_cur = init_a, init_b
    for t in times:
        while ia < len(en_a) and en_a[ia][0] <= t:
            a_cur = en_a[ia][1]
            ia += 1
        while ib < len(en_b) and en_b[ib][0] <= t:
            b_cur = en_b[ib][1]
            ib += 1
        if a_cur and b_cur and not any(t0 <= t <= t1 for (t0, t1) in skip):
            problems.append(f"en_a_q and en_b_q both high at {t} ps")
    return problems


def check_handover(
    out, labels, pa, pb, tck_rises, t_sw, target, t_end, ub_ps, max_old_pulses=0, lower=3
):
    """One select change at t_sw to `target` ('A' or 'B'), observed until t_end.
    Rules (all per the dft_clk_switch contract):
      * output pulses in [t_sw, t_end) are some old-source pulses (at most max_old_pulses, 0 for the
        shipped design: the old enable drops at once) followed by new-source pulses, never an old
        pulse after a new one, never an unclassifiable pulse;
      * the passed new-source pulses are a contiguous SUFFIX of the new source's pulses (once the
        handover completed every pulse passes, none is skipped);
      * lower bound (lower=3; 0 disables it for steady windows): the first passed new-source pulse
        rises no earlier than the 3rd rising edge after t_sw of the clock that carries the
        handshake (tck_i for ->A, clk_b_i for ->B): a shorter handover would mean a missing
        synchroniser stage;
      * upper bound: every new-source pulse rising at or after t_sw + ub_ps passes.
    Returns (problems, info) with info = {latency_ps (first passed new pulse rise - t_sw or None),
    n_old, n_new, n_new_total}."""
    new = pa if target == "A" else pb
    old_l = "B" if target == "A" else "A"
    sync = tck_rises if target == "A" else [r for r, _f in pb]
    problems = []
    passed_new, passed_old = [], []
    state = "old"
    for i, (r, _f) in enumerate(out):
        if not (t_sw <= r < t_end):
            continue
        lab = labels[i]
        if lab in (None, "M", "AB"):
            problems.append(f"unclassifiable output pulse at {r} ps (label {lab})")
        elif lab == target:
            state = "new"
            passed_new.append(r)
        elif lab == old_l:
            if state == "new":
                problems.append(f"old-source ({lab}) pulse at {r} ps after the handover completed")
            passed_old.append(r)
    if len(passed_old) > max_old_pulses:
        problems.append(
            f"{len(passed_old)} old-source pulses passed after the select changed at {t_sw} ps "
            f"(allowed {max_old_pulses}): {passed_old[:4]}"
        )
    new_rises = [r for r, _f in new if t_sw <= r < t_end]
    if passed_new and new_rises[len(new_rises) - len(passed_new) :] != passed_new:
        problems.append(
            f"passed {target} pulses {passed_new[:4]}.. are not a contiguous suffix of the "
            f"source pulses {new_rises[:6]}..: a pulse was skipped after the handover"
        )
    j = bisect.bisect_right(sync, t_sw)
    if lower and passed_new and j + lower - 1 < len(sync) and passed_new[0] < sync[j + lower - 1]:
        problems.append(
            f"first {target} pulse passed at {passed_new[0]} ps, before handshake-clock rise "
            f"#{lower} ({sync[j + lower - 1]} ps) after the select change at {t_sw} ps"
        )
    passed_set = set(passed_new)
    late = [r for r in new_rises if r >= t_sw + ub_ps and r not in passed_set]
    if late:
        problems.append(
            f"{target} pulses at {late[:4]} ps (>= {ub_ps} ps after the select change at "
            f"{t_sw} ps) were not passed: handover not complete within the bound"
        )
    info = {
        "latency_ps": (passed_new[0] - t_sw) if passed_new else None,
        "n_old": len(passed_old),
        "n_new": len(passed_new),
        "n_new_total": len(new_rises),
    }
    return problems, info
