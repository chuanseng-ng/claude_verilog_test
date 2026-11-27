# ruff: noqa: E501
"""Tests for tools/dft/atpg/untestable_audit.py and audit_graph.py: sampling, class parsing, statistics, classifier, and the
SAT / ternary machinery on a small BLIF with one fault of every cause.

Doc: cr:suite:test-dft-atpg-untestable-audit
"""

import sys
from pathlib import Path

import pytest

ATPG_DIR = Path(__file__).resolve().parents[2] / "tools" / "dft" / "atpg"
sys.path.insert(0, str(ATPG_DIR))
sys.path.insert(
    0, "/nobackup/claude_sim_build/j41m25/pylib"
)  # python-sat is not in the repo environment

import untestable_audit as ua  # type: ignore[import-not-found]  # noqa: E402

SITES = [
    "u_dut.i1.cvtpin_A",
    "u_dut.n1",
    "u_dut.i2.cvtpin_A1",
    "u_dut.n2",
    "u_dut.i3.cvtpin_SCD",
    "u_dut.i4.cvtpin_RESET_B",
    "u_dut.i5.cvtpin_SCE",
    "u_dut.n5",
]


def status_lines(codes):
    return [f"{k} {c}" for k, c in enumerate(codes)]


# ---- pure functions -----------------------------------------------------------------------------------------------------------


def test_fault_site_decodes_site_and_stuck_value():
    assert ua.fault_site(0) == (0, 0)
    assert ua.fault_site(7) == (3, 1)
    assert ua.fault_site(944121) == (472060, 1)


def test_codes_by_index_rejects_a_missing_fault():
    assert ua.codes_by_index(status_lines("DUDU"), 4) == list("DUDU")
    with pytest.raises(ValueError):
        ua.codes_by_index(status_lines("DU"), 4)


def test_faults_by_class_skips_scan_pins_and_names_output_class():
    st = list("UUUUUUUUUUUUDUUD")  # 16 faults = 8 sites
    by = ua.faults_by_class(SITES, st, "U")
    assert "SCD" not in by and "SCE" not in by
    assert by["<output>"] == [2, 3, 6, 7, 14]  # sites n1, n2 and n5 (its sa1 is D)
    assert by["A"] == [0, 1]
    assert by["A1"] == [4, 5]
    assert by["RESET_B"] == [10, 11]
    assert ua.faults_by_class(SITES, st, "D", skip_scan=False)["SCE"] == [12]
    assert ua.faults_by_class(SITES, st, "U", skip_scan=False)["SCD"] == [8, 9]


def test_top_classes_orders_by_size_then_name():
    by = {"B": [1, 2], "A": [3, 4], "C": [5], "D": [6, 7, 8]}
    assert ua.top_classes(by, 3) == ["D", "A", "B"]


def test_draw_is_deterministic_and_independent_per_label():
    items = list(range(1000))
    a = ua.draw(items, 50, 244, "A1")
    assert a == ua.draw(items, 50, 244, "A1")
    assert a != ua.draw(items, 50, 245, "A1")
    assert a != ua.draw(items, 50, 244, "A2")
    assert len(set(a)) == 50 and a == sorted(a)
    assert ua.draw([1, 2, 3], 50, 1, "x") == [1, 2, 3]  # a class smaller than n is taken whole


def test_draw_strata_has_top_classes_and_one_pooled_tail():
    by = {f"c{i}": list(range(i * 100, i * 100 + 20 + i)) for i in range(14)}
    strata = ua.draw_strata(by, 5, 7, 3)
    assert len(strata) == 11
    assert strata[-1]["name"] == ua.TAIL and len(strata[-1]["faults"]) == 7
    assert sum(s["N"] for s in strata) == sum(len(v) for v in by.values())
    assert strata == ua.draw_strata(by, 5, 7, 3)
    top = {s["name"] for s in strata[:-1]}
    tail_faults = set(strata[-1]["faults"])
    assert all(k not in tail_faults for c in top for k in by[c])


