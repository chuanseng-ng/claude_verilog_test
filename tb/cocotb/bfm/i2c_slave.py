"""
I2C Slave / Bus BFM (Bus Functional Model)

Models the PHYSICAL I2C BUS and one register-file slave sitting on it, for testbenches that drive
an open-drain I2C *master* (rtl/periph/i2c_controller.sv).  Companion to apb4_master.py: that BFM
speaks the register bus, this one speaks the pins.

Signals sampled (DUT master outputs, open-drain triplets, `<prefix>` is "i2c_" in tb_i2c /
tb_soc_top):
  <prefix>scl_oe_o, <prefix>scl_o, <prefix>sda_oe_o, <prefix>sda_o
Signals driven (DUT master inputs, the sensed pad levels):
  <prefix>scl_i, <prefix>sda_i

The wired-AND lives HERE, not in the RTL
----------------------------------------
The DUT's pad-ring contract is: oe = 1 drives the line LOW, oe = 0 releases it, an external pull-up
makes a released line high, and `*_o` is a dead hard-tied-0 pin that exists only for pad symmetry
with GPIO.  The bus is therefore reconstructed in the testbench, every clock:

    sda_bus = (dut.i2c_sda_oe_o ? dut.i2c_sda_o : 1) & slave_drive & ~forced_low
    scl_bus = (dut.i2c_scl_oe_o ? dut.i2c_scl_o : 1) & slave_drive & ~forced_low

and driven back into dut.i2c_sda_i / dut.i2c_scl_i.  Because the BFM is the only thing that closes
the loop, clock stretching (the slave holds SCL low), arbitration loss (another master holds SDA
low while this master releases it) and a stuck bus are all just "slave_drive" / "forced_low"
values -- no RTL hook is needed or used.  The BFM also asserts, every tick, that the DUT's dead
`*_o` pins read 0 (`protocol_errors`), so a regression that starts using `*_o` as data is caught.

!!! TRAP (already hit once, do not rediscover): DRIVE THE BUS ON THE NEGEDGE !!!
-------------------------------------------------------------------------------
The DUT samples `i2c_scl_i` / `i2c_sda_i` (through its 2-FF synchronisers) and registers its own
oe outputs on the clock's RISING edge.  A BFM that reads the oe pins and writes the `_i` pins in
the SAME rising-edge callback races the DUT: cocotb/Verilator then hands the DUT either the old or
the new bus level depending on scheduling order, and the failure looks exactly like an RTL fault
-- during the RTL bring-up it produced two spurious read-back failures that were not RTL faults.
This BFM therefore does ALL of its reading and driving on the FALLING edge of the clock, half a
period away from every DUT sampling edge.  Every `_i` value the DUT sees is stable for a whole
clock before it is sampled, and every oe value this BFM reads has fully settled after the
preceding rising edge.  Do not "optimise" this to RisingEdge.  The consequence is that the slave
reacts with zero delay at the sampling tick, which is indistinguishable (to a master whose tick is
>= 4 clk) from a real slave that responds inside the SCL-low interval.

Slave behaviour
---------------
One slave at `address` (7-bit), register-file style (like an EEPROM / sensor):
  * address phase: ACK iff the 7-bit address matches and `ack_address` is set, else NACK and the
    slave ignores the transaction until the next START/STOP;
  * write: the FIRST data byte after an address-write is the register pointer (not stored); every
    later byte is stored at mem[ptr++].  `data_acks` is a per-byte ACK(True)/NACK(False) script
    consumed in order for write DATA bytes (exhausted = ACK).  A NACKed byte is not stored;
  * read: returns `read_queue` bytes first (if any), otherwise mem[ptr++]; stops driving after the
    master NACKs.
Everything the slave observes is appended to `events`:
    ("START",)  ("RSTART",)  ("ADDR", addr7, rw, acked)  ("WR", byte, acked)
    ("RD", byte, master_acked)  ("STOP",)
A START with no preceding STOP is logged as RSTART (repeated START), which is how a test tells a
genuine repeated START from a STOP followed by a START.

Hooks (all take effect on the next negedge; all are optional)
-------------------------------------------------------------
  stretch_at_fall(index, cycles)  hold SCL low for `cycles` clk right after SCL FALL number `index`
  stretch_every_fall(cycles)      same, after every SCL fall
  hold_scl_low(flag)              hold SCL low until released (stuck / dead slave)
  contend_at_fall(index, cycles)  drive SDA low for `cycles` clk right after SCL fall `index` --
                                  a second master driving a 0 while this master sends a 1
  hold_sda_low(flag)              hold SDA low until released (bus busy / stuck SDA)
SCL fall numbering: the count restarts at every START/repeated START; the master's pull-down right
after the START condition is fall 0, and the next SCL-high pulse is bit `index`.  So for byte
number n (0 = the address byte) bit i (0 = MSB) the preceding fall is 9*n + i, and byte n's ACK slot
is 9*n + 8.

Built-in checks (collected, not raised, so a test decides)
----------------------------------------------------------
  protocol_errors  the master advanced (moved SDA, or pulled SCL low again) while the slave was
                   stretching SCL and the master had released it -- i.e. it did not honour clock
                   stretching; or a dead `*_o` pin read 1;
  abandoned        a START/STOP that arrived mid-byte (bit count in parentheses) -- a master that
                   lost arbitration or timed out walks away mid-byte, so this is informational
                   there and a hard error everywhere else (assert_clean() checks both).
Timing records for rate checks: scl_rise_cycles / scl_fall_cycles (BFM clock-tick timestamps of
every SCL edge on the bus), plus `scl_low_cycles` / `scl_high_cycles` / `scl_periods`.
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

    def _log(self, event: tuple) -> None:
        """Record an observed bus event and the BFM tick it was observed on."""
        self.events.append(event)
        self.event_cycles.append(self.cycle)

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
        cycles = self._stretch_plan.pop(idx, 0) or self._stretch_all
        if cycles:
            self._scl_drv = 0
            self._stretch_left = cycles
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
