"""
Host-side check of the firmware images that test_soc_pmu_multiclock.py builds in its own process
(tb/cocotb/soc/pmu_cycle_fw/gen_pmu_confirm_fw.py). The images run on the Python RV32I reference
model with plain memory in place of the registers. The check covers the instruction sequence, the
addresses and the marker order. It does not cover bus timing or the cache, which only the
simulation shows.
Doc: tm:suite:soc-test-soc-pmu-multiclock
"""

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent.parent
for _p in (_ROOT / "tb" / "cocotb" / "soc" / "pmu_cycle_fw", _ROOT):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import gen_pmu_confirm_fw as cfw  # noqa: E402  # pylint: disable=import-error

from tb.models.rv32i_model import RV32IModel  # noqa: E402

GPU_REG = cfw.GPU_BASE + cfw.GPU_OFF_KERNEL_PC
PMU_STATUS_ADDR = cfw.PMU_BASE + cfw.PMU_STATUS
PMU_CTRL_ADDR = cfw.PMU_BASE + cfw.PMU_CTRL


def _run(words, steps, mmio=None, stop_pc=None):
    cpu = RV32IModel(reset_pc=cfw.ROM_BASE)
    cpu.load_program({cfw.ROM_BASE + 4 * i: w for i, w in enumerate(words)})
    for addr, value in (mmio or {}).items():
        cpu.memory.write(addr, value, 4)
    trace = []
    for _ in range(steps):
        if stop_pc is not None and cpu.pc == stop_pc:
            break
        trace.append(cpu.step())
    return cpu, trace


def _accesses(trace):
    return [(r["mem_addr"], bool(r["mem_write"])) for r in trace if r["mem_addr"] is not None]


def test_quiet_image_makes_no_memory_access():
    """The quiet image is a two-instruction loop that makes no memory access."""
    words, labels = cfw.quiet_image()
    _cpu, trace = _run(words, 60)
    assert _accesses(trace) == [], "the quiet image must not touch memory"
    loop = labels["QUIET_LOOP"]
    pcs = [r["pc"] for r in trace[1:]]
    assert set(pcs) == {loop, loop + 4}, "the quiet loop is two instructions"
    assert not any(r["trap"] for r in trace)


def test_noisy_image_reads_the_pmu_status_register_every_pass():
    """The noisy image reads PMU STATUS in each pass of its loop and makes no other access."""
    words, labels = cfw.noisy_image()
    _cpu, trace = _run(words, 60)
    acc = _accesses(trace)
    assert acc, "the noisy image must read in a loop"
    assert set(acc) == {(PMU_STATUS_ADDR, False)}, "only reads of PMU STATUS"
    loop = labels["NOISY_LOOP"]
    assert {r["pc"] for r in trace[2:]} == {loop, loop + 4}
    assert not any(r["trap"] for r in trace)


@pytest.mark.parametrize("kind", ["read", "write"])
def test_gpu_access_image_order_and_addresses(kind):
    """The GPU access image reaches its markers in order and accesses the expected addresses."""
    words, labels = cfw.gpu_access_image(kind)
    _cpu, trace = _run(
        words, 4000, mmio={PMU_STATUS_ADDR: cfw.STATUS_GPU_OFF}, stop_pc=labels["PASS"]
    )
    pcs = [r["pc"] for r in trace]
    order = ["ON_ACCESS_DONE", "OFF_SEEN", "ACCESS_BEGIN", "ACCESS_DONE", "NEXT_DONE"]
    first = [pcs.index(labels[name]) for name in order]
    assert first == sorted(first) and len(set(first)) == len(first), (order, first)
    assert labels["FAIL"] not in pcs, "the control read back a wrong value"
    assert not any(r["trap"] for r in trace)

    begin = pcs.index(labels["ACCESS_BEGIN"])
    before = _accesses(trace[:begin])
    assert before[0:2] == [(GPU_REG, True), (GPU_REG, False)], "GPU on: write then read back"
    assert (PMU_CTRL_ADDR, True) in before
    wrote = [r for r in trace if r["mem_addr"] == PMU_CTRL_ADDR and r["mem_write"]]
    assert [r["mem_data"] for r in wrote] == [cfw.MODE_GPU_OFF]
    after = _accesses(trace[begin:])
    assert after == [(GPU_REG, kind == "write"), (PMU_STATUS_ADDR, False)], after
    if kind == "write":
        assert [r["mem_data"] for r in trace[begin:] if r["mem_addr"] == GPU_REG] == [cfw.SENTINEL]


def test_gpu_access_image_waits_for_the_off_status():
    """Negative control: with STATUS never reading the GPU-off value the image must not reach the
    access under test."""
    words, labels = cfw.gpu_access_image("read")
    _cpu, trace = _run(words, 3000, mmio={PMU_STATUS_ADDR: 0x3})
    pcs = {r["pc"] for r in trace}
    assert labels["ON_ACCESS_DONE"] in pcs
    assert labels["OFF_SEEN"] not in pcs and labels["ACCESS_BEGIN"] not in pcs
