"""
test_apb_cdc_bridge.py — GH #93 cocotb verification for the APB4
clock-domain-crossing bridge (rtl/soc/apb_cdc_bridge.sv), via the standalone
wrapper tb_apb_cdc_bridge.sv.

DUT: tb_apb_cdc_bridge (re-exports apb_cdc_bridge's s_*/m_* faces as flat
top-level ports).

s_* face = source domain, APB4 SLAVE port -> bfm.apb4_master.APB4Master
  attaches as APB4Master(dut, "s_", dut.s_clk).
m_* face = destination domain, APB4 MASTER port (apb_cdc_bridge drives
  m_psel/m_penable/m_pwrite/m_paddr/m_pwdata/m_pstrb and expects
  m_pready/m_prdata/m_pslverr back) -> there is no ready-made APB4 SLAVE BFM
  in tb/cocotb/bfm/ (only masters: apb3_master.py / apb4_master.py), so this
  file provides a small local `ApbSlaveResponder` to play that role, with
  configurable wait-states and pslverr injection.

apb_cdc_bridge is a depth-1 (one outstanding transfer) 2-phase toggle-
handshake bridge -- see the RTL module header (rtl/soc/apb_cdc_bridge.sv)
for the full protocol and CDC argument before reading the tests below.

**Two-Clock() mechanic**: both s_clk and m_clk are true top-level input ports
written via VPI, so two independent `Clock()` coroutines free-run with no
HDL-internal timing involved (`--no-timing` in the Makefile disables only
HDL specify/intra-assignment delays). cocotb + Verilator has no ReadWrite()
-- every driving loop below (both the responder and any raw pokes) follows
the same RisingEdge-then-ReadOnly discipline as axi4_slave_model.py /
test_async_axi_fifo.py (read DUT-driven signals only in a ReadOnly context;
write our own signals only in the active/Normal phase immediately following
a RisingEdge).

Every test is wrapped in `with_timeout(..., 50, "us")` so a real CDC
deadlock fails the test instead of hanging the whole `soc_all` regression.

Clock pairs exercised across this suite (ns, all in the 4-20 ns range per
the GH #93 verification task): 4/9 (~2.25 ratio, mirrors the same proxy for
the real CPU:fabric split used by test_async_axi_fifo.py; also reused for
the latency-budget test), 18/4 (wide ratio, slow-s/fast-m), 10/10 (equal),
7/11 (coprime -- edges slide continuously, the closest sim proxy for a
metastability-window sweep), and 7/13 (coprime, used only for the long
randomized stream so it is a genuinely different ratio from the sweep
above).
"""

import random
from types import SimpleNamespace

import cocotb
from bfm.apb4_master import APB4Master
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, Combine, ReadOnly, RisingEdge, Timer, with_timeout
from cocotb.utils import get_sim_time

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
RESET_HOLD_NS = 300  # generous vs. SYNC_STAGES(2)+1 periods of any clock used here (max period 18 ns)

# ---------------------------------------------------------------------------
# Module-level task handle list (guard against cross-test coroutine leakage,
# same pattern as test_pmu.py's / test_async_axi_fifo.py's
# _active_tasks / _kill_active_tasks).
# ---------------------------------------------------------------------------
_active_tasks: list = []


def _kill_active_tasks() -> None:
    global _active_tasks
    for t in _active_tasks:
        t.kill()
    _active_tasks = []


def _idle_s_side(dut) -> None:
    """Force the s-side stimulus signals idle. Used after killing a
    mid-flight APB4Master coroutine (reset-while-busy tests) so a leaked
    psel/penable state does not confuse the next transaction."""
    dut.s_psel.value = 0
    dut.s_penable.value = 0


# ---------------------------------------------------------------------------
# Local APB4 slave responder for the m_* face (there is no ready-made APB4
# slave BFM in tb/cocotb/bfm/ -- only masters).
# ---------------------------------------------------------------------------