def test_wilson_known_values_and_edges():
    lo, hi = ua.wilson(0, 50)
    assert lo == 0.0 and 0.07 < hi < 0.08  # 0/50: upper bound about 7.1 %
    lo, hi = ua.wilson(50, 50)
    assert hi == 1.0 and 0.92 < lo < 0.93
    lo, hi = ua.wilson(25, 50)
    assert 0.36 < lo < 0.37 and 0.63 < hi < 0.64
    assert ua.wilson(0, 0) == (0.0, 1.0)


def test_stratified_point_estimate_and_interval_contain_the_truth_for_all_or_nothing():
    strata = [
        {"name": "a", "N": 1000, "n": 50, "k": {"g": 50}},
        {"name": "b", "N": 500, "n": 50, "k": {"g": 0}},
    ]
    r = ua.stratified(strata, "g")
    assert r["estimate"] == pytest.approx(1000.0)
    assert r["lo"] <= 1000.0 <= r["hi"]
    none = ua.stratified([{"name": "a", "N": 1000, "n": 50, "k": {"g": 0}}], "g")
    assert (
        none["estimate"] == 0.0 and none["lo"] == 0.0 and none["hi"] > 0.0
    )  # zero seen is not zero proven


def test_corrected_tc_counts_artifacts_back_into_the_denominator():
    assert ua.corrected_tc(839742, 944122, 104081, 0) == pytest.approx(99.9644, abs=1e-3)
    assert ua.corrected_tc(839742, 944122, 104081, 10000) < 99.9644
    assert ua.corrected_tc(90, 100, 10, 0) == 100.0


def feat(**kw):
    base = dict(
        excitable=True,
        diff_obs=True,
        struct_obs=3,
        struct_clk=0,
        const_kind="none",
        exc_sat="yes",
        sat="untestable",
        verified=True,
    )
    base.update(kw)
    return base


def test_classify_every_cause():
    assert ua.classify(feat(excitable=False, const_kind="tie")) == ("TIE_OFF", "tie-off")
    assert ua.classify(feat(excitable=False, const_kind="literal"))[1] == "tie-off"
    assert ua.classify(feat(excitable=False, const_kind="root-logic")) == (
        "CONST_FROM_ROOT",
        "constant-from-logic",
    )
    assert ua.classify(feat(excitable=False, const_kind="none")) == (
        "CONST_NOT_IN_NETLIST",
        "artifact",
    )
    assert ua.classify(feat(excitable=False, const_kind="excl-tie")) == (
        "CONST_FROM_EXCLUSION",
        "constant-from-logic",
    )
    assert ua.classify(feat(scan_path_only=True, diff_obs=False)) == (
        "SCAN_SHIFT_PATH",
        "scan-path",
    )
    assert ua.classify(feat(scan_path_only=True, cf_testable=True))[1] == "scan-path"
    assert ua.classify(feat(cf_testable=True)) == ("EXCLUSION_INDUCED", "artifact")
    assert (
        ua.classify(feat(excitable=False, const_kind="root-logic", cf_testable=True))[0]
        == "EXCLUSION_INDUCED"
    )
    assert ua.classify(feat(diff_obs=False)) == ("BLOCKED_BY_CONST", "constant-from-logic")
    assert ua.classify(feat(diff_obs=False, struct_obs=0, struct_clk=2)) == (
        "CLOCK_ONLY",
        "artifact",
    )
    assert ua.classify(feat(diff_obs=False, struct_obs=0)) == ("NO_OBSERVATION", "artifact")
    assert ua.classify(feat(exc_sat="no")) == ("REDUNDANT_CONSTANT_NET", "redundant")
    assert ua.classify(feat()) == ("REDUNDANT_MASKED", "redundant")
    assert ua.classify(feat(sat="unknown", verified=False)) == ("UNRESOLVED", "unresolved")


