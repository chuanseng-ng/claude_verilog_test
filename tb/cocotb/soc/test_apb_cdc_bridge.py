"""
test_apb_cdc_bridge.py -- cocotb verification for the APB4 clock-domain-crossing bridge
(rtl/soc/apb_cdc_bridge.sv), via the standalone wrapper tb_apb_cdc_bridge.sv.
DUT: tb_apb_cdc_bridge. The s_* face (source domain, APB4 SLAVE) is driven by
bfm.apb4_master.APB4Master(dut, "s_", dut.s_clk); the m_* face (destination domain, APB4 MASTER) is
answered by a local `ApbSlaveResponder` (configurable wait states and pslverr injection).
apb_cdc_bridge is a depth-1 (one outstanding transfer) 4-phase RZ (return-to-zero) handshake bridge.
Read the RTL module header for the protocol and the CDC argument before the tests. Backdoor names
use the RZ naming: req_q / ack_q (request and ack LEVELS) and their synchronised copies req_m
/ ack_s.
Two-Clock() mechanic: s_clk and m_clk are top-level input ports written via VPI, so two independent
`Clock()` coroutines free-run with no HDL-internal timing (`--no-timing` disables only HDL specify
and intra-assignment delays). cocotb + Verilator has no ReadWrite(). Every driving loop follows the
RisingEdge-then-ReadOnly rule of axi4_slave_model.py and test_async_axi_fifo.py: read DUT-driven
signals only in ReadOnly, write our own signals only in the active phase right after a RisingEdge.
Every test runs under `with_timeout(..., 50, "us")`, so a CDC deadlock fails the test,
not `soc_all`.
Clock pairs (s_clk/m_clk periods in ns, all from 4 to 20): 4/9 (ratio about 2.25, the proxy for the
CPU:fabric split of test_async_axi_fifo.py, also the latency-budget test), 18/4 (wide, slow-s
fast-m), 10/10 (equal), 7/11 (coprime: edges slide continuously, the closest sim proxy for a
metastability-window sweep), 7/13 (coprime, only the long randomized stream, so it differs from
the sweep).
Run: make -C tb/cocotb/soc apb_cdc_bridge
Doc: tm:suite:soc-test-apb-cdc-bridge
"""

import random
from types import SimpleNamespace

import cocotb
from bfm.apb4_master import APB4Master
from cocotb.clock import Clock
from cocotb.triggers import (
    ClockCycles,
    Combine,
    FallingEdge,
    ReadOnly,
    RisingEdge,
    Timer,
    with_timeout,
)
from cocotb.utils import get_sim_time

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
# generous vs. SYNC_STAGES(2)+1 periods of any clock used here (max period 18, in ns)
RESET_HOLD_NS = 300


def _post_reset_recovery_cycles(dut) -> int:
    """Cycles to wait, on the relevant destination clock(s), after a reset
    domain releases before code may assume this crossing's reset-status
    synchronisers have resolved and issue a transaction expected to
    succeed.

    Both directions here are cdc_sync instances (SYNC_STAGES_TO_S /
    SYNC_STAGES_TO_M, read back from the RTL via sync_stages_to_{s,m}_o
    rather than hardcoded a second time -- see tb_apb_cdc_bridge.sv
    header) whose NOMINAL settling latency is STAGES cycles. Under the
    RAND_CDC_DELAY_EN settling-delay injector (default OFF, compiled only in simulation), either
    synchroniser can legitimately take one extra cycle. A recovery wait
    pinned to the bare nominal STAGES is exactly-tight against the
    synchroniser's own worst case, not generously tight against it --
    that is precisely what was found: a literal
    `ClockCycles(dut.m_clk, 3)` (== STAGES+1) in
    test_availability_never_forwarded failed deterministically once the
    injector's one-extra-cycle fault model was active, because the
    post-recovery write landed one cycle before the synchroniser had
    actually resolved. Returns STAGES+1 (worst-case settling) + 1 cycle of
    slack for the receiving FSM to act on the newly-resolved value.
    """
    stages = max(int(dut.sync_stages_to_s_o.value), int(dut.sync_stages_to_m_o.value))
    return stages + 2


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
        self.aborted = 0

        self.psel = getattr(dut, f"{prefix}psel")
        self.penable = getattr(dut, f"{prefix}penable")
        self.pwrite = getattr(dut, f"{prefix}pwrite")
        self.paddr = getattr(dut, f"{prefix}paddr")
        self.pwdata = getattr(dut, f"{prefix}pwdata")
        self.pstrb = getattr(dut, f"{prefix}pstrb")
        self.prdata = getattr(dut, f"{prefix}prdata")
        self.pready = getattr(dut, f"{prefix}pready")
        self.pslverr = getattr(dut, f"{prefix}pslverr")
        self.rst_n = getattr(dut, f"{prefix}rst_n")

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

            # -- Enter ACCESS phase, then hold for ws extra cycles, checking
            #    after EVERY edge (via ReadOnly, safe against NBA-settling
            #    races -- see the note below) whether this transfer has been
            #    abandoned: either m_psel dropped (the availability
            #    fix force-completed the SOURCE side with a bounded error
            #    before this destination ever answered -- see
            #    apb_cdc_bridge.sv's req_fwd_q / S_REQ-abort logic) or this
            #    destination domain's own reset asserted mid-transfer
            #    (m_rst_n=0). Either way, blindly asserting m_pready later
            #    for a request nobody is listening for anymore would let
            #    THIS RESPONDER fabricate a "completed" destination-side
            #    write the real bridge never asked for -- exactly what the
            #    "no destination-side write lands after an aborted request"
            #    property (see test_availability_* below) needs to be false
            #    to hold. This responder used to
            #    have no such check at all.
            #
            #    Deliberately does NOT read anything in the plain active
            #    region right after a bare RisingEdge (only ever after
            #    ReadOnly()) -- reading a DUT-driven signal before the
            #    delta-cycle NBA settling that ReadOnly() guarantees races
            #    with whatever edge just moved that signal (confirmed by an
            #    earlier iteration of this test: a naive direct .value check
            #    immediately after the D_SETUP->D_ACCESS edge specifically
            #    spuriously saw m_penable=0 on roughly half the
            #    transactions). This costs one extra ACCESS cycle versus the
            #    original zero-wait-state timing (a fixed, constant +1 for
            #    every ws value, since the abort-check for the FINAL ACCESS
            #    cycle is what gates entering the writable region needed to
            #    drive pready) -- harmless for every existing lower/upper
            #    -bound-style timing assertion in this suite (they all have
            #    margin, none check for an exact cycle count).
            await RisingEdge(self.clock)
            aborted = False
            for _ in range(ws + 1):
                await ReadOnly()
                if not int(self.psel.value) or not int(self.rst_n.value):
                    aborted = True
                    break
                await RisingEdge(self.clock)

            if aborted:
                self.aborted += 1
                continue

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
    # periods of the slower clock in this suite's matrix (max period 18, in ns).
    await Timer(RESET_HOLD_NS, units="ns")
    dut.s_rst_n.value = 1
    dut.m_rst_n.value = 1
    # Post-reset recovery margin -- every
    # test builds on this baseline wait before issuing its first
    # transaction, so it must cover the synchronisers' worst case, not
    # just their nominal latency.
    n = _post_reset_recovery_cycles(dut)
    await ClockCycles(dut.s_clk, n)
    await ClockCycles(dut.m_clk, n)
    # Step off the clock edge: at a coprime ratio the m_clk edge this returns on can coincide with an s_clk
    # edge, and the master's first writes would then race that edge's flop sampling in Xcelium (the bridge
    # saw the ACCESS phase without ever seeing SETUP). Verilator is indifferent to the
    # one-step offset.
    await Timer(1, units="step")

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



# apb_cdc_bridge.sv s_state_e / d_state_e encodings (rtl/soc/apb_cdc_bridge.sv
# :487-492, :608-613). Named here so a structural check can never silently
# assert against the wrong ordinal -- an earlier draft of
# test_rz_four_phase_structural_proof looked for S_DONE's 3 while its message
# said S_DROP, so it failed on correct RTL.
S_IDLE, S_REQ, S_DROP, S_DONE = 0, 1, 2, 3
D_IDLE, D_SETUP, D_ACCESS, D_ACK = 0, 1, 2, 3

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

    # The destination inserts ws=15 extra ACCESS cycles (m_clk period 9) before
    # asserting m_pready -- if s_pready were NOT correctly held low across
    # that whole stall (e.g. a bug that let the s-side complete early), the
    # elapsed wall-clock time would fall well short of ws times the m_clk period.
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
    # 4/9 (~2.25 ratio) -- same proxy for the real CPU:fabric split used
    # by test_async_axi_fifo.py's gate test.
    await with_timeout(_ratio_sweep_workload(dut, 4, 9), 50, "us")


@cocotb.test()
async def test_clock_ratio_slow_s_fast_m(dut):
    # 18/4 -- wide ratio, opposite direction (slow source, fast destination).
    await with_timeout(_ratio_sweep_workload(dut, 18, 4), 50, "us")


@cocotb.test()
async def test_clock_ratio_equal(dut):
    await with_timeout(_ratio_sweep_workload(dut, 10, 10), 50, "us")


@cocotb.test()
async def test_clock_ratio_coprime(dut):
    # 7/11 -- coprime, edges slide continuously across the whole run,
    # the closest sim proxy for a real metastability-window sweep.
    await with_timeout(_ratio_sweep_workload(dut, 7, 11, n=20), 50, "us")


# --- 12. reset mid-transaction, s side (single-sided; rst_both_n hard flush) --

