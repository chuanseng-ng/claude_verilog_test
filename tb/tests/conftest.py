"""Shared pytest setup for tb/tests.

Git hooks export GIT_DIR, GIT_WORK_TREE and GIT_INDEX_FILE. A test that runs `git init` or
`git config` in a temporary directory inherits them, and git then writes to the repository that
ran the hook instead of the temporary one. Remove the variables before any test module loads.
"""

from __future__ import annotations

import os
from collections.abc import MutableMapping

GIT_LOCATION_VARS = (
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_INDEX_FILE",
    "GIT_COMMON_DIR",
    "GIT_OBJECT_DIRECTORY",
    "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    "GIT_PREFIX",
    "GIT_NAMESPACE",
)


def scrub_git_env(env: MutableMapping[str, str]) -> list[str]:
    """Remove the variables that point git at a repository; return the names removed."""
    removed = [name for name in GIT_LOCATION_VARS if name in env]
    for name in removed:
        del env[name]
    return removed


scrub_git_env(os.environ)
