"""CVT.ScanInsert: netlist-level scan insertion as a project-local LibreLane step (bead claude_verilog_test-j41m.8).

LibreLane has no DFT step.  This module adds one, plus a ``Classic`` subclass that runs it right after the synthesis
checkers, so the scan flops exist before floorplan, placement, CTS and routing see the design.  Nothing in the shared
LibreLane install is edited; the plugin directory is put on ``PYTHONPATH`` by pnr/Makefile.

Why a netlist step with OpenROAD 26Q2 (and not the flow's own OpenROAD): DFT_ARCHITECTURE.md 1.1/1.3.  The flow's
``edf00dff`` OpenROAD has a defective stitcher (SET_B left open on negedge flops) and no ``-max_length`` splitting;
26Q2 chooses the right scan flop and splits a clock domain into chains of at most ``-max_length`` cells.

Port reuse (the question bead j41m.8 asked): 26Q2 ``insert_dft`` does NOT reuse existing ports.  It creates
``scan_enable_0`` / ``scan_in_<k>`` / ``scan_out_<k>`` (the ``-scan_*_name_pattern`` options only rename them).  The Tcl
script (tcl/scan_insert.tcl) therefore merges those nets into the pre-existing ``scan_in_i[n]`` / ``scan_out_o[n]`` /
``dft_scan_en`` of the design, drops the placeholder ``conb`` tie on ``scan_out_o[n]`` and puts a buffer between the last
flop of a chain and its output port.

Output: a netlist with no ``assign`` statements (checked here), ``<step_dir>/scan_insert.rpt`` (key=value lines) and the
metrics ``dft__scan_chains`` / ``dft__scan_flops`` / ``dft__scan_unscanned_flops`` / ``dft__scan_chain_max_length``.
"""

import os
import re
from librelane.common import Path  # str subclass the State type system requires
from typing import List, Optional, Tuple

from librelane.config import Variable
from librelane.flows import Flow
from librelane.flows.classic import Classic
from librelane.logging import info as _log_info
from librelane.state import DesignFormat, State
from librelane.steps import MetricsUpdate, Step, ViewsUpdate
from librelane.steps.checker import NetlistAssignStatements
from librelane.steps.step import StepError

_TCL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "librelane_plugin_cvt_sky130", "tcl", "scan_insert.tcl")


def _tcl_list(items) -> str:
    """Brace-quote each item so the Tcl script's ``foreach`` / ``lassign`` see it as one element."""
    return " ".join("{" + str(i) + "}" for i in items)


SCAN_VARS = [
    Variable(
        "CVT_SCAN_OPENROAD",
        Optional[str],
        "OpenROAD binary that provides set_dft_config/scan_replace/execute_dft_plan (26Q2). Falls back to the "
        "CVT_SCAN_OPENROAD environment variable.",
        default=None,
    ),
    Variable("CVT_SCAN_MAX_LENGTH", int, "set_dft_config -max_length: longest chain in cells.", default=3700),
    Variable(
        "CVT_SCAN_CLOCKS",
        List[str],
        "STA clocks the stitcher needs, each 'name:port:period_ns' (e.g. core_clk:clk_i:25).",
        default=[],
    ),
    Variable(
        "CVT_SCAN_EXCLUDE_CLOCK_NETS",
        Optional[List[str]],
        "Flops whose CLK is one of these nets (or an inverter/buffer output fed only from one) stay unscanned "
        "(JTAG TAP clock, test-clock switch).",
        default=None,
    ),
    Variable(
        "CVT_SCAN_EXCLUDE_QNET_REGEX",
        Optional[str],
        "Flops whose Q net matches this regex stay unscanned (crypto key registers, DFT_ARCHITECTURE.md 7).",
        default=None,
    ),
    Variable(
        "CVT_SCAN_EXPECT_QNET_EXCLUDED",
        int,
        "Expected number of flops matched by CVT_SCAN_EXCLUDE_QNET_REGEX (-1: do not check). A mismatch aborts.",
        default=-1,
    ),
    Variable(
        "CVT_SCAN_PORT_ORDER",
        List[str],
        "Regexes on a chain's first-flop clock net; chains take port indices in this class order.",
        default=[".*"],
    ),
    Variable("CVT_SCAN_IN_FMT", str, "printf format of the existing scan-in top ports.", default="scan_in_i[%d]"),
    Variable("CVT_SCAN_OUT_FMT", str, "printf format of the existing scan-out top ports.", default="scan_out_o[%d]"),
    Variable("CVT_SCAN_EN_NET", str, "Existing net every SCE pin is joined to.", default="dft_scan_en"),
    Variable("CVT_SCAN_BUF_CELL", str, "Buffer between a chain's last Q net and its scan-out port.", default="sky130_fd_sc_hd__buf_2"),
]

