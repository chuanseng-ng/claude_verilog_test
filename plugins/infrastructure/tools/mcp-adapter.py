#!/usr/bin/env python3
"""
mcp-adapter.py — Batch MCP adapter for analog EDA tools.

Each MCP server config (mcp-ngspice.json, mcp-magic.json, etc.) points here.
This script reads a JSON request on stdin, dispatches to the appropriate
wrapper script, and returns the wrapper's compact JSON on stdout.

Protocol (line-delimited JSON-RPC 2.0 subset used by Claude MCP):
  stdin:  {"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"<tool>","arguments":{...}}}
  stdout: {"jsonrpc":"2.0","id":1,"result":{"content":[{"type":"text","text":"<json>"}]}}
"""
import json
import os
import subprocess
import sys
import tempfile
import shlex

TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))

WRAPPER_MAP = {
    "ngspice_run":  os.path.join(TOOLS_DIR, "ngspice-wrapper.sh"),
    "magic_drc":    os.path.join(TOOLS_DIR, "magic-wrapper.sh"),
    "klayout_drc":  os.path.join(TOOLS_DIR, "klayout-wrapper.sh"),
    "netgen_lvs":   os.path.join(TOOLS_DIR, "netgen-wrapper.sh"),
    "openvaf_compile": os.path.join(TOOLS_DIR, "openvaf-wrapper.sh"),
}


def dispatch(tool_name: str, arguments: dict) -> dict:
    wrapper = WRAPPER_MAP.get(tool_name)
    if wrapper is None:
        return {"tool": tool_name, "exit_code": 1, "status": "FAIL",
                "summary": {}, "errors": [f"Unknown tool: {tool_name}"],
                "warnings": [], "raw_log": ""}

    # Build argument list from the 'args' key (list) or 'netlist'/'script' keys
    extra_args = arguments.get("args", [])
    if isinstance(extra_args, str):
        extra_args = shlex.split(extra_args)

    netlist = arguments.get("netlist", "")
    cmd = [wrapper] + ([netlist] if netlist else []) + extra_args

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        stdout = proc.stdout.strip()
        try:
            return json.loads(stdout)
        except json.JSONDecodeError:
            return {"tool": tool_name, "exit_code": proc.returncode,
                    "status": "FAIL" if proc.returncode != 0 else "PASS",
                    "summary": {}, "errors": [proc.stderr[:500]],
                    "warnings": [], "raw_log": "", "raw_stdout": stdout[:500]}
    except subprocess.TimeoutExpired:
        return {"tool": tool_name, "exit_code": -1, "status": "FAIL",
                "summary": {}, "errors": ["Timeout after 300s"],
                "warnings": [], "raw_log": ""}
    except Exception as exc:
        return {"tool": tool_name, "exit_code": -1, "status": "FAIL",
                "summary": {}, "errors": [str(exc)],
                "warnings": [], "raw_log": ""}


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError as e:
            sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": None,
                                         "error": {"code": -32700, "message": str(e)}}) + "\n")
            sys.stdout.flush()
            continue

        req_id = req.get("id")
        method = req.get("method", "")
        if method == "tools/call":
            params = req.get("params", {})
            tool_name = params.get("name", "")
            arguments = params.get("arguments", {})
            result_data = dispatch(tool_name, arguments)
            response = {
                "jsonrpc": "2.0", "id": req_id,
                "result": {"content": [{"type": "text", "text": json.dumps(result_data, indent=2)}]}
            }
        elif method == "tools/list":
            response = {
                "jsonrpc": "2.0", "id": req_id,
                "result": {"tools": [
                    {"name": k, "description": f"Run {k} via wrapper", "inputSchema": {
                        "type": "object",
                        "properties": {"netlist": {"type": "string"}, "args": {"type": "array"}},
                    }} for k in WRAPPER_MAP
                ]}
            }
        else:
            response = {"jsonrpc": "2.0", "id": req_id,
                        "error": {"code": -32601, "message": f"Method not found: {method}"}}

        sys.stdout.write(json.dumps(response) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
