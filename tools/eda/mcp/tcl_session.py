#!/usr/bin/env python3
"""A long-lived Tcl subprocess (OpenSTA or OpenROAD) driven over stdin/stdout.

This is the part that makes an MCP server worth having for these two tools: the
design is elaborated once and every later query runs against the loaded state,
instead of re-reading liberty + netlist + SDC per question (minutes each on this
SoC).

Framing: every command is wrapped in `catch` and followed by a sentinel `puts`,
so a Tcl error is captured as data rather than desynchronising the stream:

    if {[catch {<command>} __eda_err]} { puts "__EDA_ERROR__ $__eda_err" }
    puts "__EDA_DONE_<n>__"

Output is read on a background thread so a hung tool hits a timeout instead of
blocking the server forever.

Stdlib only — this runs outside the repo virtualenv.
"""

from __future__ import annotations

import glob
import os
import queue
import shutil
import subprocess
import tempfile
import threading
from dataclasses import dataclass, field

# How a tool is found, in order: explicit env var, PATH, then a best-effort look
# through the nix store (the PD tools live in the librelane nix-shell and are not
# on the login PATH on this host).
TOOL_ENV = {"opensta": "EDA_STA_BIN", "openroad": "EDA_OPENROAD_BIN"}
TOOL_EXE = {"opensta": "sta", "openroad": "openroad"}
TOOL_NIX_GLOB = {
    "opensta": "/nix/store/*-opensta*/bin/sta",
    "openroad": "/nix/store/*-openroad*/bin/openroad",
}
# Flags that keep the tool quiet and non-interactive on stdin.
TOOL_ARGS = {"opensta": ["-no_splash"], "openroad": ["-no_splash", "-no_init"]}

DEFAULT_TIMEOUT_S = float(os.environ.get("EDA_SESSION_TIMEOUT_S", "600"))


class SessionError(RuntimeError):
    """The tool could not be found, started, or answered in time."""


def resolve_tool(tool: str) -> str:
    """Return an absolute path to the tool binary, or raise SessionError."""
    env_var = TOOL_ENV[tool]
    if os.environ.get(env_var):
        candidate = os.environ[env_var]
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
        raise SessionError(f"{env_var}={candidate} is not an executable file")

    found = shutil.which(TOOL_EXE[tool])
    if found:
        return found

    matches = sorted(glob.glob(TOOL_NIX_GLOB[tool]))
    if matches:
        return matches[-1]

    raise SessionError(
        f"{TOOL_EXE[tool]} not found. Set {env_var} to its path, put it on PATH, "
        f"or start the server from the librelane nix-shell "
        f"(~/Downloads/Github/librelane)."
    )


@dataclass
class TclSession:
    """One live tool process. Not thread-safe; the MCP server calls it serially."""

    tool: str
    proc: subprocess.Popen | None = None
    _lines: queue.Queue = field(default_factory=queue.Queue)
    _reader: threading.Thread | None = None
    _seq: int = 0
    _tmpdir: str = ""
    binary: str = ""

    # ---------------------------------------------------------------- lifecycle

    @property
    def alive(self) -> bool:
        """True while the tool subprocess is running."""
        return self.proc is not None and self.proc.poll() is None

    def start(self) -> str:
        """Spawn the tool. Returns the resolved binary path."""
        if self.alive:
            return self.binary

        self.binary = resolve_tool(self.tool)
        try:
            # pylint: disable=consider-using-with  # the process outlives this call by design
            self.proc = subprocess.Popen(
                [self.binary, *TOOL_ARGS[self.tool]],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
        except OSError as exc:
            raise SessionError(f"could not start {self.binary}: {exc}") from exc

        self._lines = queue.Queue()
        self._reader = threading.Thread(target=self._pump, daemon=True)
        self._reader.start()
        return self.binary

    def _pump(self) -> None:
        assert self.proc is not None and self.proc.stdout is not None
        for line in self.proc.stdout:
            self._lines.put(line.rstrip("\n"))
        self._lines.put(None)  # EOF marker

    def close(self) -> None:
        """Ask the tool to exit, then make sure it is gone."""
        if not self.alive:
            self.proc = None
            return
        assert self.proc is not None
        try:
            if self.proc.stdin:
                self.proc.stdin.write("exit\n")
                self.proc.stdin.flush()
            self.proc.wait(timeout=10)
        except (OSError, ValueError, subprocess.TimeoutExpired):
            self.proc.kill()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass
        finally:
            self.proc = None

    # ------------------------------------------------------------------ command

    def run(self, command: str, timeout: float = DEFAULT_TIMEOUT_S) -> tuple[str, str | None]:
        """Run one Tcl command.

        Returns (output, tcl_error). `tcl_error` is None when the command
        completed without raising in Tcl.
        """
        if not self.alive:
            raise SessionError("no design loaded — call load_design first")
        assert self.proc is not None and self.proc.stdin is not None

        self._seq += 1
        sentinel = f"__EDA_DONE_{self._seq}__"
        marker = f"__EDA_ERROR_{self._seq}__"
        workdir = self._workdir()
        cmd_file = os.path.join(workdir, f"cmd_{self._seq}.tcl")
        out_file = os.path.join(workdir, f"out_{self._seq}.rpt")

        # The command goes in a file that the tool `source`s, rather than down
        # stdin directly: both tools echo their stdin, so an inlined command
        # would put our own sentinel text into the output stream. Command output
        # is captured to a file via OpenSTA's redirect API (OpenROAD embeds the
        # same), which keeps the interactive prompt and ANSI escapes out of it.
        with open(cmd_file, "w", encoding="utf-8") as fh:
            fh.write(
                f'sta::redirect_file_begin "{out_file}"\n'
                f"set __eda_rc [catch {{{command}}} __eda_err]\n"
                f"sta::redirect_file_end\n"
                f'if {{$__eda_rc}} {{ puts "{marker} $__eda_err" }}\n'
                f'puts "{sentinel}"\n'
            )

        try:
            self.proc.stdin.write(f'source "{cmd_file}"\n')
            self.proc.stdin.flush()
        except (OSError, ValueError) as exc:
            raise SessionError(f"{self.tool} session died while sending a command: {exc}") from exc

        err: str | None = None
        while True:
            try:
                line = self._lines.get(timeout=timeout)
            except queue.Empty as exc:
                raise SessionError(
                    f"{self.tool} did not answer within {timeout:g}s — "
                    f"the session is left running; call close_design to reset"
                ) from exc
            if line is None:
                raise SessionError(f"{self.tool} exited unexpectedly (see the log)")
            if line.strip() == sentinel:
                break
            if line.startswith(marker):
                err = line[len(marker) :].strip()

        out = ""
        if os.path.isfile(out_file):
            with open(out_file, encoding="utf-8", errors="replace") as fh:
                out = fh.read()
        return out, err

    def _workdir(self) -> str:
        """Per-session scratch dir for the command/output files."""
        if not self._tmpdir:
            self._tmpdir = tempfile.mkdtemp(prefix=f"eda-{self.tool}-")
        return self._tmpdir
