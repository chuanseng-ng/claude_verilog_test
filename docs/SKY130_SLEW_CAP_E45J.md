# Sky130 SoC max-slew / max-cap: root cause and the RC-calibrated repair (bead `e45j`)

**Status 2026-10-09.** Mechanism found, fix measured on four runs. Section 5: confirmation on current RTL failed the
max-cap gate on one net, so NOT adopted as default. Section 6: the same-config repeat is **bit-identical** (the flow is
deterministic here, run-to-run noise is zero), and a single-variable wire-length run cut max_ss slew 423 -> 102 but
left the same one cap violation, so still NOT adopted. Bead left **open** (cap 1, slew 102-423; not 0). Everything here
is measured from run artifacts unless marked *inference*.

## 1. The earlier root cause was only half right

`e45j` attributed the violations to "repair runs on GRT-estimated parasitics, there is no post-RCX repair
stage". Two corrections, both measured on the Gate B baseline `RUN_2026-10-05_06-50-11`:

1. **The "0/0/0 at steps 33/40/41" figures were nom_tt only.** Mid-PnR STA (`OpenROAD.STAMidPNR`) runs a
   single corner (`DEFAULT_CORNER = nom_tt`); the other eight corners' values in each step's
   `state_out.json` are stale copies from step 9. Step 51 is the first all-corner measurement, so the
   headline "0 -> 8357" compared one corner with nine.
2. **The repair steps are corner-aware; the estimator is the problem.** Loading the step-40 ODB, re-running
   global routing in-session and reporting per corner gave **max_ss slew 307 (277 on ANTENNA pins), cap 0,
   and 0 at every tt/ff corner** -- versus 7622 / 140 after RCX. So at the GRT estimate the design was
   already almost clean at the worst corner; the post-RCX gap is the estimated RC being too optimistic.

Why: the sky130 tech LEF gives ground-only per-layer C (met1 0.085 fF/um ... met5 0.088 fF/um, no
coupling or fringe). `estimate_parasitics -spef_file` on the same ODB compared with the OpenRCX SPEF of the
same nets (17 525 nets with C > 5 fF), total RCX / estimate:

| RC corner | sum C | sum R | per-net median C | per-net median R |
|---|---|---|---|---|
| min | 1.69 | 0.62 | 1.58 | 0.58 |
| nom | 1.88 | 1.02 | 1.76 | 1.00 |
| max | 2.04 | 1.91 | 1.93 | 1.93 |

Every repair step therefore sized buffers against roughly half the capacitance that routing later delivers.
(A post-RCX repair stage would also work, but it is not needed to reach this result and it is the option
that needs the shared-LibreLane edit evaluated in `LIBRELANE_PATCHING_EVALUATION.md`.)

Two more measured facts:
* **ANTENNA diode pins are 26 % (max_ss) to 76 % (nom_tt) of violating pins** in the baseline, but they sit
  on the same nets as ordinary sinks, so excluding them shrinks the count, not the set of bad nets. On
  max_ss the 5 639 non-diode violating pins lie on **314 distinct nets**.
* **`set_max_fanout` really is absent**, and the unconstrained distribution is large: baseline netlist has
  5 181 nets with fanout > 10, 1 258 > 32, 51 > 100 (max 217).

## 2. The fix: project-local plugin, no edit to the shared LibreLane install

`pnr/sky130/soc/plugin/librelane_plugin_cvt_sky130/` (LibreLane imports any `librelane_plugin_*` on
`PYTHONPATH`; the Makefile adds the directory). It defines `CVT.RepairDesignPostGPL`,
`CVT.ResizerTimingPostCTS`, `CVT.RepairDesignPostGRT`, `CVT.ResizerTimingPostGRT`, subclasses of the stock
steps that run the **stock script unchanged** through `tcl/cvt_wrap.tcl`. The wrapper renames Tcl `source`
so `tcl/rc_calibration.tcl` runs right after `common/set_rc.tcl` and rescales the per-layer RC per STA
corner (`CVT_RC_CALIBRATION`, e.g. `nom=1.88,1.02 min=1.69,0.62 max=2.04,1.91`, the table above).
Verified by dumping the estimate before/after: total estimated C scales 1.87 / 2.02 and R 1.02 / 1.91 for
nom / max as set. Empty variable = byte-identical pass-through.

