# VCS code coverage and hole review (Step 4, report-only)

Environment setup and the uninstrumented VCS/Xcelium regression flow: [PROPRIETARY_SIM_FLOW.md](PROPRIETARY_SIM_FLOW.md).

Measured 2026-10-23/24 on branch `feature/commercial-sims`, Synopsys VCS Y-2026.03 + URG Y-2026.03.
Scope decision (user): **VCS only**. Xcelium coverage was not collected: `imc` is not installed on this host, so a
collected Xcelium database could not be merged or reported. `COVERAGE=1` under `SIM=xcelium` is refused with a clear
message by `tb/cocotb/common/sim_portability.mk`.

Mode: `coverage_mode: report_only` (verification-orchestrator Behaviour Rule 14). This pass collects and reviews.
It writes **no** test, constraint or waiver, and takes **no** coverage loop-back (functional < 100 % to
`constrained_random`, line < 95 % to `directed_tests`). Every "proposed test" and "proposed waiver" below is a
proposal for a human to accept or reject. Coverage below target is a WARN (`failure_class: coverage_gap`) and never
sets sign-off.

## 1. How to run

```bash
source tools/eda/sim_env.sh                       # VCS_HOME, licence, .venv-eda (python 3.11 + cocotb 1.9.2)

# whole thing: instrumented SoC regression, instrumented CPU/cache/GPU regression, urg merge + report
python3 tools/eda/vcs_coverage.py run --area all --root sim_build_cov --jobs 3

# or per area, through the Makefiles (SIM=vcs only so the soc Makefile parses without a verilator binary)
make -C tb/cocotb/soc SIM=vcs soc_coverage_vcs     # soc_all_ci job list, --jobs $(VCS_COV_JOBS)=3
make -C sim coverage_cpu_gpu_vcs                   # CPU / Phase 3 caches / Phase 4 GPU rollup, serial

# re-merge only (no simulation), e.g. after adding vdbs
python3 tools/eda/vcs_coverage.py merge --root sim_build_cov --out sim_build_cov/report/all

# re-slice a merged report into per-module scores and a machine-readable hole list
python3 tools/eda/vcs_cov_holes.py sim_build_cov/report/all/urgReport --json holes_all.json
```

Outputs under `sim_build_cov/` (gitignored, not committed): `{soc,cpu}/vcs/<chain>/<build>/simv.vdb` (one per build,
one `-cm_name` test per simulation), `report/{soc,cpu,all}/urgReport/{dashboard,modlist,hierarchy,modinfo,tests,asserts}.txt`
(+ `.html`), `report/<area>/urg.log`, `report/<area>/merge_summary.json`.
`modinfo.txt` is the per-module detail (uncovered lines, branch arms, condition rows, FSM arcs, untoggled ports).

### What `COVERAGE=1 SIM=vcs` does (tb/cocotb/common/sim_portability.mk)

| Aspect | Implementation |
| :----- | :------------- |
| Metrics | compile `-cm line+cond+fsm+tgl+branch+assert`; run with the same `-cm` (`VCS_COV_METRICS` overrides) |
| Scope | `-cm_hier <cfg>` with a **leading `+filelist`** rule, so everything not listed is excluded **at compile time**: the list is the `rtl/` files in this build's `VERILOG_SOURCES` plus the `rtl/` files reachable through the `-I`/`-y` library lookup. Testbench wrappers (`tb_*`), cocotb glue and the behavioural models under `sim/` are not listed. `-cm_libs yv` so a module found only through `-y` (e.g. `rv32i_clock_gate.sv`) is instrumented. The list is content-addressed (`vcs_cov_scope_<hash>.f/.cfg` under `COV_DIR`), so builds with different sources never race on one file. `rtl/fpga/` (the `FPGA=1` variant) is not part of these regressions |
| One database per build | the compile writes the static design into the build's own `simv.vdb`; every simulation of that build adds a test to it (`-cm_dir <SIM_BUILD>/simv.vdb`) |
| Unique test names | `-cm_name <build dir>__<MODULE>[__tc<TESTCASE hash>]__<hash of abs build dir>`. Suites that share a build dir (the `tb_soc_top` chains) therefore never overwrite each other, and names stay unique when vdbs from different `SIM_BUILD_ROOT`s are merged. Checked: 80 SoC + 34 CPU `results__*.xml` files = 80 + 34 tests recorded in the vdbs = 114 = urg `Number of tests` |
| Separate build dirs | `_cov` suffix on every `SIM_BUILD`, and the coverage flags are in the content key, so an instrumented `simv` can never be reused by a plain run (or the reverse) |
| Verilator / Xcelium | the Verilator branch is untouched; `COVERAGE=1` with `SIM=xcelium` is an `$(error ...)` explaining why |
| Merge | one `urg -lca -dir <all vdbs> -flex_merge modules -dbname ... -report ... -format both`. **Why `-flex_merge modules`:** the suites have different top-level testbenches, so the databases have different base designs; a plain `urg -dir a b` keeps only the first database's design and silently drops every instance it does not contain (observed: merging `tb_cdc_gray_fifo` + `tb_axi4_crossbar` produced a report with no crossbar). **It is an LCA (limited customer availability) URG feature and needs `-lca`**; if a future VCS drops it, merge per top-level or use `-map` |
| Empty-report guard | `vcs_coverage.py merge` fails if the dashboard "Total Coverage Summary" row is all `--` (nothing instrumented, or scope excluded everything), and warns if urg's `Number of tests` differs from the number recorded in the vdbs |

### Instrumentation did not change pass/fail

| Regression | Uninstrumented VCS (Step 3) | Instrumented (this run) |
| :--------- | :-------------------------- | :---------------------- |
| SoC `soc_all_ci` (46 chains) | 918 tests, 0 fail, 46 skip = **872 pass** | 918 tests, 0 fail, 46 skip = **872 pass**; 46/46 chains PASS |
| CPU / caches / GPU (34 chains) | **265 pass** | **265 pass**; 34/34 chains PASS |

Verdicts come only from the `results__*.xml` files (cocotb 1.x `make` exits 0 on failure).
Wall clock, `--jobs 3` for SoC and serial for `sim/`: SoC 1090 s (uninstrumented 842 s), CPU 316 s (214 s), urg merges
5 s + 1 s + 12 s. Total about 24 min instrumented against about 18 min plain (about 1.4x).
Disk: `sim_build_cov/` 616 MB (SoC 345 MB, CPU 147 MB, reports 125 MB); the 100 `simv.vdb` databases themselves total
20.6 MB; the merged report directories are 56 MB (soc), 6.6 MB (cpu), 61 MB (all) of which most is HTML.

`make -n` parity of the Verilator path (stubbed `verilator`, `cocotb-config` from the venv): 30 targets (soc, cpu and
`sim/`, including `COVERAGE=1` on `soc gpio` and `sim icache`, `soc_all_ci`, `soc_ci_shard`, `print-sim-build`) captured
at HEAD before and in the working tree after; `cmp -s` on every pair: **30 of 30 byte-identical**. The new targets are
appended at the end of `tb/cocotb/soc/Makefile` and `sim/Makefile`, so no earlier line number moved.

## 2. Results

