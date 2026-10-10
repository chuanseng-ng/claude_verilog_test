# ruff: noqa: E501
"""Round-8 (D3): element select of a struct member that is itself a multi-dimensional packed array.

usage: mkprobes8.py <outdir>
gpu_compute_unit does `id_ex_q.rs1_data[l]` on `logic [N_LANES-1:0][31:0] rs1_data`; the module-level miter
showed Synlig reading ONE bit instead of the 32-bit element.
"""

import os
import sys

P = {}
T = "package pk; typedef struct packed { logic [3:0] a; logic [3:0][7:0] r; logic [2:0] b; logic [4:0] c; } s_t; endpackage\n"
P["d3_const_idx"] = (
    T + "module top(input pk::s_t s, output logic [7:0] y);\n  assign y = s.r[2];\nendmodule\n"
)
P["d3_const_idx0"] = (
    T + "module top(input pk::s_t s, output logic [7:0] y);\n  assign y = s.r[0];\nendmodule\n"
)
P["d3_rt_idx"] = (
    T
    + "module top(input pk::s_t s, input logic [1:0] i, output logic [7:0] y);\n  assign y = s.r[i];\nendmodule\n"
)
P["d3_loop_idx"] = T + (
    "module top(input pk::s_t s, output logic [3:0][7:0] y);\n"
    "  always_comb for (int l = 0; l < 4; l++) y[l] = s.r[l];\nendmodule\n"
)
P["d3_loop_plus_const"] = T + (
    "module top(input pk::s_t s, output logic [3:0][7:0] y);\n"
    "  always_comb for (int l = 0; l < 4; l++) y[l] = s.r[l] + 8'd1;\nendmodule\n"
)
P["d3_plain_vec"] = (
    "module top(input logic [3:0][7:0] r, output logic [3:0][7:0] y);\n"
    "  always_comb for (int l = 0; l < 4; l++) y[l] = r[l];\nendmodule\n"
)
P["d3_wire_first"] = T + (
    "module top(input pk::s_t s, output logic [3:0][7:0] y);\n"
    "  logic [3:0][7:0] w; assign w = s.r;\n  always_comb for (int l = 0; l < 4; l++) y[l] = w[l];\nendmodule\n"
)
P["d3_part_of_elem"] = (
    T + "module top(input pk::s_t s, output logic [3:0] y);\n  assign y = s.r[2][5:2];\nendmodule\n"
)
P["d3_X2"] = (
    "package pk; typedef struct packed { logic [3:0][7:0] r; logic [7:0] b; } s_t; endpackage\n"
    "module top(input pk::s_t s, output logic [7:0] y);\n  assign y = s.r[2];\nendmodule\n"
)
P["d3_local"] = T + (
    "module top(input logic [47:0] d, output logic [7:0] y);\n"
    "  pk::s_t r; assign r = d; assign y = r.r[1];\nendmodule\n"
)
P["d3_unpacked_arr"] = (
    "package pk; typedef struct packed { logic [3:0] a; logic [7:0] r [0:3]; logic [2:0] b; logic [4:0] c; } s_t; endpackage\n"
    "module top(input logic [7:0] x, output logic [7:0] y);\n  pk::s_t s; assign s.a = 0; assign s.b = 0; assign s.c = 0;\n"
    "  assign s.r[0] = x; assign s.r[1] = x; assign s.r[2] = x; assign s.r[3] = x; assign y = s.r[2];\nendmodule\n"
)


def main() -> int:
    out = sys.argv[1]
    os.makedirs(out, exist_ok=True)
    for k, v in P.items():
        with open(os.path.join(out, k + ".sv"), "w", encoding="utf-8") as f:
            f.write(v)
    print(len(P), "probes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
