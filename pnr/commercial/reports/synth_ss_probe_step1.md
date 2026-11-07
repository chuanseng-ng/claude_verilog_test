# Step 1: do the commercial v1 synthesis netlists lose at ss? (Sky130 `rv32i_cpu_top`)

PrimeTime X-2025.06 on the three **synthesis** netlists (no P&R), one `pt_shell` session, identical treatment for all three:
ideal clock (no `set_propagated_clock`), **no parasitics of any kind** (no SPEF, no wire-load model), the shared SDC
(`pnr/sky130/cpu/constraints/sky130_cpu.sdc`, md5 `3c69635042a9d65cb87e71a9db713e4e`, asserted in the script), SI off, no derate.
Libraries `sky130_fd_sc_hd` tt_025C_1v80 (nom_tt) and ss_100C_1v60 (nom_ss) + the SRAM `.db` which is **TT-only in both runs (bead `o1i`)**.
Script `pnr/commercial/syn/ss_probe/pt_synth_probe.tcl`, launcher `run_probe.sh`, raw metrics `pnr/commercial/syn/ss_probe/reports/step1_probe_metrics.tsv`.
Wall 46 s for all six analyses under `licensed_lock.sh` + `safe_run.sh` (2 threads).

Netlists (md5):
Yosys/ABC `pnr/sky130/cpu/runs/b2_openroad/06-yosys-synthesis/rv32i_cpu_top.nl.v` `cb24a60d...` (OpenROAD arm, `SYNTH_STRATEGY "DELAY 3"`),
DC-NXT v1 `syn/dc/runs/b3a_dc_tt/out/rv32i_cpu_top.nl.v` `698e56f0...`, Genus v1 `syn/genus/runs/b3b_genus_tt_r2/out/rv32i_cpu_top.nl.v` `d7e7976f...`.

## Setup table (ns; viol = violating endpoints, all of them reg-to-reg)

| Netlist | cells | nom_tt WNS | nom_tt TNS / viol | nom_ss WNS | nom_ss TNS | nom_ss viol | gap to Yosys at ss |
|---|---:|---:|---:|---:|---:|---:|---:|
| Yosys/ABC (DELAY 3) | 30,369 | +4.759 | 0 / 0 | **-1.919** | -130.1 | 152 | 0 |
| DC-NXT v1 | 32,881 | +1.715 | 0 / 0 | **-10.457** | -957.4 | 303 | **-8.54 ns worse** |
| Genus v1 | 26,347 | +5.498 | 0 / 0 | **+0.606** | 0 | 0 | +2.52 ns better |

Hold at the same conditions (ideal clock): tt +0.121 / +0.116 / +0.116, ss +0.455 / +0.449 / +0.434 (Yosys / DC / Genus). Not a differentiator.
The worst setup path is reg-to-reg in all six runs (`worst_r2r_*` identical to `worst_*`).

## What the paths say
- **DC v1 loses 12.4 ns going tt to ss on its worst path (data arrival 11.98 to 23.97 ns, 2.09x on the 11-ns logic part)**, against Yosys 1.82x and Genus 1.66x.
  The path is `ex1a_ex1b_reg_q.immediate[0]` to `ex1c_ex1b_reg_q.dec_redirect_target[31]`: a **ripple-carry chain of ~30 `fa_1`/`fah_1` full-adder cells at 0.8 to 0.87 ns each at ss**
  (the PC + immediate adder). That is exactly the area-recovered structure the assessment predicted: at tt with wire estimates it met 0 ps, so DC had no reason to keep a faster adder architecture.
  Stored in `pnr/commercial/syn/ss_probe/reports/step1_worst_dc_v1_ss.txt`. This is also the endpoint the ICC2 judge names as its worst ss path (`ex1c_ex1b_reg_q_reg_dec_redirect_target__31_`).
- **Genus v1 is not worse than Yosys at ss; it is better** (+0.61 vs -1.92 ns, zero violators). Its logic is also a ripple adder (`a21bo` chain) but the cells are far faster than DC's `fa`.
- At tt the zero-wire slack ranks Genus (+5.5) > Yosys (+4.8) > DC (+1.7), so the DC netlist is intrinsically the slowest of the three even before the corner changes.

## Decision against the gate ("commercial netlists not clearly worse at ss than Yosys, gap under ~2 ns -> STOP")

| Arm | ss gap vs Yosys | Gate | Action |
|---|---:|---|---|
| DC-NXT | -8.5 ns (303 violators, TNS -957) | **confirmed** (gap >> 2 ns) | proceed with the DC v2 MCMM resynthesis |
| Genus | +2.5 ns (0 violators) | **not confirmed** (not worse; better) | **no Genus v2 run** (scripts prepared, see below) |

Consequences for the working assessment:
1. "Both commercial synths optimised tt only and area-recovered to 0 ps, which is fragile at ss" holds for **DC** and is contradicted for **Genus** at the netlist level.
2. The post-route PT judge ss WNS (OpenROAD -3.7, Innovus -7.9, ICC2 -14.9 ns) decomposes against this zero-wire netlist baseline as a post-synthesis penalty of
   about -1.8 (OpenROAD: -3.68 vs -1.92), **-8.5 (Innovus/Genus: -7.9 vs +0.61)** and -4.5 ns (ICC2/DC: -14.9 vs -10.46). For ICC2 most of the loss is already in the DC netlist.
   For Innovus the netlist is fine at ss and the loss is introduced by implementation (placement, wires, CTS skew, the b5g/b5j ECO state), not by the synthesis corner scope.
   A Genus MCMM resynthesis would therefore not be expected to repair Innovus's ss gap on its own.
3. Caveat on this probe: a zero-wire netlist hides what each tool *assumed* for wires. Genus's v1 optimisation saw a large wire estimate (+0.002 ns at tt with spatial RC vs +5.5 ns here, so its estimate was ~5.5 ns of wire on the critical path)
   and DC's SPG saw ~1.7 ns. A Genus netlist that is fast at zero wire but met 0 ps with large estimated wires is not proof that it is wire-robust at ss; only a placed netlist can show that.
   This is why the probe is a *netlist intrinsic-speed* test and not a closure prediction.
4. Prepared but **not run**: `syn/genus/scripts/genus_synth_v2.tcl` and `make -C pnr/commercial/syn/genus genus-synth-v2` (`set_analysis_view -setup {av_ss av_tt} -hold {av_ff av_tt}`; untested beyond a Tcl diff against v1).
   One command if the main thread wants the Genus arm anyway; est. 12 min tool time plus queue.

Provenance/limits: probe script and netlists are committed or in gitignored `runs/` of the producing arm; the OpenROAD netlist is the post-`yosys` stage netlist (`06-yosys-synthesis`),
not the routed one. `SEL-005` once in the log is the first `remove_design -all` on an empty session (harmless). `UITE-416` (90 invalid endpoints) appears identically in all six runs (SDC/SRAM related, symmetric).
The probe's `r2r_*` columns in the TSV count violators only (PT lists only violating paths for the 1e6-path query), so `1e9/0` there means "no violators", not "no reg-to-reg paths".
