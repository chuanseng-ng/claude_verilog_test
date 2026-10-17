"""Unit tests for content-anchored line waivers in tools/verif/coverage_report.py (bead xlc4).

Line waivers used to be keyed on absolute line numbers (``^L284\\b``).  Any edit above a waived
point silently un-waived it, and the report only warned: PR #279 shifted ``sram_controller.sv``
by +16 lines and turned the main ``soc_coverage`` gate red until PR #290 re-keyed it.  A line
waiver is now anchored on the stripped TEXT of the waived source line::

    module | line | @"default: state_q <= S_IDLE;" | b | why

with an ordinal ``#k/N`` for identical lines.  The properties pinned here:

  * an edit ABOVE the waived line (any shift) keeps the waiver valid;
  * an edit to the waived line itself (its code, not its comment or spacing) makes the waiver
    STALE, and ``--gate`` then FAILS even though the coverage floors are still met;
  * an anchor matching several lines with no ordinal is an ERROR, never a silent pick, and a
    changed count of identical lines makes an ordinal anchor stale instead of re-pointing;
  * a legacy numeric line waiver is rejected by the loader;
  * the migration of numeric waivers resolves to exactly the old line numbers;
  * the report of an anchored waiver is identical to the report of the numeric waiver it
    replaced.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "tools" / "verif" / "coverage_report.py"
_SPEC = importlib.util.spec_from_file_location("coverage_report_anchors", SCRIPT)
assert _SPEC and _SPEC.loader
cr = importlib.util.module_from_spec(_SPEC)
sys.modules["coverage_report_anchors"] = cr
_SPEC.loader.exec_module(cr)

SOH, STX = "\x01", "\x02"
HEADER = "# SystemC::Coverage-3\n"
FSM_FILE = "rtl/periph/fsm.sv"
DEFAULT_ARM = "default: state_q <= S_IDLE;"


# ------------------------------------------------------------------------------- fixtures


def _record(module: str, file: str, line: int, count: int) -> str:
    fields = [
        ("f", f"/elsewhere/{file}"),
        ("l", str(line)),
        ("n", "5"),
        ("t", "line"),
        ("page", f"v_line/{module}"),
        ("o", "block"),
        ("S", str(line)),
        ("h", "tb.u_dut"),
    ]
    body = "".join(f"{SOH}{k}{STX}{v}" for k, v in fields)
    return f"C '{body}' {count}\n"


class Repo:
    """A one-module mini repo: ``rtl/periph/fsm.sv`` with a hit arm and an unreachable default."""

    def __init__(self, root: Path, *, pad: int = 0, default_text: str = DEFAULT_ARM) -> None:
        self.root = root
        pads = [f"// padding {i}" for i in range(pad)]
        body = [
            "module fsm (input logic clk);",
            "  always_ff @(posedge clk) begin",
            "    case (state_q)",
            "      S_IDLE: state_q <= S_RUN;",
            "      S_RUN:  state_q <= S_IDLE;",
            f"      {default_text}",
            "    endcase",
            "  end",
            "endmodule",
        ]
        self.lines = pads + body
        self.hit_line = pad + 4
        self.default_line = pad + 6
        path = root / FSM_FILE
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(self.lines) + "\n", encoding="utf-8")

    def dat(self, tmp_path: Path, *, extra_hit_points: int = 0) -> Path:
        """A .dat with one hit arm, the uncovered default, and N more hit points to pad the %."""
        recs = [
            _record("fsm", FSM_FILE, self.hit_line, 7),
            _record("fsm", FSM_FILE, self.default_line, 0),
        ]
        recs += [_record("fsm", FSM_FILE, 1000 + i, 3) for i in range(extra_hit_points)]
        path = tmp_path / "m.dat"
        path.write_text(HEADER + "".join(recs), encoding="utf-8")
        return path


def anchored(text: str = DEFAULT_ARM, lineno: int = 1) -> object:
    return cr.Waiver(
        "fsm",
        "line",
        f'@"{text}"',
        "b",
        "unreachable default arm",
        lineno,
        anchors=cr.parse_anchors(f'@"{text}"', "t"),
    )


def report_of(repo: Repo, tmp_path: Path, waivers: list, **kw: int):
    return cr.build_report(cr.parse_dat(repo.dat(tmp_path, **kw)), repo.root, waivers)


# ---------------------------------------------------------------------- anchor text rules


def test_normalise_strips_comments_and_collapses_spacing() -> None:
    norm = cr.normalize_source_line
    assert norm("      default:   state_q <= S_IDLE;   // never taken") == DEFAULT_ARM
    assert norm("default: x = 1; /* inline */ ") == "default: x = 1;"
    assert norm('s = "a // not a comment";') == 's = "a // not a comment";'
    assert norm("   // only a comment") == ""


def test_parse_anchor_forms() -> None:
    (a,) = cr.parse_anchors('@"default: begin"', "t")
    assert (a.text, a.ordinal, a.count) == ("default: begin", None, None)
    (b,) = cr.parse_anchors('@"default: begin"#2/3', "t")
    assert (b.ordinal, b.count) == (2, 3)
    one, two = cr.parse_anchors('@"a;" @"b;"#1/2', "t")
    assert (one.text, two.text, two.ordinal) == ("a;", "b;", 1)
    (q,) = cr.parse_anchors(r'@"x = \"y\";"', "t")
    assert q.text == 'x = "y";'


@pytest.mark.parametrize(
    "spec",
    [
        '@"default: begin',  # unterminated
        '@""',  # empty
        '@"x;"#3/2',  # ordinal beyond the count
        '@"x;"#0/2',  # ordinals start at 1
        '@"x;" trailing',  # junk after the last anchor
        '@"// only a comment"',  # nothing left after normalisation
        "@default",  # not quoted
    ],
)
def test_parse_anchor_rejects_malformed_specs(spec: str) -> None:
    with pytest.raises(cr.CoverageError):
        cr.parse_anchors(spec, "t")


# ----------------------------------------------------------------- the four core contracts


def test_shift_above_the_waived_line_keeps_the_waiver(tmp_path: Path) -> None:
    base = Repo(tmp_path / "a")
    shifted = Repo(tmp_path / "b", pad=16)  # the PR #279 case: +16 lines above
    for repo in (base, shifted):
        rep = report_of(repo, tmp_path, [anchored()])
        (row,) = rep.modules
        assert row.line_waived == 1, repo.default_line
        assert (row.line_hit, row.line_total) == (1, 1)
        assert rep.stale_waivers == []
        assert rep.unused_waivers == []
        assert rep.resolutions[1].lines == (repo.default_line,)


def test_edit_to_the_waived_line_makes_it_stale_and_the_gate_fail(tmp_path: Path) -> None:
    edited = Repo(tmp_path / "e", default_text="default: state_q <= S_ERROR;")
    # 99 extra hit points: the line floor is met even WITHOUT the waiver, so only the stale
    # check can make this gate fail.
    rep = report_of(edited, tmp_path, [anchored()], extra_hit_points=99)
    (row,) = rep.modules
    assert row.line_waived == 0  # nothing is silently waived any more
    assert [w.lineno for w in rep.stale_waivers] == [1]
    assert rep.resolutions[1].status == "stale"
    gate = cr.evaluate_gate(rep, cr.GateConfig())
    assert not gate.passed
    assert [f.check for f in gate.failures] == ["stale-waiver"]
    assert "fsm" in gate.failures[0].detail


def test_gate_passes_when_the_waiver_resolves(tmp_path: Path) -> None:
    repo = Repo(tmp_path / "ok", pad=40)
    rep = report_of(repo, tmp_path, [anchored()])
    assert cr.evaluate_gate(rep, cr.GateConfig()).passed


def test_comment_or_spacing_change_on_the_waived_line_is_not_a_code_edit(tmp_path: Path) -> None:
    repo = Repo(tmp_path / "c", default_text="default:   state_q <= S_IDLE;   // reworded note")
    rep = report_of(repo, tmp_path, [anchored()])
    assert rep.stale_waivers == []
    assert rep.modules[0].line_waived == 1


def test_ambiguous_anchor_is_an_error_not_a_silent_pick(tmp_path: Path) -> None:
    repo = Repo(tmp_path / "amb")
    path = tmp_path / "amb" / FSM_FILE
    path.write_text(
        path.read_text(encoding="utf-8").replace("endmodule", f"  {DEFAULT_ARM}\nendmodule"),
        encoding="utf-8",
    )
    with pytest.raises(cr.CoverageError, match=r"ambiguous.*(6.*9|9.*6)"):
        report_of(repo, tmp_path, [anchored()])


def test_ordinal_anchor_selects_the_kth_identical_line(tmp_path: Path) -> None:
    repo = Repo(tmp_path / "ord")
    path = tmp_path / "ord" / FSM_FILE
    path.write_text(
        path.read_text(encoding="utf-8").replace("endmodule", f"  {DEFAULT_ARM}\nendmodule"),
        encoding="utf-8",
    )
    first = cr.Waiver(
        "fsm",
        "line",
        '@"x"#1/2',
        "b",
        "j",
        1,
        anchors=cr.parse_anchors(f'@"{DEFAULT_ARM}"#1/2', "t"),
    )
    second = cr.Waiver(
        "fsm",
        "line",
        '@"x"#2/2',
        "b",
        "j",
        2,
        anchors=cr.parse_anchors(f'@"{DEFAULT_ARM}"#2/2', "t"),
    )
    res = cr.resolve_waivers([first, second], repo.root)
    assert res[1].lines == (6,) and res[2].lines == (9,)


def test_count_change_makes_an_ordinal_anchor_stale_instead_of_repointing(tmp_path: Path) -> None:
    repo = Repo(tmp_path / "cnt")  # only ONE identical line, the anchor says 1 of 2
    waiver = cr.Waiver(
        "fsm",
        "line",
        "x",
        "b",
        "j",
        1,
        anchors=cr.parse_anchors(f'@"{DEFAULT_ARM}"#2/2', "t"),
    )
    res = cr.resolve_waivers([waiver], repo.root)
    assert res[1].status == "stale"
    assert "1 line" in res[1].problems[0] and "2" in res[1].problems[0]


# ---------------------------------------------------------------------- resolution failures


def test_unknown_module_is_stale(tmp_path: Path) -> None:
    repo = Repo(tmp_path / "m")
    waiver = cr.Waiver(
        "ghost", "line", "x", "b", "j", 3, anchors=cr.parse_anchors(f'@"{DEFAULT_ARM}"', "t")
    )
    res = cr.resolve_waivers([waiver], repo.root)
    assert res[3].status == "stale"
    assert "ghost" in res[3].problems[0]


def test_module_declared_in_two_files_is_an_error(tmp_path: Path) -> None:
    repo = Repo(tmp_path / "dup")
    other = tmp_path / "dup" / "rtl" / "soc" / "fsm_copy.sv"
    other.parent.mkdir(parents=True)
    other.write_text("module fsm;\nendmodule\n", encoding="utf-8")
    with pytest.raises(cr.CoverageError, match="declared in"):
        cr.resolve_waivers([anchored()], repo.root)


def test_multi_anchor_waiver_partial_staleness_keeps_the_resolved_targets(
    tmp_path: Path,
) -> None:
    repo = Repo(tmp_path / "multi")
    waiver = cr.Waiver(
        "fsm",
        "line",
        "x",
        "b",
        "j",
        1,
        anchors=cr.parse_anchors(f'@"{DEFAULT_ARM}" @"no such line;"', "t"),
    )
    res = cr.resolve_waivers([waiver], repo.root)[1]
    assert res.status == "stale"
    assert res.lines == (repo.default_line,)  # the good target is still honoured


# --------------------------------------------------------------------------- the file format


def write_waivers(path: Path, *entries: str) -> Path:
    path.write_text("# header\n" + "\n".join(entries) + "\n", encoding="utf-8")
    return path


def test_loader_reads_an_anchored_line_waiver(tmp_path: Path) -> None:
    wf = write_waivers(tmp_path / "w.txt", f'fsm | line | @"{DEFAULT_ARM}" | b | dead default')
    (w,) = cr.load_waivers(wf)
    assert w.anchors[0].text == DEFAULT_ARM
    assert w.justification == "dead default"
    assert w.lineno == 2


def test_loader_rejects_a_numeric_line_waiver(tmp_path: Path) -> None:
    wf = write_waivers(tmp_path / "w.txt", "fsm | line | ^L(284|667)\\b | b | dead default")
    with pytest.raises(cr.CoverageError, match="content-anchored"):
        cr.load_waivers(wf)
    wf = write_waivers(tmp_path / "w2.txt", "fsm | any | ^L284\\b | b | dead default")
    with pytest.raises(cr.CoverageError, match="content-anchored"):
        cr.load_waivers(wf)


def test_loader_rejects_an_anchor_on_a_toggle_waiver(tmp_path: Path) -> None:
    wf = write_waivers(tmp_path / "w.txt", f'fsm | toggle | @"{DEFAULT_ARM}" | b | nope')
    with pytest.raises(cr.CoverageError, match="line"):
        cr.load_waivers(wf)


def test_loader_still_accepts_toggle_regexes(tmp_path: Path) -> None:
    wf = write_waivers(tmp_path / "w.txt", "fsm | toggle | ^pslverr: | b | tied off")
    (w,) = cr.load_waivers(wf)
    assert w.anchors == ()


def test_anchored_waiver_gives_the_same_report_as_the_numeric_one_it_replaces(
    tmp_path: Path,
) -> None:
    repo = Repo(tmp_path / "eq", pad=3)
    numeric = cr.Waiver(
        "fsm", "line", rf"^L{repo.default_line}\b", "b", "unreachable default arm", 1
    )
    old = report_of(repo, tmp_path, [numeric])
    new = report_of(repo, tmp_path, [anchored()])
    old_row, new_row = old.modules[0], new.modules[0]
    for attr in ("line_hit", "line_total", "line_waived", "line_pct", "line_raw_pct"):
        assert getattr(old_row, attr) == getattr(new_row, attr), attr
    assert old.waiver_hits == new.waiver_hits


# ---------------------------------------------------------------------------------- migration

LEGACY_SRC = """\
module fsm;
  case (a)
    X: a <= 1;
    default: a <= IDLE;
  endcase
  case (b)
    Y: b <= 1;
    default: a <= IDLE;
  endcase
  if (p && q) begin
    z <= 1;
  end
