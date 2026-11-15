"""
Host-side check of the reference firmware of the PMU live power-cycle test
(tb/cocotb/soc/pmu_cycle_fw/gen_pmu_cycle_hex.py). The firmware runs on the Python RV32I reference
model with plain memory in place of the registers. The check covers the two PMU rules of the
firmware: no bus access between the request for the power-down and the wake-up (DS-PMU-182), and a
write of 1 to STATUS_CLR when STATUS bit 3 is set (DS-PMU-187). It does not cover bus timing or the
cache, which only the simulation shows.
Doc: tm:suite:soc-test-soc-pmu-multiclock
"""

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent.parent
for _p in (_ROOT / "tb" / "cocotb" / "soc" / "pmu_cycle_fw", _ROOT):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import gen_pmu_cycle_hex as ref  # type: ignore[import-not-found]  # noqa: E402  # pylint: disable=import-error

from tb.models.rv32i_model import RV32IModel  # noqa: E402

DMA_CTRL_ADDR = ref.DMA_BASE + 12
PMU_STATUS_ADDR = ref.PMU_BASE + 4
PMU_STATUS_CLR_ADDR = ref.PMU_BASE + 0xC
STATUS_TIMEOUT_BIT = 0x8
MAX_STEPS = 100_000


def _run(status_value):
    """Run the firmware until it spins in a one-instruction loop or MAX_STEPS ends.
    Returns (words, labels, trace)."""
    asm = ref.Assembler()
    ref.build_firmware(asm)
    words = asm.resolve()
    cpu = RV32IModel(reset_pc=ref.ROM_BASE)
    cpu.load_program({ref.ROM_BASE + 4 * i: w for i, w in enumerate(words)})
    cpu.memory.write(PMU_STATUS_ADDR, status_value, 4)
    trace = []
    for _ in range(MAX_STEPS):
        step = cpu.step()
        trace.append(step)
        if len(trace) > 1 and step["pc"] == trace[-2]["pc"]:
            break
    return words, dict(asm.labels), trace


def _accesses(trace):
    return [
        (r["mem_addr"], r["mem_write"], r["mem_data"])
        for r in trace
        if r["mem_addr"] is not None
    ]


def _after_request(trace):
    """The accesses after the store that starts the DMA copy of the power-down request."""
    acc = _accesses(trace)
    start = [i for i, a in enumerate(acc) if a[0] == DMA_CTRL_ADDR and a[2] == 1]
    assert len(start) == 1, f"expected one DMA start store, got {len(start)}"
    return acc[start[0] + 1:]


def test_no_bus_access_between_the_request_and_the_wake_up():
    """DS-PMU-182: after the DMA start store the first access is the read of PMU STATUS that
    follows the wake-up. Nothing else, no DMA store and no data access, comes before it."""
    _words, _labels, trace = _run(0)
    after = _after_request(trace)
    assert after, "the firmware has no access after the request"
    assert after[0][:2] == (PMU_STATUS_ADDR, False), (
        f"first access after the request is {after[0]}, not the read of PMU STATUS")


def test_request_and_wait_loop_share_one_instruction_cache_line():
    """The store that starts the DMA copy and the wait loop are in one 16-byte line. The line is
    in the instruction cache when the store executes, so the wait loop makes no fetch."""
    _words, labels, trace = _run(0)
    start_pc = next(r["pc"] for r in trace if r["mem_addr"] == DMA_CTRL_ADDR and r["mem_data"] == 1)
    loop_pcs = {r["pc"] for r in trace if r["pc"] >= start_pc and r["pc"] < labels["POST"]}
    assert {pc >> 4 for pc in loop_pcs | {start_pc}} == {start_pc >> 4}, (
        f"start store 0x{start_pc:08x} and wait loop {sorted(map(hex, loop_pcs))} cross a line")
    assert labels["LOOP"] in loop_pcs


def test_status_bit_3_clear_is_written_when_the_flag_is_set():
    """DS-PMU-187: with STATUS bit 3 at 1 the firmware records the fault, then writes 1 to
    STATUS_CLR."""
    _words, _labels, trace = _run(STATUS_TIMEOUT_BIT | 0x3)
    clears = [a for a in _after_request(trace) if a[0] == PMU_STATUS_CLR_ADDR]
    assert clears == [(PMU_STATUS_CLR_ADDR, True, 1)], clears


def test_no_clear_is_written_when_the_flag_is_not_set():
    """With STATUS bit 3 at 0 the firmware does not write STATUS_CLR."""
    _words, _labels, trace = _run(0x3)
    assert [a for a in _accesses(trace) if a[0] == PMU_STATUS_CLR_ADDR] == []


def test_firmware_ends_in_a_one_instruction_loop():
    """The firmware has no EBREAK and no trap. It ends in a jump to itself."""
    _words, _labels, trace = _run(0x3)
    assert len(trace) < MAX_STEPS, "the firmware never reached its final loop"
    assert trace[-1]["pc"] == trace[-2]["pc"]
    assert not any(r["trap"] for r in trace)
