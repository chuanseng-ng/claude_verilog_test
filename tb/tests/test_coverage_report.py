"""Unit tests for tools/verif/coverage_report.py (GH #216, bead nkj7).

The report turns a merged Verilator ``coverage.dat`` from the SoC cocotb regression into a
per-module line + toggle table.  These tests pin the contract the ``soc_coverage`` Makefile
target and the nightly CI job depend on, using a small synthetic ``.dat`` whose key format was
copied from a real Verilator 5.048 file:

    C '<\\x01key\\x02value ...>' <count>

with keys ``f`` file, ``l`` line, ``n`` column, ``t`` type, ``page`` (``v_line|v_branch|v_toggle``
``/<module>``), ``o`` object, ``S`` source-line set and ``h`` instance hierarchy.

The properties that matter, each with a test below:
  * a coverage point is the same point in every instance (the hierarchy is dropped) and is hit
    when ANY instance hit it;
  * line % is ``v_line`` + ``v_branch``, toggle % is ``v_toggle``, kept separate;
  * only the triaged (``rtl/soc|periph|npu``) and informational (``rtl/cpu|mem|gpu``) trees are
    reported -- testbench files and behavioural SRAM models never are;
  * a waiver needs a justification and removes a point from the denominator, not the report;
  * empty or malformed input is an error, never a vacuous clean report (cf. bead dwp).
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "tools" / "verif" / "coverage_report.py"
_SPEC = importlib.util.spec_from_file_location("coverage_report", SCRIPT)
assert _SPEC and _SPEC.loader
cr = importlib.util.module_from_spec(_SPEC)
sys.modules["coverage_report"] = cr
_SPEC.loader.exec_module(cr)

ROOT = "/proj"
SOH, STX = "\x01", "\x02"
HEADER = "# SystemC::Coverage-3\n"


def point(
    *,
    kind: str,
    module: str,
    file: str,
    line: int,
    obj: str,
    count: int,
    hier: str = "tb.u_dut",
    src: str | None = None,
    col: int = 5,
) -> str:
    """Render one ``C '...' count`` record the way Verilator writes it."""
    t = {"line": "line", "branch": "branch", "toggle": "toggle"}[kind]
    page = f"v_{kind}/{module}"
    fields = [("f", f"{ROOT}/{file}"), ("l", str(line)), ("n", str(col)), ("t", t), ("page", page)]
    fields.append(("o", obj))
    if src is not None:
        fields.append(("S", src))
    fields.append(("h", hier))
    body = "".join(f"{SOH}{k}{STX}{v}" for k, v in fields)
    return f"C '{body}' {count}\n"


def write_dat(tmp_path: Path, *records: str, header: str = HEADER, name: str = "m.dat") -> Path:
    path = tmp_path / name
    path.write_text(header + "".join(records), encoding="utf-8")
    return path


# A small design: one periph module with 2 line blocks (1 hit) and a branch pair (1 hit), one
# toggle signal that never moves, one that moves both ways.
def periph_records(hier: str = "tb.u_dut", scale: int = 1) -> list[str]:
    f = "rtl/periph/foo.sv"
    return [
        point(
            kind="line",
            module="foo",
            file=f,
            line=10,
            obj="block",
            src="10",
            count=5 * scale,
            hier=hier,
        ),
        point(
            kind="line", module="foo", file=f, line=20, obj="block", src="20-21", count=0, hier=hier
        ),
        point(
            kind="branch",
            module="foo",
            file=f,
            line=30,
            obj="if",
            src="30",
            count=3 * scale,
            hier=hier,
        ),
        point(
            kind="branch", module="foo", file=f, line=30, obj="else", src="31", count=0, hier=hier
        ),
        point(kind="toggle", module="foo", file=f, line=3, obj="live:0->1", count=2, hier=hier),
        point(kind="toggle", module="foo", file=f, line=3, obj="live:1->0", count=2, hier=hier),
        point(kind="toggle", module="foo", file=f, line=4, obj="dead:0->1", count=0, hier=hier),
        point(kind="toggle", module="foo", file=f, line=4, obj="dead:1->0", count=0, hier=hier),
    ]


# --------------------------------------------------------------------------- parsing


def test_parse_reads_keys_and_count(tmp_path: Path) -> None:
    dat = write_dat(tmp_path, *periph_records())
    points = cr.parse_dat(dat)
    assert len(points) == 8
    first = points[0]
    assert (first.module, first.kind, first.line, first.count) == ("foo", "line", 10, 5)
    assert first.file == f"{ROOT}/rtl/periph/foo.sv"
    assert first.name == "block"
    assert first.hier == "tb.u_dut"
    kinds = sorted({p.kind for p in points})
    assert kinds == ["branch", "line", "toggle"]


def test_parse_rejects_missing_header(tmp_path: Path) -> None:
    dat = write_dat(tmp_path, *periph_records(), header="")
    with pytest.raises(cr.CoverageError, match="header"):
        cr.parse_dat(dat)


def test_parse_rejects_empty_file(tmp_path: Path) -> None:
    dat = write_dat(tmp_path)  # header only, zero points
    with pytest.raises(cr.CoverageError, match="no coverage points"):
        cr.parse_dat(dat)


def test_parse_rejects_malformed_record(tmp_path: Path) -> None:
    dat = write_dat(tmp_path, "C 'not a record'\n")
    with pytest.raises(cr.CoverageError, match="malformed"):
        cr.parse_dat(dat)


def test_parse_rejects_missing_file(tmp_path: Path) -> None:
    with pytest.raises(cr.CoverageError, match="missing"):
        cr.parse_dat(tmp_path / "absent.dat")


def test_parse_ignores_unknown_page_kinds(tmp_path: Path) -> None:
    # Verilator can also emit user/functional pages; they are not line/toggle and are skipped.
    body = f"{SOH}f{STX}{ROOT}/rtl/periph/foo.sv{SOH}l{STX}1{SOH}page{STX}v_user/foo{SOH}h{STX}x"
    odd = f"C '{body}' 4\n"
    dat = write_dat(tmp_path, *periph_records(), odd)
    assert len(cr.parse_dat(dat)) == 8


# ------------------------------------------------------------------ aggregation / percentages


def test_percentages_split_line_and_toggle(tmp_path: Path) -> None:
    dat = write_dat(tmp_path, *periph_records())
    report = cr.build_report(cr.parse_dat(dat), Path(ROOT), [])
    (row,) = report.modules
    assert row.module == "foo"
    assert row.tree == "rtl/periph"
    assert row.triaged is True
    # line + branch: 4 points, 2 hit
    assert (row.line_hit, row.line_total) == (2, 4)
    assert row.line_pct == pytest.approx(50.0)
    # toggle: 4 points, 2 hit
    assert (row.toggle_hit, row.toggle_total) == (2, 4)
    assert row.toggle_pct == pytest.approx(50.0)


def test_point_hit_in_any_instance_counts_once(tmp_path: Path) -> None:
    # Two instances of foo (two testbenches).  inst A hits only line 10; inst B hits only line 20.
    f = "rtl/periph/foo.sv"
    recs = [
        point(
            kind="line", module="foo", file=f, line=10, obj="block", src="10", count=4, hier="tbA.u"
        ),
        point(
            kind="line", module="foo", file=f, line=20, obj="block", src="20", count=0, hier="tbA.u"
        ),
        point(
            kind="line", module="foo", file=f, line=10, obj="block", src="10", count=0, hier="tbB.u"
        ),
        point(
            kind="line", module="foo", file=f, line=20, obj="block", src="20", count=7, hier="tbB.u"
        ),
    ]
    dat = write_dat(tmp_path, *recs)
    (row,) = cr.build_report(cr.parse_dat(dat), Path(ROOT), []).modules
    assert (row.line_hit, row.line_total) == (2, 2)  # union, not 2-of-4


def test_module_with_no_toggle_points_reports_none(tmp_path: Path) -> None:
    f = "rtl/soc/bar.sv"
    dat = write_dat(
        tmp_path, point(kind="line", module="bar", file=f, line=1, obj="block", src="1", count=1)
    )
    (row,) = cr.build_report(cr.parse_dat(dat), Path(ROOT), []).modules
    assert row.toggle_total == 0
    assert row.toggle_pct is None


def test_parameterised_variants_merge_into_the_base_module(tmp_path: Path) -> None:
    # Verilator names each parameter specialisation ``<module>__<params>`` (e.g.
    # ``apb4_register_bank__N8_Rz1_Wz2``).  Two builds of one RTL module are one module here, and
    # a point hit in either specialisation is hit.
    f = "rtl/soc/bank.sv"
    recs = [
        point(kind="line", module="bank__N8", file=f, line=10, obj="block", src="10", count=3),
        point(kind="line", module="bank__N8", file=f, line=20, obj="block", src="20", count=0),
        point(kind="line", module="bank__N2", file=f, line=10, obj="block", src="10", count=0),
        point(kind="line", module="bank__N2", file=f, line=20, obj="block", src="20", count=9),
    ]
    report = cr.build_report(cr.parse_dat(write_dat(tmp_path, *recs)), Path(ROOT), [])
    (row,) = report.modules
    assert row.module == "bank"
    assert (row.line_hit, row.line_total) == (2, 2)


# ------------------------------------------------------------------------------ tree filter


def test_tree_classification(tmp_path: Path) -> None:
    def rec(file: str, mod: str) -> str:
        return point(kind="line", module=mod, file=file, line=1, obj="block", src="1", count=1)

    dat = write_dat(
        tmp_path,
        rec("rtl/soc/a.sv", "a"),
        rec("rtl/periph/b.sv", "b"),
        rec("rtl/npu/c.sv", "c"),
        rec("rtl/cpu/core/d.sv", "d"),
        rec("rtl/mem/e.sv", "e"),
        rec("rtl/gpu/f.sv", "f"),
        rec("tb/cocotb/soc/tb_x.sv", "tb_x"),  # testbench
        rec(
            "rtl/mem/sram_1rw_256x32_freepdk45.sv", "sram_1rw_256x32_freepdk45"
        ),  # behavioural model
        rec("sim/sky130_sram_4kbyte_1rw1r_32x1024_8.sv", "sky130_sram"),  # behavioural model
    )
    report = cr.build_report(cr.parse_dat(dat), Path(ROOT), [])
    by_name = {m.module: m for m in report.modules}
    assert set(by_name) == {"a", "b", "c", "d", "e", "f"}
    assert all(by_name[n].triaged for n in "abc")
    assert not any(by_name[n].triaged for n in "def")
    assert by_name["d"].tree == "rtl/cpu"


def test_files_outside_root_are_ignored(tmp_path: Path) -> None:
    other = "C '{f}{s}/nix/store/x/include/verilated.sv{l}{s}1{p}{s}v_line/zz{h}{s}t' 1\n".format(
        f=SOH + "f", s=STX, l=SOH + "l", p=SOH + "page", h=SOH + "h"
    )
    dat = write_dat(tmp_path, *periph_records(), other)
    report = cr.build_report(cr.parse_dat(dat), Path(ROOT), [])
    assert [m.module for m in report.modules] == ["foo"]


def test_no_reportable_module_is_an_error(tmp_path: Path) -> None:
    dat = write_dat(
        tmp_path,
        point(kind="line", module="tb_x", file="tb/x.sv", line=1, obj="block", src="1", count=1),
    )
    with pytest.raises(cr.CoverageError, match="no reportable"):
        cr.build_report(cr.parse_dat(dat), Path(ROOT), [])


def test_no_triaged_module_is_an_error(tmp_path: Path) -> None:
    # Only an informational tree present: the triaged trees were never measured.
    dat = write_dat(
        tmp_path,
        point(kind="line", module="d", file="rtl/cpu/d.sv", line=1, obj="block", src="1", count=1),
    )
    with pytest.raises(cr.CoverageError, match="triaged"):
        cr.build_report(cr.parse_dat(dat), Path(ROOT), [])


# ----------------------------------------------------------------------------------- waivers


def test_waiver_file_requires_justification(tmp_path: Path) -> None:
    wf = tmp_path / "w.txt"
    wf.write_text("foo | toggle | ^dead | b |\n", encoding="utf-8")
    with pytest.raises(cr.CoverageError, match="justification"):
        cr.load_waivers(wf)


def test_waiver_file_rejects_bad_category_and_kind(tmp_path: Path) -> None:
    wf = tmp_path / "w.txt"
    wf.write_text("foo | toggle | ^dead | x | because\n", encoding="utf-8")
    with pytest.raises(cr.CoverageError, match="category"):
        cr.load_waivers(wf)
    wf.write_text("foo | nope | ^dead | b | because\n", encoding="utf-8")
    with pytest.raises(cr.CoverageError, match="kind"):
        cr.load_waivers(wf)


def test_waiver_file_rejects_bad_regex(tmp_path: Path) -> None:
    wf = tmp_path / "w.txt"
    wf.write_text("foo | toggle | ([ | b | because\n", encoding="utf-8")
    with pytest.raises(cr.CoverageError, match="regex"):
        cr.load_waivers(wf)


def test_waiver_comments_and_blank_lines_are_skipped(tmp_path: Path) -> None:
    wf = tmp_path / "w.txt"
    wf.write_text("# header\n\nfoo | toggle | ^dead | b | tied off\n", encoding="utf-8")
    (w,) = cr.load_waivers(wf)
    assert (w.module, w.kind, w.category, w.justification) == ("foo", "toggle", "b", "tied off")


def test_waiver_removes_points_from_denominator_but_keeps_raw(tmp_path: Path) -> None:
    dat = write_dat(tmp_path, *periph_records())
    waivers = [cr.Waiver("foo", "toggle", r"^dead:", "b", "tied to constant by design", 1)]
    report = cr.build_report(cr.parse_dat(dat), Path(ROOT), waivers)
    (row,) = report.modules
    assert row.toggle_waived == 2
    assert (row.toggle_hit, row.toggle_total) == (2, 2)  # adjusted
    assert row.toggle_pct == pytest.approx(100.0)
    assert row.toggle_raw_pct == pytest.approx(50.0)  # raw is still visible
    assert row.line_waived == 0


def test_waiver_matches_line_items_by_line_number(tmp_path: Path) -> None:
    dat = write_dat(tmp_path, *periph_records())
    waivers = [cr.Waiver("foo", "line", r"^L(20|30 else)$", "b", "elaboration guard", 1)]
    (row,) = cr.build_report(cr.parse_dat(dat), Path(ROOT), waivers).modules
    # line 20 block (not hit) and the else arm of the line-30 branch (not hit) are waived.  The
    # else arm is labelled by its own ``l`` (the ``if`` line, as Verilator writes it), with the
    # arm name; its body line (31) only appears in the span.
    assert row.line_waived == 2
    assert (row.line_hit, row.line_total) == (2, 2)


def test_waiver_does_not_hide_a_hit_point(tmp_path: Path) -> None:
    dat = write_dat(tmp_path, *periph_records())
    waivers = [cr.Waiver("foo", "toggle", r"^live:", "b", "wrongly broad", 1)]
    (row,) = cr.build_report(cr.parse_dat(dat), Path(ROOT), waivers).modules
    assert row.toggle_waived == 0  # only UNCOVERED points can be waived


def test_unused_waiver_is_reported(tmp_path: Path) -> None:
    dat = write_dat(tmp_path, *periph_records())
    waivers = [cr.Waiver("foo", "toggle", r"^nosuchsignal", "b", "stale", 7)]
    report = cr.build_report(cr.parse_dat(dat), Path(ROOT), waivers)
    assert [w.lineno for w in report.unused_waivers] == [7]


def test_waiver_for_other_module_does_not_apply(tmp_path: Path) -> None:
    dat = write_dat(tmp_path, *periph_records())
    waivers = [cr.Waiver("bar", "toggle", r"^dead:", "b", "other module", 1)]
    (row,) = cr.build_report(cr.parse_dat(dat), Path(ROOT), waivers).modules
    assert row.toggle_waived == 0


# --------------------------------------------------------------------------- uncovered lists


def test_uncovered_lists_are_precise(tmp_path: Path) -> None:
    dat = write_dat(tmp_path, *periph_records())
    (row,) = cr.build_report(cr.parse_dat(dat), Path(ROOT), []).modules
    assert sorted(i.label for i in row.uncovered_lines) == ["L20", "L30 else"]
    # Toggle items are grouped per signal; a signal with zero hit points is "never toggles".
    (sig,) = row.uncovered_toggles
    assert sig.signal == "dead"
    assert (sig.hit, sig.total) == (0, 2)
    assert sig.never_toggles is True


def generate_loop_records(hier: str = "tb.u_dut") -> list[str]:
    """Points inside a generate loop, as Verilator 5.048 writes them (pmu.sv, GH #222 T1).

    Every point in the loop body carries ``S=<loop header line>,<own line>`` while its ``l`` key is
    its OWN line, so the first number of ``S`` is the ``for`` header, not where the point is.
    """
    f = "rtl/soc/gen.sv"
    return [
        point(
            kind="line",
            module="gen",
            file=f,
            line=290,
            obj="case",
            src="277,290",
            count=4,
            hier=hier,
        ),
        point(
            kind="line",
            module="gen",
            file=f,
            line=294,
            obj="case",
            src="277,294",
            count=0,
            hier=hier,
        ),
        point(
            kind="line",
            module="gen",
            file=f,
            line=365,
            obj="case",
            src="277,365-370",
            count=0,
            hier=hier,
        ),
    ]


def test_line_label_uses_the_points_own_line_not_the_span_start(tmp_path: Path) -> None:
    """GH #222 T1: a generate-loop point is labelled L294, not the loop header L277."""
    dat = write_dat(tmp_path, *generate_loop_records())
    (row,) = cr.build_report(cr.parse_dat(dat), Path(ROOT), []).modules
    assert sorted(g.label for g in row.uncovered_lines) == ["L294", "L365"]
    assert sorted(g.line for g in row.uncovered_lines) == [294, 365]
    # the span is kept, so the report can still show where the enclosing loop starts
    assert {g.span for g in row.uncovered_lines} == {"277,294", "277,365-370"}


def test_generate_loop_waiver_targets_the_own_line(tmp_path: Path) -> None:
    dat = write_dat(tmp_path, *generate_loop_records())
    stale = [cr.Waiver("gen", "line", r"^L277\b", "b", "header line, no such point", 1)]
    right = [cr.Waiver("gen", "line", r"^L(294|365)\b", "b", "own lines", 2)]
    (row,) = cr.build_report(cr.parse_dat(dat), Path(ROOT), stale).modules
    assert row.line_waived == 0  # the old span-start label no longer exists
    report = cr.build_report(cr.parse_dat(dat), Path(ROOT), right)
    assert report.modules[0].line_waived == 2
    assert (report.modules[0].line_hit, report.modules[0].line_total) == (1, 1)
    assert report.unused_waivers == []


def test_generate_loop_gap_shows_the_span_in_markdown(tmp_path: Path) -> None:
    dat = write_dat(tmp_path, *generate_loop_records())
    md = cr.render_markdown(cr.build_report(cr.parse_dat(dat), Path(ROOT), []))
    assert "L294 (span 277,294)" in md
    assert "L365 (span 277,365-370)" in md
    # a plain block whose span starts at its own line stays bare
    dat2 = write_dat(tmp_path, *periph_records(), name="p.dat")
    md2 = cr.render_markdown(cr.build_report(cr.parse_dat(dat2), Path(ROOT), []))
    assert "L20," in md2 or "L20 " in md2
    assert "(span 20" not in md2


def test_partially_toggled_signal_is_listed_but_not_flagged_never(tmp_path: Path) -> None:
    f = "rtl/periph/foo.sv"
    recs = [
        point(kind="line", module="foo", file=f, line=1, obj="block", src="1", count=1),
        point(kind="toggle", module="foo", file=f, line=2, obj="half[0]:0->1", count=1),
        point(kind="toggle", module="foo", file=f, line=2, obj="half[0]:1->0", count=0),
    ]
    (row,) = cr.build_report(cr.parse_dat(write_dat(tmp_path, *recs)), Path(ROOT), []).modules
    (sig,) = row.uncovered_toggles
    assert (sig.signal, sig.hit, sig.total, sig.never_toggles) == ("half", 1, 2, False)


def test_vector_bits_group_under_one_signal(tmp_path: Path) -> None:
    f = "rtl/periph/foo.sv"
    recs = [point(kind="line", module="foo", file=f, line=1, obj="block", src="1", count=1)]
    for bit in range(4):
        for d in ("0->1", "1->0"):
            recs.append(
                point(kind="toggle", module="foo", file=f, line=2, obj=f"bus[{bit}]:{d}", count=0)
            )
    (row,) = cr.build_report(cr.parse_dat(write_dat(tmp_path, *recs)), Path(ROOT), []).modules
    (sig,) = row.uncovered_toggles
    assert (sig.signal, sig.total, sig.never_toggles) == ("bus", 8, True)


# ------------------------------------------------------------------------------ rendering


def test_markdown_has_sections_and_numbers(tmp_path: Path) -> None:
    dat = write_dat(tmp_path, *periph_records())
    waivers = [cr.Waiver("foo", "toggle", r"^dead:", "b", "tied to constant by design", 1)]
    report = cr.build_report(cr.parse_dat(dat), Path(ROOT), waivers)
    md = cr.render_markdown(report)
    assert "Triaged" in md and "Informational" in md
    assert "| foo |" in md
    assert "50.0" in md  # line %
    assert "L20" in md  # uncovered list
    assert "tied to constant by design" in md  # waiver justification surfaced


def test_json_round_trips_totals(tmp_path: Path) -> None:
    dat = write_dat(tmp_path, *periph_records())
    report = cr.build_report(cr.parse_dat(dat), Path(ROOT), [])
    data = json.loads(json.dumps(cr.report_to_dict(report)))
    (mod,) = data["modules"]
    assert mod["module"] == "foo"
    assert mod["line"] == {"hit": 2, "total": 4, "waived": 0, "pct": 50.0, "raw_pct": 50.0}
    assert data["summary"]["triaged"]["line_total"] == 4


# --------------------------------------------------------------------------------- the CLI


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args], capture_output=True, text=True, check=False
    )


