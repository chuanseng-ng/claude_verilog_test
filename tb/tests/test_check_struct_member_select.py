"""Unit tests for tools/verif/check_struct_member_select.py (bead ainf)."""

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools" / "verif"))

import check_struct_member_select as chk  # noqa: E402


def _tree(tmp_path: Path, src: str) -> Path:
    (tmp_path / "rtl").mkdir()
    (tmp_path / "rtl" / "m.sv").write_text(src, encoding="utf-8")
    return tmp_path


def test_ranged_member_count_scalar_not_counted() -> None:
    body = "logic [31:0] pc; logic [31:0] instruction; logic valid;"
    assert chk.ranged_member_count(body) == 2


def test_two_ranged_type_is_hot(tmp_path: Path) -> None:
    root = _tree(tmp_path, "typedef struct packed { logic [3:0] a; logic [3:0] b; } t_t;\n")
    _, _, hot = chk.collect(root)
    assert [k for k, _, _ in hot] == ["hot-type|rtl/m.sv|t_t"]


def test_three_ranged_type_is_not_hot(tmp_path: Path) -> None:
    root = _tree(
        tmp_path, "typedef struct packed { logic [3:0] a; logic [3:0] b; logic [1:0] c; } t_t;\n"
    )
    assert chk.collect(root)[2] == []


def test_member_select_site_found_and_comment_ignored(tmp_path: Path) -> None:
    root = _tree(tmp_path, "assign y = s.f[3:0];\n// assign z = s.g[1];\n")
    sites, lhs, _ = chk.collect(root)
    assert [k for k, _, _ in sites] == ["site|rtl/m.sv|s.f"]
    assert lhs == []


def test_wire_first_idiom_is_clean(tmp_path: Path) -> None:
    root = _tree(tmp_path, "logic [31:0] w;\nassign w = s.f;\nassign y = w[3:0];\n")
    sites, lhs, hot = chk.collect(root)
    assert sites == [] and lhs == [] and hot == []


def test_lhs_member_part_select_is_reported(tmp_path: Path) -> None:
    root = _tree(tmp_path, "always_comb begin\n  y.f[7:4] = n;\nend\n")
    _, lhs, _ = chk.collect(root)
    assert [k for k, _, _ in lhs] == ["lhs|rtl/m.sv|y.f"]


def test_new_hit_fails_and_baseline_passes(tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
    root = _tree(tmp_path, "assign y = s.f[3:0];\n")
    base = tmp_path / "base.txt"
    assert chk.main(["--root", str(root), "--baseline", str(base)]) == 1
    assert "NEW" in capsys.readouterr().out
    assert chk.main(["--root", str(root), "--baseline", str(base), "--write-baseline"]) == 0
    assert chk.main(["--root", str(root), "--baseline", str(base)]) == 0
    (root / "rtl" / "n.sv").write_text("assign q = s.g[1];\n", encoding="utf-8")
    assert chk.main(["--root", str(root), "--baseline", str(base)]) == 1


def test_repo_baseline_is_current() -> None:
    assert chk.main(["--root", str(REPO)]) == 0
