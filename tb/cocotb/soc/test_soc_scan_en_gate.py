"""
test_soc_scan_en_gate.py -- bead claude_verilog_test-j41m.17 (epic j41m, GH #244), SoC level.

DUT: tb_soc_pll -> soc_top (PLL_IMPL=STUB), the same wrapper test_soc_dft_scan / test_soc_jtag use.

THE PROPERTY UNDER TEST (docs/design/DFT_ARCHITECTURE.md 14.14)
  crypto_accel zeroizes its key and state on every scan_mode edge through functional D logic, and a
  scan mux sits AFTER that logic, so an edge with scan_en = 1 would load scan_in over the cleared
  value. soc_top therefore gates the shift enable:

      dft_scan_en = dft_scan_en_req & crypto_wipe_done
      (crypto_wipe_done = u_crypto.scan_wipe_done_o)

  scan_wipe_done_o falls combinationally when scan_mode changes and rises just after the third
  clock edge (the edge at which the wipe_w-qualified clears take effect). The net named dft_scan_en
  still feeds the CPU macro (scan_en_i) and the Stage 2 SE pins.

WHAT "NO KEY-DERIVED BIT REACHES scan_out" MEANS HERE
  The RTL has no scan flops before Stage 2 insertion (scan_out_o is tied 0), so the property is
  modelled, not observed on a pin. A scan flop shifts its Q out at the first edge with scan_en = 1,
  and a chain's last flop already shows its Q on scan_out before that edge. So the value a scan flop
  would shift out at the FIRST shift edge is the flop's value at the instant dft_scan_en first
  rises, and every test below samples every scanned crypto flop class at that instant (and at every
  later sample with dft_scan_en = 1) and requires 0. key_q and rk_q are excluded from the chains
  and masked on their read side; they are sampled too (they must read 0 as wiped, and the masked
  read nets must be 0). The residue is DEPOSITED (fresh random values per run, so a stale register
  can never produce a false pass) except in test_gate_after_real_firmware_run, where the residue
  comes from CPU firmware that runs a real AES and SHA-256 operation over the bus.

TIMELINE (edge k = k-th rising edge of the test clock after the scan_mode change)
    scan_mode rises  done 1 -> 0 at once, dft_scan_en -> 0 at once (no clock needed)
    edges 1, 2       capture-type: done 0, dft_scan_en 0 even if the tester holds scan_en_i
    edge 3           clears take effect; done 0 -> 1 right after it, dft_scan_en rises with it
    edge 4           FIRST EDGE THAT CAN SHIFT (the protocol keeps scan_en low through edge 4 as a
                     spare; the hardware guarantee is only "no shift before edge 4")

Tests
  test_gate_withholds_scan_en_until_wipe_applied[_en_first]
        pin mode, adversarial tester (scan_en_i raised together with / before scan_mode_i)
  test_no_residue_visible_when_scan_en_first_rises   5 random keys, every class sampled
  test_gate_after_real_firmware_run                  residue from a real AES + SHA run by firmware
  test_tap_serial_direct_shift_is_capture_until_wipe_applied
  test_tap_serial_documented_protocol_shifts
  test_done_and_scan_en_change_once_at_the_right_edge
  test_short_scan_mode_pulse_keeps_done_low_until_pipeline_flushes
  test_scan_exit_withholds_scan_en
  test_scan_reset_does_not_fake_or_hide_done
  test_functional_reset_leaves_done_high_after_three_edges
  test_functional_mode_is_a_pass_through

Verilator is two-state and zero-delay: "glitch free" below means "no change at any simulation
timestep other than the legitimate one", which is all a zero-delay model can show. The real
glitch argument is the monotonic NOR of 14.14 item 4 plus the netlist STA; neither is claimed here.
"""

import random
import sys
from pathlib import Path

import cocotb
from cocotb.triggers import Edge, Timer
from cocotb.utils import get_sim_time
from common.hier import hsub
from jtag_driver import JtagDriver
from soc_clocks import drive_dft_inactive

_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from tb.cocotb.soc.crypto_fw.crypto_fw_addrs import FAIL_PC, PASS_PC  # noqa: E402

LOCK_CYCLES = 16  # STUB_LOCK_CYCLES in soc_top
HALF_NS = 5
FW_HEX = Path(__file__).parent / "crypto_fw" / "crypto_fw.hex"
FW_TIMEOUT_CYCLES = 120_000

# Bank word indices inside crypto_accel's apb4_register_bank (crypto_accel.sv register map).
IV_WORDS = range(6, 10)
DOUT_WORDS = range(14, 18)
DIGEST_WORDS = range(18, 26)

# Classes that must hold residue just before edge 3 (the others are refreshed by the idle
# pre-load or are FSM state that is idle by construction).
RESIDUE_REQUIRED = (
    "key_q",
    "key_seen_q",
    "msg_q",
    "ctr_op_q",
    "sha.hin_q",
    "sha.a_q",
    "sha.e_q",
    "sha.w_q[0]",
    "sha.w_q[15]",
    "DOUT0",
    "DOUT3",
    "DIGEST0",
    "DIGEST7",
    "IV0",
    "IV3",
)


# ---------------------------------------------------------------------------
# Plain-timer clocking and sampling helpers (no Clock() tasks: nothing can leak between tests)
# ---------------------------------------------------------------------------
async def _fclk(dut, n: int) -> None:
    """n functional clock cycles on clk_i and cpu_clk_i."""
    for _ in range(n):
        dut.clk_i.value = 1
        dut.cpu_clk_i.value = 1
        await Timer(HALF_NS, units="ns")
        dut.clk_i.value = 0
        dut.cpu_clk_i.value = 0
        await Timer(HALF_NS, units="ns")


