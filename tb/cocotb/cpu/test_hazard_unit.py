"""
Standalone unit tests for rv32i_hazard_unit — GH #119 bead `gvr`.

The DUT (rtl/cpu/core/rv32i_hazard_unit.sv) is purely combinational: no clock,
no reset, no always_ff. Nothing in the repo drove it standalone before this
file (tb/cocotb/cpu/test_pipeline_hazards.py is full-core level).

Two layers, run as one cocotb test module:

  (a) Directed tests — oracle is the DUT's header comment (lines 1-26 of the
      RTL), NOT the implementation body. Expected stall/flush/forward values
      below are derived by hand from that documented 9-item priority list and
      the forwarding encoding. Where the header does not fully determine an
      answer (see "SPEC AMBIGUITY" comments), the test asserts only the part
      that IS determined, or is skipped.

  (b) Randomised cross-arm differential (test_random_cross_arm) — dumps
      (inputs, outputs) for N biased-random vectors to a JSON trace file
      named after TOPLEVEL. tools/verif/compare_hazard_traces.py diffs two
      such trace files (hand-RTL vs HLS arm) to provide the actual
      cross-arm equivalence evidence; the directed tests above only check
      one arm against the spec.

GH #119 decision: the two arms have genuinely different protocols (hand-RTL
is pure combinational; the Bambu HLS arm is wrapped in a clock/reset/
start_port/done_port handshake by construction). This file branches on that
difference in exactly one place -- HazardUnitDriver.__init__ / .apply() --
detected at runtime via hasattr(dut, "clk"). Every vector, every expected
value, and every assertion after that point is identical for both arms.
"""

from __future__ import annotations

import json
import os
import random
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ReadOnly, RisingEdge, Timer

# ---------------------------------------------------------------------------
# Port name tables
# ---------------------------------------------------------------------------

# All hand-RTL / HLS-shim input port names (identical on both arms per the
# GH #119 shim contract -- the shim re-exposes the repo's port names verbatim
# plus the HLS handshake).
INPUT_FIELDS = [
    "id_ex_rs1_addr",
    "id_ex_rs2_addr",
    "id_ex_rd_addr",
    "id_ex_mem_rd",
    "id_ex_reg_wr_en",
    "ex1b_rd_addr",
    "ex1b_reg_wr_en",
    "ex1b_mem_rd",
    "ex1c_rd_addr",
    "ex1c_reg_wr_en",
    "ex1c_mem_rd",
    "ex1b2_rd_addr",
    "ex1b2_reg_wr_en",
    "ex1b2_mem_rd",
    "ex_mem_rd_addr",
    "ex_mem_reg_wr_en",
    "ex_mem_mem_rd",
    "mem_wb_rd_addr",
    "mem_wb_reg_wr_en",
    "if_id_rs1_addr",
    "if_id_rs2_addr",
    "if_cache_stall",
    "mem_cache_stall",
    "ex_pc_redirect",
    "mem_trap_redirect",
    "id_jal_taken",
]

OUTPUT_FIELDS = [
    "stall_pc",
    "stall_if_id",
    "stall_id_ex",
    "stall_ex_mem",
    "stall_ex1_ex2_o",
    "stall_ex1a_ex1b_o",
    "stall_ex1c_ex1b_o",
    "flush_if_id",
    "flush_id_ex",
    "flush_ex_mem",
    "flush_ex1_ex2_o",
    "flush_ex1a_ex1b_o",
    "flush_ex1c_ex1b_o",
    "fwd_a_sel",
    "fwd_b_sel",
    "fwd_store_sel",
    "fwd_a_ex1c",
    "fwd_b_ex1c",
    "fwd_store_ex1c",
    "fwd_a_ex1b2",
    "fwd_b_ex1b2",
    "fwd_store_ex1b2",
    "fwd_a_sel_pre",
    "fwd_a_ex1c_pre",
    "fwd_a_ex1b2_pre",
    "fwd_b_sel_pre",
    "fwd_b_ex1c_pre",
    "fwd_b_ex1b2_pre",
]


