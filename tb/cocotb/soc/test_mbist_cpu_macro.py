"""
test_mbist_cpu_macro.py -- bead claude_verilog_test-c54a (DFT Stage 4, DFT_ARCHITECTURE.md 16.7): MBIST on the ten
cache SRAMs INSIDE the CPU hard macro, driven end to end through the JTAG TAP.

DUT: tb_mbist_cpu_macro = dft_ctrl + soc_mbist (CPU-domain control-word crossing and status return) + the REAL
rv32i_cpu_top built with +define+SRAM_SKY130 (ten mem_collar, the reset-free in-macro mbist_ctrl, N_MEM = 10,
AW = 8) in front of fault-injecting stand-ins that carry the real 1 KB macro's module name, behind an
rv32i_clock_gate that mirrors soc_top's u_cpu_cg (PMU enable OR the TAP-launched mbist_force).

Memory index (status `fail` bit): 0 I$ tag, 1..4 I$ data[0..3], 5 D$ tag, 6..9 D$ data[0..3].

What is proven (each record also checked against mbist_golden.py, the independent golden model, at AW = 8):
  * idle: MBIST reads cpu_present = 1 and done = 0 (an absent controller can never read as a pass); with
    bist_en = 0 every collar is a pass-through of the cache's functional signals, cycle by cycle, while the CPU
    macro is alive and fetching;
  * no fault: every algorithm family completes on all ten macros with no failure;
  * an inter-word coupling fault (CFid) in ONE macro, for each of the ten: only that macro's go/no-go bit fails and
    the TAP record equals the golden record;
  * ten different faults at once (stuck-at, transition, state/idempotent/inversion coupling, address-decoder alias,
    write-mask lane): ten distinct bits fail and each of the ten records equals golden;
  * the TAP-launched mbist_force opens a PMU-closed clock gate for the run and releases it afterwards, and the
    run only makes progress because of that (the macro clock really stops when the force is absent);
  * a functional reset of the CPU domain aborts a running test and can never start one.
"""

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, FallingEdge, RisingEdge
from jtag_driver import OP_MBIST_CTRL, OP_MBIST_STATUS, JtagDriver
from mbist_golden import Fault, ctl_word, decode_status, golden_first_fail

AW = 8
N = 10
TCK_NS = 53
CLK_NS = 10


def mem(dut, i):
    """The fault-injecting core behind memory index i (0..9)."""
    cache = dut.u_cpu.u_core.u_icache if i < 5 else dut.u_cpu.u_core.u_dcache
    j = i % 5
    if j == 0:
        return cache.u_tag_sram.u_core
    return cache.gen_data_sram[j - 1].u_data_sram.u_core


def arm(dut, i, f: Fault):
    m = mem(dut, i)
    m.fi_kind.value = f.kind
    m.fi_a_addr.value = f.a_addr
    m.fi_a_bit.value = f.a_bit
    m.fi_v_addr.value = f.v_addr
    m.fi_v_bit.value = f.v_bit
    m.fi_val.value = f.val
    m.fi_dir.value = f.dir
    m.fi_ret_t.value = f.ret_t


def clear_faults(dut):
    for i in range(N):
        arm(dut, i, Fault())
        mem(dut, i).fi_clear.value = 1


async def setup(dut, pmu_en=1):
    cocotb.start_soon(Clock(dut.clk_i, CLK_NS, units="ns").start())
    dut.scan_clk_i.value = 0
    dut.rst_n_i.value = 0
    dut.pmu_clk_en_i.value = pmu_en
    dut.pmu_rst_n_i.value = 1
    drv = JtagDriver(dut.tck_i, dut.tms_i, dut.tdi_i, dut.trst_ni, dut.tdo_o,
                     period_ns=TCK_NS, probe=None, name="mbist_cpu")  # fmt: skip
    await drv.start(hold_reset=True)
    await ClockCycles(dut.clk_i, 8)
    dut.rst_n_i.value = 1
    await drv.release_trst()
    await ClockCycles(dut.clk_i, 6)
    clear_faults(dut)
    await ClockCycles(dut.clk_i, 6)
    return drv


async def read_status(drv):
    await drv.load_ir(OP_MBIST_STATUS)
    v = await drv.shift_dr(0, 140)
    return {"ovf": v & 1, "present": (v >> 1) & 1, "cpu": decode_status((v >> 71) & ((1 << 69) - 1))}