def _flop_classes(soc) -> dict[str, int]:
    """Every scanned key-, message- and result-derived flop class of crypto_accel (the classes the
    scan-entry wipe clears), plus the two masked ones (key_q, rk_q) and the masked read nets."""
    cr = soc.u_crypto
    aes_c = hsub(cr, "g_aes", "u_aes")
    sha_c = hsub(cr, "g_sha", "u_sha")
    regs = cr.u_regbank.regs
    out = {
        "key_q": int(cr.key_q.value),
        "key_seen_q": int(cr.key_seen_q.value),
        "msg_q": int(cr.msg_q.value),
        "ctr_op_q": int(cr.ctr_op_q.value),
        "aes.s_q": int(aes_c.s_q.value),
        "aes.rk_q": int(aes_c.rk_q.value),
        "aes.state_q": int(aes_c.state_q.value),
        "sha.hin_q": int(sha_c.hin_q.value),
        "sha.t_q": int(sha_c.t_q.value),
        "sha.state_q": int(sha_c.state_q.value),
    }
    for nm in "abcdefgh":
        out[f"sha.{nm}_q"] = int(getattr(sha_c, f"{nm}_q").value)
    for j in range(16):
        out[f"sha.w_q[{j}]"] = int(sha_c.w_q[j].value)
    for i, w in enumerate(DOUT_WORDS):
        out[f"DOUT{i}"] = int(regs[w].value)
    for i, w in enumerate(DIGEST_WORDS):
        out[f"DIGEST{i}"] = int(regs[w].value)
    for i, w in enumerate(IV_WORDS):
        out[f"IV{i}"] = int(regs[w].value)
    return out


def _nonzero(classes: dict[str, int]) -> dict[str, str]:
    return {k: hex(v) for k, v in classes.items() if v}


def _snap(dut) -> dict:
    """One sample of the gate nets and (lazily) every wiped flop class."""
    soc = dut.u_soc
    return {
        "mode": int(soc.dft_scan_mode.value),
        "req": int(soc.dft_scan_en_req.value),
        "done": int(soc.crypto_wipe_done.value),
        "en": int(soc.dft_scan_en.value),
        "macro_en": int(soc.u_cpu.scan_en_i.value),
        "wipe_w": int(soc.u_crypto.wipe_w.value),
        "classes": _flop_classes(soc),
        "t": int(get_sim_time("ps")),
    }


def _check_always(s: dict, where: str) -> None:
    """Invariants that hold at EVERY sample, whatever the tester does."""
    assert s["en"] == (s["req"] & s["done"]), f"{where}: dft_scan_en != req & wipe_done: {s}"
    assert s["macro_en"] == s["en"], (
        f"{where}: CPU macro scan_en_i={s['macro_en']} follows neither the gated net "
        f"dft_scan_en={s['en']} (req={s['req']})"
    )
    if s["en"]:
        live = _nonzero(s["classes"])
        assert not live, f"{where}: dft_scan_en = 1 while wiped flop classes hold {live}"


class _Log:
    """Every change of the watched signals with its simulation time, plus the rise times of the
    clock handles given. Start before the stimulus."""

    def __init__(self, sigs: dict, clocks: dict):
        self.sigs, self.clocks = sigs, clocks
        self.events = []  # (name, t_ps, old, new)
        self.rises = {n: [] for n in clocks}
        self._tasks = []

    async def _watch(self, name, sig):
        prev = int(sig.value)
        while True:
            await Edge(sig)
            new = int(sig.value)
            self.events.append((name, int(get_sim_time("ps")), prev, new))
            prev = new

    async def _watch_clk(self, name, sig):
        prev = int(sig.value)
        while True:
            await Edge(sig)
            new = int(sig.value)
            if new and not prev:
                self.rises[name].append(int(get_sim_time("ps")))
            prev = new

    def start(self):
        for n, s in self.sigs.items():
            self._tasks.append(cocotb.start_soon(self._watch(n, s)))
        for n, s in self.clocks.items():
            self._tasks.append(cocotb.start_soon(self._watch_clk(n, s)))
        return self

    def stop(self):
        for t in self._tasks:
            t.kill()
        self._tasks = []

    def of(self, name):
        return [e for e in self.events if e[0] == name]


# ---------------------------------------------------------------------------
# Bench bring-up and residue
# ---------------------------------------------------------------------------
async def _functional_baseline(dut, flush_edges: int = 8) -> None:
    """Known functional state: TAP held in reset, scan ports inactive, functional reset, PLL
    locked, and enough functional clocks that the crypto edge-detect pipeline has flushed. Every
    test starts here, because the simulator process is shared between tests and the pipeline
    flops are deliberately unreset (a test that inherits the previous test's scan_mode history
    sees a different done)."""
    drive_dft_inactive(dut)
    dut.clk_i.value = 0
    dut.cpu_clk_i.value = 0
    dut.rst_n_i.value = 0
    dut.cpu_rst_n_i.value = 0
    for name in ("apb_psel_i", "apb_penable_i", "apb_pwrite_i", "uart_rx_i", "spi_miso_i"):
        getattr(dut, name).value = 0
    dut.apb_paddr_i.value = 0
    dut.apb_pwdata_i.value = 0
    await Timer(2, units="ns")
    await _fclk(dut, 4)
    dut.rst_n_i.value = 1
    dut.cpu_rst_n_i.value = 1
    await _fclk(dut, LOCK_CYCLES + 6 + flush_edges)
    soc = dut.u_soc
    assert int(dut.pll_locked_o.value) == 1, "baseline: PLL did not lock"
    assert int(soc.crypto_wipe_done.value) == 1, (
        "baseline: done must be 1 in settled functional mode"
    )
    assert int(soc.dft_scan_mode.value) == 0


