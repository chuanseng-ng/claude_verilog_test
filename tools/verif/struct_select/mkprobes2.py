# ruff: noqa: E501
"""Round-2 probes: vary struct shape / packaging to find what triggers the Synlig mis-offset.

usage: mkprobes2.py <outdir>
Probe name: <id>__<member>_<hi>_<lo>.  Each probe has ONE struct typedef (own package unless 'mod_'
prefixed, in which case the typedef is local to the module) and one select on a port-typed struct.
"""

import os
import sys


def struct_def(members: list) -> str:
    body = " ".join(f"logic [{w - 1}:0] {n};" for n, w in members)
    return f"typedef struct packed {{ {body} }} s_t;"


def probe(members: list, mem: str, hi: int, lo: int, where: str = "pkg") -> str:
    width = hi - lo + 1
    expr = f"s.{mem}[{hi}:{lo}]" if hi != lo else f"s.{mem}[{hi}]"
    if where == "pkg":
        return (
            f"package pk; {struct_def(members)} endpackage\n"
            f"module top(input pk::s_t s, output logic [{width - 1}:0] y);\n"
            f"  assign y = {expr};\nendmodule\n"
        )
    return (
        f"module top(input logic [{sum(w for _, w in members) - 1}:0] d, "
        f"output logic [{width - 1}:0] y);\n  {struct_def(members)}\n  s_t s; assign s = d;\n"
        f"  assign y = {expr};\nendmodule\n"
    )


def build() -> dict:
    p: dict = {}
    two88 = [("a", 8), ("b", 8)]
    # id, members (MSB first), member, hi, lo, where
    cases = [
        ("A01", two88, "b", 3, 0, "pkg"),
        ("A02", two88, "b", 7, 4, "pkg"),
        ("A03", two88, "a", 7, 4, "pkg"),
        ("A04", [("a", 16), ("b", 8)], "b", 3, 0, "pkg"),
        ("A05", [("a", 8), ("b", 16)], "b", 3, 0, "pkg"),
        ("A06", [("a", 8), ("b", 16)], "b", 7, 4, "pkg"),
        ("A07", [("a", 8), ("b", 16)], "b", 15, 12, "pkg"),
        ("A08", [("a", 8), ("b", 8), ("c", 8)], "c", 3, 0, "pkg"),
        ("A09", [("a", 8), ("b", 8), ("c", 8)], "b", 3, 0, "pkg"),
        ("A10", [("a", 8), ("b", 8), ("c", 8)], "a", 3, 0, "pkg"),
        ("A11", [("a", 8), ("b", 8), ("c", 8)], "b", 7, 4, "pkg"),
        ("A12", [("a", 8), ("b", 8)], "b", 0, 0, "pkg"),
        ("A13", [("a", 8), ("b", 8)], "b", 5, 5, "pkg"),
        ("A14", [("a", 8), ("b", 8)], "b", 7, 0, "pkg"),
        ("A15", [("a", 8), ("b", 8)], "b", 1, 0, "pkg"),
        ("A16", [("a", 8), ("b", 8)], "b", 2, 1, "pkg"),
        ("A17", [("a", 8), ("b", 8)], "b", 6, 3, "pkg"),
        # same member names as the earlier (equivalent) 4-member struct, alone in its package
        (
            "B01",
            [("f3", 8), ("f2", 4), ("f1", 16), ("f0", 12)],
            "f1",
            7,
            4,
            "pkg",
        ),
        (
            "B02",
            [("f3", 8), ("f2", 4), ("f1", 16), ("f0", 12)],
            "f3",
            3,
            0,
            "pkg",
        ),
        ("B03", [("a", 8), ("b", 8), ("c", 8), ("d", 8)], "b", 3, 0, "pkg"),
        ("B04", [("f1", 8), ("f0", 8)], "f0", 3, 0, "pkg"),
        ("B05", [("hi", 8), ("lo", 8)], "lo", 3, 0, "pkg"),
        # local (module-scope) typedef
        ("L01", two88, "b", 3, 0, "mod"),
        ("L02", [("f3", 8), ("f2", 4), ("f1", 16), ("f0", 12)], "f1", 7, 4, "mod"),
        ("L03", two88, "a", 7, 4, "mod"),
        # mimic if_id_t: pc, instruction, ...
        (
            "M01",
            [("valid", 1), ("instruction", 32), ("pc", 32)],
            "instruction",
            19,
            15,
            "pkg",
        ),
        (
            "M02",
            [("valid", 1), ("instruction", 32), ("pc", 32)],
            "instruction",
            24,
            20,
            "pkg",
        ),
        (
            "M03",
            [("instruction", 32), ("pc", 32)],
            "instruction",
            19,
            15,
            "pkg",
        ),
        ("M04", [("pc", 32), ("instruction", 32)], "instruction", 19, 15, "pkg"),
    ]
    for cid, mem, m, hi, lo, where in cases:
        p[f"{cid}__{m}_{hi}_{lo}"] = probe(mem, m, hi, lo, where)
    return p


def main() -> int:
    out = sys.argv[1]
    os.makedirs(out, exist_ok=True)
    probes = build()
    for k, v in probes.items():
        with open(os.path.join(out, k + ".sv"), "w", encoding="utf-8") as f:
            f.write(v)
    print(len(probes), "probes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
