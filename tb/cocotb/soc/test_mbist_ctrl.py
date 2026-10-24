"""
test_mbist_ctrl.py -- bead claude_verilog_test-j41m.14 (DFT Stage 4), unit + fault-injection suite for
rtl/soc/dft/mbist_ctrl.sv and rtl/soc/dft/mem_collar.sv.

DUT: tb_mbist_domain = mbist_ctrl + N mem_collar + N sram_fi_core (fault-injecting model with the Sky130
macro timing). Three build points, selected by the MBIST_CFG environment variable (Makefile target
`mbist_ctrl`):
    small  N_MEM=4  AW=6   P1_MASK=0101  every algorithm x every fault class (fast)
    soc    N_MEM=2  AW=10  P1_MASK=01    the SoC-level shape: 1024 x 32 macros, port 1 on memory 0
    cpu    N_MEM=10 AW=8   P1_MASK=0     the CPU-macro shape: ten 256 x 32 cache SRAMs

What makes this more than a smoke test (the failure to rule out is a BIST that always passes):
  * every run is compared with an INDEPENDENT golden model (mbist_golden.py) executing the algorithm on a
    Python mirror of the same faulty memory; the RTL must reproduce the first failure exactly: fail flag
    per memory, word address, element, op slot, background, port, and the XOR mask;
  * a fault goes into ONE memory of several; the others must report no failure;
  * textbook claims are asserted separately from the golden agreement (March C- must detect every SAF, TF,
    address-decoder fault and inter-word coupling fault; a full-word March must NOT see a write-mask lane
    that is always written, the LANE algorithm must; a solid background must miss an intra-word coupling
    fault that a non-solid background exposes; RETENTION must catch a decaying cell only when the pause
    exceeds the decay time);
  * no-fault runs of every algorithm and background must pass (a BIST that always fails is excluded too).
"""

import os
import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, RisingEdge, Timer
from common.hier import hgen
from mbist_golden import (
    ALG_NAME,
    ALG_RANGE,
    BG,
    Fault,
    catalogue,
    cfg_word,
    decode_status,
    golden_first_fail,
)

CFG = os.environ.get("MBIST_CFG", "small")
GEOM = {"small": (4, 6, 0b0101), "soc": (2, 10, 0b01), "cpu": (10, 8, 0)}
N_MEM, AW, P1_MASK = GEOM[CFG]
N_WORDS = 1 << AW
MEM_IDX_FAULTY = {"small": (0, 1, 2, 3), "soc": (0, 1), "cpu": (0, 5, 9)}[CFG]

only_small = dict(skip=CFG != "small")
only_soc = dict(skip=CFG != "soc")
only_cpu = dict(skip=CFG != "cpu")


def mem(dut, i):
    return hgen(dut, "g_mem", i, "u_mem")


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


def disarm_all(dut):
    for i in range(N_MEM):
        arm(dut, i, Fault())


async def clear_all(dut):
    """Zero every memory (sram_fi_core.fi_clear). The golden model starts from zeros; real silicon starts
    from garbage, which can only make detection earlier, so the exact-record comparison needs a known start."""
    for i in range(N_MEM):
        mem(dut, i).fi_clear.value = 1
    await ClockCycles(dut.clk_i, 2)


async def init(dut):
    cocotb.start_soon(Clock(dut.clk_i, 10, units="ns").start())
    dut.rst_n_i.value = 0
    dut.run_i.value = 0
    dut.cfg_i.value = 0
    dut.f_csb0_i.value = (1 << N_MEM) - 1
    dut.f_web0_i.value = (1 << N_MEM) - 1
    dut.f_wmask0_i.value = (1 << (4 * N_MEM)) - 1
    dut.f_addr0_i.value = 0
    dut.f_din0_i.value = 0
    dut.f_csb1_i.value = (1 << N_MEM) - 1
    dut.f_addr1_i.value = 0
    disarm_all(dut)
    await ClockCycles(dut.clk_i, 4)
    dut.rst_n_i.value = 1
    await ClockCycles(dut.clk_i, 2)