def _seed(soc, rng: random.Random) -> None:
    """Deposit fresh random non-zero residue on every scanned class (clocks parked, so nothing
    refreshes it before the test clock runs)."""
    cr = soc.u_crypto
    aes_c = hsub(cr, "g_aes", "u_aes")
    sha_c = hsub(cr, "g_sha", "u_sha")
    regs = cr.u_regbank.regs

    def rnd(bits: int) -> int:
        return rng.getrandbits(bits) | (1 << rng.randrange(bits))  # never all-zero

    cr.key_q.value = rnd(128)
    cr.key_seen_q.value = 0xF
    cr.msg_q.value = rnd(512)
    cr.ctr_op_q.value = 1
    aes_c.s_q.value = rnd(128)
    aes_c.rk_q.value = rnd(128)
    sha_c.hin_q.value = rnd(256)
    for nm in "abcdefgh":
        getattr(sha_c, f"{nm}_q").value = rnd(32)
    for j in range(16):
        sha_c.w_q[j].value = rnd(32)
    for w in (*IV_WORDS, *DOUT_WORDS, *DIGEST_WORDS):
        regs[w].value = rnd(32)


def _assert_residue_present(classes: dict[str, int], where: str) -> None:
    for name in RESIDUE_REQUIRED:
        assert classes[name] != 0, f"{where}: precondition, {name} must hold residue"


async def _prepare_pin_entry(dut, rng: random.Random) -> None:
    """Functional baseline, residue seeded, functional clocks parked low, test clock parked low."""
    await _functional_baseline(dut)
    dut.clk_i.value = 0
    dut.cpu_clk_i.value = 0
    dut.scan_clk_i.value = 0
    _seed(dut.u_soc, rng)
    await Timer(1, units="ns")
    _assert_residue_present(_flop_classes(dut.u_soc), "before scan entry")


async def _test_cycle(dut, k: int, samples: list) -> None:
    """One scan_clk_i cycle; appends the post-rise sample (k, 'high') and the post-fall sample."""
    dut.scan_clk_i.value = 1
    await Timer(1, units="ns")
    samples.append((k, "high", _snap(dut)))
    await Timer(HALF_NS - 1, units="ns")
    dut.scan_clk_i.value = 0
    await Timer(1, units="ns")
    samples.append((k, "low", _snap(dut)))
    await Timer(HALF_NS - 1, units="ns")


async def _pin_entry(dut, variant: str, n_edges: int) -> list:
    """Adversarial pin-mode entry: scan_en_i is held 1 from the start (together with, or before,
    scan_mode_i) and the test clock runs. Returns [(k, phase, snap)] with k = test-clock edges
    applied so far (k = 0 is the sample right after scan_mode rose, before any edge)."""
    samples = []
    if variant == "together":
        dut.scan_en_i.value = 1
        dut.scan_mode_i.value = 1
    elif variant == "en_first":
        dut.scan_en_i.value = 1
        await Timer(1, units="ns")
        s = _snap(dut)
        # Outside the 14.1 contract (scan_en with scan_mode = 0); pass-through is expected.
        assert s["done"] == 1 and s["en"] == 1, f"functional pass-through of scan_en_i: {s}"
        dut.scan_mode_i.value = 1
    else:
        raise AssertionError(variant)
    await Timer(1, units="ns")  # no clock edge yet: the combinational path alone
    samples.append((0, "pre", _snap(dut)))
    for k in range(1, n_edges + 1):
        await _test_cycle(dut, k, samples)
    return samples


def _check_entry_timeline(samples: list, label: str) -> None:
    """The contract, sample by sample (see the module docstring TIMELINE)."""
    for k, ph, s in samples:
        where = f"{label} k={k} {ph}"
        _check_always(s, where)
        assert s["req"] == 1, f"{where}: the adversarial tester holds scan_en, req must be 1"
        assert s["mode"] == 1
        if k < 3:
            assert s["done"] == 0 and s["en"] == 0, (
                f"{where}: shift enable leaked before edge 3: {s}"
            )
        else:
            assert s["done"] == 1 and s["en"] == 1, (
                f"{where}: wipe applied but scan_en withheld: {s}"
            )
    # Non-vacuity: residue really was there up to the last pre-clearing sample, and the gate (not
    # the absence of a request) is what kept en low.
    k2 = [s for k, ph, s in samples if (k, ph) == (2, "low")][0]
    _assert_residue_present(k2["classes"], f"{label} just before edge 3")
    assert k2["req"] == 1 and k2["en"] == 0
    k3 = [s for k, ph, s in samples if (k, ph) == (3, "high")][0]
    assert not _nonzero(k3["classes"]), f"{label}: classes not zero at the first en=1 sample"


