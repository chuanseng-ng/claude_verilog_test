"""Cut the GPU memory-address cone out of gpu_compute_unit.sv, old and new alike (bead ainf).

usage: mkcone_oldnew.py <repo-root-with-rtl> <out-root>

Writes <out-root>/rtl/gpu/gpu_pkg.sv (copy) and <out-root>/cone/gpu_cu_cone.sv: a module whose
input is the id_ex_t register OUTPUT and whose outputs are the VLD/VST/VLDS/VSTS address/data/mask
nets.  The body is the verbatim source text of (a) the wire-first helper declarations/assigns, if the
tree has them, and (b) the always_comb that computes the outputs.  The wire-first rewrite changes
nothing else, so the cone covers every changed line.

Why a cone and not the whole module: the whole-module miter has to carry vector_register_file (8192
flops) and vector_alu through SAT, which does not finish in 900 s at a 4G cap, and a blackbox cell
cannot be imported by `sat`.  The cone is the same logic with the state cut at the id_ex_q flop
outputs, which the rewrite does not touch.  The script asserts that every use of an id_ex_*_w helper
in the file lies inside the extracted text, so nothing the cone omits can depend on a helper.
"""

import os
import re
import shutil
import sys

PORTS = (
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
    "    output logic [N_LANES-1:0][31:0]         shmem_wdata_o\n"
)


def main() -> int:
    """Extract the cone from <root>/rtl/gpu/gpu_compute_unit.sv into <out>."""
    root, out = sys.argv[1], sys.argv[2]
    src = os.path.join(root, "rtl/gpu/gpu_compute_unit.sv")
    cu = open(src, encoding="utf-8").read()
    typedef = re.search(r"typedef struct packed \{[^{}]*\} id_ex_t;", cu).group(0)
    always = re.search(
        r"always_comb begin\n\s*logic \[31:0\] shmem_byte_addr;.*?\n    end\n", cu, re.S
    ).group(0)
    # wire-first helpers (absent in the pre-rewrite tree)
    helpers = [
        ln
        for ln in cu.splitlines()
        if re.match(r"\s*(logic .*\bid_ex_\w+_w\b.*;|assign\s+id_ex_\w+_w\s*=.*;)", ln)
    ]
    extracted = "\n".join(helpers) + "\n" + always
    total = len(re.findall(r"\bid_ex_(?:rs1_data|rs2_data|imm)_w\b", cu))
    inside = len(re.findall(r"\bid_ex_(?:rs1_data|rs2_data|imm)_w\b", extracted))
    assert total == inside, f"helper used outside the extracted cone ({total} vs {inside})"
    pkg = "package cu_cone_pkg;\n    import gpu_pkg::*;\n    " + typedef + "\nendpackage\n"
    body = (
        "module gpu_cu_cone\n    import gpu_pkg::*;\n    import cu_cone_pkg::*;\n(\n"
        + PORTS
        + ");\n"
        + "\n".join(helpers)
        + "\n"
        + always
        + "endmodule\n"
    )
    os.makedirs(os.path.join(out, "rtl/gpu"), exist_ok=True)
    os.makedirs(os.path.join(out, "cone"), exist_ok=True)
    shutil.copy(os.path.join(root, "rtl/gpu/gpu_pkg.sv"), os.path.join(out, "rtl/gpu/gpu_pkg.sv"))
    with open(os.path.join(out, "cone/gpu_cu_cone.sv"), "w", encoding="utf-8") as f:
        f.write(pkg + body)
    print(f"cone from {src}: {len(helpers)} helper line(s), {total} helper use(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
