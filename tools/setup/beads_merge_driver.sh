#!/usr/bin/env sh
# Git merge driver for .beads/issues.jsonl  (bead b1o)
#
# WHY THIS EXISTS
# ---------------
# .beads/issues.jsonl is a per-record STATE file: one JSON object per issue,
# keyed by id. It was previously declared `merge=union`, which is the right
# driver for an append-only log and the wrong one for state: union concatenates
# hunks, so it can keep a stale `"status":"open"` row for an issue the database
# already closed, and it never reconciles two rows for the same id.
#
# Measured on 2026-08-16: main carried claude_verilog_test-0eh and -pzj as
# "open" (updated_at 2026-08-15T00:43Z / 2026-08-05T10:33Z) at BOTH the #159 and
# #160 merge points, long after both were closed and their fixes merged. Each
# `git pull` then replayed those stale rows back into the Dolt DB through beads'
# post-merge import hook, silently reopening them -- twice, same pair.
#
# WHAT THIS DOES
# --------------
# On merge, regenerate the file from the Dolt database instead of trying to
# reconcile two text versions. The DB is the authoritative store (see
# .beads/metadata.json: backend=dolt), so a regenerated export is correct by
# construction and the subsequent beads import becomes a no-op.
#
# $1 = %A = "ours"/current, and the file git takes as the merge result.
#
# If bd is unavailable we deliberately leave %A untouched (= keep ours) and
# still exit 0: a merge must not hard-fail because a tool is missing, and
# keeping ours is the same outcome the old union driver gave on a clean side.
set -eu

result="$1"

if ! command -v bd >/dev/null 2>&1; then
    echo "beads merge driver: bd not found; keeping our version of $result" >&2
    exit 0
fi

if bd export -o "$result" >/dev/null 2>&1; then
    exit 0
fi

echo "beads merge driver: 'bd export' failed; keeping our version of $result" >&2
exit 0
