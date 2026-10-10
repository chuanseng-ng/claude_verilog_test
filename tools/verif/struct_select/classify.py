"""Classify run_probes.sh summary lines.

usage: classify.py <summary.txt>...
Classes: EQUIV | WARN+X (not equivalent, out-of-bounds warning, result has x) |
         WARN+WRONG (not equivalent, warning printed, but result bits are wrong data) |
         SILENT (not equivalent, no out-of-bounds warning at all).
"""

import sys
from collections import Counter


def classify(line: str) -> tuple:
    parts = [p.strip() for p in line.rstrip("\n").split(" | ")]
    name, verdict = parts[0], parts[1]
    oob = int(parts[2].split("=")[1]) if len(parts) > 2 and "=" in parts[2] else 0
    syn = parts[3] if len(parts) > 3 else ""
    if verdict == "EQUIV":
        return name, "EQUIV"
    if verdict != "NOT-EQUIV":
        return name, verdict
    if oob == 0:
        return name, "SILENT"
    return name, "WARN+X" if "x" in syn.replace("connect", "") else "WARN+WRONG"


def main() -> int:
    for path in sys.argv[1:]:
        cnt: Counter = Counter()
        with open(path, encoding="utf-8") as f:
            for ln in f:
                if " | " not in ln:
                    continue
                name, cls = classify(ln)
                cnt[cls] += 1
                if cls in ("SILENT", "WARN+WRONG"):
                    print(f"{path}: {name}: {cls}")
        print(path, dict(cnt))
    return 0


if __name__ == "__main__":
    sys.exit(main())
