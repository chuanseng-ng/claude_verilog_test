"""Unit tests for tools/verif/gen_filelist.py (bead 1as3).

Synthetic mini-repos exercise the generator's rules; the ``real_repo`` tests pin the committed
``rtl/filelist/*.f`` to the authoritative Makefile lists so the drift gate cannot rot.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools" / "verif"))

import gen_filelist as gen  # type: ignore[import-not-found]  # noqa: E402
from check_source_closure import (  # type: ignore[import-not-found]  # noqa: E402
    extract_makefile_lists,
)

MINI_MAKEFILE = """\
SOC_DIR   := $(shell pwd)
PROJ_ROOT := $(abspath $(SOC_DIR)/..)
RTL       := $(PROJ_ROOT)/rtl
SRAM_SIM_MODEL ?= $(PROJ_ROOT)/sim/sram.v
TOP_SOURCES = \\
	$(RTL)/b.sv \\
	$(SRAM_SIM_MODEL) \\
	$(RTL)/a_pkg.sv \\
	$(RTL)/sub/c.sv \\
	$(SOC_DIR)/tb_top.sv
"""


def _mini_repo(tmp_path: Path, makefile: str = MINI_MAKEFILE) -> Path:
    """tmp/tbdir/Makefile + rtl/{a_pkg,b,sub/c,x_extra}.sv + sim/sram.v + tb_top.sv."""
    (tmp_path / "rtl" / "sub").mkdir(parents=True)
    (tmp_path / "sim").mkdir()
    (tmp_path / "tbdir").mkdir()
    (tmp_path / "rtl" / "a_pkg.sv").write_text("package a_pkg;\nendpackage\n")
    (tmp_path / "rtl" / "b.sv").write_text("module b; endmodule\n")
    (tmp_path / "rtl" / "sub" / "c.sv").write_text("module c; endmodule\n")
    (tmp_path / "rtl" / "x_extra.sv").write_text("module x_extra; endmodule\n")
    (tmp_path / "sim" / "sram.v").write_text("module sram; endmodule\n")
    (tmp_path / "tbdir" / "tb_top.sv").write_text("module tb_top; endmodule\n")
    (tmp_path / "tbdir" / "Makefile").write_text(makefile)
    return tmp_path


def _spec(**kw: object) -> gen.ListSpec:
    base: dict[str, object] = {
        "name": "mini",
        "top": "b",
        "makefile": "tbdir/Makefile",
        "variable": "TOP_SOURCES",
        "summary": "mini",
    }
    base.update(kw)
    return gen.ListSpec(**base)  # type: ignore[arg-type]


@pytest.fixture(name="tb_as_tb")
def _tb_as_tb(monkeypatch: pytest.MonkeyPatch) -> None:
    """The mini repo keeps its testbench under tbdir/; classify that as 'tb' too."""
    real = gen._classify

    def classify(rel: str) -> str:
        return "tb" if rel.startswith("tbdir/") else real(rel)

    monkeypatch.setattr(gen, "_classify", classify)


# ── collect(): the rules ────────────────────────────────────────────────────


def test_packages_first_tb_dropped_models_split(tmp_path: Path, tb_as_tb: None) -> None:
    root = _mini_repo(tmp_path)
    rtl, models = gen.collect(_spec(), root)
    assert rtl == ["rtl/a_pkg.sv", "rtl/b.sv", "rtl/sub/c.sv"]  # package hoisted, order kept
    assert models == ["sim/sram.v"]
    assert not any("tb_top" in f for f in rtl + models)


def test_extra_rtl_added_once_after_packages(
    tmp_path: Path, tb_as_tb: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _mini_repo(tmp_path)
    monkeypatch.setitem(gen.EXTRA_RTL, "rtl/x_extra.sv", "needed by a test")
    monkeypatch.setitem(gen.EXTRA_RTL, "rtl/b.sv", "already listed: must not be doubled")
    rtl, _ = gen.collect(_spec(extra_rtl=("rtl/x_extra.sv", "rtl/b.sv")), root)
    assert rtl == ["rtl/a_pkg.sv", "rtl/b.sv", "rtl/sub/c.sv", "rtl/x_extra.sv"]  # b not doubled


def test_extra_without_recorded_reason_rejected(tmp_path: Path, tb_as_tb: None) -> None:
    root = _mini_repo(tmp_path)
    with pytest.raises(gen.FilelistError, match="no recorded reason"):
        gen.collect(_spec(extra_rtl=("rtl/x_extra.sv",)), root)


def test_model_var_adds_model_not_in_list(tmp_path: Path, tb_as_tb: None) -> None:
    mk = MINI_MAKEFILE.replace("\t$(SRAM_SIM_MODEL) \\\n", "")
    root = _mini_repo(tmp_path, mk)
    spec = _spec(model_vars=("SRAM_SIM_MODEL",))
    # model variables are looked up in gen.MODEL_VAR_MAKEFILE
    gen.MODEL_VAR_MAKEFILE, saved = "tbdir/Makefile", gen.MODEL_VAR_MAKEFILE
    try:
        _, models = gen.collect(spec, root)
    finally:
        gen.MODEL_VAR_MAKEFILE = saved
    assert models == ["sim/sram.v"]


def test_unknown_path_category_is_an_error(tmp_path: Path) -> None:
    # Without the tb_as_tb fixture 'tbdir/' is neither rtl/, sim/ nor tb/: refuse to guess.
    root = _mini_repo(tmp_path)
    with pytest.raises(gen.FilelistError, match="not under rtl/, sim/ or tb/"):
        gen.collect(_spec(), root)


def test_missing_variable_and_missing_file(tmp_path: Path, tb_as_tb: None) -> None:
    root = _mini_repo(tmp_path)
    with pytest.raises(gen.FilelistError, match="NOPE_SOURCES"):
        gen.collect(_spec(variable="NOPE_SOURCES"), root)
    (root / "rtl" / "b.sv").unlink()
    with pytest.raises(gen.FilelistError, match="missing"):
        gen.collect(_spec(), root)


def test_path_outside_repo_rejected(tmp_path: Path) -> None:
    with pytest.raises(gen.FilelistError, match="outside the repository"):
        gen._rel("/etc/passwd", tmp_path)


# ── rendering ───────────────────────────────────────────────────────────────


def test_incdirs_first_appearance_order() -> None:
    files = ["rtl/a/x.sv", "rtl/b/y.sv", "rtl/a/z.sv"]
    assert gen.incdirs(files) == ["rtl/a", "rtl/b"]


def test_render_is_relative_and_prefix_applies_everywhere() -> None:
    spec = gen.SPECS[0]
    rtl = ["rtl/soc/axi_pkg.sv", "rtl/soc/soc_top.sv"]
    text = gen.render_main(spec, rtl)
    body = [ln for ln in text.splitlines() if ln and not ln.startswith("//")]
    assert body == ["+incdir+rtl/soc", "rtl/soc/axi_pkg.sv", "rtl/soc/soc_top.sv"]
    assert "GENERATED by tools/verif/gen_filelist.py" in text
    assert "-F" in text and "-f" in text  # the -f/-F guidance is present
    pre = gen.render_main(spec, rtl, prefix="/abs/repo/")
    pbody = [ln for ln in pre.splitlines() if ln and not ln.startswith("//")]
    assert pbody == [
        "+incdir+/abs/repo/rtl/soc",
        "/abs/repo/rtl/soc/axi_pkg.sv",
        "/abs/repo/rtl/soc/soc_top.sv",
    ]


def test_every_define_is_documented_not_baked_in() -> None:
    text = gen.render_main(gen.SPECS[0], ["rtl/soc/soc_top.sv"])
    for name in ("FPGA", "SRAM_SKY130", "SRAM_ASAP7", "__pnr__", "USE_ICG_CELL", "SIMULATION"):
        assert name in text
    assert not any(ln.startswith("+define") for ln in text.splitlines())


# ── write / check ───────────────────────────────────────────────────────────


def test_write_then_check_clean_then_drift(tmp_path: Path, tb_as_tb: None) -> None:
    root = _mini_repo(tmp_path)
    specs = (_spec(),)
    assert gen.check(root, specs)  # nothing written yet: reported missing
    gen.write(root, specs)
    assert gen.check(root, specs) == []
    out = root / gen.FILELIST_DIR / "mini.f"
    out.write_text(out.read_text() + "rtl/b.sv\n")  # hand edit
    problems = gen.check(root, specs)
    assert len(problems) == 1 and "out of date" in problems[0] and "-rtl/b.sv" in problems[0]


def test_check_flags_makefile_change_and_stray_list(tmp_path: Path, tb_as_tb: None) -> None:
    root = _mini_repo(tmp_path)
    specs = (_spec(),)
    gen.write(root, specs)
    (root / "rtl" / "d.sv").write_text("module d; endmodule\n")
    mk = root / "tbdir" / "Makefile"
    mk.write_text(
        mk.read_text().replace("\t$(SOC_DIR)/tb_top.sv", "\t$(RTL)/d.sv \\\n\t$(SOC_DIR)/tb_top.sv")
    )
    (root / gen.FILELIST_DIR / "handwritten.f").write_text("rtl/b.sv\n")
    problems = "\n".join(gen.check(root, specs))
    assert "mini.f: out of date" in problems and "+rtl/d.sv" in problems
    assert "handwritten.f: not produced by" in problems


def test_main_check_exit_codes(
    tmp_path: Path,
    tb_as_tb: None,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = _mini_repo(tmp_path)
    monkeypatch.setattr(gen, "REPO_ROOT", root)
    monkeypatch.setattr(gen, "SPECS", (_spec(),))
    assert gen.main(["--check"]) == 1  # nothing generated yet
    assert "drift" in capsys.readouterr().err
    assert gen.main([]) == 0  # write
    assert gen.main(["--check"]) == 0
    (root / "rtl" / "b.sv").unlink()
    assert gen.main(["--check"]) == 2  # unresolvable source list is not "drift"


# ── the real repository ─────────────────────────────────────────────────────


def _read(name: str) -> list[str]:
    text = (REPO / gen.FILELIST_DIR / name).read_text(encoding="utf-8")
    return [ln for ln in text.splitlines() if ln and not ln.startswith(("//", "+"))]


def test_real_repo_lists_are_committed_and_current() -> None:
    assert gen.check() == []


def test_real_repo_main_cli_check_passes(capsys: pytest.CaptureFixture[str]) -> None:
    assert gen.main(["--check"]) == 0
    assert "OK" in capsys.readouterr().out


def test_soc_top_file_set_equals_pll_sources_plus_clock_gate() -> None:
    tokens = extract_makefile_lists(REPO / "tb/cocotb/soc/Makefile")["PLL_SOURCES"]
    want = {Path(t).resolve().relative_to(REPO.resolve()).as_posix() for t in tokens}
    want = {f for f in want if not f.startswith("tb/")} | {"rtl/mem/rv32i_clock_gate.sv"}
    got = set(_read("soc_top.f")) | set(_read("soc_top_sim_models.f"))
    assert got == want


def test_no_duplicates_no_testbench_and_all_files_exist() -> None:
    for name in sorted(p.name for p in (REPO / gen.FILELIST_DIR).glob("*.f")):
        files = _read(name)
        assert len(files) == len(set(files)), f"{name}: duplicate entries"
        for f in files:
            assert not Path(f).is_absolute(), f"{name}: absolute path {f}"
            assert not Path(f).name.startswith("tb_") and not f.startswith("tb/"), f
            assert (REPO / f).is_file(), f"{name}: {f} does not exist"


def test_synthesisable_lists_hold_no_sim_models_and_models_are_sim_only() -> None:
    for name in ("soc_top", "cpu_top", "gpu_top"):
        assert all(f.startswith("rtl/") for f in _read(f"{name}.f"))
        assert all(f.startswith("sim/") for f in _read(f"{name}_sim_models.f"))


def test_packages_precede_every_non_package() -> None:
    for name in ("soc_top", "cpu_top", "gpu_top"):
        flags = [gen._is_package(REPO, f) for f in _read(f"{name}.f")]
        assert any(flags)
        assert flags == sorted(flags, reverse=True), f"{name}.f: a package follows a module"


def test_block_lists_are_subsets_of_soc_top() -> None:
    soc = set(_read("soc_top.f"))
    assert set(_read("cpu_top.f")) <= soc
    assert set(_read("gpu_top.f")) <= soc


def test_clock_gate_is_named_explicitly_in_every_rtl_list() -> None:
    # sv2v has no -I auto-discovery; a missing rv32i_clock_gate is silently blackboxed.
    assert "rtl/mem/rv32i_clock_gate.sv" in _read("soc_top.f")
    assert "rtl/mem/rv32i_clock_gate.sv" in _read("cpu_top.f")


def test_print_with_prefix_cli(capsys: pytest.CaptureFixture[str]) -> None:
    assert gen.main(["--print", "gpu_top", "--prefix", "/x/y"]) == 0
    out = capsys.readouterr().out
    body = [ln for ln in out.splitlines() if ln and not ln.startswith("//")]
    assert body and all("/x/y/" in ln for ln in body)
    assert gen.main(["--print", "nope"]) == 2
