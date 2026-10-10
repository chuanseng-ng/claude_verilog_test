"""Print Synlig/sv2v net connections + Synlig warnings for probes.

usage: show.py <outdir> <probe-name>...
"""

import re
import sys


def connects(path: str) -> list:
    with open(path, encoding="utf-8") as f:
        return [ln.strip() for ln in f if ln.strip().startswith("connect")]


def main() -> int:
    out = sys.argv[1]
    for n in sys.argv[2:]:
        print("==", n)
        with open(f"{out}/{n}.synlig.log", encoding="utf-8") as f:
            for ln in f:
                if re.search(r"warn|error", ln, re.I):
                    print("  W:", ln.strip())
        print("  synlig:", "; ".join(connects(f"{out}/{n}.synlig.il")))
        print("  sv2v  :", "; ".join(connects(f"{out}/{n}.sv2v.il")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