def default_inputs() -> dict:
    """All-zero / all-idle input vector (no hazard, no forwarding, no redirect)."""
    return dict.fromkeys(INPUT_FIELDS, 0)


# ---------------------------------------------------------------------------
# The one protocol branch (GH #119 decision: do not wrap the hand-RTL arm)
# ---------------------------------------------------------------------------


class HazardUnitDriver:
    """Applies an input vector and reads back outputs, for either arm.

    Hand-RTL arm: purely combinational -- drive inputs, let them settle
    (Timer + ReadOnly so Verilator's comb solver has converged), then sample.

    HLS arm: Bambu wraps the block in a clock/reset/start_port/done_port
    handshake (module rv32i_hazard_unit_hls, per the shim being written in
    parallel for this bead). Detected via hasattr(dut, "clk"); the shim is
    assumed to expose start_i / done_o alongside clk / rst_n, matching the
    convention already established by hls/gpu/memory_coalescer/shim/
    memory_coalescer_hls.sv's sibling (repo's `start_i`/`done_o` naming).
    """

    def __init__(self, dut):
        self.dut = dut
        self.is_hls = hasattr(dut, "clk")
        self._clock_started = False

    async def setup(self):
        if not self.is_hls:
            return
        if not self._clock_started:
            cocotb.start_soon(Clock(self.dut.clk, 10, units="ns").start())
            self._clock_started = True
        # Async active-low reset, matching the repo's HLS-shim convention.
        self.dut.rst_n.value = 0
        for name in INPUT_FIELDS:
            getattr(self.dut, name).value = 0
        self.dut.start_i.value = 0
        await RisingEdge(self.dut.clk)
        await RisingEdge(self.dut.clk)
        self.dut.rst_n.value = 1
        await RisingEdge(self.dut.clk)

    async def apply(self, vec: dict) -> dict:
        """Drive one input vector; return a dict of sampled output values."""
        dut = self.dut
        for name in INPUT_FIELDS:
            getattr(dut, name).value = vec.get(name, 0)

        if not self.is_hls:
            # Purely combinational: let the netlist settle, then sample.
            await Timer(1, units="ns")
            return {name: int(getattr(dut, name).value) for name in OUTPUT_FIELDS}

        dut.start_i.value = 1
        await RisingEdge(dut.clk)
        dut.start_i.value = 0
        # Wait for the Bambu handshake to complete (bounded so a stuck
        # done_port fails the test instead of hanging the regression).
        for _ in range(50):
            await RisingEdge(dut.clk)
            if int(dut.done_o.value):
                break
        else:
            raise TimeoutError("HLS arm: done_o never asserted within 50 cycles")
        await ReadOnly()
        outputs = {name: int(getattr(dut, name).value) for name in OUTPUT_FIELDS}
        # Step past the read-only sync phase before returning: ReadOnly()
        # above leaves the scheduler unable to accept writes, and the very
        # next call to apply() writes input values with no intervening
        # await -- without this, that write raises "scheduled during a
        # read-only sync phase". The combinational path never hits this
        # (it has no clock edges / read-only phase to begin with).
        await RisingEdge(dut.clk)
        return outputs


async def make_driver(dut) -> HazardUnitDriver:
    drv = HazardUnitDriver(dut)
    await drv.setup()
    return drv


def expect(outputs: dict, **expected) -> None:
    """Assert a subset of OUTPUT_FIELDS equal expected values; all others
    (fields not named in `expected`) must be 0 -- the reset/idle value for
    every output on this DUT (all outputs are single-purpose flags/selects
    with no other meaningful default)."""
    for name in OUTPUT_FIELDS:
        want = expected.get(name, 0)
        got = outputs[name]
        assert got == want, f"{name}: expected {want}, got {got} (outputs={outputs})"


# ---------------------------------------------------------------------------
# (a) Directed tests -- oracle is the header comment (lines 1-26), by hand.
# ---------------------------------------------------------------------------