_ASSIGN_RE = re.compile(r"^\s*assign\s", re.M)


_TOOL_PORT_RE = re.compile(r"scan_(?:enable|in|out)_\d+")


def strip_tool_ports(text: str) -> Tuple[str, List[str]]:
    """Remove the dangling ports insert_dft created.

    The ODB-side merge leaves ``scan_enable_0`` / ``scan_in_<k>`` / ``scan_out_<k>`` in the written module header and as
    ``input``/``output`` declarations (OpenROAD keeps the module port); they carry no net, but the flow's IO placement
    then fails with "scan_in_0 not found in config but found in design".  Returns the cleaned text and the dropped names.
    """
    m = re.search(r"\bmodule\s+\S+\s*\((.*?)\);", text, re.S)
    if not m:
        raise StepError("scan netlist: no module header found")
    names = [n.strip() for n in m.group(1).split(",")]
    dropped = [n for n in names if _TOOL_PORT_RE.fullmatch(n)]
    keep = [n for n in names if not _TOOL_PORT_RE.fullmatch(n)]
    header = m.group(0)[: m.group(0).index("(") + 1] + "\n    " + ",\n    ".join(keep) + ");"
    text = text[: m.start()] + header + text[m.end():]
    for n in dropped:
        text, k = re.subn(rf"^\s*(?:input|output)\s+{re.escape(n)}\s*;\s*\n", "", text, flags=re.M)
        if k != 1:
            raise StepError(f"scan netlist: expected one declaration of tool port {n}, removed {k}")
    left = [n for n in dropped if re.search(rf"\b{re.escape(n)}\b", text)]
    if left:
        raise StepError(f"scan netlist: tool port(s) {left} are still referenced after stripping")
    return text, dropped


