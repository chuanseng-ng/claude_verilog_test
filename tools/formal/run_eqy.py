#!/usr/bin/env python3
"""tools/formal/run_eqy.py — EQY sv2v-vs-RTL equivalence runner (bead claude_verilog_test-q7n).

Compares individual modules from the sv2v-converted ASAP7 SoC netlist
(pnr/asap7/soc/soc_top_sv2v.v -- the netlist the ASAP7 SoC synth flow actually
consumes, see pnr/Makefile SOC_SV2V_DEFINES) against the original SystemVerilog
RTL, module by module, using Yosys EQY. Registry: tools/formal/modules.json.

MUST run with eqy/yosys/sby on PATH -- i.e. inside the librelane nix devshell.
Use run_eqy.sh, which wraps this script in a single `nix develop` session so
the devshell's startup cost is paid once, not once per module.

Same verdict discipline as tools/eda/summarize.py (bead dwp): a tool exiting 0
with an empty/unparsable report must never read as PASS. EQY "DONE (PASS...)"
is necessary but not sufficient; parse_verdict() adds three guards, each
written because a real run tripped it:
  * empty-match      -- matched.ids must exist and be non-empty, and the PASS
                        marker must exist.
  * zero-partition   -- eqy will declare designs equivalent having generated
                        NO partitions (empty partitions/ dir). Measured on
                        rv32i_clock_gate: 8 matched points, 0 proof
                        obligations, DONE (PASS). Nothing was proved.
  * match-set drift  -- a PASS below the recorded baseline_matched_points /
                        baseline_partitions proves less than the baseline did.
                        Measured: signal-deleting mutations shrank the match
                        set and were still reported PASS.

SCOPE WARNING (measured, see README.md): eqy's default `sat` strategy has a
demonstrated false-PASS class -- the generated miter accepts a gold-side `x`
unconditionally, and formalff/setundef are applied to the gate side only. An
inverted D input on a feedback-free flop (cdc_2ff_sync `sync_q[0] <= ~d_i`)
is NOT caught. Read every PASS here as "eqy's default strategy found no
counterexample", not as "these are equivalent".

Two gold-side frontends are supported per module.json entry ("frontend"):
  "yosys-sv" (default) -- Yosys 0.46's native `read_verilog -sv`. Cannot parse
    `import pkg::*;` (any position) or array-shaped parameters (unpacked, or
    packed 2-D) -- see modules.json blocked_modules for the modules this
    still blocks (confirmed empirically, isolated repros in README.md).
    Synlig unblocks the PARSE but has its own RTLIL-lowering limits on
    non-scalar parameter types (crash for string/packed-2D, silent garbage
    for unpacked arrays) -- see the note above apply_param_override().
  "synlig" -- Surelog/UHDM via the Synlig plugin (synlig-sv.so), which the
    librelane nix devshell already vendors but does not put on Yosys's own
    plugins/ search path. The plugin's absolute /nix/store path is resolved
    at RUNTIME by resolve_synlig_plugin() (glob, never hardcoded -- the path
    changes whenever librelane's flake input moves). If it cannot be found,
    this script FAILS LOUDLY (ERROR, non-zero exit) rather than silently
    falling back to the yosys-sv frontend and under-reporting blocked
    modules.

Exit codes (whole invocation, across all requested modules):
    0  PASS   every requested module PASSED
    1  FAIL   at least one module's EQY run reported FAIL (a real inequivalence
               was found, or eqy's own partitions did not all prove)
    2  ERROR  at least one module could not be evaluated (setup error, empty
               match set, tool crash) and none FAILed
    3  no modules matched the given selector

Statuses are PASS / FAIL / ERROR / SKIP. SKIP exists only in
--negative-control mode, for a module that declares no negative_control
mutation; it is never counted as PASS (an undefined control is absence of
evidence, not evidence of discrimination).

The exit code is always the RAW verdict. modules.json may carry
"expected_status" for entries whose FAIL is a documented, root-caused outcome
(the tier-4/5 register banks -- see README.md); that field is reported as
"expected_status_met" but NEVER suppresses or rewrites the exit code.
"""
from __future__ import annotations

