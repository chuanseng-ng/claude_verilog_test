"""
test_mbist_tap.py -- beads claude_verilog_test-j41m.14 / j41m.10 (DFT Stage 4): MBIST driven END TO END
through the JTAG TAP.

DUT: tb_mbist_tap = dft_ctrl (jtag_tap) + soc_mbist (CPU_PRESENT = 1: two cdc_gray_fifo crossings, two status
returns) + a core-domain controller with 2 fault-injecting memories + a CPU-domain controller with 10
fault-injecting memories (the controller that moves INTO the CPU macro in the follow-up, section 16.7).
Three unrelated clocks: TCK, core, CPU; every test runs at several ratios (suffix _cfgN).

The tester sequence is the documented one (DFT_ARCHITECTURE.md 16.5): MBIST_CTRL write, idle, poll
MBIST_STATUS, read the per-memory record by rewriting rd_sel, MBIST_CTRL write with run = 0.

What is proven (each also checked against mbist_golden.py, the independent golden model):
  * no fault: both domains done, no failure, bist_en visible; run = 0 clears it again;
  * a fault in ONE memory of each domain: only that memory's go/no-go bit fails, the record read through the
    TAP equals the golden record, the XOR mask follows mask_sel;
  * dom_core / dom_cpu select which controller runs;
  * Test-Logic-Reset (five TMS-high clocks) and trst_ni abort a running test; a functional reset leaves
    MBIST idle and does NOT restart it (rst_n_i can never start MBIST);
  * the control-word crossing (depth-2 cdc_gray_fifo): a stopped destination clock fills the FIFO, the
    overflow is reported in MBIST_STATUS bit 0 and cleared by an accepted run = 0 word; with a very fast TCK
    and a slow destination clock a word is NEVER silently lost (either the overflow flag is set or the final
    holding register equals the last word written).
"""

import random

import cocotb
from cocotb.clock import Clock
from cocotb.regression import TestFactory
from cocotb.triggers import ClockCycles, Timer
from jtag_driver import OP_MBIST_CTRL, OP_MBIST_STATUS, JtagDriver, bits_of
from mbist_golden import Fault, ctl_word, decode_status, golden_first_fail

AW = 6  # both domains
N_CORE, N_CPU = 2, 10
P1_CORE = (True, False)

# (tck_ns, core_ns, cpu_ns): unrelated, coprime-ish, and both TCK-fast and TCK-slow relative to the memories
CFGS = [(53, 10, 7), (20, 31, 13), (10, 97, 29)]


def ctl_q(dut, dom):
    x = dut.u_mbist.u_xing_core if dom == "core" else dut.u_mbist.g_cpu.u_xing_cpu
    return int(x.u_hold.ctl_q.value)


def mem(dut, dom, i):
    return dut.g_core[i].u_mem if dom == "core" else dut.g_cpu[i].u_mem


def arm(dut, dom, i, f: Fault):
    m = mem(dut, dom, i)
    m.fi_kind.value = f.kind
    m.fi_a_addr.value = f.a_addr
    m.fi_a_bit.value = f.a_bit
    m.fi_v_addr.value = f.v_addr
    m.fi_v_bit.value = f.v_bit
    m.fi_val.value = f.val
    m.fi_dir.value = f.dir
    m.fi_ret_t.value = f.ret_t


def clear_faults(dut):
    for i in range(N_CORE):
        arm(dut, "core", i, Fault())
        mem(dut, "core", i).fi_clear.value = 1
    for i in range(N_CPU):
        arm(dut, "cpu", i, Fault())
        mem(dut, "cpu", i).fi_clear.value = 1


