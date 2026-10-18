"""Structural gate + negative controls for the PMU's registered outputs (bead ktwt).

``rtl/soc/pmu.sv`` drives ``cdc_sync`` D pins, the ASYNC clear of ``u_cpu_pmu_rst_sync`` and the
GPU async reset / isolation mux select. Those outputs must be flop Q pins: a combinational decode
of the binary ``dom_state_q`` can glitch on a multi-bit state change, and no zero-delay simulation
(Verilator, cocotb) can ever show that. ``tools/verif/check_registered_outputs.py`` therefore proves
it on the netlist (sv2v -> yosys ``proc``): every bit of each output port is driven directly by a
``$dff``-family cell.

A checker that cannot fail proves nothing, so each test below runs the real tool:

* the shipped ``pmu.sv`` passes for all ten sequencing outputs;
* for each output in turn, a mutant that re-routes just that port to the combinational next-state
  decode (``*_d``, a function of ``dom_state_q``, i.e. the pre-fix structure) must fail, and fail
  naming exactly that port;
* a missing port name is an error, not a vacuous pass.

Needs yosys and sv2v (``$YOSYS`` / ``$SV2V`` or PATH); skipped otherwise. CI runs this file with
the pinned tools and fails if anything skipped (see .github/workflows/rtl-checks.yml).
"""

# pylint: disable=missing-function-docstring  # descriptive test names

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
CHECKER = REPO / "tools" / "verif" / "check_registered_outputs.py"
PMU = REPO / "rtl" / "soc" / "pmu.sv"
REGBANK = REPO / "rtl" / "soc" / "apb4_register_bank.sv"

YOSYS = os.environ.get("YOSYS") or shutil.which("yosys")
SV2V = os.environ.get("SV2V") or shutil.which("sv2v")

pytestmark = pytest.mark.skipif(YOSYS is None or SV2V is None, reason="yosys and sv2v are required")

SIGNALS = ("clk_en", "iso_en", "rst_n", "ret_save", "ret_restore")
DOMAINS = ("cpu", "gpu")
PORTS = [f"{d}_{s}_o" for d in DOMAINS for s in SIGNALS]
DOM_INDEX = {"cpu": "DOM_CPU", "gpu": "DOM_GPU"}


def _run(pmu_src: Path, ports: list[str]) -> subprocess.CompletedProcess:
    env = dict(os.environ, YOSYS=str(YOSYS), SV2V=str(SV2V))
    return subprocess.run(
        [
            sys.executable,
            str(CHECKER),
            "--top",
            "pmu",
            "--ports",
            ",".join(ports),
            str(REGBANK),
            str(pmu_src),
        ],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


def test_shipped_pmu_outputs_are_flop_driven() -> None:
    res = _run(PMU, PORTS)
    assert res.returncode == 0, res.stdout + res.stderr
    assert "PASS, 10 port(s) all flop-driven" in res.stdout


@pytest.mark.parametrize("port", PORTS)
def test_combinational_output_is_caught(tmp_path: Path, port: str) -> None:
    """Re-route one output to the next-state decode (comb. of dom_state_q); it must fail by name."""
    dom, sig = port.split("_", 1)[0], port.split("_", 1)[1].removesuffix("_o")
    src = PMU.read_text()
    pat = re.compile(rf"(assign\s+{port}\s*=\s*){sig}_q(\[{DOM_INDEX[dom]}\];)")
    mutated, n = pat.subn(rf"\g<1>{sig}_d\g<2>", src)
    assert n == 1, f"mutation site for {port} not found exactly once (RTL idiom changed?)"
    mut = tmp_path / "pmu.sv"
    mut.write_text(mutated)
    res = _run(mut, PORTS)
    assert res.returncode == 1, res.stdout + res.stderr
    failing = {
        line.split(":")[0].split("[")[0].removeprefix("FAIL ")
        for line in res.stdout.splitlines()
        if line.startswith("FAIL ")
    }
    assert failing == {port}, f"expected only {port} to fail, got {failing}\n{res.stdout}"


def test_unknown_port_is_an_error_not_a_pass() -> None:
    res = _run(PMU, ["no_such_port_o"])
    assert res.returncode == 1, res.stdout + res.stderr
    assert "no such port" in res.stdout