import argparse
import glob
import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

PASS, FAIL, ERROR = 0, 1, 2

TOOLS_FORMAL_DIR = Path(__file__).resolve().parent
REPO_ROOT = TOOLS_FORMAL_DIR.parent.parent
REGISTRY_PATH = TOOLS_FORMAL_DIR / "modules.json"
FIXTURES_DIR = TOOLS_FORMAL_DIR / "fixtures"
DEFAULT_WORKDIR_ROOT = REPO_ROOT / "sim/build/formal-eqy"

MODULE_RE_TMPL = r"^module\s+{name}\b.*?^endmodule\b"

# Glob patterns tried in order to locate the Synlig plugin inside whatever
# nix store this devshell resolves to. NEVER hardcode a specific store hash
# here -- it changes whenever librelane's flake input moves (a stale hash
# would fail confusingly instead of just re-globbing). Resolved fresh on
# every invocation, inside the nix develop session (run_eqy.sh), so it always
# tracks whatever the devshell actually provides.
SYNLIG_PLUGIN_GLOBS = [
    "/nix/store/*yosys-synlig-sv*/share/yosys/plugins/synlig-sv.so",
]


class SynligPluginNotFound(RuntimeError):
    pass


def resolve_synlig_plugin() -> str:
    """Locate the Synlig read_systemverilog plugin .so, or fail loudly.

    An explicit SYNLIG_PLUGIN_PATH env var override is honoured first (useful
    for pinning/testing); otherwise globs the nix store. Never silently
    returns a "not found" sentinel that a caller could mistake for "frontend
    not needed" -- callers must only invoke this when frontend=="synlig" is
    actually selected, and must treat SynligPluginNotFound as a hard ERROR
    for every affected module, never a silent fallback to yosys-sv (that
    would under-report modules.json's blocked_modules relative to reality).
    """
    import os

    override = os.environ.get("SYNLIG_PLUGIN_PATH")
    if override:
        if Path(override).is_file():
            return override
        raise SynligPluginNotFound(
            f"SYNLIG_PLUGIN_PATH={override!r} does not exist (env override given but stale)."
        )

    matches: list[str] = []
    for pattern in SYNLIG_PLUGIN_GLOBS:
        matches.extend(sorted(glob.glob(pattern)))
    matches = [m for m in matches if Path(m).is_file()]
    if not matches:
        raise SynligPluginNotFound(
            "No synlig-sv.so found under any of "
            f"{SYNLIG_PLUGIN_GLOBS} -- is this running inside the librelane nix "
            "devshell (`nix develop ~/Downloads/Github/librelane`)? If the plugin "
            "moved to a different subpath, update SYNLIG_PLUGIN_GLOBS, or set "
            "SYNLIG_PLUGIN_PATH to override for one run."
        )
    # Multiple matches (e.g. two generations of the flake input coexisting in
    # the store) are not silently disambiguated -- take the newest by mtime
    # and say so, rather than picking arbitrarily.
    if len(matches) > 1:
        matches.sort(key=lambda p: Path(p).stat().st_mtime, reverse=True)
    return matches[0]


def load_registry() -> dict:
    return json.loads(REGISTRY_PATH.read_text())


def extract_module(netlist_text: str, module_name: str) -> str | None:
    """Pull one `module NAME ... endmodule` block out of the flat sv2v netlist.

    sv2v/Yosys output places `module`/`endmodule` at column 0 with no nesting
    (Verilog modules cannot nest), so a straightforward anchored regex is
    reliable here -- confirmed by manual inspection of all 28 module
    boundaries in pnr/asap7/soc/soc_top_sv2v.v before this script was written.
    """
    pattern = re.compile(MODULE_RE_TMPL.format(name=re.escape(module_name)), re.M | re.S)
    m = pattern.search(netlist_text)
    return (m.group(0) + "\n") if m else None


