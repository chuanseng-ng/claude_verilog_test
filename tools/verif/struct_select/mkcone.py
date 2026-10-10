"""Cut the combinational cones around the GPU struct-member selects out of the real sources (bead ainf).

usage: mkcone.py <repo-root> <outdir>
Writes <outdir>/gpu_cu_cone.sv (module gpu_cu_cone: id_ex_t -> mem/shmem address+data, text extracted verbatim from
rtl/gpu/gpu_compute_unit.sv) and <outdir>/gpu_top_cone.sv (module gpu_top_cone: n_warps_raw from kernel_desc_t,
extracted verbatim from rtl/gpu/gpu_top.sv).  Needed because the flop names of the full module differ between the
two frontends (aliasing), which defeats the name-based flop exposure used by modeq.sh.
"""

import os
import re
import sys


def main() -> int:
    root, out = sys.argv[1], sys.argv[2]
    os.makedirs(out, exist_ok=True)
    cu = open(os.path.join(root, "rtl/gpu/gpu_compute_unit.sv"), encoding="utf-8").read()
    td = re.search(r"typedef struct packed \{[^}]*?id_ex_t;", cu, re.S) or re.search(
        r"(typedef struct packed \{(?:(?!\}).)*\} id_ex_t;)", cu, re.S
    )
    typedef = re.search(r"typedef struct packed \{[^{}]*\} id_ex_t;", cu).group(0)
    # nothing in id_ex_t's body contains braces except none; assert
    always = re.search(r"always_comb begin\n\s*logic \[31:0\] shmem_byte_addr;.*?\n    end\n", cu, re.S).group(0)
    assert "id_ex_q.rs1_data[l]" in always and td is not None
    body = (
        "module gpu_cu_cone\n    import gpu_pkg::*;\n(\n"
        "    input  id_ex_t                           id_ex_q,\n"
        "    input  logic                             mem_busy,\n"
        "    input  logic                             shmem_stall_i,\n"
        "    input  logic                             is_mem_op,\n"
        "    input  logic                             is_shmem_op,\n"
        "    output logic                             mem_req_o,\n"
        "    output logic                             mem_we_o,\n"
        "    output logic [N_LANES-1:0]               mem_lane_mask_o,\n"
        "    output logic [N_LANES-1:0][31:0]         mem_addr_o,\n"
        "    output logic [N_LANES-1:0][31:0]         mem_wdata_o,\n"
        "    output logic                             shmem_req_o,\n"
        "    output logic                             shmem_we_o,\n"
        "    output logic [N_LANES-1:0]               shmem_lane_mask_o,\n"
        "    output logic [N_LANES-1:0][SHMEM_W-1:0]  shmem_addr_o,\n"
        "    output logic [N_LANES-1:0][31:0]         shmem_wdata_o\n);\n"
        "    localparam int WARP_W = $clog2(N_WARPS);\n"
        f"    {typedef}\n{always}endmodule\n"
    )
    # id_ex_t lives in the module in the source; hoist it into the cone module is not legal for a port type,
    # so declare it in a package instead.
    pkg = "package cu_cone_pkg;\n    import gpu_pkg::*;\n    " + typedef + "\nendpackage\n"
    body = body.replace(f"    {typedef}\n", "").replace("    localparam int WARP_W = $clog2(N_WARPS);\n", "")
    body = body.replace("    import gpu_pkg::*;\n(", "    import gpu_pkg::*;\n    import cu_cone_pkg::*;\n(")
    with open(os.path.join(out, "gpu_cu_cone.sv"), "w", encoding="utf-8") as f:
        f.write(pkg + body)
    top = (
        "module gpu_top_cone\n    import gpu_pkg::*;\n(\n    input  kernel_desc_t cq_desc,\n"
        "    output logic [9:0] n_warps_raw\n);\n"
        "    assign n_warps_raw = {3'b0, cq_desc.block_x[9:3]} + {9'b0, |cq_desc.block_x[2:0]};\nendmodule\n"
    )
    with open(os.path.join(out, "gpu_top_cone.sv"), "w", encoding="utf-8") as f:
        f.write(top)
    print("ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
