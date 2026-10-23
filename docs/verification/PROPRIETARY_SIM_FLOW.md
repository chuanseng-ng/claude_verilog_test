# Proprietary simulator flow: Synopsys VCS and Cadence Xcelium

How to set up, compile and run this repo's cocotb regressions on commercial simulators. Verilator, run from
the nix dev shell, is still the default flow and the one CI runs (see [Quick Start](../readme/QUICK_START.md)).
Nothing here changes it.

Validated on 2026-10-24 with **VCS Y-2026.03** and **Xcelium 24.03**, cocotb 1.9.2, Python 3.11, RHEL 8:

| Simulator | SoC (`SOC_CI_SUITES`, 46 jobs) | CPU / cache / GPU (34 jobs) | Wall clock (SoC / CPU) |
|---|---|---|---|
| VCS | 872 pass / 0 fail / 46 skip | 265 pass / 0 fail | ~14 min / ~4 min |
| Xcelium | 872 pass / 0 fail / 46 skip | 265 pass / 0 fail | ~6 min / ~3 min |

Both SoC rows use `--jobs 3` on an 8-core, 15 GB host. Code coverage on VCS is a separate flow: see
[COMMERCIAL_SIM_COVERAGE.md](COMMERCIAL_SIM_COVERAGE.md).

## 1. Prerequisites