# NOTE (2026-08-15, bead q7n): an earlier revision of this file carried an
# `apply_array_fill_workaround()` that rewrote `'{default: 'X}` unpacked-array
# PARAMETER defaults into an explicit positional literal, on the theory that
# only the fill-literal form tripped Surelog. That theory is FALSE and the
# function was a proven no-op -- it has been deleted rather than left in place
# creating the impression that the X corruption had been handled. Evidence:
#
#   * Real file: elaborating rtl/soc/apb4_register_bank.sv through Synlig with
#     and without the rewrite produces BYTE-IDENTICAL `write_verilog` output
#     (16x `32'hxxxxxxxx` for WMASK, 16x `32'b0...0x` for RESET_VAL, both ways).
#   * Synthetic repro: a module with
#         parameter logic [31:0] PEXPL [2] = '{32'hAAAA_AAAA, 32'hBBBB_BBBB}
#         parameter logic [31:0] PFILL [2] = '{default: '1}
#         parameter logic [31:0] PSCALAR   = 32'hCCCC_CCCC
#     elaborates PSCALAR correctly (32'hCCCCCCCC) but BOTH array parameters to
#     the same garbage `32'b0000000000000000000000000000001x` -- i.e. Surelog
#     mis-elaborates unpacked-array-TYPED parameters regardless of how the
#     default is written. No source-level literal rewrite avoids it.
#
# This is the silent-X member of the same family as the two crashing members
# already recorded in modules.json blocked_modules: Yosys RTLIL cannot
# represent non-scalar parameter types, so Synlig's UHDM lowering either
# asserts (string params -- see boot_rom.sv's own header comment; packed-2D
# array params -- see axi4_crossbar) or, here, silently emits garbage.


PARAM_OVERRIDE_RE_TMPL = r"(parameter\s+int\s+unsigned\s+{param}\s*=\s*)(\d+)"


def apply_param_override(gold_text: str, params: dict, source_label: str) -> str:
    """Rewrite a gold-side `parameter int unsigned NAME = <int>` default in place.

    Used only by the tier-5 DIAGNOSTIC entries, which shrink the register
    banks' N_REGS to isolate the unpacked-array flattening-order root cause
    (see README.md "Tier 4 register-bank FAIL -- root cause"). The gate side
    is given the matching value with `chparam -set` (build_eqy_config), so
    both sides elaborate the same shape.

    Patching the SOURCE (rather than chparam-ing the gold side too) is
    deliberate: the Synlig frontend is invoked once per file list, and a
    later `chparam` cannot undo choices Surelog already baked into RTLIL
    during read_systemverilog (the same reason the deleted array-fill
    workaround could not repair the array-parameter garbage). Source rewrites
    land before elaboration, where they still have effect.

    Raises (never silently skips) if a named parameter is not found -- a
    silently-unapplied override would make the diagnostic compare two
    different designs and report a meaningless verdict.
    """
    for name, value in params.items():
        pat = re.compile(PARAM_OVERRIDE_RE_TMPL.format(param=re.escape(name)))
        m = pat.search(gold_text)
        if not m:
            raise RuntimeError(
                f"{source_label}: param_override target `parameter int unsigned {name}` "
                "not found -- RTL changed shape since this diagnostic was written. "
                "Do not silently skip (the run would compare mismatched shapes)."
            )
        gold_text = gold_text[: m.start()] + m.group(1) + str(value) + gold_text[m.end() :]
    return gold_text


def apply_text_rewrite(gold_text: str, spec: dict, source_label: str) -> str:
    """Apply one declared, exactly-once find/replace to a gold-side source copy.

    Used by `gold_rewrites` (tier-5 diagnostics that need a source edit to
    isolate a root cause) and by apply_negative_control(). `find` must occur
    EXACTLY ONCE: 0 means the edit silently did not land -- which for a
    diagnostic means it measured the wrong thing, and for a negative control
    means a vacuous "pass". Both raise rather than continue.
    """
    find, replace = spec["find"], spec["replace"]
    n = gold_text.count(find)
    if n != 1:
        raise RuntimeError(
            f"{source_label}: rewrite `find` string matched {n} times (expected exactly 1) "
            f"[{spec.get('note', 'no note')}]. An edit that does not land makes the run "
            "meaningless -- refusing to continue. Update modules.json to match the current RTL."
        )
    return gold_text.replace(find, replace)


