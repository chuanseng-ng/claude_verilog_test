#!/usr/bin/env sh
# Git hook wrapper around beads' own hooks  (bead 78ld)
#
# usage: beads_hook_wrapper.sh <hook-name> [git hook args...]
#
# `make setup-beads` copies this file, tools/setup/githooks/* and the two python
# scripts into <git-common-dir>/beads-guard/hooks/ and points core.hooksPath
# there. Installing OUTSIDE the work tree is deliberate: a hooksPath inside the
# tree would vanish (silently -- git ignores a missing hooks dir) whenever a
# branch predating these files was checked out, taking beads' pre-commit export
# with it.
#
# Every hook is delegated unchanged to the primary worktree's .beads/hooks/<name>
# (exactly what core.hooksPath pointed at before), so beads' export, the bead-o4y
# code-review-graph block and anything else in those shims keep running.
#
# post-checkout (branch switch only) and post-merge are additionally GUARDED:
# beads' hook there runs `bd import .beads/issues.jsonl`, which lets an older
# file overwrite newer DB rows (closed beads reopen, post-commit notes vanish).
# We snapshot the DB before, snapshot it again after, and let
# beads_checkout_guard.py re-import the pre-hook row of every regressed bead.
#
# BEADS_CHECKOUT_GUARD=restore (default) | warn | off
#
# The guard never changes the hook's exit status and never blocks a checkout.

hook="$1"
shift

here=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
common=$(git rev-parse --path-format=absolute --git-common-dir 2>/dev/null)
primary=$(dirname -- "$common")
beads_hook="$primary/.beads/hooks/$hook"

run_beads() {
    if [ -x "$beads_hook" ]; then
        "$beads_hook" "$@"
    else
        return 0
    fi
}

guarded=0
case "$hook" in
    post-merge) guarded=1 ;;
    post-checkout) [ "${3:-0}" = 1 ] && guarded=1 ;;
esac
mode="${BEADS_CHECKOUT_GUARD:-restore}"
[ "$mode" = off ] && guarded=0
command -v bd >/dev/null 2>&1 || guarded=0
command -v python3 >/dev/null 2>&1 || guarded=0
[ -n "$common" ] || guarded=0

if [ "$guarded" -eq 0 ]; then
    run_beads "$@"
    exit $?
fi

backups="$common/beads-guard/backups"
mkdir -p "$backups"
stamp="$(date +%Y%m%dT%H%M%S)-$$-$hook"
before="$backups/$stamp-before.jsonl"
after="$backups/$stamp-after.jsonl"

if ! bd export -o "$before" >/dev/null 2>&1; then
    echo "beads checkout guard: could not snapshot the DB; '$hook' runs UNGUARDED" >&2
    rm -f "$before"
    run_beads "$@"
    exit $?
fi

run_beads "$@"
rc=$?

if bd export -o "$after" >/dev/null 2>&1; then
    python3 "$here/beads_checkout_guard.py" --before "$before" --after "$after" \
        --hook "$hook" --mode "$mode" ||
        echo "beads checkout guard: checker crashed; compare by hand against $before" >&2
else
    echo "beads checkout guard: could not re-snapshot the DB; check by hand against $before" >&2
fi
rm -f "$after"

# Keep the 20 newest pre-hook snapshots (about 1 MB each) for manual recovery.
# shellcheck disable=SC2012  # names are ours: no spaces, no newlines
ls -1t "$backups"/*-before.jsonl 2>/dev/null | tail -n +21 | while read -r old; do
    rm -f "$old" "${old%.jsonl}.restore.jsonl"
done

exit "$rc"
