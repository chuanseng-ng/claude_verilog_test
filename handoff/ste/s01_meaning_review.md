# S01 meaning review (independent)

Reviewer scope: the uncommitted working-tree diff of `docs/manual/um/parts/01-chapters.tex` on branch
`docs/ste-s01-um-getting-started`, compared with `HEAD`, for the S01 labels in work order section 6.
I read every changed hunk (the whole diff, 587 lines) and the whole after-text of each S01 section.
I compared each paragraph against its before text. I also read the unchanged prose in scope.
I did not edit any repository file and I did not run any gate or build.

```
VERDICT: CHANGES REQUIRED (5 small blocking items; all have paste-ready replacements)
COUNTS: MEANING 1, WRONG-REFERENT 3, STRENGTH 1, FACT-LOST 0, FACT-ADDED 0, FROZEN 1 (tooling), TERM 2, STYLE 6
```

Blocking (work order section 5: MEANING, STRENGTH, FACT and STRUCTURE block; I count WRONG-REFERENT as MEANING): findings 1 to 5.
Advice: findings 6 to 14.

---

## Findings

### 1. [WRONG-REFERENT] `um:guide:key-documentation` (after line 6789-6790) - BLOCKING
- Before: `\textbf{Always refer to these specifications} (do not rely on non-existent RTL):`
- After: `\textbf{Always refer to these specifications.}` / `Do not rely on RTL that does not exist:`
- Problem: The colon now ends the sentence "Do not rely on RTL that does not exist". The three tables that follow now read as a list of
  RTL that does not exist. Before, the colon belonged to "these specifications" and introduced the tables.
- Replacement (keeps both modals "Always" and "do not", keeps sentence order):
  ```
  \textbf{Always refer to the specifications below.}
  Do not rely on RTL that does not exist.
  ```

### 2. [WRONG-REFERENT] `um:guide:quick-start:nix-dev-shell-simulation-lint` (after line 115-117) - BLOCKING
- Before: `A pinned nix flake at the repo root provides the deterministic EDA toolchain for simulation and lint --- \textbf{Verilator 5.048}, iverilog, gcc, make --- so local and CI toolchains match.`
- After: `A pinned nix flake ... gives the deterministic EDA toolchain for simulation and lint.` / `The toolchain has \textbf{Verilator 5.048}, iverilog, gcc and make.` / `For this reason, the local toolchain and the CI toolchain match.`
- Problem: "For this reason" now points at the sentence just before it, the list of tools. The cause in the before text is the pinned flake
  that gives the toolchain, not the list of tools. The phrase "For this reason" is also new (the before text has "so").
- Replacement:
  ```
  A pinned nix flake at the root of the repository gives the deterministic EDA toolchain for simulation and lint.
  The toolchain has \textbf{Verilator 5.048}, iverilog, gcc and make.
  Because the flake gives this toolchain, the local toolchain and the CI toolchain match.
  ```

### 3. [MEANING-CHANGED] `um:guide:quick-start:soc-cocotb-regression-tbcocotbsoc` (after line 222-223) - BLOCKING
- Before: `(top level, ordered source list, \code{COMPILE_ARGS}, \code{EXTRA_ARGS} incl. every \code{-G}/\code{-D}/\code{-I}, \code{BUILD_ARGS}, ...)`
- After: `The key covers these items: the top level, the ordered source list, \code{COMPILE_ARGS} and \code{EXTRA_ARGS} with every \code{-G}/\code{-D}/\code{-I}.`
- Problem: Before, "incl. every -G/-D/-I" qualifies only `EXTRA_ARGS`. After the join with "and", "with every -G/-D/-I" can qualify
  both `COMPILE_ARGS` and `EXTRA_ARGS`. The scope of the qualifier is wider. The facts check cannot see this.
- Replacement:
  ```
  The key covers these items: the top level, the ordered source list, \code{COMPILE_ARGS}, and
  \code{EXTRA_ARGS} with every \code{-G}/\code{-D}/\code{-I} in it.
  ```

