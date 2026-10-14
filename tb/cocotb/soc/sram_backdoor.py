"""sram_backdoor.py -- the one place that knows where the SoC SRAM array lives in simulation.

Every SoC-level cocotb suite that preloads or inspects SRAM through the Verilator
``--public-flat-rw`` hierarchy goes through :func:`sram_mem` instead of spelling the path out.
The array's hierarchical name depends on which ``sram_controller`` arm was elaborated
(rtl/soc/sram_controller.sv):

==============================  =========================================  ======================
build                           array                                      served by this helper
==============================  =========================================  ======================
default (no SRAM_SKY130/FPGA)   ``u_soc.u_sram.mem``                        yes (tried first)
``FPGA``                        ``u_soc.u_sram.u_fpga_mem.mem``             yes (tried second)
``SRAM_SKY130``                 ``u_soc.u_sram.u_sram_macro.mem`` (model)   NO -- see below
==============================  =========================================  ======================

``SRAM_SKY130`` is deliberately not served.  No SoC-level cocotb build defines it (tb/cocotb/soc
/Makefile wires ``SRAM_SKY130`` only into the standalone ``sram_controller`` unit-test target,
which has no ``u_soc``), so a path for it could not be verified against a real elaboration.  The
macro model (sim/sky130_sram_4kbyte_1rw1r_32x1024_8.sv) also launches its read data on the
negedge and sits behind a two-cycle write pipeline, so a backdoor access there would need its own
timing review before anyone trusts it.  Rather than guess, the helper raises for that build and
names every path it tried.

The returned object is the raw simulator array handle, unchanged: callers index it with
``sram_mem(dut)[word_index]`` exactly as they did with ``dut.u_soc.u_sram.mem[word_index]``.
Indexing is by 32-bit word in both served arms (``MEM_WORDS`` words of 32 bits).
"""

from __future__ import annotations

from typing import Any

# Fixed lookup order.  First path that resolves wins; the arms are mutually exclusive under the
# `ifdef in sram_controller.sv, so "first wins" never hides a second candidate in a real build.
# Paths are relative to the cocotb top-level handle (``dut``: tb_soc_top / tb_soc_pll).
SRAM_ARRAY_PATHS: tuple[tuple[str, ...], ...] = (
    ("u_soc", "u_sram", "mem"),  # default arm: flat behavioural array in sram_controller
    ("u_soc", "u_sram", "u_fpga_mem", "mem"),  # FPGA arm: fpga_sdp_ram_be inferred block RAM
)

# Documented-unsupported arm, named in the error so a failure there is self-explaining.
_UNSERVED_ARMS = (
    "SRAM_SKY130 (macro model at u_soc.u_sram.u_sram_macro.mem): not served -- no SoC-level "
    "cocotb build defines SRAM_SKY130, so the path is unverified, and the macro's read/write "
    "timing differs from the flat array"
)


class SramBackdoorError(LookupError):
    """No known SRAM array path resolved on the given DUT handle."""


def _fmt(path: tuple[str, ...]) -> str:
    return "dut." + ".".join(path)


def _resolve(root: Any, path: tuple[str, ...]) -> Any:
    """Walk ``path`` from ``root``; raises AttributeError if any component is missing."""
    node = root
    for name in path:
        node = getattr(node, name)
    return node


def sram_mem(dut: Any, paths: tuple[tuple[str, ...], ...] = SRAM_ARRAY_PATHS) -> Any:
    """Return the SoC SRAM array handle for whichever ``sram_controller`` arm was elaborated.

    Tries each entry of ``paths`` in order and returns the first that resolves.  Only a missing
    hierarchy component (``AttributeError``) moves on to the next path; any other exception from
    the simulator handle propagates untouched.  If no path resolves, raises
    :class:`SramBackdoorError` naming every path tried -- it never returns a substitute.
    """
    for path in paths:
        try:
            return _resolve(dut, path)
        except AttributeError:
            continue
    tried = ", ".join(_fmt(p) for p in paths)
    raise SramBackdoorError(
        f"SoC SRAM array not found; tried (in order): {tried}. Unserved arm: {_UNSERVED_ARMS}."
    )