async def stop(dut):
    """run = 0 clears everything; wait until the controller is idle."""
    dut.run_i.value = 0
    await ClockCycles(dut.clk_i, 3)
    assert int(dut.bist_en_o.value) == 0


async def run_bist(dut, max_cycles=2_000_000, **kw):
    """Start (run = 1), wait for done, return (cycles from start to done, raw status). cfg stays applied."""
    dut.cfg_i.value = cfg_word(**kw)
    dut.run_i.value = 1
    cyc = 0
    while True:
        await RisingEdge(dut.clk_i)
        cyc += 1
        await Timer(1, units="ps")
        st = int(dut.status_o.value)
        if st & 1:
            return cyc, st
        assert cyc < max_cycles, "MBIST did not finish"


async def status_for(dut, i, base_kw):
    """Select memory i for the record readout (rd_sel is live) and decode."""
    kw = dict(base_kw)
    kw["rd_sel"] = i
    dut.cfg_i.value = cfg_word(**kw)
    await Timer(1, units="ps")
    return decode_status(int(dut.status_o.value))


async def settle(dut):
    await Timer(1, units="ps")


def has_p1(i):
    return bool((P1_MASK >> i) & 1)


async def check_against_golden(dut, alg, faulty, fault, **kw):
    """Run `alg` with `fault` armed in memory `faulty`; compare every memory with the golden model."""
    disarm_all(dut)
    await clear_all(dut)
    arm(dut, faulty, fault)
    mask_sel = kw.pop("mask_sel", faulty)
    base = dict(alg=alg, mask_sel=mask_sel, **kw)
    cyc, _ = await run_bist(dut, **base)
    exp = golden_first_fail(alg, AW, has_p1(faulty), fault, bool(kw.get("bg_sweep", 0)), kw.get("bg_sel", 0))
    for i in range(N_MEM):
        s = await status_for(dut, i, base)
        assert s["done"] == 1 and s["cfg_err"] == 0
        if i != faulty:
            assert not (s["fail"] >> i) & 1, f"clean memory {i} reported a failure ({fault.label()})"
            assert s["addr"] == 0 and s["elem"] == 0 and s["slot"] == 0, "clean memory has a record"
            continue
        got_fail = (s["fail"] >> i) & 1
        if exp is None:
            assert got_fail == 0, f"{ALG_NAME[alg]} {fault.label()}: RTL failed, golden passes"
        else:
            assert got_fail == 1, f"{ALG_NAME[alg]} {fault.label()}: RTL passed, golden fails at {exp}"
            for k in ("addr", "elem", "slot", "bg", "port"):
                assert s[k] == exp[k], f"{ALG_NAME[alg]} {fault.label()}: {k} RTL {s[k]} golden {exp[k]}"
            assert s["mask"] == exp["mask"], (
                f"{ALG_NAME[alg]} {fault.label()}: mask RTL {s['mask']:#x} golden {exp['mask']:#x}"
            )
    assert decode_status(int(dut.status_o.value))["fail_any"] == (0 if exp is None else 1)
    await stop(dut)
    return exp


