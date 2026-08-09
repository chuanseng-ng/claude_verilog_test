# Phase 5 SoC — ASAP7 P&R Run History (M11)

Full-SoC ASAP7 hierarchical place-and-route campaign (M11). Mirrors
`docs/ASAP7_RUN_HISTORY.md` (CPU/GPU). The SoC integrates the CPU + GPU as hard
macros with the crossbar / AXI-Lite interconnect / DMA / peripherals / PLL stub
synthesized flat. Branch `feature/phase7-mixed-signal-pll`.

## Sign-off result (run 14 — accepted)

Run `RUN_2026-06-23_18-05-38`, sv2v synthesis frontend, single-clock 1750 ps.

| Metric | Value |
| ------ | ----- |
| **Fmax** | **571 MHz** (1750 ps period; setup WS **+113.6 ps**, achievable ~611 MHz) |
| Hold | WS **+22.2 ps** (WNS 0) |
| **Power** | **62.9 mW** (internal 47.6 / switching 15.3 / leakage 0.03 mW) |
| **Die** | 520 × 520 µm (270,400 µm²); core 249,716 µm² |
| Std-cell area | 31,322 µm²; **245,149 std-cells**; **65.6 % utilization** |
| Macros | 2 (rv32i_cpu_top, gpu_top — hard macros) |
| Routing DRC | **0** (`design__violations = 0`) |
| Antenna | **0** violating nets/pins |
| Max slew / cap / fanout | 0 |
| PDN power-grid violations | 8,281,711 — **benign PSM-0039 tap-cell tool artifact** (see note) |

SoC fmax is GPU-governed (GPU macro signed off at 571 MHz); the flattened
integration logic + CPU macro meet the same period with positive margin.

### PDN note (why the tap-cell violations are accepted)
The 8.28 M power-grid violations are all `PSM-0039 Unconnected instance
TAP_TAPCELL_ROW_*/VDD|VSS` — a documented ASAP7 tool artifact (tap-cell wells tie
through the substrate, not the routed grid). The standalone CPU/GPU ASAP7
sign-offs carried ~1.8 M of the identical artifact and were accepted. Real
std-cell + macro power connectivity is intact (timing/power are valid). This is an
**indicative ASAP7** sign-off (predictive PDK — no Magic/KLayout DRC or Netgen LVS,
as with the CPU/GPU sign-offs).

## Run campaign

