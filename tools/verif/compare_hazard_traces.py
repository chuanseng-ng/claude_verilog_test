#!/usr/bin/env python3
"""Diff two rv32i_hazard_unit random-vector trace files for cross-arm equivalence.

Companion to tb/cocotb/cpu/test_hazard_unit.py's test_random_cross_arm, which
dumps (inputs, outputs) for N random vectors to sim/build/hazard_trace_<TOPLEVEL>.json.
Run once against the hand-RTL arm (TOPLEVEL=rv32i_hazard_unit) and once against
the HLS arm (TOPLEVEL=rv32i_hazard_unit_hls), then diff the two trace files with
this script -- that diff, not either arm's directed tests, is the actual
cross-arm equivalence evidence for GH #119 bead `gvr`.

Exit code convention mirrors tools/eda/summarize.py (bead `dwp`: an unparsed
or vacuous result must never read as PASS):

    0  PASS   both traces present, same stimulus, every output matched
    1  FAIL   both traces compared cleanly but at least one vector's outputs
               differed -- a real cross-arm mismatch
    2  ERROR  either trace file is missing/empty/unparsable, has zero
               vectors, the two files have different vector counts, or the
               two files were not driven with the same input sequence --
               nothing meaningful was compared

Stdlib only, run outside the repo virtualenv same as the tools/eda wrappers.

Usage:
    compare_hazard_traces.py <trace_a.json> <trace_b.json> [--max-mismatches N]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PASS, FAIL, ERROR = 0, 1, 2

DEFAULT_MAX_MISMATCHES = 20


def _error(reason: str, **extra) -> dict:
    verdict = {"status": "ERROR", "exit_code": ERROR, "reason": reason}
    verdict.update(extra)
    return verdict


def _load_trace(path: Path) -> tuple[dict | None, str | None]:
    """Return (trace_dict, None) or (None, error_reason)."""
    if not path.exists():
        return None, f"trace file not found: {path}"
    try:
        text = path.read_text()
    except OSError as exc:
        return None, f"could not read {path}: {exc}"
    if not text.strip():
        return None, f"trace file is empty: {path}"
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        return None, f"trace file is not valid JSON: {path} ({exc})"
    if not isinstance(data, dict) or "vectors" not in data:
        return None, f"trace file missing 'vectors' key: {path}"
    vectors = data["vectors"]
    if not isinstance(vectors, list) or len(vectors) == 0:
        return None, f"trace file has zero vectors: {path}"
    for i, v in enumerate(vectors):
        if not isinstance(v, dict) or "inputs" not in v or "outputs" not in v:
            return None, f"trace file vector {i} malformed (missing inputs/outputs): {path}"
    return data, None


def compare(path_a: Path, path_b: Path, max_mismatches: int) -> dict:
    trace_a, err_a = _load_trace(path_a)
    if err_a:
        return _error(err_a, file=str(path_a))
    trace_b, err_b = _load_trace(path_b)
    if err_b:
        return _error(err_b, file=str(path_b))

    vectors_a = trace_a["vectors"]
    vectors_b = trace_b["vectors"]

    if len(vectors_a) != len(vectors_b):
        return _error(
            "vector count mismatch -- traces were not generated with the same run",
            count_a=len(vectors_a),
            count_b=len(vectors_b),
            toplevel_a=trace_a.get("toplevel"),
            toplevel_b=trace_b.get("toplevel"),
        )

    # Refuse to compare traces driven with different stimulus: the two arms
    # must have been fed identical inputs (same seed/count) or an output
    # match/mismatch means nothing.
    for i, (va, vb) in enumerate(zip(vectors_a, vectors_b, strict=True)):
        if va["inputs"] != vb["inputs"]:
            return _error(
                "input sequences differ -- traces were not driven with the same "
                "stimulus (check HAZARD_TRACE_SEED/HAZARD_TRACE_N match on both arms)",
                first_diverging_index=i,
                inputs_a=va["inputs"],
                inputs_b=vb["inputs"],
            )

    mismatches = []
    for i, (va, vb) in enumerate(zip(vectors_a, vectors_b, strict=True)):
        oa, ob = va["outputs"], vb["outputs"]
        diff_fields = {}
        # Union of keys: an output field present in one trace but not the
        # other is itself a mismatch worth reporting, not silently skipped.
        for field in sorted(set(oa) | set(ob)):
            va_val = oa.get(field, "<missing>")
            vb_val = ob.get(field, "<missing>")
            if va_val != vb_val:
                diff_fields[field] = {"a": va_val, "b": vb_val}
        if diff_fields:
            mismatches.append({"index": i, "inputs": va["inputs"], "fields": diff_fields})

    total = len(vectors_a)
    reported = mismatches[:max_mismatches]
    truncated = len(mismatches) - len(reported)

    if mismatches:
        return {
            "status": "FAIL",
            "exit_code": FAIL,
            "total_vectors": total,
            "mismatch_count": len(mismatches),
            "mismatches": reported,
            "truncated_additional_mismatches": max(truncated, 0),
            "toplevel_a": trace_a.get("toplevel"),
            "toplevel_b": trace_b.get("toplevel"),
        }

    return {
        "status": "PASS",
        "exit_code": PASS,
        "total_vectors": total,
        "mismatch_count": 0,
        "toplevel_a": trace_a.get("toplevel"),
        "toplevel_b": trace_b.get("toplevel"),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trace_a", type=Path)
    parser.add_argument("trace_b", type=Path)
    parser.add_argument(
        "--max-mismatches",
        type=int,
        default=DEFAULT_MAX_MISMATCHES,
        help=f"cap the number of reported mismatches (default {DEFAULT_MAX_MISMATCHES})",
    )
    args = parser.parse_args(argv)

    verdict = compare(args.trace_a, args.trace_b, args.max_mismatches)

    if verdict["status"] == "PASS":
        print(f"PASS: {verdict['total_vectors']} vectors, 0 mismatches")
    elif verdict["status"] == "FAIL":
        print(
            f"FAIL: {verdict['mismatch_count']}/{verdict['total_vectors']} "
            f"vectors mismatched (showing first {len(verdict['mismatches'])})"
        )
        for m in verdict["mismatches"]:
            fields = ", ".join(f"{k}(a={v['a']},b={v['b']})" for k, v in m["fields"].items())
            print(f"  vector {m['index']}: {fields}")
            print(f"    inputs: {m['inputs']}")
    else:
        print(f"ERROR: {verdict['reason']}")

    print(json.dumps(verdict, indent=2))
    return verdict["exit_code"]


if __name__ == "__main__":
    sys.exit(main())
