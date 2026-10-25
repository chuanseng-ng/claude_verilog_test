# Synopsys DC-NXT topographical synthesis, Sky130 `rv32i_cpu_top` (step B3a)

**Comparison run, no target.** Constraints are `pnr/sky130/cpu/constraints/sky130_cpu.sdc` unchanged
(md5 `3c69635042a9d65cb87e71a9db713e4e`, 13.333 ns / 75 MHz). Nothing was tuned to close or to shrink. Compared with the
OpenROAD/Yosys arm (`openroad_summary.md`, run `b2_openroad`) and later with Genus.

Run dir (gitignored): `pnr/commercial/syn/dc/runs/b3a_dc_tt/` (`dc.log`, `out/`, `reports/`). Committed copies of the
summary reports (renamed `.txt`, because `pnr/.gitignore` ignores `*.rpt`): `pnr/commercial/syn/dc/reports/`.
Reproduce: `make -C pnr/commercial/syn/dc dc-synth` (scripts in `pnr/commercial/syn/dc/scripts/`).
Git base: HEAD `21ae7fe`, branch `feat/commercial-pd-sky130`.

## Tool and setup
- `dcnxt_shell -topographical_mode` X-2025.06-SP3 (NDM mode; plain `dc_shell -topo` is the Milkyway flow), `set_host_options -max_cores 2`,
  under `safe_run.sh` (SAFE_MEM_MAX=6G, 2 threads).
- Corner: **tt_025C_1v80** (`sky130_fd_sc_hd__tt_025C_1v80.db`); SRAM `sky130_sram_1kbyte_1rw1r_32x256_8_TT_1p8V_25C.db` (the patched
  lib, TT only). OpenROAD/Yosys synthesises against the same tt libs.
- NDMs `sky130_hd_tt`, `sky130_hd_phys`, `sky130_sram_1kbyte_1rw1r_32x256_8` + `sky130_hd.tf`. Routing directions read correctly (li1 V, met1 H, ...).
- RTL: native SystemVerilog (`analyze -format sverilog`), the 28 files and 5 defines of `make -C pnr sky130-cpu-sv2v-inputs`
  (`PDK_sky130A SCL_sky130_fd_sc_hd __librelane__ __pnr__ SRAM_SKY130`), no sv2v. The SRAM stub `.v` is not read (the script errors if it is);
  the 10 SRAMs link from the `.db`/NDM and are `set_dont_touch`.
- `dont_use.tcl` sourced (22 cells flagged).
- Parasitics: **TLU+ is valid.** `build/nxtgrd/nom/sky130A_nom.tluplus` (gzip, 166 kB, nominal only) with `starrc_layer.map`:
  `set_tlu_plus_files -max_tluplus X -min_tluplus X -tech2itf_map map`; `check_tlu_plus_files` passes all 3 checks (conducting layers, vias,
  min width/space vs the .tf). The queue log's `tluplus rc=1` was the known tool exit-time crash, not a bad file. min/max TLU+ do not exist,
  so nominal is used for both. `read_parasitic_tech` does not exist in dcnxt. Unvalidated against OpenRCX (part 2b).
- Floorplan (consistent with the OpenROAD arm): die 3600x1800, rows on 20..3580 x 20..1780 lattice of the OR DEF, 503 pins fixed at the
  `pin_template.def` positions (`scripts/mk_fp_def.py` -> `extract_physical_constraints`), the 10 SRAMs at the `macro_placement.cfg` coordinates
  with `set_cell_location -fixed` (DEF cannot name DC's `gen_data_sram[i].u_data_sram` cells). Routing layers met1..met4 (`set_ignored_layers`,
  as RT_MAX_LAYER met4). DC reports `PSYN-111` "coordinates out of the core area" x5: the I-cache SRAMs sit at y=20 and the OR row lattice starts at y=24.48;
  placements were applied (bboxes checked).
- DRV limits: the SDC already sets `set_max_transition 0.5`, `set_max_fanout 16`, `set_max_capacitance 0.1` (outputs), so OpenROAD's
  `MAX_FANOUT_CONSTRAINT 8` was **not** re-applied (per instruction). This is a real difference between the arms.
- Compile: `compile_ultra -spg` (default auto-ungroup kept; SVF written for Formality), then `change_names -rules verilog -hierarchy`.

## Runtime and memory
| | |
|---|---|
| `compile_ultra -spg` | 219 s wall in-script (177 s reported compile wall, 258 s CPU) |
| whole dcnxt session (elab to DC_DONE incl. writes) | 537 s in-session, 8:59 wall under safe_run |
| peak RSS | 1.38 GB (cap 6 GB) |
| elaboration alone | 6 s, 0.76 GB |

