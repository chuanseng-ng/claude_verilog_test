# Innovus b5g: why the neutral judge does not reproduce the native numbers

Diagnosis only. No ECO, no change to the shared SDC (md5 `3c69635042a9d65cb87e71a9db713e4e`), to the judge scripts, or to any judge baseline result.
All experiments are under `pnr/commercial/signoff/pt/runs_diag_b5g/` (PT runs `e*_*`, Innovus sessions `innovus_b`, partial first session `innovus_a_partial_n0`).
The Innovus sessions are read-only on `runs/b5g_innovus/dbs/06_finish` (nothing saved). Scripts: `runs_diag_b5g/scripts/` (`diag_gap.tcl`, `inn_gap.tcl`, `mk_sdc*.py`, `run_g.sh`, `run_inn.sh`).

Gap (nom_tt): Innovus native setup WNS +0.394 / hold WNS +0.252 / power 92.65 mW; judge (PT on StarRC tuned SPEF, shared SDC) -0.320 / -2.044 / 70.59 mW (variant B).

## 1. Result in one table (every row measured; rows sum to the gap)

Each row changes ONE variable, in this order, native to judge. Setup/hold from Innovus sessions (`innovus_b/inn.log`, lines `WNS <step> ...`) for steps 1 to 3, and the PT judge for step 4.

| # | Contributor (one variable) | Δ setup WNS (ns) | Δ hold WNS (ns) | Δ power (mW) |
|---|---|---:|---:|---:|
| 0 | **Innovus native (b5g)** | +0.394 | +0.252 | 92.65 |
| 1 | SI (crosstalk) aware delay calc ON -> OFF (judge has `si_enable_analysis false`) | +1.034 | +0.371 | n/a |
| 2 | **Hidden, asymmetric I/O clock latency removed** (Innovus `views/av_tt/latency.sdc`, not in the exported SDC) | **-2.909** | **-2.909** | 0 |
| 3 | RC: Innovus tech-LEF-only RC -> StarRC tuned SPEF | +1.233 | +0.026 | -5.41 |
| 4 | Default activity 0.2 (seq + primary input) -> 0.1 (judge) | 0 | 0 | **-16.99** |
| 5 | Engine residual: Innovus -> PT / PrimePower (same SPEF, SDC, activity) | -0.072 | +0.216 | +0.34 |
| = | **Judge (PT, shared SDC, StarRC)** | **-0.320** | **-2.044** | **70.59** |
| | Total Δ (judge - native) | -0.714 | -2.296 | -22.06 |

Check: setup 1.034 - 2.909 + 1.233 - 0.072 = -0.714; hold 0.371 - 2.909 + 0.026 + 0.216 = -2.296; power -5.41 - 16.99 + 0.34 = -22.06.
Step values: setup WNS native +0.3941 -> SI off +1.4279 -> latency off -1.4809 -> StarRC -0.2477 -> PT -0.3199. Hold: +0.2517 -> +0.6230 -> -2.2858 -> -2.2600 -> -2.0437.
Power: Innovus native RC @0.2 92.65 -> Innovus StarRC @0.2 87.24 -> Innovus StarRC @0.1 70.25 -> PrimePower B @0.1 70.59.
Step 2 is exactly 2.909 ns on both setup and hold (the late-latency value `-1.90877` ns on top of the 1.0 ns source latency).

## 2. Root causes

### 2.1 (dominant timing cause) Innovus times with an I/O latency that never reaches the SDC
`clock_opt_design -cts` logs "Innovus updating I/O latencies" and executes
`set_clock_latency -source -early|-late -max -rise -1.90877 [get_pins clk_i]` (fall -1.65153) (`runs/b5f_innovus/logs/04_cts.innovus.log:3632-3638`, same mechanism in b5d).
It is stored as the analysis view's latency file, `runs/b5g_innovus/dbs/06_finish.enc.dat/mmmc/views/av_tt/latency.sdc`, and **`write_sdc` does not export it**: the exported `out/rv32i_cpu_top.sdc` (md5 `97ae278d...`) carries only `set_clock_latency -source 1`. So the SDC the judge gets is not the constraint set Innovus closed against.

