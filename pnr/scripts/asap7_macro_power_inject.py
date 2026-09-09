#!/usr/bin/env python3
"""asap7_macro_power_inject.py — inject lumped macro power into an ASAP7
abstracted-macro Liberty file, from the report_power output of
asap7_macro_power.tcl.

Companion to (NOT a modification of) asap7_macro_views.tcl / write_timing_model.
write_timing_model has no power code path (bead claude_verilog_test-86a): the
macro .lib it emits declares leakage_power_unit but never a cell_leakage_power
or internal_power value, so any report_power run above the macro (e.g. the
SoC-level flow that treats rv32i_cpu_top / gpu_top as a black box) attributes
0.00 W to it. This script patches that gap into an already-generated macro
.lib in place, by:

  1. Parsing the "Total" row (Internal / Switching / Leakage / Total, Watts)
     out of a report_power -digits 6 report (asap7_macro_power.tcl's output).
  2. Reading the target .lib's own declared capacitive_load_unit,
     voltage_unit and leakage_power_unit so the injected numbers land in
     whatever unit that specific file already declares (do not assume a
     fixed unit across files).
  3. Writing a single `cell_leakage_power` on the macro cell = the report's
     total Leakage Power, converted into leakage_power_unit.
  4. Writing a single `internal_power` group on the macro's clock pin
     (--clock-pin) whose rise_power/fall_power scalars, evaluated at the
     block's clock period (--period-ps), reproduce the report's total
     (Internal + Switching) dynamic power. No other pin gets an
     internal_power entry — see "Why the clock pin only" below.
  5. Writing a documentation comment block into the library header recording
     the activity assumption, netlist/SDC sources and unit derivation, so
     nobody downstream reads the injected numbers as measured-under-real-
     workload silicon data.

Why the clock pin only
-----------------------
Liberty internal_power groups are always declared per pin, but this script
deliberately attaches the *entire* macro-internal dynamic power to the clock
pin rather than spreading invented per-output-pin numbers around. There is no
per-pin toggle measurement behind this characterization (see the activity
note below) — report_power was run with one FLAT global activity rate applied
uniformly to every internal net, so any pin-level split would just be a
proportional slice of that same single assumption, not independent
information. Presenting that as "per-pin data" would fabricate a precision
this characterization does not have. Lumping it onto the clock pin instead
is the standard practice for macro/ILM-style power abstraction when no real
per-pin activity trace exists (a large synchronous macro's dynamic power is
overwhelmingly clock-edge-triggered in any case: see this project's own
Sequential+Clock rows, which are >60% of total dynamic power for both macros
characterized here) and it reproduces the correct TOTAL macro power under the
stated activity assumption, which is what a caller's report_power actually
needs.

Liberty internal_power unit derivation
----------------------------------------
Liberty does not declare a distinct "energy unit" attribute in these files.
The implicit unit for internal_power (rise_power/fall_power) scalar values is
capacitive_load_unit x voltage_unit^2 (an energy, since power ~ 1/2 C V^2).
This was verified empirically against THIS project's own OpenSTA build (not
assumed from a spec reading): a minimal single-cell macro .lib with
capacitive_load_unit(1,fF), voltage_unit "1V", rise_power=100 (raw units),
period 1000 ps, reported exactly 1.0e-04 W via report_power — matching
100 raw x 1 fJ (= 1fF x 1V^2) / 1000 ps, and NOT matching a 1 pJ or 1 nJ
interpretation (100x / 100000x off respectively). See the bead 86a session
notes for the reproduction script. This script re-derives that same unit
from each target .lib's own header rather than hardcoding fJ, so it stays
correct if a future macro .lib declares different capacitive_load_unit /
voltage_unit values.

Usage
-----
    python3 asap7_macro_power_inject.py \\
        --macro-lib pnr/asap7/soc/macro/rv32i_cpu_top__nom_tt_025C_0p7V.lib \\
        --power-report /path/to/rv32i_cpu_top.power.rpt \\
        --clock-pin clk_i --period-ps 780 \\
        --design-name rv32i_cpu_top \\
        --netlist pnr/asap7/cpu/macro/rv32i_cpu_top.nl.v.gz \\
        --sdc pnr/asap7/cpu/constraints/asap7.sdc \\
        --stdcell-instances 74175 --macro-instances 10 --macro-instance-kind "SRAM (I$+D$)"

Exits nonzero (and writes nothing) if the target cell/pin isn't found, if the
report has no parseable Total row, or if the cell already carries an injected
block and --force was not given.
"""
import argparse
import re
import sys
from datetime import datetime, timezone

