"""act_only_flops.py classifies flops by the Verilator region of their Q assignment (bead j41m.29).  Doc: tm:ch:dft-architecture:1814-chain2-cause"""
import json
import subprocess
import sys
from pathlib import Path

TOOL = Path(__file__).resolve().parents[2] / "tools" / "dft" / "atpg" / "act_only_flops.py"

SRC = """void Vreplay_top___024root___act_sequent__TOP__1(Vreplay_top___024root* vlSelf) {
    vlSelfRef.replay_top__DOT__u_dut__DOT___100___DOT__buf_Q = 1U;
    vlSelfRef.replay_top__DOT__u_dut__DOT___101___DOT__buf_Q = 1U;
}
void Vreplay_top___024root___nba_sequent__TOP__2(Vreplay_top___024root* vlSelf) {
    vlSelfRef.replay_top__DOT__u_dut__DOT___101___DOT__buf_Q = 0U;
    vlSelfRef.replay_top__DOT__u_dut__DOT___102___DOT__buf_Q = 0U;
}
"""


def run(obj: Path, mp: Path, neg: bool = False):
    r = subprocess.run([sys.executable, str(TOOL), str(obj), "--map", str(mp), "--json"], capture_output=True, text=True)
    return r


def test_act_only_found(tmp_path):
    (tmp_path / "Vreplay_top___024root__0.cpp").write_text(SRC)
    mp = tmp_path / "map.json"
    mp.write_text(json.dumps({"chains": [["_099_", "_100_", "_101_", "_102_"]]}))
    out = json.loads(run(tmp_path, mp).stdout)
    assert out["act_only"] == ["_100_"]  # _101_ is in both regions, _102_ only in nba
    assert out["chains"]["0"]["positions"] == [1]
    assert out["chains"]["0"]["latency_if_shift_race"] == 3


def test_negative_control_no_act_function(tmp_path):
    (tmp_path / "Vreplay_top___024root__0.cpp").write_text(SRC.replace("_act_sequent_", "_nba_sequent_"))
    r = run(tmp_path, tmp_path / "none.json")
    assert r.returncode == 2  # no act-region assignment: the tool refuses instead of reporting an empty list
