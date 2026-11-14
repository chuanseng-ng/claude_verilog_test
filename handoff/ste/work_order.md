# Work order: STE-style pass on the text that stays (pass 2, scoped)

Status: plan for owner approval. Written by the secondary planner against `claude_verilog_test/main`
at `592c54a4` (the working tree `docs/manual/` and `tools/docs/` are identical to that commit).
All sizes are measured from the files (1 KB = 1000 bytes). Line numbers are as of that commit and
shift after every merged PR. Workers locate sections by **label**, never by line.

Owner decisions this order applies: (1) STE only for text that stays, design areas excluded;
(2) "STE-style", not compliance, no `% ste: done` marker anywhere; (3) review = `check_facts.py`
plus an Opus meaning review of the diff.

---

## 0. Findings that change the shape of the pass (read first)

1. **Almost all in-scope text is inside `relocated` environments.** Pass 1 wrapped every converted
   Markdown document in `\begin{relocated}{docs/X.md} ... \end{relocated}` (74 wrappers in DS/TM/UM:
   64 converted documents and 10 `CLAUDE.md` blocks). The PDF prints "Moved from docs/X.md" and "End of moved text" around
   them. Consequences:
   - `tools/docs/ste_check.py` skips the environment `relocated` (`SKIP_ENVS`), so on the real files it
     reports **nothing** for the text this pass rewrites. Workers must run it on a scratch copy with the
     wrappers removed (procedure in section 3.2).
   - After an STE rewrite the caption "Moved from ..." is false. The owner must decide what happens to the
     wrapper (Q1). This order assumes **Q1 = A** (remove the wrapper of each rewritten document, keep a
     LaTeX comment that names the source). If the owner chooses otherwise, only step 3.3-b changes.
2. **Two kinds of `relocated` text.** (a) Converted documents (`relocated{*.md}`, `relocated{CLAUDE.md}`):
   in scope where they are not design area. (b) Relocated **source comments** (`relocated{rtl/...}`,
   `{tb/...}`, `{pnr/...}`, `{.github/workflows/...}`): 865 KB in DS/TM/UM, **95 % of it inside `textblock`
   verbatim blocks**. These stay verbatim (justified in 1.3 and Q2).
3. **The TM part "Tool defects and standing caveats" is an empty shell** (`tm/parts/06-...tex`, 287 bytes,
   two sentences). `AGENTS.md` section 11 sends readers there for tool defects and caveats, but the text is
   not there. The `AGENTS.md` section 2 caveats live in `AGENTS.md`, in the CR (`cr:defect:*`, `cr:run:*`),
   and in scattered TM sections (`tm:pd:node-strategy`, `tm:pd:commercial-flow-comparison`,
   `tm:pd:sky130-real-drc-lvs`, the HLS evaluation). The words "unvalidated" and "-727.37" occur nowhere in
   the TM. Some TM text **contradicts** the standing caveats (example: section title and first sentence of
   `tm:pd:node-strategy:asap7-phase-23-sign-off-achieved-at-run-43-2026-05-20` say "signed off"; the same
   section later says the figures "do not hold"). The STE pass must not fix this (rule 2.4); it is reported
   to the owner (Q4, and section 8 "Reported discrepancies").
4. **Source files cite numbers and item IDs inside in-scope sections**, not only labels:
   `um:guide:coding-guidelines` "§1.3", "§1.4", "section 1.4", "1.7" (RTL, HLS shims, `flake.nix`,
   `lint/spyglass/waivers.awl`), "section Source comments" (`AGENTS.md`); `um:flow:dqc` "F-2"
   (`dqc/waivers/lint_soc_top.awl`); `um:flow:proprietary-sim` "rule 6" (`tools/verif/check_elab_strict.py`);
   `tm:dec:xezim` "s5"/"section 5" (`.github/workflows/qa-checks.yml`, `check_elab_strict.py`);
   `tm:flow:synth-undef-gate` probe IDs "p13/p19" (`tools/verif/check_synth_undef.py`). `check_facts.py`
   strips leading heading numbers, so it does **not** catch a renumbered heading. Hence rule 2.5 (titles and
   numbering frozen).
5. **`labels.tsv` holds the line number of every label.** Any PR that changes the line count of a part file
   makes `docs/manual/common/labels.tsv` stale; `check_doc_labels.py` (blocking in `qa-checks.yml` and in
   `docs.yml`) then fails. Every STE PR regenerates it, and **all STE PRs conflict on it**. Run the PRs
   one at a time (merge, then rebase the next and regenerate), and never in parallel with an authored-chapter
   PR.
6. **The git remote on this clone is `claude_verilog_test`, not `origin`.** `origin/main` does not exist
   here (`git show origin/main:...` fails). Commands below use `$REMOTE` (see 3.1). The UM guide
   `um:guide:source-archive` says `origin/main`; that is only true on other clones.

---

## 1. Inventory

### 1.1 Classes

- **(a) STAYS** - converted documents that no authored chapter replaces: rewrite in this pass.
- **(b) DESIGN AREA** - out of scope; an authored chapter replaces it later (future area named).
  `b*` = owner question Q3.
- **(c) VERBATIM** - never reworded: `record` (CR), relocated source comments, the CR source archive,
  and, inside (a) sections, every code block (`lstlisting`, `textblock`, `logblock`), data table cell,
  generated file and identifier table.
- **(d) ALREADY STE-STYLE** - authored chapters, `00-about`, chapter/part framing sentences, the UM
  documentation-system chapter, the UM cleanup appendix, the UM integration part, CR framing.

Column meanings: **conv prose** = converted-document prose outside code and tables (the text a worker
rewrites); **conv tab+code** = tables and code blocks inside converted documents (read, but kept; prose
cells of six words or more may be rewritten, rule 2.6); **src-rel** = relocated source comments;
**free** = text outside any wrapper (framing, authored text).

### 1.2 Totals by class and book (KB)

| Book (file total) | (a) STAYS: prose / tab+code / total | (b) DESIGN AREA | (c) VERBATIM | (d) ALREADY STE |
|---|---|---|---|---|
| UM (318.9) | 126.2 / 97.5 / **223.7** | 0 | 23.7 (CI workflow comments) | 71.5 |
| TM (2065.1) | 515.2 / 346.7 / **861.9** | 352.7 (DFT 338.6, CPU decoder analysis 14.3) | 634.2 (relocated source comments) | 216.4 (authored 161.2, framing 55.2) |
| DS (990.9) | 0 | 649.4 converted docs (of which b* 94.4) + 207.3 module contracts (relocated source comments, also c) | (207.3, counted in b) | 134.2 (authored 113.4, framing 20.8) |
| CR (1605.3) | 0 | 0 | 1420.6 (records 1302.7, source archive 117.9) | 184.7 framing (see 1.5) |
| **All** | **641.4 / 444.2 / 1085.6** | **1209.4** | **2078.5** | **606.8** |

The pass rewrites about **641 KB of prose** inside **1086 KB of section text**. If the owner skips the
three measurement reports (Q5 = B), it is **552 KB of prose in 875 KB**.

### 1.3 Why relocated source comments are VERBATIM (class c)

- They are the history and contract of a source file, moved by pass 1 with a byte-exact proof; the caption
  names the source file. `AGENTS.md` section 10: "copy it verbatim first"; the UM guide
  `um:guide:source-archive`: relocated text "goes into the part Source archive of the Changes record,
  unchanged" when an authored chapter replaces it. Rewording it now would break that "unchanged" promise.
- 95 % of the bytes (ds 196.4 of 207.3 KB, tm 592.8 of 634.2 KB, um 22.0 of 23.7 KB) are inside `textblock`
  verbatim blocks that keep the original comment lines. They cannot be reflowed without changing the record.
- Nearly all of them sit in design areas (`ds:ch:mod-*`, `tm:ch:mod-*`) or describe test suites and PD
  files (`tm:suite:*`, `tm:pd:*` notes) whose future home is an authored chapter.
- Tools: `repoint.py` treats the `relocated` argument as provenance; `ste_check.py` skips it; no test or
  `check_pinned_text.py` anchor pins its wording (checked: no consumer in `check_pinned_text.py` points into
  `docs/manual`; the doc tests run on synthetic trees, except `test_real_repository_is_clean` for labels and
  requirements and `test_committed_glossary_is_in_sync`). The decision is therefore policy, not tooling (Q2).

### 1.4 Chapter-level inventory (DS, TM, UM)