def apply_negative_control(gold_text: str, spec: dict, source_label: str) -> str:
    """Inject the module's declared negative-control mutation into the gold copy.

    A negative control proves the harness can FAIL: a deliberate, documented
    corruption is injected into gold only, and the run is expected to flip
    from PASS to FAIL. If it does not, the harness is not discriminating on
    that path and every PASS it produced is worthless (see README.md
    "Negative controls").

    `find` must occur EXACTLY ONCE (enforced by apply_text_rewrite).
    """
    return apply_text_rewrite(gold_text, spec, source_label)


class NoNegativeControl(RuntimeError):
    pass


def build_patched_gold_files(entry: dict, case_dir: Path, negative_control: bool) -> dict[str, Path]:
    """Apply every in-memory gold-side source rewrite this entry asks for.

    Rewrites are applied per file in a FIXED order -- param_override, then
    gold_rewrites, then negative_control -- so a diagnostic entry can shrink a
    parameter and then edit code that depends on it. The committed RTL is never
    touched; every rewrite lands in a copy under the run's own scratch dir.
    """
    edits: dict[str, list] = {}

    def add(fname: str, fn) -> None:
        edits.setdefault(fname, []).append(fn)

    po = entry.get("param_override")
    if po:
        add(po["file"], lambda t, po=po: apply_param_override(t, po["params"], po["file"]))
    for rw in entry.get("gold_rewrites", []):
        add(rw["file"], lambda t, rw=rw: apply_text_rewrite(t, rw, rw["file"]))
    if negative_control:
        nc = entry.get("negative_control")
        if not nc:
            raise NoNegativeControl(
                f"{entry['name']}: no negative_control defined in modules.json "
                "(see negative_control_na for why, if present)."
            )
        add(nc["file"], lambda t, nc=nc: apply_negative_control(t, nc, nc["file"]))

    out: dict[str, Path] = {}
    for fname, fns in edits.items():
        text = (REPO_ROOT / fname).read_text()
        for fn in fns:
            text = fn(text)
        dest = case_dir / f"gold_patched_{Path(fname).name}"
        dest.write_text(text)
        out[fname] = dest
    return out


def build_eqy_config(
    entry: dict,
    gate_file: Path,
    extra_defines: list[str] | None = None,
    synlig_plugin_path: str | None = None,
    patched_gold_files: dict[str, Path] | None = None,
) -> str:
    defines = list(entry.get("defines", [])) + list(extra_defines or [])
    frontend = entry.get("frontend", "yosys-sv")
    patched_gold_files = patched_gold_files or {}

    gold_lines = []
    if frontend == "synlig":
        assert synlig_plugin_path, "build_eqy_config: frontend=synlig requires synlig_plugin_path"
        # Surelog/Synlig's argument parser wants the glued `-DFOO` form, NOT
        # `-D FOO` (confirmed empirically: `-D FOO` mis-splits and Surelog
        # tries to open a file literally named after the macro; `-DFOO`
        # works). This is the opposite convention from the yosys-sv branch
        # below (`read_verilog -sv` wants `-D FOO`, space form) -- both were
        # verified independently, do not unify them.
        def_flags = " ".join(f"-D{d}" for d in defines)
        gold_lines.append(f"plugin -i {synlig_plugin_path}")
        file_list = " ".join(
            str(patched_gold_files.get(f, REPO_ROOT / f)) for f in entry["gold_files"]
        )
        gold_lines.append(f"read_systemverilog {def_flags} {file_list}".rstrip())
    else:
        def_flags = " ".join(f"-D {d}" for d in defines)
        for f in entry["gold_files"]:
            gold_lines.append(f"read_verilog -sv {def_flags} {patched_gold_files.get(f, REPO_ROOT / f)}".rstrip())
    for f in entry.get("common_fixtures", []):
        gold_lines.append(f"read_verilog {FIXTURES_DIR / f}")
    gold_lines.append(f"prep -top {entry['top']}")
    # Commands appended IDENTICALLY to both sides after prep. Only ever use
    # this to reconcile a representation difference the two frontends disagree
    # on (e.g. memory inference); anything applied to one side only would be
    # a way to launder a real mismatch into a PASS, so there is deliberately
    # no per-side variant of this key.
    gold_lines.extend(entry.get("post_prep_both", []))

    gate_lines = [f"read_verilog {gate_file}"]
    for f in entry.get("common_fixtures", []):
        gate_lines.append(f"read_verilog {FIXTURES_DIR / f}")
    # param_override: the gold side got the new value by source rewrite
    # (apply_param_override); the gate side gets it with chparam, BEFORE prep,
    # so hierarchy re-derives the module -- and, critically, re-evaluates the
    # sv2v-emitted RESET_VAL/WMASK defaults, which are written as
    # `{N_REGS{32'b...}}` and so resize themselves. Never hand the gate a
    # gold-ordered array literal here: sv2v reverses element order in
    # parameter arrays too (see README.md root-cause section).
    po = entry.get("param_override")
    if po:
        for name, value in po["params"].items():
            gate_lines.append(f"chparam -set {name} {value} {entry['top']}")
    gate_lines.append(f"prep -top {entry['top']}")
    gate_lines.extend(entry.get("post_prep_both", []))

    depth = entry.get("depth", 5)
    return (
        "[gold]\n" + "\n".join(gold_lines) + "\n\n"
        "[gate]\n" + "\n".join(gate_lines) + "\n\n"
        "[strategy simple]\nuse sat\ndepth " + str(depth) + "\n"
    )


