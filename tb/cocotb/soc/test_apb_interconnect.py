"""
test_apb_interconnect.py -- Phase 6 groundwork cocotb verification for apb_interconnect
(rtl/soc/apb_interconnect.sv).
DUT: tb_apb_interconnect (standalone wrapper; its header has the flattened-port rationale and the
OVERLAP_TEST knob). apb_interconnect is PURELY COMBINATIONAL: no clock or reset port. The suite
starts no clock and does not use bfm/apb4_master.py (its SETUP/ACCESS protocol needs `await
RisingEdge(clock)`). It drives the flattened inputs and settles with a plain `Timer` before
sampling. There are no wait states: pready_o is combinationally 1 in every reachable state.
N_SLAVES and OVERLAP_TEST are Verilator `-G` elaboration overrides (see the `apb_interconnect`
Makefile target). The Makefile passes them to this module in two environment variables:
APB_IC_N_SLAVES (default 8) and APB_IC_OVERLAP ("1" for the OVERLAP_TEST=1 build, "0" otherwise).
N_SLAVES changes SEL_W, IDXW and the array sizes, so each value needs its own elaboration. The
target runs THIS module once per N_SLAVES in {1, 2, 7, 8, 9, 13, 14, 15, 16, 17}, each in its own
SIM_BUILD directory (stale-Verilator-cache hazard), plus one build at N_SLAVES=2 with
OVERLAP_TEST=1. The repetition IS the sweep coverage: SEL_W/IDXW differ at powers of two, so
1/2/8/16 bracket the WIDTHTRUNC trap at 8.
Tests: test_idle, test_basic_decode and test_response_mux (skipped under OVERLAP_TEST),
test_unmapped_slverr (the first address past the last window: pready=1, pslverr=1, prdata=0, no
psel), test_write_fanout_reaches_every_slave, test_first_match_wins (OVERLAP_TEST=1 only: the lowest
index wins).
Run: make -C tb/cocotb/soc apb_interconnect
Doc: tm:suite:soc-test-apb-interconnect
"""

import os
import sys
from pathlib import Path

import cocotb
from cocotb.triggers import Timer

_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# ---------------------------------------------------------------------------
# Elaboration parameters for THIS build (set by the Makefile; see module docstring)
# ---------------------------------------------------------------------------
N_SLAVES = int(os.environ.get("APB_IC_N_SLAVES", "8"))
OVERLAP = os.environ.get("APB_IC_OVERLAP", "0") == "1"

ADDR_W = 32
DW = 32
SW = 4
SLV_WINDOW = 0x1000  # must match tb_apb_interconnect.sv's SLV_WINDOW default

def slv_base(i: int) -> int:
    return i * SLV_WINDOW


def slv_limit(i: int) -> int:
    if OVERLAP and i == 0 and N_SLAVES >= 2:
        return 2 * SLV_WINDOW - 1
    return i * SLV_WINDOW + (SLV_WINDOW - 1)


UNMAPPED_ADDR = N_SLAVES * SLV_WINDOW  # first byte past the last generated window


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _idle(dut) -> None:
    dut.psel.value = 0
    dut.penable.value = 0
    dut.pwrite.value = 0
    dut.paddr.value = 0
    dut.pwdata.value = 0
    dut.pstrb.value = 0x0
    dut.pready_i_flat.value = 0
    dut.pslverr_i_flat.value = 0
    dut.prdata_i_flat.value = 0


async def _drive_access(dut, addr: int) -> None:
    """Drive a full SETUP+ACCESS phase to `addr` (read-shaped: pwrite=0) and settle."""
    dut.psel.value = 1
    dut.penable.value = 0
    dut.pwrite.value = 0
    dut.paddr.value = addr
    dut.pwdata.value = 0
    dut.pstrb.value = 0x0
    await Timer(1, units="ns")
    dut.penable.value = 1
    await Timer(1, units="ns")


def _pack_data(values: list) -> int:
    """Pack a list of N_SLAVES DW-bit values into one flat vector (chunk i = values[i])."""
    v = 0
    for idx, val in enumerate(values):
        v |= (val & 0xFFFF_FFFF) << (idx * DW)
    return v