class Tester:
    def __init__(self, dut, drv, core_clk, cpu_clk):
        self.dut, self.drv = dut, drv
        self.core_clk, self.cpu_clk = core_clk, cpu_clk

    async def write_ctl(self, **kw):
        await self.drv.write_tdr(OP_MBIST_CTRL, ctl_word(**kw), 29)

    async def read_status(self):
        await self.drv.load_ir(OP_MBIST_STATUS)
        v = await self.drv.shift_dr(0, 140)
        return {
            "ovf": v & 1,
            "present": (v >> 1) & 1,
            "core": decode_status((v >> 2) & ((1 << 69) - 1)),
            "cpu": decode_status((v >> 71) & ((1 << 69) - 1)),
        }

    async def wait_done(self, doms=("core", "cpu"), max_polls=400):
        for _ in range(max_polls):
            st = await self.read_status()
            if all(st[d]["done"] for d in doms):
                return st
        raise AssertionError("MBIST did not finish")

    async def record(self, base_kw, dom, i):
        """Select memory i for the record readout (rd_sel) with run still 1, read the status."""
        kw = dict(base_kw)
        kw["rd_sel"] = i
        await self.write_ctl(run=1, dom_core=1, dom_cpu=1, **kw)
        await ClockCycles(self.dut.clk_core_i, 4)
        st = await self.read_status()
        return st[dom]


async def setup(dut, cfg, hold_reset_cycles=6):
    tck_ns, core_ns, cpu_ns = cfg
    dut.clk_core_i.value = 0
    dut.clk_cpu_i.value = 0
    core_clk = cocotb.start_soon(Clock(dut.clk_core_i, core_ns, units="ns").start())
    cpu_clk = cocotb.start_soon(Clock(dut.clk_cpu_i, cpu_ns, units="ns").start())
    dut.scan_clk_i.value = 0
    dut.rst_core_n_i.value = 0
    dut.rst_cpu_n_i.value = 0
    drv = JtagDriver(dut.tck_i, dut.tms_i, dut.tdi_i, dut.trst_ni, dut.tdo_o,
                     period_ns=tck_ns, probe=None, name="mbist_tap")  # fmt: skip
    await drv.start(hold_reset=True)  # a real TRST_N falling edge, left low
    await ClockCycles(dut.clk_core_i, hold_reset_cycles)
    dut.rst_core_n_i.value = 1
    dut.rst_cpu_n_i.value = 1
    await drv.release_trst()
    await ClockCycles(dut.clk_core_i, 4)
    clear_faults(dut)
    await ClockCycles(dut.clk_core_i, 4)
    return Tester(dut, drv, core_clk, cpu_clk)


# ---------------------------------------------------------------------------
async def t_idle_and_readback(dut, cfg):
    """After power-up: MBIST idle, status shows cpu_present and done = 0 (an absent/stuck controller cannot
    read as a pass); MBIST_CTRL reads back what was written; trst_ni = 0 keeps everything inert."""
    t = await setup(dut, cfg)
    assert int(dut.core_bist_en_o.value) == 0 and int(dut.cpu_bist_en_o.value) == 0
    st = await t.read_status()
    assert st["present"] == 1 and st["ovf"] == 0
    assert st["core"]["done"] == 0 and st["cpu"]["done"] == 0
    assert st["core"]["fail_any"] == 0 and st["cpu"]["fail_any"] == 0
    word = ctl_word(run=0, alg=3, bg_sweep=1, bg_sel=5, pause_mant=0xA5, pause_exp=5, mask_sel=9, rd_sel=6,
                    dom_core=1, dom_cpu=1)  # fmt: skip
    await t.drv.write_tdr(OP_MBIST_CTRL, word, 29)
    await t.drv.load_ir(OP_MBIST_CTRL)
    got = await t.drv.shift_dr(word, 29)  # Capture-DR reads the update register back; the same word is shifted in
    assert got == word, f"MBIST_CTRL readback {got:#x} != written {word:#x}"
    assert int(dut.core_bist_en_o.value) == 0, "run = 0 must not start anything"
    await ClockCycles(dut.clk_core_i, 8)
    assert ctl_q(dut, "core") == word and ctl_q(dut, "cpu") == word, "holding registers follow the crossing"


