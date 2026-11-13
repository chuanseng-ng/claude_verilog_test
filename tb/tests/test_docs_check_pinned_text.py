"""Unit tests for tools/docs/check_pinned_text.py (synthetic trees only)."""

import ast
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools" / "docs"))

import check_pinned_text as cp  # type: ignore[import-not-found]  # noqa: E402  # pylint: disable=import-error


def write(root: Path, rel: str, text: str) -> None:
    """Helper: write."""
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def run(group, root: Path) -> cp.Ctx:
    """Helper: run."""
    ctx = cp.Ctx(root=root)
    group(ctx)
    return ctx


# ----------------------------------------------------------------------------- a: mutants
MUT = """\
import pathlib
ROOT = pathlib.Path(__file__).resolve().parents[2]
SRC = ROOT / "rtl/m.sv"
MUTANTS = [("m1", "why", [("assign y = a;", "assign y = b;")])]
"""


def _mut_tree(tmp_path: Path, rtl: str) -> Path:
    """Helper: mut tree."""
    write(tmp_path, "tools/verif/mutate_cdc_gray_fifo.py", MUT)
    write(tmp_path, "rtl/m.sv", rtl)
    return tmp_path


def test_mutant_old_text_once_passes(tmp_path: Path) -> None:
    """Check mutant old text once passes."""
    ctx = run(cp.check_mutants, _mut_tree(tmp_path, "assign y = a;\n"))
    assert not ctx.failures and ctx.counts["a"] == 1


def test_mutant_old_text_missing_or_twice_fails(tmp_path: Path) -> None:
    """Check mutant old text missing or twice fails."""
    ctx = run(cp.check_mutants, _mut_tree(tmp_path, "// comment only\n"))
    assert len(ctx.failures) == 1 and "0 occurrence" in ctx.failures[0]
    ctx = run(cp.check_mutants, _mut_tree(tmp_path, "assign y = a;\n// assign y = a;\n"))
    assert "2 occurrence" in ctx.failures[0]


def test_unknown_mutation_script_is_a_setup_error(tmp_path: Path) -> None:
    """Check unknown mutation script is a setup error."""
    write(tmp_path, "tools/verif/mutate_new_thing.py", "MUTANTS = [1]\nROOT = None\n")
    with pytest.raises(cp.SetupError, match="no adapter"):
        run(cp.check_mutants, tmp_path)


def test_no_mutation_scripts_is_a_setup_error(tmp_path: Path) -> None:
    """Check no mutation scripts is a setup error."""
    (tmp_path / "tools" / "verif").mkdir(parents=True)
    with pytest.raises(cp.SetupError):
        run(cp.check_mutants, tmp_path)


# ----------------------------------------------------------------------------- b: sed
FM = "pnr/commercial/signoff/lec/formality/Makefile"
FM_TEXT = "probe:\n\tsed '3s/<= old;/<= new;/' $(REPO)/rtl/c.sv > $(OUT)/c_m.sv\n"


def test_line_addressed_sed_holds(tmp_path: Path) -> None:
    """Check line addressed sed holds."""
    write(tmp_path, FM, FM_TEXT)
    write(tmp_path, "rtl/c.sv", "a\nb\n  x <= old;\n")
    ctx = run(cp.check_seds, tmp_path)
    assert not ctx.failures and ctx.counts["b"] == 1


def test_line_addressed_sed_breaks_when_a_line_is_inserted(tmp_path: Path) -> None:
    """Check line addressed sed breaks when a line is inserted."""
    write(tmp_path, FM, FM_TEXT)
    write(tmp_path, "rtl/c.sv", "// new comment\na\nb\n  x <= old;\n")
    ctx = run(cp.check_seds, tmp_path)
    assert len(ctx.failures) == 1 and "line 3" in ctx.failures[0]
    assert f"{FM}:2" in ctx.failures[0]


