# Quick Start

Build and run commands per phase. For environment requirements see the root
[`README.md`](../../README.md#requirements).

## Nix dev shell (simulation + lint)

A pinned nix flake at the repo root provides the deterministic EDA toolchain for
simulation and lint — **Verilator 5.048**, iverilog, gcc, make — so local and CI
toolchains match. Enter it before running any `sim/` make target:

```bash
nix develop          # primary entry point (flakes)
# or, without flakes enabled:
nix-shell            # same shell via shell.nix flake-compat wrapper

cd sim && make test  # Verilator + cocotb now use the pinned toolchain
```

The Python/cocotb stack (cocotb, pyuvm, cocotbext-axi, cocotb-bus) stays on the
system Python + pip — install once with
`pip install -r requirements.txt cocotb-bus cocotbext-axi`. Synthesis / PnR is
**not** covered by this shell; it uses the external librelane nix env via
`pnr/Makefile`.

## Phase 0: Reference Model Testing (Complete ✅)

```bash
# Navigate to test directory
cd tb/tests

# Run all reference model unit tests (66 tests)
pytest -v

# Run specific model tests
pytest test_rv32i_model.py -v      # CPU model (33 tests)
pytest test_gpu_model.py -v        # GPU model (12 tests)
pytest test_memory_model.py -v     # Memory model (21 tests)

# Run with coverage
pytest --cov=tb.models --cov-report=html
```

## Phase 1: RTL Simulation ✅ Complete (Archived to `micro_p/`)

Phase 1 single-cycle CPU has been completed and archived. All verification passed.

## Phase 2: RTL Simulation ✅ Complete

```bash
# Navigate to cocotb test directory (WSL)
cd tb/cocotb/cpu

# Run all Phase 2 test suites (111 tests)
make phase2_all

# Run individual suites
make smoke_uvm          # 4 smoke tests
make isa_uvm            # 54 ISA compliance tests
make pipeline_hazards   # 16 pipeline hazard tests
make interrupts         # 13 interrupt/CSR tests (incl. concurrent-IRQ priority)
make debug              # 6 debug interface tests
make axi_protocol       # 12 AXI protocol tests
make fault_injection    # 7 fault injection tests

# Run random regression (500 seeds × 100 instructions)
RANDOM_TEST_SEEDS=500 RANDOM_TEST_INSTRS=100 make random_uvm

# Replay a single failing seed (per-seed outcomes are logged to
# results/random_seed_log.txt by every multi-seed run)
make random_uvm SEED=1042 INSTRS=100

# Clean build artifacts
make clean
```

## Phase 3: Cache Simulation ✅ Complete

```bash
# Navigate to sim directory
cd sim

# Run all Phase 3 cache tests (20 tests)
make phase3_all

# Run individual cache test suites
make icache             # I-cache unit tests (7 tests)
make dcache             # D-cache unit tests (8 tests)
make cache_integration  # CPU + cache integration tests (5 tests)

# Clean build artifacts
make clean
```

## SoC cocotb regression (`tb/cocotb/soc`)

```bash
nix develop --command make -C tb/cocotb/soc soc_all_ci SIM_BUILD_ROOT=/nobackup/claude_sim_build/soc
#   optional: SIM_BUILD_JOBS=4  (parallel C++ compile of each model; CI passes $(nproc))
#   optional: SIM_CCACHE=1      (compiler cache, see sim/cxx_shim.sh; needs ccache on PATH)
nix develop --command make -C tb/cocotb/soc print-sim-build MODULE=m TOPLEVEL=tb_soc_top SIM_KEY_VERBOSE=1
```

Each Verilator build lives in `$(SIM_BUILD_ROOT)/sim_build_<TOPLEVEL>_<key>[_cov]`, where `<key>` is a
sha256 of everything that determines the compiled model (top level, ordered source list, `COMPILE_ARGS`,
`EXTRA_ARGS` incl. every `-G`/`-D`/`-I`, `BUILD_ARGS`, build-time env, and the verilator / g++ / cocotb
versions plus the `cxx_shim.sh` content). Suites with an identical model share one directory: the 15 full-SoC
`tb_soc_top` suites compile once, not 15 times. MODULE, TESTCASE and plusargs are runtime-only and are not
in the key. Source *content* is not hashed; staleness is still decided by cocotb's mtime rule on
`VERILOG_SOURCES`. If two suites you expect to share do not, `print-sim-build` with `SIM_KEY_VERBOSE=1`
shows the exact material. Checks: `pytest tb/tests/test_sim_build_key.py` and
`make -C tb/cocotb/soc check-shared-build-failure` (both also run in CI, job "cocotb build-directory key
self-tests"). `make clean-sim-builds` sweeps every directory.

## RTL Linting & Formatting

Two complementary tools, both run from `sim/`:

- **Verilator** (`make lint`) — semantic/structural lint (widths, latches, unused signals).
- **Verible** (`make lint-verible`) — SystemVerilog *style* lint. `nix develop` provides the
  binary; otherwise install a prebuilt one from
  [Verible releases](https://github.com/chipsalliance/verible/releases) (no build needed).

```bash
cd sim

make lint                  # Verilator semantic lint (CPU top + soc_top)

make lint-verible          # Verible style lint (curated ruleset, whole tree)
make verible               # alias for lint-verible
```

Style rules live in [`.rules.verible_lint`](../../.rules.verible_lint). CI runs Verible via the
[`rtl-checks.yml`](../../.github/workflows/rtl-checks.yml) workflow — the **lint step is a hard
gate** (whole tree clean). There is no format check: the formatter cannot reproduce the
hand-aligned house style (bead `hn9l`), so formatting is enforced by review. `nix develop` provides the same
Verible binary CI installs, so no manual download is needed there.