def test_cli_writes_outputs_and_exits_zero_even_with_low_coverage(tmp_path: Path) -> None:
    dat = write_dat(tmp_path, *periph_records())
    md, js = tmp_path / "r.md", tmp_path / "r.json"
    waivers = tmp_path / "w.txt"
    waivers.write_text("# none\n", encoding="utf-8")
    proc = run_cli(
        "--dat",
        str(dat),
        "--root",
        ROOT,
        "--waivers",
        str(waivers),
        "--out-md",
        str(md),
        "--out-json",
        str(js),
    )
    assert proc.returncode == 0, proc.stderr  # informational: coverage % never gates
    assert "| foo |" in md.read_text(encoding="utf-8")
    assert json.loads(js.read_text(encoding="utf-8"))["modules"][0]["module"] == "foo"


def test_cli_fails_on_empty_data(tmp_path: Path) -> None:
    dat = write_dat(tmp_path)
    proc = run_cli("--dat", str(dat), "--root", ROOT)
    assert proc.returncode != 0
    assert "no coverage points" in proc.stderr


def test_cli_fails_on_missing_dat(tmp_path: Path) -> None:
    proc = run_cli("--dat", str(tmp_path / "nope.dat"), "--root", ROOT)
    assert proc.returncode != 0


def test_cli_fails_on_bad_waiver_file(tmp_path: Path) -> None:
    dat = write_dat(tmp_path, *periph_records())
    waivers = tmp_path / "w.txt"
    waivers.write_text("foo | toggle | ^dead | b |\n", encoding="utf-8")
    proc = run_cli("--dat", str(dat), "--root", ROOT, "--waivers", str(waivers))
    assert proc.returncode != 0
    assert "justification" in proc.stderr


