"""
test_apb_cdc_bridge_skew.py -- the reset-race sweeps of test_apb_cdc_bridge.py with the settling-delay
injector of cdc_sync switched on for u_ack_sync and u_m_alive_dly_sync (tb_apb_cdc_bridge_skew.sv).
Each synchroniser can then take one s_clk_i cycle more than its nominal latency, so the response of a
completed transfer and the destination reset status can arrive on the same edge or in the wrong order
by one cycle. The bridge must still return the real response.
Run: make -C tb/cocotb/soc apb_cdc_bridge_skew
Doc: tm:suite:soc-test-apb-cdc-bridge
"""

import cocotb
from cocotb.triggers import with_timeout

import test_apb_cdc_bridge as base


@cocotb.test()
async def test_skew_completed_write_returns_okay(dut):
    """The B1 sweep with one cycle of synchroniser skew: every write that completed returns okay."""
    rows = await with_timeout(base._sweep(dut, "long"), 1500, "us")
    live = [r for r in rows if not r["skipped"]]
    assert live
    bad = [r for r in live if r["m_writes"] >= 1 and base._err_count(r) >= 1]
    assert not bad, "; ".join(base._fmt_row(r) for r in bad[:6])
    for r in live:
        assert len(r["s_done"]) == 1 and r["m_writes"] == 1, base._fmt_row(r)


@cocotb.test()
async def test_skew_completed_read_returns_real_data(dut):
    """The B5 sweep with one cycle of synchroniser skew: no okay completion carries wrong data, and a
    read that completed before the reset returns the data."""
    rows = await with_timeout(base._read_sweep(dut), 2500, "us")
    live = [r for r in rows if not r["skipped"]]
    assert live
    for r in live:
        assert not base._bad_okay_read(r), base._fmt_read_row(r)
        assert base._err_count(r) == 0 and r["s_done"][0][2] == base.READ_DATA, base._fmt_read_row(r)


@cocotb.test()
async def test_skew_short_pulses_make_one_transfer(dut):
    """The B3 sweep with skew: one transfer per request, one okay completion."""
    rows = await with_timeout(base._sweep(dut, "narrow"), 1500, "us")
    live = [r for r in rows if not r["skipped"]]
    assert live
    for r in live:
        assert r["m_xfers"] == 1 and len(r["s_done"]) == 1 and base._err_count(r) == 0, base._fmt_row(r)
