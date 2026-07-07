# Coding Guidelines Compliance Audit

**Date**: 2026-07-07 · **Baseline**: `e8e633d` (post-PR #113)
**Guidelines**: [`CODING_GUIDELINES.md`](CODING_GUIDELINES.md)

Audit of the current codebase against the adopted guidelines. Corpus: 63 `.sv` files
under `rtl/` (the 11 `.v` files in the tree are vendor stubs/sim models, out of scope),
~207 Python files (~55 k lines, of which ~17 k are the stale `micro_p/` duplicate).

Per the adopted policy, existing verified code is **grandfathered** — the violations
below are a prioritized backlog, not a mandate for immediate mass edits.

---

## 1. What already complies (codified as-is)

| Area | Finding |
| :--- | :--- |
| RTL file organization | One module per file, filename == module name: **100 %** of `rtl/` files. All 6 packages follow `*_pkg.sv` with no co-located modules. |
| RTL processes | `always_ff`/`always_comb` only — **zero** plain `always @` blocks in `rtl/`. |
| Reset polarity | Uniformly active-low `rst_n` — no active-high resets anywhere. |
| Ports | ANSI style, one per line, clk/rst first, interface-grouped with banner comments. |
| Case discipline | No `casex`; the 4 `casez` sites are `unique casez` don't-care decodes (e.g. `rtl/periph/uart_controller.sv:190`). |
| Constants | `localparam` vs `parameter` used correctly; params `ALL_CAPS`. |
| Types | Strong package/typedef/enum/struct usage; enums packed with explicit base types (`rtl/gpu/gpu_pkg.sv:38`). |
| Whitespace | Spaces only — no tabs in `rtl/` or Python. |
| Python core | `tb/models`, `tb/tests`, `sim`, `sw` are ruff-format-clean, typed (PEP 604), Google-docstring'd, pylint ≥ 9.5. |
| Python safety | No wildcard imports, no bare `except:` anywhere. |
| Shell | `install-missing-tools/`, `tools/cdc/`, plugin wrappers all use `set -euo pipefail`. |
| Declaration before use | `rv32i_core.sv` / `rv32i_cpu_top.sv` violations fixed in PR #113 (issue #111). |

---

## 2. Violations and remediation plan

Priorities: **P1** = low-risk, high-value, do soon · **P2** = mechanical cleanup,
schedule freely · **P3** = touches verified RTL semantics/interfaces, needs full
regression (`soc_all` 73/73) and its own review; naming-only changes don't invalidate
ASAP7 sign-off but a confirmation P&R run is prudent.

### P1 — low-risk, high-value

| # | Finding | Evidence | Proposal |
| :- | :--- | :--- | :--- |
| P1-1 | No license ⇒ no SPDX headers possible. 0 of 63 RTL files (and no Python file) carry a license header; no `LICENSE` file exists (README says "educational and testing purposes"). | `grep -rl 'SPDX\|Copyright' rtl` → 0 | Choose a license (MIT/Apache-2.0 typical for educational HW), add `LICENSE`, then add SPDX tags file-by-file as files are touched. |
| P1-2 | Stale `micro_p/` tree: ~17,421 Python lines (~31 % of all Python) duplicating an old `tb/` + `sim/` snapshot; unreferenced by pyproject, testpaths, or CI. | `diff -rq tb micro_p/tb` shows dozens of divergent copies | Delete `micro_p/` (git history preserves Phase 1). If it must stay, add a top-level `micro_p/README.md` marking it frozen and exclude it in every tool config. |
| P1-3 | `sim/cxx_shim.sh` has no `set -e` — a compiler shim that silently continues past failures. | only `.sh` in tree without it | Add `set -euo pipefail`. |
| P1-4 | RTL CI is non-gating: `rtl-checks.yml` runs Verible with `continue-on-error: true`; ~33 open findings (`case-missing-default`, `always-ff-non-blocking`) per `.rules.verible_lint` note. | `.github/workflows/rtl-checks.yml`; `.rules.verible_lint:45` | Burn down the ~33 findings (each is a real latch/discipline risk), then drop `continue-on-error` to make Verible a hard gate. |
| P1-5 | Python CI gate covers only `tb/models tb/tests` — `tb/cpu_uvm`, `sim`, `tb/cocotb`, `pnr`, `analog`, `plugins` have zero CI lint/type enforcement. Pre-commit covers more (`tb/cpu_uvm`, `sim`) than CI, so local and CI results diverge. | `qa-checks.yml` hardcodes the two dirs in every step | Step 1: align CI scope with pre-commit (`tb/models tb/tests tb/cpu_uvm sim`). Step 2: ruff-format `tb/cocotb` (P2-2) then add it. |
| P1-6 | Hardcoded machine-specific absolute paths break portability. | `analog/pll_clkgen/sky130/sim/run_vco_sweep.py:10-11` (`/home/neuromorphic/...`), also `run_vco_sweep_retuned.py` | Derive repo root from `__file__`; take the librelane path from an env var with a documented default. |
| P1-7 | Verilator lint (`make lint` / `lint_soc`) exists but is not run in any CI workflow. | `sim/Makefile:339`; no workflow invokes it | Add a Verilator lint job to `rtl-checks.yml` (blocking — the tree is already clean). |

### P2 — mechanical cleanup

| # | Finding | Evidence | Proposal |
| :- | :--- | :--- | :--- |
| P2-1 | Indent outliers vs 4-space rule: `rtl/cpu/core/rv32i_alu.sv` is 2-space throughout (36 two-space vs 2 four-space top-level indents); `rtl/cpu/rv32i_cpu_top.sv` mixes 2-space ports with 4-space body (210 vs 93). | verified by count | `make format-verible-fix VERIBLE_CHECK_FILES="rtl/cpu/core/rv32i_alu.sv rtl/cpu/rv32i_cpu_top.sv"`; formatting-only diff, sim-verify with existing regressions. |
| P2-2 | `tb/cocotb` (live dirs) is not ruff-formatted: 181 lines > 100 cols, hand-aligned assignment columns, `#`-comment headers instead of module docstrings, third-party-before-stdlib import order. | `tb/cocotb/soc/test_timer.py:1-38` | Run `ruff format` + `ruff check --fix` over `tb/cocotb` (excluding `legacy/`), convert headers to docstrings, then add to pre-commit + CI scope. |
| P2-3 | Comma-joined imports (E401) in ungoverned scripts. | `analog/.../run_vco_sweep.py:8`, `analog/.../budget_pll_sky130.py:9`, `pnr/asap7/soc/gen_soc_top_hjson.py:31`, `pnr/freepdk45/gen_via_stubs.py:15` | One import per line; bring `pnr/`/`analog/`/`plugins/` under ruff (add to CI scope once clean). |
| P2-4 | Misleading dead `sys.path` hack: insert placed *after* the import it would enable. | `tb/tests/test_rv32i_model.py:12-15` | Reorder or delete the insert. |
| P2-5 | Inline-pragma waiver sprawl instead of scoped waivers: e.g. 11 `lint_off UNUSEDPARAM` pairs in `rtl/gpu/gpu_pkg.sv:4-33`. | grep `verilator lint_off` | Consolidate per-file waivers to a commented block at file top (or a central `.vlt` waiver file) with reasons. |
| P2-6 | No shellcheck anywhere; `pnr/constraints/validate_sdc.sh` uses `#!/bin/bash` instead of `#!/usr/bin/env bash`. | — | Add a shellcheck pre-commit hook (new scripts blocking, existing advisory); fix the shebang. |
| P2-7 | Test-quality gaps: ~86 % of asserts have no message (51 asserts, 1 message in `tb/tests/test_rv32i_model.py`); no `conftest.py`/fixtures — every test constructs `RV32IModel()` inline. | `tb/tests/test_rv32i_model.py:23,43,54,69` | Add a `cpu` fixture in `tb/tests/conftest.py`; add messages to non-obvious asserts opportunistically. |
| P2-8 | Docstring style mixed: NumPy-style underline sections inside an otherwise Google-style package. | `tb/models/cache_model.py:50-55` | Convert to Google style when next touched. |

### P3 — refactors requiring re-verification (proposal only)

These change signal/port names or semantics in signed-off RTL. Each item = its own
branch + full regression (`soc_all` 73/73, CPU rollup, GPU suite) + prudence P&R re-run.

| # | Finding | Evidence | Proposal |
| :- | :--- | :--- | :--- |
| P3-1 | Port-suffix split: GPU + CPU-top fully `_i`/`_o`; CPU leaf modules bare (`rtl/cpu/core/rv32i_alu.sv:20-30`: `operand_a`, `result`); periph mixed within single modules (`rtl/periph/uart_controller.sv:54-75`: bare `psel`/`prdata` beside `uart_tx_o`). | ~40 files suffixed, ~30 not | Harmonize to `_i`/`_o` per guidelines, one subsystem per change, starting with periph (smallest). |
| P3-2 | Clock/reset naming split: `clk_i`/`rst_n_i` in only 8 files (CPU top/core, soc_top, PLL); bare `clk`/`rst_n` in 36 — inconsistent even inside the CPU. | grep counts | Rename toward `clk_i`/`rst_n_i` together with P3-1 per subsystem. |
| P3-3 | Register-suffix drift: `_q` dominates (~1,930 uses) but `_r` used in `rtl/cpu/core/rv32i_core.sv`, `rtl/mem/rv32i_icache.sv`, `rtl/cpu/core/pipeline/rv32i_pipeline_ex1c.sv`; `_next` (7) coexists with `_d` (52). | grep | Rename `_r`→`_q`, `_next`→`_d` (mechanical, sim-verified). |
| P3-4 | File-scope package imports in 13 files (all cpu/mem): `rtl/cpu/core/rv32i_core.sv:13-15`, `rtl/mem/rv32i_dcache.sv:36-38`, all pipeline stages, `rtl/cpu/rv32i_cpu_top.sv:5`. GPU/soc/periph already use module-scoped imports. | `grep -rl '^import ' rtl` → 13 | Move to `module x import pkg::*;` header form. Note: `lint_soc` currently waives `-Wno-IMPORTSTAR`; after this fix the waiver can go. |
| P3-5 | `wire` declarations instead of `logic`: `rtl/periph/uart_controller.sv:182-250`, `rtl/periph/spi_controller.sv:170-237`, `rtl/gpu/vector_register_file.sv:42-44`. | grep | `wire x = expr;` → `logic x; assign x = expr;` (or keep single-line `logic` continuous assigns), per file, sim-verified. |
| P3-6 | Reset-discipline split: GPU + soc bridges async (`rtl/gpu/warp_scheduler.sv:142`), CPU pipeline + periph sync (`rtl/periph/timer.sv`) — documented as intentional (`sim/Makefile` `SYNCASYNCNET` waiver note) but heterogeneous. | — | **Recommend: accept as documented.** New modules follow the async-assert/sync-deassert guideline; unifying frozen leaf RTL is high-risk for zero functional gain. Revisit only at a tape-out gate. |
| P3-7 | Declaration-before-use: two known violators fixed (PR #113); rest of tree unswept. | — | Sweep remaining 61 files (Verible `forbid-forward-references`-style manual/scripted check); fix any stragglers found. |

### Config/tooling contradictions — **fixed in this change**

| Finding | Resolution applied |
| :--- | :--- |
| `.flake8` disabled E501/W503, contradicting ruff's 100-col limit; flake8 wired into nothing (not CI, not pre-commit). | **Deleted `.flake8`.** Ruff is the lint authority. |
| Two competing pylint configs: `.pylintrc` (fail-under 9.5, design limits) vs `pyproject.toml [tool.pylint]` (different disable list). Bare `pylint` (CI) read `.pylintrc`; pre-commit read pyproject — different rules per invocation. | **Merged pyproject's `[tool.pylint]` into `.pylintrc`** (single source); pre-commit hook now points at `.pylintrc`. |
| No `.editorconfig` despite a documented 4-space rule. | **Added `.editorconfig`.** |
| Commit categories drifted: `[RTL]` (9), `[Chore]` (8), `[Analog]` (7), `[PD]` (4) in active use but undocumented; `[Spec]` documented but unused. | **CLAUDE.md category list expanded** to match reality. |
| Guidelines not discoverable. | **Linked from README + CLAUDE.md.** |

---

## 3. Per-subsystem consistency matrix (reference)

| Dimension | CPU leaf (alu/regfile) | CPU top/core | GPU | periph | soc |
| :--- | :--- | :--- | :--- | :--- | :--- |
| Port `_i/_o` | none | yes | yes (all) | partial | partial |
| clk/rst naming | `clk`/`rst_n` | `clk_i`/`rst_n_i` | `clk`/`rst_n` | `clk`/`rst_n` | mixed |
| Reset discipline | sync | sync (pipeline) / async (control) | async | sync | mixed |
| `logic` vs `wire` | logic | logic | mostly logic | wire-heavy | logic |
| Indent | 2-space (alu) | mixed 2/4 (top) | 4-space | 4-space | 4-space |
| `default_nettype none` | no | no | yes | yes | mostly |
| pkg import placement | file-scope | file-scope | module header | module header | module header |

## 4. Suggested sequencing

1. **Now (this change)**: config fixes above (done).
2. **Next session**: P1-3 (`cxx_shim.sh`, verify sim builds still pass), P1-2
   (`micro_p/` deletion), P1-4 (Verible burn-down → hard gate), P1-5 step 1 (CI scope),
   P1-7 (Verilator in CI).
3. **Then**: P2 batch (formatting-only diffs, cheap to review).
4. **Scheduled refactors**: P3-3/P3-4/P3-5 (mechanical, sim-verified), then P3-1/P3-2
   per subsystem. P3-6 accepted as-is.

File each as a `bd` issue when picked up.
