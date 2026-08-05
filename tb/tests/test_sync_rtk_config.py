"""Unit tests for tools/setup/sync_rtk_config.py.

The behaviour under test that matters most: this script edits a hand-written
TOML file it does not fully parse. It must never guess wrong and corrupt
content it does not understand -- every case where it cannot safely find
`transparent_prefixes` inside `[hooks]` must leave the file byte-for-byte
untouched and report failure, rather than silently doing nothing while
claiming success (the same discipline as bead `dwp` for the EDA parsers).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
_SPEC = importlib.util.spec_from_file_location(
    "sync_rtk_config", REPO_ROOT / "tools" / "setup" / "sync_rtk_config.py"
)
assert _SPEC and _SPEC.loader
sync_rtk_config = importlib.util.module_from_spec(_SPEC)
sys.modules["sync_rtk_config"] = sync_rtk_config
_SPEC.loader.exec_module(sync_rtk_config)

REQUIRED = sync_rtk_config.REQUIRED_PREFIXES


def test_missing_file_is_created_with_hooks_section(tmp_path: Path) -> None:
    """A from-scratch machine with no rtk config gets a minimal, correct one."""
    config = tmp_path / "config.toml"
    ok, _ = sync_rtk_config.sync(config)
    assert ok
    assert config.is_file()
    for prefix in REQUIRED:
        assert prefix in config.read_text(encoding="utf-8")


def test_already_complete_is_a_noop(tmp_path: Path) -> None:
    """All three prefixes already present -> file is not rewritten at all."""
    config = tmp_path / "config.toml"
    prefixes = ", ".join(f'"{p}"' for p in REQUIRED)
    text = f"[hooks]\ntransparent_prefixes = [{prefixes}]\n"
    config.write_text(text, encoding="utf-8")
    ok, message = sync_rtk_config.sync(config)
    assert ok
    assert "already complete" in message
    assert config.read_text(encoding="utf-8") == text


def test_partial_array_gets_missing_entries_added(tmp_path: Path) -> None:
    """One prefix missing from an existing array: it is appended, nothing
    else in the file changes, and existing user entries are kept.
    """
    config = tmp_path / "config.toml"
    text = (
        "[tracking]\n"
        "enabled = true\n"
        "\n"
        "[hooks]\n"
        "exclude_commands = []\n"
        'transparent_prefixes = ["nix develop --command", "nix-shell --run", "my-custom-wrapper"]\n'
        "\n"
        "[limits]\n"
        "grep_max_results = 200\n"
    )
    config.write_text(text, encoding="utf-8")
    ok, _ = sync_rtk_config.sync(config)
    assert ok
    new_text = config.read_text(encoding="utf-8")
    for prefix in [*REQUIRED, "my-custom-wrapper"]:
        assert prefix in new_text
    # Every line outside the transparent_prefixes line is untouched.
    old_lines = text.splitlines()
    new_lines = new_text.splitlines()
    assert len(old_lines) == len(new_lines)
    for old, new in zip(old_lines, new_lines):
        if "transparent_prefixes" not in old:
            assert old == new


def test_sync_is_idempotent(tmp_path: Path) -> None:
    """Running twice produces the same file the second time."""
    config = tmp_path / "config.toml"
    config.write_text(
        '[hooks]\ntransparent_prefixes = ["nix develop --command"]\n', encoding="utf-8"
    )
    sync_rtk_config.sync(config)
    once = config.read_text(encoding="utf-8")
    ok, message = sync_rtk_config.sync(config)
    assert ok
    assert "already complete" in message
    assert config.read_text(encoding="utf-8") == once


def test_no_hooks_section_appends_one(tmp_path: Path) -> None:
    """No [hooks] table anywhere: a new one is appended, existing content
    is preserved verbatim.
    """
    config = tmp_path / "config.toml"
    text = "[tracking]\nenabled = true\n"
    config.write_text(text, encoding="utf-8")
    ok, _ = sync_rtk_config.sync(config)
    assert ok
    new_text = config.read_text(encoding="utf-8")
    assert new_text.startswith(text)
    for prefix in REQUIRED:
        assert prefix in new_text


def test_hooks_without_transparent_prefixes_bails_out_untouched(tmp_path: Path) -> None:
    """[hooks] exists but has no transparent_prefixes line: refuse to guess
    where to insert one. File must be byte-for-byte untouched and the call
    must report failure (not a silent no-op success).
    """
    config = tmp_path / "config.toml"
    text = '[hooks]\nexclude_commands = ["rm"]\n\n[limits]\ngrep_max_results = 200\n'
    config.write_text(text, encoding="utf-8")
    ok, message = sync_rtk_config.sync(config)
    assert not ok
    assert config.read_text(encoding="utf-8") == text
    for prefix in REQUIRED:
        assert prefix in message  # the paste-by-hand snippet is still shown


def test_multiline_array_bails_out_untouched(tmp_path: Path) -> None:
    """A multi-line transparent_prefixes array is deliberately not parsed --
    same bail-out contract as the missing-key case.
    """
    config = tmp_path / "config.toml"
    text = '[hooks]\ntransparent_prefixes = [\n  "nix develop --command",\n]\n'
    config.write_text(text, encoding="utf-8")
    ok, _ = sync_rtk_config.sync(config)
    assert not ok
    assert config.read_text(encoding="utf-8") == text


def test_main_exits_nonzero_on_bail_out(tmp_path: Path) -> None:
    """The CLI entry point propagates the bail-out as a real exit code, not
    just a printed message a caller could miss.
    """
    config = tmp_path / "config.toml"
    config.write_text("[hooks]\nexclude_commands = []\n", encoding="utf-8")
    argv_backup = sys.argv
    try:
        sys.argv = ["sync_rtk_config.py", str(config)]
        rc = sync_rtk_config.main()
    finally:
        sys.argv = argv_backup
    assert rc == 1


def test_literal_string_array_is_left_untouched(tmp_path: Path) -> None:
    """TOML literal strings ('x') are not decodable by the line parser.

    Rewriting the line anyway would silently DELETE the user's entries, since
    the double-quote regex sees zero elements. The file must stay byte-for-byte
    identical and sync() must report failure so the caller pastes by hand.
    """
    cfg = tmp_path / "config.toml"
    original = "[hooks]\ntransparent_prefixes = ['custom-wrapper']\n"
    cfg.write_text(original, encoding="utf-8")

    ok, message = sync_rtk_config.sync(cfg)

    assert ok is False
    assert cfg.read_text(encoding="utf-8") == original
    assert "cannot parse" in message
