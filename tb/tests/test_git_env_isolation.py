"""Tests for the git environment scrub in tb/tests/conftest.py."""

from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

TESTS_DIR = Path(__file__).resolve().parent


def _load_conftest() -> ModuleType:
    spec = importlib.util.spec_from_file_location("tb_tests_conftest", TESTS_DIR / "conftest.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_scrub_removes_only_the_location_variables() -> None:
    """Scrub removes only the location variables."""
    conftest = _load_conftest()
    env = {"GIT_DIR": "x", "GIT_INDEX_FILE": "y", "GIT_AUTHOR_NAME": "keep", "PATH": "p"}
    assert conftest.scrub_git_env(env) == ["GIT_DIR", "GIT_INDEX_FILE"]
    assert env == {"GIT_AUTHOR_NAME": "keep", "PATH": "p"}


def test_no_location_variable_reaches_a_test() -> None:
    """No location variable reaches a test."""
    conftest = _load_conftest()
    assert not [name for name in conftest.GIT_LOCATION_VARS if name in os.environ]


@pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")
def test_git_init_under_a_hook_environment_stays_in_tmp(tmp_path: Path) -> None:
    """A pytest run that starts with GIT_DIR set must not write to that GIT_DIR."""
    decoy = tmp_path / "decoy.git"
    decoy.mkdir()
    work = tmp_path / "work"
    work.mkdir()
    probe = tmp_path / "test_probe.py"
    probe.write_text(
        "import subprocess\n"
        "def test_init(tmp_path):\n"
        "    subprocess.run(['git', '-C', str(tmp_path), 'init', '-q'], check=True,\n"
        "                   stdin=subprocess.DEVNULL, capture_output=True)\n"
        "    assert (tmp_path / '.git').is_dir()\n",
        encoding="utf-8",
    )
    shutil.copy(TESTS_DIR / "conftest.py", tmp_path / "conftest.py")
    env = dict(os.environ, GIT_DIR=str(decoy))
    res = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", str(probe)],
        cwd=work,
        env=env,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        check=False,
    )
    assert res.returncode == 0, res.stdout + res.stderr
    assert not list(decoy.iterdir())
