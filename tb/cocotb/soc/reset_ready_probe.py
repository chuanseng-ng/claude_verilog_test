"""
reset_ready_probe.py -- shared probe for "a ready output must be low while its reset is asserted".

A reset value must not advertise availability: while a domain is in reset, every ready output it
drives must be low, whatever the masters present on VALID. Suites at unit level call these helpers
to hold reset low with every VALID input high and to sample the ready outputs once per cycle. A
suite at SoC level reads the same signals from a bench with a clock ratio other than 1:1.

Method of one probe:
  1. Assert reset with every VALID low and run a few edges, so the reset reaches a synchronous FSM
     and no state of an earlier test remains.
  2. Raise every VALID in `valids` (and apply `extra`), then keep reset asserted.
  3. Sample every ready at each falling edge for `cycles` cycles. Falling-edge sampling shows the
     settled value of a combinational ready.
The hold of step 1 begins from an idle FSM, so a reset that arrives in the middle of a transaction
is not covered by these helpers.

The control half releases reset with the same VALID inputs still high. It must show the ready
outputs go high. This proves the probe can see a ready at all, so an all-low result in reset is not
blindness.
"""

from cocotb.triggers import FallingEdge, ReadOnly, RisingEdge

FLUSH_EDGES = 3
LEAD_EDGES = 2
SAMPLE_CYCLES = 8


async def hold_reset_sample_ready(
    clk, rst_n, valids, readies, extra=None, cycles=SAMPLE_CYCLES, reset_active_low=True
):
    """Hold reset with every VALID high; return [(cycle, ready_name), ...] for each high sample.

    clk, rst_n    handles of the clock and the reset input under test (the clock must be running)
    valids        VALID input handles, all driven high after the flush
    readies       {name: handle} of every ready output whose reset behaviour is checked
    extra         {handle: value} data inputs (addresses) applied together with the VALID inputs
    """
    asserted = 0 if reset_active_low else 1
    rst_n.value = asserted
    for sig in valids:
        sig.value = 0
    for _ in range(FLUSH_EDGES):
        await RisingEdge(clk)
    for sig, val in (extra or {}).items():
        sig.value = val
    for sig in valids:
        sig.value = 1
    for _ in range(LEAD_EDGES):
        await RisingEdge(clk)
    seen = []
    for cycle in range(cycles):
        await FallingEdge(clk)
        for name, sig in readies.items():
            if int(sig.value):
                seen.append((cycle, name))
    return seen


async def release_reset_sample_ready(
    clk, rst_n, readies, cycles=SAMPLE_CYCLES, reset_active_low=True
):
    """Release reset with the VALID inputs still high; return the set of ready names seen high."""
    rst_n.value = 1 if reset_active_low else 0
    seen = set()
    # A ready that rises with reset can fall again at the first clock edge (a handshake with the
    # VALID that is still high), so look at the settled value before that edge as well.
    await ReadOnly()
    seen.update(name for name, sig in readies.items() if int(sig.value))
    for _ in range(cycles):
        await FallingEdge(clk)
        for name, sig in readies.items():
            if int(sig.value):
                seen.add(name)
    return seen


def summarise(seen):
    """Return 'name (first cycle, n cycles of m)' text for a list from hold_reset_sample_ready."""
    names = sorted({n for _, n in seen})
    parts = []
    for name in names:
        cycles = [c for c, n in seen if n == name]
        parts.append(f"{name} high in {len(cycles)} sampled cycle(s), first at cycle {cycles[0]}")
    return "; ".join(parts)


def assert_ready_low(dut, seen, what):
    """Log the measured summary, then fail when any ready was high in reset."""
    msg = f"{what}: " + (summarise(seen) if seen else "every ready low in every sampled cycle")
    dut._log.info(msg)
    assert not seen, msg