def test_unaddressed_sed_in_shell_script_must_match_code(tmp_path: Path) -> None:
    """Check unaddressed sed in shell script must match code."""
    write(tmp_path, FM, FM_TEXT)
    write(tmp_path, "rtl/c.sv", "a\nb\n  x <= old;\n  y(sig_w),\n")
    write(tmp_path, "tools/x.sh", "sed 's/(sig_w),/(other),/' \"$REPO/rtl/c.sv\" > o.sv\n")
    assert not run(cp.check_seds, tmp_path).failures
    write(tmp_path, "rtl/c.sv", "a\nb\n  x <= old;\n  // y(sig_w),\n")
    assert len(run(cp.check_seds, tmp_path).failures) == 1


def test_self_help_sed_needs_leading_comment(tmp_path: Path) -> None:
    """Check self help sed needs leading comment."""
    write(tmp_path, FM, FM_TEXT)
    write(tmp_path, "rtl/c.sv", "a\nb\n  x <= old;\n")
    write(tmp_path, "tools/h.sh", "#!/bin/sh\n# usage\nsed -n '2,2p' \"$0\"\n")
    assert not run(cp.check_seds, tmp_path).failures
    write(tmp_path, "tools/h.sh", "#!/bin/sh\necho hi\nsed -n '2,2p' \"$0\"\n")
    assert len(run(cp.check_seds, tmp_path).failures) == 1


def test_bre_conversion_and_unsupported_features() -> None:
    """Check bre conversion and unsupported features."""
    assert cp.bre_to_py(r"a\(b\)c") == "a(b)c"
    assert cp.bre_to_py("a(b)") == r"a\(b\)"
    assert cp.bre_to_py(r"x\.y") == r"x\.y"
    with pytest.raises(cp.SetupError):
        cp.bre_to_py(r"\<word\>")
    with pytest.raises(cp.SetupError):
        cp.bre_to_py("[[:alpha:]]")


# ----------------------------------------------------------------------------- e, f, g, i
def test_scan_analysis_false_path_must_occur_once(tmp_path: Path) -> None:
    """Check scan analysis false path must occur once."""
    write(
        tmp_path,
        "tools/dft/make_scan_analysis_sdc.py",
        'FALSE_PATH = "set_false_path -to x"\nD = "pnr/sky130_soc.sdc"\n',
    )
    write(tmp_path, "pnr/sky130_soc.sdc", "a\nset_false_path -to x\nb\n")
    assert not run(cp.check_scan_analysis, tmp_path).failures
    write(tmp_path, "pnr/sky130_soc.sdc", "set_false_path -to x\nset_false_path -to x\n")
    assert len(run(cp.check_scan_analysis, tmp_path).failures) == 1


PMU_TEST = """\
SIGNALS = ("clk_en",)
DOMAINS = ("cpu", "gpu")
DOM_INDEX = {"cpu": "DOM_CPU", "gpu": "DOM_GPU"}
"""


def test_pmu_port_assigns_exactly_once(tmp_path: Path) -> None:
    """Check pmu port assigns exactly once."""
    write(tmp_path, "tb/tests/test_pmu_registered_outputs.py", PMU_TEST)
    good = "assign cpu_clk_en_o = clk_en_q[DOM_CPU];\nassign gpu_clk_en_o = clk_en_q[DOM_GPU];\n"
    write(tmp_path, cp.PMU, good)
    ctx = run(cp.check_pmu_ports, tmp_path)
    assert not ctx.failures and ctx.counts["i"] == 2
    write(tmp_path, cp.PMU, good + "// assign cpu_clk_en_o = clk_en_q[DOM_CPU];\n")
    assert len(run(cp.check_pmu_ports, tmp_path).failures) == 1


