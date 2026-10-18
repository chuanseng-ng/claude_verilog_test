"""
APB4 Master BFM (Bus Functional Model)

Provides an APB4 master interface for testbenches.
Implements the SETUP → ACCESS two-phase protocol (ARM IHI0024C).
Supports APB4 pstrb byte-enable strobes.

Protocol:
  SETUP  phase: psel=1, penable=0 — one clock cycle.
  ACCESS phase: psel=1, penable=1 — held until pready=1 (slave inserts waits).

Signals driven (master outputs):
  psel, penable, pwrite, paddr, pwdata, pstrb
Signals sampled (slave outputs):
  prdata, pready, pslverr
"""

from cocotb.triggers import RisingEdge


class APB4Master:
    """
    APB4 Master Bus Functional Model.

    Implements the APB4 two-phase (SETUP/ACCESS) protocol with pstrb support.
    Suitable for driving apb4_register_bank or any APB4 slave.

    Signal prefix convention: pass the prefix used on the DUT top-level port
    (e.g. "" for bare psel/penable/..., or "apb_" for apb_psel/apb_penable/...).
    The clock signal is passed separately and is not prefixed.
    """

    def __init__(self, dut, prefix: str, clock, reset=None):
        """
        Initialise the APB4 master BFM.

        Args:
            dut:    Device under test (cocotb handle).
            prefix: Signal name prefix (e.g. "" or "apb_").
            clock:  Clock signal handle.
            reset:  Optional reset signal handle (active-low).
        """
        self.dut    = dut
        self.clock  = clock
        self.reset  = reset
        # Passive listeners (bead h367 functional coverage), see add_observer().
        self._observers: list = []

        # Master-driven outputs
        self.psel    = getattr(dut, f"{prefix}psel")
        self.penable = getattr(dut, f"{prefix}penable")
        self.pwrite  = getattr(dut, f"{prefix}pwrite")
        self.paddr   = getattr(dut, f"{prefix}paddr")
        self.pwdata  = getattr(dut, f"{prefix}pwdata")
        self.pstrb   = getattr(dut, f"{prefix}pstrb")

        # Slave-driven inputs to master
        self.prdata  = getattr(dut, f"{prefix}prdata")
        self.pready  = getattr(dut, f"{prefix}pready")
        self.pslverr = getattr(dut, f"{prefix}pslverr")

        self._init_signals()

    def _init_signals(self) -> None:
        """Drive master outputs to idle (bus idle: psel=0)."""
        self.psel.value    = 0
        self.penable.value = 0
        self.pwrite.value  = 0
        self.paddr.value   = 0
        self.pwdata.value  = 0
        self.pstrb.value   = 0xF  # all bytes valid; overridden per transaction

    def add_observer(self, callback) -> None:
        """Register a passive listener, called after every COMPLETED transfer as
        `callback(is_write, addr, data, strb, ok)`: `data` is the written word for a write and the
        sampled prdata for a read, `ok` is False on pslverr.  It must not touch the bus.  Nothing
        is registered by default, so an unobserved BFM behaves exactly as before."""
        self._observers.append(callback)

    def _notify(self, is_write: bool, addr: int, data: int, strb: int, ok: bool) -> None:
        for callback in self._observers:
            callback(is_write, addr, data, strb, ok)

    async def write(self, addr: int, data: int, strb: int = 0xF) -> bool:
        """
        Perform an APB4 write transaction.

        SETUP phase  (1 cycle): psel=1, penable=0.
        ACCESS phase (>=1 cycle): psel=1, penable=1, wait until pready=1.

        Args:
            addr: Byte address (word-aligned for register-bank targets).
            data: 32-bit write data.
            strb: 4-bit byte-enable strobes (default 0xF = all bytes).

        Returns:
            True if pslverr=0 (OKAY), False if pslverr=1 (SLVERR).
        """
        # SETUP phase
        self.psel.value    = 1
        self.penable.value = 0
        self.pwrite.value  = 1
        self.paddr.value   = addr
        self.pwdata.value  = data
        self.pstrb.value   = strb
        await RisingEdge(self.clock)

        # ACCESS phase — hold until pready
        self.penable.value = 1
        await RisingEdge(self.clock)
        while not self.pready.value:
            await RisingEdge(self.clock)

        err = bool(self.pslverr.value)

        # Return bus to idle
        self.psel.value    = 0
        self.penable.value = 0
        self.pwrite.value  = 0
        self.pstrb.value   = 0xF  # restore default

        self._notify(True, addr, data, strb, not err)
        return not err

    async def read(self, addr: int) -> tuple[int, bool]:
        """
        Perform an APB4 read transaction.

        SETUP phase  (1 cycle): psel=1, penable=0, pwrite=0.
        ACCESS phase (>=1 cycle): psel=1, penable=1, wait until pready=1.
        prdata is sampled when pready=1 in ACCESS.

        Args:
            addr: Byte address.

        Returns:
            Tuple of (data: int, ok: bool).
            data — 32-bit read data sampled at pready.
            ok   — True if pslverr=0 (OKAY), False if pslverr=1 (SLVERR).
        """
        # SETUP phase
        self.psel.value    = 1
        self.penable.value = 0
        self.pwrite.value  = 0
        self.paddr.value   = addr
        self.pstrb.value   = 0x0  # strobes unused for reads; drive 0
        await RisingEdge(self.clock)

        # ACCESS phase — hold until pready
        self.penable.value = 1
        await RisingEdge(self.clock)
        while not self.pready.value:
            await RisingEdge(self.clock)

        data = int(self.prdata.value)
        err  = bool(self.pslverr.value)

        # Return bus to idle
        self.psel.value    = 0
        self.penable.value = 0

        self._notify(False, addr, data, 0x0, not err)
        return (data, not err)
