# Functional coverage in the cocotb flow (bead h367)

`tools/verif/coverage_report.py` measures Verilator **code** coverage (line, toggle). Until this
change nothing measured **functional** coverage: no covergroup, so the verification sign-off
criterion `functional_coverage_pct: 100` could not be met for any peripheral. This document records
the mechanism evaluation, the chosen design and how another peripheral adds a model. The pilot is
I2C (`I2C_FUNCTIONAL_COVERAGE_MODEL.md`).

## 1. Evaluation

| Option | Verdict | Evidence |
| :----- | :------ | :------- |
| **`cocotb-coverage` 1.2.0** (PyPI) | **Chosen** | `Requires-Dist: cocotb ~=1.8` (so `>=1.8,<2.0`), matching `requirements.txt` (`cocotb>=1.8.0,<2.0`) and the installed cocotb 1.9.2. Pure Python; `cocotb_coverage.coverage` does not even import cocotb. CoverPoint / CoverCross / `at_least` / weights, YAML and XML export, and a `merge_coverage` for runs. Verified here: installs, imports, samples inside a Verilator cocotb 1.9.2 simulation, exports, and its merge agrees with this repo's merge (a unit test). |
| `cocotb-coverage` 2.0 (2025-10-03) | Not usable now | Requires `cocotb>=2` and Python `>=3.11`. This repo is pinned to cocotb 1.x (cocotb 2 removed the `units=` kwarg used throughout `tb/`) and CI runs Python 3.10. Revisit when the cocotb 2 migration happens; the YAML schema is unchanged, so only `func_cov.py` would be touched. |
| pyuvm (4.0.1 installed, `<3.1` pinned) | No | No covergroup facility: the package has the UVM component, phase, TLM, factory and register-model classes only (a search for covergroup / coverpoint over the installed package finds nothing). |
| SystemVerilog covergroups under Verilator | No | Verilator 5.048 (the flake pin) parses and **ignores** them: `%Warning-COVERIGN: Ignoring unsupported: coverpoint` / `cover bin specification` / `coverage clocking event` (reproduced with a 2-bin covergroup). They would also have to live in RTL or an SV testbench, which this pilot must not touch. |
| In-repo collector | No | Would re-implement bins, crosses, `at_least`, merge and export that the library already has and tests. The one design hedge kept: the merge/gate script reads the plain exported YAML schema and does **not** import the library, so the sampling layer can be replaced without touching the gate. |

**Recommendation: `cocotb-coverage==1.2.0`**, pinned exactly in `requirements.txt` (1.x is frozen at
1.2.0, 2023-11-15; 2.0 is the maintained line but needs cocotb 2).

Known library traits that shaped the glue (`tb/cocotb/soc/func_cov.py`):

* `CoverageDB` is a process-wide singleton and cocotb runs every test of a MODULE in one simulator
  process, so the database is cumulative across a suite; export once, at process exit.
* Sampling is by decorated function. `CoverPoint` runs `inspect.getmembers` on the first argument
  the first time it is called, so samplers take plain Python values (never a DUT handle).
* The first matching bin wins (`inj`), which makes ordered range bins exclusive.
* A cross reads the `new_hits` of its coverpoints, so the coverpoints must be sampled first
  (`func_cov.pair` orders the decorators correctly).
* Cross bins are exported as `str(tuple)` keys, for example `('write', 'ack')`.

## 2. Flow

```
 cocotb test --> BFM observers --> func_cov samplers --> coverage_db (per process)
                                                              | atexit, if FUNC_COV_DIR is set
                                                              v
                                       $FUNC_COV_DIR/<module>__<pid>.yml   (one per simulator process)
                                                              | CI: uploaded by each shard
                                                              v
        tools/verif/functional_coverage_report.py  --gate  -->  report .md/.json + merged .yml
```

* Sampling is on by default and costs a few dict updates per event. **Export is opt-in** through
  `FUNC_COV_DIR`; unset means nothing is written, so a local run leaves no files.
* If `cocotb_coverage` is not installed every sampler is a no-op and the suites still run. The CI
  gate is what fails (a required group with no data is exit 2), so a missing package cannot turn
  it green.
