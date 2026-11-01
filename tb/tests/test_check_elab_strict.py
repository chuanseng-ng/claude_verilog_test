"""Tests for tools/verif/check_elab_strict.py (bead lvdk): strict pyslang elaboration gate."""
# ruff: noqa: E501

import sys
from pathlib import Path

import pytest

pytest.importorskip("pyslang")

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools" / "verif"))

import check_elab_strict as chk  # type: ignore[import-not-found]  # noqa: E402

CHILD = 'module child #(parameter string S = "") (input logic a, output logic y);\n  assign y = a;\nendmodule\n'


def _elab(tmp_path: Path, src: str, *flags: str) -> int:
    """Elaborate one source in tmp_path and return the exit code."""
    path = tmp_path / "t.sv"
    path.write_text(src, encoding="utf-8")
    return int(chk.elaborate(["--top", "top", *flags, str(path)]).code)


@pytest.mark.parametrize(
    "src",
    [
        "module top(input logic a, output logic y);\n  assign y = w;\n  logic w;\n  assign w = a;\nendmodule\n",
        "module top(input logic a, output logic y);\n  always_comb y = w;\n  logic w;\n  assign w = a;\nendmodule\n",
        "module top(input logic a, output logic y);\n  missing_mod u (.a(a), .y(y));\nendmodule\n",
        "module top(input logic a, output logic y);\n  assign y = never_declared;\nendmodule\n",
        "module top(input logic a, output logic y);\n  assign y = = a;\nendmodule\n",
        CHILD
        + 'module top(input logic a, output logic y);\n  child #("a", "b") u (.a(a), .y(y));\nendmodule\n',
        CHILD
        + 'module top(input logic a, output logic y);\n  child #(.S("a"), .S("b")) u (.a(a), .y(y));\nendmodule\n',
        CHILD
        + 'module top(input logic a, output logic y);\n  child #(.TYPO("a")) u (.a(a), .y(y));\nendmodule\n',
    ],
    ids=[
        "use_before_decl_assign",
        "use_before_decl_always_comb",
        "missing_module",
        "undeclared",
        "syntax",
        "excess_positional_override",
        "duplicate_named_override",
        "nonexistent_override",
    ],
)
def test_illegal_design_rejected(tmp_path: Path, src: str) -> None:
    """Every illegal form must give the findings exit code."""
    assert _elab(tmp_path, src) == chk.EXIT_FINDINGS


def test_legal_design_accepted(tmp_path: Path) -> None:
    """A legal override must pass, so rejection above is not blanket failure."""
    src = (
        CHILD
        + 'module top(input logic a, output logic y);\n  child #(.S("a")) u (.a(a), .y(y));\nendmodule\n'
    )
    assert _elab(tmp_path, src) == chk.EXIT_OK


def test_ignore_flag_hides_missing_module_but_not_use_before_decl(tmp_path: Path) -> None:
    """Pins the trap: why only macro arms may carry --ignore-unknown-modules."""
    missing = (
        "module top(input logic a, output logic y);\n  missing_mod u (.a(a), .y(y));\nendmodule\n"
    )
    assert _elab(tmp_path, missing, chk.IGNORE_UNKNOWN) == chk.EXIT_OK
    ubd = "module top(input logic a, output logic y);\n  assign y = w;\n  logic w;\n  assign w = a;\nendmodule\n"
    assert _elab(tmp_path, ubd, chk.IGNORE_UNKNOWN) == chk.EXIT_FINDINGS


def test_missing_source_is_load_failure_not_clean() -> None:
    """A file that cannot be loaded is an error, not a clean run."""
    assert chk.elaborate(["--top", "top", "/nonexistent/x.sv"]).code == chk.EXIT_LOAD