# Priority 1: mem_trap_redirect > everything.
# Header: "flush EX2, EX1b2, EX1b, EX1c, EX1a, ID, IF" -- no stalls.
@cocotb.test()
async def test_priority_mem_trap_redirect(dut):
    drv = await make_driver(dut)
    vec = default_inputs()
    vec["mem_trap_redirect"] = 1
    # Higher-beats-lower conflict #1: also assert mem_cache_stall, ex_pc_redirect,
    # id_jal_taken and a load-use condition; mem_trap_redirect must still win outright.
    vec["mem_cache_stall"] = 1
    vec["ex_pc_redirect"] = 1
    vec["id_jal_taken"] = 1
    vec["id_ex_mem_rd"] = 1
    vec["id_ex_rd_addr"] = 3
    vec["if_id_rs1_addr"] = 3
    out = await drv.apply(vec)
    expect(
        out,
        flush_if_id=1,
        flush_id_ex=1,
        flush_ex1a_ex1b_o=1,
        flush_ex1c_ex1b_o=1,
        flush_ex1_ex2_o=1,
        flush_ex_mem=1,
    )


# Priority 2: mem_cache_stall -- global freeze, no flushes.
@cocotb.test()
async def test_priority_mem_cache_stall(dut):
    drv = await make_driver(dut)
    vec = default_inputs()
    vec["mem_cache_stall"] = 1
    vec["ex_pc_redirect"] = 1  # lower priority; must not fire
    out = await drv.apply(vec)
    expect(
        out,
        stall_pc=1,
        stall_if_id=1,
        stall_id_ex=1,
        stall_ex_mem=1,
        stall_ex1_ex2_o=1,
        stall_ex1a_ex1b_o=1,
        stall_ex1c_ex1b_o=1,
    )


# Priority 3: ex_pc_redirect -- same flush set as mem_trap_redirect, but only
# when neither higher-priority condition holds.
@cocotb.test()
async def test_priority_ex_pc_redirect(dut):
    drv = await make_driver(dut)
    vec = default_inputs()
    vec["ex_pc_redirect"] = 1
    vec["id_jal_taken"] = 1  # lower priority; must not change the result
    out = await drv.apply(vec)
    expect(
        out,
        flush_if_id=1,
        flush_id_ex=1,
        flush_ex1a_ex1b_o=1,
        flush_ex1c_ex1b_o=1,
        flush_ex1_ex2_o=1,
        flush_ex_mem=1,
    )


# Priority 4: id_jal_taken -- flush IF only.
# Higher-beats-lower conflict #2: id_jal_taken must beat a simultaneous load-use.
@cocotb.test()
async def test_priority_id_jal_taken_beats_load_use(dut):
    drv = await make_driver(dut)
    vec = default_inputs()
    vec["id_jal_taken"] = 1
    vec["id_ex_mem_rd"] = 1
    vec["id_ex_rd_addr"] = 5
    vec["if_id_rs1_addr"] = 5  # would be load_use_ex1 on its own
    out = await drv.apply(vec)
    expect(out, flush_if_id=1)


# Priorities 5-8: the four load-use hazards (load_use_ex1/ex1c/ex1b/ex2) are
# documented as four DISTINCT priority levels, but the header specifies the
# SAME response for all four ("stall IF,ID; flush ID->EX1a"). From the header
# alone the four are output-indistinguishable, so rather than assert a
# specific tier "wins" (which the header's stall/flush outputs cannot show),
# we assert the response is correct and identical however many of the four
# fire simultaneously -- a fact the header DOES determine (each branch
# independently produces this same triple).
def _expect_load_use_stall(out):
    expect(out, stall_pc=1, stall_if_id=1, flush_id_ex=1)