Run it: `make -C pnr librelane-sky130-soc-rccal-noklayout` (selects `config_rccal.json`, which is
`config.json` plus `meta.substituting_steps` and `CVT_RC_CALIBRATION`; `config.json` is untouched).

Two plugin gotchas found: `TclStep` moves non-allowlisted env into the `_TCL_ENV_IN` file, so a wrapper
must `source` it before reading its own variables; and `set_layer_rc` wants kohm/um and pF/um (a first
attempt with C off by 1e12 collapsed the estimate 67x, caught by the dump).

## 3. Result

Baseline `RUN_2026-10-05_06-50-11` (the Gate B run; its config keys and numbers match f7vs.15's close
reason) vs `RUN_2026-10-06_22-43-34` (`config_rccal.json`). **RTL caveat:** `dma_engine.sv` was pinned to its
Gate B version (`49ace76`) for the run, because `857750c` landed afterwards; the run therefore changes
exactly one thing. All 62 steps completed; the only deferred error is the 8 984 Magic DRC of bead `45a`.

| | baseline | RC-calibrated |
|---|---|---|
| max_ss slew / cap violating pins | 7622 / 140 | **295 / 0** |
| nom_ss | 2648 / 78 | 143 / 0 |
| min_ss | 1669 / 33 | 5 / 0 |
| max_tt | 2331 / 3 | 209 / 0 |
| nom_tt | 1016 / 1 | 64 / 0 |
| max_ff / nom_ff / min_tt / min_ff | 1661 / 944 / 876 / 753 (cap 2/0/0/0) | 122 / 53 / 0 / 0 (cap 0) |
| max_ss slew, non-diode pins (distinct nets) | 5639 (314) | **97 (33)** |
| max_ss slew composition ANT / other / SRAM | 1983 / 5609 / 30 | 198 / 81 / 16 |
| antenna nets / pins | 210 / 305 | **184 / 259** |
| setup worst slack (all corners) | +0.579 ns | **+3.276 ns** |
| hold worst slack | +0.279 ns | +0.275 ns |
| setup / hold violators | 0 / 0 | 0 / 0 |
| Netgen LVS | PASSED | PASSED |
| routing DRC | 0 | 0 |
| Magic DRC (bead 45a) | 8984 | 8984 |
| stdcell area / utilisation | 1 703 620 um2 / 44.84 % | 1 778 150 um2 / 45.20 % |
| power | 81.0 mW | 80.9 mW |
| fanout > 10 / > 32 / > 100 nets | 5181 / 1258 / 51 | 5839 / 694 / 26 |

Max-cap is **0 at all nine corners**, which is the gate `Checker.MaxCapViolations` would apply
(`TIMING_VIOLATION_CORNERS = ['*']`). It is still `--skip`ped: the checker was not executed on this run, only
the metric read. Max-slew is not 0, so `Checker.MaxSlewViolations` stays skipped.

Unlike the margin-raise (`e45j`, 2380 slew, +50 antenna nets) and the antenna-effort raise (`58q`) that
traded against each other, this lever **improved both axes at once** and bought +2.7 ns of setup margin on
the thin max_ss path. The antenna improvement is *inference-level* explained: fewer late-added repair buffers
because the repair was sized correctly the first time.

## 4. What is left (max_ss 295)

* 16 pins on the SRAM macro inputs: checked against the relaxed 0.5 ns limit of `sky130_soc.sdc:120-124`;
  inherits bead `o1i`, not a buffering problem.
* 198 ANTENNA diode pins at max_ss (*inference*: they sit on the same nets as real sinks, in line with the
  baseline pattern, and are the `58q` mirror effect; not re-mapped to nets in this run).