Rows under 0.3 KB (shells) are omitted: `tm:part:tool-defects-and-standing-caveats` (0.3, class d, empty -
finding 0.3), `tm:app:project-infrastructure` (0.2, d), `ds:ch:dft-requirements` (0.1, b DFT),
`ds:ch:functional-coverage` (0.1, b*), `tm:ch:asap7-flow`, `tm:ch:freepdk45-flow`,
`tm:ch:proprietary-simulators`, `tm:ch:analog-pll`, `um:ch:issue-tracking`, `um:ch:project-status`
(all framing only, d).

| File | Label | Title | KB | conv prose | conv tab+code | src-rel | free | Class (future area) |
|---|---|---|---|---|---|---|---|---|
| ds/00-about | (none) | About this book | 1.9 | 0 | 0 | 0 | 1.9 | d |
| ds/01-architecture | `ds:ch:system-overview` | System overview | 2.4 | 2.3 | 0 | 0 | 0.2 | b (SoC overview, with bus fabric) |
| ds/01 | `ds:ch:cpu-phases-0-to-3` | CPU phases 0 to 3 | 192.8 | 103.3 | 89.3 | 0 | 0.2 | b (CPU core and caches) |
| ds/01 | `ds:ch:gpu-lite-simt-engine` | GPU-lite SIMT engine | 68.5 | 50.8 | 17.5 | 0 | 0.2 | b (GPU) |
| ds/01 | `ds:ch:soc-integration` | SoC integration | 71.8 | 54.6 | 17.0 | 0 | 0.2 | b (bus fabric) |
| ds/01 | `ds:ch:phase-6-ip-expansion` | Phase 6 IP expansion | 103.2 | 71.3 | 31.8 | 0 | 0.2 | b (peripherals, crypto, NPU) |
| ds/01 | `ds:ch:mixed-signal-pll` | Mixed-signal PLL | 23.1 | 12.3 | 10.6 | 0 | 0.2 | b (PLL) |
| ds/01 | `ds:ch:memory-map` | Memory map | 71.7 | 41.0 | 30.6 | 0 | 0.1 | b (bus fabric) |
| ds/01 | `ds:ch:interface-definitions` | Interface definitions | 16.7 | 12.4 | 4.2 | 0 | 0.1 | b (CPU core, bus fabric) |
| ds/01 | `ds:ch:reference-models` | Reference models | 19.6 | 7.9 | 11.6 | 0 | 0.1 | b* (Q3) |
| ds/01 | `ds:dec:key-design-decisions`, `ds:dec:locked-phase5`, `ds:ch:phase4-5-architecture`, `ds:inv:struct-member-select`, `ds:inv:strict-elaboration` (moved from `CLAUDE.md`) | Locked decisions, invariants | 7.7 | 6.3 | 0 | 0 | 1.4 | b (decisions of each area) |
| ds/02-constraints-and-power-intent | `ds:ch:timing-constraints` | Timing constraints (`SDC_TIMING_SPEC`) | 26.0 | 8.8 | 17.0 | 0 | 0.2 | b* (Q3) |
| ds/03-module-contracts | `ds:ch:mod-cpu-core` ... `ds:ch:mod-fpga-wrappers` (10 chapters) | Module contracts | 222.3 | 0 | 0 | 207.3 | 15.0 | b + c (each area) |
| ds/04-verification-plan | `ds:ch:verification-strategy` (`ds:ch:verification-plan`) | Verification strategy | 48.8 | 29.1 | 19.6 | 0 | 0.2 | b* (Q3) |
| ds/chapters/cdc, power, power-intent | `ds:ch:mod-cdc-primitives`, `ds:ch:mod-power-management`, `ds:ch:power-intent` | Authored chapters | 113.4 | 0 | 0 | 0 | 113.4 | d |
| tm/00-about | (none) | About this book | 1.3 | 0 | 0 | 0 | 1.3 | d |
| tm/01-module-reference | `tm:ch:mod-cpu-core` ... `tm:ch:mod-fpga-wrappers` (10 chapters) | Module reference | 85.8 | 0 | 0 | 74.1 | 11.7 | b + c (each area) |
| tm/02-physical-design | `tm:ch:flow-overview` | Flow overview | 95.0 | 59.6 | 35.3 | 0 | 0.2 | a |
| tm/02 | `tm:ch:constraint-files` | Constraint files | 47.4 | 29.2 | 18.1 | 0 | 0.1 | a |
| tm/02 | `tm:ch:sky130-flow` | Sky130 flow | 45.6 | 36.9 | 8.5 | 0 | 0.1 | a |
| tm/02 | `tm:ch:commercial-flow-comparison` | Commercial flow comparison | 44.3 | 23.4 | 20.7 | 0 | 0.2 | a |
| tm/02 | `tm:pd:node-strategy` (moved from `CLAUDE.md`) | Technology Node Strategy | 10.4 | 7.5 | 2.8 | 0 | 0.1 | a |
| tm/02 | `tm:ch:pd-constraint-notes`, `tm:ch:pd-macro-placement-notes`, `tm:ch:pd-flow-script-notes`, `tm:ch:pd-makefile-notes` | PD file notes | 182.8 | 0 | 0 | 168.1 | 14.7 | c + d framing |
| tm/03-verification-infrastructure | `tm:ch:test-benches-and-suites` | Test benches and suites | 442.3 | 16.2 | 10.2 | 391.6 | 24.3 | c (suites) + a (`tm:suite:phase4-random-kernels`, 12.1) + b (`tm:flow:control-signals-analysis`, 14.3, CPU core) |
| tm/03 | `tm:ch:coverage` | Coverage | 233.8 | 101.2 | 132.4 | 0 | 0.1 | a |
| tm/03 | `tm:ch:cdc-and-lint-checks` | CDC and lint checks | 7.8 | 5.7 | 1.9 | 0 | 0.1 | a |
| tm/03 | `tm:ch:synthesis-undefined-value-gate` | Synthesis undefined-value gate | 24.7 | 17.5 | 7.0 | 0 | 0.2 | a |
| tm/04-dft-fpga-hls-and-analog | `tm:ch:dft-architecture` | DFT architecture (Stage 0 to 4 records) | 338.6 | 239.1 | 99.3 | 0 | 0.2 | b (DFT) |
| tm/04 | `tm:ch:tessent-flows` | Tessent flows | 64.6 | 30.0 | 34.4 | 0 | 0.1 | a |
| tm/04 | `tm:ch:fpga-prototyping` | FPGA prototyping | 103.5 | 67.2 | 36.2 | 0 | 0.2 | a |
| tm/04 | `tm:ch:high-level-synthesis` | High-level synthesis | 94.0 | 79.2 | 14.7 | 0 | 0.1 | a |
| tm/05-decisions | `tm:ch:decision-log` | Decision log | 80.5 | 52.0 | 28.3 | 0 | 0.2 | a |
| tm/chapters/cdc, power | `tm:ch:mod-cdc-primitives`, `tm:ch:mod-power-management` | Authored chapters | 161.2 | 0 | 0 | 0 | 161.2 | d |
| um/00-about | (none) | About this book | 1.1 | 0 | 0 | 0 | 1.1 | d |
| um/01-chapters | `um:ch:getting-started` | Getting started | 1.5 | 0.3 | 1.0 | 0 | 0.1 | a |
| um/01 | `um:ch:project-structure` | Project structure | 4.2 | 0.2 | 3.8 | 0 | 0.1 | a |
| um/01 | `um:ch:build-and-run-commands` | Build and run commands | 11.5 | 6.7 | 4.7 | 0 | 0.1 | a |
| um/01 | `um:ch:supported-instructions` | Supported instructions | 2.2 | 2.0 | 0 | 0 | 0.1 | a |
| um/01 | `um:ch:debug-interface` | Debug interface | 1.8 | 0.4 | 1.3 | 0 | 0.1 | a |
| um/01 | `um:ch:coding-guidelines` | Coding guidelines | 76.7 | 44.5 | 32.0 | 0 | 0.1 | a |
| um/01 | `um:ch:local-quality-checks` | Local quality checks | 10.8 | 6.9 | 3.8 | 0 | 0.1 | a |
| um/01 | `um:ch:continuous-integration` | Continuous integration | 93.0 | 44.0 | 24.1 | 23.6 | 1.4 | a + c (`um:flow:ci-cocotb`, `ci-qa-checks`, `ci-random-tests`, `ci-rtl-checks`, `ci-soc-coverage`) |
| um/01 | `um:ch:tool-flows` | Simulator and lint tool flows | 37.9 | 16.9 | 20.9 | 0 | 0.2 | a |
| um/01 | `um:ch:documentation-system` | Documentation system | 22.1 | 0 | 0 | 0.1 | 22.0 | d |
| um/01 | `um:guide:key-documentation`, `um:guide:frequently-used-commands`, `um:guide:reference-model-and-verification`, `um:guide:commit-and-coding-rules` (moved from `CLAUDE.md`) | Pointer chapters | 10.8 | 4.4 | 5.9 | 0 | 0.6 | a |
| um/02-integration | `um:ch:cdc-integration`, `um:ch:power-integration` | Integration guide | 34.2 | 0 | 0 | 0 | 34.2 | d |
| um/99-appendix | `um:guide:cleanup-recommendations` | Cleanup recommendations | 10.8 | 0 | 0 | 0 | 10.8 | d |