def _mk_blocks(tmp_path: Path, mk: str) -> None:
    """Helper: mk blocks."""
    write(tmp_path, "tools/verif/soc_shards.py", "# SOC_CI_SUITES SOC_CI_SPLITS\n")
    write(tmp_path, "tools/fpga/stage0_filelist.sh", "# PLL_SOURCES\n")
    write(tmp_path, cp.SOC_MAKEFILE, mk)


MK_OK = (
    "SOC_CI_SUITES = a \\\n  b\nSOC_CI_SPLITS = a=x|y\n"
    "PLL_SOURCES = \\\n  $(RTL)/a.sv \\\n  $(RTL)/tb_soc_pll.sv\n"
)


def test_makefile_blocks_must_not_contain_hash(tmp_path: Path) -> None:
    """Check makefile blocks must not contain hash."""
    _mk_blocks(tmp_path, MK_OK)
    ctx = run(cp.check_makefile_blocks, tmp_path)
    assert not ctx.failures and ctx.counts["g"] == 3
    _mk_blocks(tmp_path, MK_OK.replace("  b\n", "  b # note\n"))
    assert "SOC_CI_SUITES" in run(cp.check_makefile_blocks, tmp_path).failures[0]
    _mk_blocks(tmp_path, MK_OK.replace("  $(RTL)/a.sv \\\n", "  $(RTL)/a.sv \\\n  # x\\\n"))
    assert "PLL_SOURCES" in run(cp.check_makefile_blocks, tmp_path).failures[0]


def test_missing_consumer_is_a_setup_error(tmp_path: Path) -> None:
    """Check missing consumer is a setup error."""
    with pytest.raises(cp.SetupError):
        run(cp.check_makefile_blocks, tmp_path)


# ----------------------------------------------------------------------------- literal engine
def test_engine_derives_literals_regexes_and_counts(tmp_path: Path) -> None:
    """Check engine derives literals regexes and counts."""
    src = (
        "from pathlib import Path\nimport re\n"
        "ROOT = Path(__file__).resolve().parents[2]\n"
        "SDC = (ROOT / 'pnr' / 'a.sdc').read_text()\n"
        "def test_x():\n"
        "    rtl = (ROOT / 'rtl' / 'm.sv').read_text()\n"
        "    assert 'keep' in rtl\n"
        "    assert 'bad' not in SDC\n"
        "    assert re.search(r'^from x', rtl, re.M)\n"
        "    assert SDC.count('set') == 2\n"
        "    m = re.search(r'foo\\d', rtl)\n"
        "    assert m\n"
        "    SDC.index('marker')\n"
    )
    checks = cp.derive_literal_checks(ast.parse(src))
    kinds = {(c[0], c[1], c[3]) for c in checks}
    assert ("in", "rtl/m.sv", True) in kinds
    assert ("in", "pnr/a.sdc", False) in kinds
    assert ("re", "rtl/m.sv", True) in kinds
    assert ("count", "pnr/a.sdc", True) in kinds
    assert sum(1 for c in checks if c[0] == "re") == 2
    assert ("in", "pnr/a.sdc", "marker", True) in {(c[0], c[1], c[2], c[3]) for c in checks}


def test_test_literals_follow_the_consumer(tmp_path: Path) -> None:
    """Check test literals follow the consumer."""
    test = (
        "from pathlib import Path\n"
        "ROOT = Path(__file__).resolve().parents[2]\n"
        "def test_x():\n"
        "    t = (ROOT / 'rtl' / 'm.sv').read_text()\n"
        "    assert 'keep_me' in t\n"
    )
    for rel in cp.KNOWN_ENGINE_TESTS:
        write(tmp_path, rel, test)
    write(tmp_path, "rtl/m.sv", "keep_me\n")
    ctx = run(cp.check_test_literals, tmp_path)
    assert not ctx.failures
    write(tmp_path, "rtl/m.sv", "// removed\n")
    assert len(run(cp.check_test_literals, tmp_path).failures) == len(cp.KNOWN_ENGINE_TESTS)