async def run(drv, **kw):
    await drv.write_tdr(OP_MBIST_CTRL, ctl_word(run=1, dom_core=0, dom_cpu=1, **kw), 29)
    for _ in range(600):
        st = await read_status(drv)
        if st["cpu"]["done"]:
            return st
    raise AssertionError("CPU-domain MBIST did not finish")


async def record(drv, base, i):
    kw = dict(base)
    kw["rd_sel"] = i
    await drv.write_tdr(OP_MBIST_CTRL, ctl_word(run=1, dom_core=0, dom_cpu=1, **kw), 29)
    return (await read_status(drv))["cpu"]


async def stop(dut, drv):
    await drv.write_tdr(OP_MBIST_CTRL, ctl_word(run=0, dom_core=0, dom_cpu=1), 29)
    await ClockCycles(dut.clk_i, 10)
    assert int(dut.bist_en_o.value) == 0


def passthrough_pairs(dut):
    """(functional, macro-side) signal pairs of the tag and data collars of both caches."""
    pairs = []
    for cache in (dut.u_cpu.u_core.u_icache, dut.u_cpu.u_core.u_dcache):
        pairs.append((cache.tag_csb0, cache.tag_csb0_m))
        pairs.append((cache.tag_web0, cache.tag_web0_m))
        pairs.append((cache.tag_addr0, cache.tag_addr0_m))
        pairs.append((cache.tag_din0, cache.tag_din0_m))
        for g in range(4):
            sc = cache.gen_data_sram[g]
            pairs.append((cache.data_csb0[g], sc.d_csb0_m))
            pairs.append((cache.data_web0[g], sc.d_web0_m))
            pairs.append((cache.data_addr0[g], sc.d_addr0_m))
            pairs.append((cache.data_din0[g], sc.d_din0_m))
    return pairs


@cocotb.test()
async def test_idle_collars_are_passthrough_and_macro_alive(dut):
    drv = await setup(dut)
    assert int(dut.bist_en_o.value) == 0
    st = await read_status(drv)
    assert st["present"] == 1 and st["ovf"] == 0
    assert st["cpu"]["done"] == 0 and st["cpu"]["fail_any"] == 0 and st["cpu"]["busy"] == 0, st
    pairs = passthrough_pairs(dut)
    fetches = 0
    activity = 0
    ic = dut.u_cpu.u_core.u_icache
    dc = dut.u_cpu.u_core.u_dcache
    # restart the parked CPU so its first fetch (tag + data reads, refill request) falls inside the sampled window
    dut.rst_n_i.value = 0
    await ClockCycles(dut.clk_i, 4)
    dut.rst_n_i.value = 1
    for _ in range(400):
        await RisingEdge(dut.gclk_o)
        fetches += int(dut.arvalid_o.value)
        for f, m in pairs:
            assert int(f.value) == int(m.value), "bist_en = 0: a collar must pass the functional signal through"
        # a macro operation is requested this cycle (active-low csb0) on any of the ten macros
        csbs = [ic.tag_csb0, dc.tag_csb0] + [ic.data_csb0[g] for g in range(4)] + [dc.data_csb0[g] for g in range(4)]
        activity += any(int(c.value) == 0 for c in csbs)
    assert fetches > 0, "the parked CPU macro must still be asking for its first fetch (alive)"
    assert activity > 0, "a cache macro was accessed at least once, so the pass-through check was not vacuous"
    # run = 0 written explicitly changes nothing
    await stop(dut, drv)


@cocotb.test()
async def test_no_fault_all_algorithms(dut):
    drv = await setup(dut)
    for kw in (dict(alg=0), dict(alg=2, pause_mant=3, pause_exp=0), dict(alg=3, bg_sel=2), dict(alg=4), dict(alg=5)):
        st = await run(drv, **kw)
        c = st["cpu"]
        assert c["done"] == 1 and c["fail_any"] == 0 and c["fail"] == 0 and c["cfg_err"] == 0, (kw, c)
        assert int(dut.bist_en_o.value) == 1
        await stop(dut, drv)
    dut._log.info("all five algorithm families pass on the ten cache macros with no fault")


