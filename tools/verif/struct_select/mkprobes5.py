# ruff: noqa: E501
"""Round-5: read the Synlig stride directly, using structs with large members so hi*X stays in bounds.

usage: mkprobes5.py <outdir>
Members are listed MSB first.  A scalar member ("s") is declared `logic s;` (no packed range).
"""

import os
import sys

S = ("s", "")


def r(name: str, width: int) -> tuple:
    return (name, f"[{width - 1}:0] ")


CASES = {
    "t01": ([r("a", 64), r("b", 64), S], "a"),
    "t02": ([r("a", 64), r("b", 64), S], "b"),
    "t03": ([S, r("a", 64), r("b", 64)], "a"),
    "t04": ([S, r("a", 64), r("b", 64)], "b"),
    "t05": ([r("a", 64), S, r("b", 64)], "a"),
    "t06": ([r("a", 64), S, r("b", 64)], "b"),
    "t07": ([r("a", 16), r("b", 32), S], "a"),
    "t08": ([r("a", 16), r("b", 32), S], "b"),
    "t09": ([r("a", 16), r("b", 40), r("c", 8), S], "a"),
    "t10": ([r("a", 16), r("b", 40), r("c", 8), S], "b"),
    "t11": ([r("a", 16), r("b", 40), r("c", 8), S], "c"),
    "t12": ([r("a", 16), r("b", 32)], "a"),
    "t13": ([r("a", 16), r("b", 32)], "b"),
    "t14": ([r("a", 32), r("b", 16)], "a"),
    "t15": ([r("a", 32), r("b", 16)], "b"),
    "t16": ([r("a", 64), S], "a"),
    "t17": ([S, r("a", 64)], "a"),
    "t18": ([r("a", 64), r("b", 64), r("c", 64)], "a"),
    "t19": ([r("a", 64), r("b", 64), r("c", 64)], "b"),
    "t20": ([r("a", 64), r("b", 64), r("c", 64)], "c"),
}


def main() -> int:
    out = sys.argv[1]
    os.makedirs(out, exist_ok=True)
    n = 0
    for k, (members, mem) in CASES.items():
        body = " ".join(f"logic {rng}{nm};" for nm, rng in members)
        for hi, lo in [(1, 0), (3, 2)]:
            wd = hi - lo + 1
            src = (
                f"package pk; typedef struct packed {{ {body} }} t_t; endpackage\n"
                f"module top(input pk::t_t s, output logic [{wd - 1}:0] y);\n"
                f"  assign y = s.{mem}[{hi}:{lo}];\nendmodule\n"
            )
            with open(os.path.join(out, f"{k}_{mem}_{hi}_{lo}.sv"), "w", encoding="utf-8") as f:
                f.write(src)
            n += 1
    print(n, "probes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
