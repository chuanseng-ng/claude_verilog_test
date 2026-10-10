# ruff: noqa: E501
"""Generate Synlig struct-member part-select probes (bead ainf).

usage: mkprobes.py <outdir>

Every probe is a tiny module `top` whose output is a select of a packed struct member.
`s_t` layout (LSB first): f0@0 w12, f1@12 w16, f2@28 w4, f3@32 w8 (40 bits).
`n_t` nests s_t: tail@0 w5, in@5 w40, pad@45 w8 (53 bits).
Each probe is elaborated by Synlig and by sv2v; run_probes.sh compares them by miter + SAT
and dumps the net connections Synlig produced.
"""

import os
import sys

PK = """package pk;
  typedef struct packed { logic [7:0] f3; logic [3:0] f2; logic [15:0] f1; logic [11:0] f0; } s_t;
  typedef struct packed { logic [7:0] pad; s_t in; logic [4:0] tail; } n_t;
endpackage
"""
PK2 = """package pk2;
  typedef struct packed { logic [7:0] a; logic [7:0] b; } s_t;
endpackage
"""


def sel(probes: dict, name: str, expr: str, width: int) -> None:
    probes[name] = (
        PK
        + f"module top(input pk::s_t s, output logic [{width - 1}:0] y);\n"
        + f"  assign y = {expr};\nendmodule\n"
    )