| Run | Outcome | Key event |
| --- | ------- | --------- |
| 1–12 | hollow | `SYNTH_HIERARCHY_MODE=keep` + Synlig left peripheral submodules unflattened → **0 DFFs at soc_top** → STA saw no paths (ws=1e42), 20 µW, 0.57 % util. Every "Flow complete" was empty. PDN macro-connection + SDC clock bugs surfaced and were fixed but masked by the deeper synth problem. |
| 13 | first **valid** | **sv2v frontend** (see below) → 43,546 DFFs, real placement+route. First real numbers: setup **−364 ps** (fails), clock skew **214 ps** (abnormal), PDN tap artifact, hold clean. |
| 14 | **sign-off** | Dropped the broken `create_generated_clock` → single clean `clk_i` H-tree; IO delays 350/20→175/10 ps; CTS tuning. **Setup +113.6 ps (MET @ 571 MHz)**, hold +22.2 ps, 0 DRC, 0 antenna, 62.9 mW, 65.6 % util. |
| 15 | reverted | Added M7 PG geometry to macro LEFs to chase the PDN count — **no effect** (8.28 M identical: the violations are the tap artifact, not macro pins) **and** setup regressed to −341 ps (M7 PG shapes over macros likely blocked routing). Change reverted (`f84813c`). |
| 16 | first **multi-clock** | GH #96. `phase5_soc_multiclock.sdc` wired in via new `config_multiclock.json` (`config.json` untouched). Two real CTS trees. `sys_clk` **+106.2 ps (MET)**, `cpu_clk` **−205.3 ps** → 1014.9 MHz. Limiter measured: an 800.71 ps *combinational* arc inside the CPU macro (APB debug read). |
| 17 | APB exception | Added SDC §10a `set_false_path -through u_cpu/apb_prdata_o[*]`, matching the CPU block's own sign-off. `cpu_clk` −205.3 → **−44.9 ps** (1212.2 MHz), TNS −7262 → −1757. `CLOCK_PERIOD 1.75→0.78` tried in the same run and measured as a **no-op** (−11 std cells). |
| 18 | **null result** | Hold-margin 0.075→0.030 produced a **byte-identical netlist**. Root cause: librelane declares the resizer margins `units="ns"` but passes them raw to OpenROAD, which reads the Liberty unit — ASAP7 is `1ps`, so both values meant ~0. Bead `s9f`; affects **every** ASAP7 sign-off. |
| 19 | best under the old abstract | `CTS_SINK_CLUSTERING` 20/50 → 8/10. `cpu_clk` −44.9 → **−32.3 ps** (1231.1 MHz), TNS −1757 → −283, violators 162 → 64. `sys_clk` held at +104.4 ps. 0 DRC, 0 antenna, **CDC budget check PASS**. Still relied on the §10a false path and a CPU abstract with no burst pins. |
| 20 | regression, diagnostic | First run on the **regenerated CPU macro** (registered `apb_prdata_o`, burst pins present) with §10a retired. `cpu_clk` **−350.1 ps** (884.9 MHz), 15 violators — **all 15 end at macro APB input pins**. Cause: registering the output *relocated* the ~800 ps read mux from an in→out arc into an **876.85 ps input setup requirement** in the Liberty. |
| 22 | regression, diagnostic | Rebuilt CPU macro with `apb_pready_o`/`apb_pslverr_o` also registered. `cpu_clk` **−596.0 ps**, 690 violators. Root cause was NOT the RTL: the macro had no `FP_PIN_ORDER_CFG`, so regeneration reshuffled **393 of 401** boundary pins → SoC placement perturbed → post-CTS `cpu_clk` skew doubled (−485.6 → −922.1 ps) → hold violations 805 → 4702 → 4814 hold buffers → padding ate setup. |
| 23 | **BOTH DOMAINS MET** | Added `pin_order.cfg` (deterministic boundary, then tuned by function) + kept all three APB outputs registered. `sys_clk` **+74.8 ps TNS 0 → 571 MHz MET**; `cpu_clk` **+9.8 ps, TNS 0, 0 violators → 1282 MHz MET** — the first time the CPU domain has ever closed at its 780 ps target. 0 DRC, 0 antenna, 51.9 mW, CDC check PASS. |
| 21 | best before the macro rebuild | Added §10b mirroring the CPU block's own `set_multicycle_path -setup 3 / -hold 2` on the APB inputs (`asap7.sdc:183-184`). `cpu_clk` **−60.7 ps → 1189.5 MHz**, 1 violator; `sys_clk` **+83.8 ps, TNS 0 — 571 MHz MET**; 0 DRC, 0 antenna, 53.2 mW, **CDC check PASS**. PDN artifact fell 8.28 M → 7.19 M with the new abstract. |

## Multi-clock re-closure (GH #96, 2026-08-06)

Run 14 above **remains the accepted M11 sign-off**. The runs below are an
additional data point: the same SoC re-closed with the 2-domain SDC
(`sys_clk` 1750 ps on `clk_i`, `cpu_clk` 780 ps on `cpu_clk_i`,
`set_clock_groups -asynchronous`), driven by `pnr/asap7/soc/config_multiclock.json`
so `config.json` and run 14 stay byte-reproducible.

Best run: `RUN_2026-08-06_17-32-37` (run 19).

| Metric | Run 14 (single-clock) | Run 19 (multi-clock) |
| ------ | --------------------- | -------------------- |
| `sys_clk` | 1750 ps, setup WS **+113.6 ps** | 1750 ps, setup WS **+104.4 ps**, TNS 0 — **571 MHz MET** |
| `cpu_clk` | n/a (CPU de-rated onto the 1750 ps fabric cycle) | 780 ps target, setup WS **−32.3 ps**, TNS −283, 64 violators → **1231.1 MHz achieved** |
| Hold WS | +22.2 ps | +17.8 ps (`sys_clk`) / +18.0 ps (`cpu_clk`) |
| Routing DRC / antenna | 0 / 0 | **0 / 0** |
| Power | 62.9 mW | 52.6 mW (int 44.0 / sw 8.5 / leak 0.04) |
| Std cells / area | 245,149 / 31,322 µm² | 261,112 / 34,202 µm² |
| Utilisation | 65.6 % | 66.8 % |
| Clock buffers + inverters | 2,610 + 1,275 | 6,395 + 3,729 |
| Die | 520 × 520 µm | unchanged |
| PDN violations | 8,281,711 (tap artifact) | 8,281,711 (identical) |
| CDC budget check | n/a | **PASS** (0 unmatched exceptions, 0 budget violations) |