# ------------------------------------------------------------- multi-input merge (bead 1eyv)
#
# The combined report merges the SoC regression's ``merged.dat`` with the CPU/cache/GPU suites'
# ``.dat`` files.  They come from different checkouts (absolute paths differ: a developer
# worktree, a CI runner), so the report must normalise to repo-relative paths itself, and the
# points of one RTL file measured by two inputs must be one point, hit if either input hit it.

FOREIGN_ROOTS = (
    "/home/runner/work/claude_verilog_test/claude_verilog_test",
    "/home/dev/Github/repo/.claude/worktrees/agent-abc123",
)


def foreign_point(root: str, **kw: object) -> str:
    """A ``point()`` record whose file lives under a different checkout root."""
    rec = point(**kw)  # type: ignore[arg-type]
    return rec.replace(f"{ROOT}/", f"{root}/", 1)


def cpu_records(hit_line: int, root: str | None = None) -> list[str]:
    """Two line blocks of an informational-tree module; only ``hit_line`` is hit."""
    out = []
    for ln in (10, 20):
        kw: dict[str, object] = {
            "kind": "line",
            "module": "dec",
            "file": "rtl/cpu/core/dec.sv",
            "line": ln,
            "obj": "block",
            "src": str(ln),
            "count": int(ln == hit_line),
        }
        out.append(point(**kw) if root is None else foreign_point(root, **kw))  # type: ignore[arg-type]
    return out


