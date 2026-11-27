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
| `untestable_audit.py`, `audit_graph.py` | (j41m.25) sample audit of the SAT-proven untestable cell-pin faults: seeded sample per pin class, cause per fault (tie-off / constant from logic / redundant / cut artifact), independent SAT (python-sat Glucose, not Quaigh), exclusion counterfactual, negative control on detected faults, Wilson extrapolation; `sample` / `analyse` / `report` subcommands |
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

Not done here: SVF, SRAM shadowing, delay faults (follow-up beads).  Pattern mapping and the gate-level replay are in the next section.

**Untestable-fault audit (bead j41m.25).** No new ATPG run: it reads the B3 `status.txt`, the `cut5` BLIF and `netlist_cellpin.v`.
`python3 untestable_audit.py sample --cut-dir cut5 --status B3/status.txt --out sample.json` (seed 244, 50 per top-10 pin class plus a
pooled 50 for the rest, and 5 detected faults per class as a negative control), then
`PYTHONPATH=<dir with python-sat> run_capped.sh <out> -- python3 untestable_audit.py analyse --cut-dir cut5 --netlist cut5/netlist_cellpin.v --sample sample.json --out analysis.json`
(about 5 min, under 1 GiB), then `untestable_audit.py report --analysis analysis.json --md`.  `python-sat` is the only extra
dependency (`pip install --target DIR python-sat`).  The cell-level constant analysis reads `assign net = 1'bV;` lines of the prepped
netlist as the cut's exclusion ties; the free-mode counterfactual re-runs each fault with those nets free.

## Pattern mapping and gate-level scan replay (bead j41m.19)

No module rung (npu, crypto, dma) has a scan netlist: `synth_module.sh` is a plain Yosys synthesis and the cut assumes full scan.  The only
scan-inserted netlist is the fabric post-fill netlist (RUN_2026-10-28_05-14-30, 6 fabric chains), so the replay runs on `soc_top` with the
cell-pin cut (`cut5`, 21,660 patterns of run B3).  Heavy outputs: `/nobackup/claude_sim_build/j41m19/`.

| File | Role |
|---|---|
| `pattern_map.py` | cut `.inputs` / `.latch` Q / `.outputs` / latch D -> (chain, position) or pin or black-box port or fixed value; chain order from the SCD walk through hold buffers; refuses unmapped bits; masks the 94 hold-masked D bits; checks that a clock PI reaches no data endpoint.  Pure helpers: `chain_load_stream`, `chain_unload_stream`.  Pytest: `tb/tests/test_dft_pattern_map.py` |
| `replay_netlist.py` | rewrites the post-fill netlist for simulation: the 3 black boxes and the unscanned free latch become `rp_fv` / `rp_ov` vectors, single stuck-at faults at instance pins get runtime selects `fsel_k` (one build serves all faults), wrapper `replay_top` with `pi_vec` / `po_vec` |
| `replay_vectors.py` | selected patterns + `quaigh simulate --expose-ff` expected response -> `pi/po/ld/ex/mk.hex` and `params_h.h` |
| `replay_main.cpp`, `build_replay.sh` | Verilator 5.048 build of the gate netlist with the PDK functional models (`VL_OPT=-O0` about 36 min, `-Os` about 50 min, 3.8 GiB RSS) and a separate C++ harness (seconds to rebuild): modes `flush`, `pat`, `tapid`; `+tap=0|1`, `+fault=k`, `+npat=N`, `+dump=chain`, `+bypass=0` |
| `fault_sample.py`, `run_replay.py` | seeded fault sample (detected by the first 300 patterns / SAT-proven untestable / SCD / SCE) and the run table |
| `replay_tb.sv` | first, SystemVerilog version of the bench (superseded by the C++ harness: any bench change recompiled the whole netlist) |

Flow: `quaigh simulate --expose-ff cut.blif -i P.test -o E.test`; `pattern_map.py cut.blif sim.v --cut-info cut_info.json --hold-mask --allow-free --out map.json`;
`fault_sample.py`; `replay_netlist.py`; `replay_vectors.py`; `build_replay.sh`; `run_replay.py`.  Quaigh `0.0.6+cvt2` (`j41m20b/qroot`) `atpg-report --fault-report`
gives the per-fault status of a pattern prefix.

Protocol (TM 14.14): scan_mode, three `scan_clk_i` edges with `scan_en=0`, spare edges, then shift; capture = `scan_en=0`, apply PIs, compare POs, one edge,
`scan_en=1`, unload overlapped with the next load.  Pin mode uses the cut's own conditions (scan_mode_i=1, TAP held in reset).

Findings on the shipped netlist (all measured, see the experience record `j41m19-final`):
- the three scan-entry edge-detect flops (`scan_s1_q`, `scan_s2_q`, `scan_prev_q`, chain 3) are scan flops, so `crypto_wipe_done` (and with it `dft_scan_en` and the six `scan_out_o` gates) falls at shift edge 1: no chain shifts;
- the replay therefore holds the wipe-done pins and the async reset gates (80 gate outputs) at 1 during shift phases only (`+bypass=0` turns that off): a what-if, not the shipped design.  With it, chains 0, 1, 2, 4 flush `0011...` exactly; chains 3 and 5 still lose every 1 (cause not found).
- the clock-switch enable latch `_155911_` (`dft_clk_switch.en_b_q`) is the cut's only free pseudo-input; the harness forces it to 1 (its pin-mode value; it reaches no data endpoint).
- TAP entry (`+tap=1`, `+mode=tapid`) is NOT demonstrated: the harness reads IDCODE shifted by one bit and no IR value raised `dft_scan_mode`; the TAP serial path to the chains is a 1-bit stub (STAGE2_CHAIN) anyway, so only the PARALLEL entry exists.
