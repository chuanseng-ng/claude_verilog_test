# Xezim evaluation: secondary compile + simulation tool (bead `qd9l`)

**Date:** 2026-11-01. **Status:** evaluation only. No CI, RTL or flow change; adoption is an open human decision (section 9).

**Verdict: do not add xezim to cocotb regression or CI now.** It silently miscompiles an idiom used in this RTL (section 4), and stock cocotb 1.9.2 cannot run on it (section 3). It is usable locally as a cross-check for functional gate-level sim and X-probing, never as sole evidence. **Separately, slang closes the use-before-declare CI gap today with no new dependency** (section 5).

Tags: **measured** (run here, this session), **inferred**, **claimed** (xezim's docs, not reproduced), **reported** (user or repo docs, not run here). Measurements are single runs unless stated. Raw logs live under `/nobackup/xezim_eval/` (not in the repo, and may be wiped).

## 1. Method

Tool under test: xezim 0.11.4, git `9dcffd69-dirty` (local one-line `Cargo.toml` edit), plain release build, no JIT. Baselines: Verilator 5.048, sv2v 0.0.13.1, pyslang 11.0.0, cocotb 1.9.2 (repo pin) and 2.0.1 (isolated install). RTL: `origin/main` at `87b7cf0`.

Each legality check needed a negative control, and each pass needed a control able to fail. **VCS and Xcelium are not installed on this host**: their figures are reported from `docs/verification/PROPRIETARY_SIM_FLOW.md` (2026-10-24), plus the user's confirmation from another machine that they reject use-before-declare.

Phase 3, the full regression bake-off, **was not run**: the plan's stop gate tripped (section 3).

## 2. Elaboration (measured)

`soc_top` and `rv32i_cpu_top` elaborate with exit 0 on four define arms (default, `SRAM_SKY130`, `SRAM_ASAP7`, `FPGA`). `--verbose` confirms real elaboration: 92 modules on default `soc_top`.

| Tool, `soc_top` | Wall | Peak RSS | Note |
|---|---|---|---|
| xezim `--compile` | 0.46-0.81 s | 135-186 MB | |
| Verilator `--lint-only` | 2.4-4.1 s | 91-151 MB | |
| sv2v | ~4.7 s | ~655 MB | |
| pyslang full compilation | 0.2-0.34 s | 57-73 MB | Default, FPGA, macro arms |

| Negative control | xezim | Verilator | sv2v | slang |
|---|---|---|---|---|
| Missing module | reject | reject | **accept** | reject |
| Use before declare (`assign`, `always_comb`) | **accept** | **accept** | **accept** | reject |
| Never-declared identifier | reject | reject | **accept** | reject |
| Illegal syntax | reject | reject | reject | reject |
| Override of nonexistent parameter | reject | reject | reject | reject |
| Override of localparam | reject | reject | reject | reject |
| Too many positional overrides | **accept** | reject | reject | reject |
| Same parameter overridden twice | **accept** | reject | reject | reject |
| String into `int unsigned` parameter | accept | accept + warning | accept | accept |
| Positive control, legal string override | accept | accept | accept | accept |

The string-into-integer row is probably legal SV (inferred), so accepting it isn't scored as a defect. Struct-select reproducers D1-D3 (`docs/SYNLIG_STRUCT_SELECT_AINF.md`) give correct values on xezim and Verilator; this is no evidence about Synlig.

### Can xezim's misses be fixed? (source read, nothing built)

| Miss | Location | Assessment (effort inferred) |
|---|---|---|
| Duplicate named override | `xezim-parser/src/strict_check.rs` ~268 | Small: seen-set, hours |
| Excess positional | Same pass, or `src/elaborate.rs` ~35346 | Small: count check, hours; must count body parameters right |
| Use before declare, read | `src/elaborate.rs:7137` | **Deliberate omission:** the code flags writes only, as its reference simulator is said to tolerate reads "irregularly". Opt-in flag recommended |

All belong in the separate `xezim-core` repo, so upstreaming is the only sensible long-term route.

## 3. cocotb (measured)

| Setup | Trivial DUT | `test_gpio` | Other |
|---|---|---|---|
| Stock cocotb 1.9.2 | **FATAL** `We are calling up again`, no `results.xml` | **FATAL** | |
| 1.9.2 + throwaway shim | 10 pass, both fail controls report FAIL | 18/18, sim time per test identical to Verilator; RTL mutant caught | `test_command_queue` 3/3, pyuvm smoke 4/4, `test_mbist_soc_slice` **2/3** |
| cocotb 2.0.1, no shim | 3 pass, fail control reports FAIL | Not run | `test_functional_path_and_no_fault_run` same failure as shim |

- Trigger: `cbValueChange` delivered while Python is inside `vpi_put_value`, for example a Python-driven clock. Timer-only tests and HDL-generated clocks pass.
- **Which side violates the VPI contract is not established.** cocotb 2 tolerates it, so it isn't a blanket xezim failure.
- The shim is a byte-patched copy of cocotb's VPI library plus `LD_PRELOAD`. Not acceptable for production.
- Project cannot simply move to cocotb 2: `requirements.txt:9` records that 2.x removed the `units=` keyword used throughout `tb/`. Migration size not measured.
- Throughput: `test_gpio` on xezim ~1.5 s end to end, no build. Verilator ~25 s build, test body 1.16 s vs xezim 1.25-1.37 s. **Unit-suite only; long-run throughput unmeasured.**

## 4. Silent miscompile (measured, reproduced twice independently)

```systemverilog
function automatic logic f(input logic [7:0] a); return a == 8'h40; endfunction
logic [7:0] x = 8'h40;  logic one = 1, zero = 0;
wire a = ~f(x) || zero;   // correct 0, xezim 0.11.4 gives 1
wire b = ~f(x) && one;    // correct 0, xezim 0.11.4 gives 1
```

| Form | xezim |
|---|---|
| `~f(x) \|\| y`, `~f(x) && y` (wire, `always_comb`, NBA) | **wrong** (`&&` measured on wire only) |
| `~f(x)` alone, `~fx \|\| y` (no call), `!f(x) \|\| y`, `~f(x) \| y` | right |
| `if (~f(x))`, `~f(x) ? a : b`, `1'(~f(x)) \|\| y` | right |
| Same in `initial`, blocking | right |

- Verilator gives correct results. `XEZIM_TWO_STATE=0`, `XEZIM_JIT=0`, `XEZIM_INIT_ZERO=1` don't change it.
- Inferred mechanism, source not traced: `~` widened in logical-operand context, making the result always nonzero.
- **This RTL hits it:** `rtl/soc/sram_controller.sv:253-254, 647-648, 825-826`, the only `~call(...)` sites in `rtl/`. On xezim a legal SRAM write returns SLVERR. **Not an RTL bug** on this evidence: Verilator correct, and the RTL is legal.
- It shows why xezim can't be sole evidence: a similar miscompile that hides a fault instead of raising one would pass silently. Other forms were not swept.

## 5. Slang as use-before-declare check (measured)

Gap: Verilator and sv2v accept use-before-declare, while VCS and Xcelium reject it (reported), and neither runs in CI. `pyslang==11.0.0` is **already pinned** in `requirements.txt` and used by the blocking `check_upf.py` gate.

| Check | Result |
|---|---|
| Negative controls | Every illegal case rejected; legal cases accepted (section 2) |
| `soc_top` default (396 instances, 84 unique modules), `-DFPGA` | 0 errors, 0 warnings |
| `rv32i_cpu_top`, `gpu_top` default | 0 errors, 0 warnings |
| `soc_top` Sky130 + ASAP7 `__pnr__` arms | 0 errors with `--ignore-unknown-modules` |
| Seeded use-before-declare: `soc_top`, `gpio_controller`, `rv32i_regfile` | All 3 caught, default arm; `soc_top` also on Sky130 arm |

Limits:
- **`--ignore-unknown-modules` hides missing modules** (measured: missing-module control exits 0). Macro arms need it because macro models aren't in the file lists. Use it only there, or add macro stubs.
- Testbench code wasn't checked. Default warning set only; stricter `-Wextra` not evaluated.
- This section reports the trial. The gate that followed is `tools/verif/check_elab_strict.py`, clean on its 6 arms: 3 defaults, FPGA with `rtl/fpga/*.sv`, Sky130 and ASAP7 `__pnr__`.

## 6. Differentiators (measured)

| Item | Result |
|---|---|
| **Sky130 functional GLS** | Committed `rv32i_cpu_top` netlist: `x4=0x0c`, BEQ taken. **Control:** July Synlig netlist (`995c487`): `x4=0x30`, BEQ not taken. ~14 s, 2.9 GB. 2 of 6 programs; no 31-register matrix |
| **SDF** | **No valid result.** No SDF exists for the committed netlist. On a different on-disk netlist/SDF pair, xezim annotated 0 signals and left 30,420 timing-check entries unmatched; cause unknown |
| **X-propagation** | 10/10 probes match 4-state LRM expectation (no commercial reference available). Verilator is 2-state; with `rand+reset+2`, seed 7 takes the opposite `if` branch. `XEZIM_INIT_ZERO=1` zeroes uninitialised memory but leaves scalar `logic` at X |
| **UPF** | Small DUT: clamp and corruption occur under `--upf`, neither without. `phase5_soc.upf` parses and binds on `soc_top`, but all 4 domains show "always on", so **no clamp exercised**. Wrong supply path logs "unknown supply" and proceeds |
| **Metastability / CDC** | Nothing documented. Toy `$setuphold` + notifier gives X on violation; `+notimingcheck` removes it |

## 7. Pros and cons per option

| Option | Pros | Cons | Best role |
|---|---|---|---|
| **Verilator** | Fast build-once runs, in CI, mature, 896-test floor | 2-state hides X, accepts use-before-declare, no SDF, zero-delay CDC | Primary, unchanged |
| **VCS** | 4-state, full SV, 872/0/46 (reported), coverage works | Licensed, not in CI, not on this host | Periodic cross-check |
| **Xcelium** | Same; fastest reported (~6 min SoC); found `dft_clk_switch` race | Licensed; no `imc` for coverage | Periodic cross-check |
| **xezim** | Free, 4-state event-driven, CI-capable, sub-second elaboration, no build, GLS + UPF + X on one command | Silent miscompile above; cocotb 1.9.2 blocked; 8 months old, one dominant author; conflicting perf and sv-tests claims (below); no merge tool, FSM or condition coverage; no Liberty | Local cross-check only |
| **Icarus** | Free, 4-state | Older SV; repo memory forbids it; unused by any workflow | Remove |
| **Yosys `sim`** | Race-free cycle model, proved useful in `u99` | Niche; netlist only | Keep for GLS triage |
| **sv2v + Yosys** | Sky130 fabric flow | Silent on missing modules; slow on SoC (yosys ~10 min) | Unchanged, synthesis only |
| **Synlig** | CPU macro baseline | Proven silent struct-select defects | Guarded, per existing gates |
| **pyslang** | Strictest measured, fastest, already pinned | Elaboration only; `--ignore-unknown-modules` trap | **Blocking CI gate** (`lvdk`) |
| **SpyGlass / HAL** | Deep lint | Local only; CDC/RDC core rules not run | Unchanged |

Xezim claims not supported by this work: README near-parity with commercial sim vs `NOTES.md:3288` "4-5x faster" reference; README sv-tests 99.0 % (0.11.0) vs checked-in 91.3 % (0.8.1); README "keep warm cache on" vs `--help` "EXPERIMENTAL, off by default"; `Cargo.toml` "MIT OR Apache-2.0" vs `LICENSE` Apache-2.0.

## 8. Improvement areas

**This repo (independent of xezim):**
1. Pyslang strict-elaboration gate (section 5): done, bead `lvdk`. Closes the use-before-declare CI gap.
2. `uv.lock` pins cocotb 2.0.1 while `requirements.txt` says `<2.0`.
3. `sim/Makefile:90-91, 124-125` list `mem_collar.sv` and `mbist_ctrl.sv` twice; yosys fails on sv2v output unless de-duplicated (those two lists may serve different targets: check before editing).
4. Stale docs: `docs/CI_CD_WORKFLOW.md:533` suggests Icarus; `docs/verification/VERIFICATION_PLAN.md:402` says "Verilator + SDF", which is not implemented. Icarus remains in `flake.nix:203` + `tb/cocotb/cpu/Makefile:101`.
5. No free 4-state simulation in CI; X and race bugs surface only on non-CI proprietary runs. No clean solution today: xezim is the candidate, once fixed.
6. No local Verilator wall-clock baseline. CI timeouts aren't measured durations.
7. Simulator choice hard-coded in `sim_portability.mk:56` and `run_cocotb_targets.py:152`; adding any simulator touches both.
8. Plan a cocotb 2 migration: `units=` was the recorded blocker, and it would also remove the 1.9.2 blocker here.

**Xezim, if pursued (upstream, needs approval to file):** fix section 4; settle cocotb 1.x re-entrancy; add cocotb to its CI (20 pytest cases currently not in `cargo test`); publish current sv-tests data + a controlled benchmark; add duplicate/excess override checks and opt-in read check; report SDF mismatches clearly.

## 9. Recommendation and open decisions

| Role | Recommendation |
|---|---|
| cocotb regression / CI | **Not now.** Re-check after section 4 is fixed and either cocotb blocker clears |
| Local GLS and X cross-check | **Allowed as cross-check only**, with a control able to fail. Disagreements are triaged, not trusted |
| Compile / elaboration check | **Use pyslang instead** |

Open human decisions:
1. **Decided:** pyslang gate added, blocking, on 6 arms (`tools/verif/check_elab_strict.py`, bead `lvdk`).
2. **Done:** both reports filed upstream on 2026-11-02, after both reproduced on git `0f4d2fcf`: the section 4 miscompile as [aionhw/xezim#810](https://github.com/aionhw/xezim/issues/810) and the cocotb 1.9.2 abort as [#811](https://github.com/aionhw/xezim/issues/811) (bead `gxg0`).
3. **Deferred:** xezim-core prototype, revisit after upstream responds (bead `1ljh`).
4. **Deferred:** Phase 3, until the section 4 miscompile is fixed and a cocotb route exists (bead `9xn3`).

## 10. What was NOT verified

- Full regression, SoC-scale cocotb suites, long-run throughput, memory on long runs.
- Any cocotb 2 run of `test_gpio` or a pyuvm suite; size of cocotb 2 migration.
- VCS/Xcelium on these probes (use-before-declare confirmed by user, logs not seen here).
- SDF on the committed macro; timing GLS of any kind; 4 of 6 GLS programs; register matrix; Verilator GLS timing.
- Clamp and corruption on `soc_top`; X state on `soc_top` after reset beyond a sampled testbench (26 X-warn lines on MBIST, collar, macro signals; not triaged).
- Root cause of section 4 and other expression forms; shim correctness beyond these suites; seeds other than 1234.
- Any xezim source fix: section 2 fix assessments are from reading code.
- Xezim's own regression suite wasn't run; its claimed C906/C910/Ibex results weren't reproduced.
