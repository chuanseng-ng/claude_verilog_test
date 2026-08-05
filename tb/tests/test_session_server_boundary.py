"""Unit tests for tools/eda/mcp/session_server.py.

Covers two CodeRabbit findings:

- Finding 3: `_save` named report files `{tool}-{name}-{seq}.rpt`, and
  `TclSession._seq` restarts at 0 in every new server process, so a second
  server run's `opensta-timing-1.rpt` silently overwrote the first run's
  file of the same name -- and a `report` path already handed back to a
  caller in the first run then pointed at different content. The fix adds a
  per-process discriminator (`_RUN_ID`, PID + start time) to the filename,
  and exposes `TclSession.seq` as a public accessor instead of reaching into
  `_seq`.
- Finding 4: one malformed request used to end the server process and
  discard the loaded design -- exactly the loss this server exists to
  prevent. The fix adds an exception boundary in `main()`'s stdio loop
  (outermost guard, covers a `params` shape a handler does not expect) and a
  final `except Exception` in `EdaSessionServer.call()` (handler faults stay
  a tool-level error).
"""

from __future__ import annotations

import importlib.util
import io
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
_SPEC = importlib.util.spec_from_file_location(
    "eda_session_server", REPO_ROOT / "tools" / "eda" / "mcp" / "session_server.py"
)
assert _SPEC and _SPEC.loader
session_server = importlib.util.module_from_spec(_SPEC)
sys.modules["eda_session_server"] = session_server
_SPEC.loader.exec_module(session_server)


# ---------------------------------------------------------------------------
# Finding 3 -- report filenames must not collide across server processes
# ---------------------------------------------------------------------------


def test_save_filename_includes_run_id_and_seq(monkeypatch, tmp_path: Path) -> None:
    """Test save filename includes run id and seq."""
    monkeypatch.setattr(session_server, "REPORT_DIR", tmp_path)
    monkeypatch.setattr(session_server, "_RUN_ID", "12345-1690000000")

    server = session_server.EdaSessionServer("opensta")
    server.session._seq = 3
    path = server._save("timing", "some text")

    assert path.endswith("opensta-timing-12345-1690000000-3.rpt")
    assert Path(path).read_text(encoding="utf-8") == "some text"


def test_two_server_runs_with_same_seq_do_not_collide(monkeypatch, tmp_path: Path) -> None:
    """Simulates the exact bug: two 'server processes' (different _RUN_ID)
    both at seq==1 must not write the same file."""
    monkeypatch.setattr(session_server, "REPORT_DIR", tmp_path)
    server = session_server.EdaSessionServer("opensta")
    server.session._seq = 1

    monkeypatch.setattr(session_server, "_RUN_ID", "111-1000")
    path_a = server._save("timing", "run A content")

    monkeypatch.setattr(session_server, "_RUN_ID", "222-2000")
    path_b = server._save("timing", "run B content")

    assert path_a != path_b
    assert Path(path_a).read_text(encoding="utf-8") == "run A content"
    assert Path(path_b).read_text(encoding="utf-8") == "run B content"


def test_save_does_not_need_protected_access() -> None:
    """TclSession.seq is a public property -- _save no longer reaches into
    the private `_seq` attribute (and no longer needs the pylint pragma)."""
    src = (REPO_ROOT / "tools" / "eda" / "mcp" / "session_server.py").read_text(encoding="utf-8")
    assert "session._seq" not in src
    assert "pylint: disable=protected-access" not in src


# ---------------------------------------------------------------------------
# Finding 4 -- one bad request must not kill the server / drop the session
# ---------------------------------------------------------------------------


def test_call_converts_unexpected_handler_exception_to_tool_error(monkeypatch) -> None:
    """A handler fault that is neither SessionError nor KeyError/OSError
    (e.g. a bug surfaced as a plain ValueError) must come back as a
    tool-level ERROR payload, not propagate out of call()."""
    server = session_server.EdaSessionServer("opensta")

    def _boom(*_args, **_kwargs):
        raise ValueError("boom")

    monkeypatch.setattr(server.session, "run", _boom)

    payload, is_error = server.call("report_wns_tns", {})

    assert is_error is True
    assert payload["status"] == "ERROR"
    assert "boom" in payload["error"]


def test_call_still_handles_unknown_tool_name() -> None:
    """Test call still handles unknown tool name."""
    server = session_server.EdaSessionServer("opensta")
    payload, is_error = server.call("not_a_real_tool", {})
    assert is_error is True
    assert payload["status"] == "ERROR"