@cocotb.test()
async def test_load_use_ex1_alone(dut):
    drv = await make_driver(dut)
    vec = default_inputs()
    vec["id_ex_mem_rd"] = 1
    vec["id_ex_rd_addr"] = 4
    vec["if_id_rs1_addr"] = 4
    out = await drv.apply(vec)
    _expect_load_use_stall(out)


@cocotb.test()
async def test_load_use_ex1c_alone(dut):
    drv = await make_driver(dut)
    vec = default_inputs()
    vec["ex1b_mem_rd"] = 1
    vec["ex1b_rd_addr"] = 4
    vec["if_id_rs2_addr"] = 4
    out = await drv.apply(vec)
    _expect_load_use_stall(out)


@cocotb.test()
async def test_load_use_ex1b_alone(dut):
    drv = await make_driver(dut)
    vec = default_inputs()
    vec["ex1c_mem_rd"] = 1
    vec["ex1c_rd_addr"] = 4
    vec["if_id_rs1_addr"] = 4
    out = await drv.apply(vec)
    _expect_load_use_stall(out)


@cocotb.test()
async def test_load_use_ex2_alone(dut):
    drv = await make_driver(dut)
    vec = default_inputs()
    vec["ex1b2_mem_rd"] = 1
    vec["ex1b2_rd_addr"] = 4
    vec["if_id_rs2_addr"] = 4
    out = await drv.apply(vec)
    _expect_load_use_stall(out)


@cocotb.test()
async def test_load_use_all_four_simultaneous(dut):
    """All four load-use conditions true at once -- response must be
    identical to any one alone (the header gives each an independent,
    identical stall/flush response, so ORing them must not change it)."""
    drv = await make_driver(dut)
    vec = default_inputs()
    vec["id_ex_mem_rd"] = 1
    vec["id_ex_rd_addr"] = 1
    vec["ex1b_mem_rd"] = 1
    vec["ex1b_rd_addr"] = 2
    vec["ex1c_mem_rd"] = 1
    vec["ex1c_rd_addr"] = 3
    vec["ex1b2_mem_rd"] = 1
    vec["ex1b2_rd_addr"] = 4
    vec["if_id_rs1_addr"] = 1
    vec["if_id_rs2_addr"] = 2
    out = await drv.apply(vec)
    _expect_load_use_stall(out)


# Priority 9: if_cache_stall -- stall PC only, when nothing higher fires.
@cocotb.test()
async def test_priority_if_cache_stall_alone(dut):
    drv = await make_driver(dut)
    vec = default_inputs()
    vec["if_cache_stall"] = 1
    out = await drv.apply(vec)
    expect(out, stall_pc=1)


# Higher-beats-lower conflict #3: a load-use hazard must beat if_cache_stall.
@cocotb.test()
async def test_load_use_beats_if_cache_stall(dut):
    drv = await make_driver(dut)
    vec = default_inputs()
    vec["if_cache_stall"] = 1
    vec["id_ex_mem_rd"] = 1
    vec["id_ex_rd_addr"] = 7
    vec["if_id_rs1_addr"] = 7
    out = await drv.apply(vec)
    _expect_load_use_stall(out)


@cocotb.test()
async def test_idle_all_zero(dut):
    """Nothing asserted -- every stall/flush output must be 0."""
    drv = await make_driver(dut)
    out = await drv.apply(default_inputs())
    expect(out)


# ---------------------------------------------------------------------------
# Forwarding tiers (fwd_a_* for rs1; a smaller mirror set for fwd_b_*/store)
#
# Header encoding (lines 9-15): 00=regfile, 01=EX2, 10=WB, 11=EX1b(highest);
# EX1c and EX1b2 are separate 1-bit tiers layered on top of the 2-bit select.
# The header states EX1b is explicitly "highest priority" and gives a cycles-
# behind figure for each producer (EX1b=1, EX1c=2, EX1b2=3, EX2=4, WB=later
# still, after a stall). For an in-order pipeline a RAW hazard must resolve
# to the CLOSEST (fewest-cycles-behind) producer -- an older, more-cycles-
# behind write to the same rd has necessarily already been superseded in
# program order by a nearer one if both are simultaneously in flight -- so
# priority strictly follows the header's cycle counts:
#     EX1b(1) > EX1c(2) > EX1b2(3) > EX2(4) > WB.
# This is the one place the header does not spell out relative priority in
# so many words; it is derived from the documented cycle counts rather than
# read off the implementation. (Flagged in the task report: this ordering of
# EX1c vs EX1b2 is the part the header leaves most implicit.)
# ---------------------------------------------------------------------------


