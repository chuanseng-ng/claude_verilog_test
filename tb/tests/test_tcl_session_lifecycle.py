"""Unit tests for tools/eda/mcp/tcl_session.py's process lifecycle.

Covers two CodeRabbit findings fixed together because both are about a
TclSession outliving the process it wraps:

- Finding 1: `_pump` used to resolve `self._lines`/`self.proc.stdout` off
  `self` inside its read loop. If a previous process's reader thread was
  still draining to EOF when `start()` rebinds `self._lines` to a fresh
  queue, the *old* thread's leftover lines -- and finally its `None` EOF
  marker -- landed in the *new* queue, making `run()` raise "exited
  unexpectedly" for a perfectly healthy new session. The fix binds the
  queue and stream to the reader thread via explicit args.
- Finding 2: `close()` never removed the per-session temp dir
  (`_workdir()`), never closed `proc.stdin`/`proc.stdout`, and never joined
  the reader thread -- a long session repeated across server restarts fills
  /tmp and leaks two fds + a thread per close/start cycle.

Both use a fake subprocess so the tests do not depend on OpenSTA/OpenROAD
being installed.
"""

from __future__ import annotations

import importlib.util
import queue
import sys
import threading
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
_SPEC = importlib.util.spec_from_file_location(
    "tcl_session", REPO_ROOT / "tools" / "eda" / "mcp" / "tcl_session.py"
)
assert _SPEC and _SPEC.loader
tcl_session = importlib.util.module_from_spec(_SPEC)
sys.modules["tcl_session"] = tcl_session
_SPEC.loader.exec_module(tcl_session)

TclSession = tcl_session.TclSession


# ---------------------------------------------------------------------------
# fakes -- a subprocess.Popen stand-in whose stdout blocks until fed, so a
# test can hold a "previous process" reader thread open past the point where
# a new session starts.
# ---------------------------------------------------------------------------


class _ManualStdout:
    """An iterable stdout stand-in that blocks in __next__ until push()/end()."""

    def __init__(self) -> None:
        self._q: queue.Queue = queue.Queue()
        self._eof = object()
        self.closed = False

    def push(self, line: str) -> None:
        """Push."""
        self._q.put(line)

    def end(self) -> None:
        """End."""
        self._q.put(self._eof)

    def close(self) -> None:
        """Close."""
        self.closed = True

    def __iter__(self):
        return self

    def __next__(self):
        item = self._q.get()
        if item is self._eof:
            raise StopIteration
        return item


class _FakeStdin:
    def __init__(self) -> None:
        self.closed = False
        self.written: list[str] = []

    def write(self, text: str) -> None:
        """Write."""
        self.written.append(text)

    def flush(self) -> None:
        """Flush."""
        pass

    def close(self) -> None:
        """Close."""
        self.closed = True


class _FakeProc:
    def __init__(self) -> None:
        self.stdout = _ManualStdout()
        self.stdin = _FakeStdin()
        self.returncode: int | None = None

    def poll(self) -> int | None:
        """Poll."""
        return self.returncode

    def wait(self, timeout: float | None = None) -> int:
        """Wait."""
        return self.returncode or 0

    def kill(self) -> None:
        """Kill."""
        self.returncode = -9


# ---------------------------------------------------------------------------
# Finding 1 -- stale reader thread must not poison the next session's queue
# ---------------------------------------------------------------------------


def test_stale_reader_thread_cannot_poison_new_session_queue(monkeypatch) -> None:
    """A dead generation's reader thread, still alive when start() rebinds
    self._lines, must keep writing to the queue it was launched with."""
    procs: list[_FakeProc] = []

    def fake_popen(*_args, **_kwargs):
        proc = _FakeProc()
        procs.append(proc)
        return proc

    monkeypatch.setattr(tcl_session, "resolve_tool", lambda _tool: "/fake/bin/sta")
    monkeypatch.setattr(tcl_session.subprocess, "Popen", fake_popen)

    session = TclSession(tool="opensta")
    session.start()
    assert len(procs) == 1
    gen1_proc = procs[0]
    gen1_queue = session._lines
    gen1_reader = session._reader
    assert gen1_reader is not None
    assert gen1_reader.is_alive()

    # gen1's process ends without close() ever being called (e.g. it crashed);
    # its reader thread is still blocked waiting for more stdout, exactly the
    # race window the bug lived in.
    gen1_proc.returncode = 1
    assert not session.alive

    # A fresh start() rebinds self._lines to a brand-new queue.
    session.start()
    assert len(procs) == 2
    gen2_queue = session._lines
    gen2_reader = session._reader
    assert gen2_queue is not gen1_queue

    # Now let the still-running gen1 reader thread see more output and EOF.
    gen1_proc.stdout.push("leftover output from the dead process")
    gen1_proc.stdout.end()
    gen1_reader.join(timeout=5)
    assert not gen1_reader.is_alive()

    # The leftover line and the EOF marker must land in gen1's own queue --
    # never in gen2's.
    assert gen1_queue.get(timeout=2) == "leftover output from the dead process"
    assert gen1_queue.get(timeout=2) is None
    assert gen2_queue.empty()

    # Clean up gen2's reader thread so the test does not leak it.
    session.proc.stdout.end()
    if gen2_reader is not None:
        gen2_reader.join(timeout=5)
        assert not gen2_reader.is_alive()


