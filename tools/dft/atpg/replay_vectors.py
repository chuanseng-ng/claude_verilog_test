#!/usr/bin/env python3
"""Turn Quaigh patterns plus expected responses into tb memories for replay_tb.sv (bead j41m.19).

usage: replay_vectors.py --map map.json --patterns P.test --expected E.test --out DIR [--select 1,5,9 | --first N] [--info replay_info.json]

Reads the plan of pattern_map.py.  For each selected pattern (1-based line number of the .test file) it writes, under DIR:
  pi.hex   cut inputs then the free-latch bits, 32 bit words, bit i of the vector = bit i of word i//32
  po.hex   expected outputs (cut `.outputs` order)
  ld.hex   scan-in byte per shift edge: bit k = chain k (chain_load_stream)
  ex.hex   expected scan-out byte per shift edge of the NEXT shift phase (chain_unload_stream of the captured D values)
  mk.hex   compare mask per scan-out bit (0 for: chain padding, hold-masked flops, chains the cut does not contain)
  params.svh   localparams for the tb
The tb applies pattern i: shift-in ld[i] while comparing ex[i-1]; capture with pi[i]; compare po[i].
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pattern_map import chain_load_stream, chain_unload_stream  # noqa: E402


def read_patterns(path, wanted):
    out = {}
    with open(path) as fh:
        for ln in fh:
            if ln[0] == "*":
                continue
            n, bits = ln.split(": ")
            n = int(n)
            if wanted is None or n in wanted:
                out[n] = bits.strip()
    return out


def words(bits_lsb_first):
    n = (len(bits_lsb_first) + 31) // 32
    ws = []
    for w in range(n):
        v = 0
        for b, ch in enumerate(bits_lsb_first[w * 32:(w + 1) * 32]):
            if ch == "1":
                v |= 1 << b
        ws.append(v)
    return ws


def scan_in_index(plan):
    """Index of `scan_in_i[0]` in the cut inputs, or -1.  The harness drives the 8 pins from the pattern bits in capture."""
    sel = sorted((x["chain"], i) for i, x in enumerate(plan["inputs"]) if x["kind"] == "scan_in")
    if not sel:
        return -1
    first = sel[0][1]
    if [k for k, _ in sel] != list(range(len(sel))) or [i for _, i in sel] != list(range(first, first + len(sel))):
        raise SystemExit("scan_in inputs are not contiguous and in chain order")
    return first


def po_mask_words(plan, ports):
    """Compare mask of the cut outputs, 32 bit words: 0 for a `pin` output of one of `ports` (not strobed in capture)."""
    return words(["0" if x["kind"] == "pin" and x.get("port") in ports else "1" for x in plan["outputs"]])


def build(plan, pat, exp, n_pi_extra):
    nin, nout = len(plan["inputs"]), len(plan["outputs"])
    L = max(plan["chain_len"])
    nch = len(plan["chain_len"])
    pi = list(pat[:nin]) + ["0"] * n_pi_extra
    free = [j for j, x in enumerate(plan["latches"]) if x["kind"] == "free"]
    for f, j in enumerate(free):
        pi[nin + f] = pat[nin + j]
    for i, x in enumerate(plan["inputs"]):
        if x["kind"] not in ("pin", "bb", "scan_in"):  # scan_in bits are the capture-time value of the scan_in_i pins
            pi[i] = "0"
    vals = [[0] * n for n in plan["chain_len"]]
    dvals = [[0] * n for n in plan["chain_len"]]
    mask = [[0] * n for n in plan["chain_len"]]
    for j, x in enumerate(plan["latches"]):
        if x["kind"] == "scan":
            k, p = x["chain"], x["pos"]
            vals[k][p] = int(pat[nin + j])
            dvals[k][p] = int(exp[nout + j])
            mask[k][p] = 0 if x.get("masked") else 1
    ld = [0] * L
    ex = [0] * L
    mk = [0] * L
    for k in range(nch):
        if not plan["chain_len"][k]:
            continue
        ls = chain_load_stream(vals[k], L)
        es = chain_unload_stream(dvals[k], L)
        ms = chain_unload_stream(mask[k], L)
        for c in range(L):
            ld[c] |= ls[c] << k
            ex[c] |= es[c] << k
            mk[c] |= ms[c] << k
    return "".join(pi), exp[:nout], ld, ex, mk


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--map", required=True)
    ap.add_argument("--patterns", required=True)
    ap.add_argument("--expected", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--select")
    ap.add_argument("--first", type=int)
    ap.add_argument("--info")
    ap.add_argument("--mask-po-port", default="", help="comma list of top ports whose primary outputs are not compared in capture")
    a = ap.parse_args(argv)
    plan = json.loads(Path(a.map).read_text())
    sel = None
    if a.select:
        sel = [int(x) for x in a.select.split(",")]
    elif a.first:
        sel = list(range(1, a.first + 1))
    pats = read_patterns(a.patterns, set(sel) if sel else None)
    exps = read_patterns(a.expected, set(sel) if sel else None)
    # the expected file renumbers from 1 in selection order when it was produced from a selected file: accept both
    order = sel if sel else sorted(pats)
    if set(order) - set(exps):
        exps = dict(zip(order, [exps[k] for k in sorted(exps)]))
    nfree = sum(1 for x in plan["latches"] if x["kind"] == "free")
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    f_pi, f_po, f_ld, f_ex, f_mk = (open(out / n, "w") for n in ("pi.hex", "po.hex", "ld.hex", "ex.hex", "mk.hex"))
    L = max(plan["chain_len"])
    nin, nout = len(plan["inputs"]), len(plan["outputs"])
    for n in order:
        pi, po, ld, ex, mk = build(plan, pats[n], exps[n], nfree)
        f_pi.write("".join(f"{w:08x}\n" for w in words(pi)))
        f_po.write("".join(f"{w:08x}\n" for w in words(po)))
        f_ld.write("".join(f"{b:02x}\n" for b in ld))
        f_ex.write("".join(f"{b:02x}\n" for b in ex))
        f_mk.write("".join(f"{b:02x}\n" for b in mk))
    for f in (f_pi, f_po, f_ld, f_ex, f_mk):
        f.close()
    idx = {x["name"]: i for i, x in enumerate(plan["inputs"])}
    lens = plan["chain_len"]
    (out / "params.svh").write_text(
        f"localparam NPAT = {len(order)};\nlocalparam L = {L};\nlocalparam N_PI = {nin + nfree};\nlocalparam N_PO = {nout};\n"
        f"localparam PIW = {(nin + nfree + 31) // 32};\nlocalparam POW = {(nout + 31) // 32};\n"
        f"localparam integer IDX_TMS = {idx.get('tms_i', -1)};\nlocalparam integer IDX_TDI = {idx.get('tdi_i', -1)};\n"
        f"localparam NFAULT = {json.loads(Path(a.info).read_text())['n_fault'] if a.info else 0};\n"
        f"localparam integer CHLEN [0:7] = '{{{', '.join(str(x) for x in lens)}}};\n")
    ports = {x for x in a.mask_po_port.split(",") if x}
    (out / "pm.hex").write_text("".join(f"{w:08x}\n" for w in po_mask_words(plan, ports)))
    (out / "params_h.h").write_text(
        f"#define IDX_SI {scan_in_index(plan)}\n#define NPAT {len(order)}\n#define L {L}\n#define N_PI {nin + nfree}\n#define N_PO {nout}\n#define PIW {(nin + nfree + 31) // 32}\n"
        f"#define POW {(nout + 31) // 32}\n#define NFREE {nfree}\n" + "".join(f"#define CH{i} {lens[i]}\n" for i in range(8)))
    (out / "selection.json").write_text(json.dumps(order))
    print(json.dumps({"patterns": len(order), "L": L, "chain_len": lens}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