def test_main_survives_malformed_params_and_keeps_serving(monkeypatch, capsys) -> None:
    """A `params` shape a handler does not expect (a list where `tools/call`
    needs a dict with .get) must not end the process -- the next, valid
    request on the same stream must still be answered."""
    bad_request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": ["not", "a", "dict"],
    }
    good_request = {"jsonrpc": "2.0", "id": 2, "method": "ping"}
    stdin_text = json.dumps(bad_request) + "\n" + json.dumps(good_request) + "\n"

    monkeypatch.setattr(sys, "argv", ["session_server.py", "--tool", "opensta"])
    monkeypatch.setattr(sys, "stdin", io.StringIO(stdin_text))

    rc = session_server.main()
    assert rc == 0

    lines = [ln for ln in capsys.readouterr().out.splitlines() if ln.strip()]
    assert len(lines) == 2

    first = json.loads(lines[0])
    assert first["id"] == 1
    assert "error" in first
    assert first["error"]["code"] == -32603

    second = json.loads(lines[1])
    assert second["id"] == 2
    assert second["result"] == {}


def test_main_survives_handler_exception_and_reports_tool_error(monkeypatch, capsys) -> None:
    """An unexpected exception raised deep inside a tool handler (not a
    JSON-RPC framing problem) must also stay a tool-level error and keep the
    process -- and the loaded session -- alive."""
    request = {
        "jsonrpc": "2.0",
        "id": 7,
        "method": "tools/call",
        "params": {"name": "report_wns_tns", "arguments": {}},
    }
    monkeypatch.setattr(sys, "argv", ["session_server.py", "--tool", "opensta"])
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(request) + "\n"))

    def _boom(self, *_args, **_kwargs):  # noqa: ANN001
        raise ValueError("boom")

    monkeypatch.setattr(session_server.TclSession, "run", _boom)

    rc = session_server.main()
    assert rc == 0

    lines = [ln for ln in capsys.readouterr().out.splitlines() if ln.strip()]
    assert len(lines) == 1
    reply = json.loads(lines[0])
    assert reply["id"] == 7

    content = json.loads(reply["result"]["content"][0]["text"])
    assert content["status"] == "ERROR"
    assert "boom" in content["error"]
    assert reply["result"]["isError"] is True


def test_main_survives_unhandled_exception_in_handle_itself(monkeypatch, capsys) -> None:
    """Belt-and-braces: even if a future change makes handle() itself raise
    (not just a called handler), main()'s outer boundary must still catch it
    and keep serving instead of exiting."""
    monkeypatch.setattr(sys, "argv", ["session_server.py", "--tool", "opensta"])
    good_request = {"jsonrpc": "2.0", "id": 1, "method": "ping"}
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(good_request) + "\n"))

    real_handle = session_server.handle
    calls = {"n": 0}

    def _flaky_handle(server, req):
        calls["n"] += 1
        raise RuntimeError("simulated framing bug")

    monkeypatch.setattr(session_server, "handle", _flaky_handle)

    rc = session_server.main()
    assert rc == 0
    assert calls["n"] == 1

    lines = [ln for ln in capsys.readouterr().out.splitlines() if ln.strip()]
    assert len(lines) == 1
    reply = json.loads(lines[0])
    assert reply["id"] == 1
    assert reply["error"]["code"] == -32603

    # sanity: the real handle() is untouched by the monkeypatch elsewhere
    assert real_handle is not _flaky_handle


def test_server_keeps_serving_after_each_injected_exception(monkeypatch, capsys) -> None:
    """The property that actually matters: service CONTINUES after a fault.

    The other boundary tests each send a single bad request, so they prove the
    process does not die but not that it still answers. Here a handler raises
    on the first request and the next two requests must still get correct
    replies — that is the whole point of the boundary, since the alternative is
    losing the loaded design.
    """
    monkeypatch.setattr(sys, "argv", ["session_server.py", "--tool", "opensta"])
    requests = [
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "run_tcl", "arguments": {"command": "puts hi"}},
        },
        {"jsonrpc": "2.0", "id": 2, "method": "ping"},
        {"jsonrpc": "2.0", "id": 3, "method": "tools/list"},
    ]
    monkeypatch.setattr(
        sys, "stdin", io.StringIO("\n".join(json.dumps(r) for r in requests) + "\n")
    )

    def _boom(*_args, **_kwargs):
        raise ValueError("boom")

    monkeypatch.setattr(session_server.TclSession, "run", _boom)
    monkeypatch.setattr(session_server.TclSession, "start", lambda self: "/fake/sta")

    assert session_server.main() == 0

    replies = [json.loads(ln) for ln in capsys.readouterr().out.splitlines() if ln.strip()]
    assert [r["id"] for r in replies] == [1, 2, 3], "every request must get a reply"

    # 1: the fault, reported as a tool-level error rather than a crash
    assert replies[0]["result"]["isError"] is True
    # 2 and 3: normal service, unaffected by the earlier fault
    assert replies[1]["result"] == {}
    assert [t["name"] for t in replies[2]["result"]["tools"]]