Effect (native reports `reports/b5g/final_hold/*all_hold.tarpt.gz` and `final_setup/*`, my sessions `innovus_b/n0_nat_latON/path_*.txt`):
- The late (`-max`) clock path is shifted by -1.909 ns and the early path is not. Data launch in setup and the capture clock in hold use the late value (`Source Insertion Delay -1.909`), whereas I/O ports and the setup-capture clock keep +1.000.
- I/O paths are therefore timed against an ideal-like reference (sink clock arrives at about 1.0 + residual skew, not 1.0 + 2.9 ns tree). This is what makes input hold pass (`axi_rdata_i[13] -> u_icache_data_din_q_reg[13]/D`: native +0.422; judge -2.044).
- **Side effect: native reg2reg is not symmetric either.** Launch is 2.9 ns early relative to capture, so native reg2reg hold WNS is +2.846 ns (physically impossible; real value about +0.12) and the CTS/hold optimisation steered by it saw a distorted picture. With the latency removed (Innovus N1) reg2reg hold is +0.129 and PT gives +0.120/+0.127: reg2reg is genuinely clean, so the b5g reg2reg closure is real; the I/O closure is the part that depends on the hidden latency.
- Validation that the mechanism, not a PT quirk, is the cause: PT with the Innovus semantics rebuilt as an SDC (`sdc/natexact.sdc`: early 1.0 / late -1.90877, I/O on a virtual 1.0 clock) and Innovus's own SPEF (`e5_natexact_nat`) gives reg2reg hold +3.016 and in2reg setup +3.316, versus Innovus with SI off (`n0b`) +3.037 and +3.261: agreement to 0.06 ns.

The same is true of OpenROAD-style flows that do not do this: the judge shared SDC is correct for them. ICC2 does it too, but exports it (section 4).

### 2.2 SI-aware delay calculation is ON natively, OFF in the judge
Innovus `timeDesign -postRoute` uses AAE SI-aware delay calculation; the judge sets `si_enable_analysis false` for every arm. Toggling only `setDelayCalMode -siAware false` (session `n0` -> `n0b`) moves setup WNS +0.394 -> +1.428 (in2reg 0.394 -> 3.261, reg2reg 1.854 -> 4.400) and hold +0.252 -> +0.623. This is a real, large effect (about 2.5 to 2.9 ns on long paths) that the neutral judge intentionally excludes. It is **not** a judge defect, but it means native numbers are SI-pessimistic and judge numbers are SI-free; neither arm's SI-on figure is known to the judge.
Caution: with the symmetric `natlat` SDC and native SPEF the judge setup (+0.408, `e2_natlat_nat`) lands on native +0.394 only by coincidence (-2.909 from latency cancels about +2.87 from SI). Do not read that agreement as validation.

### 2.3 RC: Innovus b5g was extracted with tech-LEF RC only
`scripts/mmmc_tt.tcl` prints "rc_nom has NO qrcTechFile / capTable -> tech-LEF RC only" (b5g `06_finish.log`: "RC-Corner Cap Table : ''"). StarRC with the tuned ITF (calibrated to OpenRCX) differs from it: replacing only the parasitics in Innovus (`spefIn`) gives setup +1.233, hold +0.026, power -5.41 mW. The tech-LEF extraction overstates switching power (Innovus total switching 37.33 mW native vs 31.92 mW with StarRC at the same 0.2 activity, `innovus_b/n2_star_latOFF_siOff/power_act02.txt`; the 5.41 mW is net switching).