### 1.5 CR framing

The CR is 1605.3 KB; 1302.7 KB is inside 987 `record` environments and 117.9 KB is the source archive
(`cr/parts/06-source-archive.tex`, verbatim by rule). Outside them: about 98 KB of **headings** (original
document titles, part of the history, keep), and about 51 KB of framing sentences, of which **13.9 KB are
unique** (the rest is the repeated boilerplate "This section holds history text that was in a comment of the
source file. The text is unchanged. ..."). `ste_check.py` on the CR files reports findings outside records
only on original headings (for example "AI MAY Assist With", "Run 39 (May 19, 2026)") and on the word
"leading" in the boilerplate. **Recommendation: no STE PR for the CR**; the framing is already STE-style.
The same boilerplate occurs 493 times in CR, DS, TM and UM; it is framing, not in scope.

### 1.6 ALREADY STE: what `ste_check.py` reports on accepted text (for calibration)

| File | Findings | Prose KB | Findings per prose KB |
|---|---|---|---|
| `um/parts/02-integration.tex` | 84 | 29.5 | 2.8 |
| `tm/parts/chapters/cdc.tex` | 116 | 69.2 | 1.7 |
| `tm/parts/chapters/power.tex` | 159 | 65.4 | 2.4 |
| `ds/parts/chapters/power.tex` | 182 | 26.0 | 7.0 (requirement boxes counted separately) |
| `um/parts/99-appendix.tex` | 25 | 10.8 | 2.3 |
| In-scope text today (unwrapped copies, S01 to S18) | 3651 | 641.4 | 5.7 |

So "accepted STE-style" in this project means about **2 to 3 findings per KB of prose**, not zero.

---

## 2. Rewrite rules (the worker applies these)

### 2.1 The STE-style rules, by `ste_check.py` code

| Code | What it flags | How to fix | Do not |
|---|---|---|---|
| S1 | A step (inside `enumerate`/`procedure`) over 20 words | Split into two sentences inside the **same** item. Condition first ("If X, do Y."). | Add, remove or reorder items of a numbered list (numbers are cited). |
| S2 | A descriptive sentence over 25 words | Split into two or more sentences. One fact per sentence. Keep each qualifier ("only", "for the CPU macro", "on Sky130") with the fact it limits. | Drop a clause, or move a number to another sentence where it could bind to a different subject. |
| P1 | A paragraph over 6 sentences | Split into paragraphs at topic changes, or turn a series of parallel facts into an `itemize` list. | Reorder facts. |
| V1 | Passive voice | Make it active **when the text names the agent** ("The gate script reads the file"). | Invent an agent. If the text does not say who, keep the passive. |
| V2 | Compound, progressive or future tense | Present tense for what the design, tool or flow does now. **Past tense for past events, runs and measurements.** For plans, keep the future meaning ("A later stage adds ..." / "Stage 3 is to add ..."). | Turn a past measurement into a present claim ("was measured at 75 MHz" must not become "runs at 75 MHz"). |
| G1 | A verb form ending in -ing | Use "to" plus verb, a noun, or a clause ("when the tool runs"). Technical names in `ste_words.yaml` `allowed_ing` and in the dictionary are allowed. | Change an identifier, a tool option or a quoted message. |
| N1 | A noun cluster of more than 3 words | Break it with "of", "for" or a relative clause ("the write enable of the counter"). | Break an identifier, a product name, a register name, a title of a cited document, or a dictionary term. |
| W1 | A word in `ste_words.yaml` `not_approved` | Use the listed word. Exceptions below. | See exceptions. |
| C1 | A contraction | Write it out. **Note:** "don't" to "do not" and "can't" to "cannot" add a `modal` fact; this is the only allowed modal diff (3.4). | - |
| M1 | Two instructions in one step | Split into two sentences in the same item. | Add a list item. |
| X1 | Step without imperative (only with `--pedantic`) | Do not run `--pedantic`. | - |
| Z1 | A waiver without reason | Do not add `% ste-ok:` waivers at all in this pass. | Add `% ste: done` (owner decision 2). |

W1 exceptions (confirmed in the in-scope text, top hits: verify 150, via 105, require 100, once 71, may 71,
rather 57, therefore 52, should 37, e.g. 37):
- **"should"**: keep it (Q7). It is not in the facts check, and "must" would make it stronger.
- **"may"**: change to "can" only when it means possibility or permission. Never touch the month ("May 19, 2026").
- **"verify"**: change only the English verb. Keep `make verify-tooling`, the `verify` argument of a requirement,
  and every command, target or option name.
- **"etc."**: do not invent the list (that adds facts). Write "and other items" or keep the sentence as is.
- **"once"**: "after" or "when" for time; "one time" for a count. Choose by meaning.
- **"rather", "just", "very", "simply", "quite"**: remove only when the meaning stays. "rather than" becomes
  "instead of"; "just before" keeps its timing meaning.
- **"currently"**: "now" only when the sentence keeps its date or status context; it is a time-scoped claim.
- "e.g." to "for example", "i.e." to "that is", "via" to "through" or "by", "require" to "need",
  "therefore"/"thus"/"hence" to "so", "however" to "but", "ensure" to "make sure", "provide" to "give".

Patterns taken from the accepted authored chapters (`um/parts/02-integration.tex`, `tm/parts/chapters/cdc.tex`):
- Short declarative sentences in the present tense. One fact or one instruction per sentence.
- "The X of the Y" instead of noun stacks ("the clock of the receiving domain").
- Repeat the noun instead of an unclear "it" or "this" ("The script reads ...", "This file ...").
- Limits are stated as plain sentences ("The tool does not model metastability.").
- Procedures in `procedure` or `enumerate`, each step starting with an imperative verb.
- Lists for enumerations; "because" and "so" for reasons.

Line layout: write **one sentence per line** in rewritten paragraphs (the converted text is hard-wrapped at
72 columns). This makes the review diff readable. Do not reflow text outside the PR's sections.

### 2.2 Glossary

- The only source of terms is `docs/manual/common/dictionary.yaml` (78 entries: acronyms, technical names,
  tools, PDKs). `glossary.tex` is generated; never edit it.
- **One word, one meaning.** Use each dictionary term with its dictionary meaning. Do not replace a technical
  word with a synonym ("register" with "flop", "macro" with "block", "sign-off" with "closure") unless the
  dictionary says they are the same. Do not use a dictionary term for a different thing.
- **Add a term** only if it is used at least three times in in-scope text, is not an identifier, and the
  worker needs it to fix G1 or N1 findings (examples seen: "clock-domain crossing", "sign-off", "pin order").
  Add it under `# --- technical names ---` or `# --- technical verbs ---` with `term`, `kind`, a one-sentence
  STE `definition` and `glossary: true|false`. Then run `python tools/docs/gen_glossary.py`, commit both
  files, and list every added term in the PR description. Effect on `ste_check.py`: a multi-word term is no
  longer a noun cluster; a single `technical-name` ending in -ing passes G1.
- Do **not** add `\gls{...}` calls in this pass: they move the first-use expansion of acronyms in other
  chapters of the same book.

### 2.3 What must never change

Every one of these is a hard rule; the facts check covers some, the meaning review the rest.

1. Every number and unit, including numbers written as words ("two flops"), ranges ("100--120 MHz"),
   "about" and "~" values, dates, run names, percentages. Keep digits as digits and words as words.
2. Every identifier, signal, module, file path, command, make target, option, environment variable, URL,
   `\code{}`/`\src{}`/`\texttt{}`/`\bead{}`/`\runid{}`/`\ghref{}`/`\prref{}` argument (byte for byte), tracker
   token (bead IDs, "GH #n", "PR #n"), and run directory.
3. Every `\label`, `\cref`/`\Cref`/`\ref` target, `\reqref`, `\href` target, and every status mark macro
   (`\ok{}`, `\bad{}`, `\warn{}`, `\hold{}`, `\wip{}`, `\partialmark{}`, `\notemark{}`, `\openmark{}`) in
   its place. The facts check does **not** see status marks (verified).
4. Every code block (`lstlisting`, `textblock`, `logblock`) byte for byte, and every table: its structure,
   column specification, header cells and every data cell (names, values, status words).
5. The meaning and the **strength** of each statement: modal words (must, must not, do not, never, always,
   only, cannot, should, may), negations (not, no, none, without, unless, except), hedges and limits
   ("about", "at least", "up to", "lower bound", "indicative", "unvalidated", "unsupported", "does not hold",
   "not signed off", "proposal only", "host-blocked"), and conditions ("if", "when", "only on Sky130").
   A caveat stays a caveat and stays next to the figure it limits. A historical result stays in the past.
6. The standing caveats of `AGENTS.md` section 2 wherever they appear (ASAP7 macro views from Synlig are
   wrong; ASAP7 figures unvalidated; zero-wire STA; withdrawn "0 DRC, 0 antenna"; empty ASAP7 power grid;
   Sky130 timing nom_tt only, "clean at 9 corners" is 9 labels on one model; commercial flows indicative, no
   arm meets sign-off; Sky130 CPU macro re-hardened with sv2v; ASAP7 re-harden needs 32 GB).

### 2.4 Unclear or false sentences

- Do **not** fix facts in an STE PR. Keep the meaning, even when it looks stale or wrong.
- If a sentence is unclear so that two rewrites with different meanings are possible, keep the original
  sentence unchanged.
- List each case in the PR description under "Owner list" (format in 3.6): label, quoted sentence, why
  (stale, contradicts `AGENTS.md` section 2, contradicts the code, unclear), the evidence path, and a proposed
  action. Do not add a note, box or footnote to the book.

### 2.5 Structure

- No splitting or merging of sections, no new sections, no label changes, no reordering of sections or
  paragraphs, no moving text between sections (the facts check is per section).
- **Titles are frozen** in this pass (Q6 default): `\chapter`, `\section`, `\subsection`, `\paragraph`
  titles, their leading numbers ("1.3", "7. Source comments"), list numbering and item IDs ("rule 6",
  "F-2", "s5"). Source files and `AGENTS.md` cite them, and the facts check strips heading numbers. A
  section without a label is keyed by its title in the facts check, so a title change also breaks the check.
- Sentence order inside a paragraph stays; inside one sentence a condition may move to the front.

### 2.6 Tables

Rewrite only table cells that are sentences of six words or more (the cells `ste_check.py` checks). Keep
header cells, name cells, value cells and status cells unchanged. Do not change column widths; if a rewritten
cell makes a row taller than a page the build reports `tallrows` and fails (fix by shortening, not by layout).

---

## 3. Tool procedure per PR

All commands run from the repository root in Git Bash with `PYTHONUTF8=1` (PowerShell: `$env:PYTHONUTF8=1`).
Do not pipe a gate into `tail`/`head` when you need its exit code (the pipe returns the exit code of the last
command). Do not use `diff` or `rtk diff` to decide anything; use `cmp -s` or `sha256sum`.

### 3.1 Set up

```bash
export PYTHONUTF8=1
REMOTE=$(git remote | head -1)          # "claude_verilog_test" on this clone, "origin" elsewhere
git fetch "$REMOTE"
git checkout -b docs/ste-sNN-<slug> "$REMOTE/main"
BASE=$(git rev-parse HEAD)
SCR=<your scratch directory>            # never inside the repository
F=docs/manual/um/parts/01-chapters.tex  # the part file of this PR (one or more)
git show "$BASE:$F" > "$SCR/base.tex"
```

Save this script as `$SCR/ste_unwrap.py`. It writes a copy of a file with the `relocated` wrappers of the
named documents replaced by comment lines (line count kept, so line numbers match).

```python
"""ste_unwrap.py SRC DST DOC [DOC ...]: drop \\begin{relocated}{DOC} and its \\end{relocated}."""
import re, sys
src, dst, docs = sys.argv[1], sys.argv[2], set(sys.argv[3:])
B = chr(92)
beg = re.compile(r"\s*" + re.escape(B + "begin{relocated}{") + r"([^}]*)\}\s*$")
end = re.compile(r"\s*" + re.escape(B + "end{relocated}") + r"\s*$")
out, stack = [], []
for ln in open(src, encoding="utf-8").read().split("\n"):
    m = beg.match(ln)
    if m:
        hit = m.group(1) in docs
        stack.append(hit)
        out.append("% unwrapped " + m.group(1) if hit else ln)
        continue
    if end.match(ln) and stack:
        out.append("%" if stack.pop() else ln)
        continue
    out.append(ln)
open(dst, "w", encoding="utf-8").write("\n".join(out))
```

The wrapper lines are always on their own line (checked: all 74 converted-document wrappers and their
`\end{relocated}` lines). The script was tested on `um/parts/01-chapters.tex`: same line count, and
`check_facts.py` base versus unwrapped copy shows exactly one `DIFF id <doc>` per unwrapped wrapper. Run once for the PR's documents (the `DOC` list for each PR is in section 6):

```bash
python "$SCR/ste_unwrap.py" "$SCR/base.tex" "$SCR/base_unwrapped.tex" docs/readme/QUICK_START.md ...
```

### 3.2 Before counts (`ste_check.py`)

```bash
python tools/docs/ste_check.py --format tsv "$SCR/base_unwrapped.tex" > "$SCR/ste_before.tsv"
awk -F'\t' -v a=FIRST -v b=LAST '$2>=a && $2<=b {print $3}' "$SCR/ste_before.tsv" | sort | uniq -c
```

`FIRST`/`LAST` are the line range of the PR's sections in the base file (find with
`grep -n '\\label{<label>}' $F`). `--format tsv` prints `path, line, rule, message, sentence, marked`; the
summary goes to stderr. Exit code is 0 (no marked regions exist). Known noise, do not chase:
- N1 on lists of names, tool chains and identifiers ("KLayout Magic Netgen", "DC ICC2 Genus Innovus").
- G1 on adjectives and nouns: "leading" (boilerplate, out of scope), "existing", "missing", "remaining",
  "following", "outstanding", "matching", "warning"; and on "crossing" in "clock-domain crossing".