# ---------------------------------------------------------------------------
# 1. Gate holds scan_en off (pin mode)
# ---------------------------------------------------------------------------
@cocotb.test()
async def test_gate_withholds_scan_en_until_wipe_applied(dut):
    """Key, message, SHA state and result words are non-zero; scan_en_i rises TOGETHER with
    scan_mode_i and the tester clocks at once. done falls before any edge, dft_scan_en (and the CPU
    macro's scan_en_i) stays 0 through edges 1-3, rises right after edge 3 while scan_en_i is still
    1, and is never 1 on a sample in which any wiped flop class is non-zero.
    MUTATION TARGET: dft_scan_en = dft_scan_en_req (gate removed); done tied 1."""
    await _prepare_pin_entry(dut, random.Random(0x17A))
    samples = await _pin_entry(dut, "together", 8)
    pre = samples[0][2]
    assert pre["done"] == 0 and pre["en"] == 0 and pre["req"] == 1, (
        f"done must fall combinationally when scan_mode rises, before edge 1: {pre}"
    )
    _check_entry_timeline(samples, "together")


@cocotb.test()
async def test_gate_withholds_scan_en_until_wipe_applied_en_first(dut):
    """Same, but scan_en_i is raised BEFORE scan_mode_i (outside the 14.1 contract, the worse
    ordering for a gate): dft_scan_en is 1 in functional mode (pass-through, no wipe pending), falls
    when scan_mode rises and stays 0 until edge 3.
    MUTATION TARGET: gate removed; raw scan_mode term dropped from done (edge-1 window)."""
    await _prepare_pin_entry(dut, random.Random(0x17B))
    samples = await _pin_entry(dut, "en_first", 8)
    pre = samples[0][2]
    assert pre["done"] == 0 and pre["en"] == 0 and pre["req"] == 1, pre
    _check_entry_timeline(samples, "en_first")


# ---------------------------------------------------------------------------
# 2. No key-derived bit reaches scan_out (modelled: values at the first shift edge)
# ---------------------------------------------------------------------------
@cocotb.test()
async def test_no_residue_visible_when_scan_en_first_rises(dut):
    """Five runs, a fresh random key / message / state each. At the instant dft_scan_en first
    rises, which is the value every scanned flop would shift out at the first shift edge (and the
    value a chain's last flop already shows on scan_out), every scanned class is 0 and the masked
    key read nets key_eff / rk_eff are 0. Before that instant no sample has dft_scan_en = 1. The
    residue differs between runs and is non-zero before the wipe, so a stale register cannot pass.
    MUTATION TARGET: gate removed (en high while the classes are non-zero); a class not wiped."""
    rng = random.Random(0x5EC)
    seen_keys = set()
    for run in range(5):
        await _prepare_pin_entry(dut, rng)
        soc = dut.u_soc
        key_before = int(soc.u_crypto.key_q.value)
        assert key_before not in seen_keys, "run reused a key: the false-pass guard is void"
        seen_keys.add(key_before)
        samples = await _pin_entry(dut, "together", 6)
        first_en = None
        for idx, (k, ph, s) in enumerate(samples):
            if s["en"] and first_en is None:
                first_en = idx
            if first_en is None:
                assert s["en"] == 0
        assert first_en is not None, f"run {run}: dft_scan_en never rose"
        k, ph, s = samples[first_en]
        assert (k, ph) == (3, "high"), (
            f"run {run}: first en=1 sample is k={k} {ph}, expected 3 high"
        )
        assert not _nonzero(s["classes"]), (
            f"run {run}: residue at the first shift edge: {_nonzero(s['classes'])}"
        )
        assert int(soc.u_crypto.key_eff_w.value) == 0, "masked key read net must be 0 in scan mode"
        assert int(hsub(soc.u_crypto, "g_aes", "u_aes").rk_eff_w.value) == 0
        for k, ph, s in samples[first_en:]:
            assert not _nonzero(s["classes"]), f"run {run} k={k} {ph}: {_nonzero(s['classes'])}"
        # leave scan mode for the next run (functional baseline re-establishes everything)
        dut.scan_en_i.value = 0
        dut.scan_mode_i.value = 0


@cocotb.test()
async def test_gate_after_real_firmware_run(dut):
    """Residue left by CPU firmware that really runs AES (polled + interrupt driven) and SHA-256
    over the bus (crypto_fw, the test_soc_crypto image): functional mode keeps dft_scan_en = 0 and
    done = 1 on every cycle of the run, then an adversarial pin entry is held off exactly as with
    deposited residue and every class is 0 when dft_scan_en first rises.
    MUTATION TARGET: gate removed."""
    drive_dft_inactive(dut)
    words = []
    for line in FW_HEX.read_text().splitlines():
        tok = line.strip()
        if tok and not tok.startswith(("//", "@")):
            words.append(int(tok, 16))
    mem = dut.u_soc.u_boot_rom.mem
    assert len(words) <= len(mem)
    for i, w in enumerate(words):
        mem[i].value = w
    dut.clk_i.value = 0
    dut.cpu_clk_i.value = 0
    dut.rst_n_i.value = 0
    dut.cpu_rst_n_i.value = 0
    for name in ("apb_psel_i", "apb_penable_i", "apb_pwrite_i", "uart_rx_i", "spi_miso_i"):
        getattr(dut, name).value = 0
    dut.apb_paddr_i.value = 0
    dut.apb_pwdata_i.value = 0
    dut.uart_rx_i.value = 1
    await Timer(2, units="ns")
    await _fclk(dut, 5)
    dut.rst_n_i.value = 1
    dut.cpu_rst_n_i.value = 1
    soc = dut.u_soc
    reached = False
    for cyc in range(FW_TIMEOUT_CYCLES):
        await _fclk(dut, 1)
        if int(soc.crypto_wipe_done.value) != 1 or int(soc.dft_scan_en.value) != 0:
            raise AssertionError(
                f"functional mode, cycle {cyc}: done={int(soc.crypto_wipe_done.value)} "
                f"dft_scan_en={int(soc.dft_scan_en.value)}"
            )
        if int(dut.commit_valid_o.value):
            pc = int(dut.commit_pc_o.value)
            assert pc != FAIL_PC, "crypto firmware reached FAIL_PC"
            if pc == PASS_PC:
                reached = True
                break
    assert reached, "crypto firmware never reached PASS_PC"
    await _fclk(dut, 8)  # let the idle pre-load settle; still functional
    classes = _flop_classes(soc)
    for name in ("key_q", "msg_q", "sha.hin_q", "DOUT0", "DIGEST0", "IV0"):
        assert classes[name] != 0, f"firmware run left no residue in {name}"
    dut.clk_i.value = 0
    dut.cpu_clk_i.value = 0
    dut.scan_clk_i.value = 0
    await Timer(1, units="ns")
    samples = await _pin_entry(dut, "together", 6)
    for k, ph, s in samples:
        _check_always(s, f"firmware k={k} {ph}")
        if k < 3:
            assert s["en"] == 0 and s["done"] == 0
    k2 = [s for k, ph, s in samples if (k, ph) == (2, "low")][0]
    assert _nonzero(k2["classes"]), "no residue left just before the clearing edge"
    k3 = [s for k, ph, s in samples if (k, ph) == (3, "high")][0]
    assert k3["en"] == 1 and k3["done"] == 1 and not _nonzero(k3["classes"])
    dut.scan_en_i.value = 0
    dut.scan_mode_i.value = 0


