# ruff: noqa: E501
"""Round-3: seeded random struct shapes, to fit the Synlig mis-offset rule.

usage: mkprobes3.py <outdir> [n=120] [seed=1]
Probe file name encodes the layout:  r<idx>__<w_msb>_<...>_<w_lsb>__m<k>_<hi>_<lo>  where members are
named m0 (LSB) .. m<n-1> (MSB) in the packed struct declared MSB-first.
"""

import os
import random
import sys


def main() -> int:
    out = sys.argv[1]
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 120
    seed = int(sys.argv[3]) if len(sys.argv) > 3 else 1
    os.makedirs(out, exist_ok=True)
    rnd = random.Random(seed)
    made = 0
    while made < n:
        nm = rnd.choice([2, 3, 3, 4, 5])
        widths = [rnd.choice([1, 3, 4, 5, 8, 12, 16, 32]) for _ in range(nm)]  # m0..m(nm-1)
        k = rnd.randrange(nm)
        w = widths[k]
        if w < 2:
            continue
        hi = rnd.randrange(0, w)
        lo = rnd.randrange(0, hi + 1)
        if rnd.random() < 0.25:
            hi = lo
        body = " ".join(f"logic [{widths[i] - 1}:0] m{i};" for i in reversed(range(nm)))
        expr = f"s.m{k}[{hi}:{lo}]" if hi != lo else f"s.m{k}[{hi}]"
        wd = hi - lo + 1
        name = f"r{made:03d}__{'_'.join(str(x) for x in reversed(widths))}__m{k}_{hi}_{lo}"
        src = (
            f"package pk; typedef struct packed {{ {body} }} s_t; endpackage\n"
            f"module top(input pk::s_t s, output logic [{wd - 1}:0] y);\n"
            f"  assign y = {expr};\nendmodule\n"
        )
        with open(os.path.join(out, name + ".sv"), "w", encoding="utf-8") as f:
            f.write(src)
        made += 1
    print(made, "probes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
