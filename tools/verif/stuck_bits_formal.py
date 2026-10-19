#!/usr/bin/env python3
"""Prove with SymbiYosys that never-toggling coverage bits are STUCK after reset (bead xkw5).

``proven_const_bits.py`` finds bits that yosys can prove constant structurally (``opt_dff -sat``).
It cannot reach a register-bank flop that is held at its reset value by ``WMASK = 0``: with no
initial value the flop is "unknown" until reset is reasoned about.  This tool closes that gap with
an unbounded model-checking proof (ABC ``pdr``) under one explicit assumption, the same one every
simulation in this repo satisfies: the design is reset before it is used.

For each module it

  1. takes the module's toggle points that were never hit in either direction (from the merged
     Verilator ``.dat``) - a bit that already rose or fell is not stuck;
  2. generates a wrapper that instantiates the module (default parameters, or ``--param``), leaves
     every input free (any APB/AXI traffic, any reset pattern after the first), assumes the reset
     is asserted for the first two clock cycles, and asserts that each candidate bit, read through a
     hierarchical reference, equals the value it had at cycle 2 for ever after (``stuck`` -
     a combinational bit is covered too: the value must not depend on the free inputs either);
  3. runs ``sby`` (``abc pdr``, unbounded) on all candidates, and bisects on FAIL until every
     candidate is classified.

A PASS is a proof for ALL input sequences, not a lookup in a netlist, and applies to the elaborated
module with the parameters the wrapper uses.  A FAIL means the bit can move for some input sequence,
so it is a test gap (or a bit that only a very long run reaches), never a waiver.  The result is
``{"module", "proven": [...], "failed": [...], "unknown": [...], "error": str|null}`` ("unknown" =
the proof budget ran out: a bit that needs a very long run to move is not provable stuck, so it
is reported, never waived) with bits written like
the coverage point names without the direction (``regs_o[3][5]``).

Needs the nix yosys + yosys-slang + sby paths below (override with YOSYS_BIN= / SLANG_PLUGIN=).
Like ``proven_const_bits.py`` it never edits the waiver file.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import resource
import subprocess
import sys
import tempfile
import threading
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import coverage_report as cr  # noqa: E402  pylint: disable=wrong-import-position
import proven_const_bits as pcb  # noqa: E402  pylint: disable=wrong-import-position

YOSYS_BIN = os.environ.get("YOSYS_BIN", str(Path(pcb.YOSYS).parent))
SLANG = pcb.SLANG
NAME_RE = re.compile(r"^([A-Za-z_][\w$.]*)((?:\[\d+\])*):(\d)->(\d)$")
CLOCKS = ("clk", "clk_i", "pclk", "aclk", "clock")
RESETS = ("rst_n", "rst_n_i", "rst_ni", "presetn", "rstn", "aresetn", "reset_n")
BMC_TIMEOUT_S = 25
TOP_TIMEOUT_S = 45  # per-chunk proof budget; halved on every bisection level
MIN_TIMEOUT_S = 15
INCLUDES = ("rtl/soc", "rtl/soc/cdc", "rtl/soc/dft", "rtl/mem", "rtl/periph", "rtl/npu", "rtl/soc/pll")


TIES: dict[str, str] = {}  # input port -> constant (``--tie``); e.g. scan_mode_i=0 = functional mode


class FormalError(Exception):
    """A module the tool cannot wrap or a tool failure."""


def candidate_bits(
    points: list, module: str, waivers: list | None = None, skip: re.Pattern | None = None
) -> list[str]:
    """Bits of ``module`` for which neither toggle direction was ever hit.

    Points an existing waiver already covers are left out (they need no new proof), and so are
    bits whose name matches ``skip`` (counters a long run reaches, not a stuck bit).
    """
    seen: dict[str, dict[str, bool]] = defaultdict(dict)
    for pt in points:
        if pt.module.split("__")[0] != module or pt.kind != "toggle":
            continue
        match = NAME_RE.match(pt.name)
        if not match:
            continue
        if any(w.matches(module, "toggle", pt.name) for w in waivers or []):
            continue
        if skip is not None and skip.search(match.group(1) + match.group(2)):
            continue
        bit = match.group(1) + match.group(2)
        direction = f"{match.group(3)}{match.group(4)}"
        seen[bit][direction] = seen[bit].get(direction, False) or pt.count > 0
    return sorted(b for b, d in seen.items() if not any(d.values()))


def _sources() -> list[str]:
    return [str(ROOT / s) for s in pcb.SOURCES if (ROOT / s).exists()]


def _read_cmd(top: str, extra: list[str], params: dict[str, str]) -> str:
    incs = " ".join(f"-I {ROOT / i}" for i in INCLUDES)
    gen = " ".join(f"-G {k}={v}" for k, v in params.items())
    return (
        f"read_slang --allow-use-before-declare --ignore-unknown-modules {incs} {gen} "
        f"--top {top} {' '.join(extra + _sources())}"
    )


def module_ports(module: str, params: dict[str, str], workdir: Path) -> list[tuple[str, str, int]]:
    """(name, direction, width) of the module's ports, from a yosys-slang elaboration."""
    out = workdir / f"{module}_ports.json"
    script = workdir / f"{module}_ports.ys"
    script.write_text(
        f"plugin -i {SLANG}\n{_read_cmd(module, [], params)}\n"
        f"hierarchy -top {module}\nwrite_json {out}\n"
    )
    res = subprocess.run(
        [pcb.YOSYS, "-q", "-s", str(script)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=900,
        check=False,
    )
    if res.returncode != 0:
        raise FormalError(f"port elaboration failed:\n{res.stdout[-800:]}\n{res.stderr[-800:]}")
    ports = json.loads(out.read_text())["modules"][module]["ports"]
    return [(n, p["direction"], len(p["bits"])) for n, p in ports.items()]


def _pick(ports: list[tuple[str, str, int]], names: tuple[str, ...], what: str) -> str:
    found = [n for n, d, w in ports if d == "input" and w == 1 and n in names]
    if len(found) != 1:
        raise FormalError(f"cannot identify the {what} among {[n for n, d, _ in ports if d == 'input']}")
    return found[0]


def hier_ref(bit: str) -> str:
    """Hierarchical reference into the DUT instance for a coverage bit name."""
    return f"dut.{bit}"


def wrapper_text(
    module: str, params: dict[str, str], ports: list[tuple[str, str, int]], bits: list[str]
) -> str:
    """SystemVerilog wrapper asserting every ``bits`` entry is stuck after the reset."""
    clk = _pick(ports, CLOCKS, "clock")
    rst = _pick(ports, RESETS, "active-low reset")
    decl, conn = [], []
    for name, direction, width in ports:
        rng = f"[{width - 1}:0] " if width > 1 else ""
        if name == clk:
            conn.append(f".{name}(clk)")
            continue
        if name in TIES:
            conn.append(f".{name}({width}'d{TIES[name]})")
            continue
        if name == rst:
            conn.append(f".{name}(rst_n)")
            continue
        if direction == "input":
            decl.append(f"    input logic {rng}{name}_in,")
            conn.append(f".{name}({name}_in)")
        else:
            decl.append(f"    logic {rng}{name}_w;")
            conn.append(f".{name}({name}_w)")
    ins = [d for d in decl if d.strip().startswith("input")]
    outs = [d for d in decl if not d.strip().startswith("input")]
    pstr = ""
    if params:
        pstr = " #(" + ", ".join(f".{k}({v})" for k, v in params.items()) + ")"
    n_bits = len(bits)
    cur = ", ".join(hier_ref(b) for b in reversed(bits))
    return (
        f"module fv_{module} (\n    input logic clk,\n    input logic rst_n,\n"
        + "\n".join(ins).rstrip(",")
        + "\n);\n"
        + "\n".join(outs)
        + f"\n    {module}{pstr} dut ({', '.join(conn)});\n"
        "    logic [1:0] n;\n    initial n = 2'd0;\n"
        "    always_ff @(posedge clk) if (n != 2'd3) n <= n + 2'd1;\n"
        "    always_comb if (n < 2'd2) assume (!rst_n);\n"
        f"    logic [{n_bits - 1}:0] cur, ref_q;\n"
        f"    assign cur = {{{cur}}};\n"
        "    always_ff @(posedge clk) begin\n"
        "        if (n == 2'd2) ref_q <= cur;\n"
        f"        if (n == 2'd3) for (int i = 0; i < {n_bits}; i++) assert (cur[i] == ref_q[i]);\n"
        "    end\nendmodule\n"
    )


def _limit_memory() -> None:
    """preexec hook: keep one ABC/PDR run under 3 GiB so three of them fit next to a PD flow."""
    resource.setrlimit(resource.RLIMIT_AS, (3 << 30, 3 << 30))


def run_sby(
    module: str,
    params: dict[str, str],
    ports: list,
    bits: list[str],
    workdir: Path,
    tag: str,
    timeout_s: int,
) -> str:
    """"pass" if every bit is proven stuck, "fail" if one can move, "unknown" on timeout/memory."""
    wrap = workdir / f"fv_{module}_{tag}.sv"
    wrap.write_text(wrapper_text(module, params, ports, bits))
    env = dict(os.environ, PATH=f"{YOSYS_BIN}:{os.environ['PATH']}")
    script = (
        f"[script]\nplugin -i {SLANG}\n{_read_cmd('fv_' + module, [str(wrap)], {})}\n"
        f"prep -flatten -top fv_{module}\n\n[files]\n"
    )
    # A short bounded search first: it finds a bit that moves within a few cycles in seconds,
    # where PDR (which proves, but does not hunt for counterexamples) can burn its whole budget.
    for mode, engine, extra, budget in (
        ("bmc", "abc bmc3", "depth 24\n", min(timeout_s, BMC_TIMEOUT_S)),
        ("prove", "abc pdr", "", timeout_s),
    ):
        sby = workdir / f"fv_{module}_{tag}_{mode}.sby"
        sby.write_text(
            f"[options]\nmode {mode}\naigsmt none\nmulticlock on\n{extra}timeout {budget}\n\n"
            f"[engines]\n{engine}\n\n{script}"
        )
        res = subprocess.run(
            ["sby", "-f", "-d", str(workdir / f"run_{module}_{tag}_{mode}"), str(sby)],
            cwd=workdir,
            capture_output=True,
            text=True,
            env=env,
            timeout=budget + 120,
            check=False,
            preexec_fn=_limit_memory,
        )
        text = res.stdout + res.stderr
        if re.search(r"engine_\d \(abc \w+\) returned FAIL", text, re.I):
            return "fail"
        if mode == "prove" and re.search(r"engine_\d \(abc pdr\) returned pass", text, re.I):
            return "pass"
        if "Reached TIMEOUT" in text and not re.search(r"engine_\d \(abc \w+\) returned", text, re.I):
            return "unknown"  # the model itself did not build inside the budget
        if mode == "bmc" and not re.search(r"engine_\d \(abc bmc3\) returned (pass|timeout)", text, re.I):
            raise FormalError(f"sby bmc gave no verdict for {module}/{tag}:\n{text[-1500:]}")
    return "unknown"


def classify(
    module: str, params: dict[str, str], bits: list[str], workdir: Path, jobs: int
) -> dict:
    """Prove / bisect the candidate bits; returns the result object."""
    result: dict = {"module": module, "proven": [], "failed": [], "unknown": [], "error": None}
    if not bits:
        return result
    try:
        ports = module_ports(module, params, workdir)
        counter = [0]
        lock = threading.Lock()

        def solve(chunk: list[str], timeout_s: int) -> tuple[list[str], list[str], list[str]]:
            with lock:
                counter[0] += 1
                tag = f"c{counter[0]}"
            verdict = run_sby(module, params, ports, chunk, workdir, tag, timeout_s)
            print(f"  {module}/{tag}: {len(chunk)} bits -> {verdict}", file=sys.stderr, flush=True)
            if verdict == "pass":
                return chunk, [], []
            if len(chunk) == 1:
                return ([], chunk, []) if verdict == "fail" else ([], [], chunk)
            if verdict == "unknown" and timeout_s <= MIN_TIMEOUT_S:
                return [], [], chunk
            mid = len(chunk) // 2
            half = max(MIN_TIMEOUT_S, timeout_s // 2)
            left = solve(chunk[:mid], half)
            right = solve(chunk[mid:], half)
            return tuple(a + b for a, b in zip(left, right))  # type: ignore[return-value]

        # Seed the bisection with per-signal groups so that one stubborn counter does not drag
        # the whole register file down; the groups run in parallel.
        groups: dict[str, list[str]] = defaultdict(list)
        for bit in bits:
            groups[bit.split("[", maxsplit=1)[0]].append(bit)
        with ThreadPoolExecutor(max_workers=jobs) as pool:
            for proven, failed, unknown in pool.map(
                lambda g: solve(g, TOP_TIMEOUT_S), list(groups.values())
            ):
                result["proven"] += proven
                result["failed"] += failed
                result["unknown"] += unknown
    except (FormalError, subprocess.TimeoutExpired) as exc:
        result["error"] = str(exc)
    for key in ("proven", "failed", "unknown"):
        result[key].sort()
    return result


def main(argv: list[str]) -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", maxsplit=1)[0])
    parser.add_argument("--dat", action="append", required=True, type=Path)
    parser.add_argument(
        "--param",
        action="append",
        default=[],
        metavar="MODULE:NAME=VALUE",
        help="parameter override for the wrapper instance (repeatable)",
    )
    parser.add_argument("--jobs", type=int, default=3)
    parser.add_argument(
        "--tie",
        action="append",
        default=[],
        metavar="PORT=VALUE",
        help="hold an input port at a constant (e.g. scan_mode_i=0: prove functional mode only)",
    )
    parser.add_argument(
        "--waivers",
        type=Path,
        default=ROOT / "tools/verif/coverage_waivers.txt",
        help="points already waived there are not re-proven",
    )
    parser.add_argument(
        "--skip",
        default="",
        help="regex over bit names such as regs_o[0][12] to leave out (counters and other bits that only a long run reaches)",
    )
    parser.add_argument("--out", type=Path, help="write the JSON lines here as well")
    parser.add_argument("modules", nargs="+")
    args = parser.parse_args(argv)
    for item in args.tie:
        port, _, val = item.partition("=")
        TIES[port] = val
    overrides: dict[str, dict[str, str]] = defaultdict(dict)
    for item in args.param:
        mod, _, rest = item.partition(":")
        key, _, val = rest.partition("=")
        overrides[mod][key] = val
    points = [pt for dat in args.dat for pt in cr.parse_dat(dat)]
    waivers = cr.load_waivers(args.waivers)
    skip = re.compile(args.skip) if args.skip else None
    lines = []
    with tempfile.TemporaryDirectory() as tmp:
        for module in args.modules:
            res = classify(
                module,
                overrides.get(module, {}),
                candidate_bits(points, module, waivers, skip),
                Path(tmp),
                args.jobs,
            )
            lines.append(json.dumps(res))
            print(lines[-1], flush=True)
    if args.out:
        args.out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
