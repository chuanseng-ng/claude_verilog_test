"""Unit tests for tools/verif/soc_shards.py and the SOC_CI_SUITES refactor (bead 9ayu.1).

The sharded coverage workflow splits `soc_all_ci` over several runners.  What must never happen is
a suite silently dropped (or run twice) by that split, so the properties pinned here are:

  * the single source of the list is `SOC_CI_SUITES` in tb/cocotb/soc/Makefile, and the script
    reads exactly that;
  * `assign` is a partition of the list: every entry in exactly one shard, list order preserved
    within a shard, deterministic, and the five heaviest SoC suites land in different shards;
  * `check_union` (the CI gate) reports a lost suite, a suite run twice, an unknown suite and an
    empty manifest -- each a failure, never a pass;
  * (needs make + verilator) `soc_all_ci` still expands to the same sub-make invocations in the
    same order as the list, and `print-soc-ci-suites` agrees with the script's parse.
"""

# pylint: disable=missing-function-docstring,redefined-outer-name  # pytest fixtures + descriptive test names

from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "tools" / "verif" / "soc_shards.py"
SOC_DIR = REPO_ROOT / "tb" / "cocotb" / "soc"
_SPEC = importlib.util.spec_from_file_location("soc_shards", SCRIPT)
assert _SPEC and _SPEC.loader
ss = importlib.util.module_from_spec(_SPEC)
sys.modules["soc_shards"] = ss
_SPEC.loader.exec_module(ss)

DEFAULT_MAKEFILE_TEXT = (REPO_ROOT / "tb" / "cocotb" / "soc" / "Makefile").read_text()
# The eight heaviest sharding units, one per shard.  soc_multiclock dropped out when shm5 (#314)
# split test_load_verify_8n1_back_to_back into its own soc_uart_boot slice (~760 s instrumented).
HEAVY = [
    "i2c",
    "soc_integration",
    "soc_cpu_gpu",
    "soc_coherency",
    "soc_uart_boot:TESTCASE=test_load_verify_jump_and_run",
    "soc_uart_boot:TESTCASE=test_load_verify_8n1_back_to_back",
    "soc_uart_boot:TESTCASE=test_bad_crc_is_nakked_and_memory_untouched,"
    "test_refusals_nak_with_the_right_code,test_banner_and_info_default_115200_at_50mhz",
    "soc_uart_boot:TESTCASE=test_table_sum_is_independent,test_banner_and_info_sim_divisor,"
    "test_oversized_length_nak_then_resync,test_truncated_frame_times_out_and_recovers,"
    "test_line_noise_before_sof_is_ignored,test_autoboot_runs_preloaded_image,"
    "test_autoboot_refuses_empty_sram_and_stays_serviceable",
]
NSHARDS = 8


@pytest.fixture(scope="module")
def plain_suites() -> list[str]:
    """SOC_CI_SUITES: what soc_all_ci runs."""
    return list(ss.load_suites())


@pytest.fixture(scope="module")
def suites() -> list[str]:
    """The sharding units: SOC_CI_SUITES with the SOC_CI_SPLITS suites expanded."""
    return list(ss.load_units())


@pytest.fixture(scope="module")
def weights() -> dict:
    return dict(ss.load_weights())


# ----------------------------------------------------------------------------- parsing


def test_parse_continuation_lines_and_args() -> None:
    text = "FOO := 1\nSOC_CI_SUITES := \\\n    a \\\n    b:X=1 \\\n    c\n\nOTHER := z\n"
    assert ss.parse_suites(text) == ["a", "b:X=1", "c"]


def test_parse_rejects_missing_empty_and_duplicate() -> None:
    with pytest.raises(ValueError, match="not defined"):
        ss.parse_suites("FOO := 1\n")
    with pytest.raises(ValueError, match="empty"):
        ss.parse_suites("SOC_CI_SUITES :=\n")
    with pytest.raises(ValueError, match="duplicate"):
        ss.parse_suites("SOC_CI_SUITES := a b a\n")