def run_eqy_case(config_path: Path, workdir: Path) -> tuple[int, str]:
    if workdir.exists():
        shutil.rmtree(workdir)
    t0 = time.time()
    proc = subprocess.run(
        ["eqy", "-f", "-d", str(workdir), str(config_path)],
        cwd=config_path.parent,
        capture_output=True,
        text=True,
        timeout=900,
    )
    elapsed = time.time() - t0
    log = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode, log, elapsed  # type: ignore[return-value]


def parse_verdict(rc: int, log: str, workdir: Path, module: str, entry: dict | None = None) -> dict:
    """Turn eqy's raw exit code + logfile.txt + workdir artifacts into a verdict.

    eqy's own exit codes observed empirically (2026-08, eqy bundled with the
    librelane nix devshell's Yosys 0.46): 0 on "DONE (PASS...)", 2 on
    "DONE (FAIL...)", 1 when source-reading/setup fails before any partition
    is attempted (no matched.ids, no PASS file ever written).
    """
    matched_ids_path = workdir / "matched.ids"
    pass_file = workdir / "PASS"
    logfile_path = workdir / "logfile.txt"
    full_log = log
    if logfile_path.exists():
        full_log += "\n" + logfile_path.read_text()

    matched_count = 0
    matched_lines: list[str] = []
    if matched_ids_path.exists():
        matched_lines = [
            l for l in matched_ids_path.read_text().splitlines() if l.strip() and not l.startswith("#")
        ]
        matched_count = len(matched_lines)

    proved = re.findall(r"Successfully proved equivalence of partition (\S+)", full_log)
    failed_partitions = re.findall(r"Failed to prove equivalence of partition (\S+)", full_log)
    partitions_total = len(set(proved) | set(failed_partitions))

    done_pass = "DONE (PASS" in full_log
    done_fail = "DONE (FAIL" in full_log

    if done_pass:
        if matched_count == 0 or not pass_file.exists():
            status = "ERROR"
            reason = (
                "eqy reported DONE (PASS) but matched.ids is empty or the PASS marker is "
                "missing -- treating as a proof of nothing, not a proof of equivalence "
                "(bead dwp discipline: empty match != PASS)."
            )
        else:
            status = "PASS"
            reason = f"eqy proved equivalence; {matched_count} matched gold/gate points, {partitions_total} partition(s) proved."
    elif done_fail:
        status = "FAIL"
        reason = f"eqy found {len(failed_partitions)} unproved/failed partition(s): {failed_partitions or 'see log'}."
    else:
        status = "ERROR"
        err_lines = [l for l in full_log.splitlines() if "ERROR" in l]
        reason = "eqy did not reach a DONE verdict (setup/read failure)." + (
            f" First error: {err_lines[0]}" if err_lines else ""
        )

    # ── Zero-partition guard ─────────────────────────────────────────────────
    # eqy can print "Successfully proved designs equivalent" / DONE (PASS) after
    # generating NO partitions at all -- its partitions/ directory is literally
    # empty. That is the bead-dwp pathology one level deeper than the empty-match
    # guard above: the match set is non-empty (names lined up) but not a single
    # proof obligation was ever created, so nothing was proved. Measured on
    # rv32i_clock_gate, whose only content is a blackboxed liberty ICG cell.
    if status == "PASS" and partitions_total == 0:
        status = "ERROR"
        reason = (
            f"eqy reported DONE (PASS) with {matched_count} matched points but generated "
            "ZERO partitions -- no proof obligation was created, so nothing was proved. "
            "Treating as ERROR, not PASS (bead dwp discipline). Typically means the module "
            "contains no logic the prover can reason about (e.g. only blackboxed cells)."
        )

    # ── Match-set drift guard ────────────────────────────────────────────────
    # A PASS on a SMALLER match set than the recorded baseline proves strictly
    # less than the recorded proof did, and eqy will happily report DONE (PASS)
    # for it. This is the same failure shape as bead dwp (tool exits 0, report
    # is empty) one level up: the report is non-empty, it just covers less.
    # Found the hard way -- a negative control that deleted a signal from the
    # cone (cdc_2ff_sync: the 2-FF chain collapsed to `sync_q[i] <= d_i`)
    # shrank matched points 6->5 and partitions 3->2, and eqy still reported
    # DONE (PASS). Without this guard the harness silently stops discriminating
    # exactly when a corruption removes logic.
    drift = None
    base_pts = (entry or {}).get("baseline_matched_points")
    base_parts = (entry or {}).get("baseline_partitions")
    if status == "PASS" and (base_pts is not None or base_parts is not None):
        short_pts = base_pts is not None and matched_count < base_pts
        short_parts = base_parts is not None and partitions_total < base_parts
        if short_pts or short_parts:
            drift = {
                "matched_points": [base_pts, matched_count],
                "partitions": [base_parts, partitions_total],
            }
            status = "ERROR"
            reason = (
                "MATCH-SET DRIFT: eqy reported DONE (PASS) but over a SMALLER proof than the "
                f"recorded baseline ({matched_count} matched points vs {base_pts}; "
                f"{partitions_total} partitions vs {base_parts}). A PASS on a shrunken match "
                "set proves less than the baseline did and must not be reported as the same "
                "result -- either the design/netlist changed shape (update the baseline "
                "deliberately) or something removed logic from the cone."
            )

    verdict = {
        "module": module,
        "status": status,
        "eqy_exit_code": rc,
        "reason": reason,
        "matched_points": matched_count,
        "partitions_proved": sorted(set(proved)),
        "partitions_failed": sorted(set(failed_partitions)),
        "workdir": str(workdir),
    }
    if drift:
        verdict["match_drift"] = drift
    return verdict


