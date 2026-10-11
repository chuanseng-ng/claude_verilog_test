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
)
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
        self.out = {k: 0 for k in FALLING_OUTS}

    def release(self):
        """TRST_N released: the release goes through a 2-stage TCK synchroniser, so the first two
        TCK rising edges after release still see the TAP in reset (section 15.2)."""
        self.held = False
        self.rst_edges_left = 2

    # -- DR geometry -------------------------------------------------------
    def dr_len(self, ir=None) -> int:
        ir = self.ir if ir is None else ir
        return {OP_IDCODE: 32, OP_SCAN_SEL: 3}.get(ir, 1)

    def dr_capture(self) -> int:
        if self.ir == OP_IDCODE:
            return IDCODE_VAL
        if self.ir == OP_SCAN_SEL:
            return self.sel
        if self.ir == OP_SCAN_RST:
            return self.rst
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
        self.state = NEXT[s][tms]

    def fall(self):
        if self.held:
            return
        s = self.state
        if s == "TLR":
            ir_d, sel_d, rst_d = OP_IDCODE, 0, 0
        else:
            ir_d = self.ir_shift if s == "UPIR" else self.ir
            sel_d = self.dr if (s == "UPDR" and self.ir == OP_SCAN_SEL) else self.sel
            rst_d = self.dr if (s == "UPDR" and self.ir == OP_SCAN_RST) else self.rst
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
        }
        self.ir, self.sel, self.rst = ir_d, sel_d, rst_d

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

    async def measure_dr_length(self):
        """Length of the currently selected DR, measured by marker flush: 40 zeros, a 1, 49 zeros;
        the marker re-appears at output index 40 + length (captured bits are all at index < 33)."""
        stream = [0] * 40 + [1] + [0] * 49
        await self.shift_dr(0, len(stream), stream=stream)
        out = self.last_bits
        idx = [i for i in range(33, len(out)) if out[i] == 1]
        assert len(idx) == 1, f"marker not found exactly once in the shifted-out stream: {out}"
        return idx[0] - 40