async def t_no_fault_both_domains(dut, cfg):
    t = await setup(dut, cfg)
    base = dict(alg=2, pause_mant=3, pause_exp=0)
    await t.write_ctl(run=1, dom_core=1, dom_cpu=1, **base)
    st = await t.wait_done()
    for d in ("core", "cpu"):
        assert st[d]["done"] == 1 and st[d]["fail_any"] == 0 and st[d]["fail"] == 0 and st[d]["cfg_err"] == 0, st[d]
    assert int(dut.core_bist_en_o.value) == 1 and int(dut.cpu_bist_en_o.value) == 1
    await t.write_ctl(run=0, dom_core=1, dom_cpu=1)
    await ClockCycles(dut.clk_core_i, 6)
    await ClockCycles(dut.clk_cpu_i, 6)
    assert int(dut.core_bist_en_o.value) == 0 and int(dut.cpu_bist_en_o.value) == 0
    st = await t.read_status()
    assert st["core"]["done"] == 0 and st["cpu"]["done"] == 0, "run = 0 clears done"


async def t_faults_read_through_the_tap(dut, cfg):
    """One fault per domain (different memories); go/no-go bit, record and mask through the TAP == golden."""
    t = await setup(dut, cfg)
    f_core = Fault(1, v_addr=21, v_bit=9, val=1)  # SAF1 in core memory 1 (no port 1)
    f_cpu = Fault(4, a_addr=10, a_bit=2, v_addr=11, v_bit=2, val=1, dir=1)  # CFid in CPU memory 7
    f_core0 = Fault(2, v_addr=0, v_bit=0, dir=0)  # TF in core memory 0 (port 1 present)
    arm(dut, "core", 1, f_core)
    arm(dut, "cpu", 7, f_cpu)
    arm(dut, "core", 0, f_core0)
    base = dict(alg=0, mask_sel=1)
    await t.write_ctl(run=1, dom_core=1, dom_cpu=1, **base)
    st = await t.wait_done()
    assert st["core"]["fail"] == 0b11 and st["cpu"]["fail"] == 1 << 7, (st["core"]["fail"], st["cpu"]["fail"])
    assert st["core"]["fail_any"] == 1 and st["cpu"]["fail_any"] == 1
    cases = [("core", 1, f_core, False), ("core", 0, f_core0, True), ("cpu", 7, f_cpu, False)]
    for dom, i, f, p1 in cases:
        exp = golden_first_fail(0, AW, p1, f)
        rec = await t.record(base, dom, i)
        for k in ("addr", "elem", "slot", "bg", "port"):
            assert rec[k] == exp[k], f"{dom} mem {i} {f.label()}: {k} TAP {rec[k]} golden {exp[k]}"
    # mask_sel = 1 -> the XOR mask is that of memory 1 of each domain (core: the SAF; cpu: memory 1 is clean -> 0)
    rec = await t.record(base, "core", 1)
    assert rec["mask"] == golden_first_fail(0, AW, False, f_core)["mask"] == 1 << 9
    rec = await t.record(base, "cpu", 1)
    assert rec["mask"] == 0 and not (rec["fail"] >> 1) & 1
    await t.write_ctl(run=0)
    clear_faults(dut)


async def t_domain_select(dut, cfg):
    t = await setup(dut, cfg)
    await t.write_ctl(run=1, dom_core=1, dom_cpu=0, alg=0)
    st = await t.wait_done(("core",))
    assert st["core"]["done"] == 1
    await ClockCycles(dut.clk_cpu_i, 200)
    st = await t.read_status()
    assert st["cpu"]["done"] == 0 and int(dut.cpu_bist_en_o.value) == 0, "dom_cpu = 0: CPU controller must not run"
    await t.write_ctl(run=0)
    await t.write_ctl(run=1, dom_core=0, dom_cpu=1, alg=0)
    st = await t.wait_done(("cpu",))
    assert st["cpu"]["done"] == 1 and int(dut.core_bist_en_o.value) == 0, "dom_core = 0: core controller must not run"
    await t.write_ctl(run=0)


