"""Round-7: usage forms x ranged-member count (R=2 / R=3), incl. LHS selects and unpacked structs.

usage: mkprobes7.py <outdir>
X2 = {a[15:0], b[31:0]}              (R=2)    X3 = {a[15:0], b[31:0], c[7:0]}   (R=3)
X2S = {a[15:0], b[31:0], v}  scalar v (R=2)   X4 = {z[3:0], a, b, c}            (R=4)
"""

import os
import sys

DEFS = {
    "X2": "logic [15:0] a; logic [31:0] b;",
    "X3": "logic [15:0] a; logic [31:0] b; logic [7:0] c;",
    "X2S": "logic [15:0] a; logic [31:0] b; logic v;",
    "X4": "logic [3:0] z; logic [15:0] a; logic [31:0] b; logic [7:0] c;",
}
WIDTH = {"X2": 48, "X3": 56, "X2S": 49, "X4": 60}


def pkg(t: str, packed: bool = True) -> str:
    kw = "struct packed" if packed else "struct"
    return f"package pk; typedef {kw} {{ {DEFS[t]} }} s_t; endpackage\n"


def build() -> dict:
    p: dict = {}
    for t in DEFS:
        w = WIDTH[t]
        hdr = pkg(t)
        # RHS forms, member b ([31:0], not at the struct MSB end except X2S/X2: b is LSB in X2)
        p[f"{t}_rhs_port"] = hdr + "module top(input pk::s_t s, output logic [3:0] y);\n  assign y = s.b[7:4];\nendmodule\n"
        p[f"{t}_rhs_hi1"] = hdr + "module top(input pk::s_t s, output logic [1:0] y);\n  assign y = s.b[1:0];\nendmodule\n"
        p[f"{t}_rhs_a_hi1"] = hdr + "module top(input pk::s_t s, output logic [1:0] y);\n  assign y = s.a[1:0];\nendmodule\n"
        p[f"{t}_rhs_bit"] = hdr + "module top(input pk::s_t s, output logic y);\n  assign y = s.b[1];\nendmodule\n"
        p[f"{t}_rhs_bit0"] = hdr + "module top(input pk::s_t s, output logic y);\n  assign y = s.b[0];\nendmodule\n"
        p[f"{t}_rhs_local"] = hdr + (
            f"module top(input logic [{w - 1}:0] d, output logic [1:0] y);\n"
            "  pk::s_t r; assign r = d; assign y = r.b[1:0];\nendmodule\n"
        )
        p[f"{t}_rhs_reg"] = hdr + (
            f"module top(input logic clk, input logic [{w - 1}:0] d, output logic [1:0] y);\n"
            "  pk::s_t r; always_ff @(posedge clk) r <= d; assign y = r.b[1:0];\nendmodule\n"
        )
        p[f"{t}_rhs_arr"] = hdr + (
            f"module top(input logic [{w - 1}:0] d0, d1, output logic [1:0] y);\n"
            "  pk::s_t r [0:1]; assign r[0] = d0; assign r[1] = d1; assign y = r[1].b[1:0];\nendmodule\n"
        )
        p[f"{t}_rhs_case"] = hdr + (
            "module top(input pk::s_t s, input logic [3:0] u,v,x,z, output logic [3:0] y);\n"
            "  always_comb case (s.b[1:0]) 2'd0: y=u; 2'd1: y=v; 2'd2: y=x; default: y=z; endcase\n"
            "endmodule\n"
        )
        p[f"{t}_rhs_concat"] = hdr + (
            "module top(input pk::s_t s, output logic [3:0] y);\n  assign y = {s.b[1:0], s.a[1:0]};\nendmodule\n"
        )
        p[f"{t}_rhs_rtidx"] = hdr + (
            "module top(input pk::s_t s, input logic [4:0] i, output logic y);\n  assign y = s.b[i];\nendmodule\n"
        )
        p[f"{t}_rhs_plus"] = hdr + (
            "module top(input pk::s_t s, output logic [3:0] y);\n  assign y = s.b[4 +: 4];\nendmodule\n"
        )
        p[f"{t}_rhs_wirefirst"] = hdr + (
            "module top(input pk::s_t s, output logic [3:0] y);\n"
            "  logic [31:0] w; assign w = s.b; assign y = w[7:4];\nendmodule\n"
        )
        p[f"{t}_rhs_portconn"] = hdr + (
            "module sub(input logic [3:0] x, output logic [3:0] o); assign o = x ^ 4'h5; endmodule\n"
            "module top(input pk::s_t s, output logic [3:0] y);\n  sub u(.x(s.b[7:4]), .o(y));\nendmodule\n"
        )
        # LHS forms
        p[f"{t}_lhs_copy"] = hdr + (
            "module top(input logic [3:0] n, input pk::s_t s, output pk::s_t y);\n"
            "  always_comb begin y = s; y.b[7:4] = n; end\nendmodule\n"
        )
        p[f"{t}_lhs_zero"] = hdr + (
            "module top(input logic [3:0] n, output pk::s_t y);\n"
            "  always_comb begin y = '0; y.b[7:4] = n; end\nendmodule\n"
        )
        p[f"{t}_lhs_bit"] = hdr + (
            "module top(input logic n, input pk::s_t s, output pk::s_t y);\n"
            "  always_comb begin y = s; y.b[3] = n; end\nendmodule\n"
        )
        p[f"{t}_lhs_ff"] = hdr + (
            "module top(input logic clk, input logic [3:0] n, input pk::s_t s, output pk::s_t y);\n"
            "  always_ff @(posedge clk) begin y <= s; y.b[7:4] <= n; end\nendmodule\n"
        )
        p[f"{t}_lhs_ff_only"] = hdr + (
            "module top(input logic clk, input logic [3:0] n, input pk::s_t s, output pk::s_t y);\n"
            "  always_ff @(posedge clk) y.b[7:4] <= n;\nendmodule\n"
        )
        p[f"{t}_lhs_assign"] = hdr + (
            "module top(input logic [7:0] n, input pk::s_t s, output pk::s_t y);\n"
            + "".join(f"  assign y.{m} = s.{m};\n" for m in ("a", "c", "z", "v") if f"logic [" in DEFS[t] and (f" {m};" in DEFS[t]))
            + "  assign y.b[31:8] = s.b[31:8]; assign y.b[7:0] = n;\nendmodule\n"
        )
    # unpacked structs
    for t, defs in (("U2", "logic [15:0] a; logic [31:0] b;"), ("U3", "logic [15:0] a; logic [31:0] b; logic [7:0] c;")):
        p[f"{t}_unp_rhs"] = (
            f"package pk; typedef struct {{ {defs} }} s_t; endpackage\n"
            "module top(input logic [31:0] db, output logic [3:0] y);\n"
            "  pk::s_t r; assign r.a = 16'h0; assign r.b = db;\n"
            + ("  assign r.c = 8'h0;\n" if t == "U3" else "")
            + "  assign y = r.b[7:4];\nendmodule\n"
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
