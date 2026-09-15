#!/usr/bin/env python3
"""Parse a batched yosys eval log (VECTOR_MARKER-delimited) against vectors.json
and report PASS/FAIL per vector, comparing to the golden expected values."""
import json
import re
import sys

N_LANES = 8
REG_WIDTH = 32
MASK32 = 0xFFFF_FFFF


def unpack(val):
    out = []
    for _ in range(N_LANES):
        out.append(val & MASK32)
        val >>= REG_WIDTH
    return out


def main():
    vectors_path, log_path = sys.argv[1:3]
    with open(vectors_path) as f:
        vectors = json.load(f)

    # Split log into per-vector chunks by VECTOR_MARKER lines.
    text = open(log_path).read()
    # Each vector's results precede its own VECTOR_MARKER line (eval runs,
    # then the marker for that same call is logged right after).
    chunks = re.split(r"\nVECTOR_MARKER (\d+) \S+\n", text)
    # chunks[0] = preamble; then alternating (idx_str, chunk_text)
    results_by_idx = {}
    for i in range(1, len(chunks), 2):
        idx = int(chunks[i])
        body = chunks[i - 1] if i - 1 >= 0 else ""
        # body is text BEFORE this marker; but that also includes the
        # previous vector's marker line remnants. We only need the eval
        # results contained in body since the last marker, i.e. this body
        # itself (re.split already segments between markers correctly for
        # eval-then-marker ordering).
        results_by_idx[idx] = body

    fails = []
    passes = 0
    errors = []
    for idx, v in enumerate(vectors):
        body = results_by_idx.get(idx)
        if body is None:
            errors.append((idx, v["tag"], "no eval body found"))
            continue
        m_done = re.search(r"Eval result: \\done_o = 1'([01x]+)\.", body)
        m_res = re.search(r"Eval result: \\result_o = 256'([01x]+)\.", body)
        m_taken = re.search(r"Eval result: \\branch_taken_o = 8'([01x]+)\.", body)
        fail_msgs = re.findall(r"Failed to evaluate signal \\(\S+)", body)
        if fail_msgs or not m_done or not m_res or not m_taken:
            errors.append((idx, v["tag"], f"failed signals: {fail_msgs}, missing={not m_done or not m_res or not m_taken}"))
            continue
        result_bits = m_res.group(1)
        taken_bits = m_taken.group(1)
        if "x" in result_bits or "x" in taken_bits:
            errors.append((idx, v["tag"], f"X in output: result={result_bits[:40]}... taken={taken_bits}"))
            continue
        result_val = int(result_bits, 2)
        taken_val = int(taken_bits, 2)
        got_lanes = unpack(result_val)

        ok = True
        msg = []
        if "exp_result" in v:
            exp_lanes = v["exp_result"]
            if got_lanes != exp_lanes:
                ok = False
                msg.append(f"result mismatch: got={[hex(x) for x in got_lanes]} exp={[hex(x) for x in exp_lanes]}")
        if "exp_taken" in v:
            if taken_val != v["exp_taken"]:
                ok = False
                msg.append(f"branch_taken mismatch: got={taken_val:#010b} exp={v['exp_taken']:#010b}")

        if ok:
            passes += 1
        else:
            fails.append((idx, v["tag"], v["op"], "; ".join(msg)))

    print(f"Total vectors: {len(vectors)}")
    print(f"PASS: {passes}")
    print(f"FAIL: {len(fails)}")
    print(f"ERRORS (parse/eval failures): {len(errors)}")
    if fails:
        print("\n--- First 10 FAILs ---")
        for idx, tag, op, msg in fails[:10]:
            print(f"[{idx}] {tag} ({op}): {msg}")
    if errors:
        print("\n--- First 10 ERRORS ---")
        for idx, tag, msg in errors[:10]:
            print(f"[{idx}] {tag}: {msg}")


if __name__ == "__main__":
    main()