* 97 non-diode pins (81 non-SRAM) on 33 distinct nets; the worst have 8 violating pins each (e.g.
  `net3131`, `net3132`, `net23978`, `cpu_bridge_s_wdata[19]`). The nets are resizer-generated names and
  were not traced back to RTL signals.

Next experiments, each a single full run (~4 h on this host): (a) raise the C multipliers a further ~10 %
(the median ratios are below the sum ratios used, but long nets dominate slew); (b) set
`GRT_DESIGN_REPAIR_MAX_WIRE_LENGTH` (untried; the resizer auto-picks 6 335 um); (c) a real `set_max_fanout`
in the PnR SDC (changes repair behaviour: 5 839 nets exceed 10). A post-RCX ECO pass stays an option only if
(a)-(b) do not reach 0.

Single-run caveat: one full run per arm; no repeat was made, so run-to-run noise on the slew counts is not
characterised (the antenna and setup differences are large against the historical drift on this design).

## 5. Confirmation run on current RTL (2026-10-08): NOT adopted

User decision 2026-10-08: adopt the RC-calibrated flow as the default Sky130 SoC flow and un-skip
`Checker.MaxCapViolations` **if** a confirmation run on current `main` RTL matches section 3. Run:
`RUN_2026-10-08_05-21-39` (`make -C pnr librelane-sky130-soc-rccal-noklayout`, `origin/main` at `3ad22f8`, no
`dma_engine.sv` pin, so it carries the `wdmo` DMA fix and the `3xtv` `axi_lite_interconnect` fix; all 62 steps
ran, sole deferred error is the 8 984 Magic DRC of bead `45a`). **Acceptance failed on max-cap**, so no default
was changed and `Checker.MaxCapViolations` stays skipped.

| (violating pins unless noted) | Gate B `RUN_2026-10-05_06-50-11` | rccal `RUN_2026-10-06_22-43-34` (pinned DMA) | rccal confirm `RUN_2026-10-08_05-21-39` (current RTL) |
|---|---|---|---|
| max_ss slew / cap | 7622 / 140 | 295 / 0 | **423 / 1** |
| nom_ss | 2648 / 78 | 143 / 0 | 189 / **1** |
| min_ss | 1669 / 33 | 5 / 0 | 16 / **1** |
| max_tt | 2331 / 3 | 209 / 0 | 257 / **1** |
| nom_tt | 1016 / 1 | 64 / 0 | 95 / **1** |
| min_tt | 876 / 0 | 0 / 0 | 12 / **1** |
| max_ff / nom_ff / min_ff slew | 1661 / 944 / 753 | 122 / 53 / 0 | 254 / 46 / 11 (cap 0) |
| max_ss slew ANT / other / SRAM | 1983 / 5609 / 30 | 198 / 81 / 16 | 304 / 102 / 18 |
| antenna nets / pins | 210 / 305 | 184 / 259 | 205 / 273 |
| setup worst slack / violators | +0.579 ns / 0 | +3.276 ns / 0 | +3.329 ns / 0 |
| hold worst slack / violators | +0.279 ns / 0 | +0.275 ns / 0 | +0.282 ns / 0 |
| Netgen LVS / routing DRC | PASSED / 0 | PASSED / 0 | PASSED / 0 |
| Magic DRC (bead 45a) | 8984 | 8984 | 8984 |
| stdcell area / utilisation | 1 703 620 um2 / 44.84 % | 1 778 150 um2 / 45.20 % | 1 780 450 um2 / 45.21 % |
| instances | 315 038 | 314 625 | 312 320 |
| power | 81.0 mW | 80.9 mW | 84.9 mW |

