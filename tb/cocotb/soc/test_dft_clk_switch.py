"""
test_dft_clk_switch.py -- bead claude_verilog_test-j41m.3 (DFT Stage 1b), unit suite for
rtl/soc/dft/dft_clk_switch.sv, the glitch-free enable-before-switch test-clock selector that
replaced the plain mux `test_clk_o = serial ? tck_scan_gated : pin_test_clk` (open question Q-CLK).

DUT: tb_dft_clk_switch -> (rv32i_clock_gate making A = gated TCK) + dft_clk_switch.
    A = clk_a_o (gated TCK, idles low), B = clk_b_i (pin test clock, idles low), sel_a_i = 1 selects
    A, rst_n_i is a level (reset state: B selected, A off).  en_a_o / en_b_o expose the two internal
    enable latches.

The same suite runs against `assign clk_o = sel_a_i ? clk_a_o : clk_b_i` (parameter PLAIN_MUX=1,
make target dft_clk_switch_plainmux) as the RED negative control: it MUST fail there.

How the checking works (jtag_driver.py, "Clock-pulse analysis")
  Every scenario is a precomputed stimulus timeline (clocks, select, gate enable, reset) played
  into the DUT while an edge-time log records both source clocks, the output, the select and the
  two latches.  The checker then works on that log only, never on the RTL:
    * every output pulse must be ONE WHOLE source pulse (same rise time and same fall time): no
      runt, no truncation, no edge derived from nothing, no merge of an A and a B pulse;
    * no output high pulse and no output low gap shorter than the shortest source phase;
    * per select change: old-source pulses stop at once (the old enable drops without a clock
      edge), new-source pulses start no earlier than the 3rd edge of the handshake clock and every
      pulse from t_sw + bound on passes, none is skipped (contiguous suffix), old never returns;
    * latch discipline: en_a_q changes only while raw tck_i is low, en_b_q only while clk_b_i is
      low, and they are never both high (outside the declared async-reset merge window).
  The checker itself is proved able to fail (test_checker_*): synthetic logs with each defect, and
  a synthetic plain-mux log built from real clock waveforms.

Contract (dft_clk_switch.sv header), each point tested here, not assumed
  1. serial -> parallel (sel 1->0): en_a_q drops at once; B passes only from its 3rd rising edge
     after the select change; until then the output stays LOW with NO extra edge.  B never runs ->
     never completes (test_serial_to_parallel_waits_for_the_pin_clock).
  2. parallel -> serial (sel 0->1): B is retired with no B edge if it idles LOW; A passes from the
     3rd TCK rising edge after the select change (exactly the 3rd when B idles low,
     test_parallel_to_serial_needs_no_pin_clock_edge).  LIMITATION (flagged): B stopped HIGH can
     never complete (test_pin_clock_stopped_high_blocks_the_switch_limitation); TCK stopped never
     completes either (test_tck_stopped_...).
  3. reset (rst_n_i low) gives clk_o == clk_b_i whatever sel/A do (test_reset_state_selects_b);
     assertion in the middle of a pulse may MERGE pulses but never shorten one
     (test_reset_in_the_middle_of_pulses).
  4. dwell: a select reversal after a full handshake is safe at every phase
     (test_reversal_dwell).

Tests
  test_checker_detects_each_defect_class        vacuity guard: synthetic defective logs are flagged,
                                                the plain-mux log built from real waveforms too
  test_sweep_switching_<cfg>_<mode>             ~200 switches, both directions, both clocks
                                                free-running at coprime periods (7/11, 13/5, 29/17
                                                ns), select instants swept over the phases of both
                                                (mode arb), launched like the TAP, 1 ps after a TCK
                                                fall (tap), or with A randomly gated (gated)
  test_serial_to_parallel_waits_for_the_pin_clock
  test_parallel_to_serial_needs_no_pin_clock_edge
  test_pin_clock_stopped_high_blocks_the_switch_limitation
  test_tck_stopped_parallel_to_serial_goes_quiet_until_tck_toggles
  test_a_gated_off_and_back
  test_reset_state_selects_b
  test_reset_in_the_middle_of_pulses
  test_reversal_dwell
"""

import random

import cocotb
from cocotb.regression import TestFactory
from cocotb.triggers import Timer
from cocotb.utils import get_sim_time
from jtag_driver import (
    EdgeLog,
    check_enable_latches,
    check_handover,
    events_of,
    label_output_pulses,
    level_at,
    pulses_of,
)

TA_DEFAULT, TB_DEFAULT = 11000, 7000
CFGS = [(7, 11), (13, 5), (29, 17)]  # (TCK period, B period) in ns, coprime pairs
MODES = ["arb", "tap", "gated"]
N_SWITCH = 200
TOL = 3  # ps: a select/reset/gate change is never placed within TOL ps of a clock edge


