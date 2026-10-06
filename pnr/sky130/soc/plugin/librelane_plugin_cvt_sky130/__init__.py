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
"""

import os
from typing import Optional

from librelane.config import Variable
from librelane.steps import Step
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
