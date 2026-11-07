"""pytest: compare.py runs, every JSON value traces to a committed file, and the
committed comparison.json is current.

    python3 -m pytest -q pnr/commercial/compare/test_compare.py
"""

import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
SCRIPT = HERE / "compare.py"


def _tracked() -> set:
    out = subprocess.run(
        ["git", "-C", str(REPO), "ls-files", "-z"], capture_output=True, check=True
    ).stdout
    return set(out.decode().split("\0"))


def _build(tmp_path):
    out = tmp_path / "comparison.json"
    r = subprocess.run(
        [sys.executable, "-I", str(SCRIPT), "--out", str(out)], capture_output=True, text=True
    )
    assert r.returncode == 0, r.stderr
    return json.loads(out.read_text())


def _entries(node, path="$"):
    """Yield (path, dict) for every leaf entry: a dict carrying 'value' or 'values'."""
    if isinstance(node, dict):
        if "value" in node or "values" in node:
            yield path, node
        for k, v in node.items():
            if k not in ("value", "values"):
                yield from _entries(v, f"{path}.{k}")
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from _entries(v, f"{path}[{i}]")


def test_every_value_has_a_committed_source(tmp_path):
    data = _build(tmp_path)
    tracked = _tracked()
    entries = list(_entries(data))
    assert len(entries) > 300
    bad = []
    for path, e in entries:
        assert e.get("label") in ("judge", "native", "signoff", "derived"), path
        srcs = e.get("source")
        srcs = srcs if isinstance(srcs, list) else [srcs]
        if not srcs or any(s is None for s in srcs):
            bad.append((path, "no source"))
            continue
        for s in srcs:
            if not (REPO / s).is_file():
                bad.append((path, f"missing {s}"))
            elif s not in tracked:
                bad.append((path, f"not in git index {s}"))
    assert not bad, bad[:20]


def test_final_arms_complete_and_no_warnings(tmp_path):
    data = _build(tmp_path)
    assert data["warnings"] == []
    for arm in ("openroad_b2", "icc2_b6", "innovus_b6"):
        for var in ("base", "iolat", "iolat_pv", "iolat_pvs"):
            corners = data["judge"][arm][var]["corners"]
            assert all(corners[c] for c in corners) and len(corners) == 9, (arm, var)
            assert data["judge"][arm][var]["power"]["values"]["total_mW"] > 0
    for arm in ("icc2_b6", "innovus_b6"):
        assert all(data["judge"][arm]["own"]["corners"].values())


def test_committed_json_is_current():
    r = subprocess.run(
        [sys.executable, "-I", str(SCRIPT), "--check"], capture_output=True, text=True
    )
    assert r.returncode == 0, r.stderr