## QoR, DC vs Yosys/ABC (tt corner)
| Metric | OpenROAD arm (Yosys+ABC, `06-yosys-synthesis` / `12-staprepnr`) | DC-NXT topo (`compile_ultra -spg`) |
|---|---|---|
| Leaf cells incl. 10 SRAM | 30,369 | 32,881 |
| Std cells (excl. SRAM) | 30,359 | 32,871 |
| Sequential (flops) | 5,299 (all `dfxtp_2`) | 5,284 (4,812 `dfxtp_1`, 229 `_2`, 225 `_4`, **18 `dfrtn_1`**) |
| Std-cell area, um2 | 339,360 | **259,850** (comb 152,847 + seq 107,003) = -23.4 % |
| Buf+inv cells / area | n/a | 7,734 (2,754 buf, 4,980 inv) / 29,590 um2 |
| SRAM macro area | 1,907,130 | 1,907,125 (same 10 macros) |
| Setup slack, ideal clock, nom_tt, SDC uncertainty 0.5 | +4.827 ns (no wires, STA pre-PnR) | **+0.00 ns (MET)**, with SPG/TLU+ wire estimates; hold +0.12 ns |
| Critical path | n/a | `fwd_b_ex1c_r` -> ex1a alu_result[0], 74 levels, 12.70 ns |
| Power (indicative, no activity file) | 51.9 mW pre-PnR, 103.4 mW post-route | 47.8 mW total (dyn 47.7, leak 0.095), vectorless |
| DRV left after compile | n/a at synth | max-tran 4,753 nets, max-cap 1,096, max-fanout 97 (see below) |

Notes on reading this table:
- DC stops optimising timing at slack 0 and recovers area, so +0.00 is "met with nothing to spare", not a measure of headroom. The OR figure is
  an ABC mapping with no wire model, so the two slacks are not comparable. The comparable closure numbers come later (post-route / PT).
- Area is not like-for-like with the post-route 707,819 um2 (which adds tap, fill, antenna diodes, 1,015 clock buffers, repair buffers).
- DC ends with 15 fewer flops than Yosys (5,284 vs 5,299). DC logs 138 constant-register removals (`OPT-1206`, mostly `u_mbist_ctrl/rec_*`);
  how many of those Yosys also removed was not investigated.
- 18 `dfrtn_1` (negative-edge, async reset) appear in the DC netlist; Yosys has none (all `dfxtp_2`). Likely the negedge-launched SRAM-interface
  registers; needs a look in LEC and in CTS (negedge sinks).

## DRC left at the end of synthesis
5,049 of 33,373 nets violate (max-tran 4,753, max-cap 1,096, max-fanout 97), worst 5.07 ns transition on `commit_pc_o[25]` (false-path output, 0.44 pF).
Internal nets are the majority (about 4,550 of the transition violators). Example: `u_core/n3432`, a `clkbuf_1` driving 5 pins with 0.31 pF of wire
(about 2 mm), i.e. the SPG placement spreads the logic across the large core and nets between macro rows and logic are long. This is not DC failing
to size: it is the long-wire situation of this floorplan, the same effect behind OpenROAD's 3,437 nom_tt max-slew violations after route. DC leaves
the repair to the P&R tool. Not tuned (comparison run).

## Elaboration / front-end findings (these matter because of the Synlig struct-select history)
- `analyze`/`elaborate`/`link` all return 1; **0 unresolved references, 0 latches, 0 multi-driven nets, no out-of-bounds or `'x` range-select
  messages**. No struct handling problems: DC's native SV front-end elaborates the struct-member part-selects without warning.
- The Synlig-killed registers are present: `fwd_b_sel_r` (2 bits), `fwd_b_ex1c_r`, `fwd_b_ex1b2_r` -> 4 `fwd_b_*` flops in the final netlist (the
  dud4 defect deleted them). Port-to-flop wiring is therefore at least structurally intact; functional proof is the LEC step.
- Warnings (all benign): VER-708 x4 "declaration initial assignment not supported" (`_unused_*` suppress signals in `rv32i_core.sv:1036-1038`,
  `rv32i_icache.sv:787`; they become undriven unloaded nets); VER-318 x7 signed/unsigned (mbist_ctrl, alu); ELAB-311 x8 unreachable DEFAULT
  branches; VER-329 `parameter` in a local-parameter declaration (axi_pkg.sv:22). Full list: `pnr/commercial/syn/dc/reports/elab_warnings.txt`.
