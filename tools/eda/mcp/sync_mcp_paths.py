#!/usr/bin/env python3
"""Point the eda-opensta/eda-openroad entries in .mcp.json at this clone.

.mcp.json cannot portably reference the repo root at MCP-server-spawn time.
Claude Code documents a ${CLAUDE_PROJECT_DIR} placeholder for exactly this
case, but it is only guaranteed to land in the *spawned server's*
environment -- for a project-scoped .mcp.json, expanding it inside
`command`/`args` needs a `${CLAUDE_PROJECT_DIR:-.}` fallback, and that
fallback resolves "." against Claude Code's own current working directory,
not the project root.

Measured directly on this host (Claude Code 2.1.222, 2026-08-05): with
`${CLAUDE_PROJECT_DIR:-.}` in args, `claude mcp list` run from the repo root
reports both eda-* servers Connected, but the same .mcp.json run from a
subdirectory (tools/eda/) reports both "Failed to connect -- Connection
closed". So this script bakes in an absolute path instead, the same way the
pre-existing code-review-graph/hdl-kgraph entries already do -- there is no
portable placeholder form that survived the test.

Only touches eda-opensta/eda-openroad; every other server entry in
.mcp.json is left byte-for-byte untouched. Idempotent: running it twice in a
row with the same repo root produces the same file the second time.

Stdlib only -- this runs from `make setup`, outside the repo virtualenv.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

EDA_TOOL = {"eda-opensta": "opensta", "eda-openroad": "openroad"}


def sync(mcp_json: Path, repo_root: Path) -> bool:
    """Rewrite the eda-* entries in `mcp_json` to point at `repo_root`.

    Returns True if the file's contents changed.
    """
    old_text = mcp_json.read_text(encoding="utf-8")
    data = json.loads(old_text)
    servers = data.setdefault("mcpServers", {})
    session_server = str(repo_root / "tools" / "eda" / "mcp" / "session_server.py")

    for name, tool in EDA_TOOL.items():
        servers[name] = {
            "command": "python3",
            "args": [session_server, "--tool", tool],
            "cwd": str(repo_root),
            "type": "stdio",
        }

    new_text = json.dumps(data, indent=2) + "\n"
    if new_text == old_text:
        return False
    mcp_json.write_text(new_text, encoding="utf-8")
    return True


def main() -> int:
    """Parse argv, sync .mcp.json, and report whether it changed."""
    if len(sys.argv) != 3:
        print(f"usage: {sys.argv[0]} <path-to-.mcp.json> <repo-root>", file=sys.stderr)
        return 2
    mcp_json = Path(sys.argv[1])
    repo_root = Path(sys.argv[2]).resolve()
    changed = sync(mcp_json, repo_root)
    print(("updated" if changed else "already up to date") + f" -> {mcp_json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
