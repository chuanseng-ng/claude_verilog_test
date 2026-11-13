"""
I2C slave and bus BFM for testbenches that drive the open-drain master rtl/periph/i2c_controller.sv.
Companion to apb4_master.py: that BFM speaks the register bus, this one speaks the pins.

Samples <prefix>scl_oe_o, scl_o, sda_oe_o, sda_o and drives <prefix>scl_i, sda_i (prefix "i2c_" in
tb_i2c and tb_soc_top). One register-file slave answers at `address` (7-bit).

The wired-AND lives here, not in the RTL. oe = 1 pulls the line low, oe = 0 releases it, and `*_o`
is a dead pin that must read 0. Every tick the BFM builds the bus from the DUT oe, slave_drive and
forced_low, and drives it back on the `_i` pins. Clock stretching, arbitration loss and a stuck bus
are slave_drive / forced_low values. No RTL hook is used.

RULE: read and drive the bus on the FALLING edge. The DUT samples `_i` and registers oe on
the rising edge. A BFM that reads and writes in one rising-edge callback races the DUT and fakes
RTL faults.
Do not change this to RisingEdge.

Slave: ACK only on an address match with `ack_address`. The first write byte is the
register pointer.
A read returns `read_queue` first, then mem[ptr++]. `events` logs START, RSTART, ADDR, WR, RD, STOP.
Hooks: stretch_at_fall, stretch_every_fall, hold_scl_low, contend_at_fall, hold_sda_low.
Checks are collected, not raised: protocol_errors, abandoned (see assert_clean).
Doc: tm:suite:bfm-i2c-slave
"""

import cocotb
from cocotb.triggers import FallingEdge


