# Cadence Genus synthesis, Sky130 `rv32i_cpu_top` (step B3b)

**Comparison run, no target.** Constraints are `pnr/sky130/cpu/constraints/sky130_cpu.sdc` unchanged (md5
`3c69635042a9d65cb87e71a9db713e4e`, verified by the Makefile; 13.333 ns / 75 MHz). Nothing was tuned to close or to shrink.
Same RTL (28 files, 5 defines, native SystemVerilog, SRAM stub never read), same tt corner and same `dont_use.tcl` as the DC arm
(`dc_synth_summary.md`) and the OpenROAD/Yosys arm (`openroad_summary.md`).

Run dir (gitignored): `pnr/commercial/syn/genus/runs/b3b_genus_tt_r2/` (official run; `b3b_genus_tt` is an identical earlier run whose
power/db/hold outputs were incomplete: same cells, area, flops and slack, so synthesis is deterministic).
Committed copies of the reports (`.txt`, because `pnr/.gitignore` ignores `*.rpt`): `pnr/commercial/syn/genus/reports/genus_*.txt`.
Reproduce: `make -C pnr/commercial/syn/genus genus-synth TAG=b3b_genus_tt_r2 PHYS=1`. Git base: HEAD `223296b`, branch `feat/commercial-pd-sky130`.

## Tool and setup
- Genus 23.14-s090_1, `max_cpus_per_server 2`, under `safe_run.sh` (SAFE_MEM_MAX=6G, 2 threads).
- `read_mmmc pdk/sky130/scripts/mmmc.tcl`, then `set_analysis_view -setup av_tt -hold av_tt` (tt view only; the SDC is read for av_tt only).
  tt Liberty `sky130_fd_sc_hd__tt_025C_1v80` + the patched TT SRAM lib. Genus still loads the ss/ff lib sets (report headers show
  `tc_ss` as library domain 0; cell areas are library-independent, delays are from the tt view).
- **qrcTechFile NOT used**: `build/qrc/nom/qrcTechFile` did not exist (the Techgen nom job was still running; not touched). The rc corners
  therefore use the tech-LEF RC. This is the weakest point of the arm: the extraction deck the signoff will use was not available.
- `read_physical` of the tech LEF, hd cell LEF and the SRAM LEF.
- Physical-aware flow: floorplan = the DC arm's `mk_fp_def.py` output (die 3600x1800, 645 rows, 503 pins fixed) via `read_def`; the 10 SRAMs
  placed at the `macro_placement.cfg` coordinates through `read_def -incremental macros.def` (the instance `.location` attribute is read-only
  in Genus); all 10 are `preserve true` and `is_dont_touch` (lib), bboxes checked. Routing layers met1..met4.
- Flow: `syn_generic -physical` (453 s), `syn_map -physical` (161 s), `syn_opt` (51 s). **iSpatial (`syn_opt -spatial`) was attempted and
  fails with PHYS-1015**: it needs `probabilistic_extraction` and a QRC tech file, which does not exist yet. The final step is therefore a plain
  physical-aware `syn_opt`; interconnect mode in the QoR header is `spatial`. Re-run with iSpatial once Techgen delivers the qrcTechFile.
- Genus defaults for effort and auto-ungroup (the DC arm also used defaults). No area/power targets. `dont_use.tcl` Genus branch: 32 base cells flagged.
- The SDC's `set_max_area 0` is **ignored by Genus** (SDC-200 unsupported), whereas DC honours it for area recovery. This favours DC on area.

## Runtime and memory
| | Yosys/ABC | DC-NXT | Genus |
|---|---|---|---|
| synthesis (compile) | n/a | `compile_ultra -spg` 219 s | generic 453 + map 161 + opt 51 = **667 s** (Genus internal 677 s) |
| whole session wall | n/a | 8:59 (537 s in-session) | **11:44** (`/usr/bin/time`), Genus elapsed 707 s |
| peak RSS | n/a | 1.38 GB | **2.03 GB** (`time -v`); Genus reports 2.6 GB peak memory |
| cores | | 2 | 2 (plus 2 super-thread servers) |