`ASSERT` is `--` everywhere: `rtl/` contains no SVA (`assert property`/`cover property`); the only text match is a
comment. A `--` in any column means the metric has no objects in that module (not 0 %).

### 2.1 Overall

| View | Tests merged | SCORE | LINE | COND | TOGGLE | FSM | BRANCH |
| :--- | -----------: | ----: | ---: | ---: | -----: | --: | -----: |
| **Module definitions, SoC + CPU/GPU (`all`)** | 114 | 82.80 | 79.23 | 86.51 | 77.03 | 76.94 | 94.31 |
| Module definitions, SoC only | 80 | 78.16 | 77.84 | 81.80 | 69.66 | 74.44 | 87.05 |
| Module definitions, CPU/cache/GPU only | 34 | 83.80 | 94.06 | 85.60 | 79.43 | 67.42 | 92.49 |
| Instance hierarchy (dashboard), all | 114 | 67.40 | 79.07 | 71.42 | 55.04 | 54.39 | 77.09 |
| Instance hierarchy (dashboard), SoC | 80 | 66.30 | 78.47 | 70.04 | 53.06 | 53.47 | 76.48 |
| Instance hierarchy (dashboard), CPU/GPU | 34 | 74.19 | 86.60 | 79.60 | 61.59 | 61.94 | 81.20 |

How to read the two views. The **module-definition** view merges all instances of a module (the same "hit if any
instance hit it" rule as `tools/verif/coverage_report.py`), and counts every parameter shape (`( parameter ... )`
variant) as its own definition, so a rarely-used shape that one small test exercises pulls the total down. The
**instance-hierarchy** view scores each top-level testbench tree separately: a block seen only through a boot test inside
`tb_soc_top` (for example `tb_soc_pll.u_soc.u_pmu` at 50.5 %, against 83.7 % for the module) is scored on that instance alone, which is why it is
much lower. Neither is a sign-off number. The per-module rows below are the module-level merged scores (top row of each
module in `modlist.txt`).

Unweighted summary of the 84 `rtl/` modules (module-level, merged shapes; modules without objects for a metric are not
counted in it):

| Metric | Modules with objects | Mean | Median | Min | Modules >= 95 % |
| :----- | -------------------: | ---: | -----: | --: | --------------: |
| Line | 72 | 98.1 | 100.0 | 80.0 (`soc_top`) | 65 |
| Cond | 71 | 93.0 | 96.5 | 46.2 (`rv32i_pipeline_ex1b`) | 40 |
| Toggle | 84 | 84.4 | 89.8 | 23.2 (`warp_scheduler`) | 36 |
| FSM (transitions) | 22 | 81.2 | 81.5 | 38.5 (`rv32i_cpu_top`) | 7 |
| Branch | 74 | 97.0 | 100.0 | 75.0 (`rv32i_pipeline_ex1b`) | 57 |

The sharp reading: **statement and branch coverage are high (median 100 %); the gaps are FSM transitions, condition
rows and toggle.** Every FSM *state* is reached (state coverage 100 % wherever an FSM was extracted); what is missing
are 76 transitions, and 58 of them are "reset asserted while the FSM is busy" arcs (section 3, H1, H2, H6, H14).

Hole totals (never hit in any shape that lists the point): 69 lines, 61 branch arms, 585 condition rows, 76 FSM arcs,
1 860 never-toggled port/signal rows (rows are bit ranges, not bits). 38 of the 69 lines are `default:` arms, and 33 of
those already carry a category-b waiver in `tools/verif/coverage_waivers.txt` (anchor-text match), written for Verilator; **VCS reads neither that file nor the 11
`/* verilator coverage_off */` pragmas in `rtl/`**, so those points reappear here.

### 2.2 Per-module scores

Columns are urg's module-level percentages. `Shapes` = number of parameter shapes merged. The last column counts points
never hit in any shape that lists them: line / branch / cond rows / FSM arcs (toggle is reported separately, section 4).

**`rtl/cpu/`**

| Module | Score | Line | Cond | Toggle | FSM | Branch | Shapes | Uncovered (line / branch / cond / FSM arcs) |
| :----- | ----: | ---: | ---: | -----: | --: | -----: | -----: | :------------------------------------------ |
| `rv32i_alu` | 100.0 | 100.0 | 100.0 | 100.0 | -- | 100.0 | 1 | 0 / 0 / 0 / 0 |
| `rv32i_branch_comp` | 100.0 | 100.0 | 100.0 | 100.0 | -- | 100.0 | 1 | 0 / 0 / 0 / 0 |
| `rv32i_core` | 92.3 | 100.0 | 93.3 | 76.1 | -- | 100.0 | 1 | 0 / 0 / 3 / 0 |
| `rv32i_cpu_top` | 75.7 | 100.0 | 87.5 | 56.8 | 38.5 | 95.7 | 1 | 0 / 3 / 15 / 16 |
| `rv32i_csr_file` | 87.1 | 97.1 | 90.2 | 66.8 | -- | 94.1 | 1 | 6 / 6 / 12 / 0 |
| `rv32i_decode` | 97.8 | 98.1 | 100.0 | 98.2 | -- | 95.0 | 1 | 3 / 3 / 0 / 0 |
| `rv32i_forwarding_unit` | 99.7 | 100.0 | 100.0 | 98.8 | -- | 100.0 | 1 | 0 / 0 / 0 / 0 |
| `rv32i_hazard_unit` | 97.8 | 100.0 | 91.2 | 100.0 | -- | 100.0 | 1 | 0 / 0 / 20 / 0 |
| `rv32i_imm_gen` | 92.1 | 88.9 | -- | 100.0 | -- | 87.5 | 1 | 1 / 1 / 0 / 0 |
| `rv32i_interrupt_ctrl` | 79.9 | 100.0 | 90.9 | 28.6 | -- | 100.0 | 1 | 0 / 0 / 1 / 0 |
| `rv32i_pipeline_ex` | 91.8 | 100.0 | 87.5 | 79.7 | -- | 100.0 | 1 | 0 / 0 / 1 / 0 |
| `rv32i_pipeline_ex1b` | 70.1 | 82.5 | 46.1 | 76.7 | -- | 75.0 | 1 | 7 / 1 / 14 / 0 |
| `rv32i_pipeline_ex1c` | 85.5 | 95.9 | 78.5 | 77.8 | -- | 90.0 | 1 | 2 / 2 / 14 / 0 |
| `rv32i_pipeline_ex2` | 95.6 | 100.0 | 100.0 | 82.5 | -- | 100.0 | 1 | 0 / 0 / 0 / 0 |
| `rv32i_pipeline_id` | 99.7 | 100.0 | 100.0 | 99.0 | -- | 100.0 | 1 | 0 / 0 / 0 / 0 |
| `rv32i_pipeline_if` | 92.8 | 100.0 | 87.5 | 83.6 | -- | 100.0 | 1 | 0 / 0 / 5 / 0 |
| `rv32i_pipeline_mem` | 88.6 | 95.6 | 87.5 | 77.7 | -- | 93.5 | 1 | 2 / 2 / 6 / 0 |
| `rv32i_pipeline_wb` | 89.0 | 100.0 | 71.4 | 84.7 | -- | 100.0 | 1 | 0 / 0 / 4 / 0 |
| `rv32i_regfile` | 99.9 | 100.0 | 100.0 | 99.5 | -- | 100.0 | 1 | 0 / 0 / 0 / 0 |