**The single cap violation.** All six tt/ss corners fail on the same driver, `_078722_/X`, a
`sky130_fd_sc_hd__o22a_4` that drives `cpu_bridge_s_rdata[12]` (the `cdc_gray_fifo` R-channel read mux,
`cdc_gray_fifo.sv` `mem_q[rd_bin_q]`, bead `7ohm`): 0.614 pF against a 0.530 pF limit at nom_tt (+16 %) and
0.643 pF against 0.333 pF at max_ss; ff corners have no cap violation (the same driver also appears in the nom_tt slew list, 1.63 ns against 1.50 ns). `RepairDesignPostGRT`
(step 37) logged "Found 296 slew violations / 18 capacitance violations ... Inserted 34 buffers in 148 nets"
and the estimate-side `nom_tt` metric was 0 afterwards, so this net was inside the repair target on the
calibrated GRT estimate and exceeded it only after RCX (*inference*: a detour or an unbuffered long wire that
the calibrated estimate under-counts on this one net; not traced to a route length in this run).

**Reading.** Max-cap 0 at nine corners was *not* a stable property: it held on the pinned-DMA run and failed on
one net on current RTL. Un-skipping would therefore turn `librelane-sky130-soc` into a failing flow (from
`checker.py` `TimingViolations.check_timing_violations`: any violating corner matched by
`TIMING_VIOLATION_CORNERS = ['*']` raises a `DeferredStepError`; read from source, the checker was not
executed). Slew and antenna moved the wrong way against the previous rccal run, by 43 % (max_ss 295 -> 423),
2.1x (max_ff 122 -> 254), +11 % antenna nets, but remain about 18x better than Gate B on max_ss. Noise
reasoning: the netlist is different (312 320 vs 314 625 instances, -0.7 %, different DMA and interconnect RTL),
so placement and routing are a different random draw; one run per arm cannot separate that from a real
effect. The deltas in slew and antenna are therefore uncharacterised, not evidence of a regression in the
flow; the cap violation is a hard fail of the stated acceptance gate regardless of cause.

**Not done.** No default, `Makefile`, `config.json` or checker skip was changed. The recommended next step is
one more single-variable run toward cap 0 (the +10 % C multipliers, or `GRT_DESIGN_REPAIR_MAX_WIRE_LENGTH`),
and a repeat of the *same* config on the same RTL to measure run-to-run noise before adopting anything.

## 6. Noise repeat and the wire-length experiment (2026-10-08/09): still NOT adopted

User decision 2026-10-08: experiment first, adopt `config_rccal` as default (and un-skip `Checker.MaxCapViolations`)
only if max-cap is 0 at all nine corners with LVS PASSED, routing DRC 0, setup/hold 0 violators, and slew/antenna
no worse than the confirmation run within measured noise. Both runs below used `origin/main` `944d8c5`, whose
`rtl/` and `pnr/` are identical to the confirmation run's `3ad22f8` (`git diff --stat 3ad22f8 944d8c5 -- rtl pnr` is
empty; the intervening commits are tests and docs).

### 6.1 Noise: the flow is bit-deterministic here (measured)

Run 1 (`RUN_2026-10-08_21-07-20`, exact `config_rccal.json`, same RTL, a different worktree path) was compared with
the confirmation run `RUN_2026-10-08_05-21-39`. After normalising the worktree path embedded in net names, the
synthesis netlist and the DEFs after global placement, CTS, global routing, step 37, step 40 and detailed routing
have identical checksums; the step-37 repair logs match line for line (296 slew / 18 cap violations, 34 buffers in
148 nets, 40 resized); and every step-51 metric is equal: slew at all nine corners (max_ss 423 ... min_ff 11), cap
(1 at the six tt/ss corners), antenna 205 nets / 273 pins, 312 320 instances, 45.2134 % utilisation, 84.89 mW,
setup +3.3286 / hold +0.2822 ns, route wirelength 7 502 911. So the run-to-run noise on slew, cap and antenna is
**zero for identical inputs**: every difference in a changed-input run is a real response to the input, though the
response of a chaotic flow to a small input change is still one sample per arm. Run 1 was stopped at step 52
(IR-drop report) once the post-RCX metrics proved identical; steps 53-62 (Magic, LVS, DRC) were **not** repeated
(LVS PASSED / Magic 8 984 on the confirmation run carry over by determinism: *inference*).

