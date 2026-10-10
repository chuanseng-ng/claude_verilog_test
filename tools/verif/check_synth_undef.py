#!/usr/bin/env python3
"""Fail a synthesis run that let the frontend silently replace logic with undef (bead gc0y).

Why this exists
---------------
Synlig/UHDM elaborated two hazard-unit port connections (a part-select of a packed-struct member
in a port connection) as ``5'x`` and logged only ``Warning: Range select [639:608] out of bounds
on signal ... Setting all 32 result bits to undef``.  Synthesis then deleted the forwarding-select
flops; lint, ``Checker.YosysSynthChecks``, LVS and P&R all passed on the smaller, wrong design
(beads dud4 / ma7; docs/SKY130_CPU_SYNLIG_DUD4.md).

Two independent detectors, so a wording change in one tool release cannot blind the gate:

* **Log scanner** (``scan_log``) - message patterns from the yosys 0.46/0.62 and Synlig plugin
  binaries and from probe designs run through both frontends (tools/verif/synth_gate/probes).
* **Structural check** (``scan_header_json``) - reads the pre-synthesis ``<design>.h.json`` that the
  flow already writes (``Yosys.JsonHeader``: elaborated, hierarchical, before optimisation) and
  fails on any module-instance input port, or any named net, connected to constant ``x``.  It does
  not depend on any message text.

Exit codes: 0 pass, 1 an un-allowlisted FAIL finding, 2 the input could not be judged (no log,
empty log, no recognisable synthesis banner).  Never a vacuous pass.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import re
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_ALLOWLIST = Path(__file__).with_name("synth_undef_allowlist.txt")

# rule id -> (severity, regex, one-line reason).  Order matters: first match wins per line.
RULES: dict[str, tuple[str, str, str]] = {
    "undef-range-select": (
        "FAIL",
        r"out of bounds on signal .*Setting .*to undef",
        "constant bit/part-select outside the signal; the frontend substituted x (the dud4 defect)",
    ),
    "undef-substitution": (
        "FAIL",
        r"Warning:.*\b(?:[Ss]etting|[Rr]eplacing|[Ss]ubstituting)\b.*\bundef\b",
        "the tool states it replaced an expression with undef",
    ),
    "no-driver": (
        "FAIL",
        r"Wire .* is used but has no driver",
        "a used net has no driver; yosys later ties it to an arbitrary constant",
    ),
    "multi-driver": (
        "FAIL",
        r"multiple conflicting drivers for",
        "two drivers on one net; one is silently dropped or the result is x",
    ),
    "port-resize": (
        "FAIL",
        r"Resizing cell port .* from \d+ bits to \d+ bits",
        "instance port connected with a different width; bits silently dropped or zero-extended",
    ),
    "implicit-decl": (
        "FAIL",
        r"Identifier .* is implicitly declared",
        "an identifier was not declared; a typo becomes a new undriven 1-bit net",
    ),
    "tool-error": (
        "FAIL",
        r"(?:^|[\s:])ERROR:",
        "the tool reported an error (a flow that continued past it must not pass)",
    ),
    "post-increment": (
        "WARN",
        r"Post-incrementation operations are handled as pre-incrementation",
        "Synlig treats x++ as ++x; harmless for a for-loop step, a hard error when the value is "
        "used (probes p13/p19, docs/SYNTH_UNDEF_GATE.md)",
    ),
    "removed-module": (
        "WARN",
        r"Removing unelaborated module: (\S+)",
        "Synlig drops the un-parameterised copy once a $paramod copy exists (cross-checked)",
    ),
    "mem2reg": (
        "INFO",
        r"Replacing memory .* with list of registers",
        "array turned into registers; an out-of-range constant index shows up as x-driven-net",
    ),
    "assigned-in-block": (
        "INFO",
        r"wire '.*' is assigned in a block",
        "a wire-typed object assigned procedurally; yosys treats it as a reg",
    ),
    "setundef-count": (
        "INFO",
        r"Replacing (\d+) occurrences of constant undef bits with constant zero bits",
        "SYNTH_TIE_UNDEFINED: total x bits tied low after optimisation (informational count)",
    ),
}
# Rules that only exist for the structural detectors / cross-checks.
STRUCTURAL_RULES = {
    "x-driven-instance-input": "an instance input port is wired to constant x",
    "x-driven-net": "a named net is (partly) driven by constant x",
    "removed-module-missing": "module removed as unelaborated but no $paramod copy exists",
    "header-flattened": "header JSON is flattened; the structural check had nothing to inspect",
}
ALL_RULES = set(RULES) | set(STRUCTURAL_RULES)
_COMPILED = {k: (sev, re.compile(rx), why) for k, (sev, rx, why) in RULES.items()}
_BANNER = re.compile(r"Yosys \d+\.\d+|^\d+\. Executing |Executing \w+ pass|Executing .* frontend")


class InputError(Exception):
    """The input could not be judged (maps to exit code 2)."""


class AllowlistError(Exception):
    """Malformed allowlist (maps to exit code 2)."""


@dataclass(frozen=True)
class Finding:
    rule: str
    severity: str
    path: Path
    line: int
    text: str
    extra: str = ""
    allowed: bool = False
    note: str = ""


@dataclass
class AllowEntry:
    rule: str
    pattern: str
    justification: str
    used: int = field(default=0)

    def matches(self, f: Finding) -> bool:
        if f.rule != self.rule:
            return False
        try:
            return re.search(self.pattern, f.text) is not None
        except re.error:
            return self.pattern in f.text


def scan_log(path: Path | str) -> list[Finding]:
    p = Path(path)
    if not p.is_file():
        raise InputError(f"log not found: {p}")
    raw = p.read_text(errors="replace")
    if not raw.strip():
        raise InputError(f"log is empty: {p}")
    if not any(_BANNER.search(ln) for ln in raw.splitlines()):
        raise InputError(f"no recognisable yosys synthesis banner in {p}; cannot certify it")
    out: list[Finding] = []
    for n, line in enumerate(raw.splitlines(), 1):
        for rule, (sev, rx, _why) in _COMPILED.items():
            m = rx.search(line)
            if m:
                extra = m.group(1).lstrip("\\") if rule == "removed-module" else ""
                out.append(Finding(rule, sev, p, n, line.strip(), extra))
                break
    return out


def _is_user_cell(ctype: str) -> bool:
    return not ctype.startswith("$") or ctype.startswith("$paramod")


def scan_header_json(path: Path | str) -> list[Finding]:
    p = Path(path)
    try:
        data = json.loads(p.read_text())
        mods = data["modules"]
    except (OSError, ValueError, KeyError) as exc:
        raise InputError(f"header JSON unreadable: {p}: {exc}") from exc
    out: list[Finding] = []
    for mname, mod in mods.items():
        short = mname.rsplit("\\", 1)[-1]
        for cname, cell in mod.get("cells", {}).items():
            if not _is_user_cell(cell.get("type", "$")):
                continue
            tgt_ports = mods.get(cell["type"], {}).get("ports", {})
            dirs = cell.get("port_directions", {})
            for pname, bits in cell.get("connections", {}).items():
                if not any(b == "x" for b in bits if isinstance(b, str)):
                    continue
                direction = dirs.get(pname) or tgt_ports.get(pname, {}).get("direction", "?")
                if direction == "output":
                    continue
                pat = "".join(b if isinstance(b, str) else "." for b in bits)
                out.append(
                    Finding(
                        "x-driven-instance-input",
                        "FAIL",
                        p,
                        0,
                        f"{cname} (in {short}, type {cell['type'].rsplit(chr(92), 1)[-1]}) "
                        f"port {pname} [{direction}] <- {pat}",
                    )
                )
        for nname, net in mod.get("netnames", {}).items():
            if nname.startswith("$"):
                continue
            bits = net.get("bits", [])
            nx = sum(1 for b in bits if b == "x")
            if nx:
                out.append(
                    Finding(
                        "x-driven-net",
                        "FAIL",
                        p,
                        0,
                        f"net {nname} (in {short}): {nx}/{len(bits)} bits constant x",
                    )
                )
    if len(mods) == 1 and any(
        c.get("type", "").startswith("$")
        for m in mods.values()
        for c in m.get("cells", {}).values()
    ):
        out.append(
            Finding(
                "header-flattened",
                "INFO",
                p,
                0,
                "header JSON holds a single flattened module; structural check not informative",
            )
        )
    return out


def cross_check_removed_modules(findings: Iterable[Finding], header: Path | str) -> list[Finding]:
    try:
        mods = json.loads(Path(header).read_text())["modules"]
    except (OSError, ValueError, KeyError) as exc:
        raise InputError(f"header JSON unreadable: {header}: {exc}") from exc
    names = list(mods)
    out: list[Finding] = []
    for f in findings:
        if f.rule != "removed-module" or not f.extra:
            continue
        if any(
            n == f.extra
            or n.endswith("\\" + f.extra)
            or n.startswith("$paramod\\" + f.extra + "\\")
            for n in names
        ):
            continue
        out.append(
            Finding(
                "removed-module-missing",
                "FAIL",
                f.path,
                f.line,
                f"module {f.extra} removed as unelaborated and no copy of it is in {header}",
            )
        )
    return out


def load_allowlist(path: Path | str) -> list[AllowEntry]:
    p = Path(path)
    entries: list[AllowEntry] = []
    for n, raw in enumerate(p.read_text().splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = [s.strip() for s in line.split("|", 2)]
        if len(parts) != 3 or not all(parts):
            raise AllowlistError(f"{p}:{n}: need 'rule | pattern | justification' (all non-empty)")
        if parts[0] not in ALL_RULES:
            raise AllowlistError(f"{p}:{n}: unknown rule '{parts[0]}'")
        entries.append(AllowEntry(*parts))
    return entries


def apply_allowlist(findings: Iterable[Finding], entries: Sequence[AllowEntry]) -> list[Finding]:
    out: list[Finding] = []
    for f in findings:
        hit = next((e for e in entries if e.matches(f)), None)
        if hit is None:
            out.append(f)
            continue
        hit.used += 1
        out.append(dataclasses.replace(f, allowed=True, note=hit.justification))
    return out


def stale_entries(entries: Sequence[AllowEntry]) -> list[AllowEntry]:
    return [e for e in entries if e.used == 0]


def dedupe(findings: Iterable[Finding]) -> list[Finding]:
    seen: dict[tuple[str, str], int] = {}
    out: list[Finding] = []
    for f in findings:
        key = (f.rule, re.sub(r"^\S*/", "", f.text))
        if key in seen:
            seen[key] += 1
            continue
        seen[key] = 1
        out.append(f)
    return out


def find_run_inputs(run_dir: Path) -> tuple[list[Path], list[Path]]:
    logs = sorted(run_dir.glob("*yosys*/yosys-*.log"))
    headers = sorted(run_dir.glob("*yosys*/*.h.json"))
    return logs, headers


def evaluate(logs: Sequence[Path], headers: Sequence[Path], entries: Sequence[AllowEntry]) -> dict:
    findings: list[Finding] = []
    for lg in logs:
        findings += scan_log(lg)
    for h in headers:
        findings += scan_header_json(h)
        findings += cross_check_removed_modules(findings, h)
    findings = apply_allowlist(dedupe(findings), entries)
    bad = [f for f in findings if f.severity == "FAIL" and not f.allowed]
    return {
        "verdict": "FAIL" if bad else "PASS",
        "fail_count": len(bad),
        "findings": findings,
        "logs": [str(x) for x in logs],
        "headers": [str(x) for x in headers],
        "structural_check": "RAN" if headers else "NOT RUN (no *.h.json found)",
        "stale_allowlist": [e for e in stale_entries(entries)],
    }


def _fmt(f: Finding) -> str:
    loc = f"{f.path}:{f.line}" if f.line else str(f.path)
    tag = "ALLOWED" if f.allowed else f.severity
    s = f"{tag:7s} [{f.rule}] {loc}: {f.text}"
    if f.allowed:
        s += f"\n          allowlisted: {f.note}"
    return s


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("logs", nargs="*", type=Path, help="yosys/Synlig synthesis logs")
    ap.add_argument(
        "--run-dir", type=Path, help="LibreLane run dir (finds *yosys*/ logs + *.h.json)"
    )
    ap.add_argument("--header-json", type=Path, action="append", default=[])
    ap.add_argument(
        "--allowlist",
        type=Path,
        action="append",
        default=[],
        help="extra allowlist file(s), added to the repo default",
    )
    ap.add_argument(
        "--no-allowlist", action="store_true", help="ignore ALL allowlists (audit mode)"
    )
    ap.add_argument("--json", action="store_true")
    ap.add_argument("-v", "--verbose", action="store_true", help="also print WARN/INFO findings")
    args = ap.parse_args(argv)

    logs = list(args.logs)
    headers = list(args.header_json)
    try:
        if args.run_dir:
            if not args.run_dir.is_dir():
                raise InputError(f"run dir not found: {args.run_dir}")
            rl, rh = find_run_inputs(args.run_dir)
            logs += rl
            headers += rh
        if not logs:
            raise InputError("no synthesis logs given or found")
        al_paths = ([DEFAULT_ALLOWLIST] if DEFAULT_ALLOWLIST.is_file() else []) + args.allowlist
        entries = [] if args.no_allowlist else [e for ap_ in al_paths for e in load_allowlist(ap_)]
        res = evaluate(logs, headers, entries)
    except (InputError, AllowlistError) as exc:
        print(f"check_synth_undef: INPUT ERROR (exit 2): {exc}", file=sys.stderr)
        return 2

    if args.json:
        out = dict(res)
        out["findings"] = [dataclasses.asdict(f) | {"path": str(f.path)} for f in res["findings"]]
        out["stale_allowlist"] = [dataclasses.asdict(e) for e in res["stale_allowlist"]]
        print(json.dumps(out, indent=1))
    else:
        for f in res["findings"]:
            if f.severity == "FAIL" or f.allowed or args.verbose:
                print(_fmt(f))
        for e in res["stale_allowlist"] if args.verbose else []:
            print(f"WARN    [stale-allowlist] '{e.rule} | {e.pattern}' matched nothing")
        print(
            f"check_synth_undef: {res['verdict']} ({res['fail_count']} un-allowlisted FAIL; "
            f"logs={len(logs)}; structural check {res['structural_check']})"
        )
    return 1 if res["verdict"] == "FAIL" else 0


if __name__ == "__main__":
    sys.exit(main())
