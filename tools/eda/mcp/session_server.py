#!/usr/bin/env python3
"""MCP stdio server exposing a live OpenSTA or OpenROAD session.

Why an MCP server here, and nowhere else in this repo: during timing closure the
same design is queried dozens of times, and every batch invocation re-reads
liberty + netlist + SDC (minutes each on this SoC). A session loads once and
answers from the loaded state. One-shot tools (Verilator, Yosys, sv2v, cocotb)
gain nothing from this and use `tools/eda/wrap-*.sh` instead.

Every reply is a compact JSON summary plus the path to the full report on disk —
raw reports are never returned inline.

Protocol: newline-delimited JSON-RPC 2.0 over stdio, implementing `initialize`,
`notifications/initialized`, `tools/list`, `tools/call`, `ping` and `shutdown`.
(The plugin-generated adapters under plugins/infrastructure/ answer `initialize`
with -32601 and so never complete the handshake; this one does.)

Run:
    session_server.py --tool opensta
    session_server.py --tool openroad
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# pylint: disable=wrong-import-position
import summarize  # noqa: E402
from tcl_session import SessionError, TclSession  # noqa: E402

PROTOCOL_VERSION = "2024-11-05"
SERVER_VERSION = "0.1.0"
MAX_INLINE_CHARS = 4000  # cap on any raw text echoed back to the client

REPO_ROOT = Path(__file__).resolve().parents[3]
REPORT_DIR = Path(os.environ.get("EDA_LOG_DIR", REPO_ROOT / "sim" / "build" / "eda-logs"))


# ---------------------------------------------------------------------------
# tool definitions
# ---------------------------------------------------------------------------

_STR = {"type": "string"}
_STRS = {"type": "array", "items": {"type": "string"}}
_INT = {"type": "integer"}


def _schema(props: dict, required: list[str] | None = None) -> dict:
    return {"type": "object", "properties": props, "required": required or []}


OPENSTA_TOOLS = [
    {
        "name": "load_design",
        "description": (
            "Start OpenSTA (if needed) and load a design: read_liberty for each "
            "library, read_verilog, link_design, read_sdc, optional read_spef. "
            "Loading once is the point of this server — later queries reuse it."
        ),
        "inputSchema": _schema(
            {
                "liberty": _STRS,
                "netlist": _STR,
                "top": _STR,
                "sdc": _STR,
                "spef": _STR,
            },
            ["liberty", "netlist", "top"],
        ),
    },
    {
        "name": "report_timing",
        "description": (
            "report_checks on the loaded design; returns wns/tns/violated-endpoint "
            "counts plus the report path."
        ),
        "inputSchema": _schema(
            {"max_paths": _INT, "path_group": _STR, "from": _STR, "to": _STR, "extra_args": _STR}
        ),
    },
    {
        "name": "report_wns_tns",
        "description": (
            "Worst negative slack and total negative slack only — the cheapest health check."
        ),
        "inputSchema": _schema({}),
    },
    {
        "name": "check_setup",
        "description": (
            "OpenSTA check_setup: unconstrained endpoints, missing clocks, "
            "and similar constraint gaps."
        ),
        "inputSchema": _schema({}),
    },
]

OPENROAD_TOOLS = [
    {
        "name": "load_odb",
        "description": (
            "Start OpenROAD (if needed) and read an .odb database, optionally with liberty and SDC."
        ),
        "inputSchema": _schema({"odb": _STR, "liberty": _STRS, "sdc": _STR}, ["odb"]),
    },
    {
        "name": "query_timing",
        "description": (
            "report_checks on the loaded database; returns wns/tns/violated-endpoint "
            "counts plus the report path."
        ),
        "inputSchema": _schema({"max_paths": _INT, "extra_args": _STR}),
    },
    {
        "name": "get_area",
        "description": "report_design_area plus report_cell_usage for the loaded database.",
        "inputSchema": _schema({}),
    },
    {
        "name": "get_power",
        "description": "report_power for the loaded database.",
        "inputSchema": _schema({}),
    },
]

COMMON_TOOLS = [
    {
        "name": "run_tcl",
        "description": (
            "Run an arbitrary Tcl command in the live session. Output is truncated "
            "with an explicit truncated=true flag; the full text is on disk."
        ),
        "inputSchema": _schema({"command": _STR}, ["command"]),
    },
    {
        "name": "close_design",
        "description": "Terminate the tool process. The next load_* starts a fresh one.",
        "inputSchema": _schema({}),
    },
]


# ---------------------------------------------------------------------------
# handlers
# ---------------------------------------------------------------------------


class EdaSessionServer:
    """Holds the one live session and maps MCP tool calls onto Tcl commands."""

    def __init__(self, tool: str) -> None:
        self.tool = tool
        self.session = TclSession(tool=tool)
        self.tools = (OPENSTA_TOOLS if tool == "opensta" else OPENROAD_TOOLS) + COMMON_TOOLS
        self._loaded: str | None = None

    # -- helpers ------------------------------------------------------------

    def _save(self, name: str, text: str) -> str:
        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        path = REPORT_DIR / f"{self.tool}-{name}-{self.session._seq}.rpt"  # pylint: disable=protected-access
        path.write_text(text, encoding="utf-8")
        return str(path)

    def _timing_reply(self, name: str, out: str, err: str | None) -> dict:
        """Summarise a timing report the same way tools/eda/summarize.py does."""
        report = self._save(name, out)
        status, summary = summarize.parse_opensta(out, 1 if err else 0)
        if err:
            summary["errors"] = [err]
        return {
            "status": {0: "PASS", 1: "FAIL", 2: "ERROR"}[status],
            "summary": summary,
            "report": report,
            "design": self._loaded,
        }

    def _run(self, command: str) -> tuple[str, str | None]:
        return self.session.run(command)

    # -- tool implementations ----------------------------------------------

    def _load_design(self, args: dict) -> dict:
        self.session.start()
        cmds = [f'read_liberty "{lib}"' for lib in args["liberty"]]
        cmds.append(f'read_verilog "{args["netlist"]}"')
        cmds.append(f"link_design {args['top']}")
        if args.get("sdc"):
            cmds.append(f'read_sdc "{args["sdc"]}"')
        if args.get("spef"):
            cmds.append(f'read_spef "{args["spef"]}"')

        log: list[str] = []
        for cmd in cmds:
            out, err = self._run(cmd)
            log.append(out)
            if err:
                return {"status": "ERROR", "failed_command": cmd, "error": err}
        self._loaded = args["netlist"]
        return {
            "status": "PASS",
            "design": args["netlist"],
            "top": args["top"],
            "binary": self.session.binary,
            "log": self._save("load", "\n".join(log)),
        }

    def _load_odb(self, args: dict) -> dict:
        self.session.start()
        cmds = [f'read_liberty "{lib}"' for lib in args.get("liberty") or []]
        cmds.append(f'read_db "{args["odb"]}"')
        if args.get("sdc"):
            cmds.append(f'read_sdc "{args["sdc"]}"')

        log: list[str] = []
        for cmd in cmds:
            out, err = self._run(cmd)
            log.append(out)
            if err:
                return {"status": "ERROR", "failed_command": cmd, "error": err}
        self._loaded = args["odb"]
        return {
            "status": "PASS",
            "design": args["odb"],
            "binary": self.session.binary,
            "log": self._save("load", "\n".join(log)),
        }

    def _report_timing(self, args: dict) -> dict:
        # OpenSTA 2.6.0 report_checks has no -max_paths flag ("not a known
        # keyword or flag") — the path count is controlled by -group_count.
        # That flag applies regardless of -path_group, so a caller who asks
        # for both a path group and a path count gets both, instead of the
        # count silently collapsing to path_group's old hardcoded 1.
        parts = ["report_checks", "-path_delay", "max"]
        parts += ["-group_count", str(args.get("max_paths", 5))]
        if args.get("path_group"):
            parts += ["-path_group", args["path_group"]]
        if args.get("from"):
            parts += ["-from", args["from"]]
        if args.get("to"):
            parts += ["-to", args["to"]]
        if args.get("extra_args"):
            parts.append(args["extra_args"])
        out, err = self._run(" ".join(parts))
        return self._timing_reply("timing", out, err)

    def _report_wns_tns(self, _args: dict) -> dict:
        out, err = self._run("report_wns; report_tns; report_worst_slack")
        return self._timing_reply("wns_tns", out, err)

    def _check_setup(self, _args: dict) -> dict:
        out, err = self._run("check_setup")
        return {
            "status": "ERROR" if err else "PASS",
            "error": err,
            "report": self._save("check_setup", out),
            "text": _truncate(out),
        }

    def _get_area(self, _args: dict) -> dict:
        out, err = self._run("report_design_area; report_cell_usage")
        report = self._save("area", out)
        if not err and not out.strip():
            # report_design_area/report_cell_usage print through OpenROAD's
            # own Logger (utl::report), not the STA report-string channel
            # that sta::redirect_file_begin hooks -- confirmed on OpenROAD
            # 26Q2 by comparing against report_power (which does go through
            # that channel and captures fine). The text still lands on the
            # session's real stdout/terminal, it just never reaches `out`.
            # An empty report here does not mean a clean run; refuse to call
            # it PASS (same rule summarize.py enforces for opensta -- bead
            # dwp).
            return {
                "status": "ERROR",
                "error": (
                    "report_design_area/report_cell_usage produced no "
                    "captured output. These OpenROAD commands write via "
                    "utl::Logger and bypass sta::redirect_file_begin, so "
                    "this session driver cannot capture them -- use run_tcl "
                    "with a script that redirects via 'exec' or read the "
                    ".odb report_design_area output directly."
                ),
                "report": report,
                "text": _truncate(out),
            }
        return {
            "status": "ERROR" if err else "PASS",
            "error": err,
            "report": report,
            "text": _truncate(out),
        }

    def _get_power(self, _args: dict) -> dict:
        out, err = self._run("report_power")
        return {
            "status": "ERROR" if err else "PASS",
            "error": err,
            "report": self._save("power", out),
            "text": _truncate(out),
        }

    def _run_tcl(self, args: dict) -> dict:
        # The escape hatch starts the tool itself: it is legitimate to run Tcl
        # (read_liberty, sourcing a setup script) before any design is loaded.
        self.session.start()
        out, err = self._run(args["command"])
        return {
            "status": "ERROR" if err else "PASS",
            "error": err,
            "report": self._save("tcl", out),
            "text": _truncate(out),
        }

    def _close_design(self, _args: dict) -> dict:
        self.session.close()
        self._loaded = None
        return {"status": "PASS", "closed": True}

    # -- dispatch -----------------------------------------------------------

    def handlers(self) -> dict[str, Callable[[dict], dict]]:
        """Map each MCP tool name this server exposes to its implementation."""
        common = {"run_tcl": self._run_tcl, "close_design": self._close_design}
        if self.tool == "opensta":
            return {
                "load_design": self._load_design,
                "report_timing": self._report_timing,
                "report_wns_tns": self._report_wns_tns,
                "check_setup": self._check_setup,
                **common,
            }
        return {
            "load_odb": self._load_odb,
            "query_timing": self._report_timing,
            "get_area": self._get_area,
            "get_power": self._get_power,
            **common,
        }

    def call(self, name: str, args: dict) -> tuple[dict, bool]:
        """Run one tool call. Returns (payload, is_error)."""
        handler = self.handlers().get(name)
        if handler is None:
            return {"status": "ERROR", "error": f"unknown tool: {name}"}, True
        try:
            payload = handler(args or {})
        except SessionError as exc:
            return {"status": "ERROR", "error": str(exc)}, True
        except (KeyError, OSError) as exc:
            return {"status": "ERROR", "error": f"{type(exc).__name__}: {exc}"}, True
        return payload, payload.get("status") == "ERROR"


def _truncate(text: str) -> dict:
    """Cap inline text and say so explicitly rather than cutting silently."""
    if len(text) <= MAX_INLINE_CHARS:
        return {"content": text, "truncated": False}
    return {"content": text[:MAX_INLINE_CHARS], "truncated": True, "full_chars": len(text)}


# ---------------------------------------------------------------------------
# JSON-RPC plumbing
# ---------------------------------------------------------------------------


def _result(req_id: Any, result: dict) -> dict:
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def _error(req_id: Any, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}


def handle(server: EdaSessionServer, req: dict) -> dict | None:
    """Map one JSON-RPC request to a response, or None for a notification."""
    method = req.get("method", "")
    req_id = req.get("id")
    params = req.get("params") or {}

    if method == "initialize":
        # Echo the client's protocol version when it names one, so a newer client
        # is not rejected over a version string we do not care about.
        version = params.get("protocolVersion") or PROTOCOL_VERSION
        return _result(
            req_id,
            {
                "protocolVersion": version,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": f"eda-{server.tool}-session", "version": SERVER_VERSION},
            },
        )

    if method in ("notifications/initialized", "initialized", "notifications/cancelled"):
        return None

    if method == "ping":
        return _result(req_id, {})

    if method == "tools/list":
        return _result(req_id, {"tools": server.tools})

    if method == "tools/call":
        name = params.get("name", "")
        payload, is_error = server.call(name, params.get("arguments") or {})
        return _result(
            req_id,
            {
                "content": [{"type": "text", "text": json.dumps(payload, indent=2)}],
                "isError": is_error,
            },
        )

    if method in ("shutdown", "exit"):
        server.session.close()
        return None if req_id is None else _result(req_id, {})

    if req_id is None:
        return None  # unknown notification: ignore, per JSON-RPC
    return _error(req_id, -32601, f"Method not found: {method}")


def main() -> int:
    """Read JSON-RPC lines from stdin until EOF."""
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tool", required=True, choices=["opensta", "openroad"])
    args = ap.parse_args()

    server = EdaSessionServer(args.tool)
    try:
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                req = json.loads(line)
            except json.JSONDecodeError as exc:
                _emit(_error(None, -32700, f"Parse error: {exc}"))
                continue
            response = handle(server, req)
            if response is not None:
                _emit(response)
    finally:
        server.session.close()
    return 0


def _emit(message: dict) -> None:
    sys.stdout.write(json.dumps(message) + "\n")
    sys.stdout.flush()


if __name__ == "__main__":
    sys.exit(main())
