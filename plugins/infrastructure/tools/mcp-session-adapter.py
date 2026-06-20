#!/usr/bin/env python3
"""
mcp-session-adapter.py — Interactive/session MCP adapter for ngspice.

Maintains a running ngspice process and exposes stateful tools:
  load_netlist, run_analysis, measure, alter_param, run_corner, close

Usage (as configured by mcp-ngspice-session.json):
  python3 mcp-session-adapter.py --tool ngspice
"""
import argparse
import json
import os
import subprocess
import sys
import threading
import time

TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))


class NgspiceSession:
    def __init__(self):
        self._proc = None
        self._lock = threading.Lock()
        self._output_buf = []

    def _start(self):
        if self._proc is None or self._proc.poll() is not None:
            self._proc = subprocess.Popen(
                ["ngspice", "-p"],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, text=True, bufsize=1
            )
            # consume banner
            self._drain(timeout=1.5)

    def _drain(self, timeout=0.5):
        lines = []
        start = time.time()
        while time.time() - start < timeout:
            try:
                line = self._proc.stdout.readline()
                if line:
                    lines.append(line.rstrip())
            except Exception:
                break
        self._output_buf.extend(lines)
        return lines

    def _send(self, cmd: str):
        if self._proc and self._proc.poll() is None:
            self._proc.stdin.write(cmd + "\n")
            self._proc.stdin.flush()
            time.sleep(0.2)
            return self._drain(timeout=1.0)
        return ["ERROR: ngspice process not running"]

    def load_netlist(self, path: str):
        with self._lock:
            self._start()
            out = self._send(f"source {path}")
            return {"loaded": path, "output": out}

    def run_analysis(self, analysis: str):
        with self._lock:
            out = self._send(analysis)
            return {"analysis": analysis, "output": out}

    def measure(self, expression: str):
        with self._lock:
            out = self._send(f"meas {expression}")
            return {"expression": expression, "output": out}

    def alter_param(self, component: str, param: str, value: float):
        with self._lock:
            out = self._send(f"alter @{component}[{param}]={value}")
            return {"component": component, "param": param, "value": value, "output": out}

    def run_corner(self, corner_name: str, temp: float, supply: float):
        with self._lock:
            self._send(f"set temp={temp}")
            self._send(f"alter vdd dc={supply}")
            out = self._send("run")
            return {"corner": corner_name, "temp": temp, "supply": supply, "output": out}

    def close(self):
        with self._lock:
            if self._proc and self._proc.poll() is None:
                try:
                    self._proc.stdin.write("quit\n")
                    self._proc.stdin.flush()
                    self._proc.wait(timeout=3)
                except Exception:
                    self._proc.kill()
                self._proc = None
        return {"status": "closed"}


SESSION = NgspiceSession()


def dispatch(tool_name: str, arguments: dict) -> dict:
    try:
        if tool_name == "load_netlist":
            return SESSION.load_netlist(arguments["path"])
        elif tool_name == "run_analysis":
            return SESSION.run_analysis(arguments["analysis"])
        elif tool_name == "measure":
            return SESSION.measure(arguments["expression"])
        elif tool_name == "alter_param":
            return SESSION.alter_param(arguments["component"], arguments["param"], arguments["value"])
        elif tool_name == "run_corner":
            return SESSION.run_corner(arguments["corner_name"], arguments["temp"], arguments["supply"])
        elif tool_name == "close":
            return SESSION.close()
        else:
            return {"error": f"Unknown session tool: {tool_name}"}
    except Exception as exc:
        return {"error": str(exc)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tool", default="ngspice")
    args = parser.parse_args()

    session_tools = [
        {"name": "load_netlist",  "description": "Load a SPICE netlist into the session",
         "inputSchema": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}},
        {"name": "run_analysis",  "description": "Run a SPICE analysis command (e.g. 'tran 1p 10n')",
         "inputSchema": {"type": "object", "properties": {"analysis": {"type": "string"}}, "required": ["analysis"]}},
        {"name": "measure",       "description": "Evaluate a .meas expression",
         "inputSchema": {"type": "object", "properties": {"expression": {"type": "string"}}, "required": ["expression"]}},
        {"name": "alter_param",   "description": "Alter a component parameter in-session",
         "inputSchema": {"type": "object", "properties": {
             "component": {"type": "string"}, "param": {"type": "string"}, "value": {"type": "number"}},
             "required": ["component", "param", "value"]}},
        {"name": "run_corner",    "description": "Set PVT corner and re-run",
         "inputSchema": {"type": "object", "properties": {
             "corner_name": {"type": "string"}, "temp": {"type": "number"}, "supply": {"type": "number"}},
             "required": ["corner_name", "temp", "supply"]}},
        {"name": "close",         "description": "Close the ngspice session",
         "inputSchema": {"type": "object", "properties": {}}},
    ]

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

        if method == "tools/list":
            response = {"jsonrpc": "2.0", "id": req_id, "result": {"tools": session_tools}}
        elif method == "tools/call":
            params = req.get("params", {})
            result_data = dispatch(params.get("name", ""), params.get("arguments", {}))
            response = {
                "jsonrpc": "2.0", "id": req_id,
                "result": {"content": [{"type": "text", "text": json.dumps(result_data, indent=2)}]}
            }
        else:
            response = {"jsonrpc": "2.0", "id": req_id,
                        "error": {"code": -32601, "message": f"Method not found: {method}"}}

        sys.stdout.write(json.dumps(response) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
