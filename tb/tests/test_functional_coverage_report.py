"""Unit tests for tools/verif/functional_coverage_report.py (bead h367).

The script merges the per-process YAML files that the cocotb suites export through
``cocotb-coverage`` and gates the result.  The properties pinned here, each by a test:

  * hit counts of the same coverpoint in two files ADD, and totals are recomputed from them (the
    inputs' own ``coverage`` counters are ignored);
  * a coverpoint declared differently in two files is a model mismatch, exit 2, never a silent
    change of the denominator;
  * a waiver needs category ``b`` and a reason, removes only an UNCOVERED bin from the denominator,
    and is STALE (a gate failure) when its bin does not exist or was in fact hit;
  * a required group with no data, no input at all, or an empty database is exit 2, never a pass;
  * a model that shrinks below ``min_bins`` fails the gate even at 100 %;
  * the merged output is parity-checked against the library's own ``merge_coverage`` (skipped when
    ``cocotb_coverage`` is not installed).
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "tools" / "verif" / "functional_coverage_report.py"
_SPEC = importlib.util.spec_from_file_location("functional_coverage_report", SCRIPT)
assert _SPEC and _SPEC.loader
fcr = importlib.util.module_from_spec(_SPEC)
sys.modules["functional_coverage_report"] = fcr
_SPEC.loader.exec_module(fcr)

POINT = "<class 'cocotb_coverage.coverage.CoverPoint'>"
CROSS = "<class 'cocotb_coverage.coverage.CoverCross'>"
ITEM = "<class 'cocotb_coverage.coverage.CoverItem'>"


def leaf(hits: dict, kind: str = POINT, at_least: int = 1, weight: int = 1) -> dict:
    """One exported coverpoint entry (the counters are deliberately wrong: they must be ignored)."""
    return {
        "type": kind,
        "size": 999,
        "coverage": 999,
        "cover_percentage": 99.0,
        "weight": weight,
        "at_least": at_least,
        "bins:_hits": hits,
    }


def write(path: Path, entries: dict) -> Path:
    """Write."""
    path.write_text(json.dumps(entries), encoding="utf-8")  # JSON is valid YAML
    return path


def db(path: Path, **points) -> Path:
    """Export-shaped file: group node plus the given coverpoints (name -> hits)."""
    entries = {"top": {"type": ITEM, "size": 1, "coverage": 1, "cover_percentage": 100.0}}
    entries.update({name: leaf(hits) for name, hits in points.items()})
    return write(path, entries)


def run(*args) -> subprocess.CompletedProcess:
    """Run."""
    return subprocess.run(
        [sys.executable, str(SCRIPT), *map(str, args)], capture_output=True, text=True, check=False
    )


# ---------------------------------------------------------------------------------------- merge
def test_merge_adds_hits_and_recomputes_totals(tmp_path):
    """Merge adds hits and recomputes totals."""
    a = db(tmp_path / "a.yml", **{"g.x": {"p": 1, "q": 0}})
    b = db(tmp_path / "b.yml", **{"g.x": {"p": 2, "q": 0}})
    model = fcr.merge([("a", fcr.load_yaml(a)), ("b", fcr.load_yaml(b))])
    assert dict(model["g.x"].hits) == {"p": 3, "q": 0}
    groups, _subs, stale = fcr.evaluate(model, [])
    assert (groups["g"].covered, groups["g"].size, stale) == (1, 2, [])  # not the bogus 999
    assert groups["g"].uncovered == [("g.x", "q")]


def test_bin_covered_only_in_the_union(tmp_path):
    """Bin covered only in the union."""
    a = db(tmp_path / "a.yml", **{"g.x": {"p": 1, "q": 0}})
    b = db(tmp_path / "b.yml", **{"g.x": {"p": 0, "q": 4}})
    model = fcr.merge([("a", fcr.load_yaml(a)), ("b", fcr.load_yaml(b))])
    groups, _subs, _stale = fcr.evaluate(model, [])
    assert groups["g"].adjusted_pct == 100.0


def test_at_least_and_weight_are_honoured(tmp_path):
    """At least and weight are honoured."""
    entries = {"g.x": leaf({"p": 1, "q": 5}, at_least=2, weight=3)}
    model = fcr.merge([("a", fcr.load_yaml(write(tmp_path / "a.yml", entries)))])
    groups, _subs, _stale = fcr.evaluate(model, [])
    assert (groups["g"].covered, groups["g"].size) == (3, 6)  # only q reaches 2 hits


@pytest.mark.parametrize(
    "other",
    [
        {"g.x": leaf({"p": 1, "z": 0})},  # different bin set
        {"g.x": leaf({"p": 1, "q": 0}, weight=2)},  # different weight
        {"g.x": leaf({"p": 1, "q": 0}, at_least=2)},  # different at_least
    ],
)
def test_model_mismatch_is_an_error(tmp_path, other):
    """Model mismatch is an error."""
    a = db(tmp_path / "a.yml", **{"g.x": {"p": 1, "q": 0}})
    b = write(tmp_path / "b.yml", other)
    proc = run("--in", a, "--in", b)
    assert proc.returncode == 2 and "model mismatch" in proc.stderr


def test_cross_keys_survive_the_round_trip(tmp_path):
    """Cross keys survive the round trip."""
    key = "('write', 'ack')"
    path = write(tmp_path / "a.yml", {"g.c": leaf({key: 1, "('read', 'ack')": 0}, kind=CROSS)})
    model = fcr.merge([("a", fcr.load_yaml(path))])
    assert model["g.c"].kind == "cross" and model["g.c"].hits[key] == 1


# -------------------------------------------------------------------------------------- inputs
def test_no_input_is_an_error(tmp_path):
    """No input is an error."""
    proc = run("--in", tmp_path)  # an empty directory
    assert proc.returncode == 2 and "nothing was measured" in proc.stderr


def test_empty_database_is_an_error(tmp_path):
    """Empty database is an error."""
    path = write(tmp_path / "a.yml", {"top": {"type": ITEM, "size": 0, "coverage": 0}})
    proc = run("--in", path)
    assert proc.returncode == 2 and "no coverpoint" in proc.stderr


def test_unparsable_file_is_an_error(tmp_path):
    """Unparsable file is an error."""
    bad = tmp_path / "a.yml"
    bad.write_text("a: [unclosed\n", encoding="utf-8")
    assert run("--in", bad).returncode == 2


def test_directories_are_scanned_recursively(tmp_path):
    """Directories are scanned recursively."""
    (tmp_path / "shard0").mkdir()
    (tmp_path / "shard1").mkdir()
    db(tmp_path / "shard0" / "t__1.yml", **{"g.x": {"p": 1, "q": 0}})
    db(tmp_path / "shard1" / "t__2.yml", **{"g.x": {"p": 0, "q": 1}})
    out = tmp_path / "merged.yml"
    proc = run("--in", tmp_path, "--out-yaml", out)
    assert proc.returncode == 0, proc.stderr
    merged = fcr.yaml.safe_load(out.read_text(encoding="utf-8"))
    assert merged["g.x"]["bins:_hits"] == {"p": 1, "q": 1}
    assert merged["g.x"]["coverage"] == 2 and merged["g.x"]["cover_percentage"] == 100.0


# ------------------------------------------------------------------------------------- waivers
def waiver_file(tmp_path: Path, text: str) -> Path:
    """Waiver file."""
    path = tmp_path / "w.txt"
    path.write_text(textwrap.dedent(text), encoding="utf-8")
    return path


def test_waiver_removes_an_uncovered_bin_from_the_denominator(tmp_path):
    """Waiver removes an uncovered bin from the denominator."""
    a = db(tmp_path / "a.yml", **{"g.x": {"p": 1, "q": 0}})
    model = fcr.merge([("a", fcr.load_yaml(a))])
    waivers = fcr.parse_waivers(waiver_file(tmp_path, "g.x | q | b | q is impossible by design\n"))
    groups, _subs, stale = fcr.evaluate(model, waivers)
    assert stale == []
    assert groups["g"].raw_pct == 50.0 and groups["g"].adjusted_pct == 100.0
    assert groups["g"].waived == 1 and groups["g"].uncovered == []


def test_cross_waiver_with_comma_labels(tmp_path):
    """Cross waiver with comma labels."""
    key = "('read', 'nack')"
    path = write(tmp_path / "a.yml", {"g.c": leaf({"('write', 'ack')": 1, key: 0}, kind=CROSS)})
    model = fcr.merge([("a", fcr.load_yaml(path))])
    waivers = fcr.parse_waivers(waiver_file(tmp_path, "g.c | read, nack | b | why not\n"))
    groups, _subs, stale = fcr.evaluate(model, waivers)
    assert stale == [] and groups["g"].adjusted_pct == 100.0


def test_waiver_on_a_hit_bin_is_stale(tmp_path):
    """Waiver on a hit bin is stale."""
    a = db(tmp_path / "a.yml", **{"g.x": {"p": 1, "q": 0}})
    model = fcr.merge([("a", fcr.load_yaml(a))])
    waivers = fcr.parse_waivers(waiver_file(tmp_path, "g.x | p | b | but it is hit\n"))
    _groups, _subs, stale = fcr.evaluate(model, waivers)
    assert len(stale) == 1 and "unneeded" in stale[0]


def test_waiver_on_a_missing_bin_is_stale(tmp_path):
    """Waiver on a missing bin is stale."""
    a = db(tmp_path / "a.yml", **{"g.x": {"p": 1}})
    model = fcr.merge([("a", fcr.load_yaml(a))])
    waivers = fcr.parse_waivers(waiver_file(tmp_path, "g.gone | p | b | renamed away\n"))
    _groups, _subs, stale = fcr.evaluate(model, waivers)
    assert len(stale) == 1 and "not in the merged model" in stale[0]


@pytest.mark.parametrize(
    "line",
    [
        "g.x | q | c | wrong category\n",
        "g.x | q | b |\n",  # no justification
        "g.x | q | b\n",  # too few fields
    ],
)
def test_bad_waiver_lines_are_rejected(tmp_path, line):
    """Bad waiver lines are rejected."""
    with pytest.raises(fcr.ReportError):
        fcr.parse_waivers(waiver_file(tmp_path, line))


def test_waiver_comments_and_blank_lines_are_ignored(tmp_path):
    """Waiver comments and blank lines are ignored."""
    text = "# a comment\n\ng.x | q | b | reason with a # inside it\n"
    (waiver,) = fcr.parse_waivers(waiver_file(tmp_path, text))
    assert waiver.reason == "reason with a # inside it" and waiver.line == 3


# --------------------------------------------------------------------------------------- gates
def gates_file(tmp_path: Path, text: str) -> Path:
    """Gates file."""
    path = tmp_path / "g.txt"
    path.write_text(text, encoding="utf-8")
    return path


def test_gate_passes_at_the_floor_and_fails_below(tmp_path):
    """Gate passes at the floor and fails below."""
    a = db(tmp_path / "a.yml", **{"g.x": {"p": 1, "q": 0}})
    gates = gates_file(tmp_path, "g | 100 | 2 | full\n")
    proc = run("--in", a, "--gates", gates, "--gate")
    assert proc.returncode == 1 and "adjusted 50.00% < floor 100%" in proc.stdout
    gates = gates_file(tmp_path, "g | 50 | 2 | measured\n")
    assert run("--in", a, "--gates", gates, "--gate").returncode == 0


def test_report_without_gate_flag_never_fails_on_coverage(tmp_path):
    """Report without gate flag never fails on coverage."""
    a = db(tmp_path / "a.yml", **{"g.x": {"p": 0, "q": 0}})
    gates = gates_file(tmp_path, "g | 100 | 2 | full\n")
    assert run("--in", a, "--gates", gates).returncode == 0


def test_min_bins_stops_a_shrunken_model(tmp_path):
    """Min bins stops a shrunken model."""
    a = db(tmp_path / "a.yml", **{"g.x": {"p": 1}})
    gates = gates_file(tmp_path, "g | 100 | 2 | model must keep 2 bins\n")
    proc = run("--in", a, "--gates", gates, "--gate")
    assert proc.returncode == 1 and "min_bins" in proc.stdout


def test_required_group_without_data_is_an_error(tmp_path):
    """Required group without data is an error."""
    a = db(tmp_path / "a.yml", **{"other.x": {"p": 1}})
    gates = gates_file(tmp_path, "g | 100 | 1 | required\n")
    proc = run("--in", a, "--gates", gates, "--gate")
    assert proc.returncode == 2 and "no data" in proc.stderr


def test_stale_waiver_fails_the_gate(tmp_path):
    """Stale waiver fails the gate."""
    a = db(tmp_path / "a.yml", **{"g.x": {"p": 1}})
    waivers = waiver_file(tmp_path, "g.x | nope | b | stale\n")
    gates = gates_file(tmp_path, "g | 100 | 1 | full\n")
    proc = run("--in", a, "--gates", gates, "--waivers", waivers, "--gate")
    assert proc.returncode == 1 and "not in the merged model" in proc.stdout


def test_markdown_and_json_outputs(tmp_path):
    """Markdown and json outputs."""
    a = db(tmp_path / "a.yml", **{"g.x": {"p": 1, "q": 0}})
    md, js = tmp_path / "r.md", tmp_path / "r.json"
    assert run("--in", a, "--out-md", md, "--out-json", js).returncode == 0
    text = md.read_text(encoding="utf-8")
    assert "Uncovered bins in `g`" in text and "`g.x` / `q`" in text
    data = json.loads(js.read_text(encoding="utf-8"))
    assert data["groups"]["g"]["adjusted_pct"] == 50.0
    assert data["groups"]["g"]["uncovered"] == [["g.x", "q"]]


# ----------------------------------------------------------- parity with the library itself
def test_merge_matches_cocotb_coverage_merge_coverage(tmp_path):
    """Two real exports, merged by the library and by this script, give the same bins and hits."""
    pytest.importorskip("cocotb_coverage")
    code = textwrap.dedent(
        """
        import sys
        from cocotb_coverage import coverage as cc

        @cc.CoverPoint("t.g.cp", xf=lambda v: v, bins=[1, 2, 3], bins_labels=["a", "b", "c"])
        @cc.CoverPoint("t.g.cq", xf=lambda v: v % 2, bins=[0, 1], bins_labels=["even", "odd"])
        @cc.CoverCross("t.g.x", items=["t.g.cp", "t.g.cq"])
        def sample(v):
            pass

        for v in map(int, sys.argv[2:]):
            sample(v)
        cc.coverage_db.export_to_yaml(sys.argv[1])
        """
    )
    first, second = tmp_path / "run1.yml", tmp_path / "run2.yml"
    for path, values in ((first, ["1", "1", "2"]), (second, ["3", "2"])):
        subprocess.run(
            [sys.executable, "-c", code, str(path), *values], check=True, capture_output=True
        )
    merge_code = textwrap.dedent(
        """
        import json, sys
        import yaml
        from cocotb_coverage.coverage import merge_coverage

        merge_coverage(lambda *_: None, sys.argv[1], sys.argv[2], sys.argv[3])
        print(json.dumps(yaml.safe_load(open(sys.argv[1], encoding="utf-8"))))
        """
    )
    lib_out = tmp_path / "lib.yml"
    lib_run = subprocess.run(
        [sys.executable, "-c", merge_code, str(lib_out), str(first), str(second)],
        check=True,
        capture_output=True,
        text=True,
    )
    lib = json.loads(lib_run.stdout)
    ours = fcr.merge([(p.name, fcr.load_yaml(p)) for p in (first, second)])
    for name, leaf_ in ours.items():
        assert dict(leaf_.hits) == lib[name]["bins:_hits"], name
        covered = sum(1 for k in leaf_.hits if leaf_.covered(k))
        assert covered == lib[name]["coverage"], name
    assert lib["t.g"]["coverage"] == sum(
        sum(1 for k in leaf_.hits if leaf_.covered(k)) for leaf_ in ours.values()
    )