@pytest.mark.parametrize("root", FOREIGN_ROOTS)
def test_paths_from_another_checkout_normalise_to_repo_relative(tmp_path: Path, root: str) -> None:
    rec = foreign_point(
        root, kind="line", module="foo", file="rtl/periph/foo.sv", line=10, obj="b", count=1
    )
    report = cr.build_report(cr.parse_dat(write_dat(tmp_path, rec)), Path(ROOT), [])
    assert [(m.module, m.file) for m in report.modules] == [("foo", "rtl/periph/foo.sv")]


def test_dotdot_relative_path_normalises(tmp_path: Path) -> None:
    # Verilator run from sim/ can record ../rtl/... for sources named relative to it.
    rec = point(
        kind="line", module="foo", file="rtl/periph/foo.sv", line=1, obj="b", src="1", count=1
    ).replace(f"{ROOT}/rtl/periph", "../rtl/periph")
    report = cr.build_report(cr.parse_dat(write_dat(tmp_path, rec)), Path(ROOT), [])
    assert report.modules[0].file == "rtl/periph/foo.sv"


def test_foreign_root_testbench_files_stay_excluded(tmp_path: Path) -> None:
    tb = foreign_point(
        FOREIGN_ROOTS[0],
        kind="line",
        module="tb_x",
        file="tb/cocotb/soc/tb_x.sv",
        line=1,
        obj="b",
        count=1,
    )
    dat = write_dat(tmp_path, *periph_records(), tb)
    report = cr.build_report(cr.parse_dat(dat), Path(ROOT), [])
    assert [m.module for m in report.modules] == ["foo"]


