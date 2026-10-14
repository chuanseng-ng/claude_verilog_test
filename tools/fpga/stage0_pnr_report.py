#!/usr/bin/env python3
"""stage0_pnr_report.py -- summarise nextpnr-ecp5 logs from stage0_pnr_ecp5.sh (bead hlrm).

usage: stage0_pnr_report.py <out-dir> <tag> [<tag> ...]

For each tag reads ``<out-dir>/<tag>.log`` (nextpnr --log) and ``<out-dir>/<tag>.time``
(/usr/bin/time -v) and prints a markdown summary: post-route ``Max frequency`` per
clock domain, the worst cross-domain frequency, the post-route critical path of every
intra-domain clock (LUT levels, logic ns vs routing ns, source and sink), the
utilisation lines and the wall / peak-RSS figures.

Everything printed is copied from the log; nothing is estimated. nextpnr does no hold
analysis, so no hold number is produced or implied.
"""

import re
import sys
from pathlib import Path

FREQ_RE = re.compile(
    r"(?:Info|Warning): Max frequency for\s+(clock|posedge|negedge)\s+(.*?)\s*:\s*"
    r"([\d.]+) MHz \((PASS|FAIL) at ([\d.]+) MHz\)"
)
CP_RE = re.compile(r"Info: Critical path report for clock '(.*?)' \((\w+) -> (\w+)\):")
UTIL_RE = re.compile(
    r"Info:\s+(TRELLIS_FF|TRELLIS_COMB|TRELLIS_RAMW|TRELLIS_IO|DCCA|DP16KD|MULT18X18D|ALU54B)"
    r":\s+(\d+)/\s*(\d+)\s+(\d+)%"
)


def _last_block(lines: list[str]) -> list[str]:
    """Lines after the last ``Routing complete``, i.e. the post-route reports."""
    start = 0
    for i, ln in enumerate(lines):
        if "Routing complete" in ln:
            start = i
    return lines[start:]


def _critical_paths(lines: list[str]) -> list[str]:
    out: list[str] = []
    for i, ln in enumerate(lines):
        m = CP_RE.search(ln)
        if not m:
            continue
        levels = 0
        total = ""
        src = snk = ""
        for ln2 in lines[i + 1 :]:
            if "Critical path report" in ln2 or "Max frequency" in ln2:
                break
            if re.search(r"Info:\s+logic\s", ln2):
                levels += 1
            if " Source " in ln2 and "clk-to-q" in ln2:
                src = ln2.split("Source ")[1].strip()
            if " logic, " in ln2:
                total = ln2.replace("Info:", "").strip()
            if "Source" in ln2 and "setup" in ln2:
                snk = ln2.split("Source ")[1].strip()
        out.append(f"- `{m.group(1)}`: {levels} LUT levels, {total}; start `{src}`, end `{snk}`")
    return out


def _rss_wall(path: Path) -> str:
    if not path.exists():
        return "n/a"
    txt = path.read_text()
    wall = re.search(r"Elapsed \(wall clock\) time.*: (\S+)", txt)
    rss = re.search(r"Maximum resident set size \(kbytes\): (\d+)", txt)
    rss_gb = f"{int(rss.group(1)) / 1048576:.2f} GB" if rss else "n/a"
    return f"wall {wall.group(1) if wall else 'n/a'}, peak RSS {rss_gb}"


def summarise(out: Path, tag: str) -> str:
    lines = (out / f"{tag}.log").read_text().splitlines()
    post = _last_block(lines)
    res = [f"### {tag}", ""]
    clocks = [m for ln in post if (m := FREQ_RE.search(ln)) and m.group(1) == "clock"]
    cross = [m for ln in post if (m := FREQ_RE.search(ln)) and m.group(1) != "clock"]
    res.append("| clock domain (post-route) | Fmax MHz | vs target |")
    res.append("|---|---|---|")
    for m in clocks:
        res.append(f"| `{m.group(2)}` | {m.group(3)} | {m.group(4)} at {m.group(5)} |")
    if cross:
        worst = min(cross, key=lambda m: float(m.group(3)))
        res.append("")
        res.append(
            f"Worst cross-domain frequency: `{worst.group(1)} {worst.group(2)}` "
            f"{worst.group(3)} MHz ({len(cross)} cross-domain relations listed)"
        )
    res.append("")
    res.extend(_critical_paths(post))
    res.append("")
    util = {
        m.group(1): f"{m.group(2)}/{m.group(3)} ({m.group(4)}%)"
        for ln in lines
        if (m := UTIL_RE.search(ln))
    }
    res.append("Utilisation: " + ", ".join(f"{k} {v}" for k, v in util.items()))
    res.append("")
    res.append("Run: " + _rss_wall(out / f"{tag}.time"))
    res.append("")
    return "\n".join(res)


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        print(__doc__)
        return 2
    out = Path(argv[1])
    for tag in argv[2:]:
        print(summarise(out, tag))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