- `check_design` post-compile: 522 unloaded nets (`SYNOPSYS_UNCONNECTED_*`, unused debug outputs), 131 shorted outputs / 131 constant outputs,
  3 nets with multiple pins on one cell, 4 `UCN-1` "net connects multiple ports". The written netlist has **131 `assign` statements** and 526
  `SYNOPSYS_UNCONNECTED` names (no `set_fix_multiple_port_nets` was applied, nothing was tuned for P&R hand-off).
- `check_timing`: 26 input ports have no clock-relative input delay and 63 endpoints are unconstrained (the SDC has no constraints for the
  `mbist_*` ports; same in the OpenROAD arm).
- Hierarchy after `compile_ultra` auto-ungroup: only `rv32i_cpu_top`, `rv32i_core_00000000`, `rv32i_dcache` remain in the netlist (3 modules).
  The I-cache and the rest were ungrouped; their SRAMs are `u_icache_gen_data_sram_N__u_data_sram` / `u_icache_u_tag_sram` inside `rv32i_core`,
  the D-cache ones `gen_data_sram_N__u_data_sram` / `u_tag_sram` inside `rv32i_dcache`.

## Files
Scripts (committed): `pnr/commercial/syn/dc/Makefile` (`dc-synth`, `dc-elab`), `scripts/dc_synth.tcl`, `scripts/mk_fp_def.py`, `scripts/rtl_list.sh`.
Outputs under `pnr/commercial/syn/dc/runs/b3a_dc_tt/out/` (gitignored): `rv32i_cpu_top.nl.v` (3.5 MB), `.sdc` (3.6 MB, `write_sdc` includes ~69k
per-pin annotations from SPG, use with care), `.ddc`, `_final.ddc`, `_precompile.ddc`, `_elab.ddc`, `rv32i_cpu_top.svf`, `fp.def`, `rv32i_cpu_top_fp/` (ICC2 handoff).
Reports (`reports/`): `qor`, `area_hier`, `timing_max10`, `timing_summary`, `timing_min`, `power`, `cellcount`, `check_design_*`, `constraints_head`.

## For Genus and for the Formality LEC step
- **SVF** is `out/rv32i_cpu_top.svf` (binary format, written with `set_svf` before `analyze`; closed with `set_svf -off`). Read it in Formality with
  `set_svf` before `read_sverilog`. Ungrouping and `change_names` renames are recorded in it. RTL for the reference: the same 28 files and
  5 defines, `-r` containers; implementation = `rv32i_cpu_top.nl.v` plus the Sky130 `.db` (cells) and the SRAM `.db`/blackbox. The SRAM
  instances must be treated as matched black boxes (same cell name `sky130_sram_1kbyte_1rw1r_32x256_8`).
- Expect in LEC: 138 constant register bits removed (mostly `u_mbist_ctrl/rec_*`), the 18 `dfrtn_1` negedge flops, ungrouped hierarchy with
  flattened names (`u_icache_gen_data_sram_0__u_data_sram`; DC replaced `.` / `[ ]` of generate scopes by `_`), `assign` feedthroughs for the 131 shorted outputs.
- The run is **not** a single-variable comparison with the OR arm: (a) SDC `max_fanout 16` vs OR `MAX_FANOUT_CONSTRAINT 8`; (b) DC uses SPG wire
  estimates from the TLU+ with a placement of its own; (c) default `compile_ultra` effort and auto-ungroup; (d) nominal TLU+ for min and max.
- For a Genus run: use the same SDC (same md5), the same `dont_use.tcl` (Genus branch), the same tt corner, and `mmmc.tcl` (note: qrcTechFile not built
  yet, Genus will use tech-LEF RC unless Techgen has finished). Same floorplan inputs: `scripts/mk_fp_def.py` output `out/fp.def` plus the
  `macro_placement.cfg` coordinates. DC's `.ddc` and netlist should not be fed to Genus; start from the RTL.
- Not run here: ss/ff timing (PT), LEC, post-synthesis power with activity, scan/`insert_dft`, clock gating.
- Known unexplained item: DC's SPG flow table prints "Number of Dont Touch Cells 4570" while only the 10 SRAMs carry `dont_touch` in the ddc
  (checked on the precompile and final ddc). Probably an internal count; no effect seen.
- `write_parasitics -format spef` is not a valid format in DC (`WP-1` error, caught); removed from the script, no SPEF was produced.
- Source-tree state: `pnr/commercial/syn/dc/runs/probe/` is a throw-away elaboration probe (gitignored).