def test_pump_is_bound_to_explicit_args_not_self(monkeypatch) -> None:
    """Direct regression on the _pump signature: two concurrent invocations
    against two independent (stream, queue) pairs must never cross-write,
    which only holds if _pump takes them as arguments instead of reading
    them off `self`/shared state inside its loop."""
    queue_a: queue.Queue = queue.Queue()
    queue_b: queue.Queue = queue.Queue()
    stream_a, stream_b = _ManualStdout(), _ManualStdout()

    thread_a = threading.Thread(target=TclSession._pump, args=(stream_a, queue_a))
    thread_b = threading.Thread(target=TclSession._pump, args=(stream_b, queue_b))
    thread_a.start()
    thread_b.start()

    stream_b.push("b-line")
    stream_b.end()
    thread_b.join(timeout=5)
    assert queue_b.get(timeout=2) == "b-line"
    assert queue_b.get(timeout=2) is None
    assert queue_a.empty()

    stream_a.push("a-line")
    stream_a.end()
    thread_a.join(timeout=5)
    assert queue_a.get(timeout=2) == "a-line"
    assert queue_a.get(timeout=2) is None
    assert queue_b.empty()


# ---------------------------------------------------------------------------
# Finding 2 -- close() must not leak the temp dir, the fds, or the thread
# ---------------------------------------------------------------------------


def test_close_removes_tmpdir_closes_fds_and_joins_reader(monkeypatch) -> None:
    """Test close removes tmpdir closes fds and joins reader."""
    monkeypatch.setattr(tcl_session, "resolve_tool", lambda _tool: "/fake/bin/sta")
    monkeypatch.setattr(tcl_session.subprocess, "Popen", lambda *a, **k: _FakeProc())

    session = TclSession(tool="opensta")
    session.start()
    proc = session.proc
    reader = session._reader
    assert reader is not None

    # Mirror what run() does: force the per-session scratch dir into being.
    workdir = Path(session._workdir())
    (workdir / "cmd_1.tcl").write_text("puts hi\n", encoding="utf-8")
    assert workdir.is_dir()

    # Let the reader thread reach EOF on its own so close()'s join() does not
    # depend on close() itself unblocking a stuck read (real subprocess pipes
    # unblock on close(); this fake does not model that).
    proc.stdout.end()
    reader.join(timeout=5)

    session.close()

    assert session.proc is None
    assert session._reader is None
    assert session._tmpdir == ""
    assert not workdir.exists()
    assert proc.stdin.closed
    assert proc.stdout.closed
    assert not reader.is_alive()


def test_close_report_dir_is_untouched(monkeypatch, tmp_path: Path) -> None:
    """close() must only ever remove the TclSession-private scratch dir
    (_workdir()), never a report directory a caller might have handed a
    `report` path from -- those live entirely outside this class."""
    monkeypatch.setattr(tcl_session, "resolve_tool", lambda _tool: "/fake/bin/sta")
    monkeypatch.setattr(tcl_session.subprocess, "Popen", lambda *a, **k: _FakeProc())

    report_dir = tmp_path / "eda-logs"
    report_dir.mkdir()
    already_returned_report = report_dir / "opensta-timing-1.rpt"
    already_returned_report.write_text("worst_slack 24.01\n", encoding="utf-8")

    session = TclSession(tool="opensta")
    session.start()
    session._workdir()
    session.proc.stdout.end()
    session._reader.join(timeout=5)
    session.close()

    assert already_returned_report.exists()
    assert already_returned_report.read_text(encoding="utf-8") == "worst_slack 24.01\n"


def test_close_is_idempotent_and_safe_before_start(monkeypatch) -> None:
    """close() must not raise when called twice, or before start()."""
    session = TclSession(tool="opensta")
    session.close()  # never started
    session.close()  # already closed

    monkeypatch.setattr(tcl_session, "resolve_tool", lambda _tool: "/fake/bin/sta")
    monkeypatch.setattr(tcl_session.subprocess, "Popen", lambda *a, **k: _FakeProc())
    session.start()
    session.proc.stdout.end()
    session._reader.join(timeout=5)
    session.close()
    session.close()  # second close on an already-closed session


# ---------------------------------------------------------------------------
# seq is now a public accessor (Finding 3 half that lives in this module)
# ---------------------------------------------------------------------------


def test_seq_is_a_public_property() -> None:
    """Test seq is a public property."""
    session = TclSession(tool="opensta")
    assert session.seq == 0
    session._seq = 5
    assert session.seq == 5