**`rtl/gpu/`**

| Module | Score | Line | Cond | Toggle | FSM | Branch | Shapes | Uncovered (line / branch / cond / FSM arcs) |
| :----- | ----: | ---: | ---: | -----: | --: | -----: | -----: | :------------------------------------------ |
| `gpu_command_queue` | 90.7 | 100.0 | 100.0 | 62.6 | -- | 100.0 | 1 | 0 / 0 / 0 / 0 |
| `gpu_compute_unit` | 95.2 | 99.2 | 91.0 | 92.5 | -- | 98.0 | 1 | 1 / 1 / 8 / 0 |
| `gpu_memory_unit` | 99.9 | 100.0 | 100.0 | 99.7 | -- | 100.0 | 1 | 0 / 0 / 0 / 0 |
| `gpu_top` | 95.2 | 99.3 | 88.6 | 89.4 | 100.0 | 98.9 | 1 | 1 / 1 / 10 / 0 |
| `memory_coalescer` | 92.3 | 98.3 | 100.0 | 99.8 | 68.8 | 94.7 | 1 | 1 / 1 / 0 / 5 |
| `shared_memory` | 97.7 | 100.0 | 90.9 | 100.0 | -- | 100.0 | 1 | 0 / 0 / 1 / 0 |
| `vector_alu` | 96.7 | 100.0 | 87.5 | 99.4 | -- | 100.0 | 1 | 0 / 0 / 4 / 0 |
| `vector_register_file` | 99.9 | 100.0 | 100.0 | 99.8 | -- | 100.0 | 1 | 0 / 0 / 0 / 0 |
| `warp_scheduler` | 80.8 | 100.0 | 100.0 | 23.2 | -- | 100.0 | 1 | 0 / 0 / 0 / 0 |

**`rtl/mem/`**

| Module | Score | Line | Cond | Toggle | FSM | Branch | Shapes | Uncovered (line / branch / cond / FSM arcs) |
| :----- | ----: | ---: | ---: | -----: | --: | -----: | -----: | :------------------------------------------ |
| `rv32i_cache_arbiter` | 91.5 | 97.4 | 91.4 | 73.8 | 100.0 | 94.7 | 1 | 1 / 1 / 7 / 0 |
| `rv32i_clock_gate` | 100.0 | 100.0 | 100.0 | 100.0 | -- | 100.0 | 1 | 0 / 0 / 0 / 0 |
| `rv32i_dcache` | 92.1 | 98.7 | 92.2 | 76.5 | 96.2 | 97.0 | 1 | 4 / 4 / 19 / 1 |
| `rv32i_icache` | 92.8 | 98.3 | 85.0 | 87.3 | 100.0 | 93.6 | 1 | 2 / 3 / 19 / 0 |

**`rtl/npu/`**

| Module | Score | Line | Cond | Toggle | FSM | Branch | Shapes | Uncovered (line / branch / cond / FSM arcs) |
| :----- | ----: | ---: | ---: | -----: | --: | -----: | -----: | :------------------------------------------ |
| `npu_mac_array` | 100.0 | 100.0 | -- | 100.0 | -- | 100.0 | 1 | 0 / 0 / 0 / 0 |
| `npu_top` | 91.0 | 100.0 | 100.0 | 63.8 | -- | 100.0 | 3 | 0 / 0 / 0 / 0 |
| `npu_weight_mem` | 79.6 | 100.0 | 70.0 | 73.5 | -- | 75.0 | 2 | 0 / 0 / 0 / 0 |

**`rtl/periph/`**

| Module | Score | Line | Cond | Toggle | FSM | Branch | Shapes | Uncovered (line / branch / cond / FSM arcs) |
| :----- | ----: | ---: | ---: | -----: | --: | -----: | -----: | :------------------------------------------ |
| `aes128_core` | 97.7 | 100.0 | 91.2 | 99.9 | -- | 99.8 | 2 | 0 / 0 / 1 / 0 |
| `crypto_accel` | 91.2 | 100.0 | 84.2 | 71.7 | 100.0 | 100.0 | 5 | 0 / 0 / 2 / 0 |
| `dma_engine` | 82.7 | 98.7 | 96.5 | 56.0 | 66.7 | 95.7 | 1 | 2 / 2 / 2 / 7 |
| `gpio_controller` | 99.9 | 100.0 | 100.0 | 99.6 | -- | 100.0 | 1 | 0 / 0 / 0 / 0 |
| `i2c_bit_engine` | 95.5 | 100.0 | 96.3 | 97.6 | 83.8 | 100.0 | 1 | 0 / 0 / 5 / 6 |
| `i2c_controller` | 89.6 | 100.0 | 95.3 | 94.5 | 62.5 | 95.7 | 1 | 0 / 2 / 7 / 3 |
| `interrupt_controller` | 87.4 | 100.0 | -- | 74.9 | -- | -- | 2 | 0 / 0 / 0 / 0 |
| `pwm_controller` | 98.7 | 100.0 | 95.6 | 99.1 | -- | 100.0 | 1 | 0 / 0 / 2 / 0 |
| `sha256_core` | 99.5 | 99.2 | 100.0 | 100.0 | 100.0 | 98.6 | 1 | 1 / 1 / 0 / 0 |
| `spi_controller` | 96.2 | 98.7 | 97.4 | 91.3 | -- | 97.3 | 1 | 1 / 1 / 2 / 0 |
| `timer` | 97.8 | 100.0 | 100.0 | 91.3 | -- | 100.0 | 1 | 0 / 0 / 0 / 0 |
| `trng` | 98.6 | 100.0 | 95.3 | 99.2 | -- | 100.0 | 1 | 0 / 0 / 4 / 0 |
| `trng_lfsr_entropy` | 100.0 | 100.0 | 100.0 | 100.0 | -- | 100.0 | 1 | 0 / 0 / 0 / 0 |
| `uart_controller` | 92.0 | 98.6 | 97.4 | 91.6 | 75.0 | 97.5 | 1 | 2 / 2 / 4 / 3 |
| `watchdog_timer` | 99.1 | 100.0 | 97.0 | 99.4 | -- | 100.0 | 1 | 0 / 0 / 2 / 0 |

**`rtl/soc/`**