def test_two_inputs_with_different_roots_merge_into_one_report(tmp_path: Path) -> None:
    soc = write_dat(tmp_path, *periph_records(), name="soc.dat")
    cpu = write_dat(tmp_path, *cpu_records(10, FOREIGN_ROOTS[0]), name="cpu.dat")
    report = cr.build_report(cr.parse_dat(soc) + cr.parse_dat(cpu), Path(ROOT), [])
    by_name = {m.module: m for m in report.modules}
    assert set(by_name) == {"foo", "dec"}
    assert by_name["dec"].tree == "rtl/cpu" and not by_name["dec"].triaged
    assert (by_name["dec"].line_hit, by_name["dec"].line_total) == (1, 2)


def test_point_hit_in_either_input_counts_as_hit_and_is_counted_once(tmp_path: Path) -> None:
    a = write_dat(tmp_path, *cpu_records(10), name="a.dat")  # hits L10
    b = write_dat(tmp_path, *cpu_records(20, FOREIGN_ROOTS[1]), name="b.dat")  # hits L20
    soc = write_dat(tmp_path, *periph_records(), name="soc.dat")
    only_a = cr.build_report(cr.parse_dat(soc) + cr.parse_dat(a), Path(ROOT), [])
    both = cr.build_report(cr.parse_dat(soc) + cr.parse_dat(a) + cr.parse_dat(b), Path(ROOT), [])
    dec_a = next(m for m in only_a.modules if m.module == "dec")
    dec = next(m for m in both.modules if m.module == "dec")
    assert (dec_a.line_hit, dec_a.line_total) == (1, 2)
    assert (dec.line_hit, dec.line_total) == (2, 2)  # union of hits, not a sum of points
    assert dec.uncovered_lines == []