@cocotb.test()
async def test_fwd_a_ex1b_tier(dut):
    drv = await make_driver(dut)
    vec = default_inputs()
    vec["id_ex_rs1_addr"] = 6
    vec["ex1b_reg_wr_en"] = 1
    vec["ex1b_rd_addr"] = 6
    out = await drv.apply(vec)
    expect(out, fwd_a_sel=0b11)


@cocotb.test()
async def test_fwd_a_ex1c_tier(dut):
    drv = await make_driver(dut)
    vec = default_inputs()
    vec["id_ex_rs1_addr"] = 6
    vec["ex1c_reg_wr_en"] = 1
    vec["ex1c_rd_addr"] = 6
    out = await drv.apply(vec)
    expect(out, fwd_a_ex1c=1)


@cocotb.test()
async def test_fwd_a_ex1b2_tier(dut):
    drv = await make_driver(dut)
    vec = default_inputs()
    vec["id_ex_rs1_addr"] = 6
    vec["ex1b2_reg_wr_en"] = 1
    vec["ex1b2_rd_addr"] = 6
    out = await drv.apply(vec)
    expect(out, fwd_a_ex1b2=1)


@cocotb.test()
async def test_fwd_a_ex2_tier(dut):
    drv = await make_driver(dut)
    vec = default_inputs()
    vec["id_ex_rs1_addr"] = 6
    vec["ex_mem_reg_wr_en"] = 1
    vec["ex_mem_rd_addr"] = 6
    out = await drv.apply(vec)
    expect(out, fwd_a_sel=0b01)


@cocotb.test()
async def test_fwd_a_wb_tier(dut):
    drv = await make_driver(dut)
    vec = default_inputs()
    vec["id_ex_rs1_addr"] = 6
    vec["mem_wb_reg_wr_en"] = 1
    vec["mem_wb_rd_addr"] = 6
    out = await drv.apply(vec)
    expect(out, fwd_a_sel=0b10)


@cocotb.test()
async def test_fwd_a_none_matches_regfile(dut):
    drv = await make_driver(dut)
    vec = default_inputs()
    vec["id_ex_rs1_addr"] = 6
    # No producer targets rs1 -- regfile value should be used (all-zero select).
    out = await drv.apply(vec)
    expect(out)


@cocotb.test()
async def test_fwd_a_priority_ex1b_over_all(dut):
    """All five tiers target the same rd -- EX1b (highest, per header) wins."""
    drv = await make_driver(dut)
    vec = default_inputs()
    vec["id_ex_rs1_addr"] = 2
    vec["ex1b_reg_wr_en"] = 1
    vec["ex1b_rd_addr"] = 2
    vec["ex1c_reg_wr_en"] = 1
    vec["ex1c_rd_addr"] = 2
    vec["ex1b2_reg_wr_en"] = 1
    vec["ex1b2_rd_addr"] = 2
    vec["ex_mem_reg_wr_en"] = 1
    vec["ex_mem_rd_addr"] = 2
    vec["mem_wb_reg_wr_en"] = 1
    vec["mem_wb_rd_addr"] = 2
    out = await drv.apply(vec)
    expect(out, fwd_a_sel=0b11)


