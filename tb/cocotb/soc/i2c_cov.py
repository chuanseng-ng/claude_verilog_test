"""
i2c_cov.py -- functional-coverage model of the I2C master (rtl/periph/i2c_controller.sv), bead h367.

This is the PILOT of the cocotb functional-coverage flow.  The model, the bin-by-bin rationale and
the reachability notes are in ``docs/verification/I2C_FUNCTIONAL_COVERAGE_MODEL.md``; how another
peripheral adds one is in ``docs/verification/FUNCTIONAL_COVERAGE.md``.  Plumbing (coverpoint
construction, YAML export) is ``func_cov.py``; the merge and the gate are
``tools/verif/functional_coverage_report.py``.

Where the samples come from -- nothing here touches the RTL or the DUT's signals
-------------------------------------------------------------------------------
1. **The bus**: ``bfm/i2c_slave.py`` already decodes START / RSTART / ADDR / WR / RD / STOP.  This
   module registers as a passive observer of that event stream (``I2CSlave.add_observer``), so a
   bin is hit by what the master really put on the wire, not by what a test claims.  The BFM also
   reports ("STRETCH", ...) when it starts holding SCL (it is NOT in ``slave.events``).
2. **The register interface**: ``bfm/apb4_master.py`` calls its observers after every completed
   transfer, so CMD / CLKDIV / TIMEOUT / CTRL / IRQ_EN / IRQ_CLR writes and STATUS / IRQ_STAT /
   FIFO_STAT reads are sampled with the value the DUT really saw.  The tests' side-effect-free
   ``_peek`` (the poke-the-prdata trick) feeds ``reg_read`` too.  A write whose byte strobes do not
   cover the field is not sampled (the field's value is unknown).
3. **Assertion-backed scenario samples** for the few facts the pins cannot show (WHICH arbitration
   phase lost, WHICH wait timed out, WHICH ignored-command class): the test calls
   ``COV.arb_loss(...)`` / ``COV.timeout(...)`` / ``COV.cmd_ignored(...)`` / ``COV.abort(...)``
   only AFTER its own assertions for that scenario passed, so a failing scenario samples nothing.

Sampling is a few dict updates per event; ``reg_read`` drops a repeat of the same (register,
value) because a repeated poll cannot reach a new bin.
"""

from __future__ import annotations

import os

import func_cov as fc

# Byte offsets of the 12-register map (rtl/periph/i2c_controller.sv header).
CTRL, STATUS, CLKDIV, ADDR, TX_DATA, RX_DATA, CMD = 0x00, 0x04, 0x08, 0x0C, 0x10, 0x14, 0x18
FIFO_STAT, TIMEOUT, IRQ_EN, IRQ_STAT, IRQ_CLR = 0x1C, 0x20, 0x24, 0x28, 0x2C

_BIG = 1 << 30

# ---------------------------------------------------------------------------------------------
# The model.  Names are the coverage-database paths: ``i2c.<group>.<coverpoint>``.
# ---------------------------------------------------------------------------------------------
_DIRS, _ACKS = ["write", "read"], ["ack", "nack"]

# bus: what the master did on the wire (from the BFM's event stream)
_start_kind = fc.point("i2c.bus.start_kind", ["start", "rstart_after_write", "rstart_after_read"])
_addr_result = fc.pair(
    "i2c.bus.addr_result",
    ("i2c.bus.addr_dir", _DIRS, None),
    ("i2c.bus.addr_ack", _ACKS, None),
)
_wr_data_ack = fc.point("i2c.bus.wr_data_ack", _ACKS)
_rd_master_ack = fc.point("i2c.bus.rd_master_ack", _ACKS)
_wr_bytes = fc.ranges(
    "i2c.bus.wr_bytes",
    [
        ("n0", 0, 0),
        ("n1", 1, 1),
        ("n2", 2, 2),
        ("n3_4", 3, 4),
        ("n5_8", 5, 8),
        ("n9_16", 9, 16),
        ("n17_up", 17, _BIG),
    ],
)
_rd_bytes = fc.ranges(
    "i2c.bus.rd_bytes",
    [
        ("n1", 1, 1),
        ("n2", 2, 2),
        ("n3_4", 3, 4),
        ("n5_8", 5, 8),
        ("n9_16", 9, 16),
        ("n17_up", 17, _BIG),
    ],
)
_segments = fc.ranges(
    "i2c.bus.segments_per_txn", [("one", 1, 1), ("two", 2, 2), ("three_up", 3, _BIG)]
)
_stop_after = fc.point("i2c.bus.stop_after", ["write", "read", "addr_nack"])
_stretch_at = fc.point(
    "i2c.bus.stretch_at", ["addr_bit", "addr_ack", "wr_bit", "wr_ack", "rd_bit", "rd_ack"]
)
_stretch_mode = fc.point("i2c.bus.stretch_mode", ["single_fall", "every_fall"])

