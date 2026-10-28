# tools/dft/atpg - DFT Stage 3 ATPG spike (bead j41m.15)

Time-boxed open-tool ATPG spike: Quaigh 0.0.6 on a ladder `npu -> crypto -> dma -> fabric`. Findings, tables and caveats:
`docs/design/DFT_ARCHITECTURE.md` section 18. Heavy outputs go to `/nobackup/claude_sim_build/j41m15/` (never into git).

Box (user decision 2026-10-28): about 5 working days, 12 GB RAM and 24 h wall per run, stop at the first rung that breaks a limit.
`run_capped.sh` enforces it (`systemd-run --user --scope -p MemoryMax=12G -p MemorySwapMax=0` + `timeout 24h` + `/usr/bin/time -v`)
and writes `metrics.json` (rc, wall, maxrss, cgroup peak, oom_kill, timed_out). Run nothing else heavy meanwhile: systemd-oomd can kill the session.

| File | Role |
|---|---|
| `run_capped.sh`, `run_capped_inner.sh` | capped runner + `metrics.json` |
| `synth_module.sh` | standalone sv2v + Yosys (Sky130 tt Liberty) of one block, for the module rungs |
| `netlist_lib.py` | tiny structural-Verilog reader |
| `derive_hold_mask.py` | the 94 scan-view hold-masked capture flops from STABLE synchroniser Q-net names; `--validate` against the STA's `exempt_pins.txt` |
| `netlist_prep.py` | deletes physical cells; classifies and applies the exclusions (tck / scan_clk / crypto key / hold mask); writes `exclusions.json` |
| `mk_cut.py` | Yosys full-scan cut: Sky130 cells -> logic, scan-mode constants, black boxes, `abc -g`, BLIF with `.latch`, dead-logic drop |
| `atpg_coverage_report.py` | Quaigh log -> fault / test coverage with the exclusion statement |
| `regrade.py` | independent re-grade of the patterns (own simulator + `quaigh simulate` on fault-injected copies) |
| `run_rung.sh`, `Makefile` | the ladder |

Tools: Yosys 0.46 (the flow's), sv2v 0.0.13.1, Quaigh 0.0.6 (pinned external binary, `tools/dft/build_quaigh.sh`). The `dft` devshell in
`flake.nix` provides yosys, sv2v, python; point `QUAIGH=` at the binary.

Quaigh facts relied on (read from its source, DFT_ARCHITECTURE 18.1): `unobservable=N` counts faults whose SAT miter is UNSAT (proven
untestable in the cut); the universe is the collapsed list; `--num-random`/`--num-cycles` switch to random sequential patterns only (no SAT, no
grading), so they are NOT a way to "retry with more random patterns"; a sequential BLIF (`.latch`) is accepted and exposed as full scan.

Not done here: pattern -> scan-chain-order mapping, SVF/TAP replay, Sky130 cell-pin fault model, SRAM shadowing, delay faults (follow-up beads).