def test_identical_point_sets_report_no_mismatch(tmp_path: Path) -> None:
    a = write_dat(tmp_path, *cpu_records(10), name="a.dat")
    b = write_dat(tmp_path, *cpu_records(20, FOREIGN_ROOTS[0]), name="b.dat")
    soc = write_dat(tmp_path, *periph_records(), name="soc.dat")
    points = cr.parse_dat(soc) + cr.parse_dat(a) + cr.parse_dat(b)
    assert cr.build_report(points, Path(ROOT), []).consistency == []


def test_module_in_one_input_only_is_not_a_mismatch(tmp_path: Path) -> None:
    soc = write_dat(tmp_path, *periph_records(), name="soc.dat")
    cpu = write_dat(tmp_path, *cpu_records(10), name="cpu.dat")
    report = cr.build_report(cr.parse_dat(soc) + cr.parse_dat(cpu), Path(ROOT), [])
    assert report.consistency == []


def mismatched_inputs(tmp_path: Path) -> list[Any]:
    """Same module and file, but input B's points are at other lines (e.g. another Verilator)."""
    a = write_dat(tmp_path, *cpu_records(10), name="a.dat")
    shifted = [
        point(
            kind="line",
            module="dec",
            file="rtl/cpu/core/dec.sv",
            line=ln,
            obj="block",
            src=str(ln),
            count=1,
        )
        for ln in (11, 21)
    ]
    b = write_dat(tmp_path, *shifted, name="b.dat")
    soc = write_dat(tmp_path, *periph_records(), name="soc.dat")
    merged: list[Any] = cr.parse_dat(soc) + cr.parse_dat(a) + cr.parse_dat(b)
    return merged