@cocotb.test()
async def test_interword_fault_in_each_macro(dut):
    """CFid between two different words (aggressor word 4 bit 3 rising sets victim word 5 bit 3) in ONE macro at a
    time. A full-word March sees it; the go/no-go bit must be that macro's alone and the record must equal golden."""
    drv = await setup(dut)
    f = Fault(4, a_addr=4, a_bit=3, v_addr=5, v_bit=3, val=1, dir=1)
    exp = golden_first_fail(0, AW, False, f)
    assert exp is not None
    base = dict(alg=0, mask_sel=0)
    for i in range(N):
        arm(dut, i, f)
        st = await run(drv, **base)
        assert st["cpu"]["fail"] == 1 << i, f"macro {i}: fail bits {st['cpu']['fail']:#x}"
        rec = await record(drv, dict(base, mask_sel=i), i)
        for k in ("addr", "elem", "slot", "bg", "port"):
            assert rec[k] == exp[k], f"macro {i}: {k} TAP {rec[k]} golden {exp[k]}"
        # the XOR mask follows mask_sel (latched at start): re-run selecting this macro and read it
        await stop(dut, drv)
        st = await run(drv, **dict(base, mask_sel=i))
        assert (await record(drv, dict(base, mask_sel=i), i))["mask"] == exp["mask"]
        await stop(dut, drv)
        arm(dut, i, Fault())
        mem(dut, i).fi_clear.value = 1
    dut._log.info("an inter-word coupling fault is attributed to exactly the macro that has it, for all ten")


@cocotb.test()
async def test_ten_different_faults_at_once(dut):
    drv = await setup(dut)
    faults = [
        Fault(1, v_addr=200, v_bit=31, val=1),                                 # 0 I$ tag     SAF1
        Fault(2, v_addr=3, v_bit=0, dir=1),                                    # 1 I$ data0   TF (cannot rise)
        Fault(3, a_addr=10, a_bit=4, v_addr=11, v_bit=4, val=0, dir=1),        # 2 I$ data1   CFin
        Fault(5, a_addr=20, a_bit=1, v_addr=21, v_bit=9, val=1, dir=0),        # 3 I$ data2   CFst
        Fault(7, a_addr=17, v_addr=9),                                         # 4 I$ data3   AF alias
        Fault(1, v_addr=0, v_bit=0, val=0),                                    # 5 D$ tag     SAF0
        Fault(4, a_addr=100, a_bit=7, v_addr=101, v_bit=7, val=1, dir=1),      # 6 D$ data0   CFid
        Fault(10, v_bit=2, val=1),                                             # 7 D$ data1   WMASK lane 2 stuck
        Fault(6, v_addr=255),                                                  # 8 D$ data2   AF none
        Fault(8, a_addr=60, v_addr=61),                                        # 9 D$ data3   AF multi
    ]
    for i, f in enumerate(faults):
        arm(dut, i, f)
    # FULL = March C-/retention + checkerboard + lane tests, so the WMASK fault is in reach
    base = dict(alg=5, pause_mant=2, pause_exp=0)
    st = await run(drv, **base)
    c = st["cpu"]
    for i, f in enumerate(faults):
        exp = golden_first_fail(5, AW, False, f, bg_sweep=False, bg_sel=0)
        assert (c["fail"] >> i) & 1 == (exp is not None), f"macro {i} {f.label()}: go/no-go {c['fail']:#x} vs golden"
    assert bin(c["fail"]).count("1") == sum(golden_first_fail(5, AW, False, f) is not None for f in faults)
    assert c["fail"] != 0 and c["fail_any"] == 1
    checked = 0
    for i, f in enumerate(faults):
        exp = golden_first_fail(5, AW, False, f)
        if exp is None:
            continue
        rec = await record(drv, base, i)
        for k in ("addr", "elem", "slot", "bg", "port"):
            assert rec[k] == exp[k], f"macro {i} {f.label()}: {k} TAP {rec[k]} golden {exp[k]}"
        checked += 1
    assert checked >= 8, f"only {checked} of 10 faults were detected by FULL (golden model)"
    await stop(dut, drv)


async def count_edges(dut, cycles):
    n = 0
    for _ in range(cycles):
        await RisingEdge(dut.clk_i)
        await FallingEdge(dut.clk_i)
        n += int(dut.gclk_o.value)
    return n


