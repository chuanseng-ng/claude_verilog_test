# ruff: noqa: E501
"""Round-4: 3-member struct (real if_id_reg_t layout) in several usage forms.

usage: mkprobes4.py <outdir>
"""

import os
import sys

# real layout of rv32i_pipeline_pkg::if_id_reg_t: pc@33 w32, instruction@1 w32, valid@0
T = (
    "package pk; typedef struct packed { logic [31:0] pc; logic [31:0] instruction; "
    "logic valid; } t_t; endpackage\n"
)
SUB = "module sub(input logic [4:0] x, output logic [4:0] o); assign o = x ^ 5'h15; endmodule\n"


def build() -> dict:
    p = {}
    p["n01_assign_port"] = (
        T
        + "module top(input pk::t_t s, output logic [4:0] y);\n  assign y = s.instruction[19:15];\nendmodule\n"
    )
    p["n02_assign_local_reg"] = (
        T
        + "module top(input logic clk, input logic [64:0] d, output logic [4:0] y);\n"
        + "  pk::t_t r; always_ff @(posedge clk) r <= d;\n  assign y = r.instruction[19:15];\nendmodule\n"
    )
    p["n03_portconn_port"] = (
        T + SUB + "module top(input pk::t_t s, output logic [4:0] y);\n"
        "  sub u(.x(s.instruction[19:15]), .o(y));\nendmodule\n"
    )
    p["n04_portconn_local"] = (
        T + SUB + "module top(input logic [64:0] d, output logic [4:0] y);\n"
        "  pk::t_t r; assign r = d;\n  sub u(.x(r.instruction[19:15]), .o(y));\nendmodule\n"
    )
    p["n05_assign_local_wire"] = (
        T + "module top(input logic [64:0] d, output logic [4:0] y);\n"
        "  pk::t_t r; assign r = d;\n  assign y = r.instruction[19:15];\nendmodule\n"
    )
    # same, member order permuted: instruction MSB (gc0y p01 layout)
    p["o01_instr_msb_assign"] = (
        "package pk; typedef struct packed { logic [31:0] instruction; logic [31:0] pc; logic valid; } t_t; endpackage\n"
        "module top(input pk::t_t s, output logic [4:0] y);\n  assign y = s.instruction[19:15];\nendmodule\n"
    )
    p["o02_instr_lsb_assign"] = (
        "package pk; typedef struct packed { logic valid; logic [31:0] pc; logic [31:0] instruction; } t_t; endpackage\n"
        "module top(input pk::t_t s, output logic [4:0] y);\n  assign y = s.instruction[19:15];\nendmodule\n"
    )
    p["o03_instr_mid_pcmsb"] = (
        "package pk; typedef struct packed { logic [31:0] pc; logic valid; logic [31:0] instruction; } t_t; endpackage\n"
        "module top(input pk::t_t s, output logic [4:0] y);\n  assign y = s.instruction[19:15];\nendmodule\n"
    )
    # the real package, port select
    p["q01_real_ifid_port"] = (
        '`include "RTLPKG"\n'
        "module top(input rv32i_pipeline_pkg::if_id_reg_t s, output logic [4:0] y);\n"
        "  assign y = s.instruction[19:15];\nendmodule\n"
    )
    return p


def main() -> int:
    out = sys.argv[1]
    os.makedirs(out, exist_ok=True)
    for k, v in build().items():
        with open(os.path.join(out, k + ".sv"), "w", encoding="utf-8") as f:
            f.write(v)
    print(len(build()), "probes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