@cocotb.test()
async def test_fwd_a_priority_ex1c_over_ex1b2_ex2_wb(dut):
    """EX1b disqualified (issuing a load, so it cannot forward a value yet);
    EX1c, EX1b2, EX2, WB all target the same rd -- EX1c must win per the
    cycles-behind ordering derived above."""
    drv = await make_driver(dut)
    vec = default_inputs()
    vec["id_ex_rs1_addr"] = 2
    vec["ex1b_reg_wr_en"] = 1
    vec["ex1b_mem_rd"] = 1  # disqualifies EX1b tier (load, not yet forwardable)
    vec["ex1b_rd_addr"] = 2
    vec["ex1c_reg_wr_en"] = 1
    vec["ex1c_rd_addr"] = 2
    vec["ex1b2_reg_wr_en"] = 1
    vec["ex1b2_rd_addr"] = 2
    vec["ex_mem_reg_wr_en"] = 1
    vec["ex_mem_rd_addr"] = 2
    vec["mem_wb_reg_wr_en"] = 1
    vec["mem_wb_rd_addr"] = 2
    out = await drv.apply(vec)
    expect(out, fwd_a_ex1c=1)


@cocotb.test()
async def test_fwd_a_priority_ex1b2_over_ex2_wb(dut):
    drv = await make_driver(dut)
    vec = default_inputs()
    vec["id_ex_rs1_addr"] = 2
    vec["ex1b_reg_wr_en"] = 1
    vec["ex1b_mem_rd"] = 1
    vec["ex1b_rd_addr"] = 2
    vec["ex1c_reg_wr_en"] = 1
    vec["ex1c_mem_rd"] = 1
    vec["ex1c_rd_addr"] = 2
    vec["ex1b2_reg_wr_en"] = 1
    vec["ex1b2_rd_addr"] = 2
    vec["ex_mem_reg_wr_en"] = 1
    vec["ex_mem_rd_addr"] = 2
    vec["mem_wb_reg_wr_en"] = 1
    vec["mem_wb_rd_addr"] = 2
    out = await drv.apply(vec)
    expect(out, fwd_a_ex1b2=1)


@cocotb.test()
async def test_fwd_a_priority_ex2_over_wb(dut):
    drv = await make_driver(dut)
    vec = default_inputs()
    vec["id_ex_rs1_addr"] = 2
    vec["ex_mem_reg_wr_en"] = 1
    vec["ex_mem_rd_addr"] = 2
    vec["mem_wb_reg_wr_en"] = 1
    vec["mem_wb_rd_addr"] = 2
    out = await drv.apply(vec)
    expect(out, fwd_a_sel=0b01)


@cocotb.test()
async def test_fwd_b_ex1b_tier(dut):
    """fwd_b_* mirrors fwd_a_* against rs2 -- spot-check one tier + priority.

    fwd_store_sel is expected to track fwd_b_sel here too (see
    test_fwd_store_mirrors_fwd_b below for why): a producer targeting rs2
    is also the store-data producer, so both sighted outputs move together.
    """
    drv = await make_driver(dut)
    vec = default_inputs()
    vec["id_ex_rs2_addr"] = 5
    vec["ex1b_reg_wr_en"] = 1
    vec["ex1b_rd_addr"] = 5
    out = await drv.apply(vec)
    expect(out, fwd_b_sel=0b11, fwd_store_sel=0b11)


@cocotb.test()
async def test_fwd_b_ex2_over_wb(dut):
    drv = await make_driver(dut)
    vec = default_inputs()
    vec["id_ex_rs2_addr"] = 5
    vec["ex_mem_reg_wr_en"] = 1
    vec["ex_mem_rd_addr"] = 5
    vec["mem_wb_reg_wr_en"] = 1
    vec["mem_wb_rd_addr"] = 5
    out = await drv.apply(vec)
    expect(out, fwd_b_sel=0b01, fwd_store_sel=0b01)