def test_test_with_no_derivable_assertions_is_a_setup_error(tmp_path: Path) -> None:
    """Check test with no derivable assertions is a setup error."""
    for rel in cp.KNOWN_ENGINE_TESTS:
        write(tmp_path, rel, "def test_x():\n    assert True\n")
    with pytest.raises(cp.SetupError):
        run(cp.check_test_literals, tmp_path)


# ----------------------------------------------------------------------------- f, o, l, main
def test_upf_directive_lines_must_parse(tmp_path: Path) -> None:
    """Check upf directive lines must parse."""
    write(
        tmp_path,
        "tools/verif/check_upf.py",
        'import re\n_DIRECTIVE = re.compile(r"^\\s*#\\s*upf-check\\s+(aon|unclamped)\\b(.*)$")\n',
    )
    pmu = "MODE_A: begin\n  x = 1; // note\nend\n"
    write(tmp_path, cp.PMU, pmu)
    write(tmp_path, cp.UPF, "# upf-check aon u_x\n")
    assert not run(cp.check_upf, tmp_path).failures
    write(tmp_path, cp.UPF, "# upf-check bogus u_x\n")
    assert run(cp.check_upf, tmp_path).failures
    write(tmp_path, cp.UPF, "# upf-check aon u_x\n")
    write(tmp_path, cp.PMU, "MODE_A: begin\n  // the end of it\nend\n")
    assert any("MODE_A" in f for f in run(cp.check_upf, tmp_path).failures)


def test_last_endmodule_must_be_code(tmp_path: Path) -> None:
    """Check last endmodule must be code."""
    write(tmp_path, "tb/tests/test_check_elab_strict.py", "x = 1\n")
    for rel in cp.ELAB_STRICT_RTL:
        write(tmp_path, rel, "module m;\nendmodule\n")
    assert not run(cp.check_elab_strict_tail, tmp_path).failures
    write(tmp_path, cp.ELAB_STRICT_RTL[0], "module m;\nendmodule\n// endmodule note\n")
    assert len(run(cp.check_elab_strict_tail, tmp_path).failures) == 1


def test_formal_find_strings_must_occur_once(tmp_path: Path) -> None:
    """Check formal find strings must occur once."""
    mods = '{"modules":[{"name":"m","negative_control":{"file":"rtl/m.sv","find":"a = b;"}}]}'
    write(tmp_path, "tools/formal/modules.json", mods)
    write(tmp_path, "rtl/m.sv", "a = b;\n")
    assert not run(cp.check_formal_modules, tmp_path).failures
    write(tmp_path, "rtl/m.sv", "a = b;\na = b;\n")
    assert len(run(cp.check_formal_modules, tmp_path).failures) == 1


def test_main_exit_codes(tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
    """Check main exit codes."""
    assert cp.main(["--root", str(tmp_path / "nope")]) == 2
    assert cp.main(["--root", str(tmp_path), "--skip-waivers"]) == 2  # empty tree: loud, not a pass
    out = capsys.readouterr().out
    assert "SETUP ERROR" in out and "OK:" not in out


def test_run_all_reports_failure_as_exit_1(tmp_path: Path, monkeypatch, capsys) -> None:  # type: ignore[no-untyped-def]
    """Check run all reports failure as exit 1."""

    def fake(ctx: cp.Ctx) -> None:
        """Helper: fake."""
        ctx.fail("x", "pinned thing", "consumer.py:1", "A", "B")

    monkeypatch.setattr(cp, "GROUPS", [("x", fake)])
    assert cp.main(["--root", str(tmp_path), "--skip-waivers"]) == 1
    assert "pinned thing" in capsys.readouterr().out


def test_real_tree_holds() -> None:
    """The committed tree satisfies every anchor (waivers step skipped; CI runs it separately)."""
    ctx = cp.run_all(REPO, skip_waivers=True)
    assert ctx.setup == [] and ctx.failures == []