### 2.4 Unconstrained ports: the native hold WNS is not on a constrained path
26 input ports have no `set_input_delay` (mbist_cfg_i/mbist_run_i etc.; PT `check_timing`: "26 ports with no clock-relative input delay", 34 unconstrained outputs). PT does not time them; Innovus times them with an undefined clock ('@', input delay 0) and the native hold WNS +0.252 is `mbist_cfg_i[6] -> u_mbist_ctrl_bg_idx_q_reg[2]/D`. The best constrained hold path seen in the native top-100 is `axi_rdata_i[13]` at +0.422. So up to about 0.17 ns of the native hold number is a path the judge cannot reproduce; it is inside step 1/2 of the table (the table is built from all-path WNS in each tool, not constrained-only).

### 2.5 Power: activity assumption, then RC
- Innovus `report_power` defaults to 0.2 for sequential and primary-input activity (`final_power.txt`: "Sequential Element Activity 0.2, Primary Input Activity 0.2"); the judge uses 0.1 (variant B also asserts 0.1 on every register output). Same Innovus, same StarRC SPEF, 0.2 -> 0.1: 87.24 -> 70.25 mW. This is 77 % of the gap.
- RC accounts for 5.41 mW (combinational switching 28.07 -> 23.28 mW).
- PrimePower B vs Innovus at the same SPEF and activity differ by +0.34 mW (0.5 %), and PrimePower B at 0.2 (86.8, `e4_base_star_t02`) vs Innovus 87.24: -0.4 mW. The engines agree.
- Variant A (57.30 mW) is lower again because register-output activity is not asserted; it is a different definition, not part of the native gap. Native "Clock (Combinational)" 8.47 mW vs PrimePower `clock_network` 23.8 mW is a grouping difference (PrimePower includes register clock-pin power in `clock_network`); totals agree after RC/activity are matched.

## 3. What is the right number, and what needs a fix

- **Judge engine: no defect found.** With identical inputs (SDC semantics, SPEF, SI off) PT reproduces Innovus to 0.06 ns (setup) / 0.2 ns (hold, PT less pessimistic by 0.22 with StarRC; unresolved Innovus OCV/CPPR vs PT residual) and PrimePower to 0.5 % in power. Controls: `e0_base_star` reproduces the judge baseline exactly (-0.3199 / -2.0437 / 57.30 / 70.59).
- **Native setup/hold are not valid for the comparison.** They rest on a latency that is not in the exported SDC, asymmetric between late and early paths, with SI on and tech-LEF RC. Not comparable with the ICC2 or OpenROAD native figures, and not reproducible by anyone holding only the SDC.
- **For the comparison, use the judge numbers, labelled by SDC**:
  - shared SDC (b5g was not closed against it for I/O): setup -0.320 (1 endpoint, `apb_pslverr_o`), hold -2.044 (430 `axi_rdata_i` input-hold endpoints); both are I/O-constraint failures, reg2reg is clean (hold +0.120, setup +2.357).
  - symmetric I/O latency equal to b5g's own CTS insertion (2.909 rise / 2.652 fall; `sdc/natlat.sdc`, `e1_natlat_star`): setup +1.039, hold +0.120 (in2reg +0.865), 0 violators. This is the closest neutral statement of "what Innovus actually closed against".
  - the repo's `iolat` SDC (1.778, ICC2's value) gives hold -0.266 on b5g because Innovus's tree is 1.1 ns deeper than ICC2's.
- **Power for the comparison**: judge B at 0.1 (70.59). Native 92.65 is an artefact of the 0.2 default and tech-LEF RC; at the judge's activity Innovus itself says 73.2 mW on native RC (`n0_nat_latON/power_act01.txt`) and 70.25 on StarRC.