class I2CSlave:
    """Open-drain I2C bus model + one register-file slave (see module docstring)."""

    def __init__(
        self,
        dut,
        prefix: str,
        clock,
        address: int = 0x50,
        mem_size: int = 256,
    ):
        """
        Initialise the I2C bus/slave BFM and release both bus lines.

        Args:
            dut:      Device under test (cocotb handle).
            prefix:   Signal name prefix (e.g. "i2c_" -> i2c_scl_oe_o / i2c_scl_i ...).
            clock:    Clock signal handle the DUT samples on (the BFM acts on its FALLING edge).
            address:  7-bit slave address.
            mem_size: Size of the register file (pointer wraps modulo this).
        """
        self.dut = dut
        self.clock = clock

        # DUT master outputs (read) ...
        self._scl_oe = getattr(dut, f"{prefix}scl_oe_o")
        self._scl_o = getattr(dut, f"{prefix}scl_o")
        self._sda_oe = getattr(dut, f"{prefix}sda_oe_o")
        self._sda_o = getattr(dut, f"{prefix}sda_o")
        # ... and DUT master inputs (driven)
        self._scl_i = getattr(dut, f"{prefix}scl_i")
        self._sda_i = getattr(dut, f"{prefix}sda_i")

        # Configuration (public; tests set these freely)
        self.address = address & 0x7F
        self.ack_address = True
        self.data_acks: list = []
        self.read_queue: list = []
        self.mem = bytearray(mem_size)
        self.ptr = 0
        self.register_mode = True
        # Passive listeners (functional coverage): each is called as cb(event) with the
        # same tuple that is appended to `events`.  Configuration, so reset_state() keeps them.
        self._observers: list = []

        self._task = None
        self._init_runtime()
        self._drive_released()

    # ------------------------------------------------------------------ state
    def _init_runtime(self) -> None:
        """(Re)initialise every runtime field; configuration is untouched."""
        # slave-driven levels, 1 = released
        self._sda_drv = 1
        self._scl_drv = 1
        # manual / hook overrides
        self._hold_scl = False
        self._hold_sda = False
        self._stretch_plan: dict = {}
        self._stretch_all = 0
        self._contend_plan: dict = {}
        self._stretch_left = 0
        self._contend_left = 0
        self._contend_on = False
        # protocol FSM
        self._mode = "IDLE"  # IDLE | ADDR | WR | RD | IGN
        self._in_txn = False
        self._bits = 0  # SCL rising edges seen in the current byte (0..9)
        self._shift = 0
        self._fall_idx = -1
        self._rw = 0
        self._ptr_pending = False
        self._rd_byte = 0
        self._rd_master_ack = True
        self._addr_matched = False
        # edge-detection history
        self._prev_scl = 1
        self._prev_sda = 1
        self._prev_m = (0, 0)  # (scl_oe, sda_oe) last tick
        self._suppress_edge = False
        self._rise_pending = False  # an SCL rise not yet followed by its fall
        # observations
        self.cycle = 0
        self.scl_bus = 1
        self.sda_bus = 1
        self.events: list = []
        self.event_cycles: list = []  # BFM tick each event was observed on (parallel to events)
        self.received: list = []
        self.protocol_errors: list = []
        self.abandoned: list = []
        self.scl_rise_cycles: list = []
        self.scl_fall_cycles: list = []

    def reset_log(self) -> None:
        """Forget recorded events/timing/errors (keep configuration, memory and bus state)."""
        self.events = []
        self.event_cycles = []
        self.received = []
        self.protocol_errors = []
        self.abandoned = []
        self.scl_rise_cycles = []
        self.scl_fall_cycles = []

    def reset_state(self) -> None:
        """Return the slave to power-up: releases every hook and forgets the transaction.
        Use after resetting the DUT mid-transaction. Memory contents are kept."""
        self._init_runtime()
        self._drive_released()

    def add_observer(self, callback) -> None:
        """Register a passive listener called as `callback(event)` for every logged bus event
        (the tuples documented above) and for the extra ("STRETCH", ...) notification (see
        `_notify`).  It must not touch the bus or the BFM's state."""
        self._observers.append(callback)

    def _log(self, event: tuple) -> None:
        """Record an observed bus event and the BFM tick it was observed on."""
        self.events.append(event)
        self.event_cycles.append(self.cycle)
        self._notify(event)

    def _notify(self, event: tuple) -> None:
        """Pass `event` to the observers.  Besides everything `_log` records, observers receive
        ("STRETCH", mode, fall_idx, every_fall) when the slave starts holding SCL low; that one is
        NOT in `events` (so no test's event-list assertion can see it)."""
        for callback in self._observers:
            callback(event)

    def _drive_released(self) -> None:
        self._scl_i.value = 1
        self._sda_i.value = 1

    # ------------------------------------------------------------------ hooks
    def stretch_at_fall(self, index: int, cycles: int) -> None:
        """Hold SCL low for `cycles` clk right after SCL fall number `index` (one shot)."""
        self._stretch_plan[index] = cycles

    def stretch_every_fall(self, cycles: int) -> None:
        """Hold SCL low for `cycles` clk after EVERY SCL fall (0 disables)."""
        self._stretch_all = cycles

    def hold_scl_low(self, flag: bool = True) -> None:
        """Hold SCL low until called with False (a stuck / dead slave)."""
        self._hold_scl = flag

    def contend_at_fall(self, index: int, cycles: int = 200) -> None:
        """Drive SDA low right after SCL fall `index` (one shot): a second master transmitting a 0
        while this master releases SDA to send a 1.  `cycles` is the hold in clk; pass
        cycles=-1 to hold exactly until the NEXT SCL fall (one bit time -- what a real second
        master transmitting a single 0 bit does, and what the negative controls need so the
        contention cannot spill into the following bit)."""
        self._contend_plan[index] = cycles

    def hold_sda_low(self, flag: bool = True) -> None:
        """Hold SDA low until called with False (bus busy / stuck SDA)."""
        self._hold_sda = flag
        self._suppress_edge = True

    # ------------------------------------------------------------- properties
    @property
    def stretching(self) -> bool:
        """True while the slave is holding SCL low (hook or manual)."""
        return self._hold_scl or self._stretch_left > 0

    def starts(self) -> int:
        """Number of START + repeated-START conditions seen."""
        return sum(1 for e in self.events if e[0] in ("START", "RSTART"))

    def assert_clean(self) -> None:
        """Raise AssertionError if the master broke clock stretching, used a dead `*_o` pin, or
        abandoned a byte. Call at the end of every test whose master is expected to behave."""
        assert not self.protocol_errors, f"I2C protocol errors: {self.protocol_errors}"
        assert not self.abandoned, f"START/STOP arrived mid-byte: {self.abandoned}"

    # ---------------------------------------------------------------- running
    def start(self):
        """Start the bus coroutine and return its task (append it to the caller's active-task
        list so it is killed between tests)."""
        self._drive_released()
        self._task = cocotb.start_soon(self._run())
        return self._task

    async def _run(self) -> None:
        while True:
            await FallingEdge(self.clock)
            self._tick()

    # --------------------------------------------------------------- bus math
    def _master_levels(self) -> tuple:
        """(scl, sda) as the DUT master alone drives them: (oe ? o : 1)."""
        scl_oe, sda_oe = int(self._scl_oe.value), int(self._sda_oe.value)
        scl_m = int(self._scl_o.value) if scl_oe else 1
        sda_m = int(self._sda_o.value) if sda_oe else 1
        return scl_m, sda_m, scl_oe, sda_oe

    def _bus(self, scl_m: int, sda_m: int) -> tuple:
        scl = scl_m & self._scl_drv & (0 if self._hold_scl else 1)
        sda = sda_m & self._sda_drv & (0 if (self._hold_sda or self._contend_on) else 1)
        return scl, sda

    # ------------------------------------------------------------------- tick
    def _tick(self) -> None:
        self.cycle += 1
        scl_m, sda_m, scl_oe, sda_oe = self._master_levels()

        # Pad-ring contract: *_o is hard-tied 0.
        if int(self._scl_o.value) or int(self._sda_o.value):
            self.protocol_errors.append(f"cycle {self.cycle}: dead *_o pin read 1")

        # Clock-stretch compliance: while we hold SCL low and the master had released it, the
        # master must neither move SDA nor pull SCL low again.
        if self.stretching and self._prev_m[0] == 0:
            if scl_oe == 1:
                self.protocol_errors.append(
                    f"cycle {self.cycle}: master pulled SCL low while stretched (advanced "
                    f"without waiting for SCL high)"
                )
            elif sda_oe != self._prev_m[1]:
                self.protocol_errors.append(
                    f"cycle {self.cycle}: master changed SDA while SCL was stretched"
                )
        self._prev_m = (scl_oe, sda_oe)

        self._count_hooks()
        scl, sda = self._bus(scl_m, sda_m)
        self._fsm_step(scl, sda)
        scl2, sda2 = self._bus(scl_m, sda_m)

        # Bus timing records (edge of the FINAL level this tick leaves on the wire).
        if scl2 and not self._prev_scl:
            self.scl_rise_cycles.append(self.cycle)
        if not scl2 and self._prev_scl:
            self.scl_fall_cycles.append(self.cycle)

        self._scl_i.value = scl2
        self._sda_i.value = sda2
        self.scl_bus, self.sda_bus = scl2, sda2
        self._prev_scl, self._prev_sda = scl2, sda2

    def _count_hooks(self) -> None:
        """Advance the stretch / contention timers by one tick."""
        if self._stretch_left > 0:
            self._stretch_left -= 1
            if self._stretch_left == 0:
                self._scl_drv = 1
        if self._contend_left > 0:
            self._contend_left -= 1
            if self._contend_left == 0:
                self._contend_on = False
                self._suppress_edge = True

    # -------------------------------------------------------------- slave FSM
    def _fsm_step(self, scl: int, sda: int) -> None:
        start = bool(scl and self._prev_scl and self._prev_sda and not sda)
        stop = bool(scl and self._prev_scl and not self._prev_sda and sda)
        if self._suppress_edge:
            start = stop = False  # an SDA edge this BFM caused itself is not a bus event
            self._suppress_edge = False
        rise = bool(scl and not self._prev_scl)
        fall = bool(not scl and self._prev_scl)

        if start:
            self._on_start()
        elif stop:
            self._on_stop()
        else:
            if rise and self._mode != "IDLE":
                self._on_rise(sda)
            if fall and self._mode != "IDLE":
                self._on_fall()
            if fall:
                self._on_fall_hooks()

    def _bits_at_condition(self) -> int:
        """Data bits genuinely clocked when a START/STOP arrives. The SCL rise that precedes a
        START/STOP is the master's setup clock for the condition, not a data bit."""
        return max(0, self._bits - 1) if self._rise_pending else self._bits

    def _on_start(self) -> None:
        if self._mode != "IDLE" and self._bits_at_condition() != 0:
            self.abandoned.append(("START", self._bits_at_condition()))
        self._log(("RSTART",) if self._in_txn else ("START",))
        self._in_txn = True
        self._mode = "ADDR"
        self._bits = 0
        self._shift = 0
        self._fall_idx = -1
        self._sda_drv = 1
        self._ptr_pending = False
        self._addr_matched = False

    def _on_stop(self) -> None:
        if self._in_txn:
            if self._mode != "IDLE" and self._bits_at_condition() != 0:
                self.abandoned.append(("STOP", self._bits_at_condition()))
            self._log(("STOP",))
        self._in_txn = False
        self._mode = "IDLE"
        self._bits = 0
        self._sda_drv = 1

    def _on_rise(self, sda: int) -> None:
        self._rise_pending = True
        if self._mode in ("ADDR", "WR"):
            if self._bits < 8:
                self._shift = ((self._shift << 1) | sda) & 0xFF
            self._bits += 1
        elif self._mode == "RD":
            if self._bits == 8:
                self._rd_master_ack = sda == 0
                self._log(("RD", self._rd_byte, self._rd_master_ack))
            self._bits += 1

    def _on_fall(self) -> None:
        self._rise_pending = False
        if self._mode in ("ADDR", "WR"):
            if self._bits == 8:
                self._finish_rx_byte()
            elif self._bits == 9:
                self._bits = 0
                self._shift = 0
                self._sda_drv = 1  # release the ACK
                if self._mode == "ADDR":
                    self._enter_data_phase()
        elif self._mode == "RD":
            if 1 <= self._bits <= 7:
                self._sda_drv = (self._rd_byte >> (7 - self._bits)) & 1
            elif self._bits == 8:
                self._sda_drv = 1  # release for the master's ACK slot
            elif self._bits == 9:
                self._bits = 0
                if self._rd_master_ack:
                    self._rd_byte = self._next_read_byte()
                    self._sda_drv = (self._rd_byte >> 7) & 1
                else:
                    self._mode = "IGN"
                    self._sda_drv = 1

    def _finish_rx_byte(self) -> None:
        """Called on the SCL fall after the 8th data bit: decide ACK/NACK for the byte."""
        if self._mode == "ADDR":
            addr, rw = self._shift >> 1, self._shift & 1
            self._rw = rw
            self._addr_matched = (addr == self.address) and self.ack_address
            self._log(("ADDR", addr, rw, self._addr_matched))
            if self._addr_matched:
                self._sda_drv = 0
            else:
                self._mode = "IGN"
                self._bits = 0
            return
        byte = self._shift
        ack = self.data_acks.pop(0) if self.data_acks else True
        self._log(("WR", byte, ack))
        if ack:
            self._sda_drv = 0
            self.received.append(byte)
            self._store_write(byte)

    def _store_write(self, byte: int) -> None:
        if self.register_mode and self._ptr_pending:
            self.ptr = byte % len(self.mem)
            self._ptr_pending = False
        else:
            self.mem[self.ptr % len(self.mem)] = byte
            self.ptr = (self.ptr + 1) % len(self.mem)

    def _enter_data_phase(self) -> None:
        """Address ACK slot has ended: go to write or read data phase."""
        if self._rw:
            self._mode = "RD"
            self._rd_byte = self._next_read_byte()
            self._sda_drv = (self._rd_byte >> 7) & 1
            self._rd_master_ack = True
        else:
            self._mode = "WR"
            self._ptr_pending = self.register_mode

    def _next_read_byte(self) -> int:
        if self.read_queue:
            return self.read_queue.pop(0) & 0xFF
        byte = self.mem[self.ptr % len(self.mem)]
        self.ptr = (self.ptr + 1) % len(self.mem)
        return byte

    def _on_fall_hooks(self) -> None:
        """Count the SCL fall and arm any stretch / contention planned for it."""
        self._fall_idx += 1
        idx = self._fall_idx
        planned = self._stretch_plan.pop(idx, 0)
        cycles = planned or self._stretch_all
        if cycles:
            self._scl_drv = 0
            self._stretch_left = cycles
            self._notify(("STRETCH", self._mode, idx, not planned))
        if self._contend_left < 0:  # "until the next fall": this is it
            self._contend_left = 0
            self._contend_on = False
            self._suppress_edge = True
        cycles = self._contend_plan.pop(idx, 0)
        if cycles:
            self._contend_on = True
            self._contend_left = cycles
            self._suppress_edge = True

    # ------------------------------------------------------------ rate helpers
    @property
    def scl_low_cycles(self) -> list:
        """Clk cycles each SCL-low interval lasted (fall -> next rise)."""
        out = []
        for f in self.scl_fall_cycles:
            nxt = [r for r in self.scl_rise_cycles if r > f]
            if nxt:
                out.append(nxt[0] - f)
        return out

    @property
    def scl_high_cycles(self) -> list:
        """Clk cycles each SCL-high interval lasted (rise -> next fall)."""
        out = []
        for r in self.scl_rise_cycles:
            nxt = [f for f in self.scl_fall_cycles if f > r]
            if nxt:
                out.append(nxt[0] - r)
        return out

    @property
    def scl_periods(self) -> list:
        """Clk cycles between consecutive SCL rising edges."""
        return [b - a for a, b in zip(self.scl_rise_cycles, self.scl_rise_cycles[1:])]