def _pack_bits(values: list) -> int:
    """Pack a list of N_SLAVES 1-bit values into one flat vector (bit i = values[i])."""
    v = 0
    for idx, val in enumerate(values):
        v |= (val & 1) << idx
    return v


def _drive_slave_responses(dut, prdata: list, pready: list, pslverr: list) -> None:
    """Drive all N_SLAVES slaves' flat response inputs from Python-side lists in one shot.

    Deliberately does NOT read back dut.*_i_flat.value and read-modify-write it per slave:
    a cocotb `.value =` write is not visible to a same-delta-cycle `.value` read (it is only
    applied at the next simulation time step), so composing the flat vector in Python state
    and writing each of the three signals exactly once avoids that race entirely.
    """
    dut.prdata_i_flat.value = _pack_data(prdata)
    dut.pready_i_flat.value = _pack_bits(pready)
    dut.pslverr_i_flat.value = _pack_bits(pslverr)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
@cocotb.test()
async def test_idle(dut):
    """psel=0 -> pready=1, pslverr=0, prdata=0, and no slave selected."""
    _idle(dut)
    await Timer(1, units="ns")

    assert int(dut.pready.value) == 1, "idle bus must report pready=1"
    assert int(dut.pslverr.value) == 0, "idle bus must report pslverr=0"
    assert int(dut.prdata.value) == 0, "idle bus must report prdata=0"
    assert int(dut.psel_o_flat.value) == 0, "idle bus must not select any slave"