def test_mismatched_point_sets_are_flagged_and_never_inflate_coverage(tmp_path: Path) -> None:
    report = cr.build_report(mismatched_inputs(tmp_path), Path(ROOT), [])
    dec = next(m for m in report.modules if m.module == "dec")
    # Union semantics: four distinct points, three hit (L10 from a, L11 + L21 from b); the
    # shifted input's hits are NOT credited to the other input's points, and the denominator is
    # not silently shrunk to the overlap.
    assert (dec.line_hit, dec.line_total) == (3, 4)
    assert len(report.consistency) == 1
    row = report.consistency[0]
    assert (row.module, row.shared, row.total) == ("dec", 0, 4)
    assert row.suspect
    assert row.only_in == {"a.dat": 2, "b.dat": 2}


def test_mismatch_appears_in_markdown_and_json(tmp_path: Path) -> None:
    report = cr.build_report(mismatched_inputs(tmp_path), Path(ROOT), [])
    md = cr.render_markdown(report)
    assert "Cross-input point-set consistency" in md
    assert "SUSPECT" in md
    data = cr.report_to_dict(report)
    assert data["consistency"][0]["module"] == "dec"
    assert data["consistency"][0]["suspect"] is True


def test_input_contributing_nothing_reportable_is_an_error(tmp_path: Path) -> None:
    soc = write_dat(tmp_path, *periph_records(), name="soc.dat")
    # Wrong tree entirely: a clean-looking merge would otherwise hide that this input was lost.
    junk = write_dat(
        tmp_path,
        point(kind="line", module="tb_x", file="tb/x.sv", line=1, obj="b", src="1", count=1),
        name="junk.dat",
    )
    with pytest.raises(cr.CoverageError, match="junk.dat"):
        cr.build_report(cr.parse_dat(soc) + cr.parse_dat(junk), Path(ROOT), [])