### 4. [WRONG-REFERENT] `um:guide:frequently-used-commands` (after line 6963-6965) - BLOCKING
- Before: `The analog flow state lives in \texttt{analog/pll_clkgen/\{,sky130\}/design_state.json} --- \textbf{separate from the digital \src{design_state.json}} at repo root.`
- After: `The state of the analog flow is in \texttt{...\{,sky130\}/design_state.json}.` / `This file is \textbf{separate from the digital \src{design_state.json}} at the root of the repository.`
- Problem: The brace pattern `{,sky130}` names two files (`analog/pll_clkgen/design_state.json` and
  `analog/pll_clkgen/sky130/design_state.json`). "This file" says one file.
- Replacement:
  ```
  These files are \textbf{separate from the digital \src{design_state.json}} at the root of the repository.
  ```

### 5. [STRENGTH-CHANGED] `um:guide:quick-start:dft-cdc-and-fpga-targets-added-2026-10-15` (after line 317) - BLOCKING
- Before: `Targets verified against the Makefiles (\code{.PHONY} lists in \src{tb/cocotb/soc/Makefile} and \src{pnr/Makefile}).`
- After: `The targets were checked against the Makefiles (\code{.PHONY} lists in ...).`
- Problem: "Verified" states the result of the comparison (the targets agree with the Makefiles). "Checked" states only that a
  comparison was done, not its result. The claim is weaker. The worker kept "verified" in the Phase 1 instruction sentence, so
  the pass is also not consistent. (I confirmed the claim: every target in that listing is in the two Makefiles.)
- Replacement (W1-clean and keeps the strength):
  ```
  A check against the Makefiles (\code{.PHONY} lists in
  \src{tb/cocotb/soc/Makefile} and \src{pnr/Makefile}) confirmed these targets.
  ```
  If the owner allows "verified" as a status word (see the method section below), keep the before verb: `The targets were verified against the Makefiles (...)`.

### 6. [TERM] `um:guide:quick-start:soc-cocotb-regression-tbcocotbsoc` (after line 221) - advice
- Before: `a sha256 of everything that determines the compiled model`
- After: `a sha256 of everything that defines the compiled model`
- Problem: "Determines" means "has an effect on the result". "Defines" can be read as "is the specification of". The difference is small, but
  the sentence describes hash inputs, so "has an effect on" is the exact meaning.
- Replacement: `where \code{<key>} is a sha256 of everything that has an effect on the compiled model.`

### 7. [TERM] `um:guide:quick-start:soc-cocotb-regression-tbcocotbsoc` (after line 229) - advice
- Before: `Source \emph{content} is not hashed;`
- After: `The key does not hash the \emph{content} of the source files.`
- Problem: Rule V1 says keep the passive when the text does not name the agent. The key is the hash. It is not the agent that hashes.
  The meaning is the same, but the subject is not.
- Replacement: `The \emph{content} of the source files is not hashed.`

### 8. [STYLE] `um:guide:supported-instructions:phase-2-white-check-mark-verification-complete-rv32i-zicsr` (after line 401) - advice
- Before: `All Phase 1 instructions PLUS:`
- After: `This phase has all Phase 1 instructions, plus these:`
- Problem: A phase does not "have" instructions. The CPU supports them (the chapter intro says "the instructions that the CPU supports").
  "plus these" is stilted. The list that follows has instructions, CSR registers and interrupt support, so "items" is correct and "instructions" is not.
- Replacement: `The Phase 2 CPU supports all Phase 1 instructions and also these items:`
  (This keeps the number multiset: "Phase 2" is already in the title, and the check counts per section. Run check_facts.py. If `num 2` moves, use
  `This CPU supports all Phase 1 instructions and also these items:`.)

### 9. [STYLE] `um:guide:quick-start:tool-input-rtl-filelists-rtlfilelist` (after line 309-311) - advice
- Before: `The lists are generated from the Makefile source lists (\texttt{python3 tools/verif/gen_filelist.py})`
- After: `The script \texttt{python3 tools/verif/gen_filelist.py} generates the lists from the Makefile source lists.`
- Problem: The `\texttt` argument is a command line, not a script name ("The script python3 ...").
- Replacement: `The command \texttt{python3\ tools/\allowbreak{}verif/\allowbreak{}gen\_\allowbreak{}filelist.\allowbreak{}py} generates the lists from the Makefile source lists.`