def build() -> dict:
    p: dict = {}
    # packed-member part-selects on a port-typed struct
    for n, e, w in [
        ("a01_f0_3_0", "s.f0[3:0]", 4),
        ("a02_f0_11_8", "s.f0[11:8]", 4),
        ("a03_f1_3_0", "s.f1[3:0]", 4),
        ("a04_f1_15_12", "s.f1[15:12]", 4),
        ("a05_f1_7_4", "s.f1[7:4]", 4),
        ("a06_f2_3_0", "s.f2[3:0]", 4),
        ("a07_f3_7_4", "s.f3[7:4]", 4),
        ("a08_f3_3_0", "s.f3[3:0]", 4),
        ("a09_f3_1_0", "s.f3[1:0]", 2),
        ("a10_f1_1_0", "s.f1[1:0]", 2),
        ("a11_f0_1_0", "s.f0[1:0]", 2),
        ("a12_f2_1_0", "s.f2[1:0]", 2),
        ("a13_f1_15_8", "s.f1[15:8]", 8),
        ("a14_f1_7_0", "s.f1[7:0]", 8),
        ("a15_f1_full", "s.f1", 16),
        ("a16_f3_7_0", "s.f3[7:0]", 8),
        ("a17_f3_6_2", "s.f3[6:2]", 5),
        ("a18_f0_11_0", "s.f0[11:0]", 12),
        # bit selects
        ("b01_f1_5", "s.f1[5]", 1),
        ("b02_f0_0", "s.f0[0]", 1),
        ("b03_f3_7", "s.f3[7]", 1),
        ("b04_f1_0", "s.f1[0]", 1),
        ("b05_f1_15", "s.f1[15]", 1),
        ("b06_f3_0", "s.f3[0]", 1),
        ("b07_f2_3", "s.f2[3]", 1),
        # indexed part-selects
        ("c01_f1_plus", "s.f1[4 +: 4]", 4),
        ("c02_f1_minus", "s.f1[11 -: 4]", 4),
    ]:
        sel(p, n, e, w)
    p["d01_ctl_wire"] = (
        PK
        + "module top(input pk::s_t s, output logic [3:0] y);\n"
        + "  logic [15:0] w; assign w = s.f1;\n  assign y = w[7:4];\nendmodule\n"
    )
    case = (
        "module top(input pk::s_t s, input logic [3:0] a,b,c,d, output logic [3:0] y);\n"
        "  always_comb case (%s) 2'd0: y=a; 2'd1: y=b; 2'd2: y=c; default: y=d; endcase\n"
        "endmodule\n"
    )
    p["e01_case_sel"] = PK + case % "s.f1[3:2]"
    p["e02_case_sel_hi"] = PK + case % "s.f1[15:14]"
    p["e03_case_sel_f3"] = PK + case % "s.f3[1:0]"
    p["f01_concat"] = (
        PK
        + "module top(input pk::s_t s, output logic [7:0] y);\n"
        + "  assign y = {s.f1[7:4], s.f0[3:0]};\nendmodule\n"
    )
    loc = "module top(input logic [39:0] d0, d1, output logic [3:0] y);\n  pk::s_t %s;\n%s\nendmodule\n"
    p["g01_local"] = PK + loc % ("r", "  assign r = d0; assign y = r.f1[7:4];")
    p["g02_local_alw"] = PK + loc % ("r", "  always_comb begin r = d0; y = r.f1[7:4]; end")
    p["g03_array_elem1"] = PK + loc % (
        "a [0:1]",
        "  assign a[0] = d0; assign a[1] = d1; assign y = a[1].f1[7:4];",
    )
    p["g04_array_elem0"] = PK + loc % (
        "a [0:1]",
        "  assign a[0] = d0; assign a[1] = d1; assign y = a[0].f1[7:4];",
    )
    p["g05_reg"] = (
        PK
        + "module top(input logic clk, input logic [39:0] d0, output logic [3:0] y);\n"
        + "  pk::s_t r; always_ff @(posedge clk) r <= d0;\n  assign y = r.f1[7:4];\nendmodule\n"
    )
    p["h01_portconn"] = (
        PK
        + "module sub(input logic [3:0] x, output logic [3:0] o); assign o = x ^ 4'h5; endmodule\n"
        + "module top(input pk::s_t s, output logic [3:0] y);\n"
        + "  sub u(.x(s.f1[7:4]), .o(y));\nendmodule\n"
    )
    for n, e, w in [
        ("i01_nested_f1", "n.in.f1[7:4]", 4),
        ("i02_nested_f3", "n.in.f3[7:4]", 4),
        ("i03_nested_tail", "n.tail[3:2]", 2),
        ("i04_nested_pad", "n.pad[7:4]", 4),
        ("i05_nested_f0", "n.in.f0[3:0]", 4),
    ]:
        p[n] = (
            PK
            + f"module top(input pk::n_t n, output logic [{w - 1}:0] y);\n"
            + f"  assign y = {e};\nendmodule\n"
        )
    p["j01_lhs_alw"] = (
        PK
        + "module top(input logic [3:0] a, input pk::s_t s, output pk::s_t y);\n"
        + "  always_comb begin y = s; y.f1[7:4] = a; end\nendmodule\n"
    )
    p["j02_lhs_assign"] = (
        PK
        + "module top(input logic [7:0] a, input pk::s_t s, output pk::s_t y);\n"
        + "  assign y.f0 = s.f0; assign y.f1[15:8] = s.f1[15:8]; assign y.f1[7:0] = a;\n"
        + "  assign y.f2 = s.f2; assign y.f3 = s.f3;\nendmodule\n"
    )
    p["k01_runtime_bit"] = (
        PK
        + "module top(input pk::s_t s, input logic [3:0] i, output logic y);\n"
        + "  assign y = s.f1[i];\nendmodule\n"
    )
    p["l01_unpacked"] = (
        "package pu; typedef struct { logic [7:0] a; logic [15:0] b; } u_t; endpackage\n"
        "module top(input logic [7:0] da, input logic [15:0] db, output logic [3:0] y);\n"
        "  pu::u_t r; assign r.a = da; assign r.b = db;\n  assign y = r.b[7:4];\nendmodule\n"
    )
    p["m01_p10_b"] = (
        PK2
        + "module top(input pk2::s_t s, output logic [3:0] y);\n"
        + "  assign y = s.b[3:0];\nendmodule\n"
    )
    p["m02_p10_a"] = (
        PK2
        + "module top(input pk2::s_t s, output logic [3:0] y);\n"
        + "  assign y = s.a[3:0];\nendmodule\n"
    )
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
