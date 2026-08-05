#!/usr/bin/env python3
"""Idempotently ensure ~/.config/rtk/config.toml has the `[hooks]`
`transparent_prefixes` this repo needs, without touching anything else.

Without these three prefixes, the PreToolUse hook cannot see through
`nix develop --command ...` / `nix-shell --run ...`, so none of the sim/lint
output gets filtered by `.rtk/filters.toml` -- and it fails *quietly*: the
command still runs, it is just not compressed, so there is no error to
notice. That silent-failure mode is exactly why this script exists instead
of a one-line "add this to your config" note in a README.

Safety model: this script has no TOML writer and does not attempt to be one.
It only ever does one of three things to the file:

  1. transparent_prefixes already has all required entries -> no write.
  2. transparent_prefixes exists as a single-line array whose every element
     the double-quote parser recognises -> that one line is rewritten in
     place to hold the union of its existing entries and the required ones.
     Every other line is untouched. If any element is NOT recognised (TOML
     literal strings, `'like this'`), the line is left alone and case 3
     applies -- rewriting it would silently delete the user's values.
  3. No [hooks] section, or a [hooks] section with no transparent_prefixes
     line (including a multi-line array, which this script deliberately
     does not try to parse) -> nothing is written. The exact TOML snippet
     to paste in by hand is printed instead, and the process exits 1.

Case 3 is the deliberate "cannot edit this safely" bail-out: guessing wrong
about a hand-written TOML file's structure and corrupting a user's config is
worse than asking them to paste four lines once.

Stdlib only -- this runs from `make setup`, outside the repo virtualenv.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REQUIRED_PREFIXES = [
    "nix develop --command",
    "nix develop -c",
    "nix-shell --run",
]

DEFAULT_CONFIG_PATH = Path.home() / ".config" / "rtk" / "config.toml"

_SECTION_RE = re.compile(r"^\[(?P<name>[^\]]+)\]\s*$")
_ARRAY_LINE_RE = re.compile(r"^(?P<indent>[ \t]*)transparent_prefixes\s*=\s*\[(?P<body>.*)\]\s*$")
_STRING_RE = re.compile(r'"((?:[^"\\]|\\.)*)"')


def _snippet() -> str:
    prefixes = ", ".join(json.dumps(p) for p in REQUIRED_PREFIXES)
    return f"[hooks]\ntransparent_prefixes = [{prefixes}]\n"


def sync(config_path: Path) -> tuple[bool, str]:
    """Ensure REQUIRED_PREFIXES are present. Returns (ok, message).

    ok is False exactly when the caller must paste the printed snippet by
    hand -- the file was left untouched in that case.
    """
    if not config_path.is_file():
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(_snippet(), encoding="utf-8")
        return True, f"created {config_path} with a new [hooks] section"

    lines = config_path.read_text(encoding="utf-8").splitlines(keepends=True)

    hooks_start: int | None = None
    array_line: int | None = None
    in_hooks = False
    for i, line in enumerate(lines):
        section = _SECTION_RE.match(line.rstrip("\n"))
        if section:
            if in_hooks:
                break  # left the [hooks] section without finding the array
            in_hooks = section.group("name") == "hooks"
            if in_hooks:
                hooks_start = i
            continue
        if in_hooks and _ARRAY_LINE_RE.match(line.rstrip("\n")):
            array_line = i

    if array_line is not None:
        match = _ARRAY_LINE_RE.match(lines[array_line].rstrip("\n"))
        assert match is not None
        body = match.group("body")
        existing = _STRING_RE.findall(body)
        # _STRING_RE only understands double-quoted strings. TOML also allows
        # literal strings ('custom-wrapper'), which would parse as zero entries
        # and silently DELETE the user's values when the line is rewritten.
        # Bail out to the manual-edit path unless every element was recognised.
        residue = _STRING_RE.sub("", body)
        if residue.strip(" \t,"):
            return False, (
                f"{config_path}: transparent_prefixes contains values this script "
                "cannot parse (only double-quoted strings are understood), so it "
                "was left untouched. Add these by hand inside [hooks]:\n\n"
                f"transparent_prefixes = [{', '.join(json.dumps(p) for p in REQUIRED_PREFIXES)}]\n"
            )
        missing = [p for p in REQUIRED_PREFIXES if p not in existing]
        if not missing:
            return True, f"{config_path}: transparent_prefixes already complete"
        merged = existing + missing
        rendered = ", ".join(json.dumps(p) for p in merged)
        lines[array_line] = f"{match.group('indent')}transparent_prefixes = [{rendered}]\n"
        config_path.write_text("".join(lines), encoding="utf-8")
        return True, f"{config_path}: added {missing} to transparent_prefixes"

    if hooks_start is None:
        # No [hooks] section anywhere: append one. Purely additive.
        sep = "" if (lines and lines[-1].endswith("\n")) else "\n"
        lines.append(f"{sep}\n{_snippet()}")
        config_path.write_text("".join(lines), encoding="utf-8")
        return True, f"{config_path}: appended a new [hooks] section"

    # [hooks] exists but transparent_prefixes doesn't appear as a single-line
    # array within it (missing entirely, or a multi-line array this script
    # does not parse) -- bail out rather than guess where to insert a line.
    return False, (
        f"{config_path} has a [hooks] section without a single-line "
        "transparent_prefixes array this script can safely edit. Add this "
        "line inside [hooks] by hand:\n\n"
        f"transparent_prefixes = [{', '.join(json.dumps(p) for p in REQUIRED_PREFIXES)}]\n"
    )


def main() -> int:
    """Sync the config, print the result, and exit 1 on the manual-edit case."""
    config_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_CONFIG_PATH
    ok, message = sync(config_path)
    print(message)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
