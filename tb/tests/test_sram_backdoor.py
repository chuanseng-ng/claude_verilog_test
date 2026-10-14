"""Unit tests for tb/cocotb/soc/sram_backdoor.py (bead hlrm) -- no simulator needed.

The helper resolves the SoC SRAM array across the ``sram_controller`` arms.  These tests drive it
with fake ``dut`` objects (nested ``SimpleNamespace``) so every path and the not-found error are
covered without Verilator/cocotb.  A final source scan keeps the refactor from regressing: no
SoC suite may spell the ``u_sram`` array path out again.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

_REPO = Path(__file__).resolve().parents[2]
_SOC = _REPO / "tb" / "cocotb" / "soc"
_SPEC = importlib.util.spec_from_file_location("sram_backdoor", _SOC / "sram_backdoor.py")
assert _SPEC is not None and _SPEC.loader is not None
sb = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(sb)


def _ns(**kw: Any) -> SimpleNamespace:
    return SimpleNamespace(**kw)


def _dut(u_sram: SimpleNamespace) -> SimpleNamespace:
    return _ns(u_soc=_ns(u_sram=u_sram))


def test_default_arm_path() -> None:
    """Default build: u_sram.mem is returned."""
    arr = object()
    assert sb.sram_mem(_dut(_ns(mem=arr))) is arr


def test_fpga_arm_path() -> None:
    """FPGA build: u_sram.u_fpga_mem.mem is returned."""
    arr = object()
    assert sb.sram_mem(_dut(_ns(u_fpga_mem=_ns(mem=arr)))) is arr


def test_default_path_is_tried_first() -> None:
    """Fixed order: default path wins (arms are exclusive in a real build; this pins the order)."""
    first, second = object(), object()
    dut = _dut(_ns(mem=first, u_fpga_mem=_ns(mem=second)))
    assert sb.sram_mem(dut) is first


def test_returns_handle_unwrapped() -> None:
    """The raw handle comes back, not a wrapper."""

    class Arr(list[int]):
        """Stand-in for a simulator array handle."""

    arr = Arr([1, 2, 3])
    assert sb.sram_mem(_dut(_ns(mem=arr))) is arr


@pytest.mark.parametrize(
    "dut",
    [
        _ns(),  # no u_soc at all
        _ns(u_soc=_ns()),  # no u_sram
        _dut(_ns()),  # u_sram with neither array
        _dut(_ns(u_fpga_mem=_ns())),  # FPGA wrapper without its array
    ],
    ids=["no_u_soc", "no_u_sram", "no_array", "fpga_without_mem"],
)
def test_not_found_raises_naming_every_path(dut: SimpleNamespace) -> None:
    """No resolvable path: raise, and name every path tried."""
    with pytest.raises(sb.SramBackdoorError) as exc:
        sb.sram_mem(dut)
    msg = str(exc.value)
    for path in sb.SRAM_ARRAY_PATHS:
        assert "dut." + ".".join(path) in msg


def test_sky130_macro_arm_is_not_served() -> None:
    """SRAM_SKY130-only hierarchy is refused with a message naming the arm."""
    # An elaboration that only has the macro model must fail loudly, never be guessed at.
    dut = _dut(_ns(u_sram_macro=_ns(mem=object())))
    with pytest.raises(sb.SramBackdoorError) as exc:
        sb.sram_mem(dut)
    assert "SRAM_SKY130" in str(exc.value)
    assert "u_sram_macro" in str(exc.value)


def test_error_is_a_lookup_error() -> None:
    """The not-found error is a LookupError."""
    assert issubclass(sb.SramBackdoorError, LookupError)


def test_non_attribute_errors_propagate() -> None:
    """Only a missing component moves to the next path; other failures surface."""

    class Boom:  # pylint: disable=too-few-public-methods
        """Handle whose array access fails inside the simulator."""

        @property
        def mem(self) -> Any:
            """Always fails."""
            raise RuntimeError("simulator handle failure")

    with pytest.raises(RuntimeError, match="simulator handle failure"):
        sb.sram_mem(_dut(Boom()))  # type: ignore[arg-type]


def test_custom_paths_override() -> None:
    """An explicit path list replaces the default order and is named in the error."""
    arr = object()
    dut = _ns(top=_ns(ram=arr))
    assert sb.sram_mem(dut, paths=(("top", "ram"),)) is arr
    with pytest.raises(sb.SramBackdoorError) as exc:
        sb.sram_mem(dut, paths=(("top", "nope"), ("other", "ram")))
    assert "dut.top.nope" in str(exc.value) and "dut.other.ram" in str(exc.value)


def test_no_direct_u_sram_array_reference_outside_helper() -> None:
    """Regression guard: SoC suites must go through sram_mem(), not dut.u_soc.u_sram.mem."""
    pat = re.compile(r"u_sram\s*\.\s*(u_fpga_mem|mem)\b|u_sram[\"']\s*\)?\s*,\s*[\"']mem")
    offenders: list[str] = []
    for py in sorted(_SOC.rglob("*.py")):
        if py.name == "sram_backdoor.py":
            continue
        for n, line in enumerate(py.read_text().splitlines(), 1):
            code = line.split("#", 1)[0]
            if pat.search(code):
                offenders.append(f"{py.relative_to(_REPO)}:{n}: {line.strip()}")
    assert not offenders, "direct SRAM array path (use sram_backdoor.sram_mem):\n" + "\n".join(
        offenders
    )
