"""race_free.py: shadow flops against the Verilator Active-region race of the zero-delay replay.

Doc: tm:ch:dft-architecture:1814-chain2-cause
Structure tests need no tools.  The simulation test builds a 4-flop chain behind a derived clock
with Verilator and measures the chain latency: 3 without the fix (the race), 4 with it.
It is skipped when Verilator or the Sky130 models are not on the host.
"""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

PDK_VER = "0fe599b2afb6708d281543108caf8310912f54af"
ATPG = Path(__file__).resolve().parents[2] / "tools" / "dft" / "atpg"
sys.path.insert(0, str(ATPG))
import race_free  # type: ignore[import-not-found]  # noqa: E402

NETLIST = """module soc_top(si, clk, so, g_q);
  input si, clk;
  output so, g_q;
  wire n0, nx, nb, n2, n3, rn, ck, gd;
  wire one = 1'b1;
  wire zero = 1'b0;
  sky130_fd_sc_hd__mux2_1 mk (.A0(g_q), .A1(clk), .S(one), .X(ck));
  sky130_fd_sc_hd__sdfxtp_1 f0 (.CLK(ck), .D(zero), .SCD(si), .SCE(one), .Q(n0));
  sky130_fd_sc_hd__sdfxtp_1 fx (.CLK(ck), .D(zero), .SCD(n0), .SCE(one), .Q(nx));
  sky130_fd_sc_hd__dlygate4sd3_1 hb (.A(nx), .X(nb));
  sky130_fd_sc_hd__sdfxtp_1 f2 (.CLK(ck), .D(zero), .SCD(nb), .SCE(one), .Q(n2));
  sky130_fd_sc_hd__sdfxtp_1 f3 (.CLK(ck), .D(zero), .SCD(n2), .SCE(one), .Q(n3));
  sky130_fd_sc_hd__and2_1 ag (.A(nx), .B(one), .X(rn));
  sky130_fd_sc_hd__inv_1 gi (.A(g_q), .Y(gd));
  sky130_fd_sc_hd__sdfrtp_1 g (.CLK(ck), .D(gd), .SCD(zero), .SCE(zero), .RESET_B(rn), .Q(g_q));
  assign so = n3;
endmodule
"""

TB = """#include "Vmini.h"
#include "verilated.h"
#include <cstdio>
int main(int argc, char** argv) {
  Verilated::commandArgs(argc, argv); Vmini* d = new Vmini; int first = -1;
  for (int i = 0; i < 4; i++) { d->si = 0; d->clk = 0; d->eval(); d->clk = 1; d->eval(); }
  for (int t = 0; t < 12; t++) {
    d->si = (t == 0); d->clk = 0; d->eval();
    if (first < 0 && d->so) first = t;
    d->clk = 1; d->eval();
  }
  printf("LATENCY %d\\n", first); return 0; }
"""


def test_structure():
    out, info = race_free.shadow(NETLIST, ["fx", "g"])
    assert (
        ".SCD(rf_net" in out.split("sky130_fd_sc_hd__sdfxtp_1 f2")[1].split(";")[0]
    )  # data load of fx.Q moved to the shadow net
    assert (
        "sky130_fd_sc_hd__and2_1 ag (.A(nx)" in out
    )  # trigger side (async reset) keeps the original net
    assert ".RESET_B(rn)" in out and ".Q(nx)" in out  # the act-only flop itself is unchanged
    assert "rf_fx" in out and "rf_hb" in out  # shadow flop and shadow of the delay gate
    assert (
        ".D(gd)" in out.split("sky130_fd_sc_hd__sdfrtp_1 g ")[1].split(";")[0] or ".D(rf_net" in out
    )  # a flop behind a flop in the set takes shadow data
    assert info["shadow_cells"] >= 2


def test_negative_control_nothing_to_do():
    out, info = race_free.shadow(NETLIST, [])
    assert out == NETLIST and info["shadow_cells"] == 0


def test_unknown_flop_stops():
    with pytest.raises(SystemExit):
        race_free.shadow(NETLIST, ["nope"])


def _tools():
    nix = "/nix/store/xjx9zx3vaz367c7lbnvsd1isvqfkmgg7-verilator-5.048"
    vb = (
        os.environ.get("VERILATOR_BIN")
        or shutil.which("verilator")
        or (nix + "/bin/verilator" if Path(nix, "bin/verilator").exists() else None)
    )
    if vb and vb.startswith(nix):
        os.environ.setdefault("VERILATOR_ROOT", nix + "/share/verilator")
    pdk = os.environ.get("PDK_VLOG") or str(
        Path.home()
        / ".ciel/ciel/sky130/versions"
        / PDK_VER
        / "sky130A/libs.ref/sky130_fd_sc_hd/verilog"
    )
    return vb, pdk


@pytest.mark.skipif(
    not _tools()[0] or not Path(_tools()[1], "sky130_fd_sc_hd.v").exists(),
    reason="Verilator or Sky130 models missing",
)
def test_simulated_latency(tmp_path):
    vb, pdk = _tools()

    def latency(netlist: str, tag: str) -> int:
        d = tmp_path / tag
        d.mkdir()
        (d / "n.v").write_text(netlist)
        (d / "tb.cpp").write_text(TB)
        cmd = [
            vb,
            "--cc",
            "--exe",
            "--build",
            "-Wno-fatal",
            "-Wno-lint",
            "-Wno-style",
            "-Wno-TIMESCALEMOD",
            "--timing",
            "-DFUNCTIONAL",
            "-DUNIT_DELAY=",
            "--Mdir",
            str(d / "obj"),
            "--top-module",
            "soc_top",
            "--prefix",
            "Vmini",
            "-o",
            "Vmini",
            f"{pdk}/primitives.v",
            f"{pdk}/sky130_fd_sc_hd.v",
            str(d / "n.v"),
            str(d / "tb.cpp"),
        ]
        r = subprocess.run(cmd, capture_output=True, text=True)
        assert r.returncode == 0, r.stderr[-500:]
        o = subprocess.run([str(d / "obj" / "Vmini")], capture_output=True, text=True).stdout
        return int(o.split("LATENCY")[1])

    base = latency(NETLIST, "base")
    assert base == 3  # the race: the chain f0,fx,f2,f3 is one flop short (negative control)
    act = tmp_path / "act"
    act.mkdir()
    # classify the unfixed build exactly as the flow does
    r = subprocess.run(
        [sys.executable, str(ATPG / "act_only_flops.py"), str(tmp_path / "base" / "obj"), "--json"],
        capture_output=True,
        text=True,
    )
    names = json.loads(r.stdout)["act_only"]
    assert "fx" in names
    fixed, _ = race_free.shadow(NETLIST, names)
    assert latency(fixed, "fixed") == 4
