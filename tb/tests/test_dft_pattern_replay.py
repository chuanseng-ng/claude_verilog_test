# ruff: noqa: E501
"""Tests for the scan-replay helpers of tools/dft/atpg: replay_netlist.py, replay_vectors.py, fault_sample.py, run_replay.py.

Doc: tm:ch:dft-architecture
"""

import json
import sys
from pathlib import Path

import pytest

ATPG_DIR = Path(__file__).resolve().parents[2] / "tools" / "dft" / "atpg"
sys.path.insert(0, str(ATPG_DIR))

import fault_sample as fs  # type: ignore[import-not-found]  # noqa: E402
import replay_netlist as rn  # type: ignore[import-not-found]  # noqa: E402
import replay_vectors as rv  # type: ignore[import-not-found]  # noqa: E402
import run_replay as rr  # type: ignore[import-not-found]  # noqa: E402

NETLIST = """\
module soc_top (a_i, y_o);
  input a_i;
  output y_o;
  wire n1, n2;
 sky130_fd_sc_hd__and2_1 g1 (.A(a_i), .B(\\u.x[3] ), .X(n1));
 sky130_fd_sc_hd__inv_1 g2 (.A(n1), .Y(n2));
 sky130_fd_sc_hd__buf_1 g3 (.A(n2), .X(y_o));
endmodule
"""


def test_conn_bits_handles_scalar_vector_concat_and_escaped_names():
    assert rn.conn_bits("n1", 1) == ["n1"]
    assert rn.conn_bits("bus", 3) == ["bus[0]", "bus[1]", "bus[2]"]
    assert rn.conn_bits("{a, b, c}", 3) == [
        "c",
        "b",
        "a",
    ]  # MSB first in the text, LSB first in the result
    assert rn.conn_bits("{\\u.x[3] , b}", 2) == ["b", "\\u.x[3] "]
    assert rn.conn_bits("", 2) == [None, None]
    with pytest.raises(SystemExit):
        rn.conn_bits("{a, b}", 3)


def test_inject_pins_branch_and_stem_faults_are_selectable_and_leave_other_pins_alone():
    out = rn.inject_pins(NETLIST, "soc_top", [("g1", "B", "in", 1), ("g2", "Y", "out", 0)])
    assert "module soc_top (a_i, y_o, fsel_0, fsel_1);" in out
    assert (
        ".B(cvtf_0)" in out and "assign cvtf_0 = fsel_0 ? 1'b1 : \\u.x[3] ;" in out
    )  # escaped net keeps its terminator
    assert ".Y(cvtf_1)" in out and "assign n2 = fsel_1 ? 1'b0 : cvtf_1;" in out
    assert ".A(a_i)" in out and ".A(n1)" in out


def test_inject_pins_refuses_a_missing_instance_a_repeated_pin_and_an_unconnected_pin():
    with pytest.raises(SystemExit):
        rn.inject_pins(NETLIST, "soc_top", [("nope", "A", "in", 0)])
    with pytest.raises(SystemExit):
        rn.inject_pins(NETLIST, "soc_top", [("g1", "A", "in", 0), ("g1", "A", "in", 1)])
    with pytest.raises(SystemExit):
        rn.inject_pins(NETLIST, "soc_top", [("g1", "C", "in", 0)])


def plan():
    return {
        "inputs": [{"kind": "pin"}, {"kind": "bb"}, {"kind": "clock"}],
        "outputs": [{"kind": "pin"}],
        "latches": [
            {"kind": "scan", "chain": 0, "pos": 0, "masked": False},
            {"kind": "scan", "chain": 0, "pos": 1, "masked": True},
            {"kind": "scan", "chain": 1, "pos": 0, "masked": False},
            {"kind": "free", "inst": "u0"},
        ],
        "chain_len": [2, 1, 0],
    }


def test_vectors_load_unload_and_mask_follow_the_shift_convention():
    pat = "101" + "1" + "0" + "1" + "1"  # inputs, then latch Q: (c0p0)=1 (c0p1)=0 (c1p0)=1 free=1
    exp = "1" + "0" + "1" + "1" + "0"  # 1 output, then latch D: c0p0=0 c0p1=1 c1p0=1 free=0
    pi, po, ld, ex, mk = rv.build(plan(), pat, exp, 1)
    assert pi == "10" + "0" + "1"  # clock bit forced 0, free-latch bit appended from the pattern
    assert po == "1"
    # chain 0 holds [1, 0]: position 1 is loaded first (value 0), then position 0 (value 1)
    assert [b & 1 for b in ld] == [0, 1]
    assert [(b >> 1) & 1 for b in ld] == [
        0,
        1,
    ]  # chain 1 has one flop: one pad edge in front, then its value
    # unload: last position first; D of chain 0 = [0, 1] -> 1, 0; position 1 is hold-masked -> mask 0 then 1
    assert [b & 1 for b in ex] == [1, 0]
    assert [b & 1 for b in mk] == [0, 1]
    assert [(b >> 1) & 1 for b in mk] == [1, 0]
    assert all(b >> 2 == 0 for b in mk)  # chains with no flops are never compared


def test_words_pack_lsb_first():
    assert rv.words("1" + "0" * 31 + "1") == [1, 1]
    assert rv.words("0101") == [0b1010]


def test_fault_sample_is_seeded_and_never_mixes_groups(tmp_path):
    sites = [f"u_dut.i{k}.cvtpin_{p}" for k, p in enumerate(["A", "B", "SCD", "SCE"] * 10)]
    (tmp_path / "cut_sites.txt").write_text("\n".join(sites) + "\n")
    n = 2 * len(sites)
    full = ["D" if k % 3 else "U" for k in range(n)]
    sub = ["D" if k % 2 == 0 else "N" for k in range(n)]
    (tmp_path / "full.txt").write_text("\n".join(f"{k} {c}" for k, c in enumerate(full)) + "\n")
    (tmp_path / "sub.txt").write_text("\n".join(f"{k} {c}" for k, c in enumerate(sub)) + "\n")
    args = [
        "--cut-dir",
        str(tmp_path),
        "--status",
        str(tmp_path / "full.txt"),
        "--status-sub",
        str(tmp_path / "sub.txt"),
        "--n-detected",
        "5",
        "--n-untestable",
        "3",
        "--n-scd",
        "4",
        "--n-sce",
        "2",
    ]
    fs.main(args + ["--out", str(tmp_path / "a.json")])
    fs.main(args + ["--out", str(tmp_path / "b.json")])
    a = json.loads((tmp_path / "a.json").read_text())
    assert a == json.loads((tmp_path / "b.json").read_text())
    for f in a:
        if f["group"] == "detected":
            assert (
                f["full_status"] == "D"
                and f["sub_status"] == "D"
                and f["pin"] not in ("SCD", "SCE")
            )
        if f["group"] == "untestable":
            assert f["full_status"] == "U" and f["pin"] not in ("SCD", "SCE")
        if f["group"] == "scd":
            assert f["pin"] == "SCD"
    assert {f["group"] for f in a} == {"detected", "untestable", "scd", "sce"}


def test_run_replay_parses_the_tb_result_line_and_treats_any_mismatch_as_detection():
    line = "RESULT mode=pat tap=0 fault=3 npat=20 so_mismatch=0 first_so_pat=-1 first_so_chains=0x0 po_mismatch=2 first_po_pat=4"
    m = rr.RES.search("noise\n" + line + "\n")
    assert m and int(m.group(8)) == 2 and int(m.group(3)) == 3
    assert rr.RES.search("RESULT garbage") is None
