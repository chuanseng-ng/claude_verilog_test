# LibreLane live-install state capture — 2026-09-26

Captured because **no PD figure in this repo was reproducible from a clean checkout**: the shared
install at `~/Downloads/Github/librelane` (`LIBRELANE_DIR`, `pnr/Makefile:78`) carried 15 modified
files as *uncommitted working-tree changes*, against only 7 archived per-topic diffs. Every ASAP7,
Sky130 and FreePDK45 number this project has produced depends on that state.

See `docs/LIBRELANE_PATCHING_EVALUATION.md` for why this was the precondition for any further
patching.

## ⚠️ Why this directory exists instead of `memory/pd/patches/`

The pre-existing convention archived these diffs under `memory/pd/patches/`. **`memory/` is
gitignored** (`.gitignore:78`), so **none of those 7 diffs has ever reached the git remote.** The
archive existed only on one machine's disk. Combined with the install's changes being uncommitted
working-tree edits, the practical situation was that the exact tool state behind every PD number in
this project existed in exactly one place, backed up nowhere, and a disk loss would have taken it.

Everything here is therefore duplicated into `pnr/librelane_patches/`, which **is** tracked. The
`memory/pd/patches/` copies are left in place — harmless, and they keep working for anyone reading the
older beads that reference those paths.

Future LibreLane patches should be archived **here**, not under `memory/`.

## Base

| | |
|---|---|
| Upstream commit | `3562a8d3e66d196ecd60b361662cb9572f2e73c0` |
| `git describe --tags` | `2.4.13-2-g3562a8d` |
| Captured | 2026-09-26 |

## Artifacts

| File | Purpose |
|---|---|
| `librelane_live_state_2026-09-26.diff` | Full combined diff of all 15 tracked modifications |
| `librelane_live_untracked_2026-09-26/` | The 2 untracked **source** files a diff cannot carry |

Checksums:

```
a3afa6aee05e37141bce3f61cd35a64272def8a9d943eeff9099d9de0de82c2e  librelane_live_state_2026-09-26.diff
4b91975a0fccea353e7b74d94f85df20a16a94022e882cb097257ee64a29934a  librelane_live_untracked_2026-09-26/nix/openvaf.nix
e68b49a28ae89eba4f43504ca824fbb9330fe9fae7befa8691e54075283e1d0f  librelane_live_untracked_2026-09-26/librelane/scripts/pyosys/json_header_patched.py
```

**Verified**: `git apply --check --reverse` succeeds against the live tree, so the diff reproduces
that tree exactly — not an approximation.

Untracked run artifacts (`reports/`, `results/`, `results.xml`) are deliberately **not** captured;
they are outputs, not source.

## Restore onto a clean clone

```bash
git clone https://github.com/librelane/librelane ~/librelane-restore
cd ~/librelane-restore && git checkout 3562a8d3e66d196ecd60b361662cb9572f2e73c0
git apply /path/to/librelane_live_state_2026-09-26.diff
cp -r /path/to/librelane_live_untracked_2026-09-26/* .
```

## What is modified

```
 flake.nix                                          |  20 +++
 librelane/scripts/odbpy/diodes.py                  |  36 ++++
 librelane/scripts/openroad/common/io.tcl           | 107 ++++++++++-
 librelane/scripts/openroad/common/set_rc.tcl       |  26 +++
 librelane/scripts/openroad/drt.tcl                 |  45 ++++-
 librelane/scripts/openroad/ioplacer.tcl            |  11 +-
 librelane/scripts/openroad/pdn.tcl                 |  21 ++-
 .../scripts/openroad/repair_design_postgrt.tcl     |   9 +
 librelane/scripts/openroad/rsz_timing_postcts.tcl  |  29 +++
 librelane/scripts/openroad/rsz_timing_postgrt.tcl  |  33 ++++
 librelane/scripts/openroad/sta/corner.tcl          | 117 ++++++++-----
 librelane/scripts/pyosys/synthesize.py             |  56 +++++-
 librelane/steps/odb.py                             |  20 +++
 librelane/steps/openroad.py                        | 195 +++++++++++++++++++--
 librelane/steps/pyosys.py                          |   5 +-
 15 files changed, 641 insertions(+), 89 deletions(-)
```

## Per-topic archived diffs (pre-existing, retained)

These 7 predate this capture and are **topic-scoped**, so they remain useful for understanding *why*
each change exists. They do **not** collectively equal the live state — that is what the combined
diff above is for.

- `58q_librelane_heuristic_diode_skip_clock_nets.diff`
- `librelane2413_ioplacer_26q2_random_seed.diff`
- `librelane2413_postgrt_annotation_fix.diff`
- `librelane2413_psm_report_parser_26q2_format.diff`
- `librelane2413_repairdesignpostgrt_annotation_gate.diff`
- `librelane2413_resizer_timing_bounds.diff`
- `librelane2413_sta_26q2_scenes.diff`

## Known-hazardous patch in this set

`librelane/scripts/openroad/drt.tcl` wraps `detailed_route` in `catch {}` and emits
*"WARNING: detailed_route reported errors; continuing (DRT may be incomplete)"*. **This is the patch
responsible for bead `xy6`** — every ASAP7 "0 DRC / 0 antenna" claim was vacuous because the flow
swallowed routing failure and continued reporting clean. Those claims were withdrawn wholesale.

Re-examining whether it is still needed is step 2 of the recommendation in
`docs/LIBRELANE_PATCHING_EVALUATION.md`. Sky130 routing now converges genuinely (DRC 0 at iteration
5), so it may be removable, or at minimum made to fail loudly.