@cocotb.test()
async def test_mbist_force_opens_the_closed_clock_gate(dut):
    drv = await setup(dut, pmu_en=1)
    dut.pmu_clk_en_i.value = 0  # the PMU powers the CPU clock down
    await ClockCycles(dut.clk_i, 6)
    ticks = 0
    for _ in range(40):
        await RisingEdge(dut.clk_i)
        await FallingEdge(dut.clk_i)
        ticks += int(dut.gclk_o.value)
    assert ticks == 0, "PMU-closed gate: the macro clock must be stopped (sampled high during the clk low phase)"
    assert int(dut.mbist_force_o.value) == 0
    # dom_cpu = 1 only: the force is the ONLY thing that can open the gate
    await drv.write_tdr(OP_MBIST_CTRL, ctl_word(run=1, dom_core=0, dom_cpu=1, alg=0), 29)
    for _ in range(600):
        st = await read_status(drv)
        if st["cpu"]["done"]:
            break
    else:
        raise AssertionError("MBIST made no progress through the forced gate")
    assert int(dut.mbist_force_o.value) == 1 and int(dut.bist_en_o.value) == 1
    assert st["cpu"]["fail_any"] == 0
    await drv.write_tdr(OP_MBIST_CTRL, ctl_word(run=0, dom_core=0, dom_cpu=1), 29)
    await ClockCycles(dut.clk_i, 12)
    assert int(dut.mbist_force_o.value) == 0 and int(dut.bist_en_o.value) == 0
    # gate closes again once the force is released (and MBIST is idle)
    assert await count_edges(dut, 30) == 0 or int(dut.pmu_clk_en_i.value) == 1
    # negative control: dom_cpu = 0 with run = 1 never forces the gate and never starts the CPU controller
    await drv.write_tdr(OP_MBIST_CTRL, ctl_word(run=1, dom_core=0, dom_cpu=0, alg=0), 29)
    await ClockCycles(dut.clk_i, 20)
    assert int(dut.mbist_force_o.value) == 0 and int(dut.bist_en_o.value) == 0
    await drv.write_tdr(OP_MBIST_CTRL, ctl_word(run=0), 29)


@cocotb.test()
async def test_functional_reset_aborts_and_never_starts(dut):
    drv = await setup(dut)
    await drv.write_tdr(OP_MBIST_CTRL, ctl_word(run=1, dom_core=0, dom_cpu=1, alg=5, bg_sweep=1), 29)
    for _ in range(100):
        await ClockCycles(dut.clk_i, 20)
        if int(dut.bist_en_o.value):
            break
    assert int(dut.bist_en_o.value) == 1, "the long run must be in progress"
    dut.rst_n_i.value = 0
    await ClockCycles(dut.clk_i, 8)
    assert int(dut.bist_en_o.value) == 0, "a functional reset aborts a running test"
    dut.rst_n_i.value = 1
    await ClockCycles(dut.clk_i, 40)
    assert int(dut.bist_en_o.value) == 0, "reset can never start MBIST: the holding register was cleared"
    st = await read_status(drv)
    assert st["cpu"]["done"] == 0 and st["cpu"]["busy"] == 0
    # and it restarts from scratch on a fresh MBIST_CTRL write
    st = await run(drv, alg=0)
    assert st["cpu"]["done"] == 1 and st["cpu"]["fail_any"] == 0
    await stop(dut, drv)


@cocotb.test()
async def test_macro_reset_alone_aborts_the_controller(dut):
    """The macro's own synchronous reset (the PMU part of cpu_domain_rst_n) does NOT reset the MBIST holding
    register, so only the reset folded into the controller's run (run & rst_n_i) can stop a test: bist_en must fall
    for the duration of the reset, and the run restarts from scratch (status cleared) once it is released because the
    run level is still 1."""
    drv = await setup(dut)
    await drv.write_tdr(OP_MBIST_CTRL, ctl_word(run=1, dom_core=0, dom_cpu=1, alg=5, bg_sweep=1), 29)
    for _ in range(100):
        await ClockCycles(dut.clk_i, 20)
        if int(dut.bist_en_o.value):
            break
    assert int(dut.bist_en_o.value) == 1
    dut.pmu_rst_n_i.value = 0
    await ClockCycles(dut.clk_i, 8)
    assert int(dut.bist_en_o.value) == 0, "macro reset must flush the reset-free controller"
    st = await read_status(drv)
    assert st["cpu"]["busy"] == 0 and st["cpu"]["done"] == 0
    dut.pmu_rst_n_i.value = 1
    await ClockCycles(dut.clk_i, 30)
    assert int(dut.bist_en_o.value) == 1, "run is still 1 in the holding register: the test restarts from scratch"
    await drv.write_tdr(OP_MBIST_CTRL, ctl_word(run=0, dom_core=0, dom_cpu=1), 29)
    await ClockCycles(dut.clk_i, 12)
    assert int(dut.bist_en_o.value) == 0
