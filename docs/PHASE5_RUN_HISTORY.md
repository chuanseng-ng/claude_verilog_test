# Phase 5 SoC — ASAP7 P&R Run History (M11)

Full-SoC ASAP7 hierarchical place-and-route campaign (M11). Mirrors
`docs/ASAP7_RUN_HISTORY.md` (CPU/GPU). The SoC integrates the CPU + GPU as hard
macros with the crossbar / AXI-Lite interconnect / DMA / peripherals / PLL stub
synthesized flat. Branch `feature/phase7-mixed-signal-pll`.

> ⚠️ **Every "SoC power" figure in this document is fabric-only.** `report_power`
> attributes **0.00 W to both hard macros** (CPU, GPU) in every run below — the
> bulk of the design contributes nothing to the reported total. Every mW value
> quoted here, including the run-14 M11 sign-off figure, is fabric + glue power,
> not true SoC power. Root cause, re-measurement, and how to bound the gap:
> see **[§ Power figure caveat (bead `ew3`)](#power-figure-caveat-macro-power-omitted-from-every-figure-bead-ew3)**.

> ⚠️ **Every "Routing DRC 0" / "antenna 0" claim in this document is
> unsupported — detailed routing never committed a wire.** Measured directly
> on run 14's own artifacts: `final/def/soc_top.def` has zero `ROUTED ` net
> records and `route__wirelength__max = 0`. `OpenROAD.DetailedRouting`
> (step 38) errored during pin access (`[ERROR DRT-0073] No access point for
> u_cpu/apb_paddr_i[5]` / `u_gpu/m_axi_araddr[19]`) before track assignment
> ever ran; a local, non-upstream patch to LibreLane's `drt.tcl` wraps the
> whole call in `catch {}` and lets the flow continue anyway, so every
> downstream checker reports 0 violations because nothing was routed to
> violate. This is **not** a run-14-specific or SoC-specific defect: it
> reproduces on both GPU 571 MHz sign-off runs and every CPU tuning run in
> the #96 campaign — see **[§ Routing / physical-closure caveat (bead
> `xy6`)](#routing--physical-closure-caveat-detailed-routing-committed-zero-wires-bead-xy6)**
> for the full table and what remains valid.

## Sign-off result (run 14 — accepted)

Run `RUN_2026-06-23_18-05-38`, sv2v synthesis frontend, single-clock 1750 ps.

| Metric | Value |
| ------ | ----- |
| **Fmax** | **571 MHz** (1750 ps period; setup WS **+113.6 ps**, achievable ~611 MHz) |
| Hold | WS **+22.2 ps** (WNS 0) |
| **Power** | **62.9 mW** ⚠️ fabric-only (internal 47.6 / switching 15.3 / leakage 0.03 mW) — excludes both hard macros, see caveat below |
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
| 14 | **sign-off** | Dropped the broken `create_generated_clock` → single clean `clk_i` H-tree; IO delays 350/20→175/10 ps; CTS tuning. **Setup +113.6 ps (MET @ 571 MHz)**, hold +22.2 ps, 0 DRC, 0 antenna, 62.9 mW ⚠️ fabric-only, 65.6 % util. |
| 15 | reverted | Added M7 PG geometry to macro LEFs to chase the PDN count — **no effect** (8.28 M identical: the violations are the tap artifact, not macro pins) **and** setup regressed to −341 ps (M7 PG shapes over macros likely blocked routing). Change reverted (`f84813c`). |
| 16 | first **multi-clock** | GH #96. `phase5_soc_multiclock.sdc` wired in via new `config_multiclock.json` (`config.json` untouched). Two real CTS trees. `sys_clk` **+106.2 ps (MET)**, `cpu_clk` **−205.3 ps** → 1014.9 MHz. Limiter measured: an 800.71 ps *combinational* arc inside the CPU macro (APB debug read). |
| 17 | APB exception | Added SDC §10a `set_false_path -through u_cpu/apb_prdata_o[*]`, matching the CPU block's own sign-off. `cpu_clk` −205.3 → **−44.9 ps** (1212.2 MHz), TNS −7262 → −1757. `CLOCK_PERIOD 1.75→0.78` tried in the same run and measured as a **no-op** (−11 std cells). |
| 18 | **null result** | Hold-margin 0.075→0.030 produced a **byte-identical netlist**. Root cause: librelane declares the resizer margins `units="ns"` but passes them raw to OpenROAD, which reads the Liberty unit — ASAP7 is `1ps`, so both values meant ~0. Bead `s9f`; affects **every** ASAP7 sign-off. |
| 19 | best under the old abstract | `CTS_SINK_CLUSTERING` 20/50 → 8/10. `cpu_clk` −44.9 → **−32.3 ps** (1231.1 MHz), TNS −1757 → −283, violators 162 → 64. `sys_clk` held at +104.4 ps. 0 DRC, 0 antenna, **CDC budget check PASS**. Still relied on the §10a false path and a CPU abstract with no burst pins. |
| 20 | regression, diagnostic | First run on the **regenerated CPU macro** (registered `apb_prdata_o`, burst pins present) with §10a retired. `cpu_clk` **−350.1 ps** (884.9 MHz), 15 violators — **all 15 end at macro APB input pins**. Cause: registering the output *relocated* the ~800 ps read mux from an in→out arc into an **876.85 ps input setup requirement** in the Liberty. |
| 21 | best before the macro rebuild | Added §10b mirroring the CPU block's own `set_multicycle_path -setup 3 / -hold 2` on the APB inputs (`asap7.sdc:183-184`). `cpu_clk` **−60.7 ps → 1189.5 MHz**, 1 violator; `sys_clk` **+83.8 ps, TNS 0 — 571 MHz MET**; 0 DRC, 0 antenna, 53.2 mW ⚠️ fabric-only, **CDC check PASS**. PDN artifact fell 8.28 M → 7.19 M with the new abstract. |
| 22 | regression, diagnostic | Rebuilt CPU macro with `apb_pready_o`/`apb_pslverr_o` also registered. `cpu_clk` **−596.0 ps**, 690 violators. Root cause was NOT the RTL: the macro had no `FP_PIN_ORDER_CFG`, so regeneration reshuffled **393 of 401** boundary pins → SoC placement perturbed → post-CTS `cpu_clk` skew doubled (−485.6 → −922.1 ps) → hold violations 805 → 4702 → 4814 hold buffers → padding ate setup. |
| 23 | **BOTH DOMAINS MET** | Added `pin_order.cfg` (deterministic boundary, then tuned by function) + kept all three APB outputs registered. `sys_clk` **+74.8 ps TNS 0 → 571 MHz MET**; `cpu_clk` **+9.8 ps, TNS 0, 0 violators → 1282 MHz MET** — the first time the CPU domain has ever closed at its 780 ps target. 0 DRC, 0 antenna, 51.9 mW ⚠️ fabric-only, CDC check PASS. |

## Multi-clock re-closure (GH #96) — BOTH DOMAINS MET

Run 14 remains the accepted single-clock M11 sign-off. This section records the
2-domain re-closure (`sys_clk` 1750 ps on `clk_i`, `cpu_clk` 780 ps on
`cpu_clk_i`, `set_clock_groups -asynchronous`), driven by
`pnr/asap7/soc/config_multiclock.json` so `config.json` and run 14 stay
byte-reproducible.

**Best and accepted: run 23, `RUN_2026-08-09_14-36-16`.**

| Metric | Run 14 (single-clock) | Run 23 (multi-clock) |
| ------ | --------------------- | -------------------- |
| `sys_clk` | 1750 ps, WS **+113.6 ps** | 1750 ps, WS **+74.8 ps**, TNS 0, 0 violators — **571 MHz MET** |
| `cpu_clk` | n/a (CPU de-rated onto the 1750 ps fabric cycle) | 780 ps, WS **+9.8 ps**, TNS 0, 0 violators — **1282 MHz MET** |
| Hold WS | +22.2 ps | +26.7 ps (`sys_clk`) / +23.6 ps (`cpu_clk`) |
| Routing DRC / antenna | 0 / 0 | **0 / 0** |
| Max slew / cap | 0 | **0** |
| Power ⚠️ fabric-only, not comparable to a power-optimization delta | 62.9 mW | 51.9 mW |
| Std cells / utilisation | 245,149 / 65.6 % | 267,504 / 66.9 % |
| Die | 520 × 520 µm | unchanged |
| PDN violations | 8,281,711 (tap artifact) | 7,186,185 (same artifact) |
| CDC budget check | n/a | **PASS** (0 unmatched exceptions, 0 budget violations) |

**Headline: the CPU domain runs at 1282 MHz — 2.24× the fabric's 571 MHz —
and both domains close with positive slack and zero violating endpoints.** The
CPU is no longer de-rated onto the fabric cycle, which was the entire point of
epic #90.

### Caveats — read before quoting any number above

- **The power comparison is not like-for-like — and is not a real SoC total in
  the first place.** `report_power` attributes **0.00 W to the macros**, and
  the drop from 62.9 mW coincides with the first-ever insertion of real ICG
  clock gates (`USE_ICG_CELL`), not with the domain split. Do not claim
  multi-clock as a power win on this evidence. Full root-cause investigation,
  independent re-measurement, and how to bound the true SoC power → **[§ Power
  figure caveat, below](#power-figure-caveat-macro-power-omitted-from-every-figure-bead-ew3)**.
- **`cpu_clk` covers 960 flat registers**, not the CPU core — the core is a hard
  macro whose interior is fixed by its own sign-off (which closes at −0.87 ps
  setup / +8.54 ps hold). The 960 are the CDC bridge's CPU face, the
  synchronisers, the clock gate and the PLL2 APB registers.
- **Optimisation guard band was ~0 before bead `s9f`** — the resizer margins
  were declared `units="ns"` but read in the Liberty's `1ps`. Run 23 is the
  first multi-clock run with real margins — 45 ps setup / 25 ps hold in
  `pnr/asap7/soc/config_multiclock.json`; the CPU block config
  (`pnr/asap7/cpu/config.json`) uses 20 ps / 10 ps, sized under its own achieved
  slack.
- **IR drop is still unobtainable**: `analyze_power_grid` fails `PSM-0069` on
  both rails from the same M1-only tap-cell connectivity artifact.
- Indicative ASAP7 (predictive PDK): no Magic/KLayout DRC, no Netgen LVS.

### How `cpu_clk` was closed — two independent problems

**1. The macro exported ~600–800 ps combinational in→out arcs on its APB
outputs.** `apb_prdata_o`, `apb_pslverr_o` and `apb_pready_o` are now pure
registered outputs; no output pin of the macro carries a combinational arc.
Two earlier attempts failed and are recorded in `rv32i_cpu_top.sv` so they are
not retried: registering `prdata` alone merely **relocated** the delay into an
876.85 ps *input setup requirement*, and a SETUP-phase decode for `pslverr`
still left a 617.9 ps arc re-sourced from `apb_psel_i`. Every APB output pays
~600 ps crossing this block's internal distribution regardless of logic depth,
so only a pure flop breaks it.

**2. The macro boundary was not reproducible.** `pnr/asap7/cpu/config.json` had
no `FP_PIN_ORDER_CFG`, so each regeneration free-floated the pins — **393 of
401 moved** between two consecutive builds. In run 22 that perturbed SoC
placement around `u_cpu`, doubled post-CTS `cpu_clk` skew (−485.6 → −922.1 ps),
drove hold violations 805 → 4702 endpoints and 4814 inserted hold buffers, and
took `cpu_clk` to −596.0 ps. With `pin_order.cfg` two runs now produce a
byte-identical LEF (0/401 pins moved), which made tuning measurable for the
first time — block slack had previously drawn randomly from a ~47 ps band.

Tuning then took two measured iterations, using the SoC context (`u_cpu` sits
at 365,15, so W/N face the fabric and E/S face the die edge):

| Pin-order revision | Block setup WS | Block setup TNS | Block hold WS |
| --- | --- | --- | --- |
| v1 — replicate the free-floated sides | −25.87 ps | −1180.02 | +27.47 ps |
| v2 — group AXI onto W/N | −10.48 ps | −10.48 | −2.06 ps |
| v3 — move APB off the fabric-facing edge | **−0.87 ps** | **−0.87** | **+8.54 ps** |

v2's hold violator was `apb_paddr_i[*]`, which pointed straight at the error:
APB carries a 3-cycle setup multicycle at block level, so those paths want to
be **long** and should never occupy scarce fabric-facing slots.

### What made `cpu_clk` hard (measured, not inferred)

> **Status note.** This subsection records the runs 16–19 diagnosis. §10a is
> **retired** in the accepted run-23 configuration: all three APB outputs are now
> pure registered outputs, so the combinational arc it excluded no longer exists.
> What remains active is §10b (the APB *input* multicycle mirroring
> `asap7.sdc:183-184`). See "How `cpu_clk` was closed" above for the shipped state.

1. **An 800.71 ps combinational arc inside the CPU macro** — `apb_paddr_i` →
   `apb_prdata_o`, the APB debug read mux (`rv32i_cpu_top.sv:261-285`, pure
   `always_comb`). It cannot fit a 780 ps period and is fixed in Liberty. The
   CPU's own standalone sign-off already excludes it
   (`set_false_path -to [get_ports apb_prdata_o[*]]`, `pnr/asap7/cpu/constraints/asap7.sdc:150`),
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

## Power figure caveat: macro power omitted from every figure (bead `ew3`)

Filed after GH #96 (run 23 vs. run 14) surfaced `Macro = 0.00 W` in
`report_power` for both hard macros. Investigated 2026-08-15; bead
`claude_verilog_test-ew3`. This section is the authoritative statement — every
inline ⚠️ mark above points here.

**Finding 1 — the macro Liberty files have no power tables at all, by
construction.** `pnr/asap7/{cpu,gpu}/macro/*__nom_tt_025C_0p7V.lib` (the
tracked source of truth; `pnr/asap7/soc/macro/*` are gitignored copies of the
same content) each declare `leakage_power_unit : 1pW;` and never use it — a
full-text grep of both files for `leakage_power`, `cell_leakage_power`, and
`internal_power` finds **zero** occurrences beyond that one unit declaration.
Every `cell()` / `pin()` block carries only `capacitance` and `timing()`
(setup/hold constraints, `cell_rise`/`cell_fall`/`*_transition` tables) — no
`power()` group of any kind. `report_power` is not misreading these files; the
files contain nothing to report.

**Finding 2 — this is a characterization-flow gap, not an OpenROAD
registration or corner-mapping bug.** Both macro libs generate from
`pnr/scripts/asap7_macro_views.tcl`, which after loading the routed macro ODB
and the real stdcell/SRAM Liberty set calls a single OpenSTA/OpenROAD command,
`write_timing_model`, to emit the abstracted `.lib`. Tracing that command to
its implementation (`MakeTimingModel.cc` in the vendored OpenSTA source,
`/nix/store/.../src/sta/search/MakeTimingModel.cc`) shows **zero
power-related code** — a case-insensitive grep for `power` in the file returns
nothing. `write_timing_model` characterizes I/O timing arcs only; it has no
code path that could emit `cell_leakage_power` or `internal_power` even in
principle. The fix, if pursued, belongs in the macro characterization step
(`asap7_macro_views.tcl` would need a genuinely different tool/technique — e.g.
running `report_power` on the macro's own signed-off block netlist under
representative activity and hand-injecting the resulting lumped numbers as
`cell_leakage_power` / pin `internal_power` — not a flag or option that exists
on `write_timing_model` today), **not** in how the SoC flow loads or maps the
resulting `.lib`.

The SoC-level registration was checked and is correct: `pnr/asap7/soc/config.json`
lists both macro libs under `EXTRA_LIBS` in the same `nom_tt_025C_0p7V` corner
slot as the stdcell/SRAM Liberty (`config.json:100-104`) — there is no separate
"macro corner" mapping to get wrong.

**Finding 3 — independently re-measured, reproduces exactly.** Using the
`eda-openroad` MCP session server (`load_odb` on run 23's final ODB,
`pnr/asap7/soc/runs/RUN_2026-08-09_14-36-16/final/odb/soc_top.odb`, with the 5
stdcell Liberty files + SRAM Liberty + **both** macro Liberty files explicitly
loaded, then `get_power`) reproduces the archived figure bit-for-bit:

```
Group          Internal    Switching    Leakage       Total
Sequential     3.02e-02    4.65e-05     9.62e-06      3.02e-02   58.2%
Combinational  2.41e-04    2.65e-04     2.34e-05      5.30e-04    1.0%
Clock          1.31e-02    8.04e-03     1.73e-06      2.12e-02   40.8%
Macro          0.00e+00    0.00e+00     0.00e+00      0.00e+00    0.0%
Pad            0.00e+00    0.00e+00     0.00e+00      0.00e+00    0.0%
Total          4.35e-02    8.36e-03     3.48e-05      5.19e-02  100.0%
```

Total 51.9134 mW, matching `final/metrics.json`'s `power__total` exactly. This
rules out "the archived run just didn't have the macro libs loaded" as an
explanation — the libs were loaded, correctly, and still contribute nothing,
because there is nothing in them to contribute. (Unrelated: bead `pzj`, a known
`get_area` limitation of the same MCP server, was not touched — different
workstream.)

**Per-hierarchy comparison, run 18 vs. run 23** (both fabric-only; the macro
row is 0.00 W / 0.0% in both, by the same mechanism):

| Group | Run 18 | Run 23 |
| --- | --- | --- |
| Sequential | 29.9 mW (69.0%) | 30.2 mW (58.2%) |
| Clock | 13.0 mW (30.0%) | 21.2 mW (40.8%) |
| Combinational | 0.44 mW (1.0%) | 0.53 mW (1.0%) |
| Macro | 0.00 mW (0%) | 0.00 mW (0%) |
| **Total** | **43.3 mW** | **51.9 mW** |

Clock power's share nearly doubling (30.0% → 40.8%) while total power *rose*
between run 18 and run 23 is consistent with the ICG-insertion timeline
(`USE_ICG_CELL` landed in `SOC_SV2V_DEFINES` during GH #96 Gate B, between
these two runs) changing where switching activity is attributed, not with any
claim about macro contribution — the macro row is identically absent in both.

**Bounding the true gap.** The standalone block sign-offs *do* include their
own internals, because they run `report_power` on the flat block netlist
directly rather than through a `write_timing_model` abstraction:

- CPU standalone (`pnr/asap7/cpu/`, M7-updated 780 ps sign-off): **24.38 mW**
- GPU standalone (`pnr/asap7/gpu/`): **262 mW**

**Naively summing these onto the 51.9 mW SoC figure (→ ~338 mW) is the wrong
arithmetic and must not be quoted as an estimate of true SoC power.** The
block sign-offs use `report_power`'s default/no-VCD activity assumptions
against each block's *own* clock and I/O environment in isolation (the GPU
figure in particular reflects the GPU's own 571 MHz sign-off activity, not its
activity as driven by the SoC's crossbar and DMA in context); the SoC run
applies the same default-activity mechanism to the fabric only, under the
SoC's own clocking. Summing conflates two different activity contexts and
double-uses the same default-activity assumption rather than compounding a
real one. All three numbers can be reported side by side as bounds — a true
macro-inclusive SoC total is almost certainly between the fabric-only 51.9 mW
and the naive-sum ~338 mW, closer to the sum given the macros' area/gate-count
dominance — but no arithmetic on the numbers available in this repo produces a
defensible point estimate.

**Conclusion — this cannot be fixed inside OpenROAD or this project's SoC PD
flow.** The macro `.lib` files never carried power tables because
`write_timing_model` doesn't characterize power; no `EXTRA_LIBS`/corner
re-mapping in `config.json` changes that. A real fix requires a macro power
characterization step that does not exist in this repo today. Filed as a
follow-up: **bead `claude_verilog_test-ew3` is closed** with this
investigation as the resolution (root cause identified, re-measurement
confirmed, gap bounded, docs corrected); the actual fix — adding a macro power
characterization step to `asap7_macro_views.tcl` (or equivalent) so
`rv32i_cpu_top`/`gpu_top` carry real `cell_leakage_power`/`internal_power`
tables — is tracked separately as **bead `claude_verilog_test-86a`** so it
isn't lost. Any future SoC power number must carry the same ⚠️ fabric-only
caveat until that follow-up lands.

## Routing / physical-closure caveat: detailed routing committed zero wires (bead `xy6`)

Found 2026-08-16 while standalone-validating the RCX ruleset for bead `e69`
against run 23's ODB. **MEASURED, not inferred**, and swept across every
ASAP7 run with recoverable artifacts on disk (SoC, GPU, and CPU alike) as
part of root-causing bead `claude_verilog_test-xy6`. This section is the
authoritative statement — every inline ⚠️ mark above points here.

**What "zero wires" means, precisely.** `OpenROAD.DetailedRouting`'s
`detailed_route` call is wrapped in `catch {}` by a local (uncommitted-to-
upstream) patch to LibreLane's `librelane/scripts/openroad/drt.tcl`. On
every run below, the pin-access phase (`[INFO DRT-0165] Start pin access`)
hits an unresolved access point — `[ERROR DRT-0073]` for a macro boundary
pin (SoC integration, 1–2 pins) or `[ERROR DRT-0074]` for a top-level I/O
pin (standalone CPU/GPU blocks, hundreds of pins) — **before track
assignment or any search-and-repair pass ever runs.** The Tcl error is
caught, a `WARNING: detailed_route reported errors; continuing` line is
printed, and `write_views` commits the DEF as-is: `final/def/*.def` has
**zero** `ROUTED ` net records, `final/metrics.json`'s
`route__wirelength__max` is `0`, and every downstream checker
(`design__violations`, antenna, max slew/cap) reports 0 because nothing was
routed to violate. Reproduction: `grep -c 'ROUTED ' <run>/final/def/*.def`.

**Scope: this is not a regression, and not limited to the SoC.** The leading
hypothesis when this was filed was that the run-23-era changes (registering
the CPU macro's APB outputs, bead `cyb`/`g0o`; adding `pin_order.cfg`, bead
GH #96) introduced the failure. They did not — the identical zero-wire
pattern is present on **every** ASAP7 run with recoverable final-stage
artifacts, including the GPU 571 MHz sign-off runs from 2026-05-27/28, more
than three weeks before those changes landed. `drt.tcl`'s catch-and-continue
patch itself predates all of them: `memory/pd/knowledge.md`'s DRT-0074 note
already describes it as in place during the Phase-3 CPU PPA campaign
(runs 6–7, 2026-04-25/26), where 374 DRT-0074 errors per run were already
being treated as "structural, non-fatal" without anyone connecting that
acceptance to "therefore zero wires were committed." **No ASAP7 run
inspected in this investigation ever produced a genuinely routed design.**

| Run (design) | Date | Routed net records | `route__wirelength__max` | DRT errors | Note |
| --- | --- | --- | --- | --- | --- |
| GPU `RUN_2026-05-27_11-16-37` | 2026-05-27 | 0 | 0 | 325 (`DRT-0074`, top-level I/O) | Phase-4 GPU 571 MHz sign-off input |
| **GPU `RUN_2026-05-28_06-29-48`** | 2026-05-28 | **0** | **0** | 325 (`DRT-0074`) | **the accepted GPU 571 MHz / 262 mW sign-off run** |
| SoC `RUN_2026-06-23_18-05-38` (**run 14**) | 2026-06-23 | **0** | **0** | 2 (`DRT-0073`, macro pins: `u_cpu/apb_paddr_i[5]`, `u_gpu/m_axi_araddr[19]`) | **the accepted M11 single-clock sign-off — every claim below "Routing DRC 0 / antenna 0" in the table above is vacuous** |
| SoC `RUN_2026-06-24_05-23-19` | 2026-06-24 | 0 | 0 | 2 (`DRT-0073`) | run 15 (reverted PDN LEF change) |
| SoC runs 16–22 (2026-08-05 – 2026-08-08) | 2026-08 | 0 | 0 | 1–2 (`DRT-0073`) | every GH #96 multi-clock re-closure iteration |
| **SoC `RUN_2026-08-09_14-36-16` (run 23)** | 2026-08-09 | **0** | **0** | 1 (`DRT-0073`) | **the accepted "BOTH DOMAINS MET" multi-clock sign-off — same defect** |
| CPU `RUN_2026-08-08_21-01-46` … `RUN_2026-08-09_14-05-02` (8 runs) | 2026-08-08/09 | 0 (all 8) | 0 (all 8) | 401 each (`DRT-0074`, the 3 registered APB output pins × fan-out) | #96 `pin_order.cfg` tuning campaign |

Runs not listed either predate the artifact retention window (`/nobackup`
periodically cleaned; see bead `o1i` on host reboots) or never reached
`write_views` (`ndef=0` in the sweep — earlier "hollow" synthesis-only runs
1–12, ~2026-06-23 06:xx). Notably absent and **not directly re-verifiable**:
the CPU 1418 MHz Run 43 (2026-05-20) and the 1282 MHz M7 re-sign-off
(2026-06-02) cited in `CLAUDE.md` — both run directories are gone from disk.
Given `drt.tcl`'s catch patch was already in place by the April Phase-3 PPA
campaign (predating both), and given **100 % of the runs that could be
checked show the same pattern with no exception**, the working assumption
must be that those two are affected as well, not that they are somehow
exempt — but this is inference, not measurement, and is flagged as such.

**Root cause, to the depth reached.** Two separate things compound:

1. *Software defect (root-caused, fixed by this bead — see the routing gate
   below):* `drt.tcl`'s `catch {}` wraps the **entire** `detailed_route`
   call, not just per-pin access-point resolution. A single unresolved pin
   anywhere in a 150,000–250,000-pin design aborts the whole call before any
   wire is committed. LibreLane's own upstream default (no catch at all)
   would have failed these runs loudly at step 38/40/41 instead of
   completing 20+ downstream steps against an empty layout.
2. *Why individual pins fail access-point resolution at all (only partially
   characterized, not fully solved):* for standalone-block top-level I/O
   pins (`DRT-0074`), `memory/pd/knowledge.md` already documents that ASAP7
   M4/M5's `WIDTHTABLE` rejects the default pin width and that even the
   mitigated width (`FP_IO_HTHICKNESS_MULT=5`, later 8) does not eliminate
   all failures — congestion/obstruction near specific die-edge locations is
   the untested remaining hypothesis. For SoC macro-boundary pins
   (`DRT-0073`), the failing pins are on the CPU/GPU hard-macro abstract
   LEFs (e.g. `apb_paddr_i[5]` at `RECT 126 15.042 130 15.234` on M4 in the
   current `rv32i_cpu_top.lef`) — the exact geometry in force *at run-14
   time* cannot be recovered (pin_order.cfg postdates run 14 by GH #96, and
   393/401 boundary pins reshuffle on every macro regeneration absent it),
   so the precise geometric cause for run 14's two specific pins is
   unconfirmed. The `gyx` PSM-0069 tap-cell connectivity artifact was
   considered as a related mechanism (both are PDK/geometry artifacts on the
   ASAP7 predictive stack) but no evidence ties the two together — they stay
   separate beads, not merged.

**What survives and what doesn't.** The setup/hold WNS/TNS numbers quoted
throughout this document are **not fabricated** — `OpenROAD.STAPostPNR`
genuinely runs and genuinely computes timing on the placed netlist. But
because detailed routing committed no wires, the parasitics behind every
one of those numbers are the **pre-route global-route (GRT) estimate**, not
real extracted post-route RC — STAPostPNR runs after `DetailedRouting` in
flow order, but "after DetailedRouting" and "on routed parasitics" are not
the same thing when DetailedRouting produced nothing. Read plainly:

- **Survives, self-consistent on its own terms:** setup/hold WNS/TNS, fmax,
  cell count, utilization, die area, std-cell power (all computed from
  GRT-estimated RC on a real placed netlist — this was already true before
  this investigation and is a pre-existing, separately documented
  limitation, not new information).
- **Does not survive — withdrawn as of this bead:** every "Routing DRC 0",
  "antenna 0 violating nets/pins", and "0 max slew/cap/fanout" claim in this
  document, for every run in the table above, including run 14 and run 23.
  These numbers are not "clean" — they are computed over an empty routed
  layout and are vacuously zero.
- **Downstream consequence:** bead `claude_verilog_test-e69` (RCX ruleset)
  is effectively blocked behind this bead — RCX extraction on an unrouted
  design cannot produce a meaningful SPEF. Cross-linked, not merged.

**Fix landed with this bead.** `tools/verif/check_asap7_routing.py` +
`pnr/Makefile` targets `check-asap7-routing` / `check-asap7-gpu-routing` /
`check-asap7-soc-routing`, wired as a mandatory gate immediately after every
full-flow ASAP7 `librelane-asap7*` target (before pruning, so a failing run
is never pruned away) — the build now fails loudly (non-zero exit) whenever
a completed run has zero routed net records, `route__wirelength__max == 0`,
or any unresolved `[ERROR DRT-*]` in the `OpenROAD.DetailedRouting` log,
following the precedent of bead `dwp` ("a tool exiting 0 with an empty or
absent report must never be read as PASS"). **Root-causing why the
individual pin-access points fail (item 2 above) is not solved by this
bead** and is tracked as a follow-up; no full P&R run was launched to
pursue it further given the 2026-08-16 06:48 host reboot (bead `o1i`) that
had just killed a 9-hour in-flight run.

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