# NOTE: these two constants must together form exactly ONE C-style comment
# (BEGIN_MARK opens with "/*" and does NOT close it; END_MARK closes with
# "*/" and does NOT open a new one) -- everything in between is emitted as
# plain text lines (see build_doc_comment), which are only valid Liberty
# syntax while still inside that one open comment. Do not "fix" either
# marker to be self-contained; that was tried once and broke the parser
# (every body line would then be interpreted as bare Liberty tokens outside
# any comment).
BEGIN_MARK = "/* === asap7_macro_power_inject.py: BEGIN injected power characterization ==="
END_MARK = "=== asap7_macro_power_inject.py: END injected power characterization === */"

UNIT_MULT = {
    "ff": 1e-15, "pf": 1e-12, "nf": 1e-9, "f": 1e-15,
    "fw": 1e-15, "pw": 1e-12, "nw": 1e-9, "uw": 1e-6, "mw": 1e-3, "w": 1.0,
    "v": 1.0, "mv": 1e-3,
    "a": 1.0, "ma": 1e-3, "ua": 1e-6,
}

TOTAL_ROW_RE = re.compile(
    r"^Total\s+([0-9.eE+\-]+)\s+([0-9.eE+\-]+)\s+([0-9.eE+\-]+)\s+([0-9.eE+\-]+)",
    re.MULTILINE,
)


def parse_unit(raw: str):
    """'"1pW"' / '1pW' / '(1,fF)' style Liberty unit -> (numeric_value, multiplier_to_base)."""
    raw = raw.strip().strip('"').strip(";").strip()
    m = re.match(r"\(?\s*([0-9.eE+\-]+)\s*,?\s*([a-zA-Z]+)\s*\)?", raw)
    if not m:
        raise ValueError(f"cannot parse Liberty unit: {raw!r}")
    value = float(m.group(1))
    unit = m.group(2).lower()
    if unit not in UNIT_MULT:
        raise ValueError(f"unrecognized unit suffix {unit!r} in {raw!r}")
    return value, UNIT_MULT[unit]


def parse_header_units(lib_text: str):
    def find(attr, required=True):
        m = re.search(rf"^\s*{attr}\s*[:(]\s*(.+?)\s*;?\s*$", lib_text, re.MULTILINE)
        if not m:
            if required:
                raise ValueError(f"target .lib has no {attr} declaration")
            return None
        return m.group(1)

    cload_raw = find("capacitive_load_unit")
    cload_val, cload_mult = parse_unit(cload_raw)
    cload_F = cload_val * cload_mult

    volt_raw = find("voltage_unit")
    volt_val, volt_mult = parse_unit(volt_raw)
    volt_V = volt_val * volt_mult

    leak_raw = find("leakage_power_unit")
    leak_val, leak_mult = parse_unit(leak_raw)
    leak_unit_W = leak_val * leak_mult

    return cload_F, volt_V, leak_unit_W


def parse_power_report(report_text: str):
    m = TOTAL_ROW_RE.search(report_text)
    if not m:
        raise ValueError("no 'Total <internal> <switching> <leakage> <total>' row found in report")
    internal_w, switching_w, leakage_w, total_w = (float(x) for x in m.groups())
    return internal_w, switching_w, leakage_w, total_w


