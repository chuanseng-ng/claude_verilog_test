# tools/dft/atpg - DFT Stage 3 ATPG spike (bead j41m.15)

Time-boxed open-tool ATPG spike: Quaigh 0.0.6 on a ladder `npu -> crypto -> dma -> fabric`. Findings, tables and caveats:
`Doc: tm:ch:dft-architecture` section 18. Heavy outputs go to `/nobackup/claude_sim_build/j41m15/` (never into git).

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
| `regrade.py` | independent re-grade of the patterns (own simulator + `quaigh simulate` on fault-injected copies); `--sites` samples only the cell-pin sites |
| `regrade_vl.py` | Verilator + Yosys SAT re-grade of a fault sample (shares nothing with Quaigh); preselected mode for `pin_inject.py` |
| `pin_inject.py` | (j41m.20) injects sampled cell-pin faults at the instance pins of the Verilog netlist, then the generic flow + `regrade_vl.py` |
| `cellpin_report.py` | (j41m.20) cell-pin coverage from a Quaigh `--fault-report`: raw, scan-path pins (SCD/SCE) credited, by pin, whole-cut estimate |
| `run_rung.sh`, `Makefile` | the ladder |

Tools: Yosys 0.46 (the flow's), sv2v 0.0.13.1, Quaigh 0.0.6 (pinned external binary, `tools/dft/build_quaigh.sh`).
**Use the patched Quaigh `0.0.6+cvt1` for the fabric** (bead j41m.18, DFT_ARCHITECTURE 18.9): `tools/dft/build_quaigh.sh patched`
applies `quaigh/*.patch` (sparse pattern-detection rows; pattern files byte-identical to stock on timer/npu/crypto/dma,
dma peak 11.42 -> 0.94 GiB) and installs to `/nobackup/claude_sim_build/j41m18/qroot`. Run with
`QUAIGH=/nobackup/claude_sim_build/j41m18/qroot/bin/quaigh W=/nobackup/claude_sim_build/j41m18 make rung-fabric` (5.1 GiB, 50 min). The `dft` devshell in
`flake.nix` provides yosys, sv2v, python; point `QUAIGH=` at the binary.

Quaigh facts relied on (read from its source, DFT_ARCHITECTURE 18.1): `unobservable=N` counts faults whose SAT miter is UNSAT (proven
untestable in the cut); the universe is the collapsed list; `--num-random`/`--num-cycles` switch to random sequential patterns only (no SAT, no
grading), so they are NOT a way to "retry with more random patterns"; a sequential BLIF (`.latch`) is accepted and exposed as full scan.

**Cell-pin fault universe (bead j41m.20, DFT_ARCHITECTURE 18.10).** `mk_cut.py --cellpin` wraps every Liberty cell model so each
port passes through a kept `$_BUF_`, skips `abc`, lowers the primitives to `.names` itself and writes `cut_sites.txt` (the output net
of every pin buffer).  Quaigh `0.0.6+cvt2` (`quaigh/0002-fault-sites.patch`, on top of 0001) grades exactly those faults:
`quaigh atpg|atpg-report --fault-sites cut_sites.txt --fault-report status.txt` (one stuck-at-0/1 pair per pin, no collapsing; the
report gives `k D|U|R|N` per fault).  Without the flags `+cvt2` is byte-identical to `+cvt1` on timer/npu/crypto/dma.  Build:
`PW=<dir> tools/dft/build_quaigh.sh patched` (default `PW` /nobackup/claude_sim_build/j41m20).  The cell-pin cut is checked against
the generic cut by simulation (same outputs on every pattern) and by a formal positional miter (timer).
Fabric result (B3, 944,122 faults): test coverage 99.96 %, fault coverage 88.94 % raw / 94.93 % with SCD/SCE credited, 37 h 57 min,
6.0 GiB peak; the sign-off gate is test coverage only (TM book 18.10 and 2.1).  `cellpin_report.py <cut_dir> status.txt --label L
--out report.json --md` gives the numbers.  A run of more than a few hours must not use the `--scope` of `run_capped.sh` from an
interactive session (the scope ends with the session); start it as a user service:
`systemd-run --user --unit=<name> --collect -p WorkingDirectory=$PWD --setenv=MEM_MAX=12G --setenv=WALL_MAX=72h bash tools/dft/atpg/run_capped.sh <out> -- <cmd>`.

**Yosys SAT trap (fixed in `regrade_vl.yosys_sat_equiv`, j41m.20).** A net in both `.inputs` and `.outputs` of the comb view (a flop
Q feeding the next flop's D) makes Yosys `miter -equiv` + `sat -prove` report EQUIVALENT for a detectable fault (`y = a & q` vs
`y = 0` with `q` dual, Yosys 0.46).  `dealias_dual_ports` gives such outputs their own net; the regression test is in
`tb/tests/test_dft_atpg_regrade_vl.py`.  Re-grades of the generic cuts made before the fix (j41m.15/.18) were re-run.

Not done here: pattern -> scan-chain-order mapping, SVF/TAP replay, SRAM shadowing, delay faults (follow-up beads).
