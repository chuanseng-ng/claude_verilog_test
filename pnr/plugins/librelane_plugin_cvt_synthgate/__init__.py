"""Project-local LibreLane plugin: synthesis undef-elaboration gate (bead gc0y).

LibreLane imports every module named ``librelane_plugin_*`` found on ``sys.path`` at start-up, so
putting ``pnr/plugins`` on ``PYTHONPATH`` (``SYNTH_GATE_ENV`` in pnr/Makefile) activates this for
EVERY PDK / frontend / config without touching the shared LibreLane install or any config.json.

What it does
------------
1. After every ``Yosys.JsonHeader`` / ``Yosys.Synthesis`` / ``Yosys.Resynthesis`` step it runs
   ``tools/verif/check_synth_undef.py`` (log scan + structural check of the ``*.h.json`` header) and
   aborts the flow with a ``StepError`` naming file:line and message on an un-allowlisted hit.  The
   JsonHeader step is first in the flow, so a doomed design is stopped after ~1 minute instead of
   after a multi-hour P&R run.  A report is written to ``<step_dir>/synth_undef_gate.rpt``.
2. Gives every Pyosys step a private cwd (its own step dir).  Surelog writes ``slpp_all/`` to the
   cwd; the Makefile runs LibreLane from the shared LibreLane checkout, so that cache used to be
   shared by every project and worktree (a stale-source hazard measured in bead dud4).

Environment: ``CVT_SYNTH_GATE=warn`` reports but does not abort, ``=off`` disables the check
(never use either for sign-off runs).  If the hooks cannot be installed the import raises, so a
missing gate is loud rather than silent.
"""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[3]
_VERIF = str(_REPO / "tools" / "verif")
if _VERIF not in sys.path:
    sys.path.insert(0, _VERIF)

import check_synth_undef as gate  # noqa: E402  pylint: disable=wrong-import-position
from librelane.steps import pyosys as _pyosys  # noqa: E402  pylint: disable=wrong-import-position
from librelane.steps.step import Step, StepError  # noqa: E402  pylint: disable=wrong-import-position

from librelane.logging import info as _log_info  # noqa: E402  pylint: disable=wrong-import-position

_MARK = "_cvt_synthgate_installed"


def _mode() -> str:
    return os.environ.get("CVT_SYNTH_GATE", "on").strip().lower()


_PROOF_NAME = "func_temp_proof.pre.il"


def _needs_proof(logs, headers, entries) -> bool:
    """True if, without a proof, the header holds x-driven nets that look like function temporaries."""
    res = gate.evaluate(logs, headers, entries)
    return any(
        f.rule == "x-driven-net" and gate.FUNC_TEMP_RE.match(f.text.split(" ")[1])
        for f in res["findings"]
        if f.severity == "FAIL"
    )


def _write_proof(step, il_path: Path) -> None:
    """Re-elaborate the step's own sources up to ``hierarchy`` and dump the PRE-proc RTLIL.

    Same sources, defines and top as the JsonHeader step (its config.json/extra.json), plain yosys
    frontend only - a Synlig run has no ``$func$`` temporaries, so no proof is ever needed there.
    """
    step_dir = Path(step.step_dir)
    cfg = json.loads((step_dir / "config.json").read_text(encoding="utf-8"))
    extra_p = step_dir / "extra.json"
    extra = json.loads(extra_p.read_text(encoding="utf-8")) if extra_p.is_file() else {}
    defines = list(cfg.get("VERILOG_DEFINES") or []) + [
        f"PDK_{cfg['PDK']}",
        f"SCL_{cfg['STD_CELL_LIBRARY']}",
        "__librelane__",
        "__pnr__",
    ]
    if cfg.get("VERILOG_POWER_DEFINE"):
        defines.append(cfg["VERILOG_POWER_DEFINE"])
    flags = [f"-D{d}" for d in defines] + [f"-I{d}" for d in (cfg.get("VERILOG_INCLUDE_DIRS") or [])]
    cmds = [f"read_verilog -sv -lib {' '.join(flags)} {m}" for m in extra.get("blackbox_models", [])]
    cmds += [f"read_verilog -sv {' '.join(flags)} {f}" for f in cfg["VERILOG_FILES"]]
    chparams = " ".join(
        "-chparam " + " ".join(p.split("=", 1)) for p in (cfg.get("SYNTH_PARAMETERS") or [])
    )
    cmds += [f"hierarchy -top {cfg['DESIGN_NAME']} {chparams}".strip(), f"write_rtlil {il_path}"]
    yosys = shutil.which("yosys")
    if yosys is None:
        raise StepError("CVT synth gate: yosys not on PATH, cannot prove function temporaries dead")
    log = step_dir / "func_temp_proof.log"
    proc = subprocess.run(  # noqa: S603
        [yosys, "-l", str(log), "-p", "; ".join(cmds)],
        cwd=step_dir,
        capture_output=True,
        text=True,
        check=False,
        timeout=1800,
    )
    if proc.returncode != 0 or not il_path.is_file():
        raise StepError(
            f"CVT synth gate: proof elaboration failed (rc={proc.returncode}); see {log}:\n"
            + proc.stderr[-2000:]
        )