def test_report_lists_each_input_with_its_reportable_points(tmp_path: Path) -> None:
    soc = write_dat(tmp_path, *periph_records(), name="soc.dat")
    cpu = write_dat(tmp_path, *cpu_records(10), name="cpu.dat")
    report = cr.build_report(cr.parse_dat(soc) + cr.parse_dat(cpu), Path(ROOT), [])
    assert {i.name: i.reportable for i in report.inputs} == {"soc.dat": 8, "cpu.dat": 2}
    assert [i["name"] for i in cr.report_to_dict(report)["inputs"]] == ["soc.dat", "cpu.dat"]


def test_cli_accepts_repeated_dat_and_merges(tmp_path: Path) -> None:
    soc = write_dat(tmp_path, *periph_records(), name="soc.dat")
    cpu = write_dat(tmp_path, *cpu_records(10, FOREIGN_ROOTS[0]), name="cpu.dat")
    js = tmp_path / "r.json"
    proc = run_cli("--dat", str(soc), "--dat", str(cpu), "--root", ROOT, "--out-json", str(js))
    assert proc.returncode == 0, proc.stderr
    names = {m["module"] for m in json.loads(js.read_text(encoding="utf-8"))["modules"]}
    assert names == {"foo", "dec"}


def test_cli_fails_when_any_input_is_missing(tmp_path: Path) -> None:
    soc = write_dat(tmp_path, *periph_records(), name="soc.dat")
    proc = run_cli("--dat", str(soc), "--dat", str(tmp_path / "gone.dat"), "--root", ROOT)
    assert proc.returncode != 0
    assert "gone.dat" in proc.stderr