* Local run: `FUNC_COV_DIR=/tmp/fc nix develop --command make -C tb/cocotb/soc i2c`, then
  `python3 tools/verif/functional_coverage_report.py --in /tmp/fc --waivers
  tools/verif/functional_coverage_waivers.txt --gates tools/verif/functional_coverage_gates.txt
  --gate`. `PYTHONPATH` must reach a Python that has `cocotb-coverage` (it is in
  `requirements.txt`).
* CI: `cocotb.yml` (per pull request). Each `soc_shard` leg sets `FUNC_COV_DIR`, installs the
  package and uploads `func_cov/`; the `soc_all` aggregate job runs the gate over all shards and
  publishes the report as the `functional-coverage` artifact (and in the job summary). The
  instrumented `soc_coverage.yml` is not used: sampling needs no instrumented build, and cocotb.yml
  already runs per pull request.

## 3. The gate

`functional_coverage_report.py --gate` merges every YAML (hits add; totals are recomputed from the
hits, never taken from the inputs; a coverpoint declared differently in two files is exit 2), then:

* `tools/verif/functional_coverage_gates.txt` (`group | floor_pct | min_bins | why`): every listed
  group is **required** (no data is exit 2), its adjusted percentage must reach `floor_pct`, and its
  model must keep at least `min_bins` bins, so deleting coverpoints cannot buy a pass.
* `tools/verif/functional_coverage_waivers.txt` (`item | bin | b | why`): category `b` only,
  unreachable by design, with a reason. A bin that is merely not hit needs a test. A waiver for a bin
  that does not exist, or that was hit, is stale and fails the gate.

Exit status: 0 pass, 1 gate red, 2 could not evaluate (same convention as `coverage_report.py`).

## 4. Rolling out to another peripheral

1. **Model first.** Write `docs/verification/<PERIPH>_FUNCTIONAL_COVERAGE_MODEL.md`: one row per
   coverpoint with its bins and why each matters (spec section or RTL header). Derive bins from the
   register map and the behaviours the spec promises, not from what the tests happen to do.
2. **`tb/cocotb/soc/<periph>_cov.py`**, modelled on `i2c_cov.py`: declare the coverpoints at module
   level with `func_cov.point` / `ranges` / `pair` (names `<periph>.<group>.<coverpoint>`), put the
   samplers in a small observer class, create `COV = ...` and call
   `func_cov.enable_export(os.environ.get("MODULE", "<periph>"))`.
3. **Sampling points, in order of preference:**
   a. observers on the existing BFMs. `APB4Master.add_observer(cb)` gives
      `cb(is_write, addr, data, strb, ok)` after every transfer; a pin-level BFM can offer the same
      (`I2CSlave.add_observer`). Sample only fields the byte strobes cover.
   b. the tests' side-effect-free register peek, via `COV.reg_read(addr, value)`.
   c. an explicit scenario call (`COV.arb_loss("data_bit")`) **only** for a fact the pins cannot
      show, placed **after** the test's own assertions for that scenario, so a failing scenario
      samples nothing.
4. **`COV.attach(apb, bfm)`** where the test builds its BFMs (per test: a new BFM per test, the
   database is per process).
5. **Run it, read the holes.** Each uncovered bin is a test to write or, if it cannot happen, a
   category-`b` waiver with the reason. Mutation-check any new test as the other suites are.
6. Add the group to `functional_coverage_gates.txt` with the measured `min_bins` (and a floor of
   100 after waivers), and the waivers to `functional_coverage_waivers.txt`. If you add a cocotb
   suite, add it to `SOC_CI_SUITES` in `tb/cocotb/soc/Makefile` and to
   `tools/verif/soc_shard_weights.json` and `soc_shard_weights_plain.json`.

## 5. What this does not do

* Coverage is only as good as the model: 100 % of a thin model is not verification closure. Bins come
  from the spec; the model document says what each one is for.
* Scenario samples (3c) are declarations backed by the test's assertions, not observations.
* No cross-run history or trend; the report is per run (the merged YAML is the artifact).
* Only I2C is modelled. Other peripherals have no covergroups until they follow section 4.
