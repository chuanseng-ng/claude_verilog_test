"""Negative controls for the SoC cocotb Makefile's content-keyed Verilator build directories.

Bead b079.  tb/cocotb/soc/Makefile derives ``SIM_BUILD`` from a sha256 of everything that
determines the compiled model, so suites with an identical model share ONE Verilator build while
anything that changes the model gets its own directory.  The danger this guards is the PR #142
class: cocotb rebuilds on VERILOG_SOURCES timestamps but not on changed defines, parameters or
tool versions, so a directory shared across a real difference silently reuses a stale ``Vtop`` and
a suite passes against the wrong model.

These tests only call ``make print-sim-build`` / ``make -n`` (no simulator run) except
``test_touching_a_source_forces_rebuild``, which runs Verilator's elaboration (not the C++ build)
on a ten-line module.  They need ``make``, ``verilator`` and ``cocotb-config`` and skip cleanly
without them, so the generic QA job (no simulator) is unaffected; the cocotb CI job runs them.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SOC_DIR = REPO_ROOT / "tb" / "cocotb" / "soc"

pytestmark = pytest.mark.skipif(
    not all(shutil.which(tool) for tool in ("make", "verilator", "cocotb-config", "g++")),
    reason="needs make, verilator, cocotb-config and g++ (the cocotb CI job provides them)",
)

# A representative multi-file source list: order is part of the key, so keep it explicit.
SRC_A = str(REPO_ROOT / "rtl" / "soc" / "axi_pkg.sv")
SRC_B = str(REPO_ROOT / "rtl" / "soc" / "soc_addr_map_pkg.sv")


def _make(
    args: list[str], root: Path, *, dry_run: bool = False
) -> subprocess.CompletedProcess[str]:
    cmd = ["make", "--no-print-directory", "-C", str(SOC_DIR), f"SIM_BUILD_ROOT={root}"]
    if dry_run:
        cmd.insert(2, "-n")
    return subprocess.run(
        cmd + args, capture_output=True, text=True, check=False, env=os.environ.copy()
    )


def _dir(root: Path, **variables: str) -> str:
    """The build directory ``make`` would use for these sub-make variables."""
    args = ["print-sim-build", "MODULE=m", "TOPLEVEL=tb_x", f"VERILOG_SOURCES={SRC_A} {SRC_B}"]
    args += [f"{key}={value}" for key, value in variables.items()]
    result = _make(args, root)
    assert result.returncode == 0, result.stderr
    line = result.stdout.strip().splitlines()[-1]
    assert line.startswith(str(root)), f"unexpected print-sim-build output: {result.stdout!r}"
    return line


def _mdir(root: Path, target: str, *extra: str) -> str:
    """The ``-Mdir`` of the Verilator invocation a dry run of ``target`` would make."""
    result = _make([target, *extra], root, dry_run=True)
    found = re.findall(r"-Mdir (\S+)", result.stdout)
    assert found, f"no verilator invocation in dry run of {target}:\n{result.stdout[-2000:]}"
    return str(found[0])


def test_key_is_deterministic(tmp_path: Path) -> None:
    """The same inputs hash to the same directory in two separate make invocations."""
    assert _dir(tmp_path) == _dir(tmp_path)


def test_runtime_only_inputs_share_a_directory(tmp_path: Path) -> None:
    """MODULE / TESTCASE / PLUSARGS never reach the compiled model, so they must not be keyed."""
    base = _dir(tmp_path)
    assert _dir(tmp_path, MODULE="another_module") == base
    assert _dir(tmp_path, TESTCASE="test_one") == base
    assert _dir(tmp_path, PLUSARGS="+some_runtime_flag=1") == base


@pytest.mark.parametrize(
    ("what", "variables"),
    [
        ("a -G parameter", {"EXTRA_ARGS": "-GADDR_W=5"}),
        ("a different -G value", {"EXTRA_ARGS": "-GADDR_W=6"}),
        ("a +define in EXTRA_ARGS", {"EXTRA_ARGS": "+define+FOO"}),
        ("a different top level", {"TOPLEVEL": "tb_y"}),
        ("a different source list", {"VERILOG_SOURCES": SRC_A}),
        ("a reordered source list", {"VERILOG_SOURCES": f"{SRC_B} {SRC_A}"}),
        ("the sky130 SRAM select", {"SRAM_TARGET": "sky130"}),
        ("coverage instrumentation", {"COVERAGE": "1"}),
        ("waveform tracing", {"VERILATOR_TRACE": "1"}),
        ("a C++ optimisation level", {"BUILD_ARGS": "OPT_FAST=-O2 OPT_SLOW=-O0"}),
    ],
)
def test_compile_time_inputs_change_the_directory(
    tmp_path: Path, what: str, variables: dict[str, str]
) -> None:
    """Negative control (a): changing anything that affects the model must change the directory."""
    assert _dir(tmp_path, **variables) != _dir(tmp_path), f"{what} did not change the build dir"


def test_coverage_directory_is_suffixed(tmp_path: Path) -> None:
    """An instrumented model must never land in an uninstrumented directory (PR #142 class)."""
    assert _dir(tmp_path, COVERAGE="1").endswith("_cov")
    assert not _dir(tmp_path).endswith("_cov")


def test_parallel_jobs_are_not_part_of_the_key(tmp_path: Path) -> None:
    """-j changes how fast the model is built, never what it is."""
    assert _dir(tmp_path, SIM_BUILD_JOBS="4") == _dir(tmp_path)


def test_tb_soc_top_suites_share_one_build(tmp_path: Path) -> None:
    """The point of the change: every full-SoC suite in soc_all_ci compiles the same model."""
    # A dry run costs ~10 s (Makefile parse + nix store lookups), so a representative subset: both
    # former -I variants (with / without rtl/soc/cdc), the plain boot path, the multi-clock path,
    # a peripheral-fabric suite and the largest integration suite.  `make soc_all_ci -n` was
    # checked for all 15 when the sharing was introduced.
    suites = [
        "soc_boot",
        "soc_periph",
        "soc_cpu_gpu",
        "soc_npu",
        "soc_multiclock_reset",
        "soc_integration",
    ]
    dirs = {suite: _mdir(tmp_path, suite) for suite in suites}
    assert len(set(dirs.values())) == 1, (
        "tb_soc_top suites no longer share one build directory; a per-suite flag crept in:\n"
        + "\n".join(f"  {suite}: {path}" for suite, path in dirs.items())
    )


def test_distinct_models_keep_distinct_directories(tmp_path: Path) -> None:
    """sram_controller default vs SRAM_TARGET=sky130 is the exact PR #142 false-pass case."""
    assert _mdir(tmp_path, "sram_controller") != _mdir(
        tmp_path, "sram_controller", "SRAM_TARGET=sky130"
    )
    assert _mdir(tmp_path, "soc_boot") != _mdir(tmp_path, "soc_pll")
    assert _mdir(tmp_path, "soc_boot") != _mdir(tmp_path, "soc_boot", "COVERAGE=1")


def test_touching_a_source_forces_rebuild(tmp_path: Path) -> None:
    """Negative control (b): staleness is still decided by cocotb's mtime rule on the sources."""
    rtl = tmp_path / "leaf.sv"
    rtl.write_text("module leaf(input logic a, output logic y);\n  assign y = ~a;\nendmodule\n")
    variables = ["MODULE=m", "TOPLEVEL=leaf", f"VERILOG_SOURCES={rtl}"]
    build_dir = Path(
        _make(["print-sim-build", *variables], tmp_path).stdout.strip().splitlines()[-1]
    )
    target = f"{build_dir}/Vtop.mk"

    first = _make([target, *variables], tmp_path)
    assert first.returncode == 0, first.stderr + first.stdout
    assert (build_dir / "Vtop.mk").exists()

    unchanged = _make([target, *variables], tmp_path, dry_run=True)
    assert "-Mdir" not in unchanged.stdout, "an up-to-date build directory must not be regenerated"

    stamp = (build_dir / "Vtop.mk").stat().st_mtime
    os.utime(rtl, (stamp + 10, stamp + 10))
    touched = _make([target, *variables], tmp_path, dry_run=True)
    assert "-Mdir" in touched.stdout, "touching an RTL source must regenerate the Verilated model"
