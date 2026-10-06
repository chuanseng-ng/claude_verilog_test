# Sky130 SoC max-slew / max-cap: root cause and the RC-calibrated repair (bead `e45j`)

**Status 2026-10-07.** Mechanism found, fix measured on one full run, bead left **open** (max_ss slew
295, not 0). Everything here is measured from run artifacts unless marked *inference*.

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