### 10. [STYLE] `um:guide:local-qa:automatically-pre-commit-hooks` (after line 2337) - advice
- Before: `Fast validation`
- After: `The validation is fast`
- Problem: The other items of the list start with a verb ("Runs smoke tests", "Enforces coding standards"). This item is now a full sentence without a full stop.
- Replacement: `Gives a fast validation`

### 11. [STYLE] `um:guide:local-qa:pre-commit-is-slow` (after line 2544) - advice
- Before: `If still slow, skip heavy checks during commit:`
- After: `If the checks are still slow, skip the heavy checks when you commit:`
- Problem: The implicit subject of the before text is pre-commit (section title "Pre-commit is slow"). "The checks" is close but less precise.
- Replacement: `If pre-commit is still slow, skip the heavy checks when you commit:`

### 12. [STYLE] `um:guide:local-qa` (whole section) - advice: rewrite incomplete
- Prose that was not rewritten and still breaks the style:
  `First run downloads and caches tools. Subsequent runs are fast.` (no articles, "Subsequent");
  `When you create a PR to main, GitHub Actions runs:` followed by `Generates coverage reports` and `Uploads coverage to Codecov` (the
  verbs do not agree with "runs:"); `Install extensions:`; `Settings (\code{.vscode/settings.json}):`; `Fix common issues:`;
  `Auto-formats code to consistent style`; `No manual formatting needed`.
  In `um:guide:frequently-used-commands:project-structure`, `Top level: ...` is still a fragment.
  The work order rule "one sentence per line" is not applied at after lines 6936-6937 and 7028-7034.
- Replacements (optional; check_facts must stay equal):
  - `The first run downloads and caches the tools. The runs after the first run are fast.`
  - `When you create a PR to main, GitHub Actions does these tasks:`
  - `Install these extensions:`
  - `Use these settings (\code{.vscode/settings.json}):`
  - `To fix common issues, do these steps:`

### 13. [STYLE] `um:guide:quick-start:rtl-linting-formatting` (after line 259-260) - advice
- Before: `Two complementary tools, both run from \src{sim/}:`
- After: `There are two complementary tools.` / `Both run from \src{sim/}:`
- Problem: "There are" plus a split gives two weak sentences. Both items of the list are lint tools.
- Replacement: `Two complementary tools lint the RTL. Both run from \src{sim/}:`

### 14. [FROZEN-CHANGED, tooling] all six `% Rewritten in STE style from docs/...md` comments - advice, fix before S02
- Before: `\begin{relocated}{docs/readme/README.md}` plus `% Converted from docs/readme/README.md by tools/docs/md2tex.py; ...`
- After: `% Rewritten in STE style from docs/readme/README.md; the verbatim original is in git history.`
- Problem: `tools/docs/repoint.py` protects provenance in two ways. One is the `relocated` argument (`TEX_PROVENANCE`). The other is
  a comment that matches `TEX_PROVENANCE_COMMENT = ^\s*%\s*(?:Converted|Moved)\b.*\bfrom\b`. The new comment begins with
  "Rewritten", so neither protection applies. The tex region scan treats a comment line as normal text. All six old paths are in `path_map.tsv`
  (`docs/readme/{README,QUICK_START,PROJECT_STRUCTURE,SUPPORTED_INSTRUCTIONS,DEBUG_INTERFACE}.md`,
  `docs/development/LOCAL_QA_SETUP.md`). So a later `repoint.py --apply` changes each comment to
  `% Rewritten in STE style from \cref{um:guide:...}; ...` and the old path is lost. `CLAUDE.md` is not in the map, so the four
  CLAUDE.md comments are safe. No CI job runs `repoint.py` (inferred from a grep of `.github/`, `Makefile`, `tools/docs/`). The risk is a manual run.
  No printed text and no gate depends on the deleted `% Converted from` and `% Moved verbatim from CLAUDE.md` lines. They are
  comments, `check_doc_labels.py` and `check_facts.py` strip comments, and `ste_check.py` only keyed on the environment.