@cocotb.test(skip=OVERLAP)
async def test_basic_decode(dut):
    """Each slave's own [BASE, LIMIT] window selects exactly that psel_o_flat bit."""
    _idle(dut)
    await Timer(1, units="ns")

    for i in range(N_SLAVES):
        for addr in (slv_base(i), (slv_base(i) + slv_limit(i)) // 2, slv_limit(i)):
            await _drive_access(dut, addr)
            got = int(dut.psel_o_flat.value)
            expected = 1 << i
            assert got == expected, (
                f"N_SLAVES={N_SLAVES}: addr=0x{addr:x} (slave {i}'s window) selected "
                f"psel_o_flat=0x{got:x}, expected exactly bit {i} (0x{expected:x})"
            )
            _idle(dut)
            await Timer(1, units="ns")


@cocotb.test(skip=OVERLAP)
async def test_response_mux(dut):
    """prdata_o/pready_o/pslverr_o come from the selected slave only."""
    _idle(dut)
    await Timer(1, units="ns")

    for i in range(N_SLAVES):
        # Unique, slave-specific pattern so a wrong-index mux is caught immediately.
        pat_data = (0xA5A5_0000 | i) & 0xFFFF_FFFF
        prdata_vals = [0] * N_SLAVES
        pready_vals = [0] * N_SLAVES
        pslverr_vals = [0] * N_SLAVES
        for j in range(N_SLAVES):
            if j == i:
                prdata_vals[j], pready_vals[j], pslverr_vals[j] = pat_data, 1, 0
            else:
                # Deliberately conflicting values on every other slave so a
                # mis-selected mux would read back wrong.
                prdata_vals[j], pready_vals[j], pslverr_vals[j] = 0xDEAD_0000 | j, 0, 1
        _drive_slave_responses(dut, prdata_vals, pready_vals, pslverr_vals)

        addr = (slv_base(i) + slv_limit(i)) // 2
        await _drive_access(dut, addr)

        assert int(dut.prdata.value) == pat_data, (
            f"N_SLAVES={N_SLAVES}: slave {i} selected but prdata_o="
            f"0x{int(dut.prdata.value):x}, expected 0x{pat_data:x}"
        )
        assert int(dut.pready.value) == 1, f"N_SLAVES={N_SLAVES}: slave {i} pready_o mismatch"
        assert int(dut.pslverr.value) == 0, f"N_SLAVES={N_SLAVES}: slave {i} pslverr_o mismatch"

        _idle(dut)
        await Timer(1, units="ns")


@cocotb.test()
async def test_unmapped_slverr(dut):
    """psel=1 at an address no slave claims -> pready=1, pslverr=1, prdata=0 (not a hang)."""
    _idle(dut)
    await Timer(1, units="ns")

    await _drive_access(dut, UNMAPPED_ADDR)

    assert int(dut.pready.value) == 1, "unmapped access must still report pready=1 (not a hang)"
    assert int(dut.pslverr.value) == 1, "unmapped access must report pslverr=1 (DECERR equivalent)"
    assert int(dut.prdata.value) == 0, "unmapped access must report prdata=0"
    assert int(dut.psel_o_flat.value) == 0, "unmapped access must not select any slave"


@cocotb.test(skip=not OVERLAP)
async def test_first_match_wins(dut):
    """Overlapping windows: the lowest matching index wins.

    Only elaborated when OVERLAP_TEST=1 (N_SLAVES=2): slave 0's window is deliberately extended
    to also cover slave 1's entire normal window. An address inside slave 1's own
    [BASE[1], LIMIT[1]] range -- which now also falls inside slave 0's extended range -- must
    select slave 0 (index order, not window order).
    """
    assert N_SLAVES >= 2, "test_first_match_wins requires the N_SLAVES=2 OVERLAP_TEST build"

    _idle(dut)
    await Timer(1, units="ns")

    addr = slv_base(1) + 0x10  # inside slave 1's normal window AND slave 0's extended window
    await _drive_access(dut, addr)

    got = int(dut.psel_o_flat.value)
    assert got == 0b01, (
        f"overlapping addr=0x{addr:x} selected psel_o_flat=0b{got:b}, "
        "expected exactly bit 0 (first-match / lowest-index wins)"
    )


@cocotb.test(skip=OVERLAP)
async def test_write_fanout_reaches_every_slave(dut):
    """pwdata/pstrb/pwrite/penable/paddr are broadcast to all slaves; only psel_o is per-slave.

    The per-slave copies are read straight from the DUT's unpacked output arrays
    (tb_apb_interconnect.{penable,pwrite,paddr,pwdata,pstrb}_o_arr[i]); the wrapper's scalar ports
    only show element [0], which would hide a fan-out that stops short of the other slaves.
    """
    mask_d = (1 << DW) - 1
    mask_a = (1 << ADDR_W) - 1
    patterns = [
        (0xFFFF_FFFF, 0xF, 1), (0x0000_0000, 0x0, 0), (0xAAAA_AAAA, 0xA, 1),
        (0x5555_5555, 0x5, 1), (0x8000_0001, 0x9, 0), (0x1234_5678, 0x6, 1),
    ]

    def copies(arr):
        return [int(arr[j].value) for j in range(N_SLAVES)]

    _idle(dut)
    await Timer(1, units="ns")
    for i in range(N_SLAVES):
        addr = slv_base(i) + 0x14
        for data, strb, wr in patterns:
            # SETUP phase: control present, penable low.
            dut.psel.value = 1
            dut.penable.value = 0
            dut.pwrite.value = wr
            dut.paddr.value = addr
            dut.pwdata.value = data
            dut.pstrb.value = strb
            await Timer(1, units="ns")
            assert copies(dut.penable_o_arr) == [0] * N_SLAVES, "penable high on a slave in SETUP"
            dut.penable.value = 1
            await Timer(1, units="ns")
            assert int(dut.psel_o_flat.value) == 1 << i, (
                f"N_SLAVES={N_SLAVES}: psel_o_flat=0x{int(dut.psel_o_flat.value):x}, "
                f"expected only slave {i}")
            assert copies(dut.penable_o_arr) == [1] * N_SLAVES, "penable not on every slave"
            assert copies(dut.pwrite_o_arr) == [wr] * N_SLAVES, f"pwrite={wr} not on every slave"
            assert copies(dut.pwdata_o_arr) == [data & mask_d] * N_SLAVES, (
                f"slave {i} addressed, pwdata 0x{data:x} not on every slave: "
                f"{[hex(v) for v in copies(dut.pwdata_o_arr)]}")
            assert copies(dut.pstrb_o_arr) == [strb] * N_SLAVES, "pstrb not on every slave"
            assert copies(dut.paddr_o_arr) == [addr & mask_a] * N_SLAVES, "paddr not on every slave"
            # The single-element convenience ports agree with the per-slave copies.
            assert int(dut.pwdata_o.value) == data & mask_d
            assert int(dut.pstrb_o.value) == strb
            _idle(dut)
            await Timer(1, units="ns")
