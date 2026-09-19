#!/usr/bin/env python3
"""Verify the bead ma7 branch-dependent regfile-read-port program (see
gen_cpu_check_rom_branch.py) against the project's golden Python reference
model (tb/models/rv32i_model.py) before it is trusted as a GLS-vs-RTL
discriminator.

Run from anywhere; it locates the repo root relative to this file.
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.abspath(os.path.join(_HERE, "..", "..", ".."))
sys.path.insert(0, _REPO_ROOT)

from tb.models.rv32i_model import RV32IModel  # noqa: E402

sys.path.insert(0, _HERE)
from gen_cpu_check_rom_branch import PROGRAM, EXPECTED_PC_SEQUENCE, jal  # noqa: E402


def run_reference():
    model = RV32IModel()
    trace = []
    for _ in range(40):
        insn = PROGRAM.get(model.pc, jal(0, 0))
        r = model.step(insn)
        trace.append((r["pc"], insn, r["rd"], r["rd_value"]))
        if r["pc"] == 0x28:
            break
    return trace


def main():
    trace = run_reference()
    print("Reference-model retire trace (pc, insn, rd, rd_value):")
    for pc, insn, rd, rd_value in trace:
        print(f"  pc={pc:#06x} insn={insn:#010x} rd={rd} rd_value={rd_value!r}")

    pcs = [t[0] for t in trace]
    assert pcs == EXPECTED_PC_SEQUENCE, (
        f"reference model PC trace {[hex(p) for p in pcs]} != "
        f"expected {[hex(p) for p in EXPECTED_PC_SEQUENCE]}"
    )
    assert 0x14 not in pcs and 0x18 not in pcs, "reference model took the WRONG branch path -- program design bug"
    print(
        "\nPASS: reference model confirms BEQ x2,x3 (9==9) TAKEN, "
        "parks at PASS (0x28)."
    )
    print(
        "A corrupted rs1/rs2 regfile read for these indices would flip the "
        "compare and divert the retire trace to 0x14/0x18."
    )


if __name__ == "__main__":
    main()