- W1 "may" in dates; "verify" in command names in prose; "once" meaning one time.
- S2 on sentences that are mostly a list of `\cref` targets or `\code` items.
- Findings in table cells that are data (name lists).
- `verify=` arguments of requirements produce no findings (the begin line is skipped); there are no
  requirements in scope.

### 3.3 Commits (one purpose each)

- **a. Wrapper commit** (only if Q1 = A). For each document of the PR, replace the line
  `\begin{relocated}{docs/X.md}` with `% Source: docs/X.md, converted in pass 1 and rewritten in STE style;
  the converted text is at <BASE short hash>.` and delete its `\end{relocated}` line. Keep the
  `% Converted from ...` comment. Nothing else. Commit `[Doc] Remove the moved-text wrappers of <docs>`.
  Proof: `python tools/docs/check_facts.py --before "$SCR/base.tex" --after $F --by-section` prints exactly
  one `DIFF id <doc path> before=1 after=0` per removed wrapper (path without a leading dot for
  `.github/X.md`) and nothing else.
- **b. Rewrite commit.** The rewrite, by the rules of section 2. Commit
  `[Doc] Rewrite <area> in STE style`.
- **c. Generated files commit.** `python tools/docs/check_doc_labels.py --write-labels`, and
  `python tools/docs/gen_glossary.py` if the dictionary changed. Commit `[Doc] Regenerate labels.tsv`
  (and glossary).

### 3.4 Facts check (blocking)

```bash
python tools/docs/check_facts.py --before "$SCR/base_unwrapped.tex" --after $F --by-section
echo "exit=$?"
```