**Headline:** the CPU domain runs at **1231 MHz — 2.16× the fabric's 571 MHz** —
instead of being de-rated to it, and the fabric baseline survived the split
(+104.4 vs +113.6 ps, inside this flow's known run-to-run variance). The
780 ps / 1282 MHz *target* was not met; 1231 MHz is the achieved, measured
result.

### Caveats — read before quoting any number above

- **`cpu_clk` did not close.** −32.3 ps over 64 endpoints. Three knobs were
  measured and are documented in the run table: the APB exception (worked,
  +160 ps), ABC target period (no-op), CTS clustering (worked, +12.7 ps).
- **The power comparison is not like-for-like.** `report_power` attributes
  **0.00 W to the macros**, and the drop from 62.9 mW coincides with the
  first-ever insertion of real ICG clock gates (`USE_ICG_CELL`), not with the
  domain split. Do not claim multi-clock as a power win on this evidence.
- **`cpu_clk` covers 872 flat registers**, not the CPU core — the core is a
  hard macro whose interior is fixed by its own sign-off. The 872 are the CDC
  bridge's CPU face, the synchronisers, the clock gate and the PLL2 APB regs.
- **The CPU macro abstract still lacks the AXI4 burst pins** (`awlen`/`wlast`/
  `arlen`, bead `g0o`), and since GH #93 the whole CPU AXI master runs through
  the cpu_clk face of the bridge. So `cpu_clk` closure covers only the macro
  pins present in the abstract. The identical 27 undriven bits exist in run 14.
- **Optimisation guard band was ~0, not 100/75 ps** (bead `s9f`) — see run 18.
  This applies to run 14 and the CPU/GPU sign-offs equally.
- **IR drop could not be produced.** `analyze_power_grid` fails `PSM-0069` on
  both rails with 32,862 "Unconnected shape … on Layer M1" errors — the same
  M1-only connectivity model behind the benign tap-cell PDN count. No bypass
  flag exists; `-source_type STRAPS` fails identically.

### Runs 20–21: the follow-up fixes, and what they actually bought

Runs 20–21 rebuilt the CPU macro (beads `cyb`/`g0o`/`s9f`) and re-integrated it.
**Run 21 supersedes run 19 as the trustworthy multi-clock result**, even though
its `cpu_clk` number is lower — run 19's 1231 MHz rested on a false path hiding
an 800 ps arc and on a CPU abstract that had no AXI4 burst pins at all.

| | Run 19 | Run 21 |
| --- | --- | --- |
| `sys_clk` | +104.4 ps, TNS 0 | **+83.8 ps, TNS 0 — 571 MHz MET** |
| `cpu_clk` | −32.3 ps → 1231.1 MHz | **−60.7 ps → 1189.5 MHz**, 1 violator |
| CPU macro abstract | stale (no burst pins, 800 ps in→out APB arc) | **regenerated** (burst pins present, `apb_prdata_o` clocked) |
| APB constraint | §10a false path on the read-data arc | §10b multicycle mirroring the block's own sign-off |
| DRC / antenna | 0 / 0 | **0 / 0** |
| CDC budget check | PASS | **PASS** |
| PDN artifact | 8,281,711 | 7,186,185 |

Three things worth carrying forward:

1. **Registering an output relocates delay; it does not delete it.** Making
   `apb_prdata_o` a flop removed the combinational in→out arc from the Liberty
   but moved the same read-mux depth into an **876.85 ps input setup
   requirement** on `apb_psel_i`/`apb_paddr_i[*]`. Run 20 measured the result:
   −350.1 ps, every violator at a macro APB input. The fix was to mirror the
   constraint the CPU block has always used itself.
2. **Run 21's netlist is byte-identical to run 20's.** A multicycle only
   relaxes, and these paths end at macro input pins whose setup requirement is
   internal to the macro — nothing the resizer can act on. Only the verdict
   changed. (Confirmed: run 21's signoff SDC carries 2 multicycles and 6
   `apb_psel_i` references; run 20's carries none.)
3. **The one remaining `cpu_clk` violator is `apb_pslverr_o`** — a 620.67 ps
   combinational arc still exported by the macro, deliberately left
   unregistered because it is write-side only. Registering it is the next step
   if the 780 ps target must be met; the block itself closes it because its own
   SDC budgets only 120 ps of external delay, and the SoC consumes more.

### What made `cpu_clk` hard (measured, not inferred)

1. **An 800.71 ps combinational arc inside the CPU macro** — `apb_paddr_i` →
   `apb_prdata_o`, the APB debug read mux (`rv32i_cpu_top.sv:261-285`, pure
   `always_comb`). It cannot fit a 780 ps period and is fixed in Liberty. The
   CPU's own standalone sign-off already excludes it
   (`set_false_path -to [get_ports apb_prdata_o[*]]`, `pnr/asap7/cpu/constraints/asap7.sdc:121`),
   so SDC §10a restores that contract at SoC level. Root fix → bead `cyb`.
   Note `-through`, not `-from`: at block level the pin is an endpoint, at SoC
   level the path continues through it.
2. **Hold padding eating setup.** Before run 19, 161 of 162 violating paths ran
   through resizer-inserted `HB4xp67` hold buffers, chains up to 20 deep — one
   path spent 665 ps of its 1050 ps arrival in 9 buffers while its real logic
   was ~222 ps. Driver: `cpu_clk` insertion-delay imbalance (109.3 ps launch vs
   256.8 ps capture). Tighter CTS clustering addressed part of it.

## The synthesis blocker and fix (the central M11 problem)

LibreLane's **Synlig/UHDM SystemVerilog frontend cannot synthesize this SoC**:
- `SYNLIG_DEFER=true` — silently drops peripheral FSM logic (0 DFFs → hollow P&R).
- `SYNLIG_DEFER=false` — crashes Yosys `rtlil.cc:2150` (empty wire name in UHDM `-link`).
- `USE_SYNLIG=false` — native `read_verilog -sv` fails on `package…endpackage`.

**Fix:** `sv2v 0.0.13.1` (nixpkgs `haskellPackages.sv2v`) converts all SoC
SystemVerilog → flat Verilog-2005, then native Yosys `read_verilog` + `flatten` +
blackbox the two macros → 43,546 DFFs, 110 k cells, clean. The verified RTL
(`soc_all` 82/82 as of M11) remains the correctness source; sv2v is a synth-frontend
transform only (Verilator lint skipped on its benign `1'sb0`/ascending-range
output). **Always sanity-check DFF count > 0 after SoC synth.** Core commit
`6ee91b6`.

Also fixed en route: SoC-level SDC (single `clk_i` clock + clean H-tree),
`PDN_MACRO_CONNECTIONS` (removed the behavioral `sram_controller`, which is flat
std-cells, not a macro), die shrink (720→520 µm), and the librelane tool patches
(`pyosys.py` json_header, `synthesize.py` hierarchy `-check`) needed for the flow.

## Reproduce

```bash
cd pnr && make librelane-asap7-soc      # sv2v frontend; run dir on /nobackup
# metrics: <run>/final/metrics.json
```

## Known limitations / follow-ups
- **sv2v ≠ formal-equivalent to source RTL.** Correctness rests on `soc_all` 82/82 (M11-era count; 120/120 as of 2026-08-01)
  against the original SystemVerilog. A Yosys EQY/LEC of sv2v output vs RTL would
  add tape-out rigor (not required for indicative ASAP7).
- **CPU macro LEF lacks AXI4 burst ports** (`awlen`/`wlast`/…) — abstract predates
  the M2 burst upgrade; SoC burst nets dangle at the macro boundary. Indicative-PPA
  acceptable; regenerate the abstract for a clean integration (bead
  `claude_verilog_test-g0o`).
- Timing showed run-to-run variance (run 14 +113 ps vs run 15 −341 ps with the LEF
  change); the +113 ps margin is an indicative single-run result.
