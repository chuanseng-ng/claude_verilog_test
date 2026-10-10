# ASAP7 CPU macro netlist vs RTL differential (beads `ma7` / `u99` / `dud4`)

Date 2026-10-10. Question: is the ASAP7 `rv32i_cpu_top` miscompile proven in `u99`/`ma7`
(`DBG_GPR[4]` = `0x30` instead of `0x0c`; `BEQ x2,x3` with 9 == 9 not taken) the same defect that `dud4`
root-caused on Sky130 (Synlig elaborates two hazard-unit port connections as `5'x`)? Test only: no PD run, no
config change, no macro view touched. Statements are tagged MEASURED or INFERRED.

**STATUS: FIRST VERSION (two ma7 programs, yosys `sim`, four netlists). The Verilator matrix, controls and
first-divergence sections are filled in as they complete; see "Not done yet" at the end.**

## Provenance (MEASURED)

Netlists from the PD agent's synthesis-only experiment, `/nobackup/claude_sim_build/dud4/asap7/` (full method,
configs, census and hashes in its `NOTES.md`). sha256 re-verified before use:

| arm | netlist | frontend | sha256 (first 16) |
|---|---|---|---|
| committed | gunzip of `pnr/asap7/soc/macro/rv32i_cpu_top.nl.v.gz` (post-P&R, RTL `999e44a`) | Synlig (config `USE_SYNLIG:true`, inferred) | `a416d23f038065433eafa81553e85b9d599892dc9e6da64ca632563b6d1da0b2` |
| S | Synlig synthesis, unmodified main RTL | Synlig | `a2abef9c8f5d024b...` |
| W | Synlig + the two hazard-unit part-selects routed through a named full-width wire | Synlig | `505b939796da1977...` |
| V | sv2v frontend | sv2v | `c2d7f3f37d7d08bec...` |

RTL for S/W/V = `origin/main` `5eb5f63` (no `rtl/cpu`/`rtl/mem` change since; this branch is based on a later main
with identical CPU RTL). The committed macro was built at `999e44a`; `rtl/cpu` and `rtl/mem` differ from main only by
declare-before-use / `default_nettype` / empty-block cleanups, and the two hazard-unit lines and the regfile are
unchanged, so the RTL reference for the committed arm is `999e44a`.

Committed-netlist physical cells: it instantiates `DECAPx1/2/4/6/10`, `FILLER`, `FILLERxp5`, `TAPCELL` (40,359 lines).
None has a port connection (no power pins in the netlist), so they were **removed** with `asap7/strip_physical.sh`
(function-neutral by construction). All other cells are covered by the Liberty-derived models.

## Method

* Simulator 1 (existing u99/ma7 harness, unmodified): yosys 0.62 `sim`, Liberty-derived cell models
  (`run_cpu_macro_check.sh`, `run_cpu_macro_check_branch.sh`), `asap7_seq_cell_models.v`, `asap7_sram_1rw_256x32_model.v`,
  `tb_cpu_macro_check.v`; one run per (netlist, program), `DBG_GPR[4]` captured by the testbench's APB sequencer
  (`apb_prdata_captured`) and the commit stream from the VCD. Wrapper: `asap7/run_yosys_gate.sh`.
* Every job ran under `systemd-run --user --scope -p MemoryMax=5G -p MemorySwapMax=0`.

## Result 1: the two ma7 programs, yosys `sim`, four netlists (MEASURED)

| netlist | `ma7_straight`: `DBG_GPR[4]` (RTL expects `0x0c`) | `ma7_branch`: `BEQ x2,x3` (x2 = x3 = 9, must be TAKEN) | `ma7_branch`: `DBG_GPR[4]` (expects `0x0e`) |
|---|---|---|---|
| committed (post-P&R) | **`0x30`** FAIL | **not taken**, retires WRONG marker `0x14`, parks at `0x18` FAIL | **`0x2e`** FAIL |
| S (Synlig, main RTL) | **`0x30`** FAIL | **not taken**, parks at `0x18` FAIL | **`0x2e`** FAIL |
| W (Synlig + workaround) | `0x0c` PASS | taken, retires `0x20`,`0x24`, parks at PASS `0x28` | `0x0e` PASS |
| V (sv2v) | `0x0c` PASS | taken, parks at `0x28` | `0x0e` PASS |

Commit streams: committed and S are identical (73 commit edges, same PCs); W and V are identical (70). The straight
program's commit stream (`0x00,04,08,0c,10,14`) is identical on all four; only the data differs.

The failing arms reproduce the u99/ma7 numbers exactly (`0x30`, BEQ not taken). The committed macro and the freshly
synthesised Synlig netlist S (different RTL vintage: `999e44a` vs main, different tool run) fail identically, and the
two netlists that avoid the `5'x` hazard-unit connections (W: same frontend, two lines rewritten; V: other frontend) are
correct. Hypothesis "ma7 = dud4" is **not falsified** by these 2 programs x 4 netlists.

## Not done yet

Verilator cycle-exact comparison and the 6-program table, 31-register x port matrix, controls (positive, negative
fault-injection, X/init), first-divergence analysis, CLAUDE.md update.

## Reproduce

`asap7/gen_cell_lib.sh`, `asap7/strip_physical.sh`, `asap7/run_yosys_gate.sh`, `asap7/build_arm.sh` (Verilator,
RTL and gate arms), `asap7/tb_asap7_cpu_check.sv`, plus the Sky130 programs/compare scripts in `sky130/`.
Netlists are not committed. Scratch: `/nobackup/claude_sim_build/dud4/asap7_sim/`.
