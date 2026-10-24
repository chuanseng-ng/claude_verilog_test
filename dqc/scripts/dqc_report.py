#!/usr/bin/env python3
"""Judge one SpyGlass goal run from its REPORTS (never from the tool's exit code).

Usage (called by dqc/Makefile):
    dqc_report.py --goal cdc/cdc_verify_struct --run dqc/run/default --tag cdc_verify \
                  --top soc_top --arm default --awl "a.awl b.awl"

Verdict
  PASS        rules completed, 0 unwaived Fatal, 0 unwaived Error
  FAIL        rules completed, >=1 unwaived Fatal/Error  (the count is printed, nothing is hidden)
  INCOMPLETE  the goal did not complete its rules, or part of the first-party design was
              black-boxed by the tool (so a clean count would mean nothing).  Exit status 2.
Exit status: 0 PASS, 1 FAIL, 2 INCOMPLETE (both non-zero are failures for `make`).

A message is "waived" when SpyGlass itself waived it through a `waive` command in an .awl file
read by sg_run.tcl; SpyGlass reports the waived count in the moresimple header, and the waived
messages are not in the table, so every row parsed here is UNWAIVED by construction.

The waiver files are also audited here: every `waive` must carry -rules, a scope (-du/-ip/-file/
-file_line/-msg/-signature) and a -comment with  id= by= why= .  A waiver without them FAILs the run.

Stdlib only (python 3.8 on the EDA host).
"""
import argparse
import collections
import glob
import json
import os
import re
import sys

SEV_RE = (r"(?:Fatal|Error|Warning|Info|SynthesisError|SynthesisWarning|SynthesisInfo|"
          r"Caution|Data|Note|Advisory|Analysis|Verification|Violation|[A-Za-z]*(?:Error|Warning|Info))")
ROW = re.compile(r"^\[(\w+)\]\s+(\S+)\s+(?:(.*?)\s+)?(" + SEV_RE + r")\s+(\S+)\s+(\d+)\s+(\d+)\s+(.*)$")
ROW_NOFILE = re.compile(r"^\[(\w+)\]\s+(\S+)\s+(?:(.*?)\s+)?(" + SEV_RE + r")\s+(\S+)?\s*(\d+)?\s*(\d+)\s+(.*)$")


def sev_class(label):
    low = label.lower()
    if "fatal" in low:
        return "fatal"
    if low.endswith("error"):
        return "error"
    if low.endswith("warning") or low == "caution":
        return "warning"
    return "info"


def find_report(run, goal, top):
    pname = goal.replace("/", "_")
    pats = [os.path.join(run, pname, "consolidated_reports", "%s_%s" % (top, pname.replace("/", "_")), "moresimple.rpt"),
            os.path.join(run, pname, "consolidated_reports", "*", "moresimple.rpt"),
            os.path.join(run, pname, "*", "*", "*", "spyglass_reports", "moresimple.rpt")]
    for p in pats:
        hits = sorted(glob.glob(p))
        if hits:
            return hits[0]
    return None


def parse_rows(path, repo):
    rows, unparsed = [], 0
    group = ""
    for line in open(path, errors="replace"):
        line = line.rstrip("\n")
        m = re.match(r"^#+ (.*?) #+$", line)
        if m:
            group = m.group(1)
            continue
        if not line.startswith("["):
            continue
        m = ROW.match(line) or ROW_NOFILE.match(line)
        if not m:
            unparsed += 1
            continue
        rid, rule, alias, sev, f, ln, wt, msg = m.groups()
        f = f or ""
        # map the overlay copies back to the repository path (line numbers are preserved)
        f = re.sub(r"^.*/dqc/run/[^/]+/overlay/", "", f)
        if f.startswith(repo + "/"):
            f = f[len(repo) + 1:]
        rows.append({"id": rid, "rule": rule, "sev": sev, "cls": sev_class(sev), "file": f,
                     "line": int(ln) if ln else 0, "msg": msg.strip(), "group": group})
    return rows, unparsed


def header_counts(path):
    h = {}
    for line in open(path, errors="replace"):
        m = re.match(r"^#\s+(Total Number of Generated Messages|Number of Waived Messages|"
                     r"Number of Reported Messages|Number of Overlimit Messages)\s*:\s*(\d+)", line)
        if m:
            h[m.group(1)] = int(m.group(2))
        if line.startswith("+++"):
            break
    return h