- Compares, **per section** (key = the `\label` right after the heading, else the title; duplicates get
  `#2`), the multiset of: `num` (numbers with an optional unit: ns ps MHz mW um KB bits cycles %, and
  more), `id` (inline code, `\texttt`/`\src`/`\path`/`\bead`/`\lstinline`, URLs, bare tokens with `_`, a
  dotted name or a path shape), `lbl` (`\label`, `\ref`, `\cref`, `\Cref`, `\autoref`, `\pageref`), `ref`
  ("GH #n", "PR #n", `RUN_YYYY-MM-DD_HH-MM-SS`), `modal` (must, must not, do not, never, always, only,
  cannot), `code` (sha256 of each code block, whitespace normalised). LaTeX comments are ignored.
- Exit codes: **0** = `FACTS: equal`; **1** = differences, one line each
  (`DIFF kind token before=n after=m section=key`, `SECTION-ADDED`, `SECTION-REMOVED`); **2** = usage or
  read error. `--before` accepts a file or `REV:PATH` (for example `"$REMOTE/main:$F"`); `--after` must be
  a file.
- Required result: exit 0. The **only** allowed differences, each listed in the PR with its line:
  `modal do not` (+1) for an expanded "don't", `modal cannot` (+1) for an expanded "can't". Anything else is
  a defect of the rewrite: fix the text, do not argue the diff.
- **Blind spots** (confirmed with a crafted before/after pair; the meaning review must cover them):
  numbers written as words ("two" to "three", "Ten" to "Nine" passed); heading numbers ("1.3" to "1.4"
  passed); negations ("is not clean" to "is clean" passed); hedges and caveat words ("unvalidated" to "valid",
  "withdrawn" to "stands" passed); "should" to "must" adds only `modal must`, "may" to "can" is invisible;
  status marks (`\warn{}` removed, passed); `\gls{CDC}` to "CDC" passed; plain-word identifiers without `_`
  or `.` ("pmu" to "power management unit" passed); the binding of facts (two numbers swapped between two
  subjects in the same section pass, because the check counts, it does not place). Units split from the
  number **are** caught ("25 ns" to "25 nanoseconds" gives `num 25 ns` -1 and `num 25` +1); expanded
  contractions **are** caught; removed URLs **are** caught.

### 3.5 Negative control (every worker shows it in the PR)

```bash
cp $F "$SCR/neg.tex"
# change ONE number inside a rewritten section of neg.tex, e.g. 75 MHz -> 76 MHz, with an editor
python tools/docs/check_facts.py --before "$SCR/base_unwrapped.tex" --after "$SCR/neg.tex" --by-section
echo "exit=$?"     # must be 1, with DIFF num 75 MHz before=1 after=0 and DIFF num 76 MHz before=0 after=1
cp $F "$SCR/neg2.tex"
# delete ONE "only" (or "must", "never") in a rewritten section of neg2.tex
python tools/docs/check_facts.py --before "$SCR/base_unwrapped.tex" --after "$SCR/neg2.tex" --by-section
echo "exit=$?"     # must be 1, with DIFF modal only before=n after=n-1
```

Paste both outputs into the PR. Never edit `$F` itself for the control.

### 3.6 Other gates, in this order

```bash
python tools/docs/check_doc_labels.py           # 0 clean, 1 findings, 2 setup. Fails if labels.tsv is stale.
python tools/docs/gen_glossary.py --check       # 0 in sync, 1 stale, 2 bad YAML
python tools/docs/check_requirements.py -v      # 0 clean (no requirements are in scope; run it anyway)
python tools/docs/gen_fact_tables.py --check    # needs pyslang (installed on this host); CI runs it
python tools/docs/check_pinned_text.py --skip-waivers   # qa-checks.yml runs it; no anchor is in the books
python -m pytest tb/tests/test_docs_*.py -q     # the CI form; includes test_real_repository_is_clean
python tools/docs/ste_check.py --format tsv $F > "$SCR/ste_after.tsv"   # after counts, same awk as 3.2
python tools/docs/build_books.py --keep-aux     # once, at the end; about 5 minutes; all four books
```

Build: the result line per book is
`<book>: undefined=0 multiply-defined=0 glossary=0 errors=0 overfull>10pt=N tallrows=0`. The command exits 1
on any undefined reference, duplicate label, missing glossary entry, error or tall row; it does **not** fail
on overfull boxes (no `--strict`; CI does not pass `--strict`). Overfull baseline from the owner: **ds 4,
tm 20, um 2, cr 93** (not re-measured by this planner; no build was allowed). If the count of a book that the
PR edits grows: open `docs/manual/_build/aux/<book>/<book>.log`, find each `Overfull \hbox (...pt too wide)
in paragraph at lines N--M`, and fix those whose lines fall in the PR's rewritten ranges. Fix by rewording so
that a long `\code`/`\src`/URL token does not end the line, or by an `\allowbreak{}` at a safe point between
words. No `\sloppy`, no `\linebreak`, no layout or package changes. If the count drops, record the new number
in the PR. Delete `docs/manual/_build/aux` after reading the log (the directory is gitignored).

CI that runs on the PR: `docs.yml` (static: glossary check, fact tables check, requirements `-v` and
`--base-ref HEAD^1`, labels, `pytest tb/tests/test_docs_*.py`; PDF build because `docs/manual/` changed;
`docs-ok` aggregate) and `qa-checks.yml` (pinned text, labels, comment budget and the RTL/Python gates,
which a docs-only PR does not affect). `cocotb.yml` and `rtl-checks.yml` do not run for a docs-only change.
Do not touch `.beads/` (the bead-reopen gate in `qa-checks.yml` reads it).

### 3.7 PR description (template)

```
## STE pass: <PR name>
Sections: <labels>   Base: <BASE>   Documents unwrapped: <list or "none (Q1=B)">
### Gates
check_facts (base_unwrapped vs after, --by-section): <paste, must be FACTS: equal or the allowed diffs>
Allowed diffs: <each modal diff with line>
Wrapper commit proof: <paste>
Negative controls: <paste both, exit=1>
check_doc_labels / gen_glossary --check / check_requirements / gen_fact_tables --check /
check_pinned_text / pytest test_docs_*: <exit codes>
build_books: <four result lines>; overfull vs baseline: <numbers>
ste_check (PR line range), before -> after by rule: S2 a->b, V1 ..., total X->Y, per prose KB
### Terms added to the dictionary
### Owner list (not fixed)
| # | Label | Quoted sentence | Why | Evidence | Proposed action |
### Not run on this host
```

Then hand the PR to the meaning reviewer (section 5). Push the branch; a human merges.

---

## 4. Negative control for the reviewer

The reviewer re-runs 3.4 on the PR head (one command) and one control from 3.5 with a number of their own
choice. A PR whose worker did not show the two controls is returned unreviewed.

---

## 5. Meaning-review brief (Opus)

Input: the base section text (from `base_unwrapped.tex`), the new section text, `git diff BASE..HEAD -- $F`,
the worker's PR description, and sections 2 and 0 of this order. Read whole sections, not only hunks.

Check, sentence by sentence:
1. **Meaning preserved.** Same subject, same action, same object, same condition, same scope. Pronouns
   resolve to the same thing. "because" and "so" are not added where the original only listed facts.
2. **Strength preserved.** Modals, negations, hedges and limits (list in 2.3-5). A caveat is still a caveat,
   still next to the figure it limits, and no weaker ("unvalidated", "indicative", "lower bound",
   "proposal only", "does not hold", "not signed off").
3. **No fact added or lost.** Including the blind spots of 3.4: numbers in words, list items, conditions,
   status marks, which number belongs to which subject, past versus present (a measurement stays a past
   result; a plan stays a plan).
4. **No fix smuggled in.** A stale or wrong statement keeps its meaning and is in the Owner list.
5. **Terminology.** Dictionary terms used with their meaning; no synonym swaps; added terms justified.
6. **Structure frozen.** Titles, heading numbers, list item counts and numbering, item IDs cited from
   sources (section 0.4), labels, section order.
7. **Standing caveats.** Every sentence that carries an `AGENTS.md` section 2 caveat is checked word by word.
8. **Code and data.** Code blocks and data cells unchanged (the facts check hashes code blocks; check the
   table cells by eye).

Output format (plain text in the PR review):

```
VERDICT: APPROVE | CHANGES REQUIRED
COUNTS: MEANING n, STRENGTH n, FACT n, STRUCTURE n, TERM n, STYLE n
1. [STRENGTH] <label>, after-file line <n>
   Before: "<exact original sentence>"
   After:  "<exact new sentence>"
   Problem: <one sentence>
   Replacement: "<full sentence ready to paste>"
2. ...
OWNER LIST: <confirmed / items to add, same table as 3.7>
```

