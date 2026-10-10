# tools/dft - Stage 0 DFT experiments (bead j41m.1, GH #244)

Throwaway-grade, reproducible. Outputs go to `/nobackup/claude_sim_build/dft_stage0/` (never into git).
Findings and interpretation: `docs/design/DFT_ARCHITECTURE.md`. Paths below use the store paths seen on the
author's host; re-resolve them with `nix-shell` in the LibreLane checkout if they have been GC'd.

| Binary | Path / how obtained |
|---|---|
| OpenROAD used by the Sky130 flow (rev `edf00dff...`) | `/nix/store/784j83ynrvz85rsqnlz32fzvby4wabaz-openroad-python3-3.11.9-env/bin/openroad` (`nix-shell` in LibreLane, `which openroad`) |
| OpenROAD 26Q2 (ASAP7 override) | `/nix/store/hgqrwa4687mf7n0y2x6lcgx1kj42sfga-openroad-26Q2/bin/openroad` |
| Yosys 0.46 (flow's) | `/nix/store/zdhr86kv5rxlp0s58rzxk1aki1igankx-yosys-with-plugins-python3-3.11.9-env/bin/yosys` |
| sv2v | `/nix/store/bknj130bjxz018c73yawkjmbzjhppqbc-sv2v-0.0.13.1/bin/sv2v` |
| Quaigh 0.0.6 | `bash build_quaigh.sh` (cargo, throwaway `CARGO_HOME`, nothing installed system-wide) |

Run from a scratch dir containing `tt.lib`, `cells.lef`, `tech.lef` symlinked to the sky130A `sky130_fd_sc_hd`
files (`__tt_025C_1v80.lib`, `sky130_fd_sc_hd.lef`, `sky130_fd_sc_hd__nom.tlef`).

1. `help_probe.tcl` - which DFT commands does a given OpenROAD expose.
2. timer experiment: `sv2v --top=timer rtl/soc/apb4_register_bank.sv rtl/periph/timer.sv > timer.v`;
   `yosys synth.ys` (replace `LIB` with `tt.lib`) -> `timer_syn.v`; `openroad dft_timer.tcl` -> `timer_scan.v`;
   `python3 chain_check.py timer_scan.v scan_in_1 scan_out_1` (structural chain walk).
3. `toy.v` + `toy_edf.tcl` / `toy_26q2.tcl` - two clocks, neg-edge flop, latch, clock gate: what the stitcher does.
4. `soc_dft.tcl` (env `MODE`, `NCH`) - scan_replace + insert_dft on a full SoC synthesis netlist.
5. `lib_setup.py <lib> <cells...>` - D/SCD/SCE setup and clk->Q at the middle table point.
6. ATPG: `yosys cut.ys` (full-scan cut, flops exposed as ports) -> `timer_cut.blif`; `quaigh atpg timer_cut.blif -o t.test`.
7. Crypto exclusion (decision 3): `python3 crypto_cone.py soc_top.nl.v --emit-instances excl.txt` (cone/fault-proxy numbers);
   `MODE=no_mix NCH=4 EXCL=excl.txt openroad soc_dft_exclude.tcl` (`set_dont_touch` is honoured);
   `python3 check_scan_exclusions.py scan_netlist.v --expect 256` (gate; exits 1 on violation; negative control = the full-scan netlist).