- Replacement: no change to the owner's wording. In a separate small PR, add `Rewritten` to the alternation in `TEX_PROVENANCE_COMMENT` and
  add a test case in `tb/tests/test_docs_repoint.py`. Do this before S02, because S02 to S15 add more such comments.

---

## Verdict on the 9 checks

1. **Meaning preserved.** Mostly yes. Findings 1, 2, 3 and 4 are the exceptions. Procedures: no step order or command-to-step binding
   changed (all listings and textblocks are unchanged, and the prose around them keeps its order). Cause and effect: the colon in "There
   is no format check: the formatter cannot ..." became "because". This is correct, because the colon gave the reason.
2. **Strength preserved.** Yes, except finding 5 ("verified" to "checked"). "Always" and "do not" (key documentation), "\textbf{not}"
   (synthesis shell), "hard gate", "no build needed", "not run in CI", "even when tests fail", "is grandfathered --- no style-only
   mass edits", "(inherent)", "\ge 9.5" to "at least 9.5" are all kept. "You might want to skip" became "you can skip". This is acceptable: both
   are optional, and the code comment "use sparingly!" keeps the caution. "Install once" to "Install it one time" and "compile once" to
   "compile one time" are correct ("once" is a count in both). "Has been completed" to "is complete" keeps the result.
   "complete" ("This complete guide") is kept as before.
3. **Nothing added, nothing lost.** No fact is lost. Added framing words: "For this reason" (finding 2, wrong), "For example" (the 15
   tb_soc_top suites). I accept "For example" because the colon introduced an instance of the rule, not the whole set. "The key covers
   these items" and "The key also covers" keep the list exhaustive. "This keeps the README easy to scan" turns a purpose into an effect.
   I accept it. "The flow needs ..." and "CI does not run it" supply a subject for a verbless fragment. The subject is correct (the dqc flow).
   Parenthetical remarks are kept ("(the rules did not run)", "(no build needed)", "(whole tree clean)", "(OOM on a 15 GiB host
   otherwise)", "(inherent)", "(instruction fields)").
4. **Splits and joins.** Findings 1, 2, 3 and 4. "It also needs \code{SIM_BUILD} routed to \code{/nobackup}" turns the "with ..." clause into a
   second need. That is the plain reading of the before text, so I accept it. "Enter it with" (analog devshell), "Enter the shell" and
   "Install it" resolve correctly.
5. **Terminology.** "provides" to "gives" (4 places): accepted by work order W1 and the meaning is the same. "lives in" to "is in" / "are in": same meaning.
   "via" to "through": same meaning. "env" to "environment": same meaning (not an identifier). "determines" to "defines" is a small shift (finding 6).
   "verified" to "checked" is a strength change (finding 5). No dictionary term was replaced. No term was added to the dictionary.
6. **Frozen things.** Unchanged: no `\chapter`/`\section`/`\subsection` line, no label, no table row, no `lstlisting`/`textblock`/`logblock`
   line, no list item count or enumerate counter (`\setcounter{enumi}{6}` kept). The authored `information` box in `um:ch:project-structure` is
   unchanged. Every hunk is inside an S01 section. `labels.tsv`: each of the 574 changed rows is one label of `um/parts/01-chapters.tex` that
   appears once removed and once added with 4 fields, so only line numbers moved.
7. **Wrapper removal.** 10 `\begin{relocated}` lines and 10 `\end{relocated}` lines removed. 10 comments added, one at the place of each begin line, with
   the owner's exact wording (6 document paths and 4 times `CLAUDE.md`). The 6 `% Converted from` lines and the 4 `% Moved verbatim from CLAUDE.md` lines are deleted.
   No printed text or check depended on them (see finding 14 for the one tool that reads them). **What the PDF shows now:** the grey rule
   with "Moved from docs/readme/QUICK_START.md" (and the other paths) and "End of moved text" is gone for these 10 blocks. The pages
   show the chapter framing sentence, then the old section title, then the rewritten text. Nothing on the page says that the text came from
   an old document or where the original is. The only trace is the old `.md` path where the body text cites it (for example
   `docs/verification/PROPRIETARY_SIM_FLOW.md (\cref{...})`), and it cites other documents, not the source of the page. The comment
   says "git history" without a commit. To find the verbatim text, a reader must know to look before the S01 merge commit (base `23e35004`).
