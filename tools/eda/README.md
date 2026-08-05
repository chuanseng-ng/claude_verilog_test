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
| `opensta` | violated endpoints, negative `wns`/`tns`; **empty report ⇒ `ERROR`** | `wns`, `tns`, `worst_slack`, `paths_reported`, `violated_endpoints` |
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

## MCP session servers (OpenSTA / OpenROAD)

`wrap-opensta.sh` is a one-shot driver: every invocation re-reads liberty +
netlist + SDC from scratch, which is minutes of setup on a design this size.
During timing closure the same loaded design gets queried dozens of times in a
row, so `tools/eda/mcp/` adds a second option that keeps the tool warm:

- **`tools/eda/mcp/tcl_session.py`** — spawns OpenSTA or OpenROAD once and
  drives it over stdin/stdout. Each command is written to a temp `.tcl` file
  and `source`d (both tools echo stdin, so an inlined command would pollute
  the output stream); output is captured via
  `sta::redirect_file_begin`/`redirect_file_end` into a report file, and a
  per-call sentinel (`__EDA_DONE_<n>__`) plus error marker
  (`__EDA_ERROR_<n>__`) let the reader thread find the end of each reply and
  turn a Tcl error into data instead of a desync. A background reader thread
  + queue gives every call a timeout, so a hung tool fails the call instead of
  hanging the server.
- **`tools/eda/mcp/session_server.py`** — an MCP stdio server (JSON-RPC 2.0,
  newline-delimited) over that session, implementing `initialize`,
  `notifications/initialized`, `tools/list`, `tools/call`, `ping`, `shutdown`.

### Session vs wrapper — when to use which

| | Use | Why |
| ---- | --- | --- |
| One-shot check (lint, synth stats, a single CI gate) | `wrap-*.sh` | Nothing is reused between calls; a subprocess is simpler and the JSON verdict is all a gate needs. |
| Many queries against one loaded design (timing closure: check a fix, re-check, check a different path group, ...) | the MCP session | The multi-minute liberty+netlist+SDC load happens once; every later query answers from the already-loaded state. |

### Tool surface

| Server | Tool | Does |
| ------ | ---- | ---- |
| `eda-opensta` | `load_design` | `read_liberty`×N, `read_verilog`, `link_design`, `read_sdc`, optional `read_spef` |
| `eda-opensta` | `report_timing` | `report_checks -path_delay max -group_count <max_paths>` (+ optional `path_group`/`from`/`to`/`extra_args`) |
| `eda-opensta` | `report_wns_tns` | `report_wns; report_tns; report_worst_slack` — cheapest health check |
| `eda-opensta` | `check_setup` | unconstrained endpoints, missing clocks |
| `eda-openroad` | `load_odb` | `read_liberty`×N, `read_db`, optional `read_sdc` |
| `eda-openroad` | `query_timing` | same as `report_timing`, against the loaded `.odb` |
| `eda-openroad` | `get_area` | `report_design_area; report_cell_usage` |
| `eda-openroad` | `get_power` | `report_power` |
| both | `run_tcl` | escape hatch — arbitrary Tcl in the live session |
| both | `close_design` | terminate the tool process; the next `load_*` starts fresh |

`report_checks` on OpenSTA 2.6.0 takes `-group_count`/`-endpoint_count`, **not**
`-max_paths` — the tool rejects that flag outright ("not a known keyword or
flag"). `report_timing`/`query_timing` accept a `max_paths` argument in the MCP
schema and translate it to `-group_count` internally, and that translation
applies whether or not `path_group` is also set, so asking for both a path
group and a path count gets both instead of the count collapsing to 1.

Raw reports are **never** returned inline: every reply is a JSON summary (the
same shape `summarize.py` produces) plus the absolute path to the full report
under `sim/build/eda-logs/` (override with `EDA_LOG_DIR`). `run_tcl`/`get_area`/
`get_power`/`check_setup` inline up to 4000 chars of text with an explicit
`truncated` flag; the full text is always on disk.

**Known OpenROAD limitation:** `report_design_area`/`report_cell_usage` print
through OpenROAD's own `utl::Logger`, not the STA report-string channel that
`sta::redirect_file_begin` hooks (confirmed on OpenROAD 26Q2 by comparing
against `report_power`, which *does* go through that channel and captures
correctly). The session driver cannot capture their text, so `get_area` reports
`status: ERROR` rather than a false `PASS` with a silently empty report — same
rule as the empty-report case below.

Configured in the repo's `.mcp.json` as `eda-opensta` / `eda-openroad`, both
launching `python3 tools/eda/mcp/session_server.py --tool <tool>` from the repo
root. Neither `sta` nor `openroad` is on the login `PATH` on this host;
`tcl_session.resolve_tool()` falls back to a `/nix/store/*-opensta*/bin/sta` /
`/nix/store/*-openroad*/bin/openroad` glob, or set `EDA_STA_BIN`/
`EDA_OPENROAD_BIN` explicitly.

## Tests

`tb/tests/test_eda_summarize.py` (20 cases, part of the CI QA job) covers every
parser, and specifically pins the three "exit 0 but nothing to report" paths to
`ERROR`, plus the `worst_slack` field (including the clean-design case where
`wns`/`tns` read `0.00` and `worst_slack` carries the real margin). Run with
`rtk pytest tb/tests/test_eda_summarize.py -q`.