@Step.factory.register()
class CVTScanInsert(Step):
    id = "CVT.ScanInsert"
    name = "Scan insertion (OpenROAD dft, netlist level)"
    long_name = "Scan chain insertion on the synthesised netlist"

    inputs = [DesignFormat.NETLIST]
    outputs = [DesignFormat.NETLIST]
    config_vars = SCAN_VARS

    def _binary(self) -> str:
        path = self.config.get("CVT_SCAN_OPENROAD") or os.environ.get("CVT_SCAN_OPENROAD")
        if not path or not os.access(path, os.X_OK):
            raise StepError(
                "CVT.ScanInsert needs an OpenROAD with the 26Q2 dft commands: set CVT_SCAN_OPENROAD "
                f"(config variable or environment); got {path!r}"
            )
        return path

    def _libs_and_lefs(self) -> Tuple[List[str], List[str]]:
        cfg = self.config
        tech = self.toolbox.filter_views(cfg, cfg["TECH_LEFS"])
        lefs = [str(p) for p in tech] + [str(p) for p in cfg["CELL_LEFS"]]
        lefs += [str(p) for p in self.toolbox.get_macro_views(cfg, DesignFormat.LEF)]
        libs = [str(p) for p in self.toolbox.filter_views(cfg, cfg["LIB"])]
        libs += [str(p) for p in self.toolbox.get_macro_views(cfg, DesignFormat.LIB)]
        # hard macros declared the pre-MACROS way (the CPU macro flow's SRAM)
        lefs += [str(p) for p in (cfg.get("EXTRA_LEFS") or [])]
        libs += [str(p) for p in (cfg.get("EXTRA_LIBS") or [])]
        return lefs, libs

    def run(self, state_in: State, **kwargs) -> Tuple[ViewsUpdate, MetricsUpdate]:
        cfg = self.config
        design = cfg["DESIGN_NAME"]
        lefs, libs = self._libs_and_lefs()
        nl_in = str(state_in[DesignFormat.NETLIST])
        nl_out = os.path.join(self.step_dir, f"{design}.nl.v")
        report = os.path.join(self.step_dir, "scan_insert.rpt")

        clocks = []
        for spec in cfg["CVT_SCAN_CLOCKS"]:
            name, port, period = spec.split(":")
            clocks.append(f"{name} {port} {period}")
        if not clocks:
            raise StepError("CVT_SCAN_CLOCKS is empty: the stitcher needs at least one STA clock")

        env = dict(os.environ)
        env.update(
            CVT_SCAN_TOP=design,
            CVT_SCAN_NL_IN=nl_in,
            CVT_SCAN_NL_OUT=nl_out,
            CVT_SCAN_REPORT=report,
            CVT_SCAN_LEFS=" ".join(lefs),
            CVT_SCAN_LIBS=" ".join(libs),
            CVT_SCAN_CLOCKS=_tcl_list(clocks),
            CVT_SCAN_EXCL_CLKNETS=" ".join(cfg["CVT_SCAN_EXCLUDE_CLOCK_NETS"] or []),
            CVT_SCAN_EXCL_QRX=cfg["CVT_SCAN_EXCLUDE_QNET_REGEX"] or "",
            CVT_SCAN_EXPECT_QEXCL=str(cfg["CVT_SCAN_EXPECT_QNET_EXCLUDED"]),
            CVT_SCAN_MAX_LENGTH=str(cfg["CVT_SCAN_MAX_LENGTH"]),
            CVT_SCAN_PORT_ORDER=_tcl_list(cfg["CVT_SCAN_PORT_ORDER"]),
            CVT_SCAN_IN_FMT=cfg["CVT_SCAN_IN_FMT"],
            CVT_SCAN_OUT_FMT=cfg["CVT_SCAN_OUT_FMT"],
            CVT_SCAN_EN_NET=cfg["CVT_SCAN_EN_NET"],
            CVT_SCAN_BUF_CELL=cfg["CVT_SCAN_BUF_CELL"],
        )
        result = self.run_subprocess([self._binary(), "-no_splash", "-exit", _TCL], env=env, check=False)
        if result["returncode"] != 0 or not os.path.isfile(nl_out) or not os.path.isfile(report):
            raise StepError(
                f"scan insertion failed (exit {result['returncode']}); see {result['log_path']} "
                "(CVT-SCAN-ERROR lines name the cause)"
            )
        with open(nl_out, encoding="utf-8", errors="replace") as fh:
            text = fh.read()
        text, dropped = strip_tool_ports(text)
        _log_info(f"dropped the tool-created ports {dropped}")
        with open(nl_out, "w", encoding="utf-8") as fh:
            fh.write(text)
        n_assign = len(_ASSIGN_RE.findall(text))
        if n_assign:
            raise StepError(f"scan netlist has {n_assign} assign statement(s); Checker.NetlistAssignStatements would reject it")

        kv = {}
        chain_lengths = []
        with open(report, encoding="utf-8") as fh:
            for line in fh:
                key, _, val = line.strip().partition("=")
                kv[key] = val
                if key.startswith("chain."):
                    m = re.search(r"length=(\d+)", val)
                    if m:
                        chain_lengths.append(int(m.group(1)))
        metrics = {
            "dft__scan_chains": int(kv.get("chains", 0)),
            "dft__scan_flops": int(kv.get("scan_flops", 0)),
            "dft__scan_unscanned_flops": int(kv.get("nonscan_flops", 0)),
            "dft__scan_chain_max_length": max(chain_lengths) if chain_lengths else 0,
        }
        return {DesignFormat.NETLIST: Path(nl_out)}, metrics


def _steps_with_scan() -> list:
    steps = list(Classic.Steps)
    idx = steps.index(NetlistAssignStatements)
    return steps[: idx + 1] + [CVTScanInsert] + steps[idx + 1 :]


@Flow.factory.register()
class CVTClassicScan(Classic):
    """Classic, plus CVT.ScanInsert right after Checker.NetlistAssignStatements (so scan flops exist from floorplan on)."""

    Steps = _steps_with_scan()