def test_negative_control_a_detectable_fault_is_never_tie_const_or_redundant():
    """A fault with a verified detecting vector must land in the 'artifact / testable' bucket whatever else the features say."""
    for extra in (dict(), dict(diff_obs=False), dict(exc_sat="no"), dict(const_kind="tie")):
        label, group = ua.classify(feat(sat="testable", verified=True, **extra))
        assert (label, group) == ("TESTABLE", "artifact")
    # an unverified model is not trusted: it does not override the structural cause
    assert ua.classify(feat(sat="testable", verified=False))[1] == "unresolved"


def test_rtl_hint_follows_instances_and_keeps_the_signal(tmp_path):
    (tmp_path / "soc_top.sv").write_text(
        "module soc_top(input clk);\n  timer #(.W(8)) u_timer (.clk(clk));\nendmodule\n"
    )
    (tmp_path / "timer.sv").write_text(
        "module timer(input clk);\n  counter u_cnt (.clk(clk));\n  logic [3:0] compare_val;\nendmodule\n"
    )
    mm = ua.build_modmap(tmp_path)
    assert ua.rtl_hint("u_timer.compare_val[29]", mm) == f"{tmp_path / 'timer.sv'}::compare_val[29]"
    assert ua.rtl_hint("u_timer.u_cnt.q", mm).endswith("::q")
    assert ua.rtl_hint("nothere.x", mm) is None
    assert ua.rtl_hint(None, mm) is None


# ---- graph side: ternary simulation, cones and SAT on a hand-made BLIF -----------------------------------------------------

BLIF = """\
.model t
.inputs a b c d
.outputs y z w v
.names $false
.names $true
1
.names a b n_and
11 1
.names n_and $true y
11 1
.names a ab
1 1
.names a b mix
1 1
0 1
.names mix ab z
10 1
.names c $false w
11 1
.names d dd
1 1
.names dd gate_en
1 1
.names d q_in
1 1
.latch q_in q re gclk 2
.names gate_en clkg
1 1
.names a c r1
11 1
.names a c r2
11 1
.names r1 r2 v
00 0
.end
"""
# y = a&b&1 (a tie input), w = c & 0 (constant 0), z has a reconvergent redundancy, gate_en only drives the clock net clkg
# (modelled as a latch clock below) and v = r1|r2 over identical terms.

BLIF_CLK = BLIF.replace(".latch q_in q re gclk 2", ".latch q_in q re clkg 2")


@pytest.fixture(scope="module")
def graph():
    pytest.importorskip("pysat")
    import audit_graph as ag  # type: ignore[import-not-found]

    b = ag.Blif()
    b.parse(BLIF_CLK)
    return ag, b


def test_blif_parse_ternary_and_levelise(graph):
    ag, b = graph
    nid = b.id
    assert b.val[nid["$false"]] == 0 and b.val[nid["$true"]] == 1
    assert b.val[nid["w"]] == 0  # c & 0
    assert b.val[nid["y"]] == ag.X  # a & b & 1 still depends on inputs
    assert (
        b.n_latches == 1
        and b.obs[nid["q_in"]] == 1
        and b.obs[nid["y"]] == 1
        and b.clk[nid["clkg"]] == 1
    )
    assert all(b.rank[nid[x]] < b.rank[nid["z"]] for x in ("mix", "ab"))


def test_teval_three_valued():
    import audit_graph as ag  # type: ignore[import-not-found]

    assert ag.teval(("11",), 1, (1, ag.X)) == ag.X
    assert ag.teval(("11",), 1, (0, ag.X)) == 0
    assert ag.teval(("00",), 0, (0, 0)) == 0  # off-set phase: the listed cube forces 0
    assert ag.teval(("1-", "-1"), 1, (ag.X, 1)) == 1
    assert ag.teval(("",), 1, ()) == 1 and ag.teval((), 1, ()) == 0


def test_constant_output_is_unexcitable_and_the_opposite_fault_is_blocked_or_seen(graph):
    ag, b = graph
    w = b.id["w"]
    assert b.val[w] == 0
    assert b.cone(w, 1)  # stuck-at-1 on a constant-0 output is excitable and observable at the PO
    assert b.id["w"] not in b.cone(b.id["c"], 0)  # c is masked by the constant 0 at w


