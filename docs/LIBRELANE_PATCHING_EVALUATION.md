# Editing the shared LibreLane install — evaluation

**Status:** ANALYSIS, 2026-09-26. No decision taken. Written for bead `e45j`, whose one remaining
high-leverage fix (a post-RCX design-repair stage) cannot be done without it.

## The question

`e45j` root-caused Sky130 max-slew/max-cap violations to a structural gap: **every** repair and
resizer step LibreLane ships runs *before* routing on GRT-**estimated** parasitics
(`repair_design_postgrt.tcl` calls `estimate_parasitics -global_routing`), and no post-RCX repair step
exists. Measured consequence: slew/cap are 0 at flow steps 33/40/41 and 8623/346 at step 51, the first
point real extracted parasitics are seen and the last point at which nothing can act on them.

Closing that properly means adding a step to LibreLane itself, at
`~/Downloads/Github/librelane` — an install **outside this repository** that every ASAP7, Sky130 and
FreePDK45 flow here invokes via `LIBRELANE_DIR` (`pnr/Makefile:78`).

I previously called this out of scope. **That framing was wrong**, and the correction matters.

## Finding: the install is already extensively patched

Measured 2026-09-26 at `~/Downloads/Github/librelane`, tag `2.4.13-2-g3562a8d`:

- **15 tracked files modified, +641 / −89 lines**, all uncommitted working-tree changes.
- `librelane/steps/openroad.py` alone carries **+195 lines** — the very file where repair/resizer steps
  are defined, i.e. exactly where a post-RCX step would go. The project already extends it.
- Modified: `flake.nix`, `odbpy/diodes.py`, `openroad/common/io.tcl`, `common/set_rc.tcl`, `drt.tcl`,
  `ioplacer.tcl`, `pdn.tcl`, `repair_design_postgrt.tcl`, `rsz_timing_postcts.tcl`,
  `rsz_timing_postgrt.tcl`, `sta/corner.tcl`, `pyosys/synthesize.py`, `steps/odb.py`,
  `steps/openroad.py`, `steps/pyosys.py`. Plus untracked `json_header_patched.py`, `nix/openvaf.nix`.
- **7 diffs archived** in `memory/pd/patches/` — the established convention is patch-then-archive.
  ⚠️ **But `memory/` is gitignored** (`.gitignore:78`), so none of those diffs had ever reached the git
  remote. The archive lived on one machine's disk only. Now duplicated to the tracked
  `pnr/librelane_patches/` — see `pnr/librelane_patches/LIBRELANE_LIVE_STATE_MANIFEST.md`.

So patching LibreLane is **existing, routine practice in this project**, not a novel escalation. The
real question is not *whether* it is allowed but *how badly it has gone before*.

## The cautionary case: `drt.tcl`

It has gone badly before, and expensively.

`librelane/scripts/openroad/drt.tcl` is patched with `catch {...}` around `detailed_route`, emitting
`WARNING: detailed_route reported errors; continuing (DRT may be incomplete)`. That is the patch
CLAUDE.md holds responsible for bead `xy6`: **every "0 DRC / 0 antenna" claim across the ASAP7
campaign was vacuous**, because the flow swallowed routing failure and carried on reporting clean.
Run 14's and run 23's routing-clean claims were withdrawn wholesale as a result.

The lesson is specific, not general: the damage came from a patch that **suppressed a failure signal**.
A patch that *adds* a repair stage does not have that shape — it can make results worse or waste
runtime, but it cannot make a broken result look clean. Patches should be classified by whether they
can corrupt a measurement, and `drt.tcl`-class patches should be held to a much higher bar than
additive ones.

## Pros of patching for a post-RCX repair stage

1. **It is the only route to the actual root cause.** The two alternatives are both dead ends:
   editing config margins (done — `e45j` got slew 8623 → 2380, but it is over-repair before routing,
   not repair after it, and cannot reach zero); and `Odb.InsertECOBuffers`, which does a genuine
   route → insert → re-route but targets pins **by name**, and the offenders are synthesis-generated
   (`_49205_/D`, `net805`, `_12721_`) so any committed list is stale after the next re-synthesis.
2. **Precedent and tooling already exist.** 15 files already modified, `openroad.py` already extended
   by ~195 lines, and a patch-archiving convention already in place.
3. **It would also help hold.** `00ef` found the identical gap — hold violations appeared only
   post-RCX for the same reason. One stage addresses both beads.
4. **Additive, not suppressive.** It adds a step; it does not silence a check. Worst case is wasted
   runtime or a worse PPA number, both visible.
5. **Upstream value.** "No post-route repair stage" is a genuine gap in LibreLane's Classic flow, not
   a local quirk. A clean implementation is plausibly upstreamable, which converts a local liability
   into a maintained feature.

## Cons and real risks

1. **The install is uncommitted and drifting.** 15 files modified in the working tree against 7
   archived diffs. Archive coverage is therefore incomplete or stale, and nothing verifies the live
   install matches the archive. **Every PD number this project has produced depends on an install
   state that is not reproducibly captured.** This is the single largest risk and it exists *today*,
   independent of any new patch.
2. **Blast radius across nodes.** ASAP7, Sky130 and FreePDK45 all share this install. A post-RCX
   stage inserted in the Classic flow would perturb ASAP7 runs — including the ones already shelved
   mid-investigation (`lxv`, `ma7`) whose DRC baselines would silently move under them.
3. **Run cost.** Each Sky130 SoC validation is ~2 h; ASAP7 re-baselining is longer. A flow-level
   change needs revalidation per node, not one run.
4. **Post-route repair is genuinely harder than pre-route.** Inserted buffers need placement *and*
   routing. LibreLane's own answer (`hold_eco_demo`) is insert-then-**re-route**, so a correct stage
   is really repair → legalize → re-route → re-extract → re-STA, i.e. an iteration loop, not one step.
   Getting it wrong risks an unconverged loop or a worse result than not repairing.
5. **Maintenance.** Local patches must be re-applied across LibreLane upgrades. Seven already are
   carried; an eighth in a more invasive location raises the cost of ever moving off 2.4.13.
6. **It reverses no decision, but it does change a signed-off flow.** The Sky130 Stage-2 result would
   no longer be reproducible on the pre-patch install.

## Recommendation

**Do not add the post-RCX stage now. Fix the reproducibility gap first** — that is higher value than
the stage itself and is a precondition for doing the stage safely.

Concretely, in order:

1. ~~**Capture the live install state.**~~ **DONE 2026-09-26** — `pnr/librelane_patches/`:
   full 1215-line combined diff of all 15 modified files, verified by `git apply --check --reverse`
   to reproduce the live tree exactly; the 2 untracked source files a diff cannot carry; base commit
   `3562a8d` / tag `2.4.13-2-g3562a8d`; sha256 for each artifact. Doing this surfaced that the
   pre-existing archive was gitignored and had never been pushed.
2. **Re-examine the `drt.tcl` patch specifically.** It is the one patch proven to have corrupted
   measurements. Now that Sky130 routing genuinely converges (DRC 0, iter 5), check whether the
   catch-and-continue is still needed at all, or can at minimum be made to fail loudly.
3. **Only then** consider the post-RCX stage, scoped to Sky130 first via a flow subclass rather than
   editing the Classic flow in place, so ASAP7 baselines cannot move underneath the shelved beads.

On `e45j` itself: the config-margin route already delivered the large win (slew −72 %, cap −80 %),
and neither checker gates the flow. The remaining 2380/77 is **quality, not blockage**. That makes the
post-RCX stage worth doing properly and slowly, not urgently.