### 6.2 Why the one cap violation survives (measured on the confirmation run)

The single violating driver `_078722_` (`sky130_fd_sc_hd__o22a_4`, max_capacitance 0.5301 pF) drives
`cpu_bridge_s_rdata[12]`. Everything about this net is an outlier:

* **Load**: one functional sink, the CPU macro pin `axi_rdata_i[12]`, plus 12 `diode_2` antenna cells (0.0009 pF
  each). The macro's Liberty gives that pin **0.2464 pF**, against a median of 0.0083 pF over its 92 input pins
  (next largest 0.1305 pF `apb_paddr_i[4]`, then 0.0658 pF). The post-RCX SPEF wire cap is 0.358 pF. 0.358 + 0.2464
  + 12 x 0.0009 = 0.615 pF, matching the 0.614 pF reported.
* **Length**: 2 196.5 um routed, rank 54 of 117 008 nets (p99 = 854 um, p99.9 = 1 871 um). The global-routing
  guide for the net at step 37 already spans 1 518 x 669 um, so the calibrated estimate saw the same length: this is
  not an under-counted detour.
* **Repair never touched it**: the net is `o22a_4 -> macro pin` unchanged at step 33 and 37; only the antenna step
  added the 11-12 diodes (they add ~0.01 pF, not the cause). The driver is already the largest drive in its family.

So the cause is a long wire into a macro input whose characterised pin capacitance is ~30x the median, not an
RC-estimator error: at ~0.16 fF/um (the calibrated nom value) the estimate for 2 190 um is ~0.35 pF, which together
with the 0.246 pF pin already exceeds 0.53 pF. The earlier "inference" in section 5 (a detour that the estimate
under-counts) is superseded.

### 6.3 The single-variable run: `GRT_DESIGN_REPAIR_MAX_WIRE_LENGTH = 1500`

Choice (justified from 6.2): the failing net is a long point-to-point wire, not high fanout, and its estimate is
already calibrated, so a further +10 % on the C multipliers would barely move a net that is 15 % over the limit by
a different mechanism, and would perturb every net. A wire-length cap targets exactly long wires. The stock auto
value is 3 205 um (`RSZ-0058` in the step-37 log), which never touches a 2 196 um net; 1 500 um is the smallest
perturbation that splits it. `config_rccal_wl1500.json` is `config_rccal.json` plus that one key (verified by `diff`
and by `resolved.json`); `config.json` and `config_rccal.json` are unchanged. Run: `RUN_2026-10-08_23-12-19`, all
62 steps, same host, `make -C pnr librelane-sky130-soc SKY130_SOC_CONFIG=config_rccal_wl1500.json
SKY130_SOC_EXTRA_SKIP="--skip KLayout.DRC --skip Checker.KLayoutDRC"`. (Passing `SKY130_SOC_CONFIG=` to the
`-rccal-noklayout` target does **not** work: that recipe re-assigns it, and a first launch silently ran the plain
rccal config; it was caught from `resolved.json`, killed after minutes, and relaunched.)