# ---------------------------------------------------------------------------
# 3. TAP-serial path
# ---------------------------------------------------------------------------
def _tap(dut, name):
    return JtagDriver(
        dut.tck_i, dut.tms_i, dut.tdi_i, dut.trst_ni, dut.tdo_o, period_ns=11, name=name
    )


class _TestClkCount:
    """Counts rising edges of the net soc_top feeds to the core (dft_test_clk) and of the crypto
    block's own clk, from the moment it is started."""

    def __init__(self, soc):
        self.n_tclk = 0
        self.n_crypto = 0
        self._tasks = [
            cocotb.start_soon(self._w(soc.dft_test_clk, "n_tclk")),
            cocotb.start_soon(self._w(soc.u_crypto.clk, "n_crypto")),
        ]

    async def _w(self, sig, attr):
        prev = int(sig.value)
        while True:
            await Edge(sig)
            new = int(sig.value)
            if new and not prev:
                setattr(self, attr, getattr(self, attr) + 1)
            prev = new

    def stop(self):
        for t in self._tasks:
            t.kill()


async def _prepare_tap_entry(dut, rng: random.Random):
    await _functional_baseline(dut)
    dut.clk_i.value = 0
    dut.cpu_clk_i.value = 0
    drv = _tap(dut, "scan_en_gate")
    await drv.start()
    _seed(dut.u_soc, rng)
    await Timer(1, units="ns")
    _assert_residue_present(_flop_classes(dut.u_soc), "before TAP scan entry")
    # SCAN_RST stays 0 and scan_rst_ni stays 1: resets released, so the wipe (not a reset) is what
    # clears the state.
    await drv.enter_scan(sel=0, rst=0)
    await drv.goto("RTI")
    return drv


@cocotb.test()
async def test_tap_serial_direct_shift_is_capture_until_wipe_applied(dut):
    """TAP serial entry, Capture-DR then Shift-DR at once with real data. The test clock exists
    only on TCK edges that end Capture-DR and Shift-DR, so Capture-DR is test edge 1 and the first
    two Shift-DR edges are test edges 2 and 3: scan_en is requested (req = 1) but withheld
    (dft_scan_en = 0, CPU macro scan_en_i = 0), so those Shift-DR edges are CAPTURE edges and the
    payload bits sent in them are lost. The third Shift-DR edge (test edge 4) is the first real
    shift. dft_scan_en is never 1 while a wiped class is non-zero, and the macro follows the gated
    net, not dft_scan_en_req.
    MUTATION TARGET: gate removed (en = req in Shift-DR); done tied 0 (never shifts)."""
    soc = dut.u_soc
    drv = await _prepare_tap_entry(dut, random.Random(0x7A9))
    cnt = _TestClkCount(soc)
    log = _Log(
        {"en": soc.dft_scan_en, "done": soc.crypto_wipe_done, "req": soc.dft_scan_en_req}, {}
    )
    log.start()
    s = _snap(dut)
    assert s["mode"] == 1 and s["done"] == 0 and s["en"] == 0 and s["req"] == 0, s
    assert cnt.n_tclk == 0, "no test clock outside Capture-DR/Shift-DR"
    rows = []  # (test_clk_edges_so_far, state, snap) sampled TCK-low, i.e. before the next rise
    await drv.goto("SHDR")  # SELDR, CAPDR, SHDR: the CAPDR rise is test edge 1
    rows.append((cnt.n_tclk, drv.ref.state, _snap(dut)))
    for i in range(7):  # Shift-DR edges 1..7 = test edges 2..8, payload all ones
        await drv.tick(0, 1)
        rows.append((cnt.n_tclk, drv.ref.state, _snap(dut)))
    log.stop()
    for n, st, s in rows:
        where = f"TAP direct shift: {n} test edges, state {st}"
        _check_always(s, where)
        assert st == "SHDR" and s["req"] == 1, f"{where}: req must be 1 in Shift-DR"
        if n < 3:
            assert s["en"] == 0 and s["done"] == 0, f"{where}: shift enable leaked"
            assert s["macro_en"] == 0, f"{where}: CPU macro follows the request, not the gated net"
        else:
            assert s["en"] == 1 and s["done"] == 1 and s["macro_en"] == 1
    assert rows[0][0] == 1, f"Capture-DR must be exactly test edge 1, saw {rows[0][0]}"
    capture_like = [r for r in rows if r[2]["req"] == 1 and r[2]["en"] == 0]
    assert len(capture_like) == 2, (
        f"exactly the first two Shift-DR edges must be capture edges, saw {len(capture_like)}"
    )
    assert cnt.n_tclk == cnt.n_crypto, "crypto saw a different clock than dft_test_clk"
    assert [e for e in log.of("en") if e[3] == 1] and len(log.of("en")) == 1, (
        f"dft_scan_en must rise exactly once and not fall in the run: {log.of('en')}"
    )
    await drv.walk([1, 1, 0])  # EXIT1, UPDATE, RTI
    await Timer(1, units="ns")
    s = _snap(dut)
    assert s["req"] == 0 and s["en"] == 0 and s["macro_en"] == 0, s
    cnt.stop()
    await drv.reset_tms()


