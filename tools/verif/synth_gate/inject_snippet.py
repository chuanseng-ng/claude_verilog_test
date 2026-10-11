#!/usr/bin/env python3
"""Write a scratch copy of an RTL file with one line replaced by a snippet (gate negative controls)."""

import sys
from pathlib import Path


def main(src: str, dst: str, snippet: str, needle: str) -> int:
    """Replace the single line equal to ``needle`` in ``src`` by ``snippet``'s text, into ``dst``."""
    lines = Path(src).read_text(encoding="utf-8").splitlines(keepends=True)
    hits = [i for i, ln in enumerate(lines) if ln.strip() == needle]
    if len(hits) != 1:
        print(
            f"inject_snippet: expected exactly one line '{needle}' in {src}, found {len(hits)}",
            file=sys.stderr,
        )
        return 3
    lines[hits[0]] = Path(snippet).read_text(encoding="utf-8")
    Path(dst).write_text("".join(lines), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:5]))