# ---------------------------------------------------------------------------
# Basic behaviour
# ---------------------------------------------------------------------------
@cocotb.test(**only_small)
async def test_idle_collar_is_pass_through(dut):
    """bist_en = 0: every memory is reachable through its functional port 0 and (where present) port 1."""
    await init(dut)
    assert int(dut.bist_en_o.value) == 0
    rng = random.Random(1)
    data = {i: [rng.getrandbits(32) for _ in range(4)] for i in range(N_MEM)}
    for i in range(N_MEM):
        for a in range(4):
            dut.f_csb0_i.value = ((1 << N_MEM) - 1) & ~(1 << i)
            dut.f_web0_i.value = ((1 << N_MEM) - 1) & ~(1 << i)
            dut.f_addr0_i.value = a << (AW * i)
            dut.f_din0_i.value = data[i][a] << (32 * i)
            dut.f_wmask0_i.value = 0xF << (4 * i)
            await ClockCycles(dut.clk_i, 1)
            dut.f_csb0_i.value = (1 << N_MEM) - 1
            dut.f_web0_i.value = (1 << N_MEM) - 1
            await ClockCycles(dut.clk_i, 1)
    for i in range(N_MEM):
        for a in range(4):
            # port 0 read
            dut.f_csb0_i.value = ((1 << N_MEM) - 1) & ~(1 << i)
            dut.f_web0_i.value = (1 << N_MEM) - 1
            dut.f_addr0_i.value = a << (AW * i)
            await ClockCycles(dut.clk_i, 1)
            dut.f_csb0_i.value = (1 << N_MEM) - 1
            await ClockCycles(dut.clk_i, 1)
            await settle(dut)
            assert (int(dut.f_dout0_o.value) >> (32 * i)) & 0xFFFFFFFF == data[i][a]
            if has_p1(i):
                dut.f_csb1_i.value = ((1 << N_MEM) - 1) & ~(1 << i)
                dut.f_addr1_i.value = a << (AW * i)
                await ClockCycles(dut.clk_i, 1)
                dut.f_csb1_i.value = (1 << N_MEM) - 1
                await ClockCycles(dut.clk_i, 1)
                await settle(dut)
                assert (int(dut.f_dout1_o.value) >> (32 * i)) & 0xFFFFFFFF == data[i][a]


@cocotb.test(**only_small)
async def test_no_fault_every_algorithm_and_background_passes(dut):
    """A BIST that always fails is as useless as one that always passes."""
    await init(dut)
    for alg in range(6):
        for sweep, bg in ((0, 0), (0, 1), (0, 4), (1, 0)):
            if sweep and alg not in (0, 3, 5):
                continue
            cyc, st = await run_bist(dut, alg=alg, bg_sweep=sweep, bg_sel=bg, pause_mant=4, pause_exp=0)
            d = decode_status(st)
            assert d["done"] and not d["busy"] and not d["cfg_err"], (alg, sweep, bg, d)
            assert d["fail_any"] == 0 and d["fail"] == 0, f"{ALG_NAME[alg]} sweep={sweep} bg={bg}: {d}"
            assert int(dut.bist_en_o.value) == 1
            await stop(dut)


@cocotb.test(**only_small)
async def test_cycle_counts_pin_the_sequencing(dut):
    """Cycle count from run to done is a closed formula (regression guard on the sequencer)."""
    await init(dut)
    n = N_WORDS
    rd_lat = 2

    def formula(alg, pause_cycles=0):
        lo, hi = ALG_RANGE[alg]
        from mbist_golden import ELEMS

        t = 1  # IDLE -> INIT edge
        for ei in range(lo, hi + 1):
            e = ELEMS[ei]
            nops = 8 if e.lane else len(e.ops)
            t += 1 + (pause_cycles if e.pause else 0) + nops * n + rd_lat
        return t

    for alg in (0, 3, 4):
        cyc, _ = await run_bist(dut, alg=alg)
        assert abs(cyc - formula(alg)) <= 3, f"{ALG_NAME[alg]}: {cyc} cycles, formula {formula(alg)}"
        await stop(dut)
    c1, _ = await run_bist(dut, alg=1, pause_mant=10, pause_exp=1)  # 40 cycles per pause
    await stop(dut)
    c2, _ = await run_bist(dut, alg=1, pause_mant=10, pause_exp=2)  # 160 cycles per pause
    await stop(dut)
    assert c2 - c1 == 2 * (160 - 40), f"two pauses of +120 cycles expected, got {c2 - c1}"
    c0, _ = await run_bist(dut, alg=1, pause_mant=0, pause_exp=3)  # mant 0: no pause
    await stop(dut)
    cz, _ = await run_bist(dut, alg=1, pause_mant=10, pause_exp=0)  # 10 cycles per pause
    await stop(dut)
    assert cz - c0 == 2 * 10 + 0 or abs((cz - c0) - 20) <= 2, f"pause 10 cycles x2: {cz - c0}"


