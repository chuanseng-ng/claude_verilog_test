"""Structural guards for the cache-FSM timing properties added by bead r51p.

The Sky130 CPU macro's ss setup failure runs through the dcache stall decode
(docs/SKY130_CPU_SS_SETUP_R51P.md).  Two RTL properties keep that decode shallow and
must not regress silently:

1. Every *unconditionally* stalling cache state has bit 3 of the state encoding set, and
   no other state does, so ``dc_stall_o`` / ``ic_stall_o`` need ``state_q[3]`` rather than
   a 4-bit decode.
2. The I-cache SRAM read enables (tag and data ``csb0``) in ``CS_IDLE`` do not depend on
   ``ic_valid_i``: they would otherwise pull the whole redirect / halt / stall network
   into the SRAM enable pin.

These are text-level checks on purpose (no simulator needed); behaviour is covered by the
cocotb cache suites and by the RTL-arm differential in tools/verif/gls/sky130.
"""

import re
from pathlib import Path

RTL = Path(__file__).resolve().parents[2] / "rtl" / "mem"

# States that stall the pipeline in every cycle they are occupied.
UNCONDITIONAL_STALL = (
    "CS_SRAM_LATCH",
    "CS_HIT_PENDING",
    "CS_REFILL",
    "CS_WRITEBACK",
    "CS_UNCACHED_RD",
    "CS_UNCACHED_WR",
    "CS_FLUSH_SCAN",
    "CS_INVAL_SCAN",
)
# States that stall only under a condition (IDLE && valid, TAG_CHECK && !hit) or never (DONE).
OTHER = ("CS_IDLE", "CS_TAG_CHECK", "CS_DONE")


def _encoding() -> dict[str, int]:
    text = (RTL / "rv32i_cache_pkg.sv").read_text()
    enc = {}
    for name, val in re.findall(r"(CS_[A-Z_]+)\s*=\s*4'b([01]{4})", text):
        enc[name] = int(val, 2)
    return enc


def test_all_states_encoded_uniquely():
    enc = _encoding()
    assert set(enc) == set(UNCONDITIONAL_STALL) | set(OTHER)
    assert len(set(enc.values())) == len(enc)


def test_idle_is_reset_state_zero():
    assert _encoding()["CS_IDLE"] == 0


def test_bit3_marks_exactly_the_unconditional_stall_states():
    enc = _encoding()
    for name in UNCONDITIONAL_STALL:
        assert enc[name] & 0b1000, f"{name} must have state_q[3] set"
    for name in OTHER:
        assert not enc[name] & 0b1000, f"{name} must have state_q[3] clear"


def test_stall_outputs_use_state_bit3():
    dc = (RTL / "rv32i_dcache.sv").read_text()
    ic = (RTL / "rv32i_icache.sv").read_text()
    dc_stall = re.search(r"assign dc_stall_o =(.*?);", dc, re.S).group(1)
    ic_stall = re.search(r"assign ic_stall_o =(.*?);", ic, re.S).group(1)
    for text in (dc_stall, ic_stall):
        assert "state_q[3]" in text
        # the 4-bit decodes of the unconditional states must be gone
        for name in UNCONDITIONAL_STALL:
            assert name not in text, f"{name} decode still in stall output"


def test_icache_sram_read_enable_independent_of_ic_valid():
    ic = (RTL / "rv32i_icache.sv").read_text()
    for block in ("SRAM combinational control — Tag SRAM", "SRAM combinational control — Data SRAMs"):
        body = ic.split(block, 1)[1].split("endcase", 1)[0]
        idle = body.split("CS_IDLE:", 1)[1]
        assert "ic_valid_i" not in idle, f"{block}: CS_IDLE read enable still gated by ic_valid_i"