def test_makefile_list_is_sane(suites: list[str]) -> None:
    assert len(suites) >= 50
    assert len(set(suites)) == len(suites)
    # The argument-carrying entry stays ONE word.
    assert "sram_controller:SRAM_TARGET=sky130" in suites
    assert all(" " not in s for s in suites)
    for s in HEAVY:
        assert s in suites


def test_weights_name_only_real_suites(suites: list[str], weights: dict) -> None:
    unknown = sorted(set(weights["suites"]) - set(suites))
    assert not unknown, f"soc_shard_weights.json names suites not in SOC_CI_SUITES: {unknown}"
    groups = {g for v in weights["suites"].values() if (g := v.get("group"))}
    assert groups <= set(weights["groups"])


# ----------------------------------------------------------------------------- assignment


@pytest.mark.parametrize("n", [1, 2, 3, 5, 6, 8])
def test_assign_is_a_partition_preserving_order(suites: list[str], weights: dict, n: int) -> None:
    shards = ss.assign(suites, n, weights)
    assert len(shards) == n
    flat = [s for m in shards for s in m]
    assert sorted(flat) == sorted(suites)  # nothing lost, nothing twice
    idx = {s: i for i, s in enumerate(suites)}
    for m in shards:
        assert [idx[s] for s in m] == sorted(idx[s] for s in m)  # list order kept


def test_assign_is_deterministic(suites: list[str], weights: dict) -> None:
    assert ss.assign(suites, 6, weights) == ss.assign(
        list(suites), 6, json.loads(json.dumps(weights))
    )


def test_heavy_suites_are_in_different_shards(suites: list[str], weights: dict) -> None:
    shards = ss.assign(suites, NSHARDS, weights)
    where = {s: k for k, m in enumerate(shards) for s in m}
    assert len({where[s] for s in HEAVY}) == len(HEAVY)


def test_shards_are_balanced(suites: list[str], weights: dict) -> None:
    shards = ss.assign(suites, 6, weights)
    loads = ss.shard_loads(shards, weights)
    assert max(loads) / min(loads) < 1.15, loads


def test_unknown_suite_gets_default_weight_and_still_shards(
    suites: list[str], weights: dict
) -> None:
    extra = suites + ["brand_new_suite"]
    shards = ss.assign(extra, 6, weights)
    assert sum("brand_new_suite" in m for m in shards) == 1


def test_assign_rejects_zero_shards(suites: list[str], weights: dict) -> None:
    with pytest.raises(ValueError):
        ss.assign(suites, 0, weights)


def test_shared_build_group_cost_is_charged_once_per_shard() -> None:
    w: dict[str, Any] = {
        "default_run_s": 10.0,
        "groups": {"g": {"build_s": 100.0}},
        "suites": {"a": {"run_s": 10, "group": "g"}, "b": {"run_s": 10, "group": "g"}},
    }
    assert ss.shard_loads([["a", "b"]], w) == [120.0]
    assert ss.shard_loads([["a"], ["b"]], w) == [110.0, 110.0]
    # A shard that already holds the group pays no second build: with x running 50 s elsewhere,
    # `a` and `b` (10 s each + one 100 s build) go together, not one per shard (2 x 110 s).
    w2 = {**w, "suites": {**w["suites"], "x": {"run_s": 50}}}
    assert ss.assign(["x", "a", "b"], 2, w2) == [["x"], ["a", "b"]]


# ----------------------------------------------------------------------------- union check


def test_union_ok(suites: list[str], weights: dict) -> None:
    shards = ss.assign(suites, 6, weights)
    assert ss.check_union(suites, {f"s{k}": m for k, m in enumerate(shards)}) == []


def test_union_detects_a_lost_suite(suites: list[str], weights: dict) -> None:
    shards = ss.assign(suites, 6, weights)
    shards[2] = shards[2][:-1]  # a suite that never ran
    lost = ss.assign(suites, 6, weights)[2][-1]
    problems = ss.check_union(suites, {f"s{k}": m for k, m in enumerate(shards)})
    assert any(lost in p and "silently lost" in p for p in problems)


