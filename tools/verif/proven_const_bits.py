#!/usr/bin/env python3
"""List the UNCOVERED toggle points of a module that are provably constant (bead xkw5).

A toggle point that never toggles is either a test gap or a bit that cannot move.  Only the second
kind may be waived (``coverage_waivers.txt``, category b), and "cannot move" needs evidence rather
than a reading of the RTL.  This tool produces that evidence with yosys:

  1. read the module's RTL with yosys-slang (default parameters), ``proc; flatten``;
  2. keep every named wire (``setattr -set keep 1 w:*``), then ``opt -full; opt_dff -sat``
     twice.  ``opt_dff -sat`` replaces a flip-flop by a constant when SAT shows its D input can
     only ever equal its reset value, so a register bit with WMASK = 0 and no hardware write, a
     zero-extended hardware-write bit, or a read-mux bit no register drives all come out as
     constants;
  3. read the netlist back as JSON and look up each uncovered Verilator toggle point
     (``name[bit]:0->1``) in it.  A point whose bit is a constant is PROVEN; every other point is
     reported as OTHER (a test gap until shown otherwise).

Unpacked arrays (``hw_wdata_i``, ``hw_wen_i``, ``regs_o`` ...) are flattened by slang with element
0 in the MOST significant position (checked against ``timer``: ``hw_wen_i == 4'b1000`` for its one
hardware-written register, element 0).

Usage::

    proven_const_bits.py --dat merged.dat [--dat more.dat] MODULE [MODULE ...]

prints one JSON object per module: ``{"module", "proven": [...], "other": [...]}``.  Needs the nix
yosys + yosys-slang paths below (override with YOSYS= / SLANG_PLUGIN=, the same convention as
``equiv_sv2v_module.sh``).  It never edits a waiver file: the waivers it justifies are written by
hand, with the file:line reasons, so each stays reviewable.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import coverage_report as cr  # noqa: E402  pylint: disable=wrong-import-position

YOSYS = os.environ.get(
    "YOSYS", "/nix/store/4bmfi4470w0i3ixcaidfki18d3fyqvva-yosys-with-plugins-0.62/bin/yosys"
)
SLANG = os.environ.get(
    "SLANG_PLUGIN",
    "/nix/store/07xn6zd11qvkp8h65gwycfisr3x9hk4f-yosys-slang/share/yosys/plugins/slang.so",
)
SOURCES = (
    "rtl/soc/axi_pkg.sv",
    "rtl/soc/soc_addr_map_pkg.sv",
    "rtl/soc/soc_periph_map_pkg.sv",
    "rtl/soc/apb4_register_bank.sv",
    "rtl/soc/axi_lite_register_bank.sv",
    "rtl/soc/cdc/cdc_sync.sv",
    "rtl/soc/cdc/cdc_reset_sync.sv",
    "rtl/soc/dft/dft_rst_mux.sv",
    "rtl/soc/dft/dft_clk_mux.sv",
    "rtl/soc/dft/mem_collar.sv",
    "rtl/mem/sram_1rw_256x32_freepdk45.sv",
    "rtl/periph/timer.sv",
    "rtl/periph/uart_controller.sv",
    "rtl/periph/spi_controller.sv",
    "rtl/periph/interrupt_controller.sv",
    "rtl/periph/pwm_controller.sv",
    "rtl/periph/watchdog_timer.sv",
    "rtl/periph/gpio_controller.sv",
    "rtl/periph/trng.sv",
    "rtl/periph/trng_lfsr_entropy.sv",
    "rtl/periph/i2c_controller.sv",
    "rtl/periph/i2c_bit_engine.sv",
    "rtl/periph/dma_engine.sv",
    "rtl/soc/pmu.sv",
    "rtl/soc/pll/pll_apb_regs.sv",
    "rtl/soc/pll/pll_clkgen_stub.sv",
    # pll_clkgen selects the STUB or RNM implementation with a string parameter; the RNM arm is
    # pruned at elaboration, so pll_rnm.sv (real-number model) is neither needed nor listed.
    "rtl/soc/pll/pll_clkgen.sv",
    "rtl/soc/pll/pll_subsystem.sv",
    "rtl/periph/crypto_accel.sv",
    "rtl/periph/aes128_core.sv",
    "rtl/periph/sha256_core.sv",
    "rtl/npu/npu_top.sv",
    "rtl/npu/npu_mac_array.sv",
    "rtl/npu/npu_weight_mem.sv",
)
# Unpacked arrays of 32-bit words (two indices in the point name) or of 1-bit flags (one index).
UNPACKED = {"hw_wdata_i", "hw_wen_i", "regs_o", "regs", "hw_wdata", "hw_wen", "regs_out"}
NAME_RE = re.compile(r"^([A-Za-z_][\w$.]*)((?:\[\d+\])*):(\d)->(\d)$")  # '.' = generate scope


def constant_nets(module: str, workdir: Path) -> dict[str, list]:
    """Return {net name: bit list} of the optimised, flattened module (const bits are '0'/'1')."""
    sources = [s for s in SOURCES if (ROOT / s).exists()]
    script = workdir / f"{module}.ys"
    out = workdir / f"{module}.json"
    script.write_text(
        f"plugin -i {SLANG}\n"
        "read_slang --allow-use-before-declare --ignore-unknown-modules "
        f"-I rtl/soc -I rtl/soc/cdc -I rtl/soc/dft -I rtl/mem -I rtl/periph -I rtl/npu --top {module} {' '.join(sources)}\n"
        f"hierarchy -top {module}\nproc\nflatten\nsetattr -set keep 1 w:*\n"
        "opt -full\nopt_dff -sat\nopt -full\nopt_dff -sat\nopt_clean\n"
        f"write_json {out}\n"
    )
    res = subprocess.run(
        [YOSYS, "-q", "-s", str(script)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=1800,
        check=False,
    )
    if res.returncode != 0:
        raise SystemExit(f"yosys failed for {module}:\n{res.stdout[-1500:]}\n{res.stderr[-1500:]}")
    nets = json.loads(out.read_text())["modules"][module]["netnames"]
    return {n: d["bits"] for n, d in nets.items()}


def const_value(nets: dict[str, list], sig: str, idx: list[int]) -> str | None:
    """'0' / '1' if the named bit is a proven constant, else None."""
    bits = nets.get(sig)
    if bits is None:
        return None
    width = len(bits)
    if sig in UNPACKED and len(idx) == 2:
        elem, bit = idx
        pos = (width // 32 - 1 - elem) * 32 + bit
    elif sig in UNPACKED and len(idx) == 1:
        pos = width - 1 - idx[0]
    elif len(idx) == 1:
        pos = idx[0]
    elif not idx:
        pos = 0
    else:
        return None
    if not 0 <= pos < width:
        return None
    val = bits[pos]
    return val if val in ("0", "1") else None


def classify(points: list, module: str, workdir: Path) -> dict:
    """Split the module's never-hit toggle points into proven-constant and other."""
    hit: dict[str, bool] = {}
    for pt in points:
        if pt.module.split("__")[0] == module and pt.kind == "toggle":
            hit[pt.name] = hit.get(pt.name, False) or pt.count > 0
    nets = constant_nets(module, workdir)
    proven, other = [], []
    for name, was_hit in sorted(hit.items()):
        if was_hit:
            continue
        match = NAME_RE.match(name)
        value = None
        if match:
            idx = [int(x) for x in re.findall(r"\[(\d+)\]", match.group(2))]
            value = const_value(nets, match.group(1), idx)
        (proven if value is not None else other).append(name)
    return {"module": module, "proven": proven, "other": other}


def main(argv: list[str]) -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", maxsplit=1)[0])
    parser.add_argument("--dat", action="append", required=True, type=Path)
    parser.add_argument("modules", nargs="+")
    args = parser.parse_args(argv)
    points = [pt for dat in args.dat for pt in cr.parse_dat(dat)]
    with tempfile.TemporaryDirectory() as tmp:
        for module in args.modules:
            print(json.dumps(classify(points, module, Path(tmp))))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