| Module | Score | Line | Cond | Toggle | FSM | Branch | Shapes | Uncovered (line / branch / cond / FSM arcs) |
| :----- | ----: | ---: | ---: | -----: | --: | -----: | -----: | :------------------------------------------ |
| `apb4_register_bank` | 88.8 | 90.5 | 100.0 | 82.8 | -- | 81.8 | 3 | 2 / 2 / 0 / 0 |
| `apb_cdc_bridge` | 97.0 | 100.0 | 93.1 | 100.0 | 91.7 | 100.0 | 1 | 0 / 0 / 4 / 1 |
| `apb_interconnect` | 91.1 | 100.0 | -- | 73.4 | -- | 100.0 | 5 | 0 / 0 / 0 / 0 |
| `async_axi_fifo` | 90.4 | -- | 100.0 | 80.7 | -- | -- | 1 | 0 / 0 / 0 / 0 |
| `axi4_crossbar` | 74.9 | 98.1 | -- | 60.2 | 66.4 | -- | 2 | 4 / 0 / 0 / 12 |
| `axi4_to_axilite` | 89.3 | 97.1 | 87.5 | 80.6 | 87.5 | 93.5 | 1 | 2 / 2 / 11 / 2 |
| `axi_lite_interconnect` | 85.5 | 98.1 | 100.0 | 65.1 | 70.0 | 94.3 | 2 | 2 / 2 / 0 / 3 |
| `axi_lite_register_bank` | 92.3 | 92.0 | 94.7 | 96.4 | -- | 86.2 | 2 | 4 / 4 / 2 / 0 |
| `axil_to_apb` | 91.0 | 96.7 | 98.7 | 90.3 | 75.0 | 94.4 | 1 | 2 / 2 / 1 / 2 |
| `axilite_to_axi4` | 85.5 | 100.0 | 92.9 | 49.0 | -- | 100.0 | 1 | 0 / 0 / 1 / 0 |
| `boot_rom` | 83.9 | 95.0 | 79.4 | 81.4 | 75.0 | 88.9 | 1 | 2 / 2 / 7 / 1 |
| `pmu` | 83.7 | 93.9 | 90.0 | 75.2 | 65.6 | 93.7 | 2 | 5 / 3 / 8 / 11 |
| `soc_bus` | 62.1 | -- | -- | 62.1 | -- | -- | 1 | 0 / 0 / 0 / 0 |
| `soc_top` | 83.0 | 80.0 | 97.7 | 57.3 | -- | 96.9 | 1 | 1 / 1 / 1 / 0 |
| `sram_controller` | 80.1 | 84.5 | 77.8 | 73.7 | 79.2 | 85.3 | 3 | 7 / 5 / 335 / 1 |

**`rtl/soc/cdc/`**

| Module | Score | Line | Cond | Toggle | FSM | Branch | Shapes | Uncovered (line / branch / cond / FSM arcs) |
| :----- | ----: | ---: | ---: | -----: | --: | -----: | -----: | :------------------------------------------ |
| `cdc_gray_fifo` | 99.1 | 100.0 | 100.0 | 96.5 | -- | 100.0 | 8 | 0 / 0 / 0 / 0 |
| `cdc_reset_sync` | 100.0 | 100.0 | 100.0 | 100.0 | -- | 100.0 | 1 | 0 / 0 / 0 / 0 |
| `cdc_sync` | 100.0 | 100.0 | -- | 100.0 | -- | 100.0 | 5 | 0 / 0 / 0 / 0 |

**`rtl/soc/dft/`**

| Module | Score | Line | Cond | Toggle | FSM | Branch | Shapes | Uncovered (line / branch / cond / FSM arcs) |
| :----- | ----: | ---: | ---: | -----: | --: | -----: | -----: | :------------------------------------------ |
| `dft_clk_mux` | 100.0 | -- | 100.0 | 100.0 | -- | 100.0 | 1 | 0 / 0 / 0 / 0 |
| `dft_clk_switch` | 100.0 | 100.0 | 100.0 | 100.0 | -- | 100.0 | 1 | 0 / 0 / 0 / 0 |
| `dft_ctrl` | 87.5 | -- | 100.0 | 62.6 | -- | 100.0 | 1 | 0 / 0 / 0 / 0 |
| `dft_ctrl_ports` | 100.0 | -- | -- | 100.0 | -- | -- | 1 | 0 / 0 / 0 / 0 |
| `dft_rst_mux` | 100.0 | -- | 100.0 | 100.0 | -- | 100.0 | 1 | 0 / 0 / 0 / 0 |
| `jtag_tap` | 96.9 | 100.0 | 99.3 | 85.0 | 100.0 | 100.0 | 1 | 0 / 0 / 1 / 0 |
| `mbist_ctl_hold` | 100.0 | 100.0 | -- | 100.0 | -- | 100.0 | 1 | 0 / 0 / 0 / 0 |
| `mbist_ctrl` | 85.1 | 95.4 | 85.0 | 65.4 | 84.6 | 95.0 | 5 | 1 / 1 / 18 / 2 |
| `mbist_status_sync` | 93.4 | 100.0 | -- | 80.1 | -- | 100.0 | 1 | 0 / 0 / 0 / 0 |
| `mbist_xing` | 100.0 | -- | 100.0 | 100.0 | -- | -- | 1 | 0 / 0 / 0 / 0 |
| `mem_collar` | 94.8 | -- | 100.0 | 84.4 | -- | 100.0 | 8 | 0 / 0 / 0 / 0 |
| `soc_mbist` | 56.2 | -- | 66.7 | 45.7 | -- | -- | 2 | 0 / 0 / 1 / 0 |

**`rtl/soc/pll/`**

| Module | Score | Line | Cond | Toggle | FSM | Branch | Shapes | Uncovered (line / branch / cond / FSM arcs) |
| :----- | ----: | ---: | ---: | -----: | --: | -----: | -----: | :------------------------------------------ |
| `pll_apb_regs` | 70.5 | -- | -- | 70.5 | -- | -- | 1 | 0 / 0 / 0 / 0 |
| `pll_clkgen` | 100.0 | -- | -- | 100.0 | -- | -- | 1 | 0 / 0 / 0 / 0 |
| `pll_clkgen_stub` | 100.0 | 100.0 | -- | 100.0 | -- | 100.0 | 1 | 0 / 0 / 0 / 0 |
| `pll_subsystem` | 78.7 | -- | 83.3 | 74.1 | -- | -- | 1 | 0 / 0 / 1 / 0 |

## 3. Ranked hole list (highest risk first)

Ranking key: (1) unvisited FSM states and transitions, (2) error / `default` / DECERR / SLVERR paths, (3) reset, flush and
abort paths, (4) CDC and async FIFO corner cases, (5) PMU timeout, (6) crypto illegal start, (7) NPU KLEN extremes,
(8) DMA error paths, (9) the rest. Within a class, by consequence of a latent bug and then by size. The user's
class order is kept, but note one measured fact that reshapes it: **all FSM states were reached, and 58 of the 76
missing FSM transitions are the reset arm of the state register** (`if (!rst_n) state <= IDLE`, which VCS counts as
an arc from every non-idle state). Classes 1 and 3 therefore overlap; they are listed once, under class 1, and tagged.

Evidence for classes the user asked about, even where the answer is "no hole":

* **PMU timeout (`ISO_ACK_TIMEOUT`, `STATUS[3]`)**: not a hole. `pmu.sv` has no uncovered line in the `g_ack_cpu` wait
  and timeout block; the timeout path is exercised (the suites written for it are `test_pmu.py` and `test_soc_pmu_iso_ack.py`; per-test attribution was not extracted). The remaining `pmu`
  holes are H6 (reset during sequencing) and the waivable items W5.
* **Crypto illegal start / `key_write_rejected`**: not a code-coverage hole. `crypto_accel` line 100 %, branch 100 %,
  FSM 100 %; `aes128_core` line 100 %. Condition rows are in section 6 (caveat C3).