def build_doc_comment(args, internal_w, switching_w, leakage_w, dynamic_w,
                       energy_unit_J, rise_raw, leakage_raw, freq_hz):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    lines = [
        BEGIN_MARK,
        f" * Generated {ts} by pnr/scripts/asap7_macro_power_inject.py",
        f" * (bead claude_verilog_test-86a — write_timing_model has no power path;",
        f" *  this backfills cell_leakage_power / internal_power onto the macro",
        f" *  view it produced, from a SEPARATE report_power characterization run",
        f" *  in pnr/scripts/asap7_macro_power.tcl. Neither script modifies the other.)",
        f" *",
        f" * SOURCE: {args.design_name}'s own flat post-route netlist",
        f" *   netlist : {args.netlist}",
        f" *   sdc     : {args.sdc}  (period {args.period_ps} ps, {freq_hz/1e6:.4f} MHz)",
        f" *   report  : {args.power_report}",
    ]
    if args.stdcell_instances is not None:
        inst_line = f" *   instances: {args.stdcell_instances} standard cells"
        if args.macro_instances:
            kind = args.macro_instance_kind or "internal hard macro"
            inst_line += f" + {args.macro_instances} {kind}"
        lines.append(inst_line)
    lines += [
        f" *",
        f" * ACTIVITY ASSUMPTION (read this before trusting these numbers):",
        f" *   report_power was run with ONE FLAT, UNMEASURED toggle-rate",
        f" *   assumption applied uniformly to every internal net:",
        f" *     set_power_activity -global -activity {args.activity_rate} -duty {args.activity_duty}",
        f" *   This is NOT derived from a workload trace, VCD, or SAIF for this",
        f" *   design -- no gate-level switching capture exists for this macro.",
        f" *   {args.activity_rate}/{args.activity_duty} matches this repo's own established",
        f" *   'no VCD available' default (pnr/scripts/08_power.tcl, Sky130 Phase 3:",
        f" *   deliberately conservative, errs toward overestimating dynamic power).",
        f" *   Treat every number below as ESTIMATED UNDER AN ASSUMED ACTIVITY,",
        f" *   not measured under real firmware/workload switching.",
        f" *",
        f" *   Also: no post-route SPEF/DEF was available for this characterization",
        f" *   (the signed-off run directory this macro came from was pruned by",
        f" *   ASAP7_MAX_RUNS before this ran -- see bead 86a session notes), so",
        f" *   report_power used gate input-pin capacitance only, with NO wire RC.",
        f" *   That tends to UNDERESTIMATE switching power somewhat, partially",
        f" *   offsetting the {args.activity_rate} activity rate's deliberate conservatism",
        f" *   in the other direction. Net effect on accuracy is not separately",
        f" *   quantified here.",
        f" *",
        f" * report_power totals at this activity (Watts):",
        f" *   Internal={internal_w:.6e}  Switching={switching_w:.6e}",
        f" *   Leakage={leakage_w:.6e}  Dynamic(Int+Sw)={dynamic_w:.6e}",
        f" *",
        f" * INJECTED VALUES:",
        f" *   cell_leakage_power = {leakage_raw:.6g} (in this file's own leakage_power_unit)",
        f" *     = {leakage_w*1e3:.6f} mW lumped macro leakage (includes any internal",
        f" *       hard macro's own real, vendor-Liberty-sourced leakage).",
        f" *   internal_power on clock pin \"{args.clock_pin}\": rise_power=fall_power=",
        f" *     {rise_raw:.6g} raw units each (unit = capacitive_load_unit x voltage_unit^2",
        f" *     = {energy_unit_J*1e15:.6g} fJ per this file's own header, verified empirically",
        f" *     against this project's OpenSTA build -- see this script's module docstring).",
        f" *     rise+fall reproduces {dynamic_w*1e3:.6f} mW dynamic power at {freq_hz/1e6:.4f} MHz",
        f" *     ({args.period_ps} ps period), i.e. energy_per_cycle = dynamic_W x period.",
        f" *     No other pin carries an internal_power entry -- see this script's",
        f" *     module docstring, \"Why the clock pin only\".",
        f" *",
        f" * Macro-inclusive total for THIS macro alone at this activity:",
        f" *   {(internal_w+switching_w+leakage_w)*1e3:.6f} mW. This is a NEW figure, not a",
        f" *   replacement for any existing fabric-only sign-off number in",
        f" *   docs/PHASE5_RUN_HISTORY.md -- those remain correctly-reported",
        f" *   fabric-only figures and are not retro-edited by this injection.",
        END_MARK,
    ]
    return "\n".join(f"  {l}" for l in lines)