def run_one(
    entry: dict,
    gate_netlist_text: str,
    workdir_root: Path,
    extra_defines=None,
    tag="",
    synlig_plugin_path: str | None = None,
    negative_control: bool = False,
) -> dict:
    module = entry["name"]
    gate_module_names = entry.get("gate_modules", [entry["top"]])
    gate_blocks = []
    missing = []
    for gm in gate_module_names:
        block = extract_module(gate_netlist_text, gm)
        if block is None:
            missing.append(gm)
        else:
            gate_blocks.append(block)
    if missing:
        return {
            "module": module,
            "status": "ERROR",
            "eqy_exit_code": None,
            "reason": f"module(s) {missing} not found in gate netlist (extraction failed)",
            "matched_points": 0,
            "partitions_proved": [],
            "partitions_failed": [],
            "workdir": None,
        }

    if entry.get("frontend") == "synlig" and not synlig_plugin_path:
        return {
            "module": module,
            "status": "ERROR",
            "eqy_exit_code": None,
            "reason": (
                "frontend=synlig requires the Synlig plugin, which could not be "
                "resolved (see resolve_synlig_plugin() error) -- refusing to "
                "silently fall back to yosys-sv, which would under-report this "
                "module as unblocked when it is not."
            ),
            "matched_points": 0,
            "partitions_proved": [],
            "partitions_failed": [],
            "workdir": None,
        }

    case_dir = workdir_root / (module + (f"_{tag}" if tag else ""))
    case_dir.mkdir(parents=True, exist_ok=True)
    gate_file = case_dir / f"gate_{entry['top']}.v"
    gate_file.write_text("\n".join(gate_blocks))

    try:
        patched_gold_files = build_patched_gold_files(entry, case_dir, negative_control)
    except NoNegativeControl as exc:
        return {
            "module": module,
            "status": "SKIP",
            "eqy_exit_code": None,
            "reason": (
                f"{exc} Reported as SKIP, never PASS -- an undefined control is "
                "absence of evidence, not evidence of discrimination."
            ),
            "matched_points": 0,
            "partitions_proved": [],
            "partitions_failed": [],
            "workdir": None,
        }
    except RuntimeError as exc:
        return {
            "module": module,
            "status": "ERROR",
            "eqy_exit_code": None,
            "reason": f"gold-side source rewrite failed: {exc}",
            "matched_points": 0,
            "partitions_proved": [],
            "partitions_failed": [],
            "workdir": None,
        }

    config_text = build_eqy_config(
        entry,
        gate_file,
        extra_defines=extra_defines,
        synlig_plugin_path=synlig_plugin_path,
        patched_gold_files=patched_gold_files,
    )
    config_path = case_dir / f"{module}.eqy"
    config_path.write_text(config_text)

    workdir = case_dir / "run"
    t0 = time.time()
    try:
        rc, log, elapsed = run_eqy_case(config_path, workdir)
    except FileNotFoundError:
        return {
            "module": module,
            "status": "ERROR",
            "eqy_exit_code": 3,
            "reason": "eqy not found on PATH -- run inside `nix develop ~/Downloads/Github/librelane --command ...` (see run_eqy.sh)",
            "matched_points": 0,
            "partitions_proved": [],
            "partitions_failed": [],
            "workdir": str(workdir),
        }
    except subprocess.TimeoutExpired:
        return {
            "module": module,
            "status": "ERROR",
            "eqy_exit_code": None,
            "reason": "eqy timed out after 900s",
            "matched_points": 0,
            "partitions_proved": [],
            "partitions_failed": [],
            "workdir": str(workdir),
        }

    verdict = parse_verdict(rc, log, workdir, module, entry)
    verdict["elapsed_s"] = round(elapsed, 1)
    verdict["tier"] = entry.get("tier")
    verdict["config"] = str(config_path)
    if negative_control:
        # Invert the sense: the injected mutation MUST be caught. A raw FAIL
        # is the control passing; anything else (PASS, or an ERROR that never
        # got as far as proving anything) is the control failing, because it
        # means this frontend/module path cannot distinguish a corrupted gold
        # from the real one.
        raw = verdict["status"]
        verdict["raw_status"] = raw
        verdict["negative_control"] = entry["negative_control"]
        # "Caught" means eqy either failed a partition, or refused to certify
        # because the mutation shrank the match set (see parse_verdict's
        # match-drift guard). A setup/read ERROR does NOT count -- the tool
        # falling over is not the tool detecting anything.
        if raw == "FAIL" or verdict.get("match_drift"):
            how = (
                f"eqy reported FAIL on {verdict['partitions_failed']}"
                if raw == "FAIL"
                else f"the match-set drift guard refused to certify it ({verdict['match_drift']})"
            )
            verdict["status"] = "PASS"
            verdict["reason"] = (
                "NEGATIVE CONTROL OK: the injected gold-side mutation "
                f"({entry['negative_control']['note']}) was caught -- {how}, "
                f"with {verdict['matched_points']} matched points."
            )
        else:
            verdict["status"] = "FAIL"
            verdict["reason"] = (
                f"NEGATIVE CONTROL BROKEN: raw verdict was {raw}, expected FAIL. The "
                "harness did not detect a deliberate corruption on this path, so every "
                f"PASS it reports here is unsupported. Raw reason: {verdict['reason']}"
            )
    exp = entry.get("expected_status")
    if exp:
        verdict["expected_status"] = exp
        verdict["expected_status_met"] = verdict["status"] == exp
    return verdict