@cocotb.test(**only_small)
async def test_abort_and_restart(dut):
    """run -> 0 mid-test: bist_en drops, status clears; a restart gives the same result."""
    await init(dut)
    arm(dut, 1, Fault(1, v_addr=5, v_bit=7, val=1))
    dut.cfg_i.value = cfg_word(alg=5)
    dut.run_i.value = 1
    await ClockCycles(dut.clk_i, 300)
    assert int(dut.bist_en_o.value) == 1
    assert decode_status(int(dut.status_o.value))["busy"] == 1
    dut.run_i.value = 0
    await ClockCycles(dut.clk_i, 3)
    await settle(dut)
    assert int(dut.bist_en_o.value) == 0
    assert int(dut.status_o.value) & 0xF == 0 and (int(dut.status_o.value) >> 4) == 0
    first = await check_against_golden(dut, 0, 1, Fault(1, v_addr=5, v_bit=7, val=1))
    assert first is not None


@cocotb.test(**only_small)
async def test_reserved_config_finishes_with_cfg_err_and_touches_nothing(dut):
    await init(dut)
    # functional marker in memory 0 word 3
    dut.f_csb0_i.value = ((1 << N_MEM) - 1) & ~1
    dut.f_web0_i.value = ((1 << N_MEM) - 1) & ~1
    dut.f_addr0_i.value = 3
    dut.f_din0_i.value = 0xA5A5_5A5A
    await ClockCycles(dut.clk_i, 1)
    dut.f_csb0_i.value = (1 << N_MEM) - 1
    dut.f_web0_i.value = (1 << N_MEM) - 1
    await ClockCycles(dut.clk_i, 2)
    for kw in (dict(alg=6), dict(alg=7), dict(alg=2, bg_sel=6), dict(alg=2, bg_sel=7)):
        cyc, st = await run_bist(dut, **kw)
        d = decode_status(st)
        assert d["done"] == 1 and d["cfg_err"] == 1 and d["fail_any"] == 0, (kw, d)
        assert cyc < 6, "a reserved configuration must finish at once"
        await stop(dut)
    # the marker survived (no BIST write happened)
    dut.f_csb0_i.value = ((1 << N_MEM) - 1) & ~1
    dut.f_addr0_i.value = 3
    await ClockCycles(dut.clk_i, 1)
    dut.f_csb0_i.value = (1 << N_MEM) - 1
    await ClockCycles(dut.clk_i, 2)
    await settle(dut)
    assert int(dut.f_dout0_o.value) & 0xFFFFFFFF == 0xA5A5_5A5A


@cocotb.test(**only_small)
async def test_rd_sel_out_of_range_reads_zero_and_mask_follows_mask_sel(dut):
    await init(dut)
    arm(dut, 2, Fault(1, v_addr=5, v_bit=7, val=1))
    arm(dut, 3, Fault(1, v_addr=9, v_bit=20, val=1))
    base = dict(alg=0, mask_sel=3)
    _, st = await run_bist(dut, **base)
    s2 = await status_for(dut, 2, base)
    s3 = await status_for(dut, 3, base)
    assert (s2["fail"] >> 2) & 1 and (s3["fail"] >> 3) & 1 and not (s2["fail"] & 0b0011)
    assert s2["addr"] == 5 and s3["addr"] == 9
    assert s3["mask"] == 1 << 20, f"mask_sel=3 must hold memory 3's XOR mask, got {s3['mask']:#x}"
    s9 = await status_for(dut, 9, base)  # no such memory
    assert s9["addr"] == 0 and s9["elem"] == 0 and s9["port"] == 0
    await stop(dut)


