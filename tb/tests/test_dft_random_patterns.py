"""random_patterns.py: seeded patterns in the Quaigh `.test` layout.

Doc: tm:ch:dft-architecture:1812-scan-replay
"""

import json
import sys
from pathlib import Path

import pytest

ATPG = Path(__file__).resolve().parents[2] / "tools" / "dft" / "atpg"
sys.path.insert(0, str(ATPG))
import random_patterns  # type: ignore[import-not-found]  # noqa: E402
from replay_vectors import read_patterns  # type: ignore[import-not-found]  # noqa: E402

PLAN: dict[str, list[dict[str, str]]] = {"inputs": [{}] * 3, "latches": [{}] * 5}


def test_width_is_inputs_plus_latches():
    assert random_patterns.width_of(PLAN) == 8


def test_same_seed_same_patterns_other_seed_differs():
    a = random_patterns.make_patterns(64, 4, 7)
    assert a == random_patterns.make_patterns(64, 4, 7)
    assert a != random_patterns.make_patterns(64, 4, 8)
    assert all(len(p) == 64 and set(p) <= {"0", "1"} for p in a)


def test_file_round_trips_through_the_replay_reader(tmp_path):
    plan = tmp_path / "map.json"
    plan.write_text(json.dumps(PLAN))
    out = tmp_path / "p.test"
    assert (
        random_patterns.main(["--map", str(plan), "--count", "5", "--seed", "3", "--out", str(out)])
        == 0
    )
    got = read_patterns(out, None)
    assert sorted(got) == [1, 2, 3, 4, 5]
    assert [got[i] for i in sorted(got)] == random_patterns.make_patterns(8, 5, 3)


def test_patterns_are_not_constant():
    # negative control: a generator stuck at one value would still pass the width checks above
    bits = "".join(random_patterns.make_patterns(256, 4, 1))
    assert 0.3 < bits.count("1") / len(bits) < 0.7


@pytest.mark.parametrize("width,count", [(0, 3), (8, 0), (-1, 2)])
def test_rejects_empty_request(width, count):
    with pytest.raises(ValueError):
        random_patterns.make_patterns(width, count, 1)
