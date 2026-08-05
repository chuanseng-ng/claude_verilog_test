"""Unit tests for tools/eda/mcp/sync_mcp_paths.py.

Covers the property that matters most for a checked-in .mcp.json: every
server entry other than eda-opensta/eda-openroad must survive untouched, and
running the sync twice with the same repo root must be a true no-op (no
diff, not just "no error").
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
_SPEC = importlib.util.spec_from_file_location(
    "sync_mcp_paths", REPO_ROOT / "tools" / "eda" / "mcp" / "sync_mcp_paths.py"
)
assert _SPEC and _SPEC.loader
sync_mcp_paths = importlib.util.module_from_spec(_SPEC)
sys.modules["sync_mcp_paths"] = sync_mcp_paths
_SPEC.loader.exec_module(sync_mcp_paths)

_FIXTURE = {
    "mcpServers": {
        "code-review-graph": {
            "command": "uvx",
            "args": ["code-review-graph", "serve"],
            "cwd": "/some/other/clone",
            "type": "stdio",
        },
        "hdl-kgraph": {
            "command": "hdl-kgraph",
            "args": ["serve", "--mcp", "--db", "/some/other/clone/.hdl-kgraph/graph.db"],
        },
        "eda-opensta": {
            "command": "python3",
            "args": ["/some/other/clone/tools/eda/mcp/session_server.py", "--tool", "opensta"],
            "cwd": "/some/other/clone",
            "type": "stdio",
        },
        "eda-openroad": {
            "command": "python3",
            "args": ["/some/other/clone/tools/eda/mcp/session_server.py", "--tool", "openroad"],
            "cwd": "/some/other/clone",
            "type": "stdio",
        },
    }
}


def _write_fixture(path: Path) -> None:
    path.write_text(json.dumps(_FIXTURE, indent=2) + "\n", encoding="utf-8")


def test_rewrites_only_eda_entries(tmp_path: Path) -> None:
    """code-review-graph and hdl-kgraph are byte-for-byte untouched."""
    mcp_json = tmp_path / ".mcp.json"
    _write_fixture(mcp_json)
    new_root = tmp_path / "clone"
    changed = sync_mcp_paths.sync(mcp_json, new_root)
    assert changed
    data = json.loads(mcp_json.read_text(encoding="utf-8"))
    assert data["mcpServers"]["code-review-graph"] == _FIXTURE["mcpServers"]["code-review-graph"]
    assert data["mcpServers"]["hdl-kgraph"] == _FIXTURE["mcpServers"]["hdl-kgraph"]


def test_eda_entries_point_at_new_root(tmp_path: Path) -> None:
    """eda-opensta/eda-openroad args[0] and cwd are rewritten to the new root."""
    mcp_json = tmp_path / ".mcp.json"
    _write_fixture(mcp_json)
    new_root = tmp_path / "clone"
    sync_mcp_paths.sync(mcp_json, new_root)
    data = json.loads(mcp_json.read_text(encoding="utf-8"))
    expected_script = str(new_root / "tools" / "eda" / "mcp" / "session_server.py")
    for name, tool in (("eda-opensta", "opensta"), ("eda-openroad", "openroad")):
        entry = data["mcpServers"][name]
        assert entry["args"] == [expected_script, "--tool", tool]
        assert entry["cwd"] == str(new_root)
        assert entry["command"] == "python3"
        assert entry["type"] == "stdio"


def test_second_run_with_same_root_is_a_true_noop(tmp_path: Path) -> None:
    """Running twice with the same repo root produces identical bytes."""
    mcp_json = tmp_path / ".mcp.json"
    _write_fixture(mcp_json)
    root = tmp_path / "clone"
    sync_mcp_paths.sync(mcp_json, root)
    once = mcp_json.read_text(encoding="utf-8")
    changed = sync_mcp_paths.sync(mcp_json, root)
    assert not changed
    assert mcp_json.read_text(encoding="utf-8") == once


def test_reports_changed_when_root_actually_differs(tmp_path: Path) -> None:
    """sync() return value distinguishes a real rewrite from a no-op."""
    mcp_json = tmp_path / ".mcp.json"
    _write_fixture(mcp_json)
    root_a = tmp_path / "clone-a"
    root_b = tmp_path / "clone-b"
    assert sync_mcp_paths.sync(mcp_json, root_a) is True
    assert sync_mcp_paths.sync(mcp_json, root_a) is False
    assert sync_mcp_paths.sync(mcp_json, root_b) is True