# ---------------------------------------------------------------------------
# Fault injection: RTL == independent golden model, every class, every algorithm
# ---------------------------------------------------------------------------
@cocotb.test(**only_small)
async def test_fault_matrix_rtl_equals_golden(dut):
    await init(dut)
    cat = catalogue(AW)
    stats = {}
    for idx, (cls, f) in enumerate(cat):
        faulty = idx % N_MEM
        for alg in (0, 3):
            exp = await check_against_golden(dut, alg, faulty, f, bg_sel=1 if alg == 3 else 0)
            key = (ALG_NAME[alg], cls)
            tot, det = stats.get(key, (0, 0))
            stats[key] = (tot + 1, det + (exp is not None))
    for alg in (4, 2):
        if alg == 4:
            sub = [(c, f) for c, f in cat if c == "WMASK"] + [(c, f) for c, f in cat if c == "SAF"][::2]
        else:
            sub = [(c, f) for c, f in cat if c in ("SAF", "CFid", "AFalias")][::2]
        for idx, (cls, f) in enumerate(sub):
            exp = await check_against_golden(dut, alg, idx % N_MEM, f)
            key = (ALG_NAME[alg], cls)
            tot, det = stats.get(key, (0, 0))
            stats[key] = (tot + 1, det + (exp is not None))
    for (alg, cls), (tot, det) in sorted(stats.items()):
        dut._log.info(f"coverage {alg:13s} {cls:11s} detected {det}/{tot}")
    # textbook claims, asserted on the golden/RTL-agreed results
    full = {"SAF", "TF", "AFnone", "AFalias", "AFmulti", "CFin", "CFid", "CFst"}
    for cls in full:
        tot, det = stats[("MARCH_CM", cls)]
        assert det == tot, f"March C- must detect every {cls}: {det}/{tot}"
    tot, det = stats[("MARCH_CM", "WMASK")]
    assert 0 < det < tot, "March C- sees a never-written lane but not an always-written one"
    tot, det = stats[("LANE", "WMASK")]
    assert det == tot, f"the LANE algorithm must detect every write-mask lane fault: {det}/{tot}"


@cocotb.test(**only_small)
async def test_background_exposes_intra_word_coupling(dut):
    """CFid(bit0 rising sets bit1) inside one word: a solid background writes both bits together and
    never exposes it; a non-solid background does. The RTL must reproduce both golden results."""
    await init(dut)
    f = Fault(4, a_addr=9, a_bit=0, v_addr=9, v_bit=1, val=1, dir=1)
    solid = await check_against_golden(dut, 0, 1, f, bg_sel=0)
    assert solid is None, "solid background must miss this fault"
    other = await check_against_golden(dut, 0, 1, f, bg_sel=1)
    assert other is not None and other["addr"] == 9, "a 0x5555... background must expose it"
    sweep = await check_against_golden(dut, 0, 1, f, bg_sweep=1)
    assert sweep is not None and sweep["bg"] == 1, "the background sweep finds it at the first non-solid pattern"
    ck = await check_against_golden(dut, 3, 1, f, bg_sel=1)
    assert ck is not None


@cocotb.test(**only_small)
async def test_full_algorithm_and_sweep_agree_with_golden(dut):
    await init(dut)
    for f in (Fault(1, v_addr=13, v_bit=9, val=0), Fault(3, 6, 2, 7, 2, 0, 1), Fault(10, v_bit=2, val=1)):
        await check_against_golden(dut, 5, 2, f, bg_sweep=1)
    # no fault, FULL with sweep
    disarm_all(dut)
    cyc, st = await run_bist(dut, alg=5, bg_sweep=1)
    assert decode_status(st)["fail_any"] == 0
    await stop(dut)