async def _reset_mid_transaction_s_side_body(dut):
    """s-only reset while a transfer is mid-flight must still be a hard
    flush (this leg is UNCHANGED by the availability fix, commit
    cb5c780 -- see apb_cdc_bridge.sv's header: an s_rst_n_i-only event still
    drops rst_both_n and flushes both domains together).

    Kill-timing note (review finding, same reasoning already
    applied to test_async_axi_fifo.py's test_reset_while_busy_s_side): the
    interrupted master task is killed AT reset assertion, not after
    release+settling. A real APB master is itself part of the domain this
    reset covers, so its own issuing state would be wiped by the very same
    reset edge; a surviving, un-reset Python coroutine that resumed driving
    psel/penable into the freshly-recovered bridge afterward would not model
    any real master's behaviour, and _idle_s_side() could then cut a
    resumed drive in half at an arbitrary point.
    """
    ctx = await _setup(dut, 10, 10, wait_states=5)

    t = cocotb.start_soon(ctx.s_master.write(0x600, 0xABCD1234))
    await ClockCycles(dut.s_clk, 2)  # let SETUP + req_q launch happen first
    # Assert ONLY s_rst_n -- m_rst_n stays high throughout. The point of this
    # test is that a single-sided reset still flushes BOTH domains via
    # rst_both_n = s_rst_n_i & m_rst_n_i (see apb_cdc_bridge.sv header).
    dut.s_rst_n.value = 0
    # Kill + idle immediately -- models the master's own reset, not a
    # surviving driver resuming mid-transfer across the DUT's reset boundary.
    t.kill()
    _idle_s_side(dut)
    await ClockCycles(dut.s_clk, 5)
    dut.s_rst_n.value = 1
    # Post-reset recovery margin -- the
    # post-recovery write below assumes success, so this must cover the
    # reset-status synchronisers' worst case, not just their nominal
    # latency.
    n = _post_reset_recovery_cycles(dut)
    await ClockCycles(dut.s_clk, n)
    await ClockCycles(dut.m_clk, n)

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
    """Availability fix: an m-only reset while a
    request has already been FORWARDED and is genuinely in flight (S_REQ,
    req_fwd_q=1) no longer wedges s_pready forever. The bridge's S_REQ exit
    condition (`ack_s || !req_fwd_q || !m_rst_n_s`) force-completes with
    s_pready=1, s_pslverr=1 within a bounded number of s_clk cycles once the
    destination is observed to have entered reset.

    This REPLACES the old assertion here (s_pslverr==0, silently dropped) --
    that encoded exactly the permanent hang this fix closes: previously
    rst_both_n held the source FSM itself in S_IDLE for as long as m_rst_n_i
    stayed low, so s_pready could never assert at all while an APB access to
    the PLL2 window raced an m-only reset, wedging the entire upstream APB
    tree. See apb_cdc_bridge.sv's "Reset strategy" header for the full
    asymmetric-reset justification (m_rst_sync_n deliberately stays coupled
    to rst_both_n as a conservative, reviewed choice (the
    RZ conversion removed the parity invariant this
    coupling used to protect -- see apb_cdc_bridge.sv header); m_rst_n_s + req_fwd_q + the
    bounded S_REQ exit are what make this direction safe without that
    coupling).

    The interrupted read task now completes ON ITS OWN (no t.kill() needed)
    -- unlike the s-side test above, there is no surviving un-reset master
    coroutine to race here: the bridge itself resolves the transaction with
    a real (error) response, so simply awaiting the task is correct.
    """
    ctx = await _setup(dut, 10, 10, wait_states=5)
    ctx.responder.mem[0x700] = 0xBEEF0001

    t = cocotb.start_soon(ctx.s_master.read(0x700))
    await ClockCycles(dut.m_clk, 3)  # let the request cross into the m domain and be forwarded first

    # Confirm (via backdoor, --public-flat-rw) this really is the "forwarded,
    # then aborted mid-S_REQ" path, not the "never forwarded" one covered
    # separately by test_availability_never_forwarded.
    assert int(dut.u_dut.req_fwd_q.value) == 1, (
        "setup assumption violated: request was not yet forwarded (req_fwd_q=0) "
        "before m_rst_n is asserted below -- this test targets the "
        "'aborted after forwarding' escape path, not the 'never forwarded' one"
    )
    assert int(dut.u_dut.s_state_q.value) == S_REQ, (
        "setup assumption violated: source FSM is not in S_REQ -- the request "
        "must still be genuinely in flight when m_rst_n is asserted"
    )

    # Assert ONLY m_rst_n -- s_rst_n stays high throughout.
    dut.m_rst_n.value = 0

    data, ok = await t
    assert ok is False, (
        "expected the m-only-reset-interrupted read to force-complete with "
        "s_pslverr=1 (the availability fix's bounded error-completion path), "
        "not silently hang forever or fabricate an OKAY response"
    )
    assert ctx.responder.completed == 0, (
        "no destination-side transfer should have completed for the aborted "
        "request -- the responder observed one anyway (completed="
        f"{ctx.responder.completed})"
    )
    assert ctx.responder.mem.get(0x700) == 0xBEEF0001, (
        "destination-side mem for the aborted read's address must be "
        "unchanged (it was a read, and the responder must not have been "
        "allowed to fabricate a completion for it)"
    )

    await ClockCycles(dut.m_clk, 5)
    dut.m_rst_n.value = 1
    # Post-reset recovery margin -- the
    # post-recovery write further below assumes success, so this must
    # cover the reset-status synchronisers' worst case, not just their
    # nominal latency.
    n = _post_reset_recovery_cycles(dut)
    await ClockCycles(dut.s_clk, n)
    await ClockCycles(dut.m_clk, n)

    await ClockCycles(dut.s_clk, 2)
    assert int(dut.s_pready.value) == 0, "s_pready must return to idle-low after the error-completion pulse"
    # Note: s_pslverr_o (resp_pslverr_q) is a "last response status" register
    # captured only during S_REQ and held stable in between transactions --
    # apb_cdc_bridge.sv never self-clears it after S_DONE (mirroring
    # resp_prdata_q's identical behaviour), and no real APB master looks at
    # pslverr except in the same cycle it observes pready=1 (exactly what
    # APB4Master.read()/write() do). Asserting it reads 0 here would test a
    # property the RTL never promised. The post-recovery write+read below
    # already proves it gets correctly overwritten to 0 on the next genuine
    # OKAY completion.

    # Re-check (not just during the abort itself, but again now, in the
    # window after m_rst_n_i has actually released) that the aborted request
    # produced no destination-side completion -- closes the "no stray write
    # lands once m_rst_n_i deasserts" / no-stale-level-collision property
    # (RZ has no parity register to protect,
    # but the req_q clamp-to-0 must still hold -- see apb_cdc_bridge.sv
    # header "No fabricated destination-side write, RZ argument"):
    # if req_q's clamp-to-0 (while !m_rst_n_s) had NOT correctly held it at
    # 0 for the entire abort, releasing m_rst_n_i here is exactly the moment
    # a stale, out-of-sync req_q could suddenly look like a "new" request to
    # D_IDLE and fire a spurious destination transfer.
    assert ctx.responder.completed == 0, (
        "a destination-side transfer appeared after m_rst_n_i released, "
        "before any new request was issued -- req_q's clamp did not "
        "correctly prevent a stale/collided level from firing"
    )

    ok2 = await ctx.s_master.write(0x700, 0x33334444)
    assert ok2, "post-recovery write reported pslverr -- unrelated to the earlier aborted request?"
    assert ctx.responder.completed == 1, (
        f"expected exactly 1 destination-side completion for this one new "
        f"write, got {ctx.responder.completed} -- possible extra transfer "
        "from a stale-level collision with the earlier aborted request"
    )
    data2, ok3 = await ctx.s_master.read(0x700)
    assert ok3, "post-recovery read reported pslverr"
    assert data2 == 0x33334444, f"post-recovery readback mismatch: {data2:#x}"
    dut._log.info(
        "reset-mid-transaction (m side) OK: in-flight transfer force-completed with "
        "s_pslverr=1 within bounded time (GH #93 availability fix), no destination "
        "write/completion fabricated, clean recovery for a new transaction"
    )


@cocotb.test()
async def test_reset_mid_transaction_m_side(dut):
    await with_timeout(_reset_mid_transaction_m_side_body(dut), 50, "us")


# --- 14. no lost/duplicated transactions, long randomized stream -------------