def test_union_detects_duplicate_and_unknown(suites: list[str]) -> None:
    problems = ss.check_union(
        suites,
        {"s0": suites[:30] + ["nope"], "s1": suites[29:]},  # suites[29] run by both
    )
    text = "\n".join(problems)
    assert f"{suites[29]}: run twice" in text
    assert "nope: run by s0 but not in SOC_CI_SUITES" in text


def test_union_detects_an_empty_manifest(suites: list[str]) -> None:
    problems = ss.check_union(suites, {"s0": suites, "s1": []})
    assert any("s1: ran no suites" in p for p in problems)


def test_cli_union_exit_codes(tmp_path: Path, suites: list[str], weights: dict) -> None:
    shards = ss.assign(suites, 3, weights)
    files = []
    for k, m in enumerate(shards):
        p = tmp_path / f"ran{k}.txt"
        p.write_text("\n".join(m) + "\n", encoding="utf-8")
        files.append(str(p))
    ok = subprocess.run(
        [sys.executable, str(SCRIPT), "union", *files], capture_output=True, text=True, check=False
    )
    assert ok.returncode == 0, ok.stdout + ok.stderr
    # Drop one suite from one manifest: the gate must go red.
    first = Path(files[0])
    first.write_text("\n".join(shards[0][1:]) + "\n", encoding="utf-8")
    bad = subprocess.run(
        [sys.executable, str(SCRIPT), "union", *files], capture_output=True, text=True, check=False
    )
    assert bad.returncode == 1
    assert shards[0][0] in bad.stdout and "silently lost" in bad.stdout
    # A missing manifest file is the same as an empty one.
    gone = subprocess.run(
        [sys.executable, str(SCRIPT), "union", *files[1:], str(tmp_path / "missing.txt")],
        capture_output=True,
        text=True,
        check=False,
    )
    assert gone.returncode == 1


