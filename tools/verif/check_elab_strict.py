#!/usr/bin/env python3
"""Strict SystemVerilog elaboration gate using pyslang (bead lvdk) - BLOCKING.

Why: Verilator and sv2v accept use-before-declare, while VCS and Xcelium reject it
(Doc: um:flow:proprietary-sim rule 6), and neither of those runs in CI.  sv2v also
accepts missing modules and undeclared names.  slang rejects all of these
(Doc: tm:dec:xezim section 5), so the defect is caught on the PR.

Every run first proves the tool still discriminates: each CONTROL must give its expected verdict
or the gate exits 2.  A gate that reports clean because it stopped detecting anything is worse
than no gate.

Scope: elaboration legality of the listed arms only.  No simulation, so no X, race, CDC or
functional coverage.  An `ifdef arm not listed in ARMS is not checked, and neither is tb/.

The macro arms need --ignore-unknown-modules because hard-macro models are not in the file lists.
That flag also hides a genuinely missing module, so it is confined to those arms; the default arms
elaborate the same RTL without it and do catch missing modules.

Exit codes: 0 clean, 1 findings, 2 a source could not be loaded or a control failed, 3 pyslang
unavailable.  Run from anywhere; paths resolve against the repository root.

usage: check_elab_strict.py [-v] [--arm NAME ...]
"""

from __future__ import annotations

import argparse
import importlib.util
import shlex
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

EXIT_OK = 0
EXIT_FINDINGS = 1
EXIT_LOAD = 2
EXIT_NO_TOOL = 3

IGNORE_UNKNOWN = "--ignore-unknown-modules"
WORKER_FLAG = "--worker"
ELAB_TIMEOUT_S = 300


@dataclass(frozen=True)
class Arm:
    """One elaboration configuration."""

    name: str
    top: str
    filelists: tuple[str, ...]
    defines: tuple[str, ...] = ()
    source_globs: tuple[str, ...] = ()
    ignore_unknown: bool = False

    def resolved_globs(self, root: Path) -> list[str]:
        """Return repo-relative sources matched by source_globs, sorted."""
        return sorted(str(p.relative_to(root)) for g in self.source_globs for p in root.glob(g))

    def args(self, root: Path) -> list[str]:
        """Return the slang command-line arguments for this arm."""
        out = ["--top", self.top]
        for filelist in self.filelists:
            out += ["-f", filelist]
        out += [f"-D{define}" for define in self.defines]
        if self.ignore_unknown:
            out.append(IGNORE_UNKNOWN)
        return out + self.resolved_globs(root)


@dataclass(frozen=True)
class Control:
    """A design with a known verdict, proving the tool still discriminates."""

    name: str
    source: str
    legal: bool


@dataclass(frozen=True)
class Result:
    """Verdict and captured tool output of one elaboration."""

    code: int
    output: str


SOC_F = "rtl/filelist/soc_top.f"
SOC_SIM_F = "rtl/filelist/soc_top_sim_models.f"

ARMS: tuple[Arm, ...] = (
    Arm("soc_default", "soc_top", (SOC_F, SOC_SIM_F)),
    Arm(
        "cpu_default",
        "rv32i_cpu_top",
        ("rtl/filelist/cpu_top.f", "rtl/filelist/cpu_top_sim_models.f"),
    ),
    Arm("gpu_default", "gpu_top", ("rtl/filelist/gpu_top.f", "rtl/filelist/gpu_top_sim_models.f")),
    Arm("soc_fpga", "soc_top", (SOC_F,), ("FPGA",), ("rtl/fpga/*.sv",)),
    Arm(
        "soc_sky130_pnr",
        "soc_top",
        (SOC_F, SOC_SIM_F),
        ("SRAM_SKY130", "__pnr__"),
        ignore_unknown=True,
    ),
    Arm(
        "soc_asap7_pnr",
        "soc_top",
        (SOC_F, SOC_SIM_F),
        ("SRAM_ASAP7", "USE_ICG_CELL", "__pnr__"),
        ignore_unknown=True,
    ),
)

_PORTS = "module top(input logic a, output logic y);\n"
CONTROLS: tuple[Control, ...] = (
    Control(
        "use_before_declare",
        _PORTS + "  assign y = w;\n  logic w;\n  assign w = a;\nendmodule\n",
        False,
    ),
    Control("missing_module", _PORTS + "  missing_mod u (.a(a), .y(y));\nendmodule\n", False),
    Control("legal", _PORTS + "  logic w;\n  assign w = a;\n  assign y = w;\nendmodule\n", True),
)


