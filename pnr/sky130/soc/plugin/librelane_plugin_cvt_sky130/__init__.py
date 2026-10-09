"""Project-local LibreLane plugin for the Sky130 SoC flow (bead claude_verilog_test-e45j).

LibreLane imports every importable module named ``librelane_plugin_*`` at start-up
(``librelane/plugins.py``), so putting this directory on ``PYTHONPATH`` registers the steps
below without touching the shared LibreLane install that every ASAP7 / Sky130 / FreePDK45 flow
in this repo uses. See docs/SKY130_SLEW_CAP_E45J.md for the measurement that motivates it.

What it adds
------------
``CVT.<step>`` variants of the four pre-route repair / resizer steps. They run the stock
LibreLane script unchanged, but through ``tcl/cvt_wrap.tcl``, which applies a per-corner
wire-RC calibration (``tcl/rc_calibration.tcl``) immediately after ``common/set_rc.tcl``. The
calibration scales the tech-LEF per-layer RC the GRT/placement estimator uses so that the resizer
sizes buffers against the capacitance OpenRCX will later extract (~1.9x the ground-only estimate).

Activation is opt-in through ``meta.substituting_steps`` in the design config, and the multipliers
come from the ``CVT_RC_CALIBRATION`` config variable, e.g.
``"nom=1.88,1.02 min=1.69,0.62 max=2.04,1.91"`` (``<rc corner>=<C scale>,<R scale>``).
An unset / empty variable makes the wrapper a byte-for-byte pass-through.

``CVT.MaxCapViolations`` is a drop-in for ``Checker.MaxCapViolations`` that applies the named, load-pin-keyed
waivers of ``constraints/max_cap_waivers.json`` (logic in ``cvt_maxcap_waiver.py``, next to this package).
It is needed because (a) the stock checker cannot waive a single net, and (b) the stock checker is a no-op
unless ``MAX_CAP_VIOLATION_CORNERS`` is set: ``corner_override = [""]`` in ``librelane/steps/checker.py``
makes it match no corner, so un-skipping it alone only produces a warning.
"""

import os
from pathlib import Path
from typing import Optional, Tuple

import cvt_maxcap_waiver as maxcap
from librelane.common import Path as ConfigPath  # str subclass LibreLane's Variable type system requires
from librelane.config import Variable
from librelane.state import DesignFormat, State
from librelane.steps import MetricsUpdate, Step, ViewsUpdate
from librelane.steps.step import DeferredStepError
from librelane.steps.openroad import (
    RepairDesignPostGPL,
    RepairDesignPostGRT,
    ResizerTimingPostCTS,
    ResizerTimingPostGRT,
)

TCL_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tcl")

CVT_VARS = [
    Variable(
        "CVT_RC_CALIBRATION",
        Optional[str],
        "Per-RC-corner multipliers applied to the signal wire RC used by the pre-route parasitic "
        "estimator in the CVT.* steps, as space-separated '<nom|min|max>=<C scale>,<R scale>' "
        "entries. Empty / unset disables the calibration (the CVT.* steps then behave exactly "
        "like the stock steps).",
        default=None,
    ),
]


def _calibrated(base, step_id: str, step_name: str):
    """Subclass ``base`` so its stock script runs through the RC-calibration wrapper."""

    class _Calibrated(base):  # type: ignore[misc, valid-type]
        id = step_id
        name = step_name
        config_vars = base.config_vars + CVT_VARS

        def get_script_path(self):
            return os.path.join(TCL_DIR, "cvt_wrap.tcl")

        def prepare_env(self, env, state):
            env = super().prepare_env(env, state)
            env["CVT_REAL_SCRIPT"] = base.get_script_path(self)
            env["CVT_PROJ_TCL"] = TCL_DIR
            return env

    _Calibrated.__name__ = "CVT_" + base.__name__
    _Calibrated.__qualname__ = _Calibrated.__name__
    _Calibrated.__doc__ = (
        f"{base.__name__} with project-local pre-route wire-RC calibration "
        "(see librelane_plugin_cvt_sky130)."
    )
    return Step.factory.register()(_Calibrated)