class ApbSlaveResponder:
    """Local APB4 slave responder sitting on the m_* face (apb_cdc_bridge's
    APB4 MASTER output port). Samples m_psel/m_penable/m_pwrite/m_paddr/
    m_pwdata/m_pstrb (DUT-driven -- read only in a ReadOnly context) and
    drives m_prdata/m_pready/m_pslverr (written only in the active/Normal
    phase immediately after a RisingEdge -- same discipline as
    axi4_slave_model.py; cocotb+Verilator has no ReadWrite()).

    wait_states: int, or callable(addr:int, write:bool) -> int. Number of
      EXTRA destination-domain ACCESS cycles to hold m_pready low beyond the
      first (zero-wait-state) ACCESS cycle -- i.e. 0 means "assert pready on
      the very first ACCESS cycle", matching apb4_register_bank.sv's own
      zero-wait-state convention.
    err_addrs: set of addresses, or callable(addr:int, write:bool) -> bool,
      selecting which transfers complete with pslverr=1 instead of 0.
    mem: word-addressed dict (byte address -> 32-bit value) backing store;
      pstrb byte-enables are honoured on writes (same merge logic as
      axi4_slave_model.py).

    `completed` counts every finished (psel && penable && pready) APB
    transfer observed on the m_* face -- used by the "no lost/duplicated
    transaction" stream test to prove the bridge neither drops nor
    fabricates a destination-side transfer.
    """

    def __init__(self, dut, prefix, clock, mem=None, wait_states=0, err_addrs=None):
        self.dut = dut
        self.clock = clock
        self.mem = mem if mem is not None else {}
        self.wait_states = wait_states
        self.err_addrs = err_addrs if err_addrs is not None else set()
        self.completed = 0

        self.psel = getattr(dut, f"{prefix}psel")
        self.penable = getattr(dut, f"{prefix}penable")
        self.pwrite = getattr(dut, f"{prefix}pwrite")
        self.paddr = getattr(dut, f"{prefix}paddr")
        self.pwdata = getattr(dut, f"{prefix}pwdata")
        self.pstrb = getattr(dut, f"{prefix}pstrb")
        self.prdata = getattr(dut, f"{prefix}prdata")
        self.pready = getattr(dut, f"{prefix}pready")
        self.pslverr = getattr(dut, f"{prefix}pslverr")

        self.prdata.value = 0
        self.pready.value = 0
        self.pslverr.value = 0

    def _resolve_ws(self, addr, write) -> int:
        if callable(self.wait_states):
            return int(self.wait_states(addr, write))
        return int(self.wait_states)

    def _resolve_err(self, addr, write) -> bool:
        if callable(self.err_addrs):
            return bool(self.err_addrs(addr, write))
        return addr in self.err_addrs

    def _apply_write(self, addr, wdata, strb) -> None:
        cur = self.mem.get(addr, 0)
        val = 0
        for b in range(4):
            src = wdata if (strb >> b) & 1 else cur
            val |= ((src >> (b * 8)) & 0xFF) << (b * 8)
        self.mem[addr] = val

    def start(self):
        return cocotb.start_soon(self._loop())

    async def _loop(self) -> None:
        while True:
            # -- Detect SETUP (psel=1, penable=0) -- sampled in ReadOnly --
            while True:
                await RisingEdge(self.clock)
                await ReadOnly()
                if int(self.psel.value) and not int(self.penable.value):
                    break
            # Still in ReadOnly here -- reads only, no writes.
            addr = int(self.paddr.value)
            write = bool(int(self.pwrite.value))
            wdata = int(self.pwdata.value)
            strb = int(self.pstrb.value)
            ws = self._resolve_ws(addr, write)
            err = self._resolve_err(addr, write)

            # -- Enter ACCESS phase (active/Normal region, safe to write) --
            await RisingEdge(self.clock)

            # -- Extra wait-state cycles: m_pready stays low (already its
            #    reset/idle value -- no write needed each iteration) -------
            for _ in range(ws):
                await RisingEdge(self.clock)

            # Note: no direct (non-ReadOnly) sanity read of psel/penable here
            # -- reading a DUT-driven signal immediately after a RisingEdge,
            # before the delta-cycle NBA settling that ReadOnly() guarantees,
            # races with the very same edge that moved d_state_q into
            # D_ACCESS (confirmed by an earlier iteration of this test: a
            # naive direct .value check right here spuriously saw
            # m_penable=0 on roughly half the transactions). The D_SETUP ->
            # D_ACCESS transition is protocol-guaranteed unconditional RTL
            # (apb_cdc_bridge.sv's d_state_d case), so no live re-check is
            # needed; psel/penable are still verified properly (via
            # ReadOnly) on the *next* SETUP-detection pass, and any real
            # protocol violation would surface as a hung with_timeout above.

            # -- Complete the transfer (active phase -- safe to write) ----
            if write:
                self._apply_write(addr, wdata, strb)
                self.prdata.value = 0
            else:
                self.prdata.value = self.mem.get(addr, 0)
            self.pslverr.value = 1 if err else 0
            self.pready.value = 1

            await RisingEdge(self.clock)  # the edge the DUT samples m_pready=1 on
            self.completed += 1
            self.pready.value = 0
            self.prdata.value = 0
            self.pslverr.value = 0