async def _capture_pass(drv) -> None:
    """One Capture-DR pass (Select-DR, Capture-DR, Exit1-DR): exactly one test-clock edge."""
    await drv.goto("CAPDR")
    await drv.tick(1, 0)


@cocotb.test()
async def test_tap_serial_documented_protocol_shifts(dut):
    """The 14.14 tester protocol over TAP: three Capture-DR passes, one spare, then Shift-DR.
    After each of the first three passes scan_en is still low and done still low (the pass count is
    the test edge count); after the third done = 1; Shift-DR then raises dft_scan_en = 1 from its
    first edge, the CPU macro's scan_en_i follows the gated net, and every scanned class is 0.
    MUTATION TARGET: done tied 0 or 1'b0 at soc_top (never shifts); wrong polarity."""
    soc = dut.u_soc
    drv = await _prepare_tap_entry(dut, random.Random(0x7AA))
    cnt = _TestClkCount(soc)
    for i in range(3):
        s = _snap(dut)
        assert s["done"] == 0 and s["en"] == 0, f"before pass {i + 1}: {s}"
        assert cnt.n_tclk == i
        await _capture_pass(drv)
        assert cnt.n_tclk == i + 1, (
            f"a Capture-DR pass must be exactly one test edge, saw {cnt.n_tclk}"
        )
    await drv.goto("RTI")
    s = _snap(dut)
    _check_always(s, "after three passes")
    assert s["done"] == 1, "wipe applied after the third Capture-DR pass"
    assert s["req"] == 0 and s["en"] == 0 and s["macro_en"] == 0
    assert not _nonzero(s["classes"]), f"classes after the wipe: {_nonzero(s['classes'])}"
    await _capture_pass(drv)  # the spare
    await drv.goto("SHDR")
    s = _snap(dut)
    _check_always(s, "Shift-DR entry")
    assert s["req"] == 1 and s["done"] == 1 and s["en"] == 1 and s["macro_en"] == 1, (
        f"the protocol must reach a real shift in the first Shift-DR cycle: {s}"
    )
    for i in range(6):
        await drv.tick(0, 1)
        s = _snap(dut)
        _check_always(s, f"Shift-DR cycle {i}")
        assert s["en"] == 1 and s["macro_en"] == 1
    assert cnt.n_tclk == cnt.n_crypto
    cnt.stop()
    await drv.walk([1, 1, 0])
    await drv.reset_tms()


# ---------------------------------------------------------------------------
# 4. done / scan_en change once, at the right edge
# ---------------------------------------------------------------------------
@cocotb.test()
async def test_done_and_scan_en_change_once_at_the_right_edge(dut):
    """Pin entry with scan_en_i held: every change of done / dft_scan_en is logged at simulation
    time resolution. done falls exactly once, at the scan_mode_i change (no clock edge), and rises
    exactly once, at the third test-clock edge and not before; dft_scan_en rises exactly once, at
    the same instant, and never falls; neither net moves at any other time (no runt pulse). The
    same for the exit direction on the functional clock, where dft_scan_en (held request) is
    withheld and released by the same single edge.
    MUTATION TARGET: done rising one edge early; combinational glitching in the gate."""
    soc = dut.u_soc
    await _prepare_pin_entry(dut, random.Random(0x6C1))
    log = _Log(
        {"done": soc.crypto_wipe_done, "en": soc.dft_scan_en, "mode": soc.dft_scan_mode},
        {"scan_clk": dut.scan_clk_i, "clk": dut.clk_i},
    ).start()
    samples = await _pin_entry(dut, "together", 6)
    _check_entry_timeline(samples, "once")
    t_mode = [e[1] for e in log.of("mode")]
    assert len(t_mode) == 1
    rises = log.rises["scan_clk"]
    assert len(rises) == 6
    assert [(e[2], e[3], e[1]) for e in log.of("done")] == [(1, 0, t_mode[0]), (0, 1, rises[2])], (
        f"done events {log.of('done')}, expected fall at {t_mode[0]} and "
        f"rise at edge 3 ({rises[2]})"
    )
    assert [(e[2], e[3], e[1]) for e in log.of("en")] == [(0, 1, rises[2])], (
        f"dft_scan_en events {log.of('en')}, expected one rise at edge 3 ({rises[2]})"
    )
    # --- exit, scan_en_i still held: functional clock, edges counted from the scan_mode change
    n_before = len(log.events)
    dut.scan_mode_i.value = 0
    await Timer(1, units="ns")
    t_exit = int(get_sim_time("ps"))
    await _fclk(dut, 6)
    log.stop()
    new = log.events[n_before:]
    f_rises = [t for t in log.rises["clk"] if t >= t_exit]
    done_ev = [(e[2], e[3], e[1]) for e in new if e[0] == "done"]
    en_ev = [(e[2], e[3], e[1]) for e in new if e[0] == "en"]
    assert len(done_ev) == 2 and done_ev[0][:2] == (1, 0) and done_ev[0][2] < f_rises[0], (
        f"exit: done must fall once, before the first functional edge: {done_ev}"
    )
    assert done_ev[1] == (0, 1, f_rises[2]), (
        f"exit: done must rise once, at functional edge 3 ({f_rises[2]}): {done_ev}"
    )
    assert [(a, b) for a, b, _ in en_ev] == [(1, 0), (0, 1)] and en_ev[1][2] == f_rises[2], (
        f"exit: dft_scan_en (held request) must drop with scan_mode and return at edge 3: {en_ev}"
    )
    dut.scan_en_i.value = 0


