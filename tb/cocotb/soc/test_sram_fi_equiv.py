"""
test_sram_fi_equiv.py -- bead claude_verilog_test-j41m.14: the fault-injecting SRAM model
(sram_fi_core.sv) with NO fault armed is cycle-equivalent to the real simulation model
sim/sky130_sram_4kbyte_1rw1r_32x1024_8.sv.

Every fault-injection result in test_mbist_ctrl.py rests on this: if the FI model's timing or its
write/read ordering differed from the real model, a pass there would say nothing about the real macro.
Random traffic includes port-0 writes with every byte mask, port-0 reads, port-1 reads, and the
same-address same-cycle write/read pair (the real model returns the OLD word on port 1).
"""

import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, RisingEdge, Timer


@cocotb.test()
async def test_fi_model_equals_real_model(dut):
    cocotb.start_soon(Clock(dut.clk_i, 10, units="ns").start())
    rng = random.Random(0xF1)
    dut.csb0_i.value = 1
    dut.web0_i.value = 1
    dut.wmask0_i.value = 0
    dut.addr0_i.value = 0
    dut.din0_i.value = 0
    dut.csb1_i.value = 1
    dut.addr1_i.value = 0
    await ClockCycles(dut.clk_i, 3)
    reads0 = reads1 = same = nonzero = 0
    hot = [rng.randrange(1024) for _ in range(12)]  # a small hot set so reads hit written words
    for cyc in range(6000):
        a0 = rng.choice(hot) if rng.random() < 0.7 else rng.randrange(1024)
        a1 = a0 if rng.random() < 0.3 else (rng.choice(hot) if rng.random() < 0.7 else rng.randrange(1024))
        op = rng.random()
        dut.csb0_i.value = 0 if op < 0.8 else 1
        dut.web0_i.value = 0 if op < 0.45 else 1
        dut.wmask0_i.value = rng.getrandbits(4) if rng.random() < 0.6 else 0xF
        dut.addr0_i.value = a0
        dut.din0_i.value = rng.getrandbits(32)
        dut.csb1_i.value = 0 if rng.random() < 0.6 else 1
        dut.addr1_i.value = a1
        reads0 += int(op < 0.8 and op >= 0.45)
        reads1 += 1
        same += int(a0 == a1 and op < 0.45)
        await RisingEdge(dut.clk_i)
        await Timer(1, units="ps")
        nonzero += int(int(dut.dout1_real_o.value) != 0 or int(dut.dout0_real_o.value) != 0)
    assert int(dut.mismatch_o.value) == 0, f"{int(dut.mismatch_o.value)} cycles with differing outputs"
    # vacuity guards: the traffic really exercised the interesting cases
    assert reads0 > 500 and reads1 > 500 and same > 20 and nonzero > 500, (reads0, reads1, same, nonzero)