| (violating pins unless noted) | Gate B `RUN_2026-10-05_06-50-11` | rccal, pinned DMA `RUN_2026-10-06_22-43-34` | confirmation `RUN_2026-10-08_05-21-39` = noise repeat `RUN_2026-10-08_21-07-20` | wl1500 `RUN_2026-10-08_23-12-19` |
|---|---|---|---|---|
| max_ss slew / cap | 7622 / 140 | 295 / 0 | 423 / 1 | **102 / 1** |
| nom_ss | 2648 / 78 | 143 / 0 | 189 / 1 | 21 / 1 |
| min_ss | 1669 / 33 | 5 / 0 | 16 / 1 | 17 / 1 |
| max_tt | 2331 / 3 | 209 / 0 | 257 / 1 | 16 / 1 |
| nom_tt | 1016 / 1 | 64 / 0 | 95 / 1 | 13 / 1 |
| min_tt | 876 / 0 | 0 / 0 | 12 / 1 | 12 / 1 |
| max_ff / nom_ff / min_ff slew (cap 0) | 1661 / 944 / 753 | 122 / 53 / 0 | 254 / 46 / 11 | 13 / 11 / 0 |
| max_ss slew ANT / SRAM / other | 1983 / 30 / 5609 | 198 / 16 / 81 | 304 / 18 / 101 | 54 / 18 / 30 |
| antenna nets / pins | 210 / 305 | 184 / 259 | 205 / 273 | 212 / 253 |
| setup worst slack / violators | +0.579 ns / 0 | +3.276 / 0 | +3.329 / 0 | +3.345 / 0 |
| hold worst slack / violators | +0.279 ns / 0 | +0.275 / 0 | +0.282 / 0 | +0.274 / 0 |
| Netgen LVS / routing DRC | PASSED / 0 | PASSED / 0 | PASSED / 0 | PASSED / 0 |
| Magic DRC (bead 45a) | 8984 | 8984 | 8984 | 8984 |
| utilisation / instances | 44.84 % / 315 038 | 45.20 % / 314 625 | 45.21 % / 312 320 | 45.23 % / 312 244 |
| power | 81.0 mW | 80.9 mW | 84.9 mW | 84.9 mW |
| step-37 repair (buffers / nets / resized) | - | - | 34 / 148 / 40 | 200 / 257 / 128 |

Result: **slew improves sharply with no cost elsewhere** (max_ss 423 -> 102, max_tt 257 -> 16, max_ff 254 -> 13; ANT
diode pins 304 -> 54; antenna pins 273 -> 253 while nets 205 -> 212; setup/hold/LVS/DRC unchanged within a few
ps), **but max-cap stays at 1 at the same six corners on the same net**: `_078722_/X` is 0.646 pF against 0.530 pF
at nom_tt, slightly worse than before (0.614), and the net is again `o22a_4 -> macro pin` with no buffer at step 37
(checked in the step-37 ODB). The adoption bar (cap 0 at all nine corners) is **not met**, so no default changed,
`Checker.MaxCapViolations` stays skipped, and `config_rccal` is not promoted. (Single arm for a changed input, with
zero repeat noise; why the resizer does not buffer this particular 2 196 um net although it buffered 200 others
under the cap was not established. *Inference*: the net's far end is a hard-macro pin and repair_design does not
rebuffer toward it.)

### 6.4 Recommendation and next step

* **Do not adopt yet.** Adoption needs cap 0 and it is 1, so the decision rule is unchanged.
* The residual is a **single net of a different kind** than the previous 8 623 -> 295 slew story: a cap violation
  caused by one macro input pin characterised at 0.2464 pF. Config-level sweeps are unlikely to fix it (two
  runs: auto-length and 1 500 um wire-length both leave it untouched). Options, cheapest first, none executed:
  (1) accept it as a tracked single-net residual and un-skip the cap checker only with a documented, named waiver
  for this net (a waiver is a moved target, user's call); (2) look at the CPU macro: why does `axi_rdata_i[12]`
  present 0.2464 pF when its siblings present ~0.01 pF? An input buffer inside the macro (a CPU macro re-harden)
  would fix it at the source, but that edits a macro view and needs explicit approval (cf. bead `ma7`/`lxv`
  hard-macro rule); (3) constrain placement of `_078722_` next to the macro pin (a pin-specific placement
  constraint, brittle across re-synthesis names).
* `GRT_DESIGN_REPAIR_MAX_WIRE_LENGTH = 1500` is independently attractive for **slew** (max_ss 423 -> 102 at no
  measured cost): worth adopting together with rccal when rccal itself is adopted, after one more arm on a different
  RTL vintage to see it is not a one-draw effect. Not adopted now.