# ---------------------------------------------------------------------------
# 5. Edge cases
# ---------------------------------------------------------------------------
async def _fedge(dut):
    """One functional cycle, returning the post-rise sample."""
    dut.clk_i.value = 1
    dut.cpu_clk_i.value = 1
    await Timer(1, units="ns")
    s = _snap(dut)
    await Timer(HALF_NS - 1, units="ns")
    dut.clk_i.value = 0
    dut.cpu_clk_i.value = 0
    await Timer(HALF_NS, units="ns")
    return s


@cocotb.test()
async def test_short_scan_mode_pulse_keeps_done_low_until_pipeline_flushes(dut):
    """scan_mode_i high for less than three clocks. One test edge, then scan_mode drops: the edge
    detect pipeline holds a pending change, so done stays low through functional edges a and b
    (wipe_w high after both, i.e. two clearing edges follow) and rises after edge c. A two-edge
    pulse likewise. Per-sample done is compared with an independent model: done = scan_mode_i
    has been constant for the last three edges.
    MUTATION TARGETS: the s1 term (pending change not yet in s2), the wipe_w term (done high while
    the clear is still to come), the raw scan_mode_i term."""
    soc = dut.u_soc
    for pulse_edges in (1, 2):
        await _prepare_pin_entry(dut, random.Random(0x5B0 + pulse_edges))
        dut.scan_mode_i.value = 1
        await Timer(1, units="ns")
        assert int(soc.crypto_wipe_done.value) == 0
        for _ in range(pulse_edges):
            tmp = []
            await _test_cycle(dut, 0, tmp)
            assert tmp[0][2]["done"] == 0 and tmp[1][2]["done"] == 0
        dut.scan_mode_i.value = 0
        await Timer(1, units="ns")
        s = _snap(dut)
        assert s["done"] == 0, (
            f"pulse {pulse_edges}: done must stay low on the drop (pending change): {s}"
        )
        assert s["en"] == 0
        # Functional edges until the pipeline has flushed. Model: constant for 3 edges + now.
        hist = [1] * pulse_edges  # mode sampled at the edges that saw it high
        dones, wipes = [], []
        for i in range(1, 6):
            s = await _fedge(dut)
            hist.append(0)
            window = hist[-3:]
            expect_done = int(len(window) == 3 and len(set(window)) == 1)
            assert s["done"] == expect_done, (
                f"pulse {pulse_edges}, functional edge {i}: done={s['done']} model={expect_done}"
            )
            dones.append(s["done"])
            wipes.append(s["wipe_w"])
        assert dones[:2] == [0, 0] and dones[2] == 1, dones
        if pulse_edges == 1:
            # (s1,s2,prev) = (0,1,0) then (0,0,1): wipe_w high after both of the first two edges.
            assert wipes[:3] == [1, 1, 0], f"wipe_w sequence after a 1-edge pulse: {wipes}"
        else:
            assert 1 in wipes[:3], wipes
        dut.scan_en_i.value = 0


@cocotb.test()
async def test_scan_exit_withholds_scan_en(dut):
    """Leaving scan mode: done goes low at once and stays low for three functional edges even
    though the tester still holds scan_en_i, so dft_scan_en is 0 for those edges (the exit wipe
    cannot be overridden either); scan-loaded residue is gone when dft_scan_en comes back. The
    held request passes through again once done is 1 (functional pass-through, the tester's own
    business outside scan mode).
    MUTATION TARGET: gate removed; exit wipe not covered by done."""
    soc = dut.u_soc
    await _prepare_pin_entry(dut, random.Random(0xE17))
    samples = await _pin_entry(dut, "together", 6)
    _check_entry_timeline(samples, "exit setup")
    _seed(soc, random.Random(0xE18))  # residue loaded while IN scan mode (the exit wipe's target)
    await Timer(1, units="ns")
    live = _snap(dut)
    assert live["en"] == 1 and _nonzero(live["classes"]), "residue seeded in scan mode"
    dut.scan_mode_i.value = 0
    await Timer(1, units="ns")
    s = _snap(dut)
    assert s["done"] == 0 and s["en"] == 0 and s["req"] == 1, f"exit: gate must close at once: {s}"
    for i in range(1, 3):
        s = await _fedge(dut)
        assert s["done"] == 0 and s["en"] == 0 and s["macro_en"] == 0, f"exit edge {i}: {s}"
    s = await _fedge(dut)
    assert s["done"] == 1 and s["en"] == 1 and not _nonzero(s["classes"]), (
        f"exit edge 3: wipe applied, request passes through: {s}"
    )
    dut.scan_en_i.value = 0