endmodule
"""


def legacy_text() -> str:
    return (
        "# header comment, kept verbatim\n"
        "\n"
        "fsm | line | ^L(4|8)\\b | b | two identical defaults\n"
        "fsm | line | ^L10\\b | b | a unique if\n"
        "fsm | toggle | ^pslverr: | b | untouched toggle waiver\n"
    )


def test_migration_resolves_to_exactly_the_old_line_numbers(tmp_path: Path) -> None:
    src = tmp_path / "rtl" / "periph" / "fsm.sv"
    src.parent.mkdir(parents=True)
    src.write_text(LEGACY_SRC, encoding="utf-8")
    old = write_waivers(tmp_path / "old.txt")
    old.write_text(legacy_text(), encoding="utf-8")

    migrated = cr.migrate_legacy_waivers(legacy_text(), tmp_path)
    new = tmp_path / "new.txt"
    new.write_text(migrated, encoding="utf-8")
    waivers = cr.load_waivers(new)  # the migrated file is a valid waiver file
    res = cr.resolve_waivers(waivers, tmp_path)

    assert res[3].lines == (4, 8)  # the ambiguous pair needed ordinals
    assert res[4].lines == (10,)
    assert all(r.status == "ok" for r in res.values())
    # everything that is not a legacy line regex is preserved byte for byte
    out = migrated.splitlines()
    assert out[0] == "# header comment, kept verbatim"
    assert out[4] == "fsm | toggle | ^pslverr: | b | untouched toggle waiver"
    assert "#1/2" in out[2] and "#2/2" in out[2]
    assert out[2].endswith("| b | two identical defaults")


def test_migration_is_idempotent(tmp_path: Path) -> None:
    src = tmp_path / "rtl" / "periph" / "fsm.sv"
    src.parent.mkdir(parents=True)
    src.write_text(LEGACY_SRC, encoding="utf-8")
    once = cr.migrate_legacy_waivers(legacy_text(), tmp_path)
    assert cr.migrate_legacy_waivers(once, tmp_path) == once


def test_migration_refuses_a_numeric_waiver_that_points_at_no_code(tmp_path: Path) -> None:
    src = tmp_path / "rtl" / "periph" / "fsm.sv"
    src.parent.mkdir(parents=True)
    src.write_text(LEGACY_SRC, encoding="utf-8")
    with pytest.raises(cr.CoverageError, match="line 99"):
        cr.migrate_legacy_waivers("fsm | line | ^L99\\b | b | gone\n", tmp_path)


# ------------------------------------------------------------------------------------- CLI


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args], capture_output=True, text=True, check=False
    )


def anchored_file(tmp_path: Path) -> Path:
    return write_waivers(tmp_path / "w.txt", f'fsm | line | @"{DEFAULT_ARM}" | b | dead default')


def test_cli_gate_fails_on_a_stale_waiver_but_the_plain_report_only_warns(tmp_path: Path) -> None:
    repo = Repo(tmp_path / "r", default_text="default: state_q <= S_ERROR;")
    dat = repo.dat(tmp_path, extra_hit_points=99)
    base = ["--dat", str(dat), "--root", str(repo.root), "--waivers", str(anchored_file(tmp_path))]
    plain = run_cli(*base)
    assert plain.returncode == 0, plain.stderr  # informational run: a warning, not a failure
    assert "stale" in plain.stderr
    gated = run_cli(*base, "--gate", "--line-gate-trees", "")
    assert gated.returncode == 1, gated.stderr
    assert "stale-waiver" in gated.stderr


def test_cli_gate_passes_after_the_shift(tmp_path: Path) -> None:
    repo = Repo(tmp_path / "r", pad=25)
    dat = repo.dat(tmp_path)
    proc = run_cli(
        "--dat",
        str(dat),
        "--root",
        str(repo.root),
        "--waivers",
        str(anchored_file(tmp_path)),
        "--gate",
        "--line-gate-trees",
        "",
    )
    assert proc.returncode == 0, proc.stderr


def test_cli_check_waivers_needs_no_coverage_data(tmp_path: Path) -> None:
    good = Repo(tmp_path / "good")
    ok = run_cli(
        "--check-waivers", "--root", str(good.root), "--waivers", str(anchored_file(tmp_path))
    )
    assert ok.returncode == 0, ok.stderr
    assert f"fsm.sv:{good.default_line}" in ok.stdout

    bad = Repo(tmp_path / "bad", default_text="default: state_q <= S_ERROR;")
    stale = run_cli(
        "--check-waivers", "--root", str(bad.root), "--waivers", str(anchored_file(tmp_path))
    )
    assert stale.returncode == 1
    assert "stale" in stale.stderr

    amb = Repo(tmp_path / "amb2")
    p = amb.root / FSM_FILE
    p.write_text(
        p.read_text().replace("endmodule", f"  {DEFAULT_ARM}\nendmodule"), encoding="utf-8"
    )
    err = run_cli(
        "--check-waivers", "--root", str(amb.root), "--waivers", str(anchored_file(tmp_path))
    )
    assert err.returncode == 2
    assert "ambiguous" in err.stderr


def test_cli_migrate_waivers_prints_the_converted_file(tmp_path: Path) -> None:
    src = tmp_path / "rtl" / "periph" / "fsm.sv"
    src.parent.mkdir(parents=True)
    src.write_text(LEGACY_SRC, encoding="utf-8")
    old = tmp_path / "old.txt"
    old.write_text(legacy_text(), encoding="utf-8")
    proc = run_cli("--migrate-waivers", str(old), "--root", str(tmp_path))
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == cr.migrate_legacy_waivers(legacy_text(), tmp_path)


# ------------------------------------------------------------------- the checked-in waivers


def test_checked_in_waivers_all_resolve_against_the_checked_in_rtl() -> None:
    """The per-PR tripwire: an RTL edit that touches a waived line fails HERE, not nightly."""
    waivers = cr.load_waivers(REPO_ROOT / "tools" / "verif" / "coverage_waivers.txt")
    anchored_waivers = [w for w in waivers if w.kind == "line"]
    assert anchored_waivers, "the repo has line waivers; the loader must have kept them"
    res = cr.resolve_waivers(waivers, REPO_ROOT)
    stale = {n: r.problems for n, r in res.items() if r.status != "ok"}
    assert not stale, f"stale line waivers (re-anchor them in coverage_waivers.txt): {stale}"
    assert set(res) == {w.lineno for w in anchored_waivers}