## Three-way QoR (tt corner, comparison run, no targets)
| Metric | Yosys+ABC (OpenROAD arm) | DC-NXT topo (`compile_ultra -spg`) | Genus 23.14 (physical-aware, no iSpatial) |
|---|---|---|---|
| Leaf cells incl. 10 SRAM | 30,369 | 32,881 | **26,347** |
| Std cells (excl. SRAM) | 30,359 | 32,871 | **26,337** |
| Flops (total) | 5,299 | 5,284 | **5,208** |
| Flops by type | all `dfxtp_2` | 4,812 `dfxtp_1`, 229 `_2`, 225 `_4`, 18 `dfrtn_1` | 4,984 `dfxtp` (4,824 `_1`, 127 `_2`, 33 `_4`), 116 `dfxbp` (Q+QN), 86 `sdfxtp` (scan-mux flops used functionally), 17 `dfrtn_1` (negedge, async reset), 4 `dfsbp`, 1 `dfbbn_2` |
| Negedge / async flops | 0 | 18 `dfrtn_1` | 17 `dfrtn_1` + 1 `dfbbn_2` (set/reset, negedge) |
| Latches | 0 | 0 | 0 |
| Std-cell area, um2 | 339,360 | 259,850 (comb 152,847 + seq 107,003) | **251,744** (seq 105,776 + comb 145,968) |
| Inverters / buffers | n/a | 4,980 inv + 2,754 buf = 29,590 um2 | 2,068 inv (7,923 um2) + 228 buf (1,079 um2) |
| SRAM macro area, um2 | 1,907,130 | 1,907,125 | 1,907,125.5 (same 10 macros) |
| Setup slack (ideal clock, SDC uncertainty 0.5 ns) | +4.827 ns, no wires | +0.00 ns (MET), SPG + TLU+ | **+2 ps (MET)**, spatial estimate, tech-LEF RC |
| Critical path | n/a | `fwd_b_ex1c_r` -> ex1a `alu_result[0]`, 74 levels, 12.70 ns | `ex2_ex_mem alu_result[0]` -> `u_if_pc_q[31]`, 12.51 ns data path; top 4 paths within 10 ps, 5th at 118 ps |
| Hold | n/a | +0.12 ns | **NOT RUN** (the three `report_timing` hold forms returned empty; Genus synthesis does not fix hold anyway) |
| Power (vectorless, no clock tree) | 51.9 mW pre-PnR | 47.8 mW | **42.5 mW** (leak 0.23 mW; memory 28.9, register 13.0, logic 0.6; clock row 0, no CTS) |
| DRV after synthesis | n/a | max-tran 4,753, max-cap 1,096, max-fanout 97 | **0 / 0 / 0** by `report_design_rules` (see caveat) |
| Hierarchy in netlist | flat | 3 modules (cpu_top, core, dcache) | 4 modules (cpu_top, `rv32i_core_RESET_PC0`, `rv32i_pipeline_ex1c`, `rv32i_decode`) |
| `assign` statements | n/a | 131 | 131 (same ports: constant/feedthrough outputs) |

Notes on reading the table (comparability caveats):
- Slack is "met with nothing to spare" for both commercial tools: both stop at ~0 and recover area. The Yosys figure has no wires. The three slacks are not comparable.
  Closure comparison belongs to the post-route/PrimeTime step.
- Genus is **not** DC-equivalent in method: tech-LEF RC instead of TLU+/QRC; spatial estimator instead of SPG; no iSpatial; `set_max_area 0` ignored;
  the SDC `max_fanout 16` / `max_transition 0.5` are honoured, OpenROAD's `MAX_FANOUT_CONSTRAINT 8` is not applied (as for DC).
- **The 0 DRV result is not evidence that Genus is cleaner than DC.** DC's SPG placement spreads logic over the 3600x1800 core and its estimates give long
  wires (5.07 ns worst transition). Genus reports its own estimate from a different (quick) placement with tech-LEF RC and the floorplan utilisation is 5.8 %.
  Real DRV counts exist only after place-and-route.
- Genus ends with 76 fewer flops than DC and 91 fewer than Yosys. Part of this is registers with no load: elaboration `check_design` lists about 250 unloaded
  sequential bits (e.g. `mem_wb_reg_o_reg[trap_cause][4..31]`), plus 5 `CDFG-508` unused registers. DC logged 138 constant-register removals (`OPT-1206`). The
  per-register difference was not analysed; LEC will show it.
- Genus used 86 `sdfxtp` cells (the scan-mux flop) as functional enable/mux flops and 116 `dfxbp` (Q and QN). Neither DC nor Yosys did. Not an RTL scan structure
  (`scan_*` ports are unloaded); expect the DFT step to want to know.
- Area is not like-for-like with the post-route 707,819 um2.

## Elaboration and front-end findings
- Native SV read: 0 unresolved references, **0 latches** (power report latch row 0), **0 multidriven combinational or sequential pins**, no out-of-bounds or `'x`
  part-select messages. No struct-member select problem is visible in Genus's front-end (as in DC).
- **The 4 `fwd_b_*` flops exist** in the netlist: `u_core/fwd_b_sel_r_reg[1]`, `fwd_b_sel_r_reg[0]` (`dfxbp_1`), `fwd_b_ex1c_r_reg`, `fwd_b_ex1b2_r_reg`. Wiring
  correctness is the LEC question; this is only the existence check the Synlig/dud4 history calls for.