# ---------------------------------------------------------------------------
# stimulus timeline
# ---------------------------------------------------------------------------
class Plan:
    """Absolute-time stimulus: a list of (t_ps, signal, value), played by play()."""

    def __init__(self, base):
        self.base = base
        self.ev = []

    def at(self, t, sig, val):
        self.ev.append((int(t), len(self.ev), sig, int(val)))

    def clock(self, sig, period, phase, t0, t1):
        """50 % duty clock: rises at t0 + phase + m*period while the rise is < t1.  Returns the
        list of (rise, fall) times."""
        out, t = [], t0 + phase
        while t < t1:
            self.at(t, sig, 1)
            self.at(t + period // 2, sig, 0)
            out.append((t, t + period // 2))
            t += period
        return out

    def end(self):
        return max(e[0] for e in self.ev)


async def play(dut, plan):
    """Apply the timeline.  Events at the same ps are applied in the order they were added."""
    now = int(get_sim_time("ps"))
    ev = sorted(plan.ev)
    i = 0
    while i < len(ev):
        t = ev[i][0]
        assert t >= now, f"timeline event at {t} ps is in the past (now {now} ps)"
        if t > now:
            await Timer(t - now, "ps")
            now = t
        while i < len(ev) and ev[i][0] == t:
            getattr(dut, ev[i][2]).value = ev[i][3]
            i += 1


def _near(t, period, phase, tol=TOL):
    """True if t is within tol ps of an edge of a 50 % clock with rises at phase + m*period."""
    h = period // 2
    r = (t - phase) % h
    return min(r, h - r) <= tol


async def prep(dut, a_en=1):
    """Everything idle, reset asserted, A gate open.  Returns the timeline base (ps)."""
    dut.tck_i.value = 0
    dut.a_en_i.value = a_en
    dut.clk_b_i.value = 0
    dut.sel_a_i.value = 0
    dut.rst_n_i.value = 0
    await Timer(10, "ns")
    return int(get_sim_time("ps")) + 2000


class Run:
    """The log of one scenario, as pulse lists / event lists."""

    def __init__(self, dut):
        self.init_a = int(dut.en_a_o.value)
        self.init_b = int(dut.en_b_o.value)
        self.log = EdgeLog(
            {
                "out": dut.clk_o,
                "a": dut.clk_a_o,
                "b": dut.clk_b_i,
                "tck": dut.tck_i,
                "en_a": dut.en_a_o,
                "en_b": dut.en_b_o,
                "sel": dut.sel_a_i,
                "rst": dut.rst_n_i,
            },
            dut.tck_i,
        ).start()
        self.dut = dut

    def finish(self):
        self.log.stop()
        ev = self.log.events
        self.out = pulses_of(ev, "out")
        self.a = pulses_of(ev, "a")
        self.b = pulses_of(ev, "b")
        self.tck = pulses_of(ev, "tck")
        self.tck_rises = [r for r, _f in self.tck]
        self.en_a = events_of(ev, "en_a")
        self.en_b = events_of(ev, "en_b")
        self.sel = events_of(ev, "sel")
        self.rst = events_of(ev, "rst")
        assert int(self.dut.clk_o.value) == 0, "clk_o ends high"
        return self

    def labels(self, ta, tb, loose=False, gap_skip=()):
        return label_output_pulses(
            self.out, self.a, self.b, min(ta, tb) // 2, loose=loose, gap_skip=gap_skip
        )

    def latch_problems(self, skip=()):
        return check_enable_latches(
            self.en_a, self.en_b, self.tck, self.b, self.init_a, self.init_b, skip
        )

    def handover(self, labels, t_sw, target, t_end, ub, **kw):
        return check_handover(
            self.out, labels, self.a, self.b, self.tck_rises, t_sw, target, t_end, ub, **kw
        )

    def dump(self, t0, t1, ta=TA_DEFAULT, tb=TB_DEFAULT):
        """Text dump of everything in [t0, t1) (diagnostic for a failing window)."""
        lab, _p = self.labels(ta, tb, loose=True)
        rows = []
        for i, (r, f) in enumerate(self.out):
            if t0 <= r < t1:
                rows.append((r, f"out  [{r},{f}] {lab[i]}"))
        for nm, lst in (("A", self.a), ("B", self.b)):
            rows += [(r, f"src{nm} [{r},{f}]") for r, f in lst if t0 <= r < t1]
        for nm, ev in (
            ("en_a", self.en_a),
            ("en_b", self.en_b),
            ("sel", self.sel),
            ("rst", self.rst),
        ):
            rows += [(t, f"{nm}={v} @{t}") for t, v in ev if t0 <= t < t1]
        return "\n".join(x[1] for x in sorted(rows)[:120])

    def en_at(self, which, t):
        """Latch value at time t (after all events of t)."""
        ev = self.en_a if which == "a" else self.en_b
        v = self.init_a if which == "a" else self.init_b
        for te, ve in ev:
            if te <= t:
                v = ve
        return v


def _fail(problems, what, limit=8):
    if problems:
        shown = "\n  ".join(problems[:limit])
        raise AssertionError(
            f"{what}: {len(problems)} problem(s), first {min(limit, len(problems))}:\n  {shown}"
        )


# ---------------------------------------------------------------------------
# handover bounds (derived from the contract, see check_handover)
# ---------------------------------------------------------------------------
def ub_to_a(ta, tb):
    """->A: en_b_q falls within B's high width (tb/2) of the select change; then two TCK edges load
    the B->A synchroniser and the 3rd passes."""
    return tb // 2 + 3 * ta + 1


def ub_to_b(ta, tb):
    """->B: en_a_q falls within TCK's high width (ta/2); then two B edges and the 3rd passes."""
    return ta // 2 + 3 * tb + 1


# ---------------------------------------------------------------------------
# checker vacuity: it must detect every defect class (pure Python, synthetic logs)
# ---------------------------------------------------------------------------
def _synthetic_sources():
    a = [(1000 + k * 20000, 11000 + k * 20000) for k in range(10)]  # period 20 ns, 10 ns high
    b = [(3000 + k * 14000, 10000 + k * 14000) for k in range(14)]  # period 14 ns, 7 ns high
    return a, b


def _mux_pulses(a, b, sel_changes):
    """Output of a PLAIN mux built from the synthetic source waveforms: sel_changes = [(t, sel)]."""
    ra, rb = [p[0] for p in a], [p[0] for p in b]
    times = sorted(
        {t for p in a for t in p} | {t for p in b for t in p} | {t for t, _s in sel_changes}
    )
    sel = 0
    out, hi = [], None
    for t in times:
        for ts, s in sel_changes:
            if ts == t:
                sel = s
        lvl = level_at(a, t, ra) if sel else level_at(b, t, rb)
        if lvl and hi is None:
            hi = t
        elif not lvl and hi is not None:
            out.append((hi, t))
            hi = None
    return out


@cocotb.test()
async def test_checker_detects_each_defect_class(dut):
    """Vacuity guard: the analysis flags a runt, a truncation, a late start, a merge, a low runt,
    a skipped pulse, an early/late/returning handover and a latch violation, and passes a clean
    log.  Also flags the log of a PLAIN mux built from real waveforms (the defect Q-CLK was)."""
    a, b = _synthetic_sources()
    mp = 7000  # shortest phase of either source
    # clean: A pulses 0..3, then B pulses from the 8th on (switch around 70 ns)
    clean = a[:3] + [p for p in b if p[0] > 60000]
    lab, prob = label_output_pulses(clean, a, b, mp)
    assert prob == [] and lab[:3] == ["A"] * 3 and set(lab[3:]) == {"B"}, (lab, prob)

    def flagged(out, kind, loose=False, mp=mp):
        _lab, pr = label_output_pulses(out, a, b, mp, loose=loose)
        assert any(kind in p for p in pr), f"{kind!r} not flagged: {pr}"

    # runt-high: a plain-mux style truncation (A pulse cut short by a select change)
    flagged([(a[0][0], a[0][0] + 2000)], "runt-high")
    flagged([(a[0][0], a[0][0] + 8500)], "truncated")  # long enough to not be a runt, still cut
    flagged([(a[0][0] + 4000, a[0][1])], "late start")  # starts mid-pulse
    flagged([(5555, 6666)], "derived from no source edge")
    # merge of an A pulse and an overlapping B pulse
    a2, b2 = [(1000, 11000)], [(8000, 15000)]
    _l, pr = label_output_pulses([(1000, 15000)], a2, b2, mp)
    assert any("merge" in p for p in pr), pr
    lab, pr = label_output_pulses([(1000, 15000)], a2, b2, mp, loose=True)
    assert pr == [] and lab == ["M"], (lab, pr)  # allowed ONLY in the async-reset window (loose)
    _l, pr = label_output_pulses([(1000, 10500)], a2, b2, mp, loose=True)
    assert pr, "loose mode must still reject a truncated pulse (falls at no source fall)"
    # low runt: B pulse right behind an A pulse
    a3, b3 = [(1000, 11000)], [(13000, 20000)]
    _l, pr = label_output_pulses([(1000, 11000), (13000, 20000)], a3, b3, mp)
    assert any("runt-low" in p for p in pr), pr
    # handover rules
    ta_rises = [p[0] for p in a]
    sw = 61000  # select to B at 61 ns
    b_after = [p for p in b if p[0] > sw]  # 66, 80, 94, 108, 122, ...
    good = a[:3] + b_after[2:]  # B passes from its 3rd rise (94 ns)
    lab, pr = label_output_pulses(good, a, b, mp)
    assert pr == []
    p, info = check_handover(good, lab, a, b, ta_rises, sw, "B", 200000, 90000)
    assert p == [] and info["n_old"] == 0 and info["latency_ps"] == b_after[2][0] - sw, (p, info)
    early = a[:3] + b_after[1:]
    lab, _ = label_output_pulses(early, a, b, mp)
    p, _i = check_handover(early, lab, a, b, ta_rises, sw, "B", 200000, 90000)
    assert any("before handshake-clock rise #3" in x for x in p), p
    skipped = a[:3] + [b_after[2]] + b_after[4:]
    lab, _ = label_output_pulses(skipped, a, b, mp)
    p, _i = check_handover(skipped, lab, a, b, ta_rises, sw, "B", 200000, 90000)
    assert any("contiguous suffix" in x for x in p), p
    late = a[:3] + b_after[4:]
    lab, _ = label_output_pulses(late, a, b, mp)
    p, _i = check_handover(late, lab, a, b, ta_rises, sw, "B", 200000, 40000)
    assert any("not complete within the bound" in x for x in p), p
    old_after = a[:3] + [a[4]] + b_after[2:]  # an A pulse (rise 81 ns) after the select left A
    old_after = sorted(old_after)
    lab, _ = label_output_pulses(old_after, a, b, mp)
    p, _i = check_handover(old_after, lab, a, b, ta_rises, sw, "B", 200000, 90000)
    assert any("old-source" in x for x in p), p
    returning = a[:3] + [b_after[2], b_after[3], a[6]] + b_after[5:]
    returning = sorted(returning)
    lab, _ = label_output_pulses(returning, a, b, mp)
    p, _i = check_handover(returning, lab, a, b, ta_rises, sw, "B", 200000, 90000)
    assert any("after the handover completed" in x for x in p), p
    # latch discipline
    tck = a
    lp = check_enable_latches([(5000, 1)], [], tck, b)  # en_a_q rises while tck high (1..11 ns)
    assert any("while its clock is high" in x for x in lp), lp
    lp = check_enable_latches([(15000, 1)], [(15000, 1)], tck, b)  # both clocks low, both high
    assert any("both high" in x for x in lp), lp
    lp = check_enable_latches([(15000, 1)], [(30000, 1)], tck, b, init_a=0, init_b=0)
    assert any("both high" in x for x in lp), lp
    assert check_enable_latches([(15000, 1)], [(16000, 0)], tck, b, init_b=0) == []
    # a PLAIN mux log built from REAL waveforms is flagged: select moved while the old source
    # is high and the new one low (truncation), while the old is high and the new high (merge),
    # while the old is low and the new low (a later low runt)
    cases = [
        ([(0, 1), (10500, 0)], "A->B at 10.5 ns: A high, B low"),
        ([(18000, 1)], "B->A at 18 ns: B high, A low"),
        ([(6000, 1)], "B->A at 6 ns: A high, B high"),
    ]
    for sel_changes, why in cases:
        out = _mux_pulses(a, b, sel_changes)
        _l, pr = label_output_pulses(out, a, b, mp)
        assert pr, f"plain-mux log ({why}) not flagged: {out[:4]}"


# ---------------------------------------------------------------------------
# the long sweep
# ---------------------------------------------------------------------------
def _plan_sweep(base, ta, tb, n_sw, mode, seed):
    rng = random.Random(seed)
    ha = ta // 2
    tmax = max(ta, tb)
    pha, phb = base + 1700, base + 900  # absolute rising-edge phases of TCK and B
    t_rel = base + 12 * tmax + 777
    while _near(t_rel, ta, pha) or _near(t_rel, tb, phb):
        t_rel += 11
    switches = []  # (t, target)
    t = t_rel + 4 * tmax
    target = "A"
    for _k in range(n_sw):
        t_c = t + rng.randrange(0, 2 * tmax)
        if mode == "tap":  # launched like the TAP's falling-edge serial flop: 1 ps after a TCK fall
            m = max(0, (t_c - (pha + ha)) // ta + 1)
            t_c = pha + ha + m * ta + 1
            while _near(t_c, tb, phb):
                t_c += ta
        else:
            while _near(t_c, ta, pha) or _near(t_c, tb, phb):
                t_c += rng.randrange(7, 31)
        switches.append((t_c, target))
        ub = ub_to_a(ta, tb) if target == "A" else ub_to_b(ta, tb)
        t = t_c + ub + 4 * tmax
        target = "B" if target == "A" else "A"
    t_final = t
    plan = Plan(base)
    plan.at(base, "rst_n_i", 0)
    plan.at(t_rel, "rst_n_i", 1)
    plan.clock("tck_i", ta, pha - base, base, t_final)
    plan.clock("clk_b_i", tb, phb - base, base, t_final)
    plan.at(base, "a_en_i", 1)
    plan.at(base, "sel_a_i", 0)
    for ts, tgt in switches:
        plan.at(ts, "sel_a_i", 1 if tgt == "A" else 0)
    gate_changes = 0
    if mode == "gated":
        g, val = t_rel, 1
        while g < t_final - 8 * tmax:
            g += rng.randrange(ta, 5 * ta)
            while _near(g, ta, pha):
                g += 13
            val ^= 1
            plan.at(g, "a_en_i", val)
            gate_changes += 1
        plan.at(t_final - 6 * tmax, "a_en_i", 1)
    return plan, switches, t_rel, t_final + 3 * tmax, (pha, phb), gate_changes


async def sweep_switching(dut, cfg, mode):
    # B gets a few extra ps so its phase against the TCK edges takes ~thousands of distinct values
    # (two whole-ns periods only ever meet at tb/gcd distinct phases)
    ta, tb = cfg[0] * 1000, cfg[1] * 1000 + 6
    base = await prep(dut)
    plan, switches, t_rel, t_end, (pha, phb), n_gate = _plan_sweep(
        base, ta, tb, N_SWITCH, mode, seed=cfg[0] * 100 + cfg[1] + MODES.index(mode)
    )
    run = Run(dut)
    await play(dut, plan)
    await Timer(max(0, t_end - int(get_sim_time("ps"))), "ps")
    run.finish()
    labels, problems = run.labels(ta, tb)
    # steady B from power-up/reset through the first select change
    first = switches[0][0]
    p, _i = run.handover(labels, 0, "B", first, 0, lower=0)
    problems += [f"[reset window] {x}" for x in p]
    stats = {"A": [], "B": []}
    cover = {"A": [], "B": []}
    for k, (ts, tgt) in enumerate(switches):
        t_next = switches[k + 1][0] if k + 1 < len(switches) else t_end
        ub = ub_to_a(ta, tb) if tgt == "A" else ub_to_b(ta, tb)
        p, info = run.handover(labels, ts, tgt, t_next, ub)
        problems += [f"[switch {k} to {tgt} at {ts} ps] {x}" for x in p]
        if info["latency_ps"] is not None:
            stats[tgt].append(info["latency_ps"])
        cover[tgt].append(
            (level_at(run.tck, ts), level_at(run.b, ts), (ts - pha) % ta, (ts - phb) % tb)
        )
    problems += [f"[latches] {x}" for x in run.latch_problems()]
    _fail(problems, f"cfg {cfg} mode {mode}")

    # ---- coverage / vacuity guards ------------------------------------------------------
    for tgt in ("A", "B"):
        c = cover[tgt]
        assert len(c) == N_SWITCH // 2
        hi_lo = {(x[0], x[1]) for x in c}
        want = {(0, 0), (0, 1)} if mode == "tap" else {(0, 0), (0, 1), (1, 0), (1, 1)}
        assert want <= hi_lo, f"{tgt}: select instants miss (tck,B) level combos {want - hi_lo}"
        for combo in want:
            assert sum(1 for x in c if (x[0], x[1]) == combo) >= 5, (tgt, combo)
        for idx, per in ((2, ta), (3, tb)):
            if mode == "tap" and idx == 2:
                continue  # TAP launch: the TCK phase is fixed by construction
            bins = {x[idx] * 8 // per for x in c}
            assert len(bins) >= 7, f"{tgt}: select instants cover only {len(bins)}/8 phase bins"
    for tgt, tsync in (("A", ta), ("B", tb)):
        lat = stats[tgt]
        assert len(lat) >= (N_SWITCH // 2) * (0.5 if mode == "gated" else 1.0) - 1, (tgt, len(lat))
        assert min(lat) >= 2 * tsync - 1, f"{tgt}: latency {min(lat)} < 2 sync periods"
        # the bound is approached, not vacuous
        ub = ub_to_a(ta, tb) if tgt == "A" else ub_to_b(ta, tb)
        if mode == "arb":  # B/TCK phase swept: the measured maximum approaches the bound
            assert max(lat) <= ub
            assert max(lat) >= 2.9 * tsync, (tgt, max(lat), 3 * tsync)
        elif mode == "tap":
            assert max(lat) <= ub
        dut._log.info(
            f"cfg {cfg} mode {mode} ->{tgt}: n={len(lat)} latency ps min {min(lat)} "
            f"max {max(lat)} bound {ub} (sync period {tsync})"
        )
    if mode == "gated":
        assert n_gate > 20, "vacuity guard: A was not gated randomly"
        assert len(run.a) < len(run.tck) * 0.9, "vacuity guard: gating removed no A pulses"


_tf = TestFactory(sweep_switching)
_tf.add_option("cfg", CFGS)
_tf.add_option("mode", MODES)
_tf.generate_tests(postfix="_sweep")


# ---------------------------------------------------------------------------
# hand-built scenarios
# ---------------------------------------------------------------------------
TA, TB = 11000, 7000  # TCK / pin clock periods (ps) of the scenario tests (coprime in ns)
PHA = 1300  # TCK rise phase relative to the timeline base


def _tck_fall(base, n):
    """Time of the n-th TCK falling edge (n counted from 0) of a clock with rises at base+PHA."""
    return base + PHA + TA // 2 + n * TA


@cocotb.test()
async def test_serial_to_parallel_waits_for_the_pin_clock(dut):
    """sel 1 -> 0 with the pin clock STOPPED low: the output goes and stays low, with no extra
    edge, for as long as B does not run, whatever TCK does; when B starts, its first two rising
    edges are consumed by the handshake and the 3rd passes (exactly), then every pulse."""
    base = await prep(dut)
    p = Plan(base)
    n_cyc = 120
    p.clock("tck_i", TA, PHA, base, base + n_cyc * TA)
    p.at(base + 6 * TA + 3000, "rst_n_i", 1)  # B idles low through reset
    p.at(base, "sel_a_i", 0)
    t_s1 = _tck_fall(base, 10) + 1
    t_s0 = _tck_fall(base, 25) + 1
    p.at(t_s1, "sel_a_i", 1)
    p.at(t_s0, "sel_a_i", 0)
    # WITNESS: B is clocked 4 cycles while A is on (its pulses are blocked), so the A->B
    # synchroniser holds "A is on"; that is what makes the later retirement wait for B edges
    t_w = _tck_fall(base, 15) + 777
    p.clock("clk_b_i", TB, 0, t_w, t_w + 4 * TB)
    t_b0 = base + 100 * TA + 777  # B restarts after ~75 TCK cycles of silence
    p.clock("clk_b_i", TB, 0, t_b0, t_b0 + 16 * TB)
    run = Run(dut)
    await play(dut, p)
    await Timer(5 * TA, "ps")
    run.finish()
    labels, problems = run.labels(TA, TB)
    assert len([r for r, _f in run.b if t_w <= r < t_w + 5 * TB]) == 4, "witness burst missing"
    assert not [o for o in run.out if t_w <= o[0] < t_w + 4 * TB and o not in run.a], (
        "a witness B pulse leaked while A was selected"
    )
    # reset -> A: B idles low so the retirement needs no B edge; A passes at the 3rd TCK rise
    hp, info = run.handover(labels, t_s1, "A", t_s0, 3 * TA + 1)
    problems += hp
    j = [r for r in run.tck_rises if r > t_s1]
    assert info["n_new"] >= 10 and info["n_old"] == 0
    assert info["latency_ps"] == j[2] - t_s1, "A must pass exactly at the 3rd TCK rise (B idle low)"
    # A -> B with B stopped: silence, no extra edge, until B runs
    quiet = [o for o in run.out if t_s0 <= o[0] < t_b0]
    assert quiet == [], f"output moved while the pin clock was stopped: {quiet[:3]}"
    assert [t for t, v in run.en_b if t_s0 <= t < t_b0] == [], "en_b_q moved without a B clock"
    assert run.en_at("a", t_s0 + 1) == 0 and run.en_at("b", t_b0 - 1) == 0
    assert len([r for r in run.tck_rises if t_s0 < r < t_b0]) > 60, "vacuity guard: TCK ran"
    after = [o for o in run.out if o[0] >= t_b0]
    b_rises = [r for r, _f in run.b if r >= t_b0]
    assert [o[0] for o in after] == b_rises[2:], (
        f"B must pass from its 3rd rise: out {[o[0] for o in after][:4]} B rises {b_rises[:5]}"
    )
    assert all(lab == "B" for o, lab in zip(run.out, labels) if o[0] >= t_b0)
    _fail(problems + run.latch_problems(), "serial->parallel with B stopped")


@cocotb.test()
async def test_parallel_to_serial_needs_no_pin_clock_edge(dut):
    """sel 0 -> 1 with B idling LOW and never toggling: A passes at exactly the 3rd TCK rising edge
    after the select change, at every phase of the select relative to TCK, with NO edge on B.
    Between iterations B is burst-clocked just enough to re-enable it (7 cycles) and then stopped
    again: the 3rd B rise after the select change passes, exactly."""
    n_it = 24
    base = await prep(dut)
    p = Plan(base)
    cyc_it = 40  # TCK cycles per iteration
    end = base + (n_it + 2) * cyc_it * TA
    p.clock("tck_i", TA, PHA, base, end)
    p.at(base + 6 * TA + 3000, "rst_n_i", 1)
    sels, bursts = [], []
    for i in range(n_it):
        t0 = base + (i + 1) * cyc_it * TA
        t_to_a = t0 + PHA + (i * TA) // n_it + 37  # sweeps one full TCK period over n_it iterations
        while _near(t_to_a, TA, base + PHA):
            t_to_a += 11
        t_to_b = _tck_fall(base, (i + 1) * cyc_it + 20) + 1
        t_burst = t_to_b + 4 * TA + 555 + i * 97
        p.at(t_to_a, "sel_a_i", 1)
        t_w = t_to_a + 12 * TA + 321  # witness: B clocked 4 cycles while A is on (blocked)
        p.clock("clk_b_i", TB, 0, t_w, t_w + 4 * TB)
        p.at(t_to_b, "sel_a_i", 0)
        bursts.append(p.clock("clk_b_i", TB, 0, t_burst, t_burst + 7 * TB))
        sels.append((t_to_a, t_to_b, t_burst))
    run = Run(dut)
    await play(dut, p)
    await Timer(8 * TA, "ps")
    run.finish()
    labels, problems = run.labels(TA, TB)
    phases = set()
    for i, (t_to_a, t_to_b, t_burst) in enumerate(sels):
        t_next = sels[i + 1][0] if i + 1 < n_it else int(get_sim_time("ps"))
        hp, info = run.handover(labels, t_to_a, "A", t_to_b, 3 * TA + 1)
        problems += [f"[it {i} ->A] {x}" for x in hp]
        j = [r for r in run.tck_rises if r > t_to_a]
        if info["latency_ps"] != j[2] - t_to_a:
            problems.append(
                f"[it {i} ->A] latency {info['latency_ps']} != 3rd TCK rise {j[2] - t_to_a}"
            )
        assert [o for o in run.out if t_to_a <= o[0] < t_to_b and o not in run.a] == []
        assert not any(t_to_a <= r < t_to_a + 11 * TA for r, _f in run.b), "B moved early"
        phases.add(((t_to_a - base - PHA) % TA) * 8 // TA)
        # ->B with B stopped until the burst: nothing in between, then the 3rd burst rise passes
        quiet = [o for o in run.out if t_to_b <= o[0] < t_burst]
        if quiet:
            problems.append(f"[it {i} ->B] output moved before the pin clock ran: {quiet[:2]}")
        burst_rises = [r for r, _f in bursts[i]]
        got = [o[0] for o in run.out if t_burst <= o[0] < t_next]
        if got != burst_rises[2:]:
            problems.append(
                f"[it {i} ->B] passed {got[:3]}.. expected the 3rd burst rise on {burst_rises[2:5]}"
            )
        hp, _info = run.handover(
            labels, t_to_b, "B", t_next, (t_burst - t_to_b) + TA // 2 + 3 * TB + 1
        )
        problems += [f"[it {i} ->B] {x}" for x in hp]
    assert len(phases) >= 7, f"select instants cover only {len(phases)}/8 TCK phases"
    _fail(problems + run.latch_problems(), "parallel->serial with B idle low")


@cocotb.test()
async def test_pin_clock_stopped_high_blocks_the_switch_limitation(dut):
    """DOCUMENTED LIMITATION (dft_clk_switch.sv contract point 2/1): clk_b_i stopped HIGH makes the
    B latch opaque, so
      (a) parallel -> serial cannot complete: the output stays high (B's level) and no A pulse
          appears for as long as B stays high;  once B falls it completes (3rd TCK rise);
      (b) serial -> parallel: the output stays low and the stuck-high B pulse never passes, until B
          toggles again.
    This is expected behaviour, not a defect: the tester must park scan_clk_i LOW."""
    base = await prep(dut)
    p = Plan(base)
    n_cyc = 220
    p.clock("tck_i", TA, PHA, base, base + n_cyc * TA)
    p.at(base + 6 * TA + 3000, "rst_n_i", 1)
    # (a) B toggles 3 cycles, then stops HIGH
    t_b0 = base + 8 * TA + 100
    p.clock("clk_b_i", TB, 0, t_b0, t_b0 + 3 * TB)
    t_stuck = t_b0 + 3 * TB + 500  # rises and stays high
    p.at(t_stuck, "clk_b_i", 1)
    t_s1 = _tck_fall(base, 20) + 1
    p.at(t_s1, "sel_a_i", 1)
    t_fall = base + 90 * TA + 1234  # B finally falls, then toggles for 20 cycles
    p.at(t_fall, "clk_b_i", 0)
    p.clock("clk_b_i", TB, TB // 2, t_fall, t_fall + 20 * TB)
    # (b) A is selected and running; select B at TCK fall; B rises once and sticks high
    t_s0 = _tck_fall(base, 130) + 1
    p.at(t_s0, "sel_a_i", 0)
    t_stuck2 = base + 140 * TA + 321
    p.at(t_stuck2, "clk_b_i", 1)
    t_fall2 = base + 190 * TA + 1234
    p.at(t_fall2, "clk_b_i", 0)
    p.clock("clk_b_i", TB, TB // 2, t_fall2, t_fall2 + 20 * TB)
    run = Run(dut)
    await play(dut, p)
    await Timer(6 * TA, "ps")
    run.finish()
    labels, problems = run.labels(TA, TB)
    # (a) output is the stuck-high B pulse: one long whole B pulse [t_stuck, t_fall]
    long_pulse = [o for o in run.out if o[0] == t_stuck]
    assert long_pulse and long_pulse[0][1] == t_fall, (
        f"output must hold B's level (stuck high) until B falls at {t_fall}: {long_pulse}"
    )
    assert not [o for o in run.out if t_s1 < o[0] < t_fall], "an A pulse leaked while B was high"
    assert run.en_at("b", t_fall - 1) == 1 and run.en_at("a", t_fall - 1) == 0, (
        "the B latch must stay opaque/enabled and A disabled while B is stuck high"
    )
    hp, info = run.handover(labels, t_fall, "A", t_s0, 3 * TA + 1)
    problems += [f"[a] {x}" for x in hp]
    assert info["n_new"] > 20 and info["n_old"] == 0, info
    j = [r for r in run.tck_rises if r > t_fall]
    assert info["latency_ps"] == j[2] - t_fall, (
        "after B falls the handover takes exactly 3 TCK rises"
    )
    # (b) A -> B with B stuck high: silent until B toggles again
    assert not [o for o in run.out if t_s0 <= o[0] < t_fall2], (
        "output moved while B was stuck high after serial->parallel"
    )
    hp, info = run.handover(labels, t_fall2, "B", int(get_sim_time("ps")), 3 * TB + 1, lower=0)
    problems += [f"[b] {x}" for x in hp]
    assert info["n_new"] >= 15, info
    b_after = [r for r, _f in run.b if r > t_fall2]
    idx = b_after.index(info["latency_ps"] + t_fall2) + 1
    dut._log.info(f"B stuck high: first B pulse passed after the restart is #{idx}")
    _fail(problems + run.latch_problems(), "B stopped high")


@cocotb.test()
async def test_tck_stopped_parallel_to_serial_goes_quiet_until_tck_toggles(dut):
    """The mirror of the pin-clock case: sel 0 -> 1 with TCK STOPPED.  B is retired at once (its
    enable drops with no clock) but A needs the TCK handshake, so the output goes quiet; B pulses
    stop immediately and A starts at the 3rd TCK rise after TCK resumes."""
    base = await prep(dut)
    p = Plan(base)
    n_cyc = 150
    p.clock("clk_b_i", TB, 0, base, base + n_cyc * TA)
    p.clock("tck_i", TA, PHA, base, base + 6 * TA)  # TCK runs through reset, then stops
    p.at(base + 6 * TA - 4000, "rst_n_i", 1)  # reset released while TCK still runs (synchroniser)
    t_s1 = base + 20 * TA + 4321  # TCK is stopped; select to A
    while _near(t_s1, TB, base):
        t_s1 += 11
    p.at(t_s1, "sel_a_i", 1)
    t_tck = base + 100 * TA + 555
    p.clock("tck_i", TA, 0, t_tck, t_tck + 20 * TA)
    run = Run(dut)
    await play(dut, p)
    await Timer(4 * TA, "ps")
    run.finish()
    labels, problems = run.labels(TA, TB)
    hp, info = run.handover(
        labels, t_s1, "A", int(get_sim_time("ps")), (t_tck - t_s1) + TB // 2 + 3 * TA + 1
    )
    problems += hp
    assert not [o for o in run.out if t_s1 <= o[0] < t_tck], "output moved while TCK was stopped"
    assert info["n_new"] >= 15 and info["n_old"] == 0, info
    j = [r for r in run.tck_rises if r > t_s1]
    assert info["latency_ps"] == j[2] - t_s1
    _fail(problems + run.latch_problems(), "TCK stopped")


@cocotb.test()
async def test_a_gated_off_and_back(dut):
    """A idles low (gate closed) while TCK keeps running: the handshake still completes (it is
    TCK-driven), the output stays quiet with no edge, and the first A pulse after the gate opens
    passes whole.  Closing the gate and selecting B again: A pulses stop, B returns after 3 B
    cycles; re-opening the gate while B is selected passes no A pulse."""
    base = await prep(dut, a_en=0)
    p = Plan(base)
    n_cyc = 260
    p.clock("tck_i", TA, PHA, base, base + n_cyc * TA)
    p.clock("clk_b_i", TB, 0, base, base + n_cyc * TA)
    p.at(base + 6 * TA + 3000, "rst_n_i", 1)
    t_s1 = _tck_fall(base, 20) + 1
    p.at(t_s1, "sel_a_i", 1)
    t_open = _tck_fall(base, 80) + 777  # gate opens (any instant: the gate latch aligns it)
    while _near(t_open, TA, base + PHA):
        t_open += 11
    p.at(t_open, "a_en_i", 1)
    t_s0 = _tck_fall(base, 120) + 1
    p.at(t_s0, "sel_a_i", 0)
    p.at(t_s0 + 3, "a_en_i", 0)
    t_open2 = _tck_fall(base, 170) + 333
    while _near(t_open2, TA, base + PHA):
        t_open2 += 11
    p.at(t_open2, "a_en_i", 1)
    run = Run(dut)
    await play(dut, p)
    await Timer(4 * TA, "ps")
    run.finish()
    assert not run.a or run.a[0][0] > t_open, (
        "vacuity guard: A must be silent before the gate opens"
    )
    labels, problems = run.labels(TA, TB)
    hp, info = run.handover(labels, t_s1, "A", t_s0, TB // 2 + 3 * TA + 1)
    problems += [f"[->A] {x}" for x in hp]
    assert not [o for o in run.out if t_s1 <= o[0] < t_open], "output moved while A was gated off"
    first_a = [r for r, _f in run.a if r > t_open][0]
    assert info["latency_ps"] == first_a - t_s1 and info["n_new"] >= 20, info
    hp, info = run.handover(labels, t_s0, "B", int(get_sim_time("ps")), TA // 2 + 3 * TB + 1)
    problems += [f"[->B] {x}" for x in hp]
    assert info["n_new"] > 50 and info["n_old"] == 0, info
    b_after = [r for r, _f in run.b if r > t_s0]
    first_b = [o[0] for o in run.out if o[0] > t_s0][0]
    assert first_b == b_after[2], "B must come back at its 3rd rise after the select change"
    assert [r for r, _f in run.a if r > t_open2], "vacuity guard: A pulses exist after re-open"
    assert not [a for a in run.a if a[0] > t_open2 and a in run.out], "A passed while B selected"
    _fail(problems + run.latch_problems(), "A gated off")


@cocotb.test()
async def test_reset_state_selects_b(dut):
    """rst_n_i LOW (level) selects B with A off whatever sel_a_i does and whatever A does: clk_o is
    clk_b_i edge for edge, en_a_q = 0, en_b_q = 1."""
    base = await prep(dut)
    p = Plan(base)
    n_cyc = 120
    p.clock("tck_i", TA, PHA, base, base + n_cyc * TA)
    p.clock("clk_b_i", TB, 0, base, base + n_cyc * TA)
    p.at(base, "sel_a_i", 1)  # A requested in reset
    for k in range(1, 8):
        p.at(base + k * 13 * TA + 2345 + k * 101, "sel_a_i", k % 2)
    run = Run(dut)
    await play(dut, p)
    await Timer(3 * TA, "ps")
    run.finish()
    assert len(run.b) > 100 and len(run.a) > 100, "vacuity guard: both clocks ran"
    assert run.out == run.b, "in reset clk_o must equal clk_b_i edge for edge"
    assert run.en_at("a", base + 100 * TA) == 0 and run.en_at("b", base + 100 * TA) == 1
    _fail(run.latch_problems(), "reset state")


def _rise_within(clocks, t0, t1):
    """True if a rising edge of any clock in clocks=[(period, abs_phase), ...] lies in [t0, t1]."""
    for per, ph in clocks:
        nxt = ph + -(-(t0 - ph) // per) * per  # first rise at or after t0
        if nxt <= t1:
            return True
    return False


def _clear_of(t, clocks, step=11):
    """Nudge t until it is more than TOL ps from every edge of clocks=[(period, abs_phase), ...]."""
    while any(_near(t, per, ph) for per, ph in clocks):
        t += step
    return t


@cocotb.test()
async def test_reset_in_the_middle_of_pulses(dut):
    """Asynchronous rst_n_i assertion at many instants (TCK high/low x B high/low) with A selected:
    pulses may MERGE but no output pulse is shortened or created from nothing (loose pulse rule),
    the old A is cut off (no A pulse starts after the assertion), B resumes within one pulse, the
    latches reach en_a=0 / en_b=1, and after release the handshake is the normal one (select still
    1 -> A again at the 3rd TCK rise, never overlapping B).  Variants: select stays 1; select falls
    with the reset; select falls in the middle of the reset."""
    n_it = 54
    base = await prep(dut)
    ha, hb = TA // 2, TB // 2
    clocks = [(TA, base + PHA), (TB, base)]
    rng = random.Random(7)
    p = Plan(base)
    p.at(base + 6 * TA + 3000, "rst_n_i", 1)
    its = []
    t = base + 16 * TA
    for i in range(n_it):
        var = i % 3
        t_sel = _clear_of(t, clocks)
        t_r = _clear_of(t_sel + 30 * TA + rng.randrange(0, 3 * TA), clocks, rng.randrange(7, 31))
        t_rel = _clear_of(t_r + 14 * TA + rng.randrange(0, TA), clocks)
        short = i % 6 == 0  # var 0 only: a 1.5 ns reset pulse that no handshake clock edge sees
        if short:
            while _rise_within(clocks, t_r - 300, t_r + 1500 + 300):
                t_r = _clear_of(t_r + 37, clocks)
            t_rel = t_r + 1500
        p.at(t_sel, "sel_a_i", 1)
        p.at(t_r, "rst_n_i", 0)
        if var == 1:
            p.at(t_r, "sel_a_i", 0)
        elif var == 2:
            p.at(_clear_of(t_r + 5 * TA + 17, clocks), "sel_a_i", 0)
        p.at(t_rel, "rst_n_i", 1)
        t_back = _clear_of(t_rel + 24 * TA, clocks)
        if var == 0:  # select still 1 at release: A comes back; return to B afterwards
            p.at(t_back, "sel_a_i", 0)
        its.append((var, t_sel, t_r, t_rel, t_back, short))
        t = (t_back if var == 0 else t_rel) + 31 * TA
    end = t + 10 * TA
    p.clock("tck_i", TA, PHA, base, end)
    p.clock("clk_b_i", TB, 0, base, end)
    run = Run(dut)
    await play(dut, p)
    await Timer(6 * TA, "ps")
    run.finish()
    t_end = int(get_sim_time("ps"))
    skip = [(it[2], it[2] + ha + hb + 100) for it in its]
    # inside the merge window a B pulse may follow an A pulse closely (both enables briefly on):
    # tolerated as the OR of two whole pulses; counted and logged below
    # The window starts one TCK period BEFORE the assertion: an A pulse that fell just before t_r
    # can be followed by a B pulse (en_b_q opens at once) with a short low notch between the two
    # whole pulses.
    gap_win = [(it[2] - TA, it[2] + 2 * max(TA, TB)) for it in its]
    labels, problems = run.labels(TA, TB, loose=True, gap_skip=gap_win)
    a_rises = {r for r, _f in run.a}
    out_rises = {o[0] for o in run.out}
    cover, n_merge = [], 0
    for k, (_var, t_sel, t_r, t_rel, t_back, short) in enumerate(its):
        var = _var
        cover.append((level_at(run.tck, t_r), level_at(run.b, t_r)))
        nxt = its[k + 1][1] if k + 1 < len(its) else t_end
        # before the reset: the normal B -> A handover (window ends a TCK period before the
        # assertion: a pulse already in progress at t_r can merge, its rise lies before t_r)
        hp, _info = run.handover(labels, t_sel, "A", t_r - TA, ub_to_a(TA, TB))
        problems += [f"[it {k} pre-reset ->A] {x}" for x in hp]
        # during the reset: A is cut off, B returns, merges are allowed
        for i, (r, _f) in enumerate(run.out):
            if t_r + TOL < r < t_rel and (labels[i] == "A" or (labels[i] == "M" and r in a_rises)):
                problems.append(f"[it {k}] A pulse starts at {r} ps after the reset at {t_r} ps")
            n_merge += int(t_r <= r < t_rel and labels[i] == "M")
        for br, _bf in run.b:
            if t_r + max(ha, hb) + TOL <= br < t_rel and br not in out_rises:
                problems.append(f"[it {k}] B pulse at {br} ps not passed {br - t_r} ps after reset")
        ea, eb = run.en_at("a", t_rel - 2), run.en_at("b", t_rel - 2)
        if (ea, eb) != (0, 1) and not short:
            problems.append(f"[it {k}] latches (en_a, en_b) = ({ea}, {eb}) at release, want (0, 1)")
        # after the release
        if var == 0:
            hp, info = run.handover(labels, t_rel, "A", t_back, ub_to_a(TA, TB))
            problems += [f"[it {k} release ->A] {x}" for x in hp]
            assert info["n_new"] > 10, info
            hp, _info = run.handover(labels, t_back, "B", nxt, ub_to_b(TA, TB))
            problems += [f"[it {k} back ->B] {x}" for x in hp]
        else:
            hp, _info = run.handover(labels, t_rel, "B", nxt, 0, lower=0)
            problems += [f"[it {k} release stays B] {x}" for x in hp]
    problems += [f"[latches] {x}" for x in run.latch_problems(skip=skip)]
    for pr in list(problems):
        if pr.startswith("runt-low gap ["):
            t_gap = int(pr.split("[")[1].split(",")[0])
            it = [x for x in its if x[2] - 2 * TA <= t_gap <= x[3] + 2 * TA]
            problems.append(
                f"context of gap at {t_gap} (iteration {it}):\n"
                + run.dump(t_gap - 3 * TA, t_gap + 3 * TA)
            )
            break
    _fail(problems, "reset in the middle of pulses", limit=6)
    for combo in ((0, 0), (0, 1), (1, 0), (1, 1)):
        assert cover.count(combo) >= 5, f"reset instants saw (tck, B) levels {combo} too rarely"
    dut._log.info(
        f"reset sweep: {n_it} assertions, {n_merge} merged pulses, coverage {sorted(set(cover))}"
    )


@cocotb.test()
async def test_reversal_dwell(dut):
    """Contract point 3: a select reversal needs a full handshake in between.  Reversal after
    `dwell` >= D_safe (= the handover bound + 3 cycles of the OTHER clock + the longer half period,
    so the first handover has completed on BOTH sides), at swept phases, is clean: whole pulses,
    exact handover, exclusive latches.  Shorter dwell is characterised, not required: the number of
    latch-exclusion violations seen at short dwell is logged."""
    base = await prep(dut)
    rng = random.Random(3)
    clocks = [(TA, base + PHA), (TB, base)]
    p = Plan(base)
    p.at(base + 6 * TA + 3000, "rst_n_i", 1)
    ub_a, ub_b = ub_to_a(TA, TB), ub_to_b(TA, TB)
    safe_x = ub_a + 3 * TB + TA // 2  # first handover ->A completed, A->B sync loaded
    safe_y = ub_b + 3 * TA + TA // 2  # first handover ->B completed, B->A sync loaded
    gap = 2 * (ub_a + ub_b) + 8 * TA
    fracs = (0.25, 0.5, 0.75, 1.0, 1.5, 2.0)
    groups = []  # (kind, frac, t0, t1, t_stop, t_end_of_group)
    t = base + 16 * TA
    for g in range(120):
        frac, kind = fracs[(g // 2) % 6], "XY"[g % 2]
        if kind == "Y":  # needs A steady first
            t_p = _clear_of(t, clocks)
            p.at(t_p, "sel_a_i", 1)
            t = t_p + gap
        t0 = _clear_of(t, clocks)
        d = int(frac * (safe_x if kind == "X" else safe_y)) + rng.randrange(0, TA)
        t1 = _clear_of(t0 + d, clocks)
        first, second = (1, 0) if kind == "X" else (0, 1)
        p.at(t0, "sel_a_i", first)
        p.at(t1, "sel_a_i", second)
        t = t1 + gap
        t_stop = t  # end of the post-reversal window (the restore below is a separate switch)
        if kind == "Y":  # restore B
            t_r = _clear_of(t, clocks)
            t_stop = t_r
            p.at(t_r, "sel_a_i", 0)
            t = t_r + gap
        groups.append((kind, frac, t0, t1, t_stop, t))
    end = t + 6 * TA
    p.clock("tck_i", TA, PHA, base, end)
    p.clock("clk_b_i", TB, 0, base, end)
    run = Run(dut)
    await play(dut, p)
    await Timer(6 * TA, "ps")
    run.finish()
    labels, _all = run.labels(TA, TB)  # problems of the short-dwell groups are NOT judged
    problems = []
    skip, n_strict, first_bad = [], 0, None
    for kind, frac, t0, t1, t_stop, t_grp_end in groups:
        if frac < 1.0:
            skip.append((t0, t_grp_end))
            continue
        n_strict += 1
        w_out = [o for o in run.out if t0 <= o[0] < t_grp_end]
        w_a = [x for x in run.a if t0 - TA <= x[0] < t_grp_end]
        w_b = [x for x in run.b if t0 - TA <= x[0] < t_grp_end]
        _l, wp = label_output_pulses(w_out, w_a, w_b, min(TA, TB) // 2)
        problems += [f"[dwell {frac}x {kind} window] {x}" for x in wp]
        tgt1, tgt2 = ("A", "B") if kind == "X" else ("B", "A")
        ub1 = ub_a if kind == "X" else ub_b
        ub2 = ub_b if kind == "X" else ub_a
        hp, _i = run.handover(labels, t0, tgt1, t1, ub1)
        problems += [f"[dwell {frac}x {kind} first] {x}" for x in hp]
        hp, _i = run.handover(labels, t1, tgt2, t_stop, ub2)
        problems += [f"[dwell {frac}x {kind} reversal] {x}" for x in hp]
        if hp and first_bad is None:
            first_bad = (t0 - TA, min(t0 + 120 * TA // 2, t_grp_end))
    assert n_strict >= 50
    problems += [f"[latches] {x}" for x in run.latch_problems(skip=skip)]
    n_short = len(run.latch_problems()) - len(run.latch_problems(skip=skip))
    if first_bad:
        problems.append("context of the first bad group:\n" + run.dump(*first_bad))
    _fail(problems, "reversal after a full handshake", limit=12)
    dut._log.info(
        f"dwell: {n_strict} strict reversals clean; short-dwell exclusion hits: {n_short}"
    )


@cocotb.test()
async def test_serial_to_parallel_with_a_never_clocked_pin_clock(dut):
    """CHARACTERISATION of a case the dft_clk_switch.sv header does not describe.  If the pin clock
    has not toggled since reset, the A->B synchroniser is still at its reset value (0, "A is off"),
    so after sel 1 -> 0 the B enable is NOT held off waiting for B edges: B is re-enabled as soon
    as its latch is open.  Not a hazard in the TAP (sel falls at a TCK falling edge, A low, and the
    gate closes with the select), but the "B must toggle ~3 cycles first" rule only holds once B
    has clocked while A was on (test_serial_to_parallel_waits_for_the_pin_clock).  Asserted here:
    no extra edge before B runs, whole pulses, B starts passing within its first 3 rises, and the
    observed index is logged."""
    base = await prep(dut)
    p = Plan(base)
    p.clock("tck_i", TA, PHA, base, base + 120 * TA)
    p.at(base + 6 * TA + 3000, "rst_n_i", 1)
    t_s1 = _tck_fall(base, 10) + 1
    t_s0 = _tck_fall(base, 25) + 1
    p.at(t_s1, "sel_a_i", 1)
    p.at(t_s0, "sel_a_i", 0)
    t_b0 = base + 100 * TA + 777
    p.clock("clk_b_i", TB, 0, t_b0, t_b0 + 16 * TB)
    run = Run(dut)
    await play(dut, p)
    await Timer(5 * TA, "ps")
    run.finish()
    labels, problems = run.labels(TA, TB)
    assert not run.b or run.b[0][0] >= t_b0, "vacuity guard: B must never have clocked before"
    assert not [o for o in run.out if t_s0 <= o[0] < t_b0], "output moved before B ran"
    after = [o[0] for o in run.out if o[0] >= t_b0]
    b_rises = [r for r, _f in run.b]
    assert after and after == b_rises[len(b_rises) - len(after) :], "B pulses must pass whole"
    idx = b_rises.index(after[0]) + 1
    assert idx <= 3, f"first B pulse passed is #{idx}, later than the handshake allows"
    dut._log.info(f"never-clocked B: first B pulse passed after sel 1->0 is #{idx}")
    _fail(problems + run.latch_problems(), "serial->parallel, B never clocked")