async def t_tlr_and_trst_abort_a_running_test(dut, cfg):
    t = await setup(dut, cfg)
    await t.write_ctl(run=1, dom_core=1, dom_cpu=1, alg=5, bg_sweep=1)
    await ClockCycles(dut.clk_core_i, 200)
    assert int(dut.core_bist_en_o.value) == 1 and int(dut.cpu_bist_en_o.value) == 1, "precondition: running"
    # five TMS-high clocks: the TAP enters Test-Logic-Reset and writes the default word (run = 0)
    await t.drv.reset_tms()
    await ClockCycles(dut.clk_core_i, 12)
    await ClockCycles(dut.clk_cpu_i, 12)
    assert int(dut.core_bist_en_o.value) == 0 and int(dut.cpu_bist_en_o.value) == 0, "TLR must abort MBIST"
    st = await t.read_status()
    assert st["core"]["done"] == 0 and st["cpu"]["done"] == 0
    # restart, then abort by TRST
    await t.write_ctl(run=1, dom_core=1, dom_cpu=1, alg=5, bg_sweep=1)
    await ClockCycles(dut.clk_core_i, 200)
    assert int(dut.core_bist_en_o.value) == 1
    await t.drv.assert_trst()
    await ClockCycles(dut.clk_core_i, 6)
    await ClockCycles(dut.clk_cpu_i, 6)
    assert int(dut.core_bist_en_o.value) == 0 and int(dut.cpu_bist_en_o.value) == 0, "trst_ni must abort MBIST"
    await t.drv.release_trst()
    await ClockCycles(dut.clk_core_i, 100)
    assert int(dut.core_bist_en_o.value) == 0 and int(dut.cpu_bist_en_o.value) == 0, "no phantom restart"
    assert ctl_q(dut, "core") == 0 and ctl_q(dut, "cpu") == 0


async def t_functional_reset_does_not_restart(dut, cfg):
    t = await setup(dut, cfg)
    await t.write_ctl(run=1, dom_core=1, dom_cpu=1, alg=5, bg_sweep=1)
    await ClockCycles(dut.clk_core_i, 150)
    assert int(dut.core_bist_en_o.value) == 1
    dut.rst_core_n_i.value = 0
    dut.rst_cpu_n_i.value = 0
    await ClockCycles(dut.clk_core_i, 6)
    await ClockCycles(dut.clk_cpu_i, 6)
    assert int(dut.core_bist_en_o.value) == 0 and int(dut.cpu_bist_en_o.value) == 0
    dut.rst_core_n_i.value = 1
    dut.rst_cpu_n_i.value = 1
    await ClockCycles(dut.clk_core_i, 300)
    assert int(dut.core_bist_en_o.value) == 0 and int(dut.cpu_bist_en_o.value) == 0, (
        "a functional reset must leave MBIST idle and must not restart it"
    )
    # the TAP register still holds run = 1 (readback); the tester has to rewrite it
    await t.drv.load_ir(OP_MBIST_CTRL)
    want = ctl_word(run=1, dom_core=1, dom_cpu=1, alg=5, bg_sweep=1)
    got = await t.drv.shift_dr(ctl_word(run=0), 29)  # readback, and write run = 0 (the tester's abort word)
    assert got == want, "the TAP register keeps run = 1 across a functional reset"
    st = await t.read_status()
    assert st["core"]["done"] == 0
    await t.write_ctl(run=0)
    await t.write_ctl(run=1, dom_core=1, dom_cpu=1, alg=0)
    st = await t.wait_done()
    assert st["core"]["fail_any"] == 0 and st["cpu"]["fail_any"] == 0, "MBIST works again after the reset"
    await t.write_ctl(run=0)


