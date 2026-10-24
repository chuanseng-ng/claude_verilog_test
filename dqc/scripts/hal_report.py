#!/usr/bin/env python3
"""Judge a Cadence HAL run from hal.log (never from the exit code) and apply dqc/waivers/hal.waivers.

HAL message format:   <engine>: *<E|W|N>,<TAG> (<file>,<line>|<col>): <text>
Verdict: PASS (0 unwaived errors), FAIL (>=1 unwaived error), INCOMPLETE (no 'Analysis complete',
no 'Analysis summary', or the compile aborted).  Exit 0 / 1 / 2.

Waiver file (dqc/waivers/hal.waivers), one per line, '|' separated, '#' comments:
    id | tag | file-regex | message-regex | by | why
All six fields are mandatory (tag may be '*' only for a file-regex scoped waiver).  A waiver that
matches nothing is reported STALE and fails the run, like the cdc_gate waivers.
Stdlib only (python 3.8).
"""
import argparse
import collections
import json
import os
import re
import sys

MSG = re.compile(r"^(hal\w+): \*([EWN]),(\w+) \((.*?),(\d+)(?:\|\d+)?\): (.*)$")


def load_waivers(path):
    ws, problems = [], []
    if not os.path.isfile(path):
        return ws, problems
    for n, ln in enumerate(open(path), 1):
        s = ln.strip()
        if not s or s.startswith("#"):
            continue
        p = [x.strip() for x in s.split("|")]
        if len(p) != 6 or not all(p):
            problems.append("hal.waivers:%d needs 6 non-empty fields (id|tag|file|msg|by|why)" % n)
            continue
        ws.append({"id": p[0], "tag": p[1], "file": re.compile(p[2]), "msg": re.compile(p[3]),
                   "by": p[4], "why": p[5], "hits": 0})
    return ws, problems


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--log", required=True)
    ap.add_argument("--waivers", default="")
    ap.add_argument("--arm", default="default")
    ap.add_argument("--timing", default="n/a")
    ap.add_argument("--out", required=True, help="prefix for .summary.json / .unwaived.tsv")
    a = ap.parse_args()
    repo = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))

    reasons = []
    txt = open(a.log, errors="replace").read() if os.path.isfile(a.log) else ""
    if not txt:
        reasons.append("no hal.log")
    if "Analysis complete" not in txt:
        reasons.append("'Analysis complete' missing: HAL did not finish")
    if "Analysis summary" not in txt:
        reasons.append("'Analysis summary' missing")
    ws, wprob = load_waivers(a.waivers)
    reasons += ["waiver audit: " + p for p in wprob]

    rows, waived = [], collections.Counter()
    cnt = collections.Counter()
    for ln in txt.splitlines():
        m = MSG.match(ln)
        if not m:
            continue
        eng, sev, tag, f, line, text = m.groups()
        f = re.sub(r"^(?:.*/dqc/run/[^/]+/|(?:\.\./)+)overlay/", "", f)
        if f.startswith(repo + "/"):
            f = f[len(repo) + 1:]
        hit = None
        for w in ws:
            if w["tag"] in ("*", tag) and w["file"].search(f) and w["msg"].search(text):
                w["hits"] += 1
                hit = w
                break
        if hit:
            waived[(sev, tag)] += 1
            continue
        cnt[sev] += 1
        rows.append((sev, tag, f, line, text))
    for w in ws:
        if w["hits"] == 0:
            reasons.append("STALE waiver %s matched nothing" % w["id"])

    verdict = "INCOMPLETE" if reasons else ("FAIL" if cnt["E"] else "PASS")
    by = collections.Counter((s, t) for s, t, *_ in rows)
    with open(a.out + ".unwaived.tsv", "w") as fh:
        fh.write("sev\ttag\tfile\tline\tmessage\n")
        for r in sorted(rows, key=lambda r: ("EWN".index(r[0]), r[1], r[2], int(r[3]))):
            fh.write("%s\t%s\t%s\t%s\t%s\n" % r)
    with open(a.out + ".summary.json", "w") as fh:
        json.dump({"tool": "hal", "arm": a.arm, "verdict": verdict, "reasons": reasons, "error": cnt["E"],
                   "warning": cnt["W"], "note": cnt["N"], "waived": sum(waived.values()),
                   "timing": a.timing, "by_tag": {"%s:%s" % k: v for k, v in sorted(by.items())}}, fh, indent=1)
    print("=" * 78)
    print("DQC hal arm=%s" % a.arm)
    print("  error=%d warning=%d note=%d (UNWAIVED) | waived: %d | waiver lines: %d"
          % (cnt["E"], cnt["W"], cnt["N"], sum(waived.values()), len(ws)))
    print("  run: %s" % a.timing)
    for (s, t), v in by.most_common(12):
        if s == "E":
            print("    E %-10s x%d" % (t, v))
    for r in reasons[:8]:
        print("  INCOMPLETE/NOTE: " + r)
    print("  all rows: %s.unwaived.tsv" % os.path.relpath(a.out, repo))
    print("  VERDICT: %s" % verdict)
    print("=" * 78)
    return {"PASS": 0, "FAIL": 1, "INCOMPLETE": 2}[verdict]


if __name__ == "__main__":
    sys.exit(main())