CVTRepairDesignPostGPL = _calibrated(
    RepairDesignPostGPL,
    "CVT.RepairDesignPostGPL",
    "Repair Design (Post-Global Placement, RC-calibrated)",
)
CVTResizerTimingPostCTS = _calibrated(
    ResizerTimingPostCTS,
    "CVT.ResizerTimingPostCTS",
    "Resizer Timing (Post-CTS, RC-calibrated)",
)
CVTRepairDesignPostGRT = _calibrated(
    RepairDesignPostGRT,
    "CVT.RepairDesignPostGRT",
    "Repair Design (Post-Global Routing, RC-calibrated)",
)
CVTResizerTimingPostGRT = _calibrated(
    ResizerTimingPostGRT,
    "CVT.ResizerTimingPostGRT",
    "Resizer Timing (Post-Global Routing, RC-calibrated)",
)


MAXCAP_VARS = [
    Variable(
        "CVT_MAXCAP_WAIVERS",
        Optional[ConfigPath],
        "JSON file of named max-capacitance waivers (see constraints/max_cap_waivers.json). Unset / "
        "missing means strict mode: every max-cap violation at every corner fails the step.",
        default=None,
    ),
    Variable(
        "CVT_MAXCAP_STRICT_STALE",
        bool,
        "Treat a waiver that waives nothing as a failure instead of a warning.",
        default=False,
    ),
]


@Step.factory.register()
class CVTMaxCapViolations(Step):
    """Max-cap checker with named, load-pin-keyed waivers (replaces ``Checker.MaxCapViolations``).

    Reads the per-corner ``checks.rpt`` of the ``OpenROAD.STAPostPNR`` step of the same run and the final
    netlist from the incoming state, fails (deferred, so the flow still finishes) on any violation not
    covered by a waiver, and warns on stale waivers.  All corners are gated, not only
    ``TIMING_VIOLATION_CORNERS``.
    """

    id = "CVT.MaxCapViolations"
    name = "Max Cap Violations Checker (named waivers)"
    long_name = "Maximum Capacitance Violations Checker with named waivers"

    inputs = [DesignFormat.NETLIST]
    outputs = []
    config_vars = MAXCAP_VARS

    def run(self, state_in: State, **kwargs) -> Tuple[ViewsUpdate, MetricsUpdate]:
        waiver_path = self.config.get("CVT_MAXCAP_WAIVERS")
        strict_stale = bool(self.config.get("CVT_MAXCAP_STRICT_STALE"))
        run_dir = Path(self.step_dir).parent
        try:
            waivers = maxcap.load_waivers(waiver_path) if waiver_path else ()
            verdict = maxcap.evaluate_sta_dir(
                maxcap.find_sta_dir(run_dir),
                state_in[DesignFormat.NETLIST],
                waivers,
                strict_stale=strict_stale,
            )
        except (maxcap.ReportError, maxcap.WaiverError) as exc:
            msg = f"max-cap check could not be completed: {exc}"
            self.err(f"{msg} - deferred")
            raise DeferredStepError(msg) from exc

        report = verdict.format()
        with open(os.path.join(self.step_dir, "max_cap_waivers.rpt"), "w") as f:
            f.write(report + "\n")
        for stale in verdict.stale_waivers:
            self.warn(f"stale max-cap waiver '{stale.id}': it waived no violation at any corner")
        metrics = {
            "design__max_cap_violation__waived__count": len(verdict.waived),
            "design__max_cap_violation__unwaived__count": len(verdict.unwaived),
        }
        if not verdict.ok:
            msg = f"{len(verdict.unwaived)} unwaived max-cap violation(s):\n{report}"
            self.err(f"{msg} - deferred")
            raise DeferredStepError(msg)
        if verdict.waived:
            self.warn(f"waived max-cap violations (see max_cap_waivers.rpt):\n{report}")
        return {}, metrics
