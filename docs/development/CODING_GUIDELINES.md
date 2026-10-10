# Coding Practices & Style Guidelines

**Status**: Adopted 2026-07-07 · **Applies to**: all new and modified code
**Compliance audit**: [`CODING_COMPLIANCE_AUDIT.md`](CODING_COMPLIANCE_AUDIT.md)

This document consolidates the project's coding standards for SystemVerilog RTL, Python,
and shell/build scripts. It is based on industry references — the
[lowRISC Verilog Style Guide](https://github.com/lowRISC/style-guides/blob/master/VerilogCodingStyle.md)
for RTL and [PEP 8](https://peps.python.org/pep-0008/) (enforced via ruff) for Python —
adapted where the established house style deliberately deviates. Where a rule is already
enforced by a tool config, this document points at the config rather than restating it;
**the config file is authoritative**.

## Scope and enforcement policy

- **New code and modified code MUST comply.** When you touch a module or script, bring
  the lines you touch into compliance; whole-file cleanup is encouraged but not required.
- **Existing verified code is grandfathered.** Signed-off RTL (ASAP7/Sky130 PPA runs,
  `soc_all` 73/73 regression) is not retro-edited for style alone. Deviations are
  tracked as a prioritized backlog in the [compliance audit](CODING_COMPLIANCE_AUDIT.md);
  each cleanup lands as its own reviewed change with regression evidence.
- Authoritative tool configs: `.rules.verible_lint` (RTL style-lint),
  `pyproject.toml` (ruff/mypy/pytest),
  `.pylintrc` (pylint), `.pre-commit-config.yaml` (local gates), `.editorconfig` (whitespace).

---

## 1. SystemVerilog RTL

Reference: lowRISC Verilog Style Guide, adapted to the house style codified in
`.rules.verible_lint`.

### 1.1 File organization

| Rule | Detail |
| :--- | :--- |
| One module per file | Exactly one `module` (or one `package`) per `.sv` file. |
| Filename == module name | `rv32i_alu.sv` contains `module rv32i_alu`. Verible `module-filename` enforces this. |
| Package files | One `package` per file, **no modules in the same file**, filename `<pkg_name>.sv` matching the package name, with the `_pkg` suffix (`gpu_pkg.sv` → `package gpu_pkg`). |
| File header | Every file opens with a `//` comment block: module purpose, key behaviors, protocol notes. See `rtl/periph/uart_controller.sv:1` for the exemplar. |
| License header | Once the project adopts a formal license (see audit P1-1), every new file carries an SPDX tag (`// SPDX-License-Identifier: <license>`) under the header. |

### 1.2 Naming

| Item | Convention | Example |
| :--- | :--- | :--- |
| Modules | `snake_case`, subsystem prefix | `rv32i_alu`, `gpu_compute_unit` |
| Signals | `snake_case` | `mem_rdata`, `warp_active` |
| Parameters / localparams | `ALL_CAPS` (documented deviation from lowRISC CamelCase; `parameter-name-style` disabled in `.rules.verible_lint`) | `AXI_ADDR_WIDTH`, `N_MASTERS` |
| Registered signals | `_q` suffix | `state_q` |
| Combinational next-state | `_d` suffix (`_w` acceptable for derived combinational nets per `.rules.verible_lint`; do **not** use `_r` or `_next` in new code) | `state_d` |
| Input ports | `_i` suffix | `opcode_i` |
| Output ports | `_o` suffix | `result_o` |
| Bidirectional ports | `_io` suffix | `pad_io` |
| Clock | `clk_i` (additional clocks `clk_<name>_i`) | `clk_i` |
| Reset | `rst_n_i` — active-low is **mandatory**; no active-high resets | `rst_n_i` |
| Enums / types | `snake_case` with `_e` / `_t` suffix, packed with explicit base type | `typedef enum logic [6:0] {...} gpu_opcode_e` |

### 1.3 Language constructs

- **`logic` only.** No `reg`; no `wire` for new declarations (continuous assigns drive
  `logic` fine). **Do not use `` `default_nettype `` directives** — they conflict with Spyglass
  (`IND` "identifier not declared yet" on the port list). Implicit-net detection is covered by
  Verilator (`IMPLICIT`/`UNDRIVEN`) and Verible instead. See §1.8.
- **`always_ff` / `always_comb` only.** Never plain `always @(...)`. Sequential blocks
  use non-blocking (`<=`); combinational blocks use blocking (`=`). Never mix within a block.
- **Case statements**: `unique case` with a `default` arm. `casez` only for genuine
  don't-care matching (byte strobes, priority encoders), always `unique casez`.
  **`casex` is banned.**
- **Constants**: `localparam` for module-internal constants; `parameter` only for values
  a parent may override.
- **Declaration before use**: every signal, typedef, and localparam MUST be declared
  textually before its first reference within the module. No forward references
  (see fix #111 / PR #113 for prior violations).
- **Package imports are module-scoped**: `module foo import gpu_pkg::*; (...)`.
  File-scope `import pkg::*;` above the module is **banned** in new code — it pollutes
  the compilation unit and breaks tool-ordering assumptions.
- **No part/bit-select of a struct field in a port connection.** Writing
  `.port(sig.field[h:l])` or `.port(sig.field[i])` (or the same inside a concatenation, or a
  select of a nested/array-element struct field) is legal SystemVerilog but is mis-elaborated by
  the Synlig/UHDM frontend: it warns `Range select ... out of bounds ... Setting all N result bits
  to undef` and ties the port to `x`, silently turning downstream compares into don't-cares
  (bead `dud4`: the CPU hazard-unit `rs1`/`rs2` ports; `rv32i_core.sv`). Lint, LVS and
  per-module equivalence do not catch it. Assign the struct field to a named full-width signal
  first, take the select from that signal into a second named signal, and connect the latter.
  Selects of struct fields inside module bodies are not affected. Any new
  `Range select ... out of bounds` / `Setting all ... bits to undef` line in a Synlig synthesis
  log is a build failure, not a warning.
- **Latches are banned.** All combinational outputs assigned on every path
  (Verilator lint + `case-missing-default` guard this).

### 1.4 Reset style

- **New modules**: asynchronous assertion, synchronous deassertion, active-low —
  `always_ff @(posedge clk_i or negedge rst_n_i)` with an external reset synchronizer
  per clock domain (lowRISC standard; already the GPU / SoC-bridge discipline).
- **Grandfathered**: the CPU core/pipeline and peripherals use fully synchronous reset —
  a documented, intentional legacy discipline (see the `SYNCASYNCNET` waiver note in
  `sim/Makefile` `lint_soc`). Do not flip verified resets for style alone; any
  unification is a P3 audit item requiring full regression.
- Within one subsystem, the discipline must be uniform.

### 1.5 Ports and module headers

- ANSI-style port declarations only; one port per line; direction-aligned.
- Order: `clk_i`, `rst_n_i` first, then ports grouped by interface with banner comments
  (see `rtl/periph/timer.sv` port list).
- Parameter list `#(...)` precedes the port list; explicit named port connections
  (`.a(b)`) at instantiation sites — no positional connections.

### 1.6 Formatting

- **4-space indent, spaces only, no tabs** (`.editorconfig` + Verible `no-tabs`).
- Line length: soft limit 120 columns; hand-aligned AXI port maps
  may exceed it (`line-length` rule intentionally disabled).
- `begin`/`end` K&R style (`begin` trails the statement).
- **No formatting tool.** `verible-verilog-format` cannot reproduce the hand-aligned house
  style (see §1.7), so there is no format target and no CI format check. Match the
  surrounding code; formatting is enforced by review.

### 1.7 Lint gates

Before committing RTL:

```bash
cd sim
make lint        # Verilator semantic lint (CPU top)
make lint_soc    # Verilator semantic lint (SoC top)
make lint-verible   # Verible style lint (hard gate; whole tree is clean)
```

- Prefer fixing findings over waiving. If a waiver is genuinely needed, prefer a
  scoped, commented waiver near the top of the file over scattering inline
  `lint_off`/`lint_on` pairs through the body; every waiver carries a one-line reason.
- CI runs Verible via `.github/workflows/rtl-checks.yml`. The **lint step is a hard gate**
  (bead `hn9l`, audit P1-4 closed): the whole tree is Verible-clean, so any new finding fails
  the job. There is **no format check** (removed 2026-10-10 by user decision): on Verible v0.0-4063,
  81 of 83 `rtl/**/*.sv` fail `--verify`, retuned flag sets only reach 72 of 83, and even the
  house-style exemplars (`rtl/periph/timer.sv`, `gpio_controller.sv`) fail every variant, so an
  advisory step was pure noise. `make verible` is now an alias for `make lint-verible`.
  Re-adding a format gate requires a deliberate, verified, one-off whole-tree reformat first.
- Local and CI run the same Verible binary: `flake.nix` (`veribleFor`) repackages the CI release
  tarball (same version + sha256). Bump `rtl-checks.yml` and `flake.nix` together.
- `.rules.verible_lint` sets `always-ff-non-blocking=waive_for_locals:true`: blocking assignments
  to block-local temporaries inside `always_ff` are legal; blocking assignment to anything
  declared outside the block is still an error.

### 1.7.1 Synthesis undef-elaboration gate (bead `gc0y`)

A synthesis frontend can replace logic with `x` and log only a warning (Synlig turned
`.port(struct_reg.member[19:15])` into `5'x`; lint, `Checker.YosysSynthChecks`, LVS and P&R all passed
on the wrong design - `docs/SKY130_CPU_SYNLIG_DUD4.md`). Every LibreLane run started from `pnr/Makefile`
now runs `tools/verif/check_synth_undef.py` after `Yosys.JsonHeader` and `Yosys.Synthesis` (project plugin
`pnr/plugins/librelane_plugin_cvt_synthgate`, no shared-LibreLane edit) and aborts on a hit, naming
file:line and the message. It also checks the elaborated `*.h.json` for any instance input or named net wired
to constant `x`, independent of message wording. Details: `docs/SYNTH_UNDEF_GATE.md`.

- Fix the RTL (or the construct) rather than allowlisting. An allowlist entry in
  `tools/verif/synth_undef_allowlist.txt` is `rule | regex | justification`; it must name the exact
  construct and say why the substituted object cannot reach a flop or port. Stale entries are reported.
- Never allowlist `undef-range-select` for design logic unless the replaced bits are provably dead.
- Run it by hand: `python3 tools/verif/check_synth_undef.py --run-dir <run dir> [-v]` (exit 0 pass,
  1 finding, 2 could not judge - empty/no-banner logs are never a pass).

### 1.8 Spyglass lint discipline

Synopsys Spyglass is run on the SoC design as an additional lint gate (it is not installed in the
default dev environment — see the remediation plan for how to run it). Write new RTL to these rules so
it passes cleanly:

- **No `` `default_nettype `` directives** (§1.3) — they trigger Spyglass `IND`.
- **Non-blocking (`<=`) exclusively in `always_ff`** — including reset for-loops. Blocking (`=`) is
  allowed only in `always_comb` and for local automatic temporaries declared and consumed within the
  same iteration. Never mix `=` and `<=` in one sequential block (`SM_BNP` / `W336` / `NonBlockAssign`).
- **No empty `begin/end` blocks or empty case arms** — use a null statement `;` (`W192`).
- **Size index / loop-temporary variables** to the array they index — no bare 32-bit `int` used as a
  small-array index (`LINT_IMPROPER_RANGE_INDEX`).
- **No bare `initial` / `$fatal` / `$readmemh` / `$display`** in synthesizable RTL — guard with
  `` `ifndef SYNTHESIS `` so simulation keeps them but lint/synth skip them
  (`SM_IGN_INITIAL` / `W430` / `W213` / `LINT_SV_STRING_USED_IN_DESIGN`).
- **Match signedness and width in expressions** — use explicit `signed'()` / `unsigned'()` casts and
  width-matched operands (`SignedUnsignedExpr-ML`).

**Standing waivers** (intentional design, captured in `lint/spyglass/waivers.awl` with per-rule
rationale — do not "fix" these):

- `SynchReset-ML` — the CPU core/pipeline + peripherals use **synchronous reset** by design (§1.4).
  Async conversion is a separate P3 audit effort, not a lint fix.
- `STARC05-2.3.6.1` / `UnInitializedReset-ML` — no-reset memory/stack arrays (e.g. GPU `div_stack`),
  local blocking temporaries, and combinational defaults are not resettable flip-flops.
- `W392` — cross-module reset-name collisions (`core_rst_n`) are false positives, not polarity bugs.
- `STARC05-2.10.3.1` — elaboration-time `string` parameter compares (e.g. `PLL_IMPL == "RNM"`).
- `UndrivenInTerm-ML` — behavioral `$readmemh` ROM contents (e.g. `boot_rom.mem`).

Full per-file remediation status: [`SPYGLASS_LINT_REMEDIATION_PLAN.md`](SPYGLASS_LINT_REMEDIATION_PLAN.md).

---

## 2. Python

Reference: PEP 8 as enforced by **ruff** (lint + format), **mypy**, and **pylint**.
`pyproject.toml` and `.pylintrc` are authoritative; highlights:

- **Formatting**: `ruff format` (black-compatible), line length **100**, 4-space indent.
  No hand-aligned assignment columns — the formatter's output is canonical.
- **Lint**: `ruff check` with `E, F, I, N, W, UP`. Imports sorted (ruff `I`), stdlib →
  third-party → local, one import per line (no `import os, sys`).
- **Types**: mypy clean. Type hints (PEP 604 unions, e.g. `int | None`) are **required**
  for library-style code (`tb/models/`, `sim/`, `sw/`) and encouraged in test code.
- **Pylint**: score ≥ 9.5 (`.pylintrc` `fail-under`); config lives in `.pylintrc` only.
- **Docstrings**: Google style (`Args:` / `Returns:` / `Attributes:`). Every module starts
  with a docstring — not a `#` comment block. Exemplar: `tb/models/rv32i_model.py`.
- **No hardcoded absolute paths.** Derive paths from `__file__`, `Path.cwd()`, or
  environment variables; scripts must run on any checkout.
- **Errors**: no bare `except:`; catch specific exceptions; define domain exception
  classes (`IllegalInstructionError` pattern in `tb/models/rv32i_model.py`).
- **Constants**: named `UPPER_CASE` at module or class scope — no magic numbers in logic.
- **Logging**: `print()` is acceptable only in CLI entry points; library code uses
  `logging` or returns data.

**Documented exceptions** (already encoded in `pyproject.toml`):

- RISC-V mnemonic naming: uppercase function/variable names allowed via `N802`/`N806`
  ignores (`sim/riscv_encoder.py`).
- cocotb path bootstrapping: `sys.path.insert(...)` before local imports allowed via
  `E402` ignores — but the insert must precede the import it enables, and be limited to
  test entry points.
- `tb/cocotb/cpu/legacy/` is frozen and excluded from all tooling.

### 2.1 Test conventions

- pytest: `test_*.py` / `Test*` / `test_*` (enforced by `[tool.pytest.ini_options]`).
  Shared setup goes in `@pytest.fixture` (in `conftest.py`) rather than repeating
  construction in every test.
- **Assertions carry messages** when the bare expression doesn't make the failure
  obvious: `assert cpu.regs[1] == 0, "x0 must remain zero"`.
- cocotb: `@cocotb.test()` coroutines named `test_<feature>`; module docstring states
  the DUT and scenarios; reuse the shared BFMs (`tb/cocotb/bfm/`) instead of ad-hoc
  bus wiggling.

---

## 3. Shell and build scripts

- Shebang: `#!/usr/bin/env bash` (not `#!/bin/bash`).
- First non-comment line: `set -euo pipefail`.
- New scripts are shellcheck-clean.
- Makefiles: tabs for recipes (required by make; `.editorconfig` handles this),
  `.PHONY` declared for non-file targets, tool-existence checks before use
  (`command -v tool >/dev/null || { echo "ERROR..."; exit 1; }` — see `sim/Makefile`).

---

## 4. Commit messages

Format: `[Category] Brief description` (imperative, ≤ 72 chars first line).

Categories: `[Fix]`, `[Feature]`, `[Code]` (refactoring), `[Env]` (build/tooling),
`[Doc]`, `[Test]`, `[Spec]`, `[RTL]` (RTL design work), `[PD]` (physical design),
`[Analog]` (mixed-signal), `[Chore]` (maintenance).

---

## 5. Repository hygiene

- **No committed build artifacts**: waveforms (`*.vcd`), sim outputs, `obj_dir/`,
  P&R `runs/` directories are gitignored and must stay untracked.
  **Documented exceptions** (P&R *inputs*, not outputs): macro `.lef`/`.lib` views,
  gzipped macro netlists (`pnr/*/macro/*.nl.v.gz` — raw netlists exceed GitHub limits),
  and the PLL GDS (`analog/pll_clkgen/sky130/layout/gds/`).
- `.editorconfig` at repo root is the single source of truth for indent/EOL/whitespace;
  editors and CI whitespace hooks defer to it.
- Large files: pre-commit blocks additions > 500 KB (`check-added-large-files`).
- Dead code is deleted, not commented out — history lives in git.

---

## 6. Enforcement summary

| Layer | Tool | Scope | Gate |
| :--- | :--- | :--- | :--- |
| Editor | `.editorconfig` | whitespace/EOL, all files | advisory |
| pre-commit | ruff, mypy, pylint, pytest-smoke, whitespace hooks | `tb/models`, `tb/tests`, `tb/cpu_uvm`, `sim` | blocking locally |
| `sim/Makefile` | Verilator lint, Verible lint, CDC snitch | `rtl/**` | manual, run before commit |
| Spyglass | Synopsys Spyglass lint (+ `lint/spyglass/waivers.awl`) | `rtl/**` (SoC) | manual (external tool) — see §1.8 |
| CI `qa-checks.yml` | ruff format+lint, mypy, pylint, pytest+coverage | `tb/models`, `tb/tests` | **blocking** |
| CI `rtl-checks.yml` | Verible lint (whole tree) | `rtl/**` | **blocking** |
| `pnr/Makefile` (every `librelane-*` target) | `check_synth_undef.py` via `pnr/plugins` | synthesis logs + `*.h.json` | **blocking** (aborts the flow) |
| CI `tests.yml` / `random_tests.yml` | pytest / cocotb regression | functional | blocking |

Widening the enforced scope (cocotb lint, RTL hard gate, shellcheck) is tracked in the
[compliance audit](CODING_COMPLIANCE_AUDIT.md) remediation plan.