@cocotb.test()
async def test_fwd_store_mirrors_fwd_b(dut):
    """RV32I stores source their store-data operand from rs2, so
    fwd_store_sel/_ex1c/_ex1b2 are expected to track fwd_b_*/_ex1c/_ex1b2
    exactly. This is an architectural inference from the RV32I ISA (not a
    fact stated in the header), included because it is the only sensible
    reading of a "store forwarding" tier that shares rs2's hazard sources."""
    drv = await make_driver(dut)
    vec = default_inputs()
    vec["id_ex_rs2_addr"] = 5
    vec["ex1c_reg_wr_en"] = 1
    vec["ex1c_rd_addr"] = 5
    out = await drv.apply(vec)
    expect(out, fwd_b_ex1c=1, fwd_store_ex1c=1)


# ---------------------------------------------------------------------------
# x0 (register 0) must never forward and never cause a load-use stall --
# this is an RV32I architectural fact (x0 hardwired to zero), stated in the
# task, not read from the implementation.
# ---------------------------------------------------------------------------


@cocotb.test()
async def test_x0_never_forwards(dut):
    drv = await make_driver(dut)
    vec = default_inputs()
    # Producer "writes" x0 (rd=0); even with reg_wr_en asserted this must
    # never be treated as a real write, so no forward should occur.
    vec["id_ex_rs1_addr"] = 0
    vec["ex1b_reg_wr_en"] = 1
    vec["ex1b_rd_addr"] = 0
    out = await drv.apply(vec)
    expect(out)


@cocotb.test()
async def test_x0_never_load_use_stalls(dut):
    drv = await make_driver(dut)
    vec = default_inputs()
    # A "load into x0" must never stall the pipeline -- x0 always reads 0
    # regardless of what any load writes to it.
    vec["id_ex_mem_rd"] = 1
    vec["id_ex_rd_addr"] = 0
    vec["if_id_rs1_addr"] = 0
    vec["if_id_rs2_addr"] = 0
    out = await drv.apply(vec)
    expect(out)


# ---------------------------------------------------------------------------
# (b) Randomised cross-arm differential
# ---------------------------------------------------------------------------

# Small pool so producer/consumer addresses collide often (a uniform 5-bit
# field would almost never collide and would exercise none of the hazard
# logic above). Includes 0 (x0) deliberately, to also exercise the x0
# never-forwards/never-stalls path under random combination with everything
# else.
_REG_POOL = list(range(8))

# Control-bit assertion probability: high enough that multiple hazard
# conditions frequently coincide (stressing the priority chain), not so high
# that every vector degenerates into the same top-priority case.
_CTRL_P = 0.35


def _random_vector(rng: random.Random) -> dict:
    vec = {}
    for name in INPUT_FIELDS:
        if name.endswith("_addr"):
            vec[name] = rng.choice(_REG_POOL)
        else:
            vec[name] = 1 if rng.random() < _CTRL_P else 0
    return vec


@cocotb.test()
async def test_random_cross_arm(dut):
    seed = int(os.environ.get("HAZARD_TRACE_SEED", "12345"))
    n = int(os.environ.get("HAZARD_TRACE_N", "2000"))
    rng = random.Random(seed)

    drv = await make_driver(dut)
    vectors = []
    for _ in range(n):
        vec = _random_vector(rng)
        # apply() itself int()-converts every output; on Verilator/cocotb
        # that raises if any bit resolved to X/Z, so a vector that reaches
        # here is already known-good -- no separate no-op check needed.
        out = await drv.apply(vec)
        vectors.append({"inputs": vec, "outputs": out})

    toplevel = os.environ.get("TOPLEVEL", "unknown")
    out_dir = Path(__file__).resolve().parents[3] / "sim" / "build"
    out_dir.mkdir(parents=True, exist_ok=True)
    trace_path = out_dir / f"hazard_trace_{toplevel}.json"
    trace_path.write_text(
        json.dumps(
            {
                "toplevel": toplevel,
                "seed": seed,
                "count": n,
                "input_fields": INPUT_FIELDS,
                "output_fields": OUTPUT_FIELDS,
                "vectors": vectors,
            },
            indent=None,
        )
    )
    dut._log.info(f"wrote {n} vectors (seed={seed}) to {trace_path}")