def test_worker_crash_is_not_a_verdict(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A broken tool must not read as "illegal design", or controls would pass vacuously."""
    fake = tmp_path / "pyslang"
    fake.mkdir()
    (fake / "__init__.py").write_text("raise RuntimeError('boom')\n", encoding="utf-8")
    monkeypatch.setenv("PYTHONPATH", str(tmp_path))
    assert chk.elaborate(["--top", "top", "/nonexistent/x.sv"]).code == chk.EXIT_LOAD
    assert chk.run_controls() != []


def test_source_path_with_space_is_loaded(tmp_path: Path) -> None:
    """Quoting survives the round trip through the slang command line."""
    spaced = tmp_path / "with space"
    spaced.mkdir()
    assert (
        _elab(spaced, "module top(input logic a, output logic y);\n  assign y = a;\nendmodule\n")
        == chk.EXIT_OK
    )


def test_arm_table_only_macro_arms_ignore_unknown_modules() -> None:
    """The hiding flag stays confined to arms that need it."""
    names = {arm.name for arm in chk.ARMS}
    assert {
        "soc_default",
        "cpu_default",
        "gpu_default",
        "soc_fpga",
        "soc_sky130_pnr",
        "soc_asap7_pnr",
    } <= names
    ignoring = {arm.name for arm in chk.ARMS if arm.ignore_unknown}
    assert ignoring == {"soc_sky130_pnr", "soc_asap7_pnr"}


def test_every_arm_source_exists() -> None:
    """A renamed file list must fail here, not silently narrow the gate."""
    for arm in chk.ARMS:
        for path in arm.filelists:
            assert (REPO / path).is_file(), f"{arm.name}: {path}"
        assert arm.resolved_globs(REPO) or not arm.source_globs, arm.name


def test_controls_pass_on_working_tool() -> None:
    """All built-in controls give their expected verdicts."""
    assert chk.run_controls() == []


def test_main_fails_when_control_stops_detecting(monkeypatch: pytest.MonkeyPatch) -> None:
    """A gate that can no longer see the defect must error, not report clean."""
    bad = chk.Control(
        "broken",
        chk.CONTROLS[0].source.replace("assign y = w;\n  logic w;", "logic w;\n  assign y = w;"),
        False,
    )
    monkeypatch.setattr(chk, "CONTROLS", (bad, *chk.CONTROLS[1:]))
    assert chk.main([]) == chk.EXIT_LOAD


def test_main_fails_when_legal_control_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    """A tool rejecting legal code must error, not report findings."""
    bad = chk.Control("broken_legal", "module top; assign y = = 1; endmodule\n", True)
    monkeypatch.setattr(chk, "CONTROLS", (bad,))
    assert chk.main([]) == chk.EXIT_LOAD


def test_main_reports_pyslang_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    """A missing tool has its own exit code."""
    monkeypatch.setattr(chk, "pyslang_available", lambda: False)
    assert chk.main([]) == chk.EXIT_NO_TOOL


@pytest.mark.parametrize(
    "rel", ["rtl/soc/soc_top.sv", "rtl/periph/gpio_controller.sv", "rtl/cpu/core/rv32i_regfile.sv"]
)
def test_seeded_defect_in_real_design_is_caught(tmp_path: Path, rel: str) -> None:
    """Top level, leaf and deep CPU: proves hierarchy is really elaborated."""
    src = (REPO / rel).read_text(encoding="utf-8")
    cut = src.rfind("endmodule")
    seeded = tmp_path / Path(rel).name
    seeded.write_text(
        src[:cut] + "  wire seeded_y = seeded_w;\n  logic seeded_w;\n" + src[cut:], encoding="utf-8"
    )
    main_f = (REPO / "rtl/filelist/soc_top.f").read_text(encoding="utf-8")
    assert f"\n{rel}\n" in main_f, rel
    flist = tmp_path / "seed.f"
    flist.write_text(main_f.replace(f"\n{rel}\n", f"\n{seeded}\n"), encoding="utf-8")
    result = chk.elaborate(
        ["--top", "soc_top", "-f", str(flist), "-f", "rtl/filelist/soc_top_sim_models.f"]
    )
    assert result.code == chk.EXIT_FINDINGS
    assert "seeded_w" in result.output


def test_repo_arms_clean() -> None:
    """Current RTL passes every arm; same check as the CI step."""
    assert chk.main([]) == chk.EXIT_OK