def test_cli_select_matches_assign(suites: list[str], weights: dict) -> None:
    for k in range(6):
        out = subprocess.run(
            [sys.executable, str(SCRIPT), "select", "--shard", str(k), "--nshards", "6"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.split()
        assert out == ss.assign(suites, 6, weights)[k]
    bad = subprocess.run(
        [sys.executable, str(SCRIPT), "select", "--shard", "6", "--nshards", "6"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert bad.returncode == 2


# ---------------------------------------------- Makefile (needs make + verilator)

needs_make = pytest.mark.skipif(
    not all(shutil.which(t) for t in ("make", "verilator", "cocotb-config")),
    reason="needs make, verilator and cocotb-config (the cocotb CI job provides them)",
)


def _make(args: list[str], root: Path) -> subprocess.CompletedProcess[str]:
    # The Makefile reads SOC_SHARD_WEIGHTS from the environment too; a CI job that exports it for
    # its real run must not change which weights these tests plan with.
    env = {k: v for k, v in os.environ.items() if k != "SOC_SHARD_WEIGHTS"}
    return subprocess.run(
        ["make", "--no-print-directory", "-C", str(SOC_DIR), f"SIM_BUILD_ROOT={root}", *args],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )


@needs_make
def test_print_target_agrees_with_the_script(tmp_path: Path, plain_suites: list[str]) -> None:
    r = _make(["print-soc-ci-suites"], tmp_path)
    assert r.returncode == 0, r.stderr
    assert r.stdout.split() == plain_suites


@needs_make
def test_soc_all_ci_expands_to_the_list_in_order(tmp_path: Path, plain_suites: list[str]) -> None:
    """`make -n MAKE=echo` turns each `$(MAKE) x y` into the line `x y`: the invocations run."""
    r = _make(["-n", "MAKE=echo", "soc_all_ci"], tmp_path)
    assert r.returncode == 0, r.stderr
    ran = [
        ln
        for ln in r.stdout.splitlines()
        if ln and not ln.startswith(("echo ", " ", "fi", "free_mb", "if ", "mkdir", "warning"))
    ]
    assert ran == [s.replace(":", " ") for s in plain_suites]


@needs_make
def test_soc_ci_shard_dry_run_selects_by_index(
    tmp_path: Path, suites: list[str], weights: dict
) -> None:
    for k in (0, NSHARDS - 1):
        r = _make(["-n", "MAKE=echo", "soc_ci_shard", f"SHARD={k}", f"NSHARDS={NSHARDS}"], tmp_path)
        assert r.returncode == 0, r.stderr
        ran = [
            ln for ln in r.stdout.splitlines() if ln and ln in {s.replace(":", " ") for s in suites}
        ]
        assert ran == [s.replace(":", " ") for s in ss.assign(suites, NSHARDS, weights)[k]]


@needs_make
def test_soc_ci_shard_refuses_to_run_nothing(tmp_path: Path) -> None:
    r = _make(["soc_ci_shard"], tmp_path)
    assert r.returncode != 0
    assert "set SUITES" in r.stderr


# ----------------------------------------------------------------------------- split suites


def test_parse_splits_and_expand_units() -> None:
    sp = ss.parse_splits("FOO := 1\nSOC_CI_SPLITS := \\\n    x=a,b|c \\\n    y=d\n")
    assert sp == {"x": [["a", "b"], ["c"]], "y": [["d"]]}
    assert ss.expand_units(["w", "x", "y"], sp) == [
        "w",
        "x:TESTCASE=a,b",
        "x:TESTCASE=c",
        "y:TESTCASE=d",
    ]
    assert ss.parse_splits("FOO := 1\n") == {}


@pytest.mark.parametrize("bad", ["x", "x=", "x=a||b", "x=a x=b"])
def test_parse_splits_rejects_malformed(bad: str) -> None:
    with pytest.raises(ValueError):
        ss.parse_splits_value(bad)


def test_expand_units_rejects_a_split_of_an_unknown_suite() -> None:
    with pytest.raises(ValueError, match="not in SOC_CI_SUITES"):
        ss.expand_units(["a"], {"nope": [["t"]]})


def test_every_split_covers_each_cocotb_test_exactly_once(plain_suites: list[str]) -> None:
    """A test missing from every slice would silently never run in the sharded coverage."""
    splits = ss.parse_splits(DEFAULT_MAKEFILE_TEXT)
    assert "soc_uart_boot" in splits
    for suite, slices in splits.items():
        assert suite in plain_suites
        module = {"soc_uart_boot": "test_uart_boot"}[suite]
        src = (SOC_DIR / f"{module}.py").read_text()
        tests = re.findall(r"@cocotb\.test\([^)]*\)\s*\nasync def (\w+)", src)
        assert tests, f"no @cocotb.test found in {module}.py"
        flat = [t for sl in slices for t in sl]
        assert sorted(flat) == sorted(tests), (
            f"{suite}: SOC_CI_SPLITS slices != the tests of {module}.py "
            f"(missing {sorted(set(tests) - set(flat))}, extra {sorted(set(flat) - set(tests))}, "
            f"duplicated {sorted({t for t in flat if flat.count(t) > 1})})"
        )


def test_split_units_are_sharded_and_unioned(suites: list[str], weights: dict) -> None:
    units = [u for u in suites if u.startswith("soc_uart_boot:")]
    assert len(units) == 4
    shards = ss.assign(suites, NSHARDS, weights)
    assert sum(u in m for m in shards for u in units) == 4
    assert ss.check_union(suites, {f"s{k}": m for k, m in enumerate(shards)}) == []
    # Running the whole module in one shard instead of its slices is a union failure, not a pass.
    problems = ss.check_union(
        suites, {"s0": [u for u in suites if u not in units] + ["soc_uart_boot"]}
    )
    assert any("soc_uart_boot: run by s0 but not in SOC_CI_SUITES" in p for p in problems)


# --------------------------------------- plain (uninstrumented) weights + cocotb.yml (bead 9ayu.2)

PLAIN_WEIGHTS = REPO_ROOT / "tools" / "verif" / "soc_shard_weights_plain.json"
COCOTB_YML = REPO_ROOT / ".github" / "workflows" / "cocotb.yml"
COCOTB_NSHARDS = 4  # must equal NSHARDS / the soc_shard matrix in cocotb.yml (checked below)


@pytest.fixture(scope="module")
def plain_weights() -> dict:
    return dict(ss.load_weights(PLAIN_WEIGHTS))


def test_plain_weights_name_only_real_suites(suites: list[str], plain_weights: dict) -> None:
    assert PLAIN_WEIGHTS.exists()
    unknown = sorted(set(plain_weights["suites"]) - set(suites))
    assert not unknown, f"{PLAIN_WEIGHTS.name} names suites not in SOC_CI_SUITES: {unknown}"
    groups = {g for v in plain_weights["suites"].values() if (g := v.get("group"))}
    assert groups <= set(plain_weights["groups"])


def test_plain_weights_are_a_different_cost_model(weights: dict, plain_weights: dict) -> None:
    """The file really is the uninstrumented one (an instrumented run is several times slower)."""
    common = set(weights["suites"]) & set(plain_weights["suites"])
    assert len(common) >= 30
    inst = sum(weights["suites"][s]["run_s"] for s in common)
    plain = sum(plain_weights["suites"][s]["run_s"] for s in common)
    assert 1.5 < inst / plain < 20, (inst, plain)


def test_plain_shards_are_balanced_and_split_the_uart_boot_slices(
    suites: list[str], plain_weights: dict
) -> None:
    shards = ss.assign(suites, COCOTB_NSHARDS, plain_weights)
    loads = ss.shard_loads(shards, plain_weights)
    assert max(loads) / min(loads) < 1.1, loads
    where = {s: k for k, m in enumerate(shards) for s in m}
    uart = [u for u in suites if u.startswith("soc_uart_boot:")]
    assert len({where[u] for u in uart}) == len(uart), "uart_boot slices must not share a shard"
    assert ss.check_union(suites, {f"s{k}": m for k, m in enumerate(shards)}) == []


def test_cocotb_workflow_shard_count_is_consistent() -> None:
    """NSHARDS, the matrix and COCOTB_NSHARDS agree; the aggregate job keeps its check name."""
    text = COCOTB_YML.read_text()
    m = re.search(r"^env:\n(?:  #.*\n)*  NSHARDS: '(\d+)'", text, re.M)
    assert m, "cocotb.yml has no top-level NSHARDS"
    n = int(m.group(1))
    mat = re.search(r"matrix:\n\s+shard: \[([0-9, ]+)\]", text)
    assert mat, "cocotb.yml soc_shard has no shard matrix"
    legs = [int(x) for x in mat.group(1).split(",")]
    assert legs == list(range(n)), f"matrix {legs} != range(NSHARDS={n})"
    assert n == COCOTB_NSHARDS
    # The aggregate gate keeps the old job name, needs the shards, and cannot be skipped.
    agg = re.search(
        r"^  soc_all:\n    name: cocotb soc_all \(SoC regression\)\n    needs: \[soc_shard\]\n"
        r"    if: \$\{\{ always\(\) \}\}\n",
        text,
        re.M,
    )
    assert agg, "the soc_all aggregate job lost its name, its needs or its always()"
    assert "SOC_SHARD_WEIGHTS: tools/verif/soc_shard_weights_plain.json" in text


@needs_make
def test_soc_ci_shard_honours_a_weights_override(
    tmp_path: Path, suites: list[str], plain_weights: dict
) -> None:
    k = 1
    r = _make(
        [
            "-n",
            "MAKE=echo",
            "soc_ci_shard",
            f"SHARD={k}",
            f"NSHARDS={COCOTB_NSHARDS}",
            f"SOC_SHARD_WEIGHTS={PLAIN_WEIGHTS}",
        ],
        tmp_path,
    )
    assert r.returncode == 0, r.stderr
    known = {s.replace(":", " ") for s in suites}
    ran = [ln for ln in r.stdout.splitlines() if ln in known]
    assert ran == [s.replace(":", " ") for s in ss.assign(suites, COCOTB_NSHARDS, plain_weights)[k]]
