#!/usr/bin/env python3
"""Exit non-zero unless a cocotb ``results.xml`` records a clean, non-empty run.

Why this exists (bead p6t8)
---------------------------
cocotb 1.9.2's makefile cannot propagate a test failure as an exit code.  Its own
``Makefile.inc`` says so ("since we can't set an exit code from cocotb") and its
``check_for_results_file`` macro only asserts that ``results.xml`` EXISTS, never
that it is free of failures.  A suite with failing tests therefore exits 0, which
makes every ``set -e`` in a multi-build-point recipe inert.  ``tb/cocotb/soc/Makefile``
redefines that macro to call this script as well.

The verdict logic is NOT reimplemented here: it is ``tools/eda/summarize.py``'s
``parse_cocotb`` (covered by ``tb/tests/test_eda_summarize.py``), so the checker and
the EDA wrapper cannot drift apart.  Not clean means any of:

  * a ``<failure>`` or ``<error>`` testcase,
  * a results.xml that parses but holds no passing test (bead ``dwp``: a clean exit
    with nothing run is not a pass),
  * a results.xml that is missing or does not parse.

Usage:  check_cocotb_results.py <results.xml>
Exit:   0 = clean, 1 = not clean (reason on stderr).  stdout stays silent when clean
because this runs once per build point of every suite.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "eda"))
import summarize  # noqa: E402  (path set up just above)

EXIT_CLEAN, EXIT_NOT_CLEAN = 0, 1


def check(results_xml: Path) -> tuple[bool, str]:
    """Return ``(clean, message)`` for one results.xml; message is empty when clean."""
    if not results_xml.is_file():
        return False, f"{results_xml}: results file is missing"

    status, summary = summarize.parse_cocotb("", 0, results_xml)
    if status == summarize.PASS:
        return True, ""

    lines = [f"{results_xml}: cocotb results are NOT clean"]
    if "errors" in summary:  # unparsable XML
        lines.extend(f"  {e}" for e in summary["errors"])
    else:
        lines.append(
            f"  passed={summary.get('passed', 0)} failed={summary.get('failed', 0)} "
            f"skipped={summary.get('skipped', 0)}"
        )
        if summary.get("note"):
            lines.append(f"  {summary['note']}")
        lines.extend(f"  FAIL {name}" for name in summary.get("failures", []))
    return False, "\n".join(lines)


def main(argv: list[str]) -> int:
    """CLI entry point; see the module docstring for the contract."""
    if len(argv) != 2:
        print(f"usage: {Path(argv[0]).name} <results.xml>", file=sys.stderr)
        return EXIT_NOT_CLEAN
    clean, message = check(Path(argv[1]))
    if not clean:
        print(message, file=sys.stderr)
    return EXIT_CLEAN if clean else EXIT_NOT_CLEAN


if __name__ == "__main__":
    sys.exit(main(sys.argv))