def _proof(step, logs, headers, entries):
    """Function-temporary proof for this run (generated once, lazily, only if candidates exist)."""
    run_dir = Path(step.step_dir).parent
    ils = sorted(run_dir.glob(f"*yosys*/{_PROOF_NAME}"))
    if not ils and not step.config.get("USE_SYNLIG") and _needs_proof(logs, headers, entries):
        il = Path(step.step_dir) / _PROOF_NAME
        _write_proof(step, il)
        ils = [il]
    return gate.load_func_temp_proof(ils) if ils else None


def _run_gate(step) -> None:
    mode = _mode()
    if mode == "off":
        step.warn("CVT synth gate DISABLED (CVT_SYNTH_GATE=off)")
        return
    step_dir = Path(step.step_dir)
    run_dir = step_dir.parent
    logs = [Path(step.get_log_path())]
    headers = sorted(run_dir.glob("*yosys*/*.h.json"))
    entries = (
        gate.load_allowlist(gate.DEFAULT_ALLOWLIST) if gate.DEFAULT_ALLOWLIST.is_file() else []
    )
    try:
        res = gate.evaluate(logs, headers, entries, _proof(step, logs, headers, entries))
    except (gate.InputError, gate.AllowlistError) as exc:
        raise StepError(f"CVT synth gate could not judge this step (never a pass): {exc}") from exc
    lines = [
        gate._fmt(f)  # pylint: disable=protected-access
        for f in res["findings"]
        if f.severity != "EXEMPT"
    ]
    lines += gate.format_exemptions(res["findings"])
    lines.append(
        f"verdict={res['verdict']} fail={res['fail_count']} structural={res['structural_check']}"
    )
    (step_dir / "synth_undef_gate.rpt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    if res["verdict"] == "FAIL":
        bad = [x for x in lines if x.startswith("FAIL")]
        msg = (
            f"CVT synthesis undef-elaboration gate FAILED ({res['fail_count']} finding(s)); the "
            "frontend replaced logic with undef or dropped a driver (beads dud4/gc0y):\n"
            + "\n".join(bad)
        )
        if mode == "warn":
            step.warn(msg + "\n(CVT_SYNTH_GATE=warn: continuing)")
            return
        raise StepError(msg)
    _census_tripwire(step, mode)
    _log_info(f"CVT synth gate PASS ({res['structural_check']}); report: synth_undef_gate.rpt")


def _census_tripwire(step, mode: str) -> None:
    """Sky130 CPU only: the fwd_b_* flops must exist in the synthesised netlist (dud4 tripwire)."""
    cfg = step.config
    if cfg.get("DESIGN_NAME") != "rv32i_cpu_top" or not str(cfg.get("PDK", "")).startswith("sky130"):
        return
    netlist = Path(step.step_dir) / "rv32i_cpu_top.nl.v"
    if not netlist.is_file():  # JsonHeader step: no netlist yet
        return
    import check_cpu_netlist_census as census  # pylint: disable=import-outside-toplevel

    if census.main([str(netlist)]) != 0 and mode != "warn":
        raise StepError(
            "CVT netlist census tripwire fired: fwd_b_* flops missing or flop count out of band "
            f"({netlist}); this is the dud4 casualty signature (docs/SYNTH_UNDEF_GATE.md)"
        )


def _install() -> None:
    if getattr(Step, _MARK, False):
        return
    pyosys_step = _pyosys.PyosysStep
    gated = [
        getattr(_pyosys, n)
        for n in ("JsonHeader", "Synthesis", "Resynthesis")
        if hasattr(_pyosys, n)
    ]
    if not gated:
        raise ImportError("librelane.steps.pyosys has no JsonHeader/Synthesis: cannot install gate")

    orig_sub = Step.run_subprocess

    def run_subprocess(self, cmd, *args, **kwargs):
        if isinstance(self, pyosys_step) and "cwd" not in kwargs:
            kwargs["cwd"] = self.step_dir  # private Surelog slpp_all cache
        return orig_sub(self, cmd, *args, **kwargs)

    Step.run_subprocess = run_subprocess  # type: ignore[method-assign]

    orig_run = pyosys_step.run

    def run(self, state_in, **kwargs):
        result = orig_run(self, state_in, **kwargs)
        if isinstance(self, tuple(gated)):
            _run_gate(self)
        return result

    pyosys_step.run = run  # type: ignore[method-assign]
    setattr(Step, _MARK, True)


_install()
