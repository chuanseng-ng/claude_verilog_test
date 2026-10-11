"""
Unit tests for the block-level launch helpers of the RTL-encoding reference model
(tb/cocotb/gpu/gpu_ref_model.py, bead 6hy6).

Contract (user decision 2026-10-11): BLOCK_X in 1..64 runs ceil(BLOCK_X/8) warps, the last of
which starts with only its valid lanes active; BLOCK_X == 0 or > 64 is a launch ERROR.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

GPU_DIR = Path(__file__).resolve().parents[1] / "cocotb" / "gpu"


def _load(name: str) -> ModuleType:
    """Load a tb/cocotb/gpu module by path (that directory is not a package)."""
    spec = importlib.util.spec_from_file_location(name, GPU_DIR / f"{name}.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(name="ref", scope="module")
def _ref_fixture() -> ModuleType:
    """gpu_asm first: gpu_ref_model imports it by bare name."""
    sys.path.insert(0, str(GPU_DIR))
    try:
        _load("gpu_asm")
        return _load("gpu_ref_model")
    finally:
        sys.path.remove(str(GPU_DIR))


@pytest.fixture(scope="module")
def asm() -> ModuleType:
    """The assembler module (the same instance gpu_ref_model decodes against)."""
    sys.path.insert(0, str(GPU_DIR))
    try:
        return _load("gpu_asm")
    finally:
        sys.path.remove(str(GPU_DIR))


def _store_tid_kernel(asm: ModuleType, out: int = 0x300) -> dict:
    """mem[out + warp*32 + lane*4] = lane + 1 for every active lane."""
    k = asm.Kernel(base_pc=0)
    k.emit(asm.vmov_tid_x(1))  # r1 = lane
    k.emit(asm.vaddi(7, 1, 1))  # r7 = lane + 1
    k.emit(asm.vaddi(2, 0, 2))
    k.emit(asm.vsll(3, 1, 2))  # r3 = lane*4
    k.emit(asm.vaddi(9, 3, out - 7))  # vst adds the data-register index (7)
    k.emit(asm.vst(7, 9, 0))
    k.emit(asm.vret())
    words: dict = k.instructions()
    return words


@pytest.mark.parametrize("block_x", [0, 65, 72, 128, 1023])
def test_illegal_block_x_is_error(ref, block_x):
    """0 and anything above 64 is a launch error in every helper."""
    assert ref.launch_is_error(block_x)
    for helper in (ref.warps_for_block, lambda b: ref.warp_lane_mask(b, 0)):
        with pytest.raises(ref.GpuLaunchError):
            helper(block_x)
    with pytest.raises(ref.GpuLaunchError):
        ref.run_block({}, block_x)


@pytest.mark.parametrize("block_x", [1, 7, 8, 9, 15, 17, 63, 64])
def test_legal_block_x_is_not_error(ref, block_x):
    """The legal range is exactly 1..64."""
    assert not ref.launch_is_error(block_x)


@pytest.mark.parametrize(
    ("block_x", "n_warps", "last_mask"),
    [
        (1, 1, 0x01),
        (7, 1, 0x7F),
        (9, 2, 0x01),
        (15, 2, 0x7F),
        (17, 3, 0x01),
        (63, 8, 0x7F),
        (64, 8, 0xFF),
    ],
)
def test_warps_and_last_warp_mask(ref, block_x, n_warps, last_mask):
    """ceil(BLOCK_X/8) warps; only the last can be partial; earlier warps are full."""
    assert ref.warps_for_block(block_x) == n_warps
    assert ref.warp_lane_mask(block_x, n_warps - 1) == last_mask
    assert all(ref.warp_lane_mask(block_x, w) == 0xFF for w in range(n_warps - 1))


@pytest.mark.parametrize("block_x", [1, 7, 9, 15, 17, 63, 64])
def test_run_block_stores_exactly_block_x_threads(ref, asm, block_x):
    """Per-warp runs with their init masks store one word per valid thread and no other."""
    out = 0x300
    # every warp writes the same 8 addresses (the kernel has no warp term), so count writes
    # through the per-warp models rather than the merged dict
    kernel = _store_tid_kernel(asm, out)
    writes = 0
    for w in range(ref.warps_for_block(block_x)):
        model = ref.GpuRefModel(warp_id=w, init_mask=ref.warp_lane_mask(block_x, w))
        stores = model.run(kernel)
        writes += len(stores)
        valid = [lane for lane in range(8) if w * 8 + lane < block_x]
        assert sorted(stores) == sorted(out + 4 * lane for lane in valid)
    assert writes == block_x


def test_masked_lanes_stay_masked_through_divergence(ref, asm):
    """BLOCK_X=9: warp 1 has one valid lane, so a branch taken by it does not diverge."""
    k = asm.Kernel(base_pc=0)
    k.emit(asm.vmov_tid_x(1))
    k.emit(asm.vaddi(4, 0, 4))
    bpc = k.pc()
    target = bpc + 32 + 4
    k.emit(asm.vblt(1, 4, bpc, target))  # lanes 0..3 taken
    while k.pc() < target:
        k.emit(asm.vret())
    k.emit(asm.vret())
    words = k.instructions()
    pushes = []
    for w in range(2):
        model = ref.GpuRefModel(warp_id=w, init_mask=ref.warp_lane_mask(9, w))
        model.run(words)
        pushes.append(model.div_pushes)
    assert pushes == [1, 0]