* **NPU KLEN extremes**: not visible to code coverage. `npu_top` line/cond/branch 100 %, and no KLEN bit is among its
  never-toggled signals (every bit toggled both ways). Whether KLEN = 1 and KLEN = 63 are both run is a *functional
  coverage* question; no covergroup exists for the NPU (section 7).
* **CDC and async FIFO full/empty**: `cdc_gray_fifo` line/cond/branch 100 %, toggle 96.5 % (the residual are payload
  bits), so full and empty are exercised. `async_axi_fifo` has no line/branch objects (it is structural) and cond 100 %.
  The CDC holes are in `apb_cdc_bridge` (H7).
* **DMA error paths**: error handling lines are covered (`dma_engine` line 98.7 %, only L394 and a `default:` open).
  The DMA holes are queue depth and one dead branch (H9).

### 3.1 Top 15

| # | Class | Where | Metric | What is missing | PROPOSAL (test or waiver) |
| -: | :---- | :---- | :----- | :-------------- | :------------------------ |
| H1 | FSM arcs, reset in flight | `axi4_crossbar.sv` 352/418/475 (12 arcs: `W_AW`,`W_DATA`,`R_AR`,`DW_DATA` to IDLE, per slave/master); `axi_lite_interconnect.sv` 192/319 (3); `axil_to_apb.sv` 185 (2); `axi4_to_axilite.sv` 160 (2); `boot_rom.sv` 144 (1); `sram_controller.sv` 241 (1) | FSM 22 arcs | hard reset while an AXI/APB transaction is mid-flight. CLAUDE.md already records that a mid-burst CPU reset "can wedge a crossbar slave engine"; this is exactly the untested path | **Test.** One new test per suite (`test_crossbar_errors.py`, `test_axil_interconnect.py`, `test_axil_to_apb.py`, `test_axi4_to_axilite.py`, `test_boot_rom.py`, `test_sram_controller.py`): start a write burst, drop `rst_n` for 2 cycles while the FSM is in each non-idle state (hold AW accepted/W pending; AR accepted/R pending), release, assert no stuck `*valid`/`*ready` and that the next transaction completes. Reset *then* check slave-side state, not just the master view |
| H2 | FSM arcs, reset in flight | `dma_engine.sv` 473 (7: `S_AR`,`S_AW`,`S_B`,`S_CALC`,`S_R`,`S_RDRAIN`,`S_W` to IDLE); `memory_coalescer.sv` 144 (5); `uart_controller.sv` 349/522 (3); `i2c_bit_engine.sv` 523 (6); `rv32i_dcache.sv` 594 (`CS_UNCACHED_WR`); `mbist_ctrl.sv` 339 (`S_INIT`,`S_PAUSE`) | FSM 24 arcs | the same reset-while-busy class for the data movers and serial engines | **Test.** `test_dma.py`: `rst_n` pulse during each DMA state of a 3-descriptor run, then verify descriptor queue empty, `STATUS` idle, no stale AXI `*valid`. `test_memory_coalescer.py`, `test_uart.py` (reset mid-frame TX and RX), `test_i2c.py` (reset mid-byte and mid-STOP), `test_dcache.py` (reset during an uncached write), `test_mbist_ctrl.py` (reset in INIT and PAUSE). Shared helper: `reset_when_state(dut, state)` |
| H3 | Error path (SLVERR/DECERR observed at SoC level) | `soc_bus`/`soc_top` `axil_{dma,gpu}_{bresp,rresp}[1:0]`, `axil_s_{bresp,rresp}`, `apb_m_pslverr`, `bus_mem_bresp[1:0]`; `rv32i_core`/`rv32i_cpu_top`/`rv32i_cache_arbiter` `axi_bresp[0]` | toggle (control) | no non-OKAY response ever crosses the DMA, GPU or APB-ring buses in a SoC run, and `bresp[0]` never toggles on the CPU/cache AXI ports, so **no DECERR/EXOKAY (2'b11/2'b01) *write* response ever reached the CPU master** (SLVERR 2'b10 did, and `rresp` bit 0 does toggle, so read-side DECERR was seen). Unit suites cover the decode-error generation (`axi4_crossbar` line 98 %, `apb_interconnect` line 100 %), the *consumers* at SoC level are untested | **Test.** `test_soc_integration.py`: (a) CPU load and store to an unmapped address, expect the precise load/store-access-fault trap and `mcause`; (b) DMA descriptor with unmapped destination, expect the DMA error status and IRQ; (c) CPU access to an unmapped APB slot, expect `pslverr` to reach `axil_to_apb` and the CPU fault; (d) GPU AXI master read of an unmapped address |
| H4 | Error path, default arm | `rv32i_dcache.sv` 876-877 (uncached read with RRESP != OKAY returns 0 and does not hang) | line 2, branch | uncached read error response never injected | **Test.** `tb/cocotb/mem/test_dcache.py` (`sim dcache`): inject `rresp=SLVERR` and `DECERR` on an uncached (MMIO) read; expect data 0, no stall, `CS_DONE` then IDLE, and the same on the refill path |
| H5 | Flush path | `rv32i_dcache.sv` 621 (`if (dc_flush_i && state_q != CS_IDLE) flush_pending_q <= 1`) | line, branch | CSR `dcache_flush` (0x7C0) issued while a refill/writeback is in progress, so the flush is latched and replayed | **Test.** `test_dcache.py` and `tb/cocotb/cpu/test_csr_access.py`: start a miss to a dirty line, pulse `dc_flush_i` in `CS_REFILL` and in `CS_WRITEBACK`, expect the line flushed after the miss completes and `flush_pending_q` cleared (the sibling `dc_inval_i`-while-busy line L622 is covered) |
| H6 | FSM arcs, reset during power sequencing | `pmu.sv` 509 (11 arcs to `DOM_ON`: `DOM_PD_SAVE`, `DOM_PD_GATE`, `DOM_PU_RST`, `DOM_PU_CLK`, `DOM_PU_RESTORE` for both domains, plus `DOM_PD_ISO` for domain 1; domain 0 is the CPU) | FSM 11 arcs | system reset in the middle of a power-down or power-up sequence | **Test.** `test_pmu.py`: request MODE_CPU_OFF / MODE_IDLE, assert `rst_n_i` in each of the 5 intermediate states, expect both domains back in `DOM_ON` with `clk_en`/`rst_n` at reset values, no stuck isolation. Add a cocotb check that outputs (registered per bead `ktwt`) never glitch on the reset edge |
| H7 | CDC, reset in flight | `apb_cdc_bridge.sv` 551 (`S_DROP` to IDLE under source-domain reset), cond 541 (`ack_s \|\| !req_fwd_q \|\| !m_rst_n_s`, row `0 1 0`), 566/585 (`IDLE && psel && !penable`, row `0 1 1`), 724 (`!req_fwd_q \|\| !m_rst_n_s`, row `1 0`) | FSM 1 arc, cond 4 rows | the bridge already has asymmetric-reset directed tests (`test_reset_asym_s_held_m_free`, `..._staggered_s_then_m`, `..._staggered_m_then_s`, GH #95), so the residue is narrow: source reset landing while the FSM is in `S_DROP`, and `req_fwd_q` dropping with neither an ack nor `m_rst_n_s` low (a destination reset shorter than the synchroniser latency) | **Test.** `test_apb_cdc_bridge.py` with `s_clk != m_clk`: (a) abort a transfer by resetting `m_rst_n`, and assert `s_rst` one cycle later while the source FSM is in `S_DROP`; (b) pulse `m_rst_n` for a single destination cycle (shorter than the 2-FF sync) in the middle of a write and expect either the real response or `pslverr=1`, never a hang |
| H8 | Error path, illegal instruction | `rv32i_decode.sv` 351 (SRLI/SRAI with funct7 other than 0/0x20), 432 (AND with funct7 != 0), `B159` OP_IMM / OP_REG / OP_SYSTEM `default` arms | line 2, branch 3 | illegal encodings of shift-immediate and AND, illegal-opcode defaults | **Test.** `tb/cocotb/cpu/test_decode_corners.py`: add `SRLI/SRAI` with funct7 = 0x01 and 0x40; `AND` with funct7 = 0x20; opcode 0x73 with reserved funct3 = 100. Expect `illegal_instruction` trap, `mepc`/`mtval`. The `default:` arms themselves carry `/* verilator coverage_off */` (fully enumerated), see W6 |
| H9 | DMA | `dma_engine.sv` `q_mem[2]`, `q_mem[3]` (src/dst/len) never toggled; cond 533 (`!q_empty && !halted_q`, row `1 0`); L394 (dead, see W7) | toggle (control) + cond | the 4-entry descriptor queue never holds more than 2 descriptors, so **queue full / wrap / back-pressure is untested**; queue non-empty while halted never seen | **Test.** `test_dma.py`: enqueue 4 descriptors back to back (and a 5th: check the full/overflow behaviour against the spec), halt in the middle, resume, check ordering and that all four complete; vary `len_words` so `q_mem[3].len_words[31:0]` toggles |
| H10 | FSM arcs, debug | `rv32i_cpu_top.sv` 677/682/684/691 (`halt_cause_lat`: 16 arcs among causes 0x1, 0x2, 0x3, 0x4, 0x8) | FSM 16 arcs | halt cause re-latched from a *different* cause: breakpoint 1 after breakpoint 0, EBREAK after step, step after breakpoint, plain halt after a latched cause | **Test.** `tb/cocotb/cpu/test_debug_if.py`: matrix of (previous halt cause) x (next halt reason) over BP0, BP1, step, EBREAK, halt request, reading `DBG_STATUS` after each; this register is the debugger-visible cause |
| H11 | Dead code | `rv32i_pipeline_ex1b.sv` 77-83 (block under `if (!valid \|\| flush_ex_mem)` whose inner condition needs `valid && !flush_ex_mem`) | line 7, cond 46 % | **unreachable by construction**: the inner `if` requires the opposite of the outer one. This is why `ex1b` is the lowest-scoring CPU module (cond 46.2, branch 75.0, line 82.5) | **RTL cleanup** (hand to rtl-design-orchestrator) is the right fix; until then **waiver** (category b, dead code) with that reasoning. A test cannot reach it |
| H12 | Coverage of address space | `sram_controller.sv` 441-444, 465 (per-group write path), toggle `g_stage2_group[n].grp_sel_k` never toggles for many groups (for example n = 11, 15, 30 and 100 to 126) | line 4 (generate instances), toggle | the upper SRAM groups were never written: the write-pipeline group select is only exercised for low addresses | **Test.** `test_sram_controller.py` (both `SRAM_TARGET` points): address sweep writing one word in every 1/N group including the last, read back; plus a write to the highest word and a byte-strobe write there |
| H13 | GPU | `warp_scheduler.sv` toggle 23.2 %: `div_stack[1][*]`, `[0][1..3]` never toggle; `gpu_top.sv` `if_ar_stuck` never asserts (cond 295 row `1 0`) | toggle (control), cond | divergence only ever on warp 0 and only the first stack slot; instruction-fetch stall detector never fires | **Test.** `tb/cocotb/gpu/test_divergence.py`: run the divergence kernel on warps 1..7 and with a taken/not-taken pair per warp; `test_gpu_top.py`: starve the instruction `ARREADY` for > threshold cycles and expect `if_ar_stuck` and the recovery path. The architecture is one-level divergence, so slots 1..3 of warp 0 are a **waiver** (W7b), but warps 1..7 are not |
| H14 | FSM arcs, I2C slave | `i2c_controller.sv` 590 (`SLV_ADDR` to IDLE reset), 608 (`SLV_RD` to `SLV_ADDR`, `SLV_WR` to `SLV_ADDR`: repeated START inside a slave transfer), cond 619/643/647 | FSM 3 arcs, cond 7 rows | loopback-slave handling of a repeated START mid-byte and mid-ACK; this is not a bin of the I2C functional model either (`loopback_op` is only write/read) | **Test.** `test_i2c.py` in CTRL.LOOPBACK: START, address+R, read one byte with master ACK, then repeated START to a write address; and the mirror (write, then repeated START to a read). Add `loopback_rstart` to `i2c_cov.py` so the functional model sees it |
| H15 | PLL enable | `pll_apb_regs.sv`/`pll_subsystem.sv` `pll_enable` never toggles; cond 148 (`rst_n_i & pll_enable`, row `1 0`) | toggle, cond | PLL enable bit is never changed during any SoC run | **Test.** `test_pll_regs.py`/`test_pll_lock.py`: write the enable bit 0 then 1 with reset released, expect the lock indication to drop and rise (the area of the GH #89 `pll_enable` self-brick fix) |

### 3.2 Further holes (ranks 16 onward, grouped)

| Class | Where | Detail | PROPOSAL |
| :---- | :---- | :----- | :------- |
| Reset arms in branch tables | `rv32i_dcache.sv` B593 (reset while `CS_REFILL` / `CS_UNCACHED_RD` / default), `rv32i_icache.sv` B479 (reset in `CS_REFILL`), `rv32i_csr_file.sv` B443 (CSR 0x7C0/0x7C1 with reset), `rv32i_cpu_top.sv` B532 (debug CSR 0x104/0x108/0x10C reset arms), `sha256_core.sv` B201 (`!rst_n \|\| wipe_i`), `sram_controller.sv` B240/B435/B632/B806 | same class as H1/H2 | extend the H1/H2 reset-in-flight tests to the caches, the SHA wipe-during-compress (`crypto`), and the SRAM read/write FSMs |
| Fully enumerated `default` arms | FSM recovery arms (`default: state <= IDLE`): `axi4_crossbar` 376/442/480/519, `axi4_to_axilite` 218/298, `axi_lite_interconnect` 209/335, `axi_lite_register_bank` 174/206, `boot_rom` 170/224, `dma_engine` 638, `gpu_top` 360, `memory_coalescer` 207, `rv32i_cache_arbiter` 138, `rv32i_dcache` 971, `rv32i_icache` 611, `sha256_core` 247, `spi_controller` 460, `sram_controller` 295/678/851, `uart_controller` 381/631; `gpu_compute_unit` 499; `mbist_ctrl` 132 and B102 | state register only ever holds a named encoding | **Waiver W1** |
| CSR file defaults | `rv32i_csr_file.sv` 251/259/286/296/597/609 (`csr_op` values 000/100 never reach the CSR file: the decoder only issues 001-011/101-111) | unreachable by decode | **Waiver W6** (with the decode contract as justification) |
| `rv32i_imm_gen` default | `rv32i_imm_gen.sv` 87 (`imm_fmt` default) | `/* verilator coverage_off */` already on the Verilator side | **Waiver W6** |
| Width-select defaults | `rv32i_pipeline_ex1c.sv` 149/162, `rv32i_pipeline_mem.sv` 73/80 (comment: "unreachable (2-bit sel fully enumerated)") | provably unreachable | **Waiver W6** (already category b in the Verilator file) |
| Elaboration guards | `apb4_register_bank.sv` 61-62, `axi_lite_register_bank.sv` 80-81, `axil_to_apb.sv` 93-94, `soc_top.sv` 408 (`$fatal` on illegal parameters) | an elaboration error aborts the build; unreachable in a passing run | **Waiver W2** |
| Dead / redundant code | `dma_engine.sv` 394 (saturate `beats_raw` to `MAX_BURST_BEATS`: `beats_raw` is already `min2(.., MAX_BURST_BEATS)` so it never exceeds it); `rv32i_icache.sv` 510 (`cancel_wait_r_q`: the source comment says "unused in burst mode but kept for symmetry") | unreachable | **Waiver W7** or RTL cleanup |
| PMU defaults and GPU-domain handshake | `pmu.sv` 494-498 and B429 `default` (output decode of an invalid state), B409/L413/L421 (GPU domain `d=1`: `iso_ack_w` is tied, so the wait-for-ack arms of `DOM_PD_ISO`/`DOM_PU_ISO` are CPU-only), L538 row `0 1` (counter equals the threshold while not waiting: impossible) | by design | **Waiver W5** |
| Tie-offs and constants | `irq_src_i[2]` (TIMER slot tied 0 in `soc_top`, "routing it here too would double-count"), `pready`/`pslverr` of every APB peripheral (tied 1/0, zero-wait-state), constant AXI sideband (`m_arburst`, `m_arsize`, `m_awburst`, `m_awsize`, `m_arid`, `m_awid`, `m_wstrb`, `arprot`, `awprot`), spare address bits (`addr_ext_w[31:10]`) | tied or constant | **Waiver W3/W4** |
| MBIST / DFT observability | `mbist_ctrl.sv` cond 503/521 (per-slot `m0/m1`, `ev_w && !fail_q`: a second failure on an already-failed slot), `soc_mbist.sv` cond 158 (`core_wr_ready_w & cpu_wr_ready_w`, one ready low), `dft_ctrl.sv`/`jtag_tap.sv` `mbist_status_i` bits 0, 3, 16, 28, 31-35, 72, 74-80, 82-83, 86 and 88-93 never toggle | only the pass/done bits of the MBIST status word ever change in SoC-level runs | **Test** in `test_mbist_soc_slice.py`/`test_mbist_tap.py`: inject faults in several slots/memories and read the whole status word through the TAP. Bits above the instantiated slot count are a **waiver W8** (DFT-only) |
| Serial / peripheral conditions | `uart_controller` cond 203/238/459/516 (read of the write-only TX-data address, `tx_pop` while empty, the `sb & sc` majority pair, framing flag already set), `spi_controller` 195/227 (same two as UART), `i2c_controller` 506-512 (push and pop in one cycle), `trng` 268/310/324/325 (run-length reaching the cutoff without a valid sample, flush with word valid, push and pop together), `pwm_controller` 300 (channel enabled with `period == 0`), `watchdog_timer` 260/269 (read of the feed address; feed while not running) | simultaneous push/pop and invalid-feed corners | **Test**, one directed case each in the owning `test_*.py`. Lower risk: all are reachable and peripheral-local |
| Handshake-stall corners | `axi4_to_axilite` conds 172-288, `boot_rom` 150-214, `gpu_compute_unit` 242-423, `gpu_top` 133-387 (`valid && !ready` rows) | a channel stalled by its partner for several cycles | **Test**: run the existing suites with `axil_stall_bfm.py` randomised back-pressure (it exists, `tb/cocotb/soc/axil_stall_bfm.py`) on these ports |
| `soc_top` instance-level | `soc_top.sv` toggle 57.3 % (167 never-toggled rows): AXI-Lite DMA/GPU address and data bits, `bus_mem_*` high address bits | wide buses, see section 4 | no action beyond H3 |

## 4. Toggle coverage: how it was treated

Toggle is the lowest metric (module-definition total 77.0 %, instance view 55.0 %) and the one most dominated by
things that cannot or should not be chased:

* **Wide data and address buses.** VCS reports a bus as untoggled by bit range (`prdata[31:10]`, `awaddr[28:15]`,
  `q_mem[2].src[31:0]`); a random-data test cannot reasonably toggle every bit of a 32-bit address, and the SoC memory
  map leaves the top address bits constant. These rows are **counted in the scores but not listed as holes**.
* **Tied-off and constant ports.** `pready` (tied 1) and `pslverr` (tied 0) never toggle on any APB peripheral (30
  rows); constant AXI sideband (burst, size, len, id, prot, wstrb) 277 rows; `_unused*` signals. Waiver proposals
  W3/W4 below. They are tool artefacts of zero-wait-state, INCR-only, full-strobe design choices, not test gaps.
* **DFT-only ports.** `mbist_status_i`, scan and test-mode ports are exercised only in the DFT suites; where a bit
  exists above the instantiated slot count it is waivable (W8). Where it is a real status field that can be set,
  it is a hole (section 3.2, MBIST / DFT observability).
* **What *was* chased.** Toggle rows on **narrow control signals** (response codes, `*_stuck`, `pll_enable`,
  state-encoding bits, queue slots, `grp_sel_k`, warp-indexed stack slots). Those are H3, H9, H12, H13, H15 above.
  By classification of the 1 860 untoggled rows in the 84 `rtl/` modules: 386 are wide-bus (>= 8 bits) ranges, 277
  AXI sideband/unused, 30 tied `pready`/`pslverr`, and 1 167 are narrower ranges, of which the large majority are
  address low/high bits, debug-CSR mirror bits (`dbg_csr_*`, `mstatus`/`mcause` bits the tests never set) and `pc[1:0]`
  (always 0 on a 4-byte-aligned ISA). I did not walk all 1 167; the ones named in section 3 are the control-flow
  relevant ones.
* The Verilator flow used `--coverage-max-width 256` to keep wide arrays out. VCS has no equivalent switch; arrays
  and memories are not toggle-instrumented by default (`-cm_tgl mda` is off), so multi-dimensional memories such as
  `sram_controller.mem` do not inflate the denominator.

## 5. Proposed waivers (nothing is written; for a human to accept)

Format follows `tools/verif/coverage_waivers.txt` (module, kind, anchor, category b, justification). VCS does not read
that file; the VCS equivalent is an `urg -elfile` exclusion file or `-cm_hier` begin/end blocks, to be generated from the
accepted list so the two flows cannot drift.

| ID | Scope | Justification |
| :-- | :---- | :------------ |
| W1 | FSM `default:` recovery arms (list in 3.2), and the VCS-inferred arcs into them | the state register only holds named encodings in simulation (reset value plus enumerated transitions); reachable only through state corruption. 33 of the 38 `default:` line holes are already waived on the Verilator side (the 5 that are not: `gpu_compute_unit` 499, `memory_coalescer` 207, `rv32i_cache_arbiter` 138, `rv32i_dcache` 971, `rv32i_decode` 483) |
| W2 | `$fatal` generate guards: `apb4_register_bank` 61-62, `axi_lite_register_bank` 80-81, `axil_to_apb` 93-94, `soc_top` 408 | elaboration-time parameter checks; a passing build cannot execute them |
| W3 | `pready`, `pslverr` of APB peripherals | zero-wait-state peripherals, bus error generated only by the interconnect (H3 covers that) |
| W4 | constant AXI sideband bits and `_unused*` signals | INCR-only, single-size, full-strobe masters by design |
| W5 | `pmu` GPU-domain handshake arms, invalid-state output decode, counter-while-idle row | the GPU domain has no isolation handshake (CLAUDE.md item 11, bead `3ogd`: "The GPU needs none"); an invalid `dom_state_d` cannot occur |
| W6 | fully enumerated case defaults: `rv32i_decode` 483, `rv32i_imm_gen` 87, `rv32i_csr_file` 251/259/286/296/597/609, `rv32i_pipeline_ex1c` 149/162, `rv32i_pipeline_mem` 73/80 | selector widths or decoder contract make the value unreachable (several already `coverage_off` in RTL) |
| W7 | dead code: `dma_engine` 394, `rv32i_icache` 510, `rv32i_pipeline_ex1b` 77-83; W7b `warp_scheduler` slots [0][1..3] | provably unreachable (reasoning in section 3). **Prefer deleting the dead RTL** over waiving it |
| W8 | DFT-only observability above the instantiated slot count (`mbist_status_i` high bits), scan-mode ports in `dft_ctrl_ports` | exist for a larger configuration; no functional path in the SoC build |
| W9 | `irq_src_i[2]` (timer) at SoC level | tied 0 by design |

None of these should be applied to raise a number: the bar for each is "unreachable by construction", and H3-H10 are
not waivable (a test can reach them).

## 6. Caveats and tool behaviour that affects reading the numbers

* **C1. Shapes.** 17 modules have more than one parameter shape (for example `sram_controller` 3, `mbist_ctrl` 5,
  `apb_interconnect` 5, `crypto_accel` 5, `mem_collar` 8, `cdc_gray_fifo` 8). The module score is urg's merged top row; the hole counts are "uncovered in
  every shape that lists the point", so a point hit in only one shape is not listed. `vcs_cov_holes.py` also records the
  shape-only holes (`*_shape_only` keys in its JSON); they are mostly rarely-used configurations (for example
  `crypto_accel` with `EN_AES`/`EN_SHA` off).
* **C2. Generate loops count per instance.** A line inside a `for ... generate` is listed once per iteration and
  counted uncovered if any iteration missed it. This is why `sram_controller` (128 groups) and `pmu` (two domains)
  show line holes that Verilator, which folds identical points, did not.
* **C3. Crypto condition rows.** `crypto_accel` L511 (`op_legal_w`) lists row `1 0` ("AES-legal and not SHA-legal") as
  never covered. That contradicts `aes128_core` line 100 % and 51 passing crypto tests, so it is treated as a
  merge/shape bookkeeping artefact of the `EN_AES`/`EN_SHA` parameters and **not** reported as a hole. Needs a
  per-shape look in Verdi before anything is concluded from it.
* **C4. Missing metric objects.** `axi4_crossbar` has no COND or BRANCH objects in the vdb (urg: "coverage shape is not
  there"). Measured with and without `-cm_hier`, so it is not the scope file, and a minimal `always_comb` `if/else`
  does produce both metrics, so it is not a blanket `always_comb` limitation. The cause was not established (the
  crossbar uses `for (int ...)` loops inside `always_comb` and a function call in the condition). Its branch and
  condition coverage is therefore **not measured** by this run; only line, toggle and FSM are.
* **C5. Verilator pragmas and waivers are not honoured by VCS** (see 2.1), so VCS lists defaults that the Verilator
  report already hides.
* **C6. `-flex_merge modules` is LCA** and the merged `.vdb` is written next to the report directory (`report/<area>.vdb`).
  Instance-level hierarchies of different testbenches are reported side by side, not merged.
* **C7. Tests that share a build.** Per-test attribution is available (`tests.txt`, one row per `-cm_name`), but this
  review ranks by module, not by which test hits what.
* **C8. Not run here:** Xcelium/imc coverage (user decision); the cocotb functional-coverage YAML export
  (`FUNC_COV_DIR` was not set, so no functional percentage is quoted for this run); formal; gate-level.

## 7. Functional coverage that already exists, and how it relates

| Item | Scope | Gate | Relation to the code-coverage holes |
| :--- | :---- | :--- | :---------------------------------- |
| `tb/cocotb/soc/func_cov.py` | plumbing over `cocotb-coverage` 1.2.0 (coverpoints, crosses, YAML export through `FUNC_COV_DIR`); never a hard dependency of a simulation | n/a | opt-in, so an ordinary run (including this one) exports nothing |
| `tb/cocotb/soc/i2c_cov.py` | **I2C only**: 138 bins sampled from the BFM event stream, APB transfers and assertion-backed scenario samples (`docs/verification/I2C_FUNCTIONAL_COVERAGE_MODEL.md`) | `tools/verif/functional_coverage_gates.txt`: `i2c`, 100 %, `min_bins` 138 | `i2c_controller` is 100 % line, 95.3 % cond, 95.7 % branch but **62.5 % FSM**: the missing arcs (H14) are the loopback slave's repeated START, which the model does not have a bin for (`loopback_op` is only write/read). A 100 % functional gate on a thin model did not catch it |
| Everything else (UART, SPI, DMA, PMU, crypto, NPU, caches, GPU, fabric) | no covergroups | none | the holes H1-H10 are all in blocks with **no** functional model; code coverage is the only coverage evidence for them. `docs/verification/FUNCTIONAL_COVERAGE.md` section 4 is the rollout recipe; the highest-value next models are the AXI/APB fabric (response codes x channel x reset-phase, which would have flagged H1 and H3), the DMA (queue depth x burst length) and the PMU (sequence state x reset phase) |

Code coverage says which code ran; it cannot say that NPU KLEN = 1 and KLEN = 63 both ran, that all four AES key sizes
or all SHA block counts ran, or that every response code was seen on every channel. Those need covergroups, which this
pass deliberately does not write.

## 8. Reproducibility and provenance

* Instrumented regression and merge: `tools/eda/vcs_coverage.py` (new), job lists from `tools/eda/regress_specs.py`,
  driver `tools/eda/run_cocotb_targets.py`, flags in `tb/cocotb/common/sim_portability.mk`.
* Hole digest: `tools/eda/vcs_cov_holes.py` (new) reads only urg's text output.
* Databases and reports are not committed (`.gitignore`: `sim_build*`, `*.vdb/`, `urgReport*/`, `simv.daidir/`,
  `vcs_cov_scope_*`). They are regenerated by the first command in section 1 in about 24 minutes.
* Artifact provenance: the coverage scope lists and `-cm_hier` files are regenerated by `make` at each build from the
  checked-in `rtl/` tree; no pre-generated artifact is consumed.