@cocotb.test()
async def test_scan_reset_does_not_fake_or_hide_done(dut):
    """scan_rst_ni pulsed inside scan mode. (a) Steady scan mode, done = 1: a reset pulse across
    several test edges neither drops done nor lifts it (the edge-detect flops are unreset), and
    dft_scan_en keeps following the request. (b) A pulse that starts after edge 1 of a fresh entry
    and ends after edge 4: done is still low at edges 1 and 2 and high from edge 3, exactly as
    without the reset.
    MUTATION TARGET: resetting the edge-detect flops (would fake an early done)."""
    soc = dut.u_soc
    # (b) first: reset pulse inside the pending window
    await _prepare_pin_entry(dut, random.Random(0x4E5))
    dut.scan_en_i.value = 1
    dut.scan_mode_i.value = 1
    await Timer(1, units="ns")
    out = []
    await _test_cycle(dut, 1, out)
    dut.scan_rst_ni.value = 0
    await Timer(1, units="ns")
    assert int(soc.core_rst_n.value) == 0, "scan_rst_ni must reset the core domain in scan mode"
    for k in (2, 3, 4):
        await _test_cycle(dut, k, out)
    dut.scan_rst_ni.value = 1
    await Timer(1, units="ns")
    for k, ph, s in out:
        where = f"reset in pending window k={k} {ph}"
        if k < 3:
            assert s["done"] == 0 and s["en"] == 0, f"{where}: {s}"
        else:
            assert s["done"] == 1 and s["en"] == 1, f"{where}: {s}"
    # (a) steady state, reset pulse
    out = []
    for k in range(5, 8):
        await _test_cycle(dut, k, out)
    dut.scan_rst_ni.value = 0
    await Timer(1, units="ns")
    for k in range(8, 12):
        await _test_cycle(dut, k, out)
    dut.scan_rst_ni.value = 1
    await Timer(1, units="ns")
    for k in range(12, 14):
        await _test_cycle(dut, k, out)
    for k, ph, s in out:
        assert s["done"] == 1 and s["en"] == 1, f"steady scan, reset pulse k={k} {ph}: {s}"
    dut.scan_en_i.value = 0
    dut.scan_mode_i.value = 0


@cocotb.test()
async def test_functional_reset_leaves_done_high_after_three_edges(dut):
    """Reset in functional mode neither fakes nor hides a pending wipe: after a 1-edge scan pulse
    the pipeline is mid-flush when the functional reset is asserted; with the reset HELD done still
    rises after three functional edges (the flops are unreset) and is still 1 after release, and
    a plain reset pulse in settled functional mode leaves done at 1 throughout.
    MUTATION TARGET: edge-detect flops reset to 0 (done not held low by the pending change)."""
    soc = dut.u_soc
    await _prepare_pin_entry(dut, random.Random(0xF00))
    dut.scan_mode_i.value = 1
    tmp = []
    await _test_cycle(dut, 1, tmp)
    dut.scan_mode_i.value = 0
    dut.rst_n_i.value = 0
    dut.cpu_rst_n_i.value = 0
    await Timer(1, units="ns")
    s = _snap(dut)
    assert s["done"] == 0, f"pending change must hold done low under reset: {s}"
    got = []
    for _ in range(5):
        got.append((await _fedge(dut))["done"])
    assert got == [0, 0, 1, 1, 1], f"done under a held functional reset: {got}"
    dut.rst_n_i.value = 1
    dut.cpu_rst_n_i.value = 1
    for _ in range(4):
        assert (await _fedge(dut))["done"] == 1
    # plain reset pulse in settled functional mode
    dut.rst_n_i.value = 0
    dut.cpu_rst_n_i.value = 0
    for _ in range(5):
        s = await _fedge(dut)
        assert s["done"] == 1 and s["en"] == s["req"]
    dut.rst_n_i.value = 1
    dut.cpu_rst_n_i.value = 1
    for _ in range(4):
        assert (await _fedge(dut))["done"] == 1
    assert soc is not None


# ---------------------------------------------------------------------------
# 6. Functional mode is a pass-through
# ---------------------------------------------------------------------------
@cocotb.test()
async def test_functional_mode_is_a_pass_through(dut):
    """Functional mode (scan_mode_i = 0, clocks running): wipe_done is a constant 1 and
    dft_scan_en equals the request on every cycle, for a random scan_en_i pattern too (outside the
    contract, but the pass-through is what the 14.14 text promises); the macro follows.
    MUTATION TARGET: done tied 0 / wrong polarity at soc_top."""
    await _functional_baseline(dut)
    rng = random.Random(0xFAC)
    for i in range(200):
        dut.scan_en_i.value = rng.getrandbits(1)
        await Timer(1, units="ns")
        s = await _fedge(dut)
        assert s["done"] == 1 and s["mode"] == 0, f"functional cycle {i}: {s}"
        assert s["en"] == s["req"] == int(dut.scan_en_i.value), f"functional cycle {i}: {s}"
        assert s["macro_en"] == s["en"]
    dut.scan_en_i.value = 0