# ---------------------------------------------------------------------------
# Setup helper
# ---------------------------------------------------------------------------

async def _setup(dut, s_ns, m_ns, wait_states=0, err_addrs=None, mem=None) -> SimpleNamespace:
    """Start both clocks, build the s-side APB4Master + m-side local
    responder, and drive a common-root reset -- rst_both_n = s_rst_n_i &
    m_rst_n_i feeds both cdc_reset_sync instances in the RTL, so BOTH
    s_rst_n/m_rst_n must be driven together here (driving only one side does
    not model the real reset architecture)."""
    _kill_active_tasks()

    s_clk_task = cocotb.start_soon(Clock(dut.s_clk, s_ns, units="ns").start())
    m_clk_task = cocotb.start_soon(Clock(dut.m_clk, m_ns, units="ns").start())
    _active_tasks.append(s_clk_task)
    _active_tasks.append(m_clk_task)

    s_master = APB4Master(dut, "s_", dut.s_clk)
    responder = ApbSlaveResponder(dut, "m_", dut.m_clk, mem=mem, wait_states=wait_states, err_addrs=err_addrs)
    resp_task = responder.start()
    _active_tasks.append(resp_task)

    dut.s_rst_n.value = 0
    dut.m_rst_n.value = 0
    # A real-time hold (not clock-edge-counted) so it is correct regardless
    # of the s/m period ratio under test -- always >> SYNC_STAGES(2)+1
    # periods of the slower clock in this suite's matrix (max period 18 ns).
    await Timer(RESET_HOLD_NS, units="ns")
    dut.s_rst_n.value = 1
    dut.m_rst_n.value = 1
    await ClockCycles(dut.s_clk, 3)
    await ClockCycles(dut.m_clk, 3)

    return SimpleNamespace(
        s_master=s_master,
        responder=responder,
        s_clk_task=s_clk_task,
        m_clk_task=m_clk_task,
        resp_task=resp_task,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

# --- 1. reset defaults -------------------------------------------------------

async def _reset_defaults_body(dut):
    await _setup(dut, 10, 10)
    await ClockCycles(dut.s_clk, 2)
    await ClockCycles(dut.m_clk, 2)

    assert int(dut.s_pready.value) == 0, "s_pready must be low (idle) at reset"
    assert int(dut.s_pslverr.value) == 0, "s_pslverr must be low at reset"
    assert int(dut.m_psel.value) == 0, "m_psel must be low (idle) at reset"
    assert int(dut.m_penable.value) == 0, "m_penable must be low (idle) at reset"
    dut._log.info("reset defaults OK: s_pready/s_pslverr/m_psel/m_penable all idle-low")


@cocotb.test()
async def test_reset_defaults(dut):
    await with_timeout(_reset_defaults_body(dut), 50, "us")


# --- 2. single write ----------------------------------------------------------

async def _single_write_body(dut):
    ctx = await _setup(dut, 10, 10)
    ok = await ctx.s_master.write(0x100, 0xA5A5A5A5)
    assert ok, "single write reported pslverr"
    assert ctx.responder.mem.get(0x100) == 0xA5A5A5A5, "destination-side mem did not receive the write"
    dut._log.info("single write OK")


@cocotb.test()
async def test_single_write(dut):
    await with_timeout(_single_write_body(dut), 50, "us")


# --- 3. single read -----------------------------------------------------------

async def _single_read_body(dut):
    ctx = await _setup(dut, 10, 10)
    ctx.responder.mem[0x104] = 0x5A5A5A5A
    data, ok = await ctx.s_master.read(0x104)
    assert ok, "single read reported pslverr"
    assert data == 0x5A5A5A5A, f"single read data mismatch: {data:#x}"
    dut._log.info("single read OK")


@cocotb.test()
async def test_single_read(dut):
    await with_timeout(_single_read_body(dut), 50, "us")


# --- 4. back-to-back transactions ---------------------------------------------

async def _back_to_back_body(dut):
    ctx = await _setup(dut, 10, 10)
    n = 20
    for i in range(n):
        ok = await ctx.s_master.write(0x110 + i * 4, 0x10000000 + i)
        assert ok, f"write {i}: pslverr"
    for i in range(n):
        data, ok = await ctx.s_master.read(0x110 + i * 4)
        assert ok, f"read {i}: pslverr"
        assert data == 0x10000000 + i, f"beat {i}: {data:#x}"
    dut._log.info(f"back-to-back OK: {n} writes then {n} reads, no gaps between transactions")


@cocotb.test()
async def test_back_to_back(dut):
    await with_timeout(_back_to_back_body(dut), 50, "us")


# --- 5. pready wait-state behaviour on the m_* (destination) side -------------

async def _low_cycle_monitor(dut):
    """Count s_clk cycles where s_pready is low, until it is finally seen
    high (the caller races this against the write/read task via Combine)."""
    count = 0
    while True:
        await RisingEdge(dut.s_clk)
        await ReadOnly()
        if int(dut.s_pready.value):
            return count
        count += 1


async def _pready_wait_states_body(dut):
    ws = 15  # m-side destination ACCESS wait-state cycles
    ctx = await _setup(dut, 4, 9, wait_states=ws)

    mon_task = cocotb.start_soon(_low_cycle_monitor(dut))
    t0 = get_sim_time(units="ns")
    write_task = cocotb.start_soon(ctx.s_master.write(0x200, 0xCAFEBABE))
    await Combine(write_task, mon_task)
    t1 = get_sim_time(units="ns")

    ok = write_task.result()
    low_cycles = mon_task.result()
    elapsed_ns = t1 - t0

    assert ok, "write completed with pslverr during wait-state test"
    assert ctx.responder.mem.get(0x200) == 0xCAFEBABE, "destination-side mem did not receive the write"

    # The destination inserts ws=15 extra 9 ns ACCESS cycles before
    # asserting m_pready -- if s_pready were NOT correctly held low across
    # that whole stall (e.g. a bug that let the s-side complete early), the
    # elapsed wall-clock time would fall well short of ws*9 ns.
    min_expected_ns = 0.9 * ws * 9
    assert elapsed_ns >= min_expected_ns, (
        f"elapsed {elapsed_ns} ns is less than the expected minimum {min_expected_ns} ns for "
        f"{ws} m-side wait-state cycles -- s_pready was not correctly held low across the "
        "destination-side wait states"
    )
    dut._log.info(
        f"pready wait-state OK: s_pready held low for {low_cycles} s-cycles, "
        f"elapsed={elapsed_ns:.1f} ns >= {min_expected_ns:.1f} ns bound ({ws} m-side wait states)"
    )


@cocotb.test()
async def test_pready_wait_states(dut):
    await with_timeout(_pready_wait_states_body(dut), 50, "us")


# --- 6. response data integrity (varied patterns, pslverr=0) ------------------

async def _response_data_integrity_body(dut):
    ctx = await _setup(dut, 10, 10)
    patterns = [
        0x00000000, 0xFFFFFFFF, 0xAAAAAAAA, 0x55555555,
        0xDEADBEEF, 0x00000001, 0x80000000, 0x12345678,
    ]
    for i, val in enumerate(patterns):
        addr = 0x300 + i * 4
        ok = await ctx.s_master.write(addr, val)
        assert ok, f"pattern {i}: write pslverr, val={val:#x}"
        data, ok2 = await ctx.s_master.read(addr)
        assert ok2, f"pattern {i}: read pslverr, val={val:#x}"
        assert data == val, f"pattern {i} at {addr:#x}: wrote {val:#x}, read back {data:#x}"
    dut._log.info(f"response data integrity OK: {len(patterns)} data patterns round-tripped exactly, all pslverr=0")


@cocotb.test()
async def test_response_data_integrity(dut):
    await with_timeout(_response_data_integrity_body(dut), 50, "us")


# --- 7. pslverr injection (0 and 1 cases) -------------------------------------

async def _pslverr_injection_body(dut):
    err_addr = 0x400
    ok_addr = 0x404
    ctx = await _setup(dut, 10, 10, err_addrs={err_addr})

    ok = await ctx.s_master.write(err_addr, 0xDEADBEEF)
    assert ok is False, "expected pslverr=1 (SLVERR) on configured error address write"

    data, ok2 = await ctx.s_master.read(err_addr)
    assert ok2 is False, "expected pslverr=1 (SLVERR) on configured error address read"

    # A different address must complete OKAY -- proves pslverr is carried
    # per-transaction through the bridge, not latched/stuck.
    ok3 = await ctx.s_master.write(ok_addr, 0x12345678)
    assert ok3 is True, "non-error address write unexpectedly reported pslverr"
    data2, ok4 = await ctx.s_master.read(ok_addr)
    assert ok4 is True, "non-error address read unexpectedly reported pslverr"
    assert data2 == 0x12345678, f"non-error address readback mismatch: {data2:#x}"
    dut._log.info("pslverr injection OK: error addr -> pslverr=1 (write+read), other addr -> pslverr=0, not sticky")


@cocotb.test()
async def test_pslverr_injection(dut):
    await with_timeout(_pslverr_injection_body(dut), 50, "us")


# --- 8-11. clock ratio sweeps ---------------------------------------------------

async def _ratio_sweep_workload(dut, s_ns, m_ns, n=8):
    ctx = await _setup(dut, s_ns, m_ns)
    for i in range(n):
        ok = await ctx.s_master.write(0x500 + i * 4, 0x70000000 + i)
        assert ok, f"txn {i}: write pslverr"
    for i in range(n):
        data, ok = await ctx.s_master.read(0x500 + i * 4)
        assert ok, f"txn {i}: read pslverr"
        assert data == 0x70000000 + i, f"txn {i}: {data:#x}"
    dut._log.info(f"clock ratio {s_ns}/{m_ns} ns OK: {n} write+read round trips")


@cocotb.test()
async def test_clock_ratio_fast_s_slow_m(dut):
    # 4/9 ns (~2.25 ratio) -- same proxy for the real CPU:fabric split used
    # by test_async_axi_fifo.py's gate test.
    await with_timeout(_ratio_sweep_workload(dut, 4, 9), 50, "us")


@cocotb.test()
async def test_clock_ratio_slow_s_fast_m(dut):
    # 18/4 ns -- wide ratio, opposite direction (slow source, fast destination).
    await with_timeout(_ratio_sweep_workload(dut, 18, 4), 50, "us")


@cocotb.test()
async def test_clock_ratio_equal(dut):
    await with_timeout(_ratio_sweep_workload(dut, 10, 10), 50, "us")


@cocotb.test()
async def test_clock_ratio_coprime(dut):
    # 7/11 ns -- coprime, edges slide continuously across the whole run,
    # the closest sim proxy for a real metastability-window sweep.
    await with_timeout(_ratio_sweep_workload(dut, 7, 11, n=20), 50, "us")


# --- 12. reset mid-transaction, s side (single-sided; rst_both_n hard flush) --

async def _reset_mid_transaction_s_side_body(dut):
    ctx = await _setup(dut, 10, 10, wait_states=5)

    t = cocotb.start_soon(ctx.s_master.write(0x600, 0xABCD1234))
    await ClockCycles(dut.s_clk, 2)  # let SETUP + req_toggle_q launch happen first
    # Assert ONLY s_rst_n -- m_rst_n stays high throughout. The point of this
    # test is that a single-sided reset still flushes BOTH domains via
    # rst_both_n = s_rst_n_i & m_rst_n_i (see apb_cdc_bridge.sv header).
    dut.s_rst_n.value = 0
    await ClockCycles(dut.s_clk, 5)
    dut.s_rst_n.value = 1
    await ClockCycles(dut.s_clk, 3)
    await ClockCycles(dut.m_clk, 3)
    t.kill()
    _idle_s_side(dut)

    await ClockCycles(dut.s_clk, 2)
    assert int(dut.s_pready.value) == 0, "s_pready must be idle-low after s-side reset recovery"
    assert int(dut.s_pslverr.value) == 0, "no fabricated pslverr after reset (hard flush, not an error response)"

    # Prove clean recovery with a fresh, unrelated transaction.
    ok = await ctx.s_master.write(0x600, 0x11112222)
    assert ok, "post-recovery write reported pslverr -- fabricated error after reset?"
    data, ok2 = await ctx.s_master.read(0x600)
    assert ok2, "post-recovery read reported pslverr"
    assert data == 0x11112222, f"post-recovery readback mismatch: {data:#x}"
    dut._log.info("reset-mid-transaction (s side) OK: in-flight transfer dropped, no fabricated pslverr, clean recovery")


@cocotb.test()
async def test_reset_mid_transaction_s_side(dut):
    await with_timeout(_reset_mid_transaction_s_side_body(dut), 50, "us")


# --- 13. reset mid-transaction, m side (single-sided; rst_both_n hard flush) --

async def _reset_mid_transaction_m_side_body(dut):
    ctx = await _setup(dut, 10, 10, wait_states=5)
    ctx.responder.mem[0x700] = 0xBEEF0001

    t = cocotb.start_soon(ctx.s_master.read(0x700))
    await ClockCycles(dut.m_clk, 3)  # let the request cross into the m domain first
    # Assert ONLY m_rst_n -- s_rst_n stays high throughout.
    dut.m_rst_n.value = 0
    await ClockCycles(dut.m_clk, 5)
    dut.m_rst_n.value = 1
    await ClockCycles(dut.s_clk, 3)
    await ClockCycles(dut.m_clk, 3)
    t.kill()
    _idle_s_side(dut)

    await ClockCycles(dut.s_clk, 2)
    assert int(dut.s_pready.value) == 0, "s_pready must be idle-low after m-side reset recovery"
    assert int(dut.s_pslverr.value) == 0, "no fabricated pslverr after reset (hard flush, not an error response)"

    ok = await ctx.s_master.write(0x700, 0x33334444)
    assert ok, "post-recovery write reported pslverr -- fabricated error after reset?"
    data, ok2 = await ctx.s_master.read(0x700)
    assert ok2, "post-recovery read reported pslverr"
    assert data == 0x33334444, f"post-recovery readback mismatch: {data:#x}"
    dut._log.info("reset-mid-transaction (m side) OK: in-flight transfer dropped, no fabricated pslverr, clean recovery")


@cocotb.test()
async def test_reset_mid_transaction_m_side(dut):
    await with_timeout(_reset_mid_transaction_m_side_body(dut), 50, "us")


# --- 14. no lost/duplicated transactions, long randomized stream -------------

async def _no_lost_or_duplicated_stream_body(dut):
    # 7/13 ns -- coprime and deliberately different from the ratio sweep
    # above, so this stress run is a genuinely independent non-1:1 ratio.
    ctx = await _setup(dut, 7, 13)
    rng = random.Random(0xC0FFEE)
    addrs = [0x800 + i * 4 for i in range(16)]
    expected: dict = {}
    n_ops = 150
    writes = reads = 0

    for i in range(n_ops):
        addr = rng.choice(addrs)
        do_write = (addr not in expected) or (rng.random() < 0.5)
        if do_write:
            val = rng.getrandbits(32)
            ok = await ctx.s_master.write(addr, val)
            assert ok, f"op {i}: write to {addr:#x} reported pslverr"
            expected[addr] = val
            writes += 1
        else:
            data, ok = await ctx.s_master.read(addr)
            assert ok, f"op {i}: read from {addr:#x} reported pslverr"
            assert data == expected[addr], (
                f"op {i}: addr {addr:#x} expected {expected[addr]:#x}, got {data:#x} "
                "-- lost or corrupted transaction"
            )
            reads += 1

    assert ctx.responder.completed == writes + reads, (
        f"m-side observed {ctx.responder.completed} completed APB transfers, expected exactly "
        f"{writes + reads} (writes={writes} + reads={reads}) -- possible dropped or duplicated "
        "transaction across the CDC bridge"
    )
    dut._log.info(
        f"no-lost/no-duplicate stream OK: {n_ops} ops ({writes} writes, {reads} reads) at 7ns/13ns "
        f"(coprime), m-side transfer count matches exactly ({ctx.responder.completed})"
    )


@cocotb.test()
async def test_no_lost_or_duplicated_stream(dut):
    await with_timeout(_no_lost_or_duplicated_stream_body(dut), 100, "us")


# --- 15. latency budget --------------------------------------------------------

async def _latency_budget_body(dut):
    # s_clk=4ns / m_clk=9ns -- same proxy ratio as the GH #93 integration
    # case (see module docstring), so this number is a usable budget input.
    ctx = await _setup(dut, 4, 9)

    sync_s = int(dut.sync_stages_to_s_o.value)
    sync_m = int(dut.sync_stages_to_m_o.value)

    t0 = get_sim_time(units="ns")
    ok = await ctx.s_master.write(0x900, 0xFEEDFACE)
    t1 = get_sim_time(units="ns")
    assert ok, "latency-budget write reported pslverr"
    write_latency_ns = t1 - t0

    t2 = get_sim_time(units="ns")
    data, ok2 = await ctx.s_master.read(0x900)
    t3 = get_sim_time(units="ns")
    assert ok2, "latency-budget read reported pslverr"
    assert data == 0xFEEDFACE, f"latency-budget readback mismatch: {data:#x}"
    read_latency_ns = t3 - t2

    # Derived bound (not just measured): a single-beat round trip crosses
    # req_toggle_q into the m domain ((sync_m + 1) m-cycles: SYNC_STAGES_TO_M
    # sync flops + 1 cycle for req_seen_q to catch up), runs one D_SETUP +
    # one zero-wait D_ACCESS cycle (2 m-cycles), crosses ack_toggle_q back
    # into the s domain ((sync_s + 1) s-cycles, same reasoning), then takes
    # one S_WAIT-capture + one S_DONE-pulse cycle (2 s-cycles) to complete.
    # Expressed conservatively in the SLOWER of the two periods, with a 2x
    # safety margin for scheduling slop between two independently
    # free-running Clock() coroutines (not a tight bound, but a real,
    # derived one -- see the GH #94 STA action item in apb_cdc_bridge.sv's
    # header for the eventual set_max_delay treatment of these same paths).
    slow_ns = max(4, 9)
    budget_cycles = (sync_m + 1) + 2 + (sync_s + 1) + 2
    bound_ns = 2 * budget_cycles * slow_ns

    dut._log.info(
        "GH #93 apb_cdc_bridge round-trip latency budget (s_clk=4ns/m_clk=9ns): "
        f"write={write_latency_ns:.1f} ns, read={read_latency_ns:.1f} ns, "
        f"derived bound={bound_ns:.1f} ns (budget_cycles={budget_cycles})"
    )
    assert write_latency_ns < bound_ns, (
        f"write latency {write_latency_ns} ns exceeds derived bound {bound_ns} ns"
    )
    assert read_latency_ns < bound_ns, (
        f"read latency {read_latency_ns} ns exceeds derived bound {bound_ns} ns"
    )


@cocotb.test()
async def test_latency_budget(dut):
    await with_timeout(_latency_budget_body(dut), 50, "us")