- Benign warnings: `VLOGPT-37` x4 initial-value assignments on reg (`rv32i_icache.sv:787`, `rv32i_core.sv:1036-1038`, the `_unused_*` suppress signals);
  `VLOGPT-506` x2 unused `keep` attribute (`rv32i_icache.sv:338`, `rv32i_dcache.sv:446`); `CDFG-472` x8 unreachable `default` case items;
  `CDFG-508` x5 removed unused regs in `mbist_ctrl` (`mask_sel_q`, `tg_rd_q[2..3]`, `tg_xm_q[2..3]`); `CDFG-818` default parameters for the top;
  `RTLOPT-55` x20 inferred datapath changed so no datapath optimisation; `LBR-9`/`LBR-81`/`LBR-38`/`PHYS-232`/`PHYS-279` are library and LEF noise
  (decap/diode/lpflow cells, non-monotonic wireload tables, ss lib vs TT SRAM nominal conditions).
- `PHYS-2257`: three pins in the shared pin template (`scan_en_i`, `scan_in_i[0]`, `scan_in_i[1]`) name nets that do not exist in the netlist (unloaded scan ports).
- Final `check_design`: no unresolved references, no empty modules; 8 unloaded ports (`scan_mode_i`, `scan_en_i`, `scan_in_i[1:0]`, `mbist_cfg_i[21:18]`); 131 assigns on output ports.
  `check_timing_intent`: 3 exceptions with no effect, 32+ inputs and the same unconstrained outputs as the DC arm (the SDC has nothing for the `mbist_*` ports).

## Files
Scripts (committed): `pnr/commercial/syn/genus/Makefile` (`genus-synth`, `genus-elab`), `scripts/genus_synth.tcl`, `scripts/rtl_list.sh` (delegates to the DC arm's).
Outputs under `runs/b3b_genus_tt_r2/out/`: `rv32i_cpu_top.nl.v` (3.5 MB) and `.lec.nl.v` (`write_hdl -lec`), `rv32i_cpu_top.sdc` (`write_sdc -view av_tt`),
`lec_rv32i_cpu_top.do`, `post_opt.db` + `post_opt_db_dir`, `fp.def`, `macros.def`; `fv/rv32i_cpu_top/` (Genus verification directory); `reports/`.
Known script gaps (not fixed, comparison data unaffected): `write_def` (both forms), `report_summary`, and the three hold-timing forms fail in this Genus release.

## For Conformal LEC
- Do-file: `pnr/commercial/syn/genus/runs/b3b_genus_tt_r2/out/lec_rv32i_cpu_top.do` (written by `write_do_lec -golden_design rtl`). **Run Conformal with the
  working directory `runs/b3b_genus_tt_r2/`**: it reads `fv/rv32i_cpu_top/{fv_map.v.gz,fv_map.map.do,fv_map.fv.json}` by relative path; absolute paths are used for the
  netlist and the log (`out/lec_rv32i_cpu_top.log`). It needs `$LEC_VERSION` set (it parses it and requires >= 19.10-p100; some steps need >= 21.10).
- Two-step compare (hierarchical for the first leg): (1) `fv_map` vs final netlist `out/rv32i_cpu_top.nl.v` (implementation information, `-use_rtl_names`);
  (2) RTL vs `fv_map` (28 RTL files read with `-define PDK_sky130A -define SCL_sky130_fd_sc_hd -define __librelane__ -define __pnr__ -define SRAM_SKY130 -define SYNTHESIS`).
  Both legs: `set_mapping_method -sensitive`, naming style genus, `%s_reg` register rule. The do-file ends with `exit -f` and errors if the first leg is not PASS.
- Black boxes: the 10 SRAMs, handled as `add_notranslate_modules -library -both sky130_sram_1kbyte_1rw1r_32x256_8` with
  `read_library -liberty -both pnr/sky130/cpu/pdk_lib_patched/sky130_sram_1kbyte_1rw1r_32x256_8_TT_1p8V_25C.lib` and the hd tt `.lib`. `set_undefined_cell black_box`.
  No other black boxes expected (netlist has 4 modules plus library cells and the SRAM).
- Names: Genus flattens generate scopes to `u_core/u_icache_gen_data_sram[0].u_data_sram...` style and registers carry `_reg` suffix (e.g. `u_core/fwd_b_sel_r_reg[0]`);
  the do-file's naming rules and the map file cover this. Expect unmapped/removed points for the unloaded `trap_cause` bits and `mbist_ctrl` registers,
  the 17 `dfrtn_1` + 1 `dfbbn_2` negedge flops, and the 116 `dfxbp` / 86 `sdfxtp` multi-output or scan-mux cells (Conformal must model them from the Liberty).
- **Conformal was not run** here (step B3b is synthesis only); equivalence of Genus's netlist is therefore unproven.
- Not run in this step: ss/ff timing, hold, post-synthesis power with activity, DFT, clock gating (the report exists, no gating was requested).