async def t_overflow_is_reported_and_cleared(dut, cfg):
    t = await setup(dut, cfg)
    # the Test-Logic-Reset default word written at power-up occupies a FIFO slot until the destination clock
    # has read it; let it drain first so exactly two slots are free
    await ClockCycles(dut.clk_core_i, 40)
    # ... and the write side only SEES the freed slot after the read pointer has crossed back into the TCK
    # domain, which needs TCK edges (tester rule: keep TCK running in Run-Test/Idle)
    await t.drv.walk([0] * 8)
    t.core_clk.kill()  # destination clock of the core FIFO stops
    dut.clk_core_i.value = 0
    await ClockCycles(dut.clk_cpu_i, 4)
    w = [ctl_word(run=1, alg=0, dom_core=1, dom_cpu=0),
         ctl_word(run=1, alg=1, dom_core=1, dom_cpu=0),
         ctl_word(run=1, alg=2, dom_core=1, dom_cpu=0)]  # fmt: skip
    for x in w:
        await t.drv.write_tdr(OP_MBIST_CTRL, x, 29)
    st = await t.read_status()
    assert st["ovf"] == 1, "a third write into a full 2-entry FIFO with a stopped reader must set the flag"
    t.core_clk = cocotb.start_soon(Clock(dut.clk_core_i, cfg[1], units="ns").start())
    await ClockCycles(dut.clk_core_i, 40)
    assert ctl_q(dut, "core") == w[1], "the two accepted words arrive in order; the third was lost (and reported)"
    st = await t.read_status()
    assert st["ovf"] == 1, "the flag is sticky"
    await t.write_ctl(run=0, dom_core=1, dom_cpu=1)  # an accepted run = 0 word clears it
    st = await t.read_status()
    assert st["ovf"] == 0, "an accepted run = 0 word clears the overflow flag"


async def t_control_word_never_silently_lost(dut, cfg):
    """Random run = 0 words back to back: either the overflow flag is set, or the holding registers equal
    the last word written. (cfg 3 is TCK 10 ns against a 97 ns destination clock: the case that overflows.)"""
    t = await setup(dut, cfg)
    rng = random.Random(0xD00D + cfg[0])
    lost_seen = 0
    for rnd in range(40):
        n = rng.randrange(1, 5)
        last = None
        for _ in range(n):
            last = ctl_word(run=0, alg=rng.randrange(8), bg_sweep=rng.getrandbits(1), bg_sel=rng.randrange(8),
                            pause_mant=rng.getrandbits(8), pause_exp=rng.randrange(8), mask_sel=rng.randrange(16),
                            rd_sel=rng.randrange(16), dom_core=rng.getrandbits(1), dom_cpu=rng.getrandbits(1))  # fmt: skip
            await t.drv.write_tdr(OP_MBIST_CTRL, last, 29)
        await ClockCycles(dut.clk_core_i, 8)
        await ClockCycles(dut.clk_cpu_i, 8)
        st = await t.read_status()
        # run = 0 is always an accepted-and-clearing word when accepted, so the flag can only be 1 if a
        # LATER word in this burst was lost after an earlier loss; check the invariant either way
        if st["ovf"] == 0:
            assert ctl_q(dut, "core") == last and ctl_q(dut, "cpu") == last, (
                f"round {rnd}: no overflow reported but holding registers {ctl_q(dut, 'core'):#x}/"
                f"{ctl_q(dut, 'cpu'):#x} != last word {last:#x}"
            )
        else:
            lost_seen += 1
    dut._log.info(f"cfg {cfg}: {lost_seen}/40 bursts reported an overflow")


for _fn in (
    t_idle_and_readback,
    t_no_fault_both_domains,
    t_faults_read_through_the_tap,
    t_domain_select,
    t_tlr_and_trst_abort_a_running_test,
    t_functional_reset_does_not_restart,
    t_overflow_is_reported_and_cleared,
    t_control_word_never_silently_lost,
):
    _fn.__name__ = _fn.__qualname__ = "test_" + _fn.__name__[2:]
    _tf = TestFactory(_fn)
    _tf.add_option("cfg", CFGS)
    _tf.generate_tests(postfix="_cfg")