def audit_awl(files):
    """Every waive needs -rules, a scope and a -comment with id= by= why=.  Returns (list, problems)."""
    waivers, problems = [], []
    for f in files:
        txt = open(f).read()
        # join Tcl line continuations
        txt = txt.replace("\\\n", " ")
        for ln in txt.splitlines():
            s = ln.strip()
            if not s.startswith("waive "):
                continue
            w = {"file": os.path.basename(f), "text": s}
            m = re.search(r'-comment\s+(?:"([^"]*)"|\{([^}]*)\})', s)
            c = (m.group(1) or m.group(2)) if m else ""
            w["comment"] = c
            w["rules"] = bool(re.search(r"-rules?\s", s))
            w["scope"] = bool(re.search(r"-(du|ip|file|file_line|file_lineblock|msg|signature)\s", s))
            miss = []
            if not w["rules"]:
                miss.append("-rules")
            if not w["scope"]:
                miss.append("scope(-du/-file/-file_line/-msg)")
            for k in ("id=", "by=", "why="):
                if k not in c:
                    miss.append("comment " + k)
            if miss:
                problems.append("%s: waiver missing %s: %s" % (os.path.basename(f), ", ".join(miss), s[:100]))
            waivers.append(w)
    return waivers, problems


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--goal", required=True)
    ap.add_argument("--run", required=True)
    ap.add_argument("--tag", required=True)
    ap.add_argument("--top", default="soc_top")
    ap.add_argument("--arm", default="default")
    ap.add_argument("--awl", default="")
    ap.add_argument("--top-n", type=int, default=12)
    a = ap.parse_args()

    repo = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
    logdir = os.path.join(a.run, a.tag)
    out_log = os.path.join(logdir, "sg_shell.out")
    reasons = []

    # --- run completion -------------------------------------------------------------------
    log = open(out_log, errors="replace").read() if os.path.isfile(out_log) else ""
    if not log:
        reasons.append("no sg_shell output (%s)" % out_log)
    if "FATAL: errors found in tcl startup file" in log:
        m = re.search(r"FATAL: errors found in tcl startup file.*?\n\s*\((.*?)\)", log, re.S)
        reasons.append("sg_shell script aborted: %s" % (m.group(1) if m else "see sg_shell.out"))
    if "Results Summary" not in log:
        reasons.append("no 'Results Summary': the goal did not finish")
    rpt = find_report(a.run, a.goal, a.top)
    rows, unparsed, hdr = [], 0, {}
    if rpt is None:
        reasons.append("no moresimple.rpt produced")
    else:
        rows, unparsed = parse_rows(rpt, repo)
        hdr = header_counts(rpt)
        if hdr and len(rows) + unparsed != hdr.get("Number of Reported Messages", len(rows) + unparsed):
            reasons.append("parsed %d+%d rows but the report header says %d reported messages"
                           % (len(rows), unparsed, hdr["Number of Reported Messages"]))
        if unparsed:
            reasons.append("%d report rows could not be parsed" % unparsed)

    # first-party module black-boxed by the tool => nothing was analysed there
    for r in rows:
        if r["rule"] == "ErrorAnalyzeBBox" and "UnsynthesizedDU" in r["msg"]:
            reasons.append("module black-boxed by the tool: %s (%s:%d)" % (r["msg"][:110], r["file"], r["line"]))
        if r["rule"] in ("ErrorAnalyzeBBox", "WarnAnalyzeBBox") and "no definition" in r["msg"]:
            reasons.append("undefined module: %s (%s:%d)" % (r["msg"][:100], r["file"], r["line"]))
    # stop at the first fatal parse errors
    fat = [r for r in rows if r["cls"] == "fatal"]

    # --- counts ---------------------------------------------------------------------------
    cnt = collections.Counter(r["cls"] for r in rows)
    waived = hdr.get("Number of Waived Messages", 0)
    awls = [x for x in a.awl.split() if x]
    waivers, wprob = audit_awl(awls)
    for p in wprob:
        reasons.append("waiver audit: " + p)

    # --- timing ---------------------------------------------------------------------------
    tfile = os.path.join(logdir, "time.txt")
    timing = open(tfile).read().strip().splitlines()[-1] if os.path.isfile(tfile) and open(tfile).read().strip() else "n/a"

    unw_err = cnt["fatal"] + cnt["error"]
    if reasons:
        verdict = "INCOMPLETE"
    elif unw_err:
        verdict = "FAIL"
    else:
        verdict = "PASS"

    # --- artifacts ------------------------------------------------------------------------
    byrule = collections.Counter((r["cls"], r["rule"]) for r in rows)
    summ = {"goal": a.goal, "arm": a.arm, "top": a.top, "verdict": verdict, "reasons": reasons,
            "fatal": cnt["fatal"], "error": cnt["error"], "warning": cnt["warning"], "info": cnt["info"],
            "waived_total": waived, "waivers_in_files": len(waivers), "report": rpt, "timing": timing,
            "by_rule": {"%s:%s" % k: v for k, v in sorted(byrule.items())}}
    with open(os.path.join(a.run, a.tag + ".summary.json"), "w") as fh:
        json.dump(summ, fh, indent=1)
    with open(os.path.join(a.run, a.tag + ".unwaived.tsv"), "w") as fh:
        fh.write("class\trule\tseverity\tfile\tline\tmessage\n")
        for r in sorted(rows, key=lambda r: (["fatal", "error", "warning", "info"].index(r["cls"]), r["rule"], r["file"], r["line"])):
            fh.write("%s\t%s\t%s\t%s\t%d\t%s\n" % (r["cls"], r["rule"], r["sev"], r["file"], r["line"], r["msg"]))

    # --- compact console summary ----------------------------------------------------------
    print("=" * 78)
    print("DQC %-26s arm=%-8s top=%s" % (a.goal, a.arm, a.top))
    print("  fatal=%d error=%d warning=%d info=%d   (all UNWAIVED) | waived by .awl: %d | waiver cmds: %d"
          % (cnt["fatal"], cnt["error"], cnt["warning"], cnt["info"], waived, len(waivers)))
    print("  unwaived Fatal+Error: %d" % unw_err)
    print("  run: %s" % timing)
    print("  report: %s" % (os.path.relpath(rpt, repo) if rpt else "(none)"))
    print("  all rows: %s" % os.path.relpath(os.path.join(a.run, a.tag + ".unwaived.tsv"), repo))
    top = [(k, v) for k, v in byrule.most_common() if k[0] in ("fatal", "error")][:a.top_n]
    for (c, rule), v in top:
        print("    %-6s %-26s x%d" % (c, rule, v))
    for rs in reasons[:8]:
        print("  INCOMPLETE/NOTE: %s" % rs)
    print("  VERDICT: %s" % verdict)
    print("=" * 78)
    return {"PASS": 0, "FAIL": 1, "INCOMPLETE": 2}[verdict]


if __name__ == "__main__":
    sys.exit(main())
