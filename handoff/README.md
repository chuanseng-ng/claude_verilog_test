# Handoff: documentation work that is not finished

This folder is on a handoff branch only. Do not merge it. Delete it before you open a pull request from this branch.

Paths in these files that start with `<scratchpad>` named a scratch folder of the first machine. Only the files copied here exist. `<repo>` is the repository root.

## State of this branch (`docs/bus-chapters-a`)

**Draft, not reviewed, not built.** A worker was stopped while it wrote PR-A of the bus-fabric chapters (memory map, fabric topology, `axi4_crossbar`, master contract, the GPU software rule in the power chapter). Its last note to itself: fix the "must" words in the Technical Manual chapter, and check `bus.yaml` and the User Manual text.

Before this draft can become a pull request:

1. Finish the work order `bus/work_order.md` for PR-A (read "Owner decisions (final)" at its end first; it overrides earlier option text).
2. Run every proof of its section 11, and the archive proofs (`bus/do_archive.py`, `bus/proof_archive.py`, `bus/proof_removed.py`, `bus/manifest.json` are the worker's scripts; they hold paths of the first machine).
3. Get an independent line-by-line truth review against the RTL. Every first draft so far had 30 to 40 real errors; see the reviews in this folder for the kinds.
4. Merge `main`, then regenerate `docs/manual/common/labels.tsv` (`python tools/docs/check_doc_labels.py --write-labels`). Another pull request changes the PMU RTL; the one new rule this draft adds to `ds/parts/chapters/power.tex` must take a free number after that merge.

## Work that is planned and not started

| Work | Plan |
| :-- | :-- |
| Bus fabric PR-B (converters, APB side, register banks, `boot_rom`) | `bus/work_order.md` section 11 |
| STE-style rewrite, PRs S02 to S15 | `ste/work_order.md`, with "Owner decisions (final)" and "Lessons of the pilot S01" at its end. S01 is the pilot; `ste/s01_meaning_review.md` shows what a meaning review finds. |
| Comment-only PR for stale RTL headers of the bus fabric | `bus/work_order.md`, section 9 |
| Authored chapters for the other design areas (CPU core and caches, GPU, peripherals, NPU, crypto, DFT, PLL) | Not planned yet. Use `bus/work_order.md` as the template. |
| Power chapters after the PMU RTL change | Timing figures, DS-PMU-100, the known limits that cite `expect_fail` tests |
| Test counts on the Technical Manual suite pages; shard weights and the CI pass floor | Not started |

## Rules that the reviews taught

- Write from the code, never from old text or from a comment that the code contradicts.
- A `test:` reference only when the test fails if that rule alone is broken. An `expect_fail` test is never a proof of a rule.
- Derive each timing figure cycle by cycle, and label it derived or measured.
- Documentation pull requests run one at a time: each regenerates `labels.tsv`.
- An STE pull request changes wording only. Meaning errors appear where a sentence is split or two items are joined; the facts check does not see them, so each STE pull request needs a meaning review.