def test_sat_classifies_testable_redundant_and_hidden_constant(graph):
    ag, b = graph
    # testable: a stuck-at-0 on n_and is seen at y
    f = b.cone(b.id["n_and"], 0)
    r = ag.sat_testable(b, b.id["n_and"], 0, f)
    assert r["result"] == "testable" and r["verified"]
    # v = r1 | r2 with r1 == r2: r1 stuck-at-0 is masked only when r2 is 1, so it stays testable; a fault on `mix` is not
    assert (
        ag.sat_excitable(b, b.id["mix"], 1) == "no"
    )  # mix = a | ~a is a logic constant 1 that the ternary pass cannot see
    assert ag.sat_excitable(b, b.id["n_and"], 0) == "yes"
    fm = b.cone(b.id["mix"], 1)  # stuck-at-1 on mix: same value as always, so never visible
    r = ag.sat_testable(b, b.id["mix"], 1, fm)
    assert r["result"] == "untestable" and r["verified"]


def test_struct_reach_and_clock_only_sink(graph):
    ag, b = graph
    gates, n_obs, n_clk = b.struct_reach(b.id["gate_en"])
    assert (
        n_obs == 0 and n_clk >= 1
    )  # gate_en feeds only the clock net: structurally unobservable, clock sink reached
    gates, n_obs, n_clk = b.struct_reach(b.id["a"])
    assert n_obs >= 2


def test_random_detect_agrees_with_sat(graph):
    ag, b = graph
    f = b.cone(b.id["n_and"], 0)
    assert ag.random_detect(b, b.id["n_and"], 0, f)
    fm = b.cone(b.id["mix"], 1)
    assert not ag.random_detect(b, b.id["mix"], 1, fm)


def test_cell_model_evaluates_three_valued_and_flags_sequential():
    import audit_graph as ag  # type: ignore[import-not-found]

    nand = ag.CellModel(
        "n",
        "input A;\ninput B;\noutput Y;\n  \\$_AND_  _0_ (\n    .A(A),\n    .B(B),\n    .Y(_1_)\n  );\n  \\$_NOT_  _2_ (\n    .A(_1_),\n    .Y(_3_)\n  );\n  assign Y = _3_;\n",
    )
    assert nand.eval({"A": 0, "B": ag.X}) == {"Y": 1}
    assert nand.eval({"A": 1, "B": 1}) == {"Y": 0}
    assert nand.eval({"A": 1, "B": ag.X}) == {"Y": ag.X}
    tie = ag.CellModel("t", "output HI;\noutput LO;\n  assign HI = 1'h1;\n  assign LO = 1'h0;\n")
    assert tie.eval({}) == {"HI": 1, "LO": 0}
    ff = ag.CellModel(
        "f", "input D;\noutput Q;\n  \\$_DFF_P_  r (\n    .C(D),\n    .D(D),\n    .Q(Q)\n  );\n"
    )
    assert ff.seq and ff.eval({"D": 1}) == {"Q": ag.X}


def test_excl_group_and_assign_tie_parsing():
    import audit_graph as ag  # type: ignore[import-not-found]

    assert ag.excl_group("u_dft_ctrl.u_tap.scan_sel_q[0]") == "u_dft_ctrl.u_tap"
    assert ag.excl_group("mbist_ctl[28]") == "mbist_ctl"
    assert ag.excl_group("u_crypto.g_aes.u_aes.rk_q[0]") == "u_crypto.g_aes.u_aes"
    txt = " assign \\u_dft_ctrl.tap_rst_assert  = 1'b0;\n assign gpu_irq_o = net8185;\n assign \\mbist_ctl[3]  = 1'b1;\n"
    assert [(n.strip(), v) for n, v in ag.ASSIGN_TIE_RE.findall(txt)] == [
        ("\\u_dft_ctrl.tap_rst_assert", "0"),
        ("\\mbist_ctl[3]", "1"),
    ]