def pyslang_available() -> bool:
    """Return True if pyslang can be imported."""
    return importlib.util.find_spec("pyslang") is not None


def _worker(slang_args: list[str]) -> int:
    """Run one full compilation; slang prints its own diagnostics.

    Runs in a child process because the driver writes diagnostics straight to the C++ streams.
    """
    try:
        from pyslang.driver import CommandLineOptions, Driver  # noqa: PLC0415 - optional dependency

        driver = Driver()
        driver.addStandardArgs()
        loaded = (
            driver.parseCommandLine("slang " + shlex.join(slang_args), CommandLineOptions())
            and driver.processOptions()
            and driver.parseAllSources()
        )
        if not loaded:
            return EXIT_LOAD
        return EXIT_OK if driver.runFullCompilation(False) else EXIT_FINDINGS
    except Exception as exc:  # pylint: disable=broad-exception-caught
        # An uncaught exception would exit 1, which is the findings code.
        print(f"worker crashed: {exc!r}", file=sys.stderr)
        return EXIT_LOAD


def elaborate(slang_args: list[str]) -> Result:
    """Elaborate in a child process rooted at the repository; anything unexpected is EXIT_LOAD."""
    try:
        proc = subprocess.run(
            [sys.executable, str(Path(__file__).resolve()), WORKER_FLAG, *slang_args],
            cwd=REPO,
            capture_output=True,
            text=True,
            timeout=ELAB_TIMEOUT_S,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return Result(EXIT_LOAD, f"timeout after {exc.timeout} s")
    output = proc.stdout + proc.stderr
    if proc.returncode in (EXIT_OK, EXIT_FINDINGS):
        return Result(proc.returncode, output)
    # A crash or signal must never read as a verdict.
    return Result(EXIT_LOAD, f"worker exit {proc.returncode}\n{output}")


def run_controls() -> list[str]:
    """Return a description of every control giving the wrong verdict."""
    bad = []
    with tempfile.TemporaryDirectory(prefix="elab_strict_") as tmp:
        for control in CONTROLS:
            path = Path(tmp) / f"{control.name}.sv"
            path.write_text(control.source, encoding="utf-8")
            result = elaborate(["--top", "top", str(path)])
            want = EXIT_OK if control.legal else EXIT_FINDINGS
            if result.code != want:
                bad.append(
                    f"{control.name}: expected exit {want}, got {result.code}\n{result.output}"
                )
    return bad


def _select_arms(names: list[str] | None) -> tuple[Arm, ...] | None:
    if not names:
        return ARMS
    known = {arm.name: arm for arm in ARMS}
    unknown = [name for name in names if name not in known]
    if unknown:
        print(f"unknown arm(s): {', '.join(unknown)}; known: {', '.join(known)}", file=sys.stderr)
        return None
    return tuple(known[name] for name in names)


def main(argv: list[str]) -> int:
    """Run controls, then each arm; return the worst exit code."""
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="print tool output for clean arms too"
    )
    parser.add_argument("--arm", action="append", help="check only this arm (repeatable)")
    args = parser.parse_args(argv)

    if not pyslang_available():
        print("pyslang unavailable: pip install -r requirements.txt", file=sys.stderr)
        return EXIT_NO_TOOL
    arms = _select_arms(args.arm)
    if arms is None:
        return EXIT_LOAD

    failed_controls = run_controls()
    if failed_controls:
        print("CONTROL FAILED, gate result would be meaningless:", file=sys.stderr)
        for line in failed_controls:
            print(line, file=sys.stderr)
        return EXIT_LOAD
    print(f"controls ok ({len(CONTROLS)})")

    worst = EXIT_OK
    for arm in arms:
        result = elaborate(arm.args(REPO))
        verdict = {EXIT_OK: "clean", EXIT_FINDINGS: "FINDINGS"}.get(result.code, "LOAD FAILURE")
        print(f"{arm.name}: {verdict}")
        if result.code != EXIT_OK or args.verbose:
            print(result.output)
        worst = max(worst, result.code)
    return worst


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == WORKER_FLAG:
        sys.exit(_worker(sys.argv[2:]))
    sys.exit(main(sys.argv[1:]))