MEANING, STRENGTH, FACT and STRUCTURE findings block the merge. TERM and STYLE findings are advice. The
worker applies the replacements, re-runs 3.4 and 3.6, and the reviewer checks only the changed sentences.

---

## 6. PR split and order

Sizing: "in-scope" = bytes of the sections of the PR; "prose" = the converted prose the worker rewrites.
The limit is about **50 KB of prose and 80 KB of section text** per PR. Reason: the worker must hold the base
section, write the new text and read tool output in one context (80 KB of LaTeX is about 25 000 tokens per
copy); the Opus reviewer reads base, new text and diff, about three times the size; and one rewritten
sentence in about 400 is a meaning risk, so a review larger than this loses attention at the end. Run the
PRs **sequentially** (finding 0.5). The order puts the most-read text first (UM, then TM flow and decisions,
then evaluations, then measurement reports).

| # | Branch name | Sections (labels) | Documents unwrapped (Q1=A) | KB section / prose / tab+code | ste findings before |
|---|---|---|---|---|---|
| **S01 pilot** | `docs/ste-s01-um-getting-started` | `um:ch:getting-started`, `um:guide:readme-index`, `um:ch:project-structure`, `um:guide:project-structure`, `um:ch:build-and-run-commands`, `um:guide:quick-start`, `um:ch:supported-instructions`, `um:guide:supported-instructions`, `um:ch:debug-interface`, `um:guide:debug-interface`, `um:ch:local-quality-checks`, `um:guide:local-qa`, `um:guide:key-documentation`, `um:guide:frequently-used-commands`, `um:guide:reference-model-and-verification`, `um:guide:commit-and-coding-rules` (with their sub-labels) | `docs/readme/README.md`, `docs/readme/PROJECT_STRUCTURE.md`, `docs/readme/QUICK_START.md`, `docs/readme/SUPPORTED_INSTRUCTIONS.md`, `docs/readme/DEBUG_INTERFACE.md`, `docs/development/LOCAL_QA_SETUP.md`, `CLAUDE.md` (4 wrappers) | 42.7 / 20.9 / 20.5 | 77 |
| S02 | `docs/ste-s02-um-coding-guidelines` | `um:ch:coding-guidelines`, `um:guide:coding-guidelines`, `um:guide:coding-compliance-audit`, `um:guide:spyglass-lint-remediation` | `docs/development/CODING_GUIDELINES.md`, `CODING_COMPLIANCE_AUDIT.md`, `SPYGLASS_LINT_REMEDIATION_PLAN.md` | 76.7 / 44.5 / 32.0 | 236 |
| S03 | `docs/ste-s03-um-ci` | `um:ch:continuous-integration` (intro), `um:flow:ci-cd-workflow`, `um:flow:ci-setup`, `um:flow:pre-commit-setup`, `um:flow:qa-workflow-diagram`, `um:flow:workflow-triggers`, `um:flow:badges`. **Not** `um:flow:ci-cocotb`, `ci-qa-checks`, `ci-random-tests`, `ci-rtl-checks`, `ci-soc-coverage` (verbatim workflow comments) | `docs/CI_CD_WORKFLOW.md`, `.github/CI_SETUP.md`, `.github/PRE_COMMIT_SETUP.md`, `.github/QA_WORKFLOW_DIAGRAM.md`, `.github/WORKFLOW_TRIGGERS.md`, `.github/BADGES.md` | 68.3 / 44.0 / 24.1 | 172 |
| S04 | `docs/ste-s04-um-tool-flows` | `um:ch:tool-flows`, `um:flow:proprietary-sim`, `um:flow:dqc` | `docs/verification/PROPRIETARY_SIM_FLOW.md`, `docs/verification/DQC_FLOW.md` | 37.9 / 16.9 / 20.9 | 83 |
| S05 | `docs/ste-s05-tm-pd-flow` | `tm:ch:flow-overview` (intro), `tm:pd:openroad-flow`, `tm:ch:constraint-files`, `tm:pd:constraints-index`, `tm:pd:constraints-quick-reference`, `tm:pd:constraints-readme-sdc`, `tm:pd:constraints-sdc-files-summary` | `docs/design/OPENROAD_FLOW_SPEC.md`, `pnr/constraints/INDEX.md`, `QUICK_REFERENCE.md`, `README_SDC.md`, `SDC_FILES_SUMMARY.md` | 75.2 / 48.8 / 26.2 | 131 |
| S06 | `docs/ste-s06-tm-sky130-node` | `tm:ch:sky130-flow`, `tm:pd:sky130-real-drc-lvs`, `tm:pd:sky130-cdc-maxss`, `tm:pd:node-strategy` and its six sub-labels | `docs/SKY130_REAL_DRC_LVS_EVALUATION.md`, `docs/SKY130_CDC_MAXSS_ANALYSIS.md`, `CLAUDE.md` | 56.2 / 44.4 / 11.3 | 228 |
| S07 | `docs/ste-s07-tm-verif-gates` | `tm:ch:test-benches-and-suites` (intro only), `tm:suite:phase4-random-kernels`, `tm:flow:functional-coverage`, `tm:flow:i2c-functional-coverage-model`, `tm:ch:cdc-and-lint-checks`, `tm:flow:cdc-snitch-poc`, `tm:ch:synthesis-undefined-value-gate`, `tm:flow:synth-undef-gate` | `docs/regression/PHASE4_RANDOM_KERNELS.md`, `docs/verification/FUNCTIONAL_COVERAGE.md`, `docs/verification/I2C_FUNCTIONAL_COVERAGE_MODEL.md`, `docs/verification/CDC_SNITCH_POC.md`, `docs/SYNTH_UNDEF_GATE.md` | 68.6 / 41.1 / 26.9 | 192 |
| S08 | `docs/ste-s08-tm-decisions` | `tm:ch:decision-log`, `tm:dec:3pll-cdc`, `tm:dec:m10-l2`, `tm:dec:peripheral-bus`, `tm:dec:xezim`, `tm:dec:agent-improvement-proposal` | `docs/3PLL_CDC_EVALUATION.md`, `docs/M10_L2_DECISION_ANALYSIS.md`, `docs/PERIPHERAL_BUS_EVALUATION.md`, `docs/XEZIM_EVALUATION.md`, `docs/AGENT_IMPROVEMENT_PROPOSAL.md` | 80.5 / 52.0 / 28.3 | 271 |
| S09 | `docs/ste-s09-tm-tessent` | `tm:ch:tessent-flows`, `tm:flow:tessent-atpg`, `tm:dec:tessent-mbist-evaluation` | `docs/design/TESSENT_ATPG_FLOW.md`, `docs/design/TESSENT_MBIST_EVALUATION.md` | 64.6 / 30.0 / 34.4 | 201 |
| S10 | `docs/ste-s10-tm-pd-evaluations` | `tm:pd:librelane-patching`, `tm:pd:rvb-fanout-fix`, `tm:pd:power-domain-evaluation` | `docs/LIBRELANE_PATCHING_EVALUATION.md`, `docs/design/RVB_FANOUT_FIX_PROPOSAL.md`, `docs/POWER_DOMAIN_EVALUATION.md` | 67.1 / 40.0 / 27.1 | 433 |
| S11 | `docs/ste-s11-tm-commercial` | `tm:ch:commercial-flow-comparison`, `tm:pd:commercial-flow-comparison` | `docs/COMMERCIAL_FLOW_COMPARISON.md` | 44.3 / 23.4 / 20.7 | 133 |
| S12 | `docs/ste-s12-tm-fpga-board` | `tm:ch:fpga-prototyping`, `tm:dec:fpga-board-selection` | `docs/FPGA_BOARD_SELECTION.md` | 65.7 / 46.9 / 18.6 | 274 |
| S13 | `docs/ste-s13-tm-fpga-stage0` | `tm:dec:fpga-stage0-evaluation` | `docs/FPGA_STAGE0_EVALUATION.md` | 37.8 / 20.3 / 17.6 | 97 |
| S14 | `docs/ste-s14-tm-hls-1` | `tm:ch:high-level-synthesis`, `tm:dec:cpp-to-rtl-hls-evaluation` from its intro to `...:verification` (sub-labels `:recommended-approach-decision` ... `:verification`) | none (the wrapper of `docs/CPP_TO_RTL_HLS_EVALUATION.md` is removed in S15) | 46.0 / 39.1 / 6.8 | 241 |
| S15 | `docs/ste-s15-tm-hls-2` | `tm:dec:cpp-to-rtl-hls-evaluation` from `...:gh-119-egt-follow-up-the-combinational-candidate-ppa-attempt-is-invalid-2026-09-15` to `...:cpugpu-hand-rtl-exposure-verdict-not-exposed-to-this-specific-construct` | `docs/CPP_TO_RTL_HLS_EVALUATION.md` | 48.0 / 40.1 / 7.9 | 268 |
| S16 | `docs/ste-s16-tm-commercial-sim-cov` | `tm:ch:coverage` (intro), `tm:flow:commercial-sim-coverage` | `docs/verification/COMMERCIAL_SIM_COVERAGE.md` | 73.7 / 18.8 / 54.8 | 173 |
| S17 | `docs/ste-s17-tm-soc-cov-1` | `tm:flow:soc-coverage-report` intro, `:method`, `:results`, `:combined-report-soc-cpu-cache-gpu-suites-bead-1eyv-2026-10-10`, `:rtlcpu-mem-gpu-line-triage-slice-1-bead-a5ze-2026-10-10`, `:rtlcpu-mem-gpu-line-triage-slice-2-...` | none (removed in S18) | 66.2 / 34.3 / 32.0 | 173 |
| S18 | `docs/ste-s18-tm-soc-cov-2` | `tm:flow:soc-coverage-report` `:coverage-cleanup-beads-...-pr-316-2026-10-18`, `:coverage-cleanup-second-pass-...`, `:7ovx-...`, `:ej6j-...`, `:gh-222-waiver-audit-...`, `:triage`, `:gate-decision`, `:reproducing` | `docs/verification/SOC_COVERAGE_REPORT.md` | 70.2 / 36.0 / 34.2 | 268 |
| | | **Total (18 PRs)** | | **1085.6 / 641.4 / 444.2** | 3651 |