# cmd: the I2C_CMD words software issued
_CMD_SHAPES = [
    f"{'S' if s else '-'}{op}{'P' if p else '-'}"
    for s in (1, 0)
    for op in ("--", "W-", "-R", "WR")
    for p in (0, 1)
]
_cmd_shape = fc.point("i2c.cmd.shape", _CMD_SHAPES)
_cmd_count = fc.ranges(
    "i2c.cmd.count",
    [("zero", 0, 0), ("one", 1, 1), ("two_8", 2, 8), ("nine_254", 9, 254), ("max_255", 255, 255)],
)
_cmd_read_last = fc.point("i2c.cmd.read_last", ["acked", "nacked"])
_cmd_loopback = fc.point("i2c.cmd.loopback_op", ["write", "read"])

# cfg: configuration values programmed
_clkdiv = fc.ranges(
    "i2c.cfg.clkdiv",
    [
        ("clamped_0_2", 0, 2),
        ("min_3", 3, 3),
        ("fast_4_61", 4, 61),
        ("fm_400k_62", 62, 62),
        ("mid_63_248", 63, 248),
        ("sm_100k_249", 249, 249),
        ("slow_250_fffe", 250, 0xFFFE),
        ("max_ffff", 0xFFFF, 0xFFFF),
    ],
)
_rx_thr = fc.ranges(
    "i2c.cfg.rx_thr", [("t0", 0, 0), ("t1", 1, 1), ("t2_8", 2, 8), ("t9_15", 9, 15)]
)
_ctrl_mode = fc.point("i2c.cfg.ctrl_mode", ["enable", "loopback", "disable"])
_timeout_cfg = fc.ranges(
    "i2c.cfg.timeout",
    [
        ("off_0", 0, 0),
        ("short_1_1023", 1, 1023),
        ("long_1024_fffe", 1024, 0xFFFE),
        ("reset_ffff", 0xFFFF, 0xFFFF),
    ],
)
_IRQ_NAMES = ["done", "nack", "arb_lost", "timeout", "rx_threshold"]
_irq_en = fc.point("i2c.cfg.irq_en", _IRQ_NAMES)

# irq / status / fifo: what software observed
_irq_cause = fc.point("i2c.irq.cause_seen", _IRQ_NAMES)
_irq_w1c = fc.point("i2c.irq.w1c", _IRQ_NAMES[:4])
_irq_gating = fc.point("i2c.irq.gating", ["asserted", "masked"])
_status_seen = fc.point("i2c.status.seen", ["busy", "txn_active", "nack", "arb_lost", "timeout"])
_fifo_tx = fc.point("i2c.fifo.tx_state", ["empty", "partial", "full"])
_fifo_rx = fc.point("i2c.fifo.rx_state", ["empty", "partial", "full"])

# err: error and recovery paths
_nack_where = fc.point("i2c.err.nack_where", ["address", "write_data"])
_nack_state = fc.point("i2c.err.nack_state", ["bus_held", "stop_sent"])
_arb_loss = fc.point(
    "i2c.err.arb_loss", ["address_bit", "data_bit", "read_nack_slot", "rstart_setup"]
)
_timeout_cause = fc.point(
    "i2c.err.timeout_cause", ["scl_stretched", "bus_busy_wait", "tx_starve", "rx_full"]
)
_cmd_ignored = fc.point("i2c.err.cmd_ignored", ["disabled", "illegal_shape", "no_strobe", "busy"])
_abort = fc.point("i2c.err.abort", ["en_cleared", "reset"])

# soc: the controller reached through the real fabric (test_soc_i2c.py only)
_soc_path = fc.point(
    "i2c.soc.path",
    [
        "reset_values",
        "loopback_write",
        "loopback_read",
        "irq_to_cpu",
        "real_pad_write",
        "real_pad_read",
        "real_pad_addr_nack",
    ],
)