| Need | Check | Notes |
|---|---|---|
| VCS | `echo $VCS_HOME; $VCS_HOME/bin/vcs -ID` | `-ID` prints the version without checking out a licence. Call `$VCS_HOME/bin/vcs`, not a shell alias. |
| Xcelium | `echo $XCELIUM_HOME; xrun -version` | `imc` (coverage reporting) is **not** part of every Xcelium install. It is absent on the reference host, so there is no Xcelium coverage. |
| Licences | `SNPSLMD_LICENSE_FILE`, `CDS_LIC_FILE` / `LM_LICENSE_FILE` | cocotb passes `-licqueue` to xrun, so a missing Cadence licence **waits forever** instead of failing. |
| Python ≥ 3.10 | `ls /usr/bin/python3.1*` | Do not use a Python bundled inside an EDA install (e.g. Calibre's `python3` on PATH). |
| gcc/g++ | `g++ --version` | The system gcc 8.5 is enough. cocotb 1.9.2 ships prebuilt VPI libraries for both simulators. |

No Verilator, nix or root access is needed.

## 2. One-time setup

```bash
make eda-venv                    # creates .venv-eda/ (gitignored) from requirements-eda.txt
                                 # override the interpreter: make eda-venv EDA_PYTHON=/path/to/python3.11
```

`requirements-eda.txt` follows the CI pins in `.github/workflows/cocotb.yml`: `cocotb>=1.8,<2.0`, pyuvm 3.0,
cocotbext-axi, cocotb-bus and cocotb-coverage 1.2.0. **Do not install from `uv.lock`:** it pins cocotb 2.x,
and the testbenches use the 1.x API (`units=`).

`make eda-venv` is idempotent: re-running it only re-syncs the requirements.

## 3. Every shell

```bash
source tools/eda/sim_env.sh      # bash/zsh
source tools/eda/sim_env.csh     # csh/tcsh: run from the repo root, or set $EDA_REPO
```

This:
- activates `.venv-eda` and exports `SIM_PYTHON3`;
- puts the Xcelium tool directories on PATH;
- sets a UTF-8 locale, without which cocotb logging raises `UnicodeEncodeError` on non-ASCII docstrings;
- warns on stderr if `VCS_HOME`, `XCELIUM_HOME`, the licence variables or `urg` are missing.

`SIM_ENV_QUIET=1` silences the OK lines.

## 4. Running

### A single suite, through the Makefiles

The same targets as the Verilator flow, with `SIM=` set:

```bash
make -C tb/cocotb/soc SIM=vcs gpio            # tb/cocotb/soc targets
make -C tb/cocotb/soc SIM=xcelium crypto
make -C tb/cocotb/cpu SIM=vcs smoke           # CPU suites
make -C sim SIM=xcelium icache                # Phase 3 cache / Phase 4 GPU targets in sim/
make -C tb/cocotb/soc SIM=vcs uart TESTCASE=test_tx_transfer
```

> ⚠️ **`make` exits 0 even when tests fail** (cocotb 1.x). Read the verdict from the `TESTS= PASS= FAIL=`
> summary line or from `results.xml`, never from the exit code.

### The full regression, through the driver

Use `tools/eda/run_cocotb_targets.py` for anything bigger than one suite. It gives every job its own
build root, runs jobs in parallel, and judges **only** from the `results__*.xml` files. A job that writes no
results file is a FAIL. The full job lists come from `tools/eda/regress_specs.py`, which reads
`SOC_CI_SUITES` from the Makefile, so it never drifts from CI.

```bash
# full SoC regression (heaviest jobs first, tb_soc_top suites chained to share one compile)
python3 tools/eda/run_cocotb_targets.py --sim vcs --jobs 3 \
    --json /tmp/soc_vcs.json $(python3 tools/eda/regress_specs.py soc)

# CPU / cache / GPU (sim/ cannot relocate results.xml, so --jobs 1)
python3 tools/eda/run_cocotb_targets.py --sim xcelium --jobs 1 \
    --json /tmp/cpu_xrun.json $(python3 tools/eda/regress_specs.py cpu)

# a few jobs: AREA:TARGET[:VAR=VAL,...], '+' chains jobs that share one compiled model
python3 tools/eda/run_cocotb_targets.py --sim vcs soc:gpio soc:sram_controller:SRAM_TARGET=sky130 \
    soc:soc_boot+soc:soc_gpio
```

The exit status is 0 only if every job passes. Build directories go under `--root`, by default
`sim_build_eda/` (gitignored). A full VCS SoC run uses about 1.2 GB.

### Pass criteria and floors

CI's floors are `PASS_FLOOR` (SoC) and `CPU_PASS_FLOOR` (CPU/cache/GPU), set in
`.github/workflows/soc_coverage.yml`. Under VCS or Xcelium, **subtract the Verilator-only tests**. These are
reported as skipped with a reason, never counted as passed:

- `test_i2c.test_i2c_clkdiv_min_guard_rejects_elaboration`
- `test_crypto.test_crypto_elaboration_guards_reject_illegal_config`
- `test_crypto.test_crypto_elaboration_legal_configs_pass`
- `test_npu.test_npu_elaboration_guard_rejects_bad_weight_words`
- `test_npu.test_npu_elaboration_legal_configs_pass`

All five shell out to `verilator --lint-only`. The `*_lint` Makefile prerequisites are no-ops under a
commercial simulator, and compile cleanliness is judged from the VCS/xrun compile logs instead. The `*_neg`
elaboration-guard targets are not in `SOC_CI_SUITES` and are **not run** here.

Expected: SoC **872 pass / 46 skip** (`PASS_FLOOR` 874 − 5 = 869 adjusted), CPU/cache/GPU **265 pass**.

## 5. How it works (`tb/cocotb/common/sim_portability.mk`)

The three cocotb Makefiles (`tb/cocotb/soc`, `tb/cocotb/cpu`, `sim/`) include one shared file. It only
applies when `SIM` is `vcs` or `xcelium`; under Verilator the generated commands are byte-identical
(30 targets checked with `make -n` and `cmp -s`).

| Verilator idiom in the Makefiles | VCS | Xcelium |
|---|---|---|
| `-G<P>=<v>` numeric parameter | `-pvalue+<TOP>.<P>=<v>` | on the xrun command line |
| `-G<P>="str"` string parameter | `-pvalue+` with the quotes escaped again for the recipe's shell | generated `$(SIM_BUILD)/sp_defparams.sv` (`defparam TOP.P = "str";`) plus a second `-top`, because `xrun -defparam` silently ignores string parameters (`*W,BDDSTR`) |
| `-I<dir>` | `+incdir+<dir>` **and** `-y <dir> +libext+.sv+.v` (Verilator's `-I` also finds modules by name) | same |
| `-D` / `+define+` | `+define+` | `+define+` |
| `-Wno-*`, `--trace*`, `--x-*`, `-O*`, `--public*`, … | dropped | dropped |
| `*_lint` prerequisite | no-op | no-op |
| `SIM_BUILD` | keyed by `SIM` | keyed by `SIM` |

Never pass `EXTRA_ARGS=` on the make command line under Xcelium. It overrides cocotb's own `EXTRA_ARGS +=`,
which carries `-top`, `-xmlibdirpath` and `-licqueue`. The include translates and then un-defines it.

Testbench hierarchy access goes through `tb/cocotb/common/hier.py`:
- `hsub` and `hgen`: VCS flattens generate-block children into names like `"g_mem[3].u_mem"`.
- `pget` and `pset`: VCS exposes packed-struct ports as member scopes with no `.value`.
- `read_only`: avoids awaiting `ReadOnly()` while already in the ReadOnly phase.

## 6. Writing portable tests

These are the failure classes found when the existing regression first ran on VCS and Xcelium. Keep new tests
clear of them, because CI only runs Verilator.

1. **Drive every DUT input in reset/setup.** An undriven input, or a register or memory never written, reads
   0 on Verilator (2-state init) and **X** on VCS and Xcelium (4-state).
2. **Don't act exactly on a clock edge.** A deposit or handshake in the same timestep as an edge can lose
   to that edge's non-blocking updates, depending on the simulator. Step one timestep off the edge first.
3. **Sample data only when it is valid**, e.g. `RDATA` only when `RVALID=1`. It is X otherwise.
4. **No bit-select on a packed vector through VPI** (`dut.sig[2]`). Read the whole value and shift and mask.
5. **LRM 9.2.2.4:** a variable written by `always_ff` must not also be written by `initial` or a declaration
   initialiser. VCS rejects it with `ICPD`.
6. **Use-before-declare in RTL is an RTL bug.** VCS (`IND`/`IPDW`) and Xcelium (`UNDIDN`/`DUPIMP`) reject
   it, even though Verilator accepts it.
7. **Zero-delay races.** Logic that depends on the delta order between a clock and a gated copy of it is not
   race-free. The `dft_clk_switch` enable latch was one such case, failing only on Xcelium.

## 7. Known noise (not failures)

| Simulator | Message | Why |
|---|---|---|
| VCS | `ERROR gpi ... Unable to register a callback handle ... cbStartOfSimulation/cbEndOfSimulation`, `Warning-[VPI-CT-NS]` | cocotb's compile-time `-load`; harmless |
| VCS | `DEBUG_DEP`, `DBGACC_DBG/CMB`, `[VCS_SAVE_RESTORE_INFO] ASLR` | cocotb passes both `-debug` and `-debug_access` |
| Xcelium | `*W,NODNTW` in testbench wrappers | `tb_*.sv` sets `` `default_nettype none `` |
| Xcelium | `*W,SPDUSD`, `*W,LIBNOU` | unused `-y` library directories from the `-I` translation |
| Xcelium | `*W,NOIEEE` at `sram_controller.sv:989` | `` `undef `` of a macro that was never defined |

Never decide pass/fail by grepping a log for `ERROR`; use `results.xml`.

## 8. Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `make` says success but tests failed | cocotb 1.x exit code. Use the driver, or read `results.xml`. |
| `ERROR: results.xml was not written` | Compile failure (read `sim_build*/compile.log` or `xrun.log`) or disk full |
| xrun hangs at start | No Cadence licence (`-licqueue`). Check `CDS_LIC_FILE`. |
| `UnicodeEncodeError` in cocotb logging | `sim_env` not sourced (UTF-8 locale) |
| `prompt: Undefined variable` sourcing in csh | Use `tools/eda/sim_env.csh`, which sets `prompt` before `activate.csh` |
| Parameter override has no effect (`PRM_ILLG` on VCS, `BDDSTR` on Xcelium) | A string parameter override. Use the Makefiles or the driver, not a hand-written `EXTRA_ARGS`. |
| Make recurses forever on a target with `VAR=VAL` | A build-root path containing `=`. The driver sanitises it; don't put `=` in `SIM_BUILD_ROOT`. |
| `ucli.key`, `xrun.log`, `xcelium.d` in the working dir | Simulator droppings. They are gitignored; run concurrent jobs through the driver. |

## 9. Coverage

VCS only: `COVERAGE=1 SIM=vcs`, `make -C tb/cocotb/soc SIM=vcs soc_coverage_vcs`, or
`python3 tools/eda/vcs_coverage.py run --area all`. Reports are merged with `urg -lca -flex_merge modules`.
Results and the ranked hole review are in [COMMERCIAL_SIM_COVERAGE.md](COMMERCIAL_SIM_COVERAGE.md).
`COVERAGE=1 SIM=xcelium` is refused because `imc` is not installed.
