# `tools/eda` — compact JSON verdicts for EDA tools

Thin drivers that run an EDA tool, keep the full log on disk, and print a short
JSON verdict on stdout. Same shape as [`tools/cdc/`](../cdc/README.md): shell
driver + Python post-processor, **and the exit code is the verdict**.

```bash
tools/eda/wrap-verilator.sh --lint-only -Wall --top-module timer rtl/periph/timer.sv
tools/eda/wrap-yosys.sh     synth.ys
tools/eda/wrap-opensta.sh   pnr/scripts/07_sta.tcl
tools/eda/wrap-cocotb.sh    tb/cocotb/soc uart
```

## Exit codes

| Code | Meaning |
| ---- | ------- |
| 0 | `PASS` — tool succeeded, no violation found |
| 1 | `FAIL` — tool failed, or the log shows a real violation |
| 2 | `ERROR` — the log could not be interpreted: empty/missing report, no recognisable result |
| 3 | tool not found in `PATH` (the JSON carries the devshell hint) |

`ERROR` is deliberately distinct from `FAIL`. OpenSTA exits 0 while reporting
violated paths, and an *empty* report is indistinguishable from a clean one at
the exit code — this repo has already shipped a CDC timing gate that passed for
exactly that reason (bead `dwp`). A gate built on these wrappers cannot repeat it.

## What each parser extracts

| Tool | Verdict comes from | Summary fields |
| ---- | ------------------ | -------------- |
| `verilator` | `%Error` lines / tool exit | `error_count`, `warning_count`, `warnings_by_code` |
| `yosys` | `ERROR:` lines / tool exit; **no statistics ⇒ `ERROR`** | `cell_count`, `chip_area`, `errors` |
| `opensta` | violated endpoints, negative `wns`/`tns`; **empty report ⇒ `ERROR`** | `wns`, `tns`, `paths_reported`, `violated_endpoints` |
| `cocotb` | JUnit `results.xml`, else the `TESTS=` tally; **neither ⇒ `ERROR`** | `passed`, `failed`, `skipped`, `failures[]` |

Every list is capped at 20 entries with an explicit `... N more (see raw log)`
marker — truncation is never silent. Full logs land in `sim/build/eda-logs/`
(override with `EDA_LOG_DIR`).

## Wrappers vs the rtk filters

They solve different problems, and for interactive test runs the filters are the
better tool:

- **`.rtk/filters.toml`** (see the RTK section of `CLAUDE.md`) compresses output
  in place, automatically, for anything you type. A 26-test cocotb suite goes
  from 244 lines to 2. Use this by default — just run `make` as usual.
- **These wrappers** produce a *structured, machine-checkable* verdict and turn
  a silent zero exit into a real failure. Use them in CI gates, Makefile
  targets, and anywhere a program (not a person) consumes the result.

## Tool discovery

`eda_common.sh` prepends the same cache paths `tools/cdc/fetch_cdc_tools.sh`
populates (`sim/build/cdc/oss-cad-suite/bin`, `sim/build/cdc/sv2v-Linux`), so a
clone that has run the CDC flow needs no second download. Otherwise:

- `verilator` — repo devshell: `nix develop --command tools/eda/wrap-verilator.sh ...`
- `yosys` — `tools/cdc/fetch_cdc_tools.sh --with-yosys`, or the librelane nix-shell
- `sta`, `openroad` — librelane nix-shell (`~/Downloads/Github/librelane`)

A missing tool exits 3 with the hint in the JSON, never a stack trace.

## Tests

`tb/tests/test_eda_summarize.py` (18 cases, part of the CI QA job) covers every
parser, and specifically pins the three "exit 0 but nothing to report" paths to
`ERROR`. Run with `rtk pytest tb/tests/test_eda_summarize.py -q`.
