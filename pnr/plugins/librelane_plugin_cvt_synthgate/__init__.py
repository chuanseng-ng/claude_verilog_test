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

import os
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
        res = gate.evaluate(logs, headers, entries)
    except (gate.InputError, gate.AllowlistError) as exc:
        raise StepError(f"CVT synth gate could not judge this step (never a pass): {exc}") from exc
    lines = [gate._fmt(f) for f in res["findings"]]  # pylint: disable=protected-access
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
    _log_info(f"CVT synth gate PASS ({res['structural_check']}); report: synth_undef_gate.rpt")


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