8. **Style quality.** See the lists below. The descriptive paragraphs are clearer: short, present tense, one fact per line, "the X of the
   Y" used well. The quick start has no prose procedure to convert. So the pilot does not yet show the `procedure` style of
   `um/parts/02-integration.tex`. The rewrite is not complete in `um:guide:local-qa` (finding 12). The worker's own counts in
   `ste_after_all.tsv` seem to be from an earlier draft: line numbers are off by 1 to 2, and a W1 "modify" is listed at a line that now says "changed". Re-run the after count on the final text.
   My approximate count of the S01 ranges: before 77 (G1 17, N1 26, P1 1, S2 6, V1 7, V2 1, W1 19), after about 44. That is about 2.1 per
   prose KB, inside the 2 to 3 target.
9. **Owner list.** See below.

## Five worst after-sentences

1. `Do not rely on RTL that does not exist:` (before: `(do not rely on non-existent RTL):`). The colon binds the tables to the wrong sentence (finding 1).
2. `This phase has all Phase 1 instructions, plus these:` (before: `All Phase 1 instructions PLUS:`). It is stilted, and a phase does not "have" instructions (finding 8).
3. `For this reason, the local toolchain and the CI toolchain match.` (before: `... --- Verilator 5.048, iverilog, gcc, make --- so local and CI toolchains match.`). The referent is wrong (finding 2).
4. `The key covers these items: the top level, the ordered source list, \code{COMPILE_ARGS} and \code{EXTRA_ARGS} with every \code{-G}/\code{-D}/\code{-I}.` (before: `(top level, ordered source list, COMPILE_ARGS, EXTRA_ARGS incl. every -G/-D/-I, ...)`). The qualifier scope is wider (finding 3).
5. `The validation is fast` (before: `Fast validation`). The list item does not match the other items (finding 10). The runner-up is `The script \texttt{python3 tools/...}` (finding 9).

## Five best after-sentences

1. `With cocotb 1.x, \code{make} exits 0 even when tests fail.` / `Judge the result from \code{results.xml}; the driver does this.` (before: `cocotb 1.x \code{make} exits 0 even when tests fail: judge from \code{results.xml} (the driver does).`)
2. `Exit 0 means PASS.` / `Exit 1 means unwaived Fatal/Error.` / `Exit 2 means INCOMPLETE (the rules did not run).` (before: `Exit 0 = PASS, 1 = unwaived Fatal/Error, 2 = INCOMPLETE (rules did not run).`)
3. `This shell does \textbf{not} cover Synthesis / PnR.` / `Synthesis / PnR uses the nix environment of the external librelane, through \src{pnr/Makefile}.` (before: `Synthesis / PnR is \textbf{not} covered by this shell; it uses the external librelane nix env via \src{pnr/Makefile}.`)
4. `If two suites that you expect to share a directory do not share one, \code{print-sim-build} with \code{SIM_KEY_VERBOSE=1} shows the exact material.` (before: `If two suites you expect to share do not, ...`)
5. `There is no format check, because the formatter cannot reproduce the hand-aligned house style (bead \bead{hn9l}).` / `So review enforces the formatting.` (before: `There is no format check: the formatter cannot reproduce ... (bead hn9l), so formatting is enforced by review.`)

**Comparison with `um/parts/02-integration.tex`:** The sentence-level style matches. It uses short declaratives, the present tense, "the X of the Y", and limits
as plain sentences. The rewrite does not yet use `procedure` environments, because there is no prose procedure in scope. It still has
untouched fragments in the local QA guide, which the accepted chapter does not have.

---

## Owner list

The worker's list of 8 items was not in the material I could read (`scratchpad/ste/s01/` has no PR description, and
`sensitive_sentences.md` has no owner list). So I could not verify the worker's 8 items one by one. The list below is my own, from the
repository. Compare it with the worker's 8 items and merge them.