_STRETCH_PHASE = {"ADDR": "addr", "WR": "wr", "RD": "rd"}


def _fifo_state(empty: int, full: int) -> str:
    return "empty" if empty else ("full" if full else "partial")


class I2CCoverage:
    """Observer/sampler for one I2C test environment.  ``attach`` it per test (a test builds a
    fresh APB master and bus BFM); the coverage database itself is process-wide."""

    def __init__(self) -> None:
        self.irq_en = 0
        self.ctrl = 0
        self._slave = None
        self._last_read: dict = {}
        self._reset_bus()

    def _reset_bus(self) -> None:
        self._seg = None  # open segment: {"dir", "acked", "wr", "rd"}
        self._nsegs = 0
        self._last_dir = None
        self._abandoned = 0

    # ------------------------------------------------------------------ wiring
    def attach(self, apb=None, slave=None) -> None:
        """Start observing a fresh APB master and/or bus BFM; forget the previous test's state."""
        self.irq_en = 0
        self.ctrl = 0
        self._last_read = {}
        self._reset_bus()
        if apb is not None:
            apb.add_observer(self.on_apb)
        if slave is not None:
            self._slave = slave
            slave.add_observer(self.on_bus)

    # ------------------------------------------------------------- APB register face
    def on_apb(self, is_write: bool, addr: int, data: int, strb: int, ok: bool) -> None:
        """APB observer: sample one completed register transfer."""
        if not ok:
            return
        if is_write:
            self._on_write(addr, data, strb)
        else:
            self.reg_read(addr, data)

    def _on_write(self, addr: int, data: int, strb: int) -> None:
        lane0, lane1 = bool(strb & 1), bool(strb & 2)
        if addr == CTRL:
            if lane0:
                self.ctrl = (self.ctrl & ~0xFF) | (data & 0xFF)
                en, loop = data & 1, (data >> 1) & 1
                _ctrl_mode("disable" if not en else ("loopback" if loop else "enable"))
            if lane1:
                self.ctrl = (self.ctrl & ~0xFF00) | (data & 0xFF00)
                _rx_thr((data >> 8) & 0xF)
        elif addr == CLKDIV and strb & 3 == 3:
            _clkdiv(data & 0xFFFF)
        elif addr == TIMEOUT and strb & 3 == 3:
            _timeout_cfg(data & 0xFFFF)
        elif addr == IRQ_EN and lane0:
            self.irq_en = data & 0x1F
            for bit, name in enumerate(_IRQ_NAMES):
                if self.irq_en >> bit & 1:
                    _irq_en(name)
        elif addr == IRQ_CLR and lane0:
            for bit, name in enumerate(_IRQ_NAMES[:4]):
                if data >> bit & 1:
                    _irq_w1c(name)
        elif addr == CMD and lane0:
            self._on_cmd(data, lane1)

    def _on_cmd(self, data: int, has_count: bool) -> None:
        start, wr, rd, stop, nack_last = (data >> b & 1 for b in range(5))
        op = ("W" if wr else "-") + ("R" if rd else "-")
        _cmd_shape(f"{'S' if start else '-'}{op}{'P' if stop else '-'}")
        if has_count:
            _cmd_count((data >> 8) & 0xFF)
        if rd and not wr:
            _cmd_read_last("nacked" if nack_last else "acked")
        if self.ctrl & 3 == 3 and (wr or rd):  # EN and LOOPBACK
            _cmd_loopback("write" if wr else "read")

    def reg_read(self, addr: int, value: int) -> None:
        """Sample a register value software (or a `_peek`) observed.  A repeat of the previous
        (value, IRQ_EN) for the same register is dropped: it cannot reach a new bin."""
        key = (value, self.irq_en if addr == IRQ_STAT else 0)
        if self._last_read.get(addr) == key:
            return
        self._last_read[addr] = key
        if addr == STATUS:
            self._on_status(value)
        elif addr == IRQ_STAT:
            for bit, name in enumerate(_IRQ_NAMES):
                if value >> bit & 1:
                    _irq_cause(name)
                    _irq_gating("asserted" if self.irq_en >> bit & 1 else "masked")
        elif addr == FIFO_STAT:
            _fifo_tx(_fifo_state(value >> 9 & 1, value >> 8 & 1))
            _fifo_rx(_fifo_state(value >> 11 & 1, value >> 10 & 1))

    @staticmethod
    def _on_status(value: int) -> None:
        for bit, name in enumerate(["busy", "txn_active", "nack", "arb_lost", "timeout"]):
            if value >> bit & 1:
                _status_seen(name)
        busy, txn, nack = value & 1, value >> 1 & 1, value >> 2 & 1
        if nack and txn:
            _nack_state("bus_held")  # NACK without STOP: the master keeps the bus
        elif nack and not busy:
            _nack_state("stop_sent")  # NACK, STOP went out, engine idle

    # ------------------------------------------------------------------- the bus
    def on_bus(self, event: tuple) -> None:
        """BFM observer: assemble START/ADDR/data/STOP events into segments and transactions."""
        kind = event[0]
        if kind == "STRETCH":
            self._on_stretch(event[1], event[2], event[3])
        elif kind in ("START", "RSTART"):
            self._close_segment()
            aborted = self._slave is not None and len(self._slave.abandoned) > self._abandoned
            if self._slave is not None:
                self._abandoned = len(self._slave.abandoned)
            if kind == "START":
                self._nsegs = 0
                _start_kind("start")
            elif not aborted and self._last_dir is not None:
                _start_kind("rstart_after_" + self._last_dir)
            self._nsegs += 1
            self._seg = {"dir": None, "acked": False, "wr": 0, "rd": 0}
        elif kind == "ADDR" and self._seg is not None:
            _, _addr, rw, acked = event
            direction = "read" if rw else "write"
            self._seg["dir"], self._seg["acked"] = direction, acked
            _addr_result(direction, "ack" if acked else "nack")
            if not acked:
                _nack_where("address")
        elif kind == "WR" and self._seg is not None:
            self._seg["wr"] += 1
            _wr_data_ack("ack" if event[2] else "nack")
            if not event[2]:
                _nack_where("write_data")
        elif kind == "RD" and self._seg is not None:
            self._seg["rd"] += 1
            _rd_master_ack("ack" if event[2] else "nack")
        elif kind == "STOP":
            seg = self._seg
            self._close_segment()
            if seg is not None and seg["dir"] is not None:
                _stop_after(seg["dir"] if seg["acked"] else "addr_nack")
            if self._nsegs:
                _segments(self._nsegs)
            self._nsegs = 0
            self._last_dir = None

    def _close_segment(self) -> None:
        seg = self._seg
        self._seg = None
        if seg is None or not seg["acked"]:
            self._last_dir = None
            return
        self._last_dir = seg["dir"]
        if seg["dir"] == "write":
            _wr_bytes(seg["wr"])
        elif seg["rd"]:
            _rd_bytes(seg["rd"])

    @staticmethod
    def _on_stretch(mode: str, fall_idx: int, every: bool) -> None:
        if mode not in ("ADDR", "WR", "RD"):
            return
        slot = "ack" if fall_idx % 9 == 8 else "bit"
        _stretch_at(f"{_STRETCH_PHASE[mode]}_{slot}")
        _stretch_mode("every_fall" if every else "single_fall")

    # ------------------------------------------- assertion-backed scenario samples
    @staticmethod
    def arb_loss(phase: str) -> None:
        """Arbitration was lost in `phase` (address_bit | data_bit | read_nack_slot |
        rstart_setup).  Call after the test asserted arb_lost (and not done)."""
        _arb_loss(phase)

    @staticmethod
    def timeout(cause: str) -> None:
        """A bounded wait expired (scl_stretched | bus_busy_wait | tx_starve | rx_full).  Call
        after the test asserted the sticky timeout bit."""
        _timeout_cause(cause)

    @staticmethod
    def cmd_ignored(reason: str) -> None:
        """A CMD write was silently ignored (disabled | illegal_shape | no_strobe | busy).  Call
        after the test proved the bus stayed quiet / the command did not run."""
        _cmd_ignored(reason)

    @staticmethod
    def abort(kind: str) -> None:
        """An in-flight transfer was aborted (en_cleared | reset), after the post-abort checks."""
        _abort(kind)

    @staticmethod
    def soc(path: str) -> None:
        """A SoC-fabric fact proven by test_soc_i2c.py (see i2c.soc.path in the model doc)."""
        _soc_path(path)


COV = I2CCoverage()
# One YAML per simulator process, named after the cocotb MODULE it ran (test_i2c / test_soc_i2c).
fc.enable_export(os.environ.get("MODULE", "i2c"))