@cocotb.test(**only_small)
async def test_retention_pause_semantics(dut):
    """A cell that decays after T cycles is caught only when the pause exceeds T."""
    await init(dut)
    T = 1000
    for decay in (1, 0):
        f = Fault(9, v_addr=9, v_bit=4, val=decay, ret_t=T)
        for faulty in (1, 2):
            disarm_all(dut)
            arm(dut, faulty, f)
            # short pause (100 cycles): the cell survives
            _, st = await run_bist(dut, alg=1, pause_mant=100, pause_exp=0, mask_sel=faulty)
            assert decode_status(st)["fail_any"] == 0, "pause shorter than the decay time must pass"
            await stop(dut)
            # long pause (250 << 4 = 4000 cycles): the cell decays
            base = dict(alg=1, pause_mant=250, pause_exp=2, mask_sel=faulty)
            await run_bist(dut, **base)
            s = await status_for(dut, faulty, base)
            assert (s["fail"] >> faulty) & 1, "pause longer than the decay time must fail"
            want_elem = 7 if decay == 1 else 8  # decays-to-1 shows in r0 (element 7), decays-to-0 in r1 (element 8)
            assert s["addr"] == 9 and s["elem"] == want_elem and s["slot"] == 0, s
            assert s["mask"] == 1 << 4
            await stop(dut)
            # March C- has no pause: the retention fault is invisible to it
            _, st = await run_bist(dut, alg=0, mask_sel=faulty)
            assert decode_status(st)["fail_any"] == 0, "March C- must not detect a retention fault"
            await stop(dut)
            # the production default (March C- then retention) catches it
            base = dict(alg=2, pause_mant=250, pause_exp=2, mask_sel=faulty)
            await run_bist(dut, **base)
            s = await status_for(dut, faulty, base)
            assert (s["fail"] >> faulty) & 1 and s["elem"] == want_elem
            await stop(dut)
    disarm_all(dut)


# ---------------------------------------------------------------------------
# SoC and CPU shapes
# ---------------------------------------------------------------------------
@cocotb.test(**only_soc)
async def test_soc_shape_full_size(dut):
    """Two 1024 x 32 macros, port 1 on memory 0: no fault, then one fault per memory including a
    port-1-visible one (port record 0b11) and a port-0-only memory (0b01)."""
    await init(dut)
    _, st = await run_bist(dut, alg=2, pause_mant=2, pause_exp=0)
    assert decode_status(st)["fail_any"] == 0
    await stop(dut)
    await check_against_golden(dut, 0, 0, Fault(1, v_addr=1023, v_bit=31, val=1))
    await check_against_golden(dut, 0, 1, Fault(2, v_addr=512, v_bit=0, dir=1))
    await check_against_golden(dut, 3, 0, Fault(5, 100, 4, 101, 4, 1, 0), bg_sel=1)
    await check_against_golden(dut, 4, 1, Fault(10, v_bit=3, val=1))
    disarm_all(dut)
    _, st = await run_bist(dut, alg=5, bg_sweep=1)
    assert decode_status(st)["fail_any"] == 0
    await stop(dut)


@cocotb.test(**only_cpu)
async def test_cpu_shape_ten_memories(dut):
    """Ten 256 x 32 memories (the cache SRAMs): no fault, then a fault in each of three memories."""
    await init(dut)
    _, st = await run_bist(dut, alg=5)
    d = decode_status(st)
    assert d["fail_any"] == 0 and d["done"]
    await stop(dut)
    for m in MEM_IDX_FAULTY:
        await check_against_golden(dut, 0, m, Fault(1, v_addr=200 + m, v_bit=m, val=m & 1))
        await check_against_golden(dut, 3, m, Fault(4, 31, 3, 32, 3, 1, 1), bg_sel=1)
    # two memories failing at once: both flags, each with its own record
    disarm_all(dut)
    arm(dut, 0, Fault(1, v_addr=3, v_bit=0, val=1))
    arm(dut, 9, Fault(1, v_addr=250, v_bit=31, val=0))
    base = dict(alg=0, mask_sel=9)
    await run_bist(dut, **base)
    s0 = await status_for(dut, 0, base)
    s9 = await status_for(dut, 9, base)
    assert (s0["fail"] & 0x201) == 0x201
    assert s0["addr"] == 3 and s9["addr"] == 250 and s9["mask"] == 1 << 31
    await stop(dut)
    disarm_all(dut)