| # | Label | Quoted sentence | Why | Evidence | Proposed action |
|---|---|---|---|---|---|
| O1 | `um:guide:key-documentation` (3 tables) | `\src{docs/design/PHASE0_ARCHITECTURE_SPEC.md} (\cref{ds:ch:phase0-architecture})` and about 20 other `docs/*.md` cells | Stale: these files do not exist. `docs/` holds only `README.md` and `manual/` (measured, `ls docs`). Accepted by `check_doc_labels.py` through `path_map.tsv` (work order 6.1). | `ls docs`; `path_map.tsv` | Separate `[Doc]` PR: drop the old paths, keep the `\cref`. |
| O2 | `um:guide:key-documentation:readme-detail-set` | `\code{docs/readme/} holds the deep content split out of the root README.` | Stale: `docs/readme/` does not exist (measured). | `ls docs/readme` fails | Rewrite to name the UM sections only. |
| O3 | `um:guide:readme-index` | `The detail pages are split out of the root \src{README.md}.` and the table names `QUICK_START.md` and the other pages | Stale: the pages are now UM sections, not files. | same as O2 | Same PR as O2. |
| O4 | `um:guide:readme-index` (table cell) | `Per-phase completion records (Phase 0--4) and implemented-feature lists` | Stale: `cr:status:phase-history` now has Phase 5 and Phase 6 subsections. | `cr/parts/01-phase-and-status-history.tex` | Change "Phase 0--4" after owner check. |
| O5 | `um:guide:supported-instructions:phase-1-...` | `All 37 RV32I base integer instructions are verified and pass:` | Internal contradiction: the list that follows has 40 mnemonics (5+6+6+4+6+2+8+3). The 37 is probably the RV32I count without FENCE/ECALL/EBREAK. | the list itself | Owner decides 37 or 40, or the wording. |
| O6 | `um:guide:frequently-used-commands` | `Use \code{rtk}-prefixed commands for token-efficient output (see RTK section).` | Dangling: no RTK section exists in the books. The text is an agent instruction copied from `CLAUDE.md` into a user manual. | grep of `docs/manual/um` | Remove the pointer or point to `CLAUDE.md`. |
| O7 | `um:guide:commit-and-coding-rules:questions` | `Refer to specifications in \src{docs/} --- they are the source of truth.` | Imprecise: the specifications are the books in `docs/manual/` (AGENTS.md section 1). | AGENTS.md | Change to `docs/manual/`. |
| O8 | `um:guide:quick-start:soc-cocotb-regression-tbcocotbsoc` | `For example, the 15 full-SoC \code{tb_soc_top} suites compile one time, not 15 times.` | Unconfirmed count (inferred risk only). `tb/cocotb/soc/Makefile` has 26 recipe lines with `TOPLEVEL=tb_soc_top`. That is not the same measure, so I could not confirm 15. | `grep -c "TOPLEVEL=tb_soc_top " tb/cocotb/soc/Makefile` = 26 | Owner or verification agent recounts. |
| O9 | `um:guide:key-documentation:physical-design` (table cell) | `Sky130 CPU macro: OpenROAD vs DC->ICC2 vs Genus->Innovus, one StarRC->PrimeTime judge; ...` | Standing caveat is absent next to it: "commercial flows are indicative; no arm meets sign-off" (AGENTS.md section 2). Pointer cell only, no figure quoted. | AGENTS.md section 2 | Optional: add "indicative" in a fix PR. |
| O10 | `um:guide:local-qa:tests-failing-locally-but-pass-in-ci` (code comment) | `# Should be 3.11 or 3.12` | Possible conflict: the `flake.nix` header says `sim/Makefile` is tuned for system Python 3.10. CI QA uses 3.11 and 3.12 (measured, `qa-checks.yml`), so the line is true for the Python QA tools. | `flake.nix` lines 9-14; `qa-checks.yml` line 19 | Low. Clarify the scope in a fix PR if the owner wants. |
| O11 | `um:guide:frequently-used-commands` | `Enter it with \texttt{nix develop ~/Downloads/Github/librelane\#analog}` | A path of one host. The `analog` devshell is not in this repository's `flake.nix` (its devShells are default, bench, fpga, dft, docs, hls; measured). It is in the external librelane. The text is correct for that host only. | `flake.nix` | Low. Note the host dependency in a fix PR. |