def inject(lib_text: str, args, internal_w, switching_w, leakage_w):
    cload_F, volt_V, leak_unit_W = parse_header_units(lib_text)
    energy_unit_J = cload_F * (volt_V ** 2)
    if energy_unit_J <= 0:
        raise ValueError("derived internal_power energy unit is non-positive; check header units")

    dynamic_w = internal_w + switching_w
    period_s = args.period_ps * 1e-12
    freq_hz = 1.0 / period_s
    energy_per_cycle_J = dynamic_w * period_s
    raw_total = energy_per_cycle_J / energy_unit_J
    rise_raw = fall_raw = raw_total / 2.0

    leakage_raw = leakage_w / leak_unit_W

    if BEGIN_MARK in lib_text:
        if not args.force:
            raise SystemExit(
                f"error: {args.macro_lib} already has an injected power block "
                f"(marker found) -- pass --force to re-inject"
            )
        lib_text = re.sub(
            re.escape(BEGIN_MARK) + r".*?" + re.escape(END_MARK),
            "__DOC_PLACEHOLDER__", lib_text, count=1, flags=re.DOTALL,
        )

    cell_re = re.compile(
        rf'(cell\s*\(\s*"?{re.escape(args.design_name)}"?\s*\)\s*\{{.*?is_macro_cell\s*:\s*true\s*;\n)',
        re.DOTALL,
    )
    m = cell_re.search(lib_text)
    if not m:
        raise SystemExit(f"error: cell (\"{args.design_name}\") {{ ... is_macro_cell : true; not found in {args.macro_lib}")
    if "cell_leakage_power" in lib_text[m.end():m.end() + 200] and not args.force:
        raise SystemExit("error: cell_leakage_power already present near cell header -- pass --force")
    insertion = f"    cell_leakage_power : {leakage_raw:.6g};\n"
    lib_text = lib_text[:m.end()] + insertion + lib_text[m.end():]

    pin_re = re.compile(
        rf'(pin\s*\(\s*"?{re.escape(args.clock_pin)}"?\s*\)\s*\{{(?:[^{{}}]*\n)*?\s*capacitance\s*:\s*[0-9.eE+\-]+\s*;\n)',
    )
    m2 = pin_re.search(lib_text)
    if not m2:
        raise SystemExit(f'error: pin("{args.clock_pin}") {{ ... capacitance : ...; not found in {args.macro_lib}')
    internal_power_block = (
        "      internal_power () {\n"
        f'        rise_power (scalar) {{ values("{rise_raw:.6g}"); }}\n'
        f'        fall_power (scalar) {{ values("{fall_raw:.6g}"); }}\n'
        "      }\n"
    )
    lib_text = lib_text[:m2.end()] + internal_power_block + lib_text[m2.end():]

    doc_comment = build_doc_comment(
        args, internal_w, switching_w, leakage_w, dynamic_w,
        energy_unit_J, rise_raw, leakage_raw, freq_hz,
    )
    if "__DOC_PLACEHOLDER__" in lib_text:
        lib_text = lib_text.replace("__DOC_PLACEHOLDER__", doc_comment, 1)
    else:
        lib_header_re = re.compile(r'(library\s*\(\s*"?[^)"]+"?\s*\)\s*\{\n)')
        m3 = lib_header_re.search(lib_text)
        if not m3:
            raise SystemExit(f"error: no 'library ( ... ) {{' header found in {args.macro_lib}")
        lib_text = lib_text[:m3.end()] + doc_comment + "\n" + lib_text[m3.end():]

    summary = {
        "internal_w": internal_w, "switching_w": switching_w, "leakage_w": leakage_w,
        "dynamic_w": dynamic_w, "cell_leakage_power_raw": leakage_raw,
        "internal_power_rise_raw": rise_raw, "internal_power_fall_raw": fall_raw,
        "energy_unit_J": energy_unit_J, "freq_hz": freq_hz,
    }
    return lib_text, summary


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--macro-lib", required=True, help="target abstracted macro .lib to patch in place")
    ap.add_argument("--power-report", required=True, help="report_power -digits 6 text report from asap7_macro_power.tcl")
    ap.add_argument("--design-name", required=True, help='cell name inside the .lib, e.g. rv32i_cpu_top')
    ap.add_argument("--clock-pin", required=True, help='clock pin name inside the .lib, e.g. clk_i or clk')
    ap.add_argument("--period-ps", required=True, type=float, help="block SDC clock period in ps")
    ap.add_argument("--netlist", required=True, help="path recorded in the doc comment (informational)")
    ap.add_argument("--sdc", required=True, help="path recorded in the doc comment (informational)")
    ap.add_argument("--activity-rate", type=float, default=0.20)
    ap.add_argument("--activity-duty", type=float, default=0.5)
    ap.add_argument("--stdcell-instances", type=int, default=None)
    ap.add_argument("--macro-instances", type=int, default=None)
    ap.add_argument("--macro-instance-kind", default=None)
    ap.add_argument("--force", action="store_true", help="re-inject even if a prior injected block exists")
    ap.add_argument("--dry-run", action="store_true", help="compute and print values, write nothing")
    ap.add_argument("--out", default=None, help="write to a different path instead of patching --macro-lib in place")
    args = ap.parse_args()

    with open(args.macro_lib) as f:
        lib_text = f.read()
    with open(args.power_report) as f:
        report_text = f.read()

    internal_w, switching_w, leakage_w, total_w = parse_power_report(report_text)

    patched, summary = inject(lib_text, args, internal_w, switching_w, leakage_w)

    print(f"Report Total row: Internal={internal_w:.6e} W  Switching={switching_w:.6e} W  "
          f"Leakage={leakage_w:.6e} W  Total={total_w:.6e} W")
    print(f"Derived internal_power energy unit: {summary['energy_unit_J']*1e15:.6g} fJ per raw unit")
    print(f"cell_leakage_power (raw, this file's leakage_power_unit) = {summary['cell_leakage_power_raw']:.6g}")
    print(f"internal_power on \"{args.clock_pin}\": rise=fall={summary['internal_power_rise_raw']:.6g} raw units "
          f"(dynamic {summary['dynamic_w']*1e3:.6f} mW @ {summary['freq_hz']/1e6:.4f} MHz)")

    if args.dry_run:
        print("--dry-run: not writing any file")
        return 0

    out_path = args.out or args.macro_lib
    with open(out_path, "w") as f:
        f.write(patched)
    print(f"Wrote patched Liberty to {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