def select_modules(registry: dict, args) -> list[dict]:
    mods = registry["modules"]
    if args.module:
        mods = [m for m in mods if m["name"] in args.module]
    elif args.tier:
        mods = [m for m in mods if m["tier"] == args.tier]
    return mods


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--module", action="append", help="run only this module (repeatable)")
    ap.add_argument("--tier", type=int, help="run only this tier")
    ap.add_argument("--all", action="store_true", help="run every module in the registry")
    ap.add_argument("--workdir-root", default=str(DEFAULT_WORKDIR_ROOT))
    ap.add_argument("--json-out", help="write the aggregate JSON summary to this path")
    ap.add_argument(
        "--negative-control",
        action="store_true",
        help=(
            "inject each module's declared negative_control mutation into a gold-side "
            "copy and INVERT the verdict: the run passes only if eqy reports FAIL. "
            "Modules with no negative_control declared are reported SKIP, never PASS."
        ),
    )
    args = ap.parse_args()

    if not (args.module or args.tier or args.all):
        ap.error("pass --module NAME, --tier N, or --all")

    registry = load_registry()
    gate_netlist_path = REPO_ROOT / registry["gate_netlist"]
    if not gate_netlist_path.exists():
        print(json.dumps({"status": "ERROR", "reason": f"gate netlist not found: {gate_netlist_path}"}))
        return ERROR
    gate_netlist_text = gate_netlist_path.read_text()

    mods = select_modules(registry, args)
    if not mods:
        print(json.dumps({"status": "ERROR", "reason": "no modules matched selector"}))
        return 3

    workdir_root = Path(args.workdir_root)
    workdir_root.mkdir(parents=True, exist_ok=True)

    synlig_plugin_path: str | None = None
    if any(m.get("frontend") == "synlig" for m in mods):
        try:
            synlig_plugin_path = resolve_synlig_plugin()
            print(f"[run_eqy] resolved synlig plugin: {synlig_plugin_path}", file=sys.stderr)
        except SynligPluginNotFound as exc:
            print(json.dumps({"status": "ERROR", "reason": f"synlig plugin resolution failed: {exc}"}))
            return ERROR

    results = []
    for entry in mods:
        verdict = run_one(
            entry,
            gate_netlist_text,
            workdir_root,
            tag="negctl" if args.negative_control else "",
            synlig_plugin_path=synlig_plugin_path,
            negative_control=args.negative_control,
        )
        results.append(verdict)
        print(json.dumps(verdict, indent=2))

    summary = {
        "run_id": "q7n_eqy_sv2v_equivalence"
        + ("_negative_control" if args.negative_control else ""),
        "mode": "negative-control" if args.negative_control else "equivalence",
        "gate_netlist": str(gate_netlist_path),
        "results": results,
        "pass": sum(1 for r in results if r["status"] == "PASS"),
        "fail": sum(1 for r in results if r["status"] == "FAIL"),
        "error": sum(1 for r in results if r["status"] == "ERROR"),
        "skip": sum(1 for r in results if r["status"] == "SKIP"),
        # Documented-expectation tracking. The exit code stays RAW (a FAIL is
        # reported as a FAIL even when modules.json says it is expected), so an
        # "expected" FAIL can never be laundered into a green run; this field
        # only tells the reader whether reality still matches the writeup.
        "expected_status_mismatches": [
            r["module"] for r in results if r.get("expected_status_met") is False
        ],
    }
    if args.json_out:
        Path(args.json_out).write_text(json.dumps(summary, indent=2))

    print("\n=== SUMMARY ===")
    for r in results:
        print(f"  {r['module']:<24} tier={r.get('tier')}  {r['status']:<6} matched={r['matched_points']:<4} {r['reason']}")

    if summary["fail"] > 0:
        return FAIL
    if summary["error"] > 0:
        return ERROR
    return PASS


if __name__ == "__main__":
    sys.exit(main())