When a PR rewrites only part of one wrapped document (S14, S17), it keeps the wrapper; the follow-on PR that
finishes the document removes it. In S14 and S17 skip step 3.3-a and pass no `DOC` to `ste_unwrap.py` (then
`ste_check.py` must run on a copy unwrapped for that document; do it for the counts only). S08 may be split
at `tm:dec:xezim` if the worker runs out of room (80.5 KB).

### 6.1 Special risks per PR

- **S01 (pilot).** `README.md` cites `um:guide:quick-start`; `CLAUDE.md` names the four pointer chapters by
  label. Quick start is mostly commands (code, unchanged) and phase titles with emoji remnants ("Phase 0:
  Reference Model Testing (Complete )", "added 2026-10-15") that stay (titles frozen). The
  `um:guide:key-documentation` table cites old `docs/design/*.md` paths next to their labels; they are stale
  but accepted by `check_doc_labels.py` through `path_map.tsv`: do not fix, put in the Owner list.
  `um:guide:commit-and-coding-rules` overlaps `AGENTS.md` section 9: do not harmonise.
- **S02.** The most cited text: section numbers 1.3, 1.4, 1.7 and the title "7. Source comments" are cited by
  RTL, HLS shims, `flake.nix`, `.editorconfig`, `pyproject.toml`, `lint/spyglass/waivers.awl` and `AGENTS.md`
  (finding 0.4). The budget table under `um:guide:coding-guidelines:71-budgets` must keep every number,
  because `tools/docs/check_comment_budget.py` enforces the same budgets. "Existing verified RTL is
  grandfathered" keeps its strength. The compliance audit and the SpyGlass plan are dated plans
  (stale-prone): Owner list, not fixes.
- **S03.** The CI guides predate the current workflows; expect stale statements (Owner list). The five
  `um:flow:ci-*` sections with relocated workflow comments stay verbatim; the workflow files cite them.
  `um:flow:qa-workflow-diagram` is mostly a `textblock` diagram (unchanged).
- **S04.** `um:flow:proprietary-sim` "rule 6" (cited by `tools/verif/check_elab_strict.py`) and
  `um:flow:dqc` "F-2" (cited by `dqc/waivers/lint_soc_top.awl`) are frozen; `dqc/Makefile` cites
  `um:flow:dqc` three times. Licence matrix tables are data.
- **S05.** `tm:pd:openroad-flow` holds long Tcl blocks (unchanged) and may describe an older flow (Owner
  list). The constraint documents are identifier-heavy; N1 noise is high.
- **S06.** Carries standing caveats: nom_tt only, "clean at 9 corners", "only node with real DRC/LVS",
  ASAP7 zero-wire STA, "does not hold". `tm:pd:node-strategy:asap7-phase-23-sign-off-achieved-at-run-43-...`
  contradicts `AGENTS.md` section 2 in its title and first sentence (finding 0.3): keep, Owner list. The
  in-line `\warn{}` marks and "unsupported" must stay next to their figures.
- **S07.** `tm:flow:synth-undef-gate` probe IDs (p13, p19) and the "dud4 casualty signature" are cited by
  `tools/verif/check_synth_undef.py` and `pnr/plugins/librelane_plugin_cvt_synthgate`. The TM CDC authored
  chapter cites `tm:flow:cdc-snitch-poc` and `tm:ch:cdc-and-lint-checks` as the flow description.
- **S08.** `tm:dec:xezim` section 5 is cited by number (`qa-checks.yml`, `check_elab_strict.py`).
  `tm:dec:peripheral-bus` and `tm:dec:m10-l2` touch the next authored area (bus fabric): do not run S08 in
  parallel with the bus-fabric chapter PR (Q8). `tm:dec:agent-improvement-proposal` states AI/human
  boundaries (owner-sensitive policy text). `tm:dec:3pll-cdc` is cited from the CR source archive.
- **S09.** Adjacent to the DFT design area; references to `tm:ch:dft-architecture` stay as they are. Licence
  and "Stage 2 evaluation" status words keep their strength.
- **S10.** `tm:pd:rvb-fanout-fix` begins "STUDY / PROPOSAL ONLY ... requires explicit human architecture
  approval": keep the strength. `tm:pd:power-domain-evaluation` sub-labels are cited from the CR archive
  (labels never change anyway). LibreLane patching relates to `AGENTS.md` section 7 "do not edit the shared
  LibreLane install".
- **S11.** "All figures are indicative", "No arm meets sign-off" (standing caveat). Mostly tables.
- **S12, S13.** "No board and no vendor toolchain on the host" status; "measured ECP5 fmax lower bound":
  keep "lower bound".
- **S14, S15.** Strength-heavy titles and sentences ("what must not be read into this table", "may and may
  not claim", "invalid", "confirmed corrupt"); Synlig/sv2v caveats (`USE_SYNLIG`); GH #119 follow-ups.
- **S16 to S18.** Measurement reports: 50 % tables. Waiver counts and coverage percentages are data. Only
  if Q5 = A.

### 6.2 The pilot

**S01** is the pilot: most-read text, procedures and commands, four `CLAUDE.md` blocks, low citation risk,
small (20.9 KB prose). Do not start S02 before the owner has looked at S01. The owner checks:
1. The wrapper decision (Q1) as applied: the PDF pages around the quick start (no "Moved from" rules, or as
   decided) and the `% Source:` comment.
2. The style: three procedures and two descriptive paragraphs, compared with `um/parts/02-integration.tex`.
   Is this the "STE-style" the owner wants, or too terse or too loose?
3. The PR description: facts check, allowed diffs, both negative controls, before/after `ste_check` counts
   (target about 2 to 3 per prose KB), build lines.
4. The Owner list: is the format useful, and the policy for stale items (Q4)?
5. The Opus review: are its findings real and its replacements usable? How many rounds were needed?
6. Effort: worker and reviewer time per KB, to plan S02 to S18.
7. Titles left unchanged (Q6) and "should" left unchanged (Q7): acceptable?

---

## 7. What is deliberately left (the pass is not complete for any book)

- **DS: the whole book except authored chapters and `00-about`** (857 KB of converted documents and module
  contracts). It is normative design text; authored chapters replace it area by area (bus fabric next, then
  CPU core and caches, GPU, peripherals, NPU, crypto, DFT, PLL). The verification plan, reference-model
  spec and SDC timing spec wait for Q3.
- **TM design areas**: `tm:ch:dft-architecture` (338.6 KB, DFT area), `tm:flow:control-signals-analysis`
  (14.3 KB, CPU core), the module reference (85.8 KB). Authored chapters replace them.
- **Relocated source comments** everywhere (DS 207.3, TM 634.2, UM 23.7 KB): history of source files, 95 %
  verbatim blocks; they move unchanged to the CR source archive when an authored chapter replaces them.
- **CR**: records, the source archive and the headings (1420.6 + about 98 KB) by rule; the framing is
  already STE-style.
- **Code blocks and data tables inside the rewritten sections** (444 KB): unchanged by rule.
- **Section titles** (Q6) and the numbers cited from source files.
- **The empty TM part 06**: filling it is new content (an authored chapter), not an STE rewrite.
- **`AGENTS.md`, `CLAUDE.md`, `README.md`** and source headers: not part of this order.

After S18 the books still hold about 1.2 MB of design-area text and 2.1 MB of verbatim text. Nobody should
read "STE pass done" as "the books are STE-style".

### Reported discrepancies (for the owner, not for workers to fix)

1. `AGENTS.md` section 11 points to the TM part "Tool defects and standing caveats"; the part is empty.
2. TM text that contradicts `AGENTS.md` section 2: `tm:pd:node-strategy:asap7-phase-23-...` ("signed off").
   Expect more in S05, S06, S11, S14/S15 (Owner lists).
3. Source files cite section numbers and item IDs inside books (finding 0.4), which `AGENTS.md` section 10
   forbids ("Never cite ... a section number"). A follow-up could add sub-labels and repoint them.
4. `um:guide:source-archive` uses `origin/main`; on this clone the remote is `claude_verilog_test`.

---

## 8. Open questions for the owner

**Q1. The `relocated` wrapper around converted documents** (all 1086 KB of in-scope text).
- A. Remove the wrapper of each rewritten document; a LaTeX comment names the source document and the base
  commit; the converted wording stays in git history. **Recommended**: the caption "Moved from" becomes false
  after a rewrite, and `ste_check.py` ignores the text while the wrapper is there.
- B. Keep the wrapper; accept a false caption and run `ste_check.py` on unwrapped copies only.
- C. Remove it and copy the converted wording verbatim into the CR source archive (about 1.1 MB more CR).
- D. Remove it and print a visible note "Rewritten from docs/X.md" instead.

**Q2. Relocated source-comment text** (DS 207, TM 634, UM 24 KB).
- A. Verbatim, out of scope; authored chapters replace it and it moves unchanged to the archive.
  **Recommended** (section 1.3).
- B. Rewrite only the 54 KB of it that is not in `textblock` blocks.
- C. Rewrite all of it.

**Q3. DS text that is not hardware architecture**: verification plan (`ds:ch:verification-plan`, 48.8 KB),
reference-model spec (`ds:ch:reference-model` in `ds:ch:reference-models`, 19.6 KB), SDC timing spec
(`ds:ch:sdc-timing-spec`, 26.0 KB); and the phase plans in DS part 1 (`docs/PHASE3_CLOSURE_AND_PHASE4_PLAN.md`,
`PHASE5/6/7_*_PLAN.md`).
- A. Design area: they wait for authored chapters (each area's requirements carry their own verification;
  a later authored chapter covers timing constraints and the models). **Recommended**.
- B. Add them as PRs S19 and S20 after S18, reviewed by the RTL or verification owner (DS is normative).
- C. Treat the phase plans as history and move them verbatim to the CR in a separate structural PR.

**Q4. Stale or false statements found during the pass.**
- A. Owner list in each PR description only.
- B. Owner list plus one bead per PR that collects the items. **Recommended** (beads are the project tracker;
  a PR description is not searchable later).
- C. B, and after owner approval a separate `[Fix]` documentation PR per item, never inside an STE PR.
  (Can be combined with B.)

**Q5. Measurement reports** (S16 to S18: `tm:flow:commercial-sim-coverage`, `tm:flow:soc-coverage-report`;
210 KB, half tables).
- A. Rewrite them like the rest (18 PRs).
- B. Leave them as converted (15 PRs); they are dated results, read rarely, and their value is the data.
  **Recommended.**
- C. Move them verbatim to the CR (structural change; the `tm:` labels would sit in the CR). Not recommended.

**Q6. Section titles.**
- A. Frozen in this pass, including leading numbers. **Recommended** (cited by sources and `AGENTS.md`;
  unlabeled sections are keyed by title in the facts check).
- B. Allow title rewrites that keep the leading number and every identifier; regenerate `labels.tsv`.

**Q7. "should" and "may".**
- A. Keep "should" as written; "may" becomes "can" only where it means possibility or permission.
  **Recommended** (no change of strength; the facts check cannot see these words).
- B. The owner states, per document, that "should" is mandatory there (for example the coding guidelines),
  and a separate owner-approved PR changes it to "must".

**Q8. Decisions that touch the next authored area** (`tm:dec:peripheral-bus`, `tm:dec:m10-l2`, and the
memory-map-related text).
- A. Rewrite them in S08 now; the bus-fabric chapter cites them as they are (precedent: the CDC and power
  chapters left `tm:dec:3pll-cdc` and `tm:pd:power-domain-evaluation` in place). **Recommended**, with S08
  not in parallel with the bus-fabric PR.
- B. Skip them until the bus-fabric chapter is merged, then decide.

**Q9. Glossary growth by workers.**
- A. Workers may add technical names and verbs under the rules of 2.2; the reviewer approves each. **Recommended.**
- B. Only the owner adds terms; workers list candidates.


## Owner decisions (final; these override any option text above)

- Q1 (owner): remove the `relocated` wrapper of each rewritten document. Leave one LaTeX source comment
  (`% Rewritten in STE style from <old path>; the verbatim original is in git history.`) at the place
  of the wrapper. Nothing is added to the Changes record.
- Q2 (primary planner): relocated source comments stay verbatim. Authored chapters replace them later.
- Q3 (owner): the DS verification plan, reference-model specification, SDC timing specification and the
  phase plans are design area. Out of scope of this pass.
- Q4 (owner): stale statements are NOT fixed in an STE PR. Each PR lists them in its description. The
  standing caveats get their own authored PR BEFORE the pilot (the TM part "Tool defects and standing
  caveats"); after it, an STE worker that meets a statement against a caveat keeps the meaning and lists it.
  `bd` is not installed on this host: no beads; the list goes in the PR description.
- Q5 (owner): the three measurement reports (PRs S16, S17, S18) are NOT rewritten. The pass is S01 to S15.
- Q6 (primary planner): section titles and numbering are frozen.
- Q7 (primary planner): keep "should". Change "may" to "can" only where it means possibility or permission.
- Q8 (primary planner): `tm:dec:peripheral-bus` and `tm:dec:m10-l2` are rewritten in S08, and S08 does
  not run in parallel with a bus-fabric chapter PR.
- Q9 (primary planner): workers add glossary terms under the work-order rules; the reviewer approves each.
- Basis: "STE-style", not compliance. No part gets the `% ste: done` marker.
- Review: `check_facts.py` with both negative controls, plus an Opus meaning review of the diff.
- Doc PRs run one at a time (each regenerates `labels.tsv`). The git remote is `claude_verilog_test`.


## Lessons of the pilot S01 (binding for S02 to S15)

The meaning review of S01 found about one meaning error for each 5 KB of prose. All were at a split or a join.

1. After a split, check what every "This", "It", "They", "For this reason", "So", "Then" and "For example"
   points to, and what every colon introduces. Do not add a reason phrase or an example phrase that the
   before text does not have.
2. When you join items with "and", each item keeps its own qualifier. A qualifier of one item does not
   spread to the other. A plural stays a plural (two files are not "this file").
3. Strength words stay: must, must not, should, can, never, always, only, at least, at most, and
   verified / validated / confirmed / signed off / passes. Never weaken "verified" to "checked".
4. Finish each section. Re-run `ste_check.py` on the FINAL file and report those counts.
5. The facts check fails on a repeated number or path-like token in a new sentence ("Phase 2", "new/modified").
   Rewrite without repeating such a token; do not write stilted text to avoid it.
6. The comment at each removed wrapper is:
   `% Rewritten in STE style from <old path>; the verbatim original is in git history (before commit <base>).`
   Remove the old `% Converted from` and `% Moved verbatim from` comment lines of that document.
7. Each PR description gives the base commit and carries the owner list of stale statements that were not fixed.
8. The shell hook rewrites `grep`; `grep -c` gives wrong counts. Use the Grep tool.