### Recommended fixes (not applied; owner decisions)
1. Innovus flow (`impl/innovus/scripts/04_cts.tcl`, `06_finish.tcl`): do not rely on the auto `update_io_latency`. Either disable it and give I/O a symmetric, SDC-visible latency (a virtual I/O clock or `set_clock_latency` on an I/O clock, as ICC2 exports), or export the latency file alongside the SDC and say so. Re-close hold/setup against that symmetric constraint; reg2reg timing during CTS is currently distorted by the +2.9 ns asymmetry.
2. Innovus RC: build the cap table/QRC tech file for `rc_nom` (`run_captbl.sh`/`gen_captbl.tcl` exist, unused by b5g) so native RC matches StarRC; otherwise native power/timing stay 5 mW / 1.2 ns off.
3. Innovus reporting: pin power activity explicitly (`set_default_switching_activity -input_activity 0.1 -seq_activity 0.1`) when quoting power next to PrimePower, and give the 26 mbist inputs input delays (they currently set the native hold WNS).
4. Judge/SDC owner: add the b5g-own-latency (natlat) SDC as a third comparison variant and, if wanted, an SI-on pass; the shared SDC is unchanged. The judge result tables should state that the Innovus native column is not SDC-reproducible.

## 4. Why ICC2 matches and Innovus does not
- I/O latency: ICC2 b5e exports it in the SDC as a clock-level, symmetric `set_clock_latency 1.82137 [get_clocks clk_i]` with `set_propagated_clock [get_ports clk_i]` (`impl/icc2/runs/b5e_icc2/out/rv32i_cpu_top.sdc:483-488`), which the `iolat` SDC (1.778) reproduces, hence hold +0.001 vs native +0.0037. Innovus hides it in a view latency file, with a late-only value, and the export drops it.
- RC: ICC2 used the tuned nxtgrd/TLU+ stack (total C within 0.4 % of StarRC); Innovus used tech-LEF only.
- Activity: ICC2 default is 0.1 (same as PrimePower defaults; 55.9 native vs 55.72 judge A); Innovus default is 0.2.
- SI: ICC2's native run is not SI-pessimised to the same extent (setup native -0.0046 vs PT -0.044 on its own SPEF).
So the ICC2 agreement is not evidence that the judge is correct for Innovus, it shows that when the three inputs agree the judge reproduces the native result.

## 5. Experiment index (all nom_tt, tt lib, PT X-2025.06 / Innovus 23.14)
| Run | SDC | Parasitics | Setup WNS | Hold WNS | Note |
|---|---|---|---:|---:|---|
| `e0_base_star` | shared | StarRC | -0.3199 | -2.0437 | control = judge baseline; power A 57.30, B 70.59 (0.1) |
| `e1_natlat_star` | shared + clk_io 2.909/2.652 | StarRC | +1.0395 | +0.1204 | symmetric Innovus-equivalent I/O latency |
| `e2_natlat_nat` | same | Innovus native SPEF | +0.4076 | +0.1269 | matches native setup by coincidence (section 2.2) |
| `e3_base_nat` | shared | Innovus native SPEF | -1.5436 | -2.2258 | Innovus N1 (-1.4809/-2.2858) agrees |
| `e4_base_star_t02` | shared | StarRC | | | PrimePower A 60.8, B 86.8 at toggle 0.2 |
| `e5_natexact_nat` | early 1.0 / late -1.909 asymmetric | native SPEF | +1.365 (reg2out; in2reg 3.316) | +0.683 (in2reg; r2r +3.016) | reproduces Innovus SI-off asymmetric result |
| `e6_natexact_star` | same | StarRC | | | |
| `innovus_b` N0 / N0b / N1 / N2 / N3 | (see log) | native / StarRC | see table | | N0 native; N0b SI off; N1 latency off; N2 + StarRC; N3 latency on again (+2.661 / +0.649) |
`innovus_a_partial_n0` is the first, interrupted session (N0 only; endpoint dumps empty by a script error); superseded by `innovus_b`.
Not run: Innovus-native `report_power` with StarRC at the PT variant-B register-output assertion (the 0.34 mW residual is the engine/definition difference); per-endpoint native-vs-PT slack join (Innovus endpoint dump failed; the partition WNS and per-path reports were used instead). Coverage: one corner (nom_tt), one layout (b5g); b5d was not re-measured here, but its native flow is identical (same `04_cts.innovus.log` mechanism: `-1.77162` rise), so the same gap mechanism applies (INFERRED, not measured).