async def _no_lost_or_duplicated_stream_body(dut):
    # 7/13 -- coprime and deliberately different from the ratio sweep
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
    # s_clk period 4 / m_clk period 9 -- same proxy ratio as the SoC integration
    # case (see module docstring), so this number is a usable budget input.
    # Bound once (review finding): previously `_setup(dut, 4, 9)`
    # and `slow_ns = max(4, 9)` repeated the same two literals independently,
    # so changing one without the other would silently desynchronize the
    # derived bound from the ratio actually under test.
    s_ns, m_ns = 4, 9
    ctx = await _setup(dut, s_ns, m_ns)

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

    # Derived bound (not just measured):
    # apb_cdc_bridge.sv's s_pready_o now gates on the FULL 4-phase round
    # trip (assert AND deassert), not just the assert half -- APB is
    # master-driven, so pready must not pulse until this bridge is actually
    # back at (one cycle from) S_IDLE to accept a new SETUP, or the next
    # transaction's SETUP would be silently missed (see apb_cdc_bridge.sv's
    # S_DROP/S_DONE header note for the full reasoning; an earlier draft of
    # this RTL got this ordering wrong and a back-to-back test caught it
    # immediately). One-way (assert) trip: req_q crosses into the m domain
    # as req_m ((sync_m + 1) m-cycles: SYNC_STAGES_TO_M sync flops + 1 cycle
    # of conservative padding -- D_IDLE watches req_m directly, RZ has no
    # comparator register to "catch up" the way the old NRZ req_seen_q did,
    # but this padding is kept as slack, not a requirement), runs one
    # D_SETUP + one zero-wait D_ACCESS cycle (2 m-cycles), then ack_q
    # crosses back into the s domain as ack_s ((sync_s + 1) s-cycles, same
    # reasoning), plus 2 s-cycles of state-transition slack. The deassert
    # (return-to-zero) half mirrors the SAME crossings and transitions in
    # reverse (req_q fall -> req_m fall -> D_ACK exit -> ack_q fall ->
    # ack_s fall -> S_DROP exit -> S_DONE pulse), so the total budget is
    # simply DOUBLE the one-way figure -- not a new derivation, just the
    # same trip taken twice. Expressed conservatively in the SLOWER of the
    # two periods, with a 2x safety margin for scheduling slop between two
    # independently free-running Clock() coroutines (not a tight bound, but
    # a real, derived one -- see the STA action item in
    # apb_cdc_bridge.sv's header for the eventual set_max_delay treatment
    # of these same paths).
    slow_ns = max(s_ns, m_ns)
    one_way_budget_cycles = (sync_m + 1) + 2 + (sync_s + 1) + 2
    budget_cycles = 2 * one_way_budget_cycles
    bound_ns = 2 * budget_cycles * slow_ns

    dut._log.info(
        f"GH #93 apb_cdc_bridge round-trip latency budget (s_clk={s_ns}ns/m_clk={m_ns}ns): "
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


# --- 16-18. availability-fix escape-path coverage ----
#
# apb_cdc_bridge.sv's availability fix closes a hang where an APB access to
# the PLL2 window while ONLY the destination (m_rst_n_i) domain was in reset
# used to wedge the source FSM in S_IDLE forever. The fix adds a new
# same-domain status crossing (m_rst_n_s), a req_fwd_q latch, and a bounded
# S_REQ exit (`ack_s || !req_fwd_q || !m_rst_n_s`). The tests below
# exercise each of the three ways S_REQ can now resolve, plus the two
# structural invariants the fix's own header commits to: no destination
# write ever lands for an aborted/errored request, and req_q's
# clamp-to-0 prevents a stale-level collision across repeated m-only
# resets (RZ removed the "toggle-parity"
# concept these comments used to invoke -- see apb_cdc_bridge.sv header).
# test_reset_mid_transaction_m_side above already covers the
# "forwarded, then aborted mid-S_REQ" path with an explicit req_fwd_q/
# s_state_q backdoor check.

# --- 16. never forwarded: destination already observed in reset at SETUP ----

async def _availability_never_forwarded_body(dut):
    """m_rst_n_i asserted BEFORE any request is issued: the very first SETUP
    latches req_fwd_q=0 (destination already observed dead), so the request
    is never forwarded at all and S_REQ resolves via the `!req_fwd_q`
    escape on the very next cycle -- a fast, local-only completion, not a
    round trip through the destination."""
    ctx = await _setup(dut, 10, 10)
    addr = 0xA00

    sync_s = int(dut.sync_stages_to_s_o.value)
    dut.m_rst_n.value = 0
    # Let m_rst_n_s (this domain's own synchronised view) settle to "in
    # reset" before issuing anything -- SYNC_STAGES_TO_S cycles plus margin.
    await ClockCycles(dut.s_clk, sync_s + 3)
    assert int(dut.u_dut.m_rst_n_s.value) == 0, (
        "setup assumption violated: m_rst_n_s should already read 0 "
        "(destination observed in reset) before SETUP is even issued"
    )

    t0 = get_sim_time(units="ns")
    data, ok = await ctx.s_master.read(addr)
    t1 = get_sim_time(units="ns")
    elapsed_ns = t1 - t0

    assert ok is False, (
        "expected an immediate pslverr=1 completion -- the destination was "
        "already observed in reset at SETUP, so req_fwd_q should latch 0 and "
        "the request should never be forwarded at all"
    )
    assert ctx.responder.completed == 0, (
        "the request must never have reached the destination responder "
        f"(completed={ctx.responder.completed})"
    )
    # Fast, local-only completion -- nowhere near a real round trip (which
    # needs at least one m_clk SETUP+ACCESS cycle plus two full CDC
    # crossings). Generous bound, not a tight one.
    generous_local_bound_ns = (sync_s + 4) * 10
    assert elapsed_ns <= generous_local_bound_ns, (
        f"never-forwarded completion took {elapsed_ns} ns, expected a fast "
        f"local-only completion under {generous_local_bound_ns} ns -- did it "
        "actually reach the destination instead of completing locally?"
    )

    # Recover and confirm clean transactions afterward.
    dut.m_rst_n.value = 1
    # Post-reset recovery margin -- THIS is
    # the site of the original failure: the old bare `ClockCycles(dut.
    # m_clk, 3)` (== SYNC_STAGES+1) was exactly-tight against the
    # m_rst_n_i-status synchroniser into the s domain's own nominal
    # latency, not generously tight against its worst case, so it failed
    # deterministically once the settling-delay injector's one-extra-cycle
    # fault model was active on that synchroniser. Also wait s_clk cycles
    # (not just m_clk) since the post-recovery write below is issued from
    # the s domain and is gated by the synchroniser that resolves there.
    n = _post_reset_recovery_cycles(dut)
    await ClockCycles(dut.s_clk, n)
    await ClockCycles(dut.m_clk, n)
    # Re-check (now that m_rst_n_i has actually released, not just during
    # the never-forwarded completion itself) that nothing spurious reached
    # the destination -- same no-stale-level-collision property as
    # test_reset_mid_transaction_m_side's equivalent check.
    assert ctx.responder.completed == 0, (
        "a destination-side transfer appeared after m_rst_n_i released, "
        "before any new request was issued"
    )
    ok2 = await ctx.s_master.write(addr, 0xAAAA5555)
    assert ok2, "post-recovery write reported pslverr"
    assert ctx.responder.completed == 1, (
        f"expected exactly 1 destination-side completion for this one new "
        f"write, got {ctx.responder.completed}"
    )
    data2, ok3 = await ctx.s_master.read(addr)
    assert ok3 and data2 == 0xAAAA5555, f"post-recovery readback mismatch: {data2:#x}"
    dut._log.info(
        f"availability never-forwarded OK: read force-completed with pslverr=1 in "
        f"{elapsed_ns:.1f} ns without ever reaching the destination "
        f"(completed={ctx.responder.completed}); clean recovery after m_rst_n release"
    )


@cocotb.test()
async def test_availability_never_forwarded(dut):
    await with_timeout(_availability_never_forwarded_body(dut), 50, "us")


# --- 17. ack_s wins a same-s_clk-edge race against destination-reset -------

async def _availability_ack_race_wins_body(dut):
    """Prove that when ack_s (the real destination response, already
    safely captured at the destination and independently propagating) and
    !m_rst_n_s (the destination-reset-detected condition) become true on the
    EXACT SAME s_clk edge, ack_s wins -- apb_cdc_bridge.sv's
    `if (ack_s) ... else if (!req_fwd_q || !m_rst_n_s) ...` checks ack_s
    first, so this is a deterministic priority encoding on two already-
    synchronised, registered single-bit signals (no metastability, no real
    hardware race) -- but it is only actually EXERCISED if both are
    engineered to change on the identical edge.

    ack_q's assert-edge (0->1) at the destination is NOT influenced by
    m_rst_n_i at all (u_ack_sync's reset is s_rst_sync_n, never m_rst_n_i),
    so it is safe to let the ack complete for real at the destination first,
    then align m_rst_n_i's assertion so its OWN independent 2-stage
    synchroniser (u_m_rst_status_sync) settles on the same edge that ack_q's
    propagation (through u_ack_sync, also 2-stage, both clocked by s_clk_i)
    completes. Getting the timestep-boundary offset for that byte-perfect
    is delicate under cocotb's RisingEdge/ReadOnly discipline (you cannot
    write a signal in the same timestep you just read it via ReadOnly), so
    this test self-calibrates: it sweeps the exact number of edges to wait
    after observing ack_q assert before asserting m_rst_n_i, on a fresh
    transaction each time, until it observes (via safe ReadOnly reads of
    ack_s / m_in_rst_s -- ack_s is ack_q's synchronised copy in the s
    domain, renamed from ack_toggle_s) that
    both actually changed on the same s_clk edge, then checks the response
    from that specific run. Only the FIRST assert (0->1) is tracked here --
    under the old NRZ encoding this was ack_toggle_q's only meaningful
    transition per request; under RZ, ack_q also later deasserts (1->0,
    the "return to zero" half), but that is irrelevant to this race, which
    only cares about the moment the real response first becomes visible.
    """
    addr = 0xB00
    golden = 0xCAFED00D
    aligned = None

    for wait_edges in range(1, 7):
        ctx = await _setup(dut, 10, 10)
        ctx.responder.mem[addr] = golden

        prev_ack_q = int(dut.u_dut.ack_q.value)
        t = cocotb.start_soon(ctx.s_master.read(addr))

        flip_seen = False
        for _ in range(300):
            await RisingEdge(dut.m_clk)
            await ReadOnly()
            cur = int(dut.u_dut.ack_q.value)
            if cur != prev_ack_q:
                flip_seen = True
                break
            prev_ack_q = cur
        assert flip_seen, f"wait_edges={wait_edges}: ack_q never asserted at the destination"

        # Advance wait_edges more m_clk edges (== s_clk edges here, 10/10
        # phase-aligned) before writing m_rst_n_i -- the earliest possible
        # write is 1 edge after the ReadOnly-based detection above (cocotb
        # cannot write in the same timestep it just read via ReadOnly), so
        # this sweep's wait_edges=1 is the tightest offset actually reachable.
        for _ in range(wait_edges):
            await RisingEdge(dut.m_clk)
        dut.m_rst_n.value = 0

        prev_ack_s = int(dut.u_dut.ack_s.value)
        prev_in_rst = int(dut.u_dut.m_in_rst_s.value)
        ack_s_edge = None
        rst_edge = None
        for i in range(10):
            await RisingEdge(dut.s_clk)
            await ReadOnly()
            cur_ack_s = int(dut.u_dut.ack_s.value)
            cur_in_rst = int(dut.u_dut.m_in_rst_s.value)
            if ack_s_edge is None and cur_ack_s != prev_ack_s:
                ack_s_edge = i
            if rst_edge is None and cur_in_rst != prev_in_rst:
                rst_edge = i
            prev_ack_s, prev_in_rst = cur_ack_s, cur_in_rst
            if ack_s_edge is not None and rst_edge is not None:
                break

        if ack_s_edge is not None and rst_edge is not None and ack_s_edge == rst_edge:
            data, ok = await t
            aligned = (wait_edges, ack_s_edge, data, ok)
            break

        # Not aligned this attempt -- clean up and try the next offset with
        # a fresh _setup() (which fully re-resets everything, including
        # ack_q back to 0, so each attempt is independent). The watch
        # loop above always exits from a ReadOnly phase (whether it broke on
        # a match or ran out of iterations), so a RisingEdge is needed first
        # to reach a writable region before touching m_rst_n.
        t.kill()
        await RisingEdge(dut.s_clk)
        dut.m_rst_n.value = 1
        await ClockCycles(dut.m_clk, 5)

    assert aligned is not None, (
        "could not engineer ack_s and the destination-reset-detected "
        "condition to land on the same s_clk edge within the swept "
        "wait_edges range 1..6 -- test calibration needs adjustment"
    )
    wait_edges, ack_s_edge, data, ok = aligned
    assert ok is True, (
        f"ack_s and the destination-reset-detected condition landed on the "
        f"same s_clk edge (wait_edges={wait_edges}, edge offset {ack_s_edge}) "
        f"but the response was NOT the real one (ok={ok}) -- ack_s must win "
        "this race per apb_cdc_bridge.sv's if/else-if priority"
    )
    assert data == golden, f"race-won response data mismatch: {data:#x}"
    dut._log.info(
        f"availability ack-race OK: at wait_edges={wait_edges}, ack_s and "
        f"m_in_rst_s both changed on the same s_clk edge (offset {ack_s_edge}) -- "
        f"ack_s won, real data 0x{data:08x} returned, not a fabricated pslverr=1"
    )


@cocotb.test()
async def test_availability_ack_race_wins(dut):
    await with_timeout(_availability_ack_race_wins_body(dut), 200, "us")


# --- 18. back-to-back m_rst_n_i pulses, transaction attempted between them --

async def _availability_back_to_back_resets_workload(dut, s_ns, m_ns):
    """Two m_rst_n_i pulses with a real transaction attempted between them,
    then a final round trip after the second pulse recovers -- proves
    req_q's continuous clamp-to-0 (while !m_rst_n_s) re-establishes req_q's
    level matching req_m's own reset default (0) across EACH pulse
    independently, so back-to-back resets never leave a stale-level
    collision (RZ has no parity register, but
    the clamp invariant this test proves is unchanged from the old NRZ
    scheme's toggle-parity property -- see apb_cdc_bridge.sv header) that
    corrupts or hangs a later, genuinely new transaction. Also confirms no
    destination-side write lands for anything spurious across either pulse
    (completed count check)."""
    ctx = await _setup(dut, s_ns, m_ns)
    addr = 0xC00

    # First pulse -- no transaction in flight, just the reset/recover cycle.
    dut.m_rst_n.value = 0
    await ClockCycles(dut.m_clk, 5)
    dut.m_rst_n.value = 1
    # Post-reset recovery margin -- the
    # write below assumes success, so this must cover the reset-status
    # synchronisers' worst case, not just their nominal latency. Applies
    # to both pulses below.
    n = _post_reset_recovery_cycles(dut)
    await ClockCycles(dut.m_clk, n)
    await ClockCycles(dut.s_clk, n)

    # Between the two pulses, the destination is genuinely alive -- this
    # must complete for real.
    ok = await ctx.s_master.write(addr, 0x11112222)
    assert ok, "write between back-to-back resets unexpectedly reported pslverr"
    assert ctx.responder.mem.get(addr) == 0x11112222, "write between resets did not land at the destination"

    # Second pulse.
    dut.m_rst_n.value = 0
    await ClockCycles(dut.m_clk, 5)
    dut.m_rst_n.value = 1
    await ClockCycles(dut.m_clk, n)
    await ClockCycles(dut.s_clk, n)

    completed_before = ctx.responder.completed
    data, ok2 = await ctx.s_master.read(addr)
    assert ok2, "read after second reset pulse reported pslverr"
    assert data == 0x11112222, (
        f"read after second reset pulse mismatch: {data:#x} -- possible "
        "stale-level collision across the back-to-back resets"
    )

    ok3 = await ctx.s_master.write(addr, 0x33334444)
    assert ok3, "write after second reset pulse reported pslverr"
    data2, ok4 = await ctx.s_master.read(addr)
    assert ok4 and data2 == 0x33334444, f"final post-reset round trip mismatch: {data2:#x}"

    assert ctx.responder.completed == completed_before + 3, (
        f"expected exactly 3 more destination-side completions (read+write+read) "
        f"after the second pulse, got {ctx.responder.completed - completed_before} "
        "-- possible extra/missing transfer from stale-level drift"
    )
    dut._log.info(
        f"back-to-back resets OK at {s_ns}ns/{m_ns}ns: mid-pulse write landed, "
        f"post-pulse round trips correct, no stale-level drift "
        f"(completed={ctx.responder.completed})"
    )


@cocotb.test()
async def test_availability_back_to_back_resets_equal(dut):
    await with_timeout(_availability_back_to_back_resets_workload(dut, 10, 10), 50, "us")


@cocotb.test()
async def test_availability_back_to_back_resets_wide_ratio(dut):
    # 18/4 (slow-s/fast-m) -- explicitly called out: this exact ratio
    # caught a regression in the RTL agent's own first attempt at this fix.
    await with_timeout(_availability_back_to_back_resets_workload(dut, 18, 4), 50, "us")


# --- 19. RZ 4-phase structural proof ----------
#
# Every test above proves FUNCTIONAL correctness -- data integrity, bounded
# completion, no fabricated writes -- and all of it holds for EITHER
# handshake encoding (NRZ toggle or RZ level); that is deliberate, since the
# conversion must not change externally observable APB behaviour. This test
# instead proves the ENCODING itself: that apb_cdc_bridge.sv actually
# executes a 4-phase return-to-zero round trip (assert req, assert ack,
# DEASSERT req, DEASSERT ack) and not a 2-phase toggle. It is the one test
# in this suite that is EXPECTED TO FAIL against the earlier 2-phase
# NRZ RTL, not just a regression check against the current (already-RZ)
# RTL -- see the docstring below for exactly why.

async def _rz_four_phase_structural_body(dut):
    """Directed structural proof that the handshake is 4-phase RZ, not
    2-phase NRZ. Monitors s_state_q, req_q and ack_s (all via
    --public-flat-rw backdoor, same mechanism test_reset_mid_transaction_m_side
    / test_availability_ack_race_wins already rely on) across one full write
    transaction and asserts the return-to-zero sequence:
      1. req_q rises (0->1)            -- phase 1, request asserted
      2. ack_s rises (0->1)            -- phase 2, destination answered
      3. req_q FALLS (1->0) while ack_s is STILL 1
                                        -- phase 3, source deasserts req
                                           FIRST, strictly before ack_s falls
      4. ack_s FALLS (1->0)            -- phase 4, destination completes
                                           the round trip
      5. s_state_q visits S_DROP (the dedicated "waiting for ack_s to fall"
         state) between S_REQ and S_DONE -- the FSM order is
         S_IDLE -> S_REQ -> S_DROP -> S_DONE -> S_IDLE.

    Why this fails on the OLD (pre-rfz) 2-phase NRZ RTL: that RTL's
    s_state_e had only 3 values (S_IDLE, S_WAIT, S_DONE) and went directly
    S_DONE -> S_IDLE every transaction -- step 5 above is structurally
    impossible to observe, since no state numbered 3 (S_DROP) ever existed.
    Steps 1-4 are equally impossible: the old RTL's req_toggle_q/ack_toggle_q
    FLIP (change value, either direction) once per transfer and never
    "return to zero" relative to each other by design -- there is no
    req-falls-before-ack-falls ordering to observe because req_toggle_q does
    not fall at all on a normal completion (it toggles again only on the
    NEXT SETUP, which may be many idle cycles later or may re-toggle it back
    to the value it fell from, depending on parity -- there is no
    deterministic per-transaction deassert step to synchronise on). Run
    against that RTL, this test's phase-3/phase-4/state-5 assertions would
    either time out (the awaited transitions never happen) or never
    observe s_state_q == 3 at all -- a clean, mechanistic failure, not a
    timing coincidence.
    """
    ctx = await _setup(dut, 10, 10)
    addr = 0xD00

    # --- Phase 1: launch a write and watch for req_q's assert edge --------
    prev_req_q = int(dut.u_dut.req_q.value)
    assert prev_req_q == 0, "setup assumption violated: req_q must be idle-low before SETUP"
    t = cocotb.start_soon(ctx.s_master.write(addr, 0xE4A5E4A5))

    req_assert_seen = False
    for _ in range(50):
        await RisingEdge(dut.s_clk)
        await ReadOnly()
        cur = int(dut.u_dut.req_q.value)
        if cur == 1 and prev_req_q == 0:
            req_assert_seen = True
            break
        prev_req_q = cur
    assert req_assert_seen, "phase 1 FAILED: req_q never asserted (0->1) after SETUP"

    # --- Phase 2: watch for ack_s's assert edge (destination answered) ----
    prev_ack_s = int(dut.u_dut.ack_s.value)
    ack_assert_seen = False
    for _ in range(50):
        await RisingEdge(dut.s_clk)
        await ReadOnly()
        cur_ack = int(dut.u_dut.ack_s.value)
        cur_req = int(dut.u_dut.req_q.value)
        if cur_ack == 1 and prev_ack_s == 0:
            ack_assert_seen = True
            # req_q must still read 1 here -- ack_s asserting is what
            # TRIGGERS req_q's deassert (S_REQ's ack_s-seen branch), so on
            # the very cycle ack_s is first observed high, req_q has not
            # yet had a chance to fall.
            assert cur_req == 1, (
                "phase ordering FAILED: req_q already fell before ack_s's "
                "assert edge was even observed -- the RZ round trip requires "
                "req_q to stay asserted until the source has SEEN ack_s"
            )
            break
        prev_ack_s = cur_ack
    assert ack_assert_seen, "phase 2 FAILED: ack_s never asserted (0->1)"

    # --- Phase 3: watch for req_q's deassert edge, confirming ack_s is
    #     STILL high at that moment (source drops req FIRST) -------------
    prev_req_q = 1
    req_deassert_seen = False
    ack_still_high_at_req_fall = False
    for _ in range(50):
        await RisingEdge(dut.s_clk)
        await ReadOnly()
        cur_req = int(dut.u_dut.req_q.value)
        if cur_req == 0 and prev_req_q == 1:
            req_deassert_seen = True
            ack_still_high_at_req_fall = int(dut.u_dut.ack_s.value) == 1
            break
        prev_req_q = cur_req
    assert req_deassert_seen, "phase 3 FAILED: req_q never deasserted (1->0) after ack_s"
    assert ack_still_high_at_req_fall, (
        "phase 3 FAILED: ack_s had already fallen by the time req_q "
        "deasserted -- the defining RZ ordering (req falls strictly before "
        "ack falls) does not hold; this looks like an NRZ-style transition, "
        "not a 4-phase return-to-zero round trip"
    )

    # --- Phase 4: watch for ack_s's deassert edge (round trip complete) ---
    prev_ack_s = 1
    ack_deassert_seen = False
    saw_s_drop = False
    for _ in range(50):
        await RisingEdge(dut.s_clk)
        await ReadOnly()
        if int(dut.u_dut.s_state_q.value) == S_DROP:
            saw_s_drop = True
        cur_ack = int(dut.u_dut.ack_s.value)
        if cur_ack == 0 and prev_ack_s == 1:
            ack_deassert_seen = True
            break
        prev_ack_s = cur_ack
    assert ack_deassert_seen, "phase 4 FAILED: ack_s never deasserted (1->0) -- round trip did not complete"
    assert saw_s_drop, (
        "structural check FAILED: s_state_q never visited S_DROP (2) while "
        "waiting for ack_s to fall -- the dedicated return-to-zero state was "
        "not exercised"
    )

    ok = await t
    assert ok, "the monitored write itself reported pslverr"
    assert ctx.responder.mem.get(addr) == 0xE4A5E4A5, "the monitored write did not land at the destination"
    dut._log.info(
        "RZ 4-phase structural proof OK: req_q asserted -> ack_s asserted "
        "(req_q still 1) -> req_q deasserted (ack_s still 1) -> ack_s "
        "deasserted, with s_state_q visiting S_DROP in between -- this exact "
        "sequence is impossible on the pre-bead-rfz 2-phase NRZ encoding"
    )


@cocotb.test()
async def test_rz_four_phase_structural_proof(dut):
    await with_timeout(_rz_four_phase_structural_body(dut), 50, "us")


# =============================================================================
# Reset-asymmetry test class.
#
# The existing availability tests above (test_availability_never_forwarded,
# test_reset_mid_transaction_m_side, test_availability_back_to_back_resets_*)
# already cover the m_rst_n_i-held direction thoroughly. Two things they do
# NOT cover, which these tests add:
#   1. The MIRROR direction (s_rst_n_i held, m_clk free-running) -- per the
#      asymmetric reset fix, s_rst_sync_n is rooted in s_rst_n_i
#      ALONE (not rst_both_n -- see apb_cdc_bridge.sv's "Reset strategy"
#      header), so this direction fully holds the source FSM at S_IDLE
#      regardless of the destination. m_rst_sync_n stays coupled to
#      rst_both_n, so the destination is ALSO held even though m_rst_n_i
#      itself is released -- zero activity on either face is the expected,
#      testable invariant.
#   2. A staggered RELEASE-ORDER sweep with CONTINUOUS offered traffic
#      during the asymmetric window (existing tests hold m_rst_n_i low
#      from before _setup()'s reset even starts, i.e. release order is not
#      exercised) -- the actual SoC bug was a
#      release-SKEW defect, not a simultaneous-both-held one.
#
# Both classes explicitly respect the documented, reviewed
# "Availability-gating exception (m_rst_n_s)" in
# apb_cdc_bridge.sv (m_rst_n_s reads "alive" for up to SYNC_STAGES_TO_S
# s_clk_i cycles after s_rst_sync_n releases, even if m_rst_n_i is already
# low) by asserting only the properties the module's own header proves hold
# THROUGH that exception: m_psel_o/m_penable_o never pulse while m_rst_n_i
# is genuinely low (no fabricated destination-side write, ever), and
# s_pready_o always completes within a bounded number of s_clk_i cycles
# (S_REQ never hangs). This class does NOT assert req_fwd_q or the forward
# decision itself, which the exception explicitly and correctly permits to
# be wrong for a bounded window.
# =============================================================================

# --- 20. mirror direction: s held, m free-running ------------------------------

async def _apb_reset_asym_s_held_m_free_body(dut, s_ns, m_ns) -> None:
    _kill_active_tasks()
    s_clk_task = cocotb.start_soon(Clock(dut.s_clk, s_ns, units="ns").start())
    m_clk_task = cocotb.start_soon(Clock(dut.m_clk, m_ns, units="ns").start())
    _active_tasks.extend([s_clk_task, m_clk_task])

    responder = ApbSlaveResponder(dut, "m_", dut.m_clk)
    resp_task = responder.start()
    _active_tasks.append(resp_task)

    dut.s_rst_n.value = 0
    dut.m_rst_n.value = 0
    _idle_s_side(dut)
    await Timer(RESET_HOLD_NS, units="ns")

    # Release ONLY m_rst_n_i -- s_rst_n_i stays low. s_psel/s_penable are
    # left at their idle-low default throughout this window (an APB master
    # genuinely held in its own domain's reset would never drive SETUP), so
    # this checks the DUT's own idle/held outputs, not a rejected offer.
    dut.m_rst_n.value = 1
    for i in range(20):
        await RisingEdge(dut.m_clk)
        await ReadOnly()
        assert int(dut.s_pready.value) == 0, f"s_pready asserted while s_rst_n_i held low (cycle {i})"
        assert int(dut.m_psel.value) == 0, f"m_psel pulsed while the bridge is held in reset (cycle {i})"
        assert int(dut.m_penable.value) == 0, f"m_penable pulsed while the bridge is held in reset (cycle {i})"
    await RisingEdge(dut.m_clk)

    dut.s_rst_n.value = 1
    # Post-reset recovery margin -- the
    # post-recovery write below assumes success, so this must cover the
    # reset-status synchronisers' worst case, not just their nominal
    # latency.
    n = _post_reset_recovery_cycles(dut)
    await ClockCycles(dut.s_clk, n)
    await ClockCycles(dut.m_clk, n)
    await Timer(1, units="step")  # step off a possibly coincident clock edge (see _setup)

    s_master = APB4Master(dut, "s_", dut.s_clk)
    ok = await s_master.write(0x900, 0xDEADBEEF)
    assert ok, "post-recovery write reported pslverr"
    assert responder.mem.get(0x900) == 0xDEADBEEF, "post-recovery write did not land at the destination"
    data, ok2 = await s_master.read(0x900)
    assert ok2 and data == 0xDEADBEEF, f"post-recovery readback mismatch: {data:#x}"
    dut._log.info(
        f"reset-asym s-held ({s_ns}/{m_ns} ns) OK: s_pready/m_psel/m_penable stayed low for "
        f"20 m_clk cycles while s_rst_n_i was held low, clean recovery after release"
    )


@cocotb.test()
async def test_reset_asym_s_held_m_free(dut):
    # Coprime ratio (7/13), matching the suite's existing convention for
    # its "genuinely different ratio" coprime pair.
    await with_timeout(_apb_reset_asym_s_held_m_free_body(dut, 7, 13), 50, "us")


# --- 21-22. staggered release-order sweep with continuous offered traffic -----

async def _apb_reset_asym_staggered_body(dut, s_ns, m_ns, order) -> None:
    assert order in ("s_first", "m_first")
    first, second = ("s", "m") if order == "s_first" else ("m", "s")
    slower_period = max(s_ns, m_ns)
    stagger_windows_ns = [1 * slower_period, 3 * slower_period, 8 * slower_period]

    for idx, stagger_ns in enumerate(stagger_windows_ns):
        _kill_active_tasks()
        s_clk_task = cocotb.start_soon(Clock(dut.s_clk, s_ns, units="ns").start())
        m_clk_task = cocotb.start_soon(Clock(dut.m_clk, m_ns, units="ns").start())
        _active_tasks.extend([s_clk_task, m_clk_task])

        responder = ApbSlaveResponder(dut, "m_", dut.m_clk)
        resp_task = responder.start()
        _active_tasks.append(resp_task)

        dut.s_rst_n.value = 0
        dut.m_rst_n.value = 0
        _idle_s_side(dut)
        await Timer(RESET_HOLD_NS, units="ns")

        getattr(dut, f"{first}_rst_n").value = 1
        first_clock = dut.m_clk if first == "m" else dut.s_clk
        await ClockCycles(first_clock, 2)

        # Background invariant for the ENTIRE staggered window (both
        # branches below): no destination-side APB transaction is ever
        # fabricated while m_rst_n_i is genuinely low. This is the one
        # property the documented m_rst_n_s exception guarantees holds
        # even during its own bounded false-"alive" window (see header
        # "Availability-gating exception", point (b)).
        async def _m_psel_never_pulses(dut=dut):
            while True:
                await RisingEdge(dut.m_clk)
                await ReadOnly()
                assert int(dut.m_psel.value) == 0, (
                    "m_psel pulsed while m_rst_n_i is held low (staggered "
                    f"order={order} stagger={stagger_ns}ns iteration {idx})"
                )

        watch = None
        if first == "s":
            watch = cocotb.start_soon(_m_psel_never_pulses())
            _active_tasks.append(watch)
            # s_rst_n_i released, m_rst_n_i still low: offer continuous
            # transactions from the s side. Each must force-complete with
            # pslverr=1 within a bounded time (S_REQ never hangs) -- the
            # same escape path test_availability_never_forwarded exercises
            # once; here it is exercised repeatedly, back-to-back, for the
            # full stagger window, at a genuinely staggered (not
            # simultaneous) release.
            s_master = APB4Master(dut, "s_", dut.s_clk)
            elapsed_ns = 0.0
            n_offered = 0
            while elapsed_ns < stagger_ns:
                t0 = get_sim_time(units="ns")
                data, ok = await s_master.read(0xA00 + idx)
                t1 = get_sim_time(units="ns")
                assert ok is False, (
                    f"staggered order={order} stagger={stagger_ns}ns: read completed "
                    f"OK while m_rst_n_i was still low -- destination should be "
                    f"unreachable (fabricated success?)"
                )
                elapsed_ns += (t1 - t0)
                n_offered += 1
            assert n_offered > 0, "test did not actually offer any transactions during the window"
            watch.kill()
            _active_tasks.remove(watch)
        else:
            # m_rst_n_i released, s_rst_n_i still low: s FSM is fully held
            # (s_rst_sync_n rooted in s_rst_n_i alone) so nothing can be
            # offered from the s side at all -- just prove no destination
            # activity appears on its own for the swept window.
            watch = cocotb.start_soon(_m_psel_never_pulses())
            _active_tasks.append(watch)
            await Timer(stagger_ns, units="ns")
            watch.kill()
            _active_tasks.remove(watch)
            await RisingEdge(dut.s_clk)  # land back in a writable phase before the release write below

        getattr(dut, f"{second}_rst_n").value = 1
        # Post-reset recovery margin -- the
        # post-recovery write below assumes success, so this must cover
        # the reset-status synchronisers' worst case, not just their
        # nominal latency.
        n = _post_reset_recovery_cycles(dut)
        await ClockCycles(dut.s_clk, n)
        await ClockCycles(dut.m_clk, n)

        s_master2 = APB4Master(dut, "s_", dut.s_clk)
        ok = await s_master2.write(0xB00 + idx, 0x10000000 + idx)
        assert ok, f"post-recovery write failed (order={order}, stagger={stagger_ns}ns, iteration {idx})"
        assert responder.mem.get(0xB00 + idx) == 0x10000000 + idx, (
            "post-recovery write did not land at the destination"
        )
        data2, ok2 = await s_master2.read(0xB00 + idx)
        assert ok2 and data2 == 0x10000000 + idx, f"post-recovery readback mismatch: {data2:#x}"
        dut._log.info(
            f"staggered apb reset-asym OK: order={order} stagger={stagger_ns}ns, "
            f"iteration {idx} ({s_ns}/{m_ns} ns)"
        )


@cocotb.test()
async def test_reset_asym_staggered_s_then_m(dut):
    # s (source domain) releases first, m held -- offered traffic during the
    # window must bounded-error-complete, never fabricate a destination
    # write. Wide ratio (18/4), the same ratio already flagged in this
    # file as having caught a real RTL regression.
    await with_timeout(_apb_reset_asym_staggered_body(dut, 18, 4, order="s_first"), 100, "us")


@cocotb.test()
async def test_reset_asym_staggered_m_then_s(dut):
    # Mirror ordering: m releases first, s held.
    await with_timeout(_apb_reset_asym_staggered_body(dut, 18, 4, order="m_first"), 100, "us")


# =============================================================================
# Directed confirmation of four reviewed behaviours (B1 to B4).
# Doc: ds:mod:apb-cdc-bridge
#
# A review read these behaviours from the RTL and no simulation had shown them:
#   B1  An error response can follow a destination write that already completed
#       (DS-CDC-102, DS-CDC-103).
#   B2  No timeout: with m_clk_i stopped and m_rst_n_i high, a transfer never completes.
#   B3  A short m_rst_n_i pulse can make the destination repeat one request (DS-CDC-106).
#   B4  Worst-case latency of the bounds of DS-CDC-102 and DS-CDC-103, per clock ratio.
# The RTL is not changed. Each test of B1 to B3 that asserts the specified behaviour is marked
# expect_fail: it must fail while the behaviour exists. If one of them passes, the review was
# wrong or the RTL changed. Then replace it by a normal test that proves the rule. A harness
# fault raises RuntimeError, not AssertionError, so expect_fail cannot hide it. Every
# expect_fail test has a normal companion test that proves the checker and the stimulus.
# =============================================================================

# A pulse of m_rst_n_i that follows DS-CDC-109 lasts this many periods of the slower clock.
LONG_PULSE_PERIODS = 8
# Bound for B2: s_clk_i cycles that s_pready_o must stay low before the test calls it a stall.
STALL_BOUND_S_CYCLES = 300
RESTART_BOUND_S_CYCLES = 100
# DS-CDC-102 counts rising edges of s_clk_i after the SETUP edge.
DS102_MAX_EDGES = 2

# (s period, m period, idle gaps in s cycles). A gap moves the m edges against the s edges.
_ALIGNMENTS = (
    (18, 4, (0, 1)),
    (10, 10, (0,)),
    (7, 11, (0, 1, 2, 3)),
    (4, 9, (0, 1, 2, 3)),
)
_B4_RATIOS = ((4, 9), (18, 4), (10, 10), (7, 11))
_SWEEP_CACHE: dict = {}
_STALL_CACHE: dict = {}


def _now_ns() -> int:
    return int(round(get_sim_time(units="ns")))


def _edge_gap_ns(origin: int, t: int, period: int) -> int:
    """Time from t to the next rising edge of a clock with an edge at origin. An edge at t does
    not count, because a flop clocked at t samples the value from before t."""
    gap = (origin - t) % period
    return gap if gap else period


class _Observer:
    """Passive monitors for one experiment; they never drive a signal.

    m_xfers: one entry (time, pwrite, paddr, pwdata) per completed APB transfer on the m_* face.
      The face is sampled at the falling edge of m_clk, where psel, penable and pready are stable
      and the next rising edge completes the transfer.
    s_done: one entry (time, pslverr, prdata) per s_pready_o pulse.
    ack_s_seen and in_rst_seen record backdoor reads of ack_s and m_in_rst_s while armed.
    """

    def __init__(self, dut):
        self.dut = dut
        self.m_xfers: list = []
        self.s_done: list = []
        self.s_origin = None
        self.armed = False
        self.ack_s_seen = False
        self.in_rst_seen = False
        self._tasks: list = []

    def start(self):
        for coro in (self._watch_m(), self._watch_s()):
            task = cocotb.start_soon(coro)
            self._tasks.append(task)
            _active_tasks.append(task)
        return self

    def stop(self) -> None:
        for task in self._tasks:
            task.kill()
        self._tasks = []

    async def _watch_m(self) -> None:
        dut = self.dut
        while True:
            await FallingEdge(dut.m_clk)
            await ReadOnly()
            if int(dut.m_psel.value) and int(dut.m_penable.value) and int(dut.m_pready.value):
                self.m_xfers.append(
                    (
                        _now_ns(),
                        int(dut.m_pwrite.value),
                        int(dut.m_paddr.value),
                        int(dut.m_pwdata.value),
                    )
                )

    async def _watch_s(self) -> None:
        dut = self.dut
        while True:
            await RisingEdge(dut.s_clk)
            await ReadOnly()
            now = _now_ns()
            if self.s_origin is None:
                self.s_origin = now
            if int(dut.s_pready.value):
                self.s_done.append((now, int(dut.s_pslverr.value), int(dut.s_prdata.value)))
            if self.armed:
                if int(dut.u_dut.ack_s.value):
                    self.ack_s_seen = True
                if int(dut.u_dut.m_in_rst_s.value):
                    self.in_rst_seen = True


async def _wait_ack_q_rise(dut, limit: int = 400):
    """Return the time of the m_clk edge after which ack_q reads 1, or None. The call returns in
    a ReadOnly phase: the caller must await a trigger before it writes a signal."""
    for _ in range(limit):
        await RisingEdge(dut.m_clk)
        await ReadOnly()
        if int(dut.u_dut.ack_q.value):
            return _now_ns()
    return None


def _err_count(row) -> int:
    return sum(1 for _t, err, _d in row["s_done"] if err)


def _fmt_row(row) -> str:
    s_ns, m_ns = row["ratio"]
    head = f"{row['plan']:<8} s/m={s_ns}/{m_ns} gap={row['gap']} edge_gap={row['edge_gap']}"
    if row["skipped"]:
        return f"{head} skipped (window too small)"
    return (
        f"{head} delay={row['delay']} width={row['width']} m_xfers={row['m_xfers']} "
        f"s_done={len(row['s_done'])} s_err={_err_count(row)} ack_s_seen={row['ack_s_seen']} "
        f"in_rst_seen={row['in_rst_seen']}"
    )


def _log_rows(dut, title, rows) -> None:
    dut._log.info(title)
    for row in rows:
        dut._log.info("  " + _fmt_row(row))


async def _ack_window_experiment(dut, s_ns, m_ns, gap, plan) -> dict:
    """One write request; m_rst_n_i pulses low a fixed time after ack_q rises on the m side.

    plan(edge_gap) returns (delay, width) in time units, or None when the window is too small.
    edge_gap is the time from the ack_q rise to the next s_clk edge, so a delay below it means
    that no s_clk edge sees ack_q high. A fresh reset and a fresh responder start each call.
    """
    ctx = await _setup(dut, s_ns, m_ns)
    obs = _Observer(dut).start()
    obs.armed = True
    if gap:
        await ClockCycles(dut.s_clk, gap)
    master = cocotb.start_soon(ctx.s_master.write(0xE00, 0x5EED0001))
    t_rise = await _wait_ack_q_rise(dut)
    if t_rise is None or obs.s_origin is None:
        raise RuntimeError("harness: ack_q never rose, or no s_clk edge was observed")
    edge_gap = _edge_gap_ns(obs.s_origin, t_rise, s_ns)
    choice = plan(edge_gap)
    row = {"ratio": (s_ns, m_ns), "gap": gap, "edge_gap": edge_gap, "skipped": choice is None}
    if choice is None:
        await Timer(1, units="step")  # leave the ReadOnly phase before the cleanup writes
    else:
        delay, width = choice
        await Timer(delay, units="ns")
        dut.m_rst_n.value = 0
        await Timer(width, units="ns")
        dut.m_rst_n.value = 1
        for _ in range(120):
            await RisingEdge(dut.s_clk)
            if obs.s_done:
                break
        # Time for a repeated transfer, if there is one, to show on the m_* face.
        await Timer(30 * max(s_ns, m_ns), units="ns")
        row.update(
            delay=delay,
            width=width,
            m_writes=sum(1 for x in obs.m_xfers if x[1]),
            m_xfers=len(obs.m_xfers),
            s_done=list(obs.s_done),
            ack_s_seen=obs.ack_s_seen,
            in_rst_seen=obs.in_rst_seen,
        )
    master.kill()
    obs.stop()
    _idle_s_side(dut)
    return row


def _long_plans(s_ns, m_ns) -> dict:
    """Pulses that follow DS-CDC-109. The first three start before any s_clk edge sees ack_q; the
    last starts after the source has captured the acknowledge."""
    long_w = LONG_PULSE_PERIODS * max(s_ns, m_ns)
    return {
        "early": lambda d: (1, long_w) if d >= 2 else None,
        "mid": lambda d: (max(1, d // 2), long_w) if d >= 2 else None,
        "last": lambda d: (d - 1, long_w) if d >= 2 else None,
        "late": lambda d: (d + 2 * s_ns + 1, long_w),
    }


def _narrow_plans() -> dict:
    """Pulses shorter than one s_clk period that end before the next s_clk edge after ack_q rises.
    No s_clk edge sees ack_q high, and none samples the pulse."""
    return {
        "w1_p1": lambda d: (1, 1) if d >= 3 else None,
        "w1_wide": lambda d: (1, d - 2) if d >= 3 else None,
        "late_p1": lambda d: (d - 2, 1) if d >= 3 else None,
    }


async def _sweep(dut, kind) -> list:
    """Run the pulse sweep once for the whole file. Tests of the same kind share its rows."""
    if kind not in _SWEEP_CACHE:
        rows = []
        for s_ns, m_ns, gaps in _ALIGNMENTS:
            plans = _long_plans(s_ns, m_ns) if kind == "long" else _narrow_plans()
            for gap in gaps:
                for name, plan in plans.items():
                    row = await _ack_window_experiment(dut, s_ns, m_ns, gap, plan)
                    row["plan"] = name
                    rows.append(row)
        _SWEEP_CACHE[kind] = rows
        _log_rows(dut, f"pulse sweep '{kind}' ({len(rows)} points)", rows)
    return _SWEEP_CACHE[kind]


# --- B1. An error response after a completed write ---------------------------------------------

@cocotb.test(expect_fail=True)
async def test_b1_no_error_completion_after_completed_write(dut):
    """Asserts: an errored request must not have written the destination (DS-CDC-102,
    DS-CDC-103). Stimulus: m_rst_n_i pulses low, as DS-CDC-109 asks, a short time after ack_q
    rises on the m side and before any s_clk edge samples it, at four clock ratios.

    expect_fail: the review reads that the source then sees only the reset status, returns
    s_pslverr_o=1, and the write has already happened. The failure message lists the points.
    If this test passes, the reading was wrong or the RTL changed."""
    rows = await with_timeout(_sweep(dut, "long"), 1000, "us")
    bad = [r for r in rows if not r["skipped"] and r["m_writes"] >= 1 and _err_count(r) >= 1]
    assert not bad, (
        f"{len(bad)} point(s) returned an error for a request whose write completed on the m_* "
        "face: " + "; ".join(_fmt_row(r) for r in bad[:6])
    )


async def _reset_before_access_experiment(dut, s_ns, m_ns) -> dict:
    ctx = await _setup(dut, s_ns, m_ns, wait_states=40)
    obs = _Observer(dut).start()
    addr = 0xE40
    ctx.responder.mem[addr] = 0x0BAD0BAD
    master = cocotb.start_soon(ctx.s_master.write(addr, 0xC0DE0001))
    for _ in range(400):
        await RisingEdge(dut.m_clk)
        await ReadOnly()
        if int(dut.m_penable.value):
            break
    else:
        raise RuntimeError("harness: the destination never reached the ACCESS phase")
    await RisingEdge(dut.m_clk)
    dut.m_rst_n.value = 0
    for _ in range(120):
        await RisingEdge(dut.s_clk)
        if obs.s_done:
            break
    await Timer(30 * max(s_ns, m_ns), units="ns")
    row = {
        "ratio": (s_ns, m_ns),
        "s_done": list(obs.s_done),
        "m_xfers": len(obs.m_xfers),
        "completed": ctx.responder.completed,
        "mem": ctx.responder.mem.get(addr),
    }
    master.kill()
    obs.stop()
    _idle_s_side(dut)
    return row


async def _b1_control_reset_before_access_body(dut):
    for s_ns, m_ns in _B4_RATIOS:
        r = await _reset_before_access_experiment(dut, s_ns, m_ns)
        tag = f"s/m={s_ns}/{m_ns}"
        assert len(r["s_done"]) == 1, f"{tag}: expected one completion, got {len(r['s_done'])}"
        assert r["s_done"][0][1] == 1, f"{tag}: a reset before the access must give s_pslverr_o=1"
        assert r["m_xfers"] == 0 and r["completed"] == 0, f"{tag}: a transfer reached the m_* face"
        assert r["mem"] == 0x0BAD0BAD, f"{tag}: the destination memory changed"
    dut._log.info("B1 control: reset before the destination access gives an error and no write")


@cocotb.test()
async def test_b1_control_reset_before_access_errors_without_write(dut):
    """Companion of the B1 test. A reset that arrives before the destination completes its access
    must give an error and no write. This proves that the m_* face monitor and the error check
    can both see their events. Ratios 4/9, 18/4, 10/10 and 7/11."""
    await with_timeout(_b1_control_reset_before_access_body(dut), 200, "us")


@cocotb.test()
async def test_b1_control_window_reached_and_late_reset_clean(dut):
    """Companion of the B1 test and of the B3 test. Proves, without asserting the B1 outcome:
    (1) the stimulus reaches the window: for the early, mid and last plans no s_clk edge sees
    ack_s, the write completes once on the m_* face, and the source completes the request once;
    (2) a reset after the source captured the acknowledge gives an okay response and one write."""
    rows = await with_timeout(_sweep(dut, "long"), 1000, "us")
    live = [r for r in rows if not r["skipped"]]
    window = [r for r in live if r["plan"] in ("early", "mid", "last")]
    assert window, "the stimulus never reached the window before an s_clk edge samples ack_q"
    for r in live:
        tag = _fmt_row(r)
        assert len(r["s_done"]) == 1, f"the source must complete once: {tag}"
        assert r["m_writes"] == 1, f"the m_* face must show exactly one write: {tag}"
    for r in window:
        assert not r["ack_s_seen"], f"ack_s rose although no s_clk edge saw ack_q: {_fmt_row(r)}"
    late = [r for r in live if r["plan"] == "late"]
    assert late, "no point of the late plan ran"
    for r in late:
        assert r["ack_s_seen"] and _err_count(r) == 0, f"late reset must be clean: {_fmt_row(r)}"
    dut._log.info(
        f"B1 window reached at {len(window)} points; {len(late)} late-reset points are clean"
    )


# --- B2. No timeout when the destination clock stops --------------------------------------------

async def _stall_experiment(dut, s_ns, m_ns, variant) -> dict:
    """Stop m_clk (variant idle: before the request, req_q: when req_q rises, m_access: when the
    destination is in its ACCESS phase), wait STALL_BOUND_S_CYCLES, restart m_clk, then run a
    second write. Returns what the monitors saw."""
    ctx = await _setup(dut, s_ns, m_ns)
    obs = _Observer(dut).start()
    addr, data = 0xF00, 0x5A5A0001
    addr2, data2 = 0xF04, 0x5A5A0002

    # Reference: one transfer with both clocks running.
    master = cocotb.start_soon(ctx.s_master.write(0xE80, 0x11110000))
    normal_cycles = 0
    while not obs.s_done:
        await RisingEdge(dut.s_clk)
        normal_cycles += 1
        if normal_cycles > STALL_BOUND_S_CYCLES:
            raise RuntimeError("harness: the reference transfer did not complete")
    await ClockCycles(dut.s_clk, 4)
    n0, x0 = len(obs.s_done), len(obs.m_xfers)

    def freeze() -> None:
        ctx.m_clk_task.kill()
        dut.m_clk.value = 0

    if variant == "idle":
        freeze()
        await Timer(1, units="step")
        master2 = cocotb.start_soon(ctx.s_master.write(addr, data))
    else:
        master2 = cocotb.start_soon(ctx.s_master.write(addr, data))
        clk, probe = (
            (dut.s_clk, dut.u_dut.req_q) if variant == "req_q" else (dut.m_clk, dut.m_penable)
        )
        for _ in range(200):
            await RisingEdge(clk)
            await ReadOnly()
            if int(probe.value):
                break
        else:
            raise RuntimeError(f"harness: the stop condition of variant {variant} never held")
        await Timer(1, units="step")
        freeze()
        await Timer(1, units="step")

    stall_done = None
    for cyc in range(STALL_BOUND_S_CYCLES):
        await RisingEdge(dut.s_clk)
        await ReadOnly()
        if int(dut.s_pready.value):
            stall_done = cyc + 1
            break
    await Timer(1, units="step")

    ctx.m_clk_task = cocotb.start_soon(Clock(dut.m_clk, m_ns, units="ns").start())
    _active_tasks.append(ctx.m_clk_task)
    restart_done = None
    if stall_done is None:
        for cyc in range(RESTART_BOUND_S_CYCLES):
            await RisingEdge(dut.s_clk)
            await ReadOnly()
            if int(dut.s_pready.value):
                restart_done = cyc + 1
                break
        await Timer(1, units="step")

    # Let the first master return the bus to idle before a second write starts.
    await ClockCycles(dut.s_clk, 4)
    master3 = cocotb.start_soon(ctx.s_master.write(addr2, data2))
    for _ in range(200):
        await RisingEdge(dut.s_clk)
        if len(obs.s_done) >= n0 + 2:
            break
    await Timer(20 * max(s_ns, m_ns), units="ns")
    row = {
        "ratio": (s_ns, m_ns),
        "variant": variant,
        "normal_cycles": normal_cycles,
        "stall_done": stall_done,
        "restart_done": restart_done,
        "events": list(obs.s_done[n0:]),
        "m_new": list(obs.m_xfers[x0:]),
        "mem": (ctx.responder.mem.get(addr), ctx.responder.mem.get(addr2)),
    }
    for task in (master, master2, master3):
        task.kill()
    obs.stop()
    _idle_s_side(dut)
    return row


async def _stall_rows(dut) -> list:
    if "rows" not in _STALL_CACHE:
        rows = []
        for s_ns, m_ns in ((10, 10), (18, 4), (4, 9)):
            for variant in ("idle", "req_q", "m_access"):
                rows.append(await _stall_experiment(dut, s_ns, m_ns, variant))
        _STALL_CACHE["rows"] = rows
        for r in rows:
            dut._log.info(
                f"B2 s/m={r['ratio'][0]}/{r['ratio'][1]} stop={r['variant']:<8} "
                f"reference_cycles={r['normal_cycles']} stall_done={r['stall_done']} "
                f"restart_done={r['restart_done']} m_new={len(r['m_new'])}"
            )
    return _STALL_CACHE["rows"]


@cocotb.test(expect_fail=True)
async def test_b2_stalled_destination_clock_completes_within_bound(dut):
    """Asserts: with m_rst_n_i high and m_clk_i stopped, the source must still complete the
    request within STALL_BOUND_S_CYCLES cycles of s_clk_i, because it must not wait for a
    destination that cannot answer. The bound is about 8 to 30 times the reference latency at the
    ratios used. Stop points: before the request, when req_q rises, in the destination ACCESS
    phase. Ratios 10/10, 18/4 and 4/9.

    expect_fail: the review reads that S_REQ exits only on ack_s, a request that was never
    forwarded, or a destination reset, so s_pready_o stays low until the clock runs again."""
    rows = await with_timeout(_stall_rows(dut), 1000, "us")
    stalled = [r for r in rows if r["stall_done"] is None]
    assert not stalled, (
        f"s_pready_o stayed low for {STALL_BOUND_S_CYCLES} s_clk cycles with m_clk stopped at "
        + ", ".join(f"s/m={r['ratio'][0]}/{r['ratio'][1]} stop={r['variant']}" for r in stalled)
    )


@cocotb.test()
async def test_b2_control_stall_then_restart_completes_once(dut):
    """Companion of the B2 test. Documents the present stall-then-resume behaviour and proves the
    bound is long: the reference transfer finishes in less than a quarter of the bound. After the
    clock restarts, the stalled request completes with an okay response, the m_* face shows one
    transfer with the right address and data, and a second write completes the same way. If a
    timeout is added, change this test together with the B2 test."""
    rows = await with_timeout(_stall_rows(dut), 1000, "us")
    for r in rows:
        tag = f"s/m={r['ratio'][0]}/{r['ratio'][1]} stop={r['variant']}"
        assert r["normal_cycles"] * 4 <= STALL_BOUND_S_CYCLES, (
            f"{tag}: reference latency {r['normal_cycles']} cycles is not short against the bound"
        )
        assert len(r["events"]) == 2, f"{tag}: expected two completions, got {len(r['events'])}"
        assert [e[1] for e in r["events"]] == [0, 0], f"{tag}: a completion carried s_pslverr_o"
        if r["stall_done"] is None:
            assert r["restart_done"] is not None, f"{tag}: no completion after the restart"
        xfers = [(x[1], x[2], x[3]) for x in r["m_new"]]
        assert xfers == [(1, 0xF00, 0x5A5A0001), (1, 0xF04, 0x5A5A0002)], (
            f"{tag}: unexpected transfers on the m_* face {xfers}"
        )
        assert r["mem"] == (0x5A5A0001, 0x5A5A0002), f"{tag}: destination memory {r['mem']}"
    dut._log.info("B2 control: stalled requests complete once after the clock restarts")


# --- B3. A short m_rst_n_i pulse can repeat a transfer -----------------------------------------

@cocotb.test(expect_fail=True)
async def test_b3_short_reset_pulse_makes_one_transfer(dut):
    """Asserts: one request makes exactly one transfer on the m_* face (DS-CDC-106), also when
    m_rst_n_i pulses low for less than one s_clk period. That pulse breaks DS-CDC-109, so the
    review calls it a caller error; the owner asked to measure it. Sweep: pulse position and
    width, 3 plans, four clock ratios, several alignments. Every point lies inside the window
    where no s_clk edge sees ack_q and none samples the pulse.

    expect_fail: the review reads that the reset clears the destination but the source still
    holds req_q, so the destination runs the same request again after the release."""
    rows = await with_timeout(_sweep(dut, "narrow"), 1000, "us")
    live = [r for r in rows if not r["skipped"]]
    dup = [r for r in live if r["m_xfers"] > 1]
    dut._log.info(f"B3: {len(dup)} of {len(live)} short-pulse points repeated the transfer")
    for r in dup:
        dut._log.info("  repeated: " + _fmt_row(r))
    assert not dup, (
        f"{len(dup)} of {len(live)} points made more than one m_* transfer for one request: "
        + "; ".join(_fmt_row(r) for r in dup[:6])
    )


@cocotb.test()
async def test_b3_control_compliant_pulse_makes_one_transfer(dut):
    """Companion of the B3 test. A pulse of m_rst_n_i that follows DS-CDC-109 never repeats a
    transfer: at every point of the long sweep (pulse start before and after the acknowledge
    reaches the source) the m_* face shows exactly one transfer and the source completes once."""
    rows = await with_timeout(_sweep(dut, "long"), 1000, "us")
    live = [r for r in rows if not r["skipped"]]
    assert live, "no point of the long sweep ran"
    for r in live:
        tag = _fmt_row(r)
        assert r["m_xfers"] == 1, f"a compliant pulse changed the transfer count: {tag}"
        assert len(r["s_done"]) == 1, f"the source must complete once: {tag}"
    dut._log.info(f"B3 control: {len(live)} compliant-pulse points made one transfer each")


@cocotb.test()
async def test_b3_control_short_pulse_window_reached(dut):
    """Companion of the B3 test. Proves, without asserting the B3 outcome, that the short pulses
    were not sampled by the status synchroniser (m_in_rst_s never rose), that the source
    completed every request once, and that the sweep has points. A transfer count of one or of
    two is accepted here."""
    rows = await with_timeout(_sweep(dut, "narrow"), 1000, "us")
    live = [r for r in rows if not r["skipped"]]
    assert live, "no short-pulse point fitted before the next s_clk edge"
    for r in live:
        tag = _fmt_row(r)
        assert not r["in_rst_seen"], f"the short pulse was sampled by the s domain: {tag}"
        assert len(r["s_done"]) == 1, f"the source must complete once: {tag}"
        assert 1 <= r["m_xfers"] <= 2, f"unexpected transfer count: {tag}"
    dut._log.info(f"B3 control: {len(live)} short-pulse points, none sampled by the s domain")


# --- B4. Worst-case latency of the bounds of DS-CDC-102 and DS-CDC-103 --------------------------

async def _measure_ds102(dut, s_ns, m_ns) -> list:
    """Edges of s_clk from the SETUP edge until s_pready_o reads 1, with the destination reset."""
    ctx = await _setup(dut, s_ns, m_ns)
    obs = _Observer(dut).start()
    dut.m_rst_n.value = 0
    await ClockCycles(dut.s_clk, int(dut.sync_stages_to_s_o.value) + 3)
    if int(dut.u_dut.m_rst_n_s.value) != 0:
        raise RuntimeError("harness: the s domain does not see the destination in reset")
    counts = []
    for rep in range(2):
        master = cocotb.start_soon(ctx.s_master.read(0x80 + 4 * rep))
        edges = None
        for _ in range(40):
            await RisingEdge(dut.s_clk)
            await ReadOnly()
            assert int(dut.m_psel.value) == 0, "m_psel rose while the destination is in reset"
            if edges is None:
                if int(dut.u_dut.s_state_q.value) == S_REQ:
                    edges = 0
            else:
                edges += 1
            if edges is not None and int(dut.s_pready.value):
                break
        else:
            raise RuntimeError("harness: no completion within 40 s_clk edges")
        assert int(dut.s_pslverr.value) == 1, "forced completion must carry s_pslverr_o=1"
        counts.append(edges)
        await RisingEdge(dut.s_clk)
        _data, ok = await master
        assert ok is False, "the read must report pslverr"
    assert not obs.m_xfers, "a transfer reached the m_* face for a request made in reset"
    return counts


@cocotb.test()
async def test_b4_ds102_latency_bound(dut):
    """Measures DS-CDC-102: s_pready_o and s_pslverr_o read 1 after at most DS102_MAX_EDGES
    rising edges of s_clk that follow the SETUP edge, with m_rst_n_i low and seen by the source.
    Ratios 4/9, 18/4, 10/10 and 7/11. The measured maximum of each ratio is logged."""
    for s_ns, m_ns in _B4_RATIOS:
        counts = await with_timeout(_measure_ds102(dut, s_ns, m_ns), 200, "us")
        dut._log.info(
            f"B4 DS-CDC-102 s/m={s_ns}/{m_ns}: edges after SETUP {counts}, max {max(counts)}, "
            f"DS bound {DS102_MAX_EDGES}"
        )
        assert max(counts) <= DS102_MAX_EDGES, (
            f"s/m={s_ns}/{m_ns}: forced completion took {max(counts)} edges, DS bound is "
            f"{DS102_MAX_EDGES}"
        )


async def _measure_ds103(dut, s_ns, m_ns) -> list:
    """Edges of s_clk from the fall of m_rst_n_i until s_pready_o reads 1, for a forwarded request
    that the destination never answers. The reset falls at three offsets inside one s period."""
    ctx = await _setup(dut, s_ns, m_ns, wait_states=1000)
    counts = []
    for offset in sorted({0, s_ns // 2, s_ns - 1}):
        master = cocotb.start_soon(ctx.s_master.read(0x40))
        for _ in range(200):
            await RisingEdge(dut.m_clk)
            await ReadOnly()
            if int(dut.m_penable.value):
                break
        else:
            raise RuntimeError("harness: the destination never reached the ACCESS phase")
        await RisingEdge(dut.s_clk)
        if offset:
            await Timer(offset, units="ns")
        dut.m_rst_n.value = 0
        edges = 0
        for _ in range(40):
            await RisingEdge(dut.s_clk)
            edges += 1
            await ReadOnly()
            if int(dut.s_pready.value):
                break
        else:
            raise RuntimeError("harness: no completion within 40 s_clk edges")
        assert int(dut.s_pslverr.value) == 1, "completion after a destination reset needs an error"
        counts.append(edges)
        await RisingEdge(dut.s_clk)
        dut.m_rst_n.value = 1
        _data, ok = await master
        assert ok is False, "the read must report pslverr"
        n = _post_reset_recovery_cycles(dut)
        await ClockCycles(dut.s_clk, n)
        await ClockCycles(dut.m_clk, n)
    return counts


@cocotb.test()
async def test_b4_ds103_latency_bound(dut):
    """Measures DS-CDC-103: after m_rst_n_i falls, a forwarded request completes with an error
    within SYNC_STAGES_TO_S+2 rising edges of s_clk. The log gives the measured maximum of each
    ratio.
    Ratios 4/9, 18/4, 10/10 and 7/11, with the reset at three offsets inside one s period."""
    stages = int(dut.sync_stages_to_s_o.value)
    for s_ns, m_ns in _B4_RATIOS:
        counts = await with_timeout(_measure_ds103(dut, s_ns, m_ns), 400, "us")
        dut._log.info(
            f"B4 DS-CDC-103 s/m={s_ns}/{m_ns}: edges after the reset falls {counts}, "
            f"max {max(counts)}, DS bound {stages + 2}"
        )
        assert min(counts) >= 1, f"s/m={s_ns}/{m_ns}: completion before any s_clk edge"
        assert max(counts) <= stages + 2, (
            f"s/m={s_ns}/{m_ns}: completion took {max(counts)} edges, DS bound is {stages + 2}"
        )