def test_free_mode_lifts_a_constant_that_an_exclusion_made(graph):
    """Relaxing a net that carried a constant makes the faults behind it excitable and detectable again; base mode is restored."""
    ag, b = graph
    w, c = b.id["w"], b.id["c"]
    assert b.val[w] == 0 and b.cone(c, 0).get(w) is None  # w = c & 0: c is masked
    # the `$false` constant stands for a tied-off excluded flop; free it
    b.set_relaxed([b.id["$false"]])
    try:
        b.mode(True)
        assert b.val[w] == ag.X and w in b.cone(c, 0)
        r = ag.sat_testable(b, c, 0, b.cone(c, 0))
        assert r["result"] == "testable" and r["verified"]
    finally:
        b.mode(False)
        b.relaxed = set()
    assert b.val[w] == 0 and w not in b.cone(c, 0)


SHARED = """\
.model s
.inputs a
.outputs y
.names $false
.names $false p1
1 1
.names $false p2
1 1
.names p1 p2 n
10 1
.names n a y
11 1
.end
"""


def test_relaxed_loads_of_one_tied_net_share_one_variable():
    """`n = p1 & ~p2` with p1, p2 both the same tied net is never 1: independent free loads would wrongly make `y` testable."""
    pytest.importorskip("pysat")
    import audit_graph as ag  # type: ignore[import-not-found]

    b = ag.Blif()
    b.parse(SHARED)
    p1, p2 = b.id["p1"], b.id["p2"]
    a = b.id["a"]

    def verdict(groups):
        b.set_relaxed([p1, p2], groups)
        b.mode(True)
        try:
            return ag.sat_testable(b, a, 0, b.cone(a, 0))["result"]
        finally:
            b.mode(False)
            b.relaxed, b.relax_group = set(), {}

    assert verdict({p1: "t", p2: "t"}) == "untestable"
    assert verdict({}) == "testable"


def test_scan_path_only_follows_buffers_to_scd_pins():
    import audit_graph as ag  # type: ignore[import-not-found]

    class Cell:
        def __init__(self, typ, pins):
            self.typ, self.pins = typ, pins

    class Design:
        pass

    cd = Design()
    cd.models = {
        "sky130_fd_sc_hd__dlygate4sd3_1": ag.CellModel(
            "d", "input A;\noutput X;\n  assign X = A;\n"
        ),
        "sky130_fd_sc_hd__sdfxtp_1": ag.CellModel("f", "input D;\ninput SCD;\noutput Q;\n"),
        "sky130_fd_sc_hd__and2_1": ag.CellModel("a", "input A;\ninput B;\noutput X;\n"),
    }
    dly, flop, and2 = (f"sky130_fd_sc_hd__{t}" for t in ("dlygate4sd3_1", "sdfxtp_1", "and2_1"))
    cd.cells = {
        "h1": Cell(dly, {"A": "q0", "X": "n1"}),
        "h2": Cell(dly, {"A": "n1", "X": "n2"}),
        "f1": Cell(flop, {"D": "d", "SCD": "n2", "Q": "q1"}),
        "g1": Cell(and2, {"A": "n9", "B": "n9", "X": "o"}),
    }
    cd.loads = {
        "q0": [("h1", "A")],
        "n1": [("h2", "A")],
        "n2": [("f1", "SCD")],
        "n9": [("g1", "A")],
    }
    rec = {"inst": "h1", "dir": "in", "net": "q0"}
    assert ua.scan_path_only(cd, rec)  # buffer -> buffer -> SCD
    assert not ua.scan_path_only(
        cd, {"inst": "g1", "dir": "in", "net": "n9"}
    )  # a logic gate is not a buffer
    cd.loads["n2"] = [("f1", "SCD"), ("g1", "A")]  # now it also feeds logic
    assert not ua.scan_path_only(cd, rec)
    assert not ua.scan_path_only(
        cd, {"inst": "h1", "dir": "out", "net": "n1"}
    )  # n1 -> h2 -> n2 now reaches the gate