Claims I checked and found **true** (not owner items): every make target named in the quick start and the frequently used commands. These are in
`sim/Makefile` (test, lint, lint-verible, verible, phase3_all, icache, dcache, cache_integration), `tb/cocotb/soc/Makefile` (soc_all_ci,
print-sim-build, check-shared-build-failure, clean-sim-builds, cdc_sync, cdc_gray_fifo, cdc_reset_sync_scan, jtag_tap, dft_ctrl,
soc_dft_scan, gpio), `pnr/Makefile` (dft-scan-check, dft-scan-check-asap7, all, report_summary), `dqc/Makefile` (lint, cdc, rdc, hal,
selftest) and the root `Makefile` (eda-venv). The scripts `tools/eda/sim_env.{sh,csh}`, `run_cocotb_targets.py`, `regress_specs.py`, `tools/fpga/stage0_synth.sh`
and `tb/tests/test_sim_build_key.py` exist, and so do `.rules.verible_lint` and `tb/models/cache_model.py`. Verilator 5.048 is on the pinned revision (`flake.nix` line 276).
The Verible step is a hard gate (`rtl-checks.yml`, no continue-on-error). `rtl/filelist/` holds exactly soc/cpu/gpu `.f` plus three `*_sim_models.f`.
The QA CI runs Python 3.11 and 3.12 and uploads to Codecov. Pylint `fail-under=9.5` is in both `.pylintrc` and `.pre-commit-config.yaml`.
The `pytest-quick` hook id exists. The three `__init__.py` files exist. The ASAP7 GPU "signoff" in the project-structure logblock already has an
authored `information` box next to it.

---

## Is the method safe to continue? (judgement for the owner)

Yes, with three changes. The rewrite lost no fact, inverted no negation and moved no status mark. The facts check caught what it can,
and the real errors were of the kinds the brief predicted. All four meaning errors happened where a sentence was split
or two items were joined: a colon left on the wrong sentence, "for this reason" or "this file" pointing at the wrong thing, and a qualifier that
spread over a new "and". All of them are easy to see in a sentence-per-line diff. About one meaning error per 5 KB of prose is the
expected rate for S02 to S15. A reviewer pass stays necessary.

Changes to the worker instructions:
1. **Splits:** after each split, read every new sentence that starts with "This", "It", "These", "For this reason", "So" or "For
   example", and every sentence that now ends in a colon. Confirm the referent and what the colon introduces. Do not add "For this reason" or "For example"
   unless the before text has "so", "because" or "e.g." at that place.
2. **Joins with "and":** when a list item had its own qualifier ("incl.", "with", "for", "only"), keep it on that item only (a comma
   before "and", or repeat the noun).
3. **Status verbs:** add "verified", "validated", "checked", "confirmed", "signed off" and "passes" to the strength list of 2.3-5. Do not change
   "verified" to "checked". W1 "verify" applies only to the instruction verb ("verify that X" to "make sure that X" or "do a check of X").
   For a status claim, keep "verified" or use "confirmed".
4. **Completeness:** finish each section. Fragments such as "Install extensions:" and "Fix common issues:" were left in `um:guide:local-qa`. Re-run
   `ste_check.py` on the final file (the worker's after TSV is from an earlier draft).
5. **Tooling, before S02:** extend `TEX_PROVENANCE_COMMENT` in `tools/docs/repoint.py` to protect the new `% Rewritten in STE style from`
   comment (finding 14). Also put the base commit in the PR description, so that "in git history" can be followed.

## What I did not check

- I did not run `check_facts.py`, the negative controls, `ste_check.py`, `check_doc_labels.py`, pytest or `build_books.py`. The
  instructions made this review read-only and forbade heavy commands. The facts-check pass and the build result are the worker's claims.
- I did not see the worker's PR description or its 8-item owner list (not in the material provided).
- I did not check whether the test counts in the unchanged code blocks are current (66, 33, 12, 21, 111, 20, ...). The code is frozen. Only the owner list could
  hold them.
- I did not confirm the "15 full-SoC suites" count (O8) or the debug register map against the RTL.
- I did not check the PDF layout (overfull boxes from the longer lines).
- I did not check the chapters outside S01, apart from confirming that the diff touches only S01 sections.
