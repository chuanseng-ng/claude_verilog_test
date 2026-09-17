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

> ⚠️ **Every setup/hold WNS/TNS number in this document from before
> 2026-09-16 is `OpenROAD.STAMidPNR-3` output, produced WITHOUT an in-session
> `global_route`** (bead `claude_verilog_test-8f3`, found/fixed 2026-09-16).
> `sta/corner.tcl` calls `estimate_parasitics -global_routing` on a loaded
> ODB, and OpenROAD does not recover GRT parasitics from a saved ODB alone —
> so these numbers run on largely zero-wire / unannotated parasitics. Proven
> on an isolated CPU-block run of this same design family: 94.44% of drivers
> unannotated, falsely reporting 0/0/0 setup and hold violations. Every run
> in this document (14, 23, and the whole #96 campaign) predates the fix
> (`STA_POSTGRT_INSESSION_GRT=1`, now applied to the shared LibreLane tree)
> and has **not** been re-measured with it — treat as **unvalidated, not
> confirmed-wrong**. The one exception: the honest, in-session-GRT current-RTL
> figure from run `w3a-sta-7` documented in **[§ Power figure caveat, "UPDATE
> 2026-09-16 (bead `86a` closing)"](#power-figure-caveat-macro-power-omitted-from-every-figure-bead-ew3)**
> — read that block for the replacement timing numbers (setup WNS −2084.08 ps
> / TNS −2.19×10⁷ ps / 41,864 violators; hold WNS −917.23 ps / 718
> violators), which is the current-RTL basis, not a re-run of run 14/23
> themselves (their run directories and RTL vintage are gone — see the "Bead
> `0p6` note" in that same section). Full re-validation inventory, run-by-run
> classification, and what is/isn't recoverable: bead
> `claude_verilog_test-0p6`.

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

> **UPDATE 2026-09-09 (bead `86a`) — the macros are now characterized. The
> figures in this document remain fabric-only and are NOT retro-edited; the
> macro-inclusive numbers below are NEW and carry different assumptions.**
>
> `pnr/scripts/asap7_macro_power.tcl` + `asap7_macro_power_inject.py` (commit
> `7b7dbae`) run `report_power` on each macro's own gate-level netlist and inject
> `cell_leakage_power` / `internal_power` into the tracked macro Liberty. Round-
> tripped against run 23's signed-off flat netlist, the **Macro row goes from
> 0.00 W to 222.545 mW** (internal 217.089 + leakage 5.456), for a whole-SoC
> total of **306.264 mW**.
>
> **Read those two numbers differently:**
> - **306.264 mW** is the cleaner figure — one methodology, everything at the
>   same flat 0.20/0.5 activity.
> - **51.9 mW (fabric, run 23) + 222.5 mW (macros) ≈ 274.4 mW** MIXES
>   methodologies: real post-route parasitics on the fabric, flat vectorless
>   activity and no wire RC on the macros. Quote it only with that caveat, never
>   as a measured total.
>
> **Two assumptions, both stacked, both disclosed in the generated `.lib`:**
> 1. Flat vectorless activity (`set_power_activity -global -activity 0.20
>    -duty 0.5`) — this repo's own existing convention from
>    `pnr/scripts/08_power.tcl`, not invented for the task. No VCD or SAIF exists
>    for either macro.
> 2. No post-route SPEF/DEF was available (the CPU run directories had been
>    pruned), so this is Liberty-table power from gate input-pin capacitance
>    only, with **no wire RC**.
>
> Magnitude was sanity-checked rather than assumed: CPU macro leakage matches
> 10 × 128.9 µW of real vendor SRAM Liberty leakage to five digits, and the
> Liberty `internal_power` scalar unit was derived *empirically* with a
> single-cell test library (`capacitive_load_unit × voltage_unit²` = 1 fJ), not
> guessed.
>
> Still outstanding before `86a` closes: re-run SoC `report_power` inside a real
> flow rather than the standalone round-trip. Do **not** use the LibreLane 3.0.14
> shell for that — its `sta` is OpenSTA 2.7.0, which corrupts `report_power` to
> inf/NaN on this design (bead `zwc`).
>
> **UPDATE 2026-09-16 (bead `86a` closing) — in-flow figure on CURRENT RTL,
> honestly annotated, from bead `w3a`'s post-GRT STA close-out. NOT a
> replacement for any number above — those stay as recorded, on their own
> RTL vintage and methodology.**
>
> Run `w3a-sta-7` (`RUN_2026-09-16_05-52-48`, step `01-openroad-stamidpnr-3`),
> `config_multiclock_hier_rsz7.json`, `STA_POSTGRT_INSESSION_GRT=true` (bead
> `8f3`) so the parasitics are a real in-session global-route annotation, not a
> stale/persisted-guide read. Annotation proven: **1553 unannotated drivers, 0
> partial, of ~213 464 total (≈0.7%)** — below the CPU block's own 1.71%
> validated floor, vs. 213 464 (essentially all of them) unannotated on the
> same design under the unpatched stock STA step. Only quote the numbers below
> because that gate passed; if it had not, they would be worthless the same
> way `w3a-rsz-5`'s now-withdrawn `-426.262 ps` / clean-hold figure was.
>
> **Fabric + macro power split**, `report_power` at `nom_tt_025C_0p7V`:
>
> | Group | Internal | Switching | Leakage | Total | % |
> |---|---|---|---|---|---|
> | Macro | 161.875 mW | 0.000 mW | 5.456 mW | **167.331 mW** | 64.7% |
> | Fabric (Sequential+Combinational+Clock) | 53.449 mW | 37.691 mW | 0.011 mW | **91.151 mW** | 35.3% |
> | **Total** | 215.325 mW | 37.691 mW | 5.467 mW | **258.483 mW** | 100% |
>
> **Vectorless-activity caveat applies exactly as before** (`set_power_activity
> -global -activity 0.20 -duty 0.5`, this repo's own convention, no VCD/SAIF for
> either macro): the Macro figure (167.331 mW) lands almost exactly on the
> previously-established **CPU-domain-gated lower bound (167.3 mW)** from this
> bead's own earlier operating-point sweep, not the default-vectorless midpoint
> (177.4 mW) or the all-domains-on upper bound (222.5 mW, using the standalone
> CPU block's 56.5 mW as the only available full-activity CPU proxy). Mechanism
> unchanged from the original finding: under default vectorless STA activity,
> `u_gpu_cg.u_icg`'s enable resolves to a *provable constant* (GPU reproduces
> its full standalone dynamic power), while `u_cpu_cg.u_icg`'s enable is real
> PMU→CDC-synchroniser logic that gets derated to ~18% duty, so the CPU macro's
> *dynamic* power is ~0 here and only its leakage (1.29 mW of the 5.456 mW
> macro leakage total) shows up. **Report the range, not a single number**:
> 167.3 mW (CPU-gated, what this run actually measured) .. 177.4 mW (default
> average) .. 222.5 mW (all domains on) for the macro contribution alone.
>
> **This is NOT comparable to run 23's 51.9 mW fabric-only figure or the
> 306.264 mW standalone round-trip above** — different RTL vintage (current
> RTL is post-`rfz`/post-CDC-hardening; run 23 predates those changes),
> different PD flow (deferred_flatten + the `w3a` CTS/repair fixes, vs run
> 23's flat synthesis), and a genuinely in-flow, honestly-annotated
> measurement rather than a standalone round-trip or a mixed-methodology sum.
> Do not average or combine it with the older figures.
>
> **Timing is NOT closed at this checkpoint** (tracked in beads `w3a`, `rvb`,
> and `0ah` — not a power-bead concern, noted here only so this power figure
> is not read as implying a signed-off design): setup WS −2084.08 ps / TNS
> −2.19 × 10⁷ ps / 41 864 violators, hold WS −917.23 ps / TNS −392 273 ps /
> 718 violators.
>
> **Bead `0p6` note**: `run 23`'s historical post-GRT timing figures elsewhere
> in this document (and by extension any power figure derived from run 23's
> post-GRT state) were measured with the SAME stock, non-re-routing STA step
> that bead `8f3` proved gives false-clean results on this design (94.44%
> unannotated on an isolated CPU-block test). They have **not** been
> re-validated with `STA_POSTGRT_INSESSION_GRT=1` and must be treated as
> **unvalidated, not confirmed-wrong** — re-validation is bead `0p6`'s own
> open scope, not retro-edited here.

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

> **RESOLVED for new runs, 2026-09-09 (bead `ocm`). This section's findings about
> runs 14, 23 and every other pre-September run REMAIN TRUE and are not
> rehabilitated — those runs really did commit zero wires.** What changed is that
> ASAP7 detailed routing now works at all.
>
> Root cause: LibreLane 2.4.13's *own pinned* OpenROAD (`edf00dff`) cannot grant
> pin access to **any** ASAP7 top-level pin — 401/401 BTerms fail — while passing
> Sky130 cleanly on the identical probe. LibreLane 3.0.14's pin (`dcf36133`)
> resolves it. A residual 16 `DRT-0255` were traced to a single macro column and
> cleared by a +10 DBU shift on `gen_data_sram[1]`.
>
> First passing run: **`RUN_2026-09-09_14-56-03`**, `tools/verif/check_asap7_routing.py`
> exit 0 — **33,396 routed net records**, `route__wirelength` 270,938,
> `route__wirelength__max` 321.17 (0 on every previous run ever recorded),
> `drt_error_count` 0, 52 steps including `write_views`. Marked `.signoff` so
> `prune_runs` cannot evict it.
>
> ⚠️ **This is NOT physical closure and must not be quoted as one.**
> `route__drc_errors = 2045` on that run, because `DRT_OPT_ITERS` was capped at 12
> to fit the host's time and memory; the gate deliberately does **not** check DRC
> violations. The residual, triaged by rule: 1135 M3.Lef58EolKeepOut, 560 M2 Metal
> Spacing, 215 M3.Short, 81 V2 Cut Spacing, 33 V3.Lef58CutSpacingTable, 12
> M2.Lef58SpacingEndOfLine, 5 V2 Cut Short, 4 M6 Rect Only — i.e. 220 real shorts,
> the rest spacing/keepout. An unbounded run reached 43 violations by iteration ~45
> but peaked at 13 GiB on a 15.9 GB host and died before `write_views`.
>
> ⚠️ **The point fix is a per-instance workaround, not a rule.** Its positive
> control — moving a *passing* column onto the identical near-grid residue class —
> did **not** reproduce the failure, so grid alignment is necessary-looking but
> demonstrably not sufficient. Any re-placement, die-size or macro-count change can
> drop a different column into the same condition.
>
> Consequence for `e69`: the first genuine post-route parasitic extraction in this
> project now exists — a 61,048,456-byte SPEF consumed by `OpenROAD.STAPostPNR` —
> for the **CPU block only**. GPU and SoC still have `RUN_SPEF_EXTRACTION` false.

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
- **sv2v vs source RTL — now formally checked (2026-09-12/13, bead `q7n`), not fully closed.**
  Originally correctness rested only on `soc_all` 82/82 (M11-era count; 120/120 as of
  2026-08-01). Gold is the **source RTL read by yosys-slang** — an independent frontend — and gate
  is `soc_top_sv2v.v`, so this checks sv2v itself rather than a self-consistency.
  * **Flat `soc_top`:** 64 209 of 64 433 equivalence points proven (99.65 %), **0 disproven**.
    Depth is host-capped at `equiv_induct -seq 5`: seq 7, 10 and 20 all die at an identical
    ~12.57 GB.
  * **Per module** (`tools/verif/equiv_sv2v_module.sh`, sv2v keeps module boundaries):
    **25 of 27 modules PROVEN outright** at seq-20 induction, including `axi4_crossbar`,
    `soc_bus`, `async_axi_fifo`; `sram_controller` at `MEM_WORDS=16` (its 4096-word array is
    unaffordable at full size; the transform is depth-independent). The flat miter's unproven
    `m_araddr` group proves cleanly at module level, so it was a flattening artefact.
  * **Remaining two, bounded evidence only:** `pmu` — 39 FSM-output points induction-unproven, but
    a 40-cycle **post-reset** bounded miter passes (39 cycles after reset — enough for a full power-down→up through both domains' 9-state sequencers; 20 cycles was not). `dma_engine` — 128 points
    (`src_q`/`dst_q`/`words_rem_q`/`m_araddr`) unproven even at seq-20 induction; 8-cycle
    bounded miters pass both from the zero state and after reset.
  * A PMU miter first reported a counterexample; it was a **pre-reset first-cycle artefact** —
    identical outputs for all 19 post-reset cycles. Bounded miters here need reset asserted at
    step 1 *and* `-prove-skip 1`; the tool's BMC mode applies both.
  **Strictness issues fixed (2026-09-13, branch `fix/q7n-slang-strict-rtl`).** The SoC now
  elaborates under yosys-slang in strict LRM mode — no `--allow-use-before-declare`, no
  `--compat vcs` (4 errors → 0):
  * `soc_top.sv` used `ext_irq`/`timer_irq` ~190 lines before declaring them; the IRQ `logic`
    declarations now precede `u_ext_irq_sync`/`u_timer_irq_sync`. Ordering only.
  * `pll_clkgen_pnr.sv` (ASAP7 **and** Sky130 copies) declared `parameter int unsigned PLL_IMPL`,
    and `boot_rom.sv`'s `__pnr__` branch declared `parameter int unsigned MEM_INIT_FILE`, while
    both are driven by `parameter string`. Synlig-era workarounds that only "worked" because sv2v
    emits untyped parameters; now `parameter string`. Neither shim reads the value.
  Re-verified: `soc_all` **183/183 PASS** (26 suite runs, including all four multiclock suites
  that exercise the IRQ synchronisers), Verilator lint clean, both sv2v netlists regenerated, and
  the equivalence tool now runs strict by default.
  ⚠️ **Correction to the results above:** the `soc_top_sv2v.v` those numbers were measured against
  was **stale** — it predated the `RAND_CDC_DELAY_*` parameters added to `cdc_2ff_sync.sv`. The
  full per-module re-sweep on the freshly regenerated netlist, in strict mode, reproduces them
  exactly: the same 25 modules proven (including `boot_rom` 79 and `pll_clkgen` 18, the two whose
  parameters changed), `sram_controller` proven at `MEM_WORDS=16`, and the same `pmu` 39 /
  `dma_engine` 128 induction residue.
- **CPU macro LEF lacks AXI4 burst ports** (`awlen`/`wlast`/…) — abstract predates
  the M2 burst upgrade; SoC burst nets dangle at the macro boundary. Indicative-PPA
  acceptable; regenerate the abstract for a clean integration (bead
  `claude_verilog_test-g0o`).
- Timing showed run-to-run variance (run 14 +113 ps vs run 15 −341 ps with the LEF
  change); the +113 ps margin is an indicative single-run result.

## PDN caveat (2026-09-12, beads `gyx` / `4l8`) — every ASAP7 run has an empty power grid

Counting `dbSWire` shapes on the POWER/GROUND nets of each run's post-PDN ODB:

| ODB | PG shapes |
| --- | --- |
| `pnr/sky130/soc/runs/RUN_2026-07-31_05-13-54/17-openroad-generatepdn` | VPWR 65 610 / VGND 65 939 |
| `pnr/asap7/soc/runs/RUN_2026-08-09_14-36-16/17-openroad-generatepdn` — **run 23, the accepted #96 sign-off** | **0 / 0** |
| `pnr/asap7/cpu/runs/RUN_2026-09-10_05-13-18/20-openroad-generatepdn` — 3.0.14 | **0 / 0** |

The sky130 row is the positive control (same script, same OpenROAD 26Q2 binary), so this is a
real absence, not a measurement artifact.

**Cause.** `pdngen` = `check_setup; build_grids; write_to_db; reset_shapes`. On ASAP7,
`[ERROR PDN-0179] Unable to repair all channels` fires *inside* `build_grids`, before
`write_to_db`. The local warn-and-continue patch in `pdn.tcl` (bead `ocm`) swallowed the error
and let the flow continue — with nothing written. The flow's "benign PDN-0179" line therefore
meant "PDN silently absent".

**What this withdraws.** The "PDN = benign tap-cell artifact" note on the CPU/GPU/SoC sign-offs
is withdrawn: there were no violations because there were no shapes. `analyze_power_grid`'s
`PSM-0069` was never a tap-cell connectivity problem either — it had no grid to analyse.

**What it does *not* change.** Timing, power and area were always GRT/estimate-based and are
unaffected in kind. What does change is routing: every ASAP7 route ran with M1/M2/M5 free of
PDN metal, so all ASAP7 DRC counts (including the 171-DRC CPU result on bead `ocm`) are a
lower bound, not closure. Re-run the routing gate once the grid actually commits.

**Fix landed in the toolchain** (both LibreLane trees, `librelane/scripts/openroad/pdn.tcl`):
decompose `pdngen` so a failed `build_grids` still commits what it built. On the CPU block this
goes 0 → 16 071 VDD / 17 151 VSS shapes. Residual: 550 VDD / 414 VSS unconnected shapes on M4
(the SRAM macro PG pins, skipped because macro via insertion follows channel repair) + 18+18 on
M1. Root-causing PDN-0179 itself is tracked on bead `4l8`.

### PDN fixed (2026-09-12, same day) — ORFS-style grid builds, and IR drop now runs

Root cause of the `PDN-0179` channel failure: the old grid connected the **M1 followpin rails
directly to the M5 straps** (a four-layer stack) and used M2 only as a sparse 4.5 µm-pitch strap
running *parallel* to those rails. ASAP7 std-cell rails sit on M1 running horizontally (M1's
non-preferred direction), so most rails had nothing reachable above them and channel repair
could not fix it — 27 unrepairable channels, all on M1, in the macro-free regions
x 82.19–124.96 µm and y 104.19–123.42 µm.

Fix ported from ORFS `flow/platforms/asap7/openRoad/pdn/BLOCKS_grid_strategy.tcl`: followpins on
**both M1 and M2** (0.018 µm wide, 0.54 µm pitch — one per row), then M2→M5→M6, with the macro
grid connecting M4↔M5 because the SRAM PG pins are on M4. Landed as
`pnr/asap7/pdn_asap7_orfs.tcl` (+ per-design `pdn_orfs.tcl` wrappers, `PDN_CFG` in both
`config_3014.json`).

Measured on the CPU block (`RUN_2026-09-10_05-13-18` step-18 ODB, standalone harness):

| | old grid | ORFS-style grid |
| --- | --- | --- |
| remaining channels | 27 | **0** |
| PG shapes committed | **0** | 27 999 VDD / 27 213 VSS |
| `check_power_grid` | `PSM-0069` both nets | **PASS** both nets |
| unconnected shapes / instances | 964 / 357 (partial-commit build) | **0 / 0** |

IR drop then needed one more thing: ASAP7 shipped **no via resistances**, so PSM aborted with
`PSM-0021` "Resistance map contains invalid values" even with clean connectivity. Added `VIAS_R`
to both `config_3014.json` using ORFS's values (`flow/platforms/asap7/setRC.tcl`). With that:

```
[INFO PSM-0040] All shapes on net VDD are connected.
Worstcase IR drop: 1.28e-03 V   Percentage drop: 0.18 %   (VDD)
Worstcase IR drop: 1.31e-03 V   Percentage drop: 0.19 %   (VSS)
```

⚠️ **Indicative only.** That number came from a standalone harness on a *floorplan-stage* ODB
(step 18, before placement/CTS/route) combined with the final run's SPEF, so instance power and
shape geometry do not correspond to the same design state. It demonstrates the flow works
end-to-end; it is **not** a sign-off IR figure. A full 3.0.14 CPU run with `PDN_CFG` +
`VIAS_R` + `RUN_IRDROP_REPORT=true` is still required, and routing with a real grid on the
tracks will be harder than every previous ASAP7 route.

### Routing with a real PDN is host-blocked (2026-09-12, bead `4l8`)

Every ASAP7 routing result in this repo was produced with **no** power grid on the tracks (see the
PDN caveat above). With the grid fixed and actually committed, detailed routing no longer fits on
this 15.9 GB host. Four attempts, all on the CPU block:

| PDN density | util / DRT threads | cap | reached | violations | peak |
| --- | --- | --- | --- | --- | --- |
| ORFS M5 2.16 / M6 4.32 | 50 / 8 | 12 GiB | 90 % of iter 0 | 122 121 | 13.4 GB |
| ORFS M5 2.16 / M6 4.32 | 50 / 4 | 14 GiB | 90 % of iter 0 | 122 121 | 13.4 GB |
| 3× sparse 6.48 / 12.96 | 50 / 4 | 12 GiB | ~75 % of iter 0 | 83 207 | 11.2 GB |
| 3× sparse 6.48 / 12.96 | 45 / 2 | 13 GiB | 80 % of iter 0 | 112 764 | 12.8 GB |

All four died inside **iteration 0 of 12**. For reference, the PDN-free run peaked at 12.4 GB and
did converge, to 1991 DRC — so a real grid costs roughly 20–30 % more violations, and this host has
no headroom to absorb that.

**What did not work, and is worth not retrying blindly:**

* *Sparser straps.* Three densities were measured (0.18 %, 0.52 %, 1.37 % worst-case IR). Violation
  counts barely moved — the congestion is driven by the **M2 followpins**, one track per row, not by
  the M5/M6 mesh. Sparser straps buy IR margin, not routing headroom.
* *Lower utilization.* `FP_CORE_UTIL` 50→45 produced an identical violation count (44 103 at the
  same checkpoint) and **more** memory, because the larger die means more area to hold state for.
* *Fewer DRT threads.* 8→4→2 moved the peak only marginally; memory is dominated by violation
  markers, not per-worker state.
* *Avoiding M2 entirely.* Rails on M1 climbing straight to M3 leaves every rail unconnected —
  pdngen will not stack M1→M3 through M2. M1→M2 followpins are the only legal way up, so the M2
  cost is structural.

**Conclusion.** PDN-clean routing on this design needs a machine with ≥32 GB, the same gate already
recorded for the Sky130 GPU stages. The PDN fix itself is verified independently of routing: the
grid builds and passes `check_power_grid` on CPU, GPU and SoC, and IR drop runs end-to-end. What
remains unverified is whether this design still closes DRC once the grid occupies the tracks — and
the honest expectation, given 1991 DRC PDN-free, is that it will need work.

## cpu_clk CTS hold-skew fix + combined rvb/0ah re-run (2026-09-17, beads `0ah`/`rvb`/`ydw`)

Bead `0ah` (filed during `w3a`'s honest post-GRT STA close-out) found the cpu_clk clock-tree
worst hold skew regressing from -823.5 ps (post-CTS-repair, placement-estimate parasitics) to
-1687.9 ps (post-GRT, real in-session-GRT parasitics, bead `je8`'s methodology) at
`u_cpu_axi_cdc.u_w_fifo`. Diagnosis (live OpenROAD session, forced `global_route` +
`estimate_parasitics -global_routing`, `report_parasitic_annotation`-gated): the regression was
real, not a placement-estimate artifact, but split into two effects — a genuine ~79 ps CTS-level
imbalance (`cpu_clk_i` and `cpu_gated_clk_regs` are balanced as fully independent TritonCTS trees
across the `u_cpu_cg` ICG boundary, worsened by one long-wire-repair buffer sized against
placement-estimate parasitics), and a separate, larger post-GRT-repair effect later found (by
another agent, bead `0ah` comment) to be a mis-attribution — `w3a-sta-7`'s -1687.9 ps number was
captured on `RepairDesignPostGRT`'s output, **skipping** `ResizerTimingPostGRT` (the hold-repair
step), not a genuine end-of-flow defect.

**Fix**: `CTS_BALANCE_LEVELS` + `CTS_OBSTRUCTION_AWARE` (both existing, previously-unused
LibreLane `Variable`s) in `pnr/asap7/soc/config_multiclock_hier_0ah_cts.json`, validated CTS-only
(`--from OpenROAD.CTS --to OpenROAD.STAMidPNR-1`, seeded from a pre-CTS checkpoint so
synthesis/placement stay identical to baseline): apples-to-apples at the same pipeline stage, hold
violators 705→0, hold WNS -639.3→0 ps, hold TNS -328 424→0 ps; setup violators 29 112→9 168, setup
TNS 3.8× better. Re-validated with real in-session-GRT parasitics (annotation-gated,
1548/204 196 unannotated, matching the unfixed baseline's 1553/204 196 coverage): worst hold skew
-902.1→+267.2 ps (cpu_clk), -187.1→+581.2 ps (sys_clk) — confirms the gain survives under real
parasitics, not just placement-estimate.

### Combined re-run: rvb RTL + 0ah CTS fix + rsz6/rsz7 bounded post-GRT repair

`soc-rvb-0ah.scope`, `pnr/asap7/soc/runs/RUN_2026-09-16_19-19-45`,
`config_multiclock_hier_rsz7_0ah.json` (= `config_multiclock_hier_rsz7.json`'s
`STA_POSTGRT_INSESSION_GRT` + rsz6's bounded post-GRT repair settings, plus the two CTS keys
above). Fresh full flow from synthesis on current RTL (bead `rvb`'s registered SRAM one-hot
write pre-decode `word_sel_q` + registered AXI-Lite read mux `r_dvalid_q`/`r_ddata_q`, verified
regression-clean at `soc_all` 178/178, commit `aaeaf36`), `--to OpenROAD.STAMidPNR-3` (includes
`RepairDesignPostGRT` and `ResizerTimingPostGRT`, real in-session GRT parasitics throughout,
annotation-gated: 1639/204 196 unannotated at all three post-GRT steps — like-for-like with the
1553 baseline). 22-minute wall time.

**Result — hold is clean on the real, complete flow path:**

| metric | STAMidPNR-3 (this run) | prior reference |
| --- | --- | --- |
| hold WNS / TNS / violators | **0 ps / 0 ps / 0** | -917 ps / -- / 718 (`w3a-sta-7`, pre-`ResizerTimingPostGRT` snapshot — not the true end state, see `0ah` comment) |
| hold skew, cpu_clk / sys_clk | **+249.2 ps / +656.5 ps** (both passing) | -1687.9 ps worst (pre-fix) |
| setup WNS / TNS / violators | -1144.5 ps / -17 625 151 ps / 40 192 | -2084 ps / -- / 41 864 (`w3a-sta-7`, different RTL vintage) |
| power (fabric-only / total) | 111.2 mW / 303.4 mW | -- |

Post-CTS-repair checkpoint (`34-openroad-stamidpnr-2`, placement-estimate parasitics): setup WS
-960.8 ps / TNS -8 847 840 ps / 26 662 violators; hold WS +26.2 ps / 0 violators; skew worst_hold
+590.5 ps, worst_setup +636.3 ps. `CTS_BALANCE_LEVELS` inserted a 17-stage `delaybuf_*_sys_clk`
chain (~330 ps insertion) as part of rebalancing sys_clk this time (not cpu_clk) — not directly
comparable to attempt 4's own post-CTS numbers since `-skip_buffer_removal`, both CTS fixes, and
the rvb RTL are all simultaneously different from attempt 4 here.

**Setup remains far from closed** — 40 192 violators, dominated by two classes, neither a
clock-tree/CTS problem:

- **rvb Path B** (GPU `s_axil_rdata` → `periph_bridge`, the `axi_lite_interconnect` registered-mux
  fix): confirmed no longer limiting — worst violator in this class is only -113.8 ps (21 total),
  far from the design's -1144.5 ps worst.
- **rvb Path A** (SRAM write-decode `s_wvalid` fanout, the `word_sel_q` registered one-hot
  pre-decode fix): improved but not closed. The original *non-terminating oscillation* (bead
  `w3a`) is gone — the flow now runs end-to-end in 22 minutes — because `word_sel_q` bounded
  `s_wvalid`'s immediate fanout from ~32 768 per-bit branches to a ~1024-wide `word_we` AND array.
  But `w_commit` (and therefore every `word_we[gw]` branch) is still purely combinational from
  `s_wvalid`, so `u_gpu/m_axi_wvalid` still directly launches 6 093/40 202 (15 %) of all setup
  violators, worst -954.8 ps — second only to the new #1 class below. Bead `rvb` left **open**
  with this residual recorded.
- **New #1 class, not caused by rvb**: the SRAM flat `mem[]` array's own combinational 1024:1 read
  mux (`assign s_rdata = mem[r_idx]`, `rtl/soc/sram_controller.sv:359`, `r_idx` registered at
  lines 315/330) — a characteristic the module's own header (lines 6-8, 20-22) already documents.
  9 259/40 202 (23 %) of all setup violators, worst -1144.5 ps
  (`u_sram._276653_/QN → u_dma.*/D`). Filed as bead `ydw` (P2, new) — candidate fix is a
  registered read-data/address pre-decode stage (adds read latency, needs human approval, not
  implemented).

**Bead outcomes**: `0ah` **closed** (hold genuinely fixed on the real flow path). `rvb` **left
open** (Path B closed-out-worthy, Path A improved but still a top-2 violator class — see that
bead's comment for the honest breakdown). `ydw` **filed** (new, P2, SRAM read-mux).

### CORRECTION (2026-09-17): the CTS fix above was a no-op; reference numbers stand but are not reproducible from config

The `CTS_BALANCE_LEVELS` / `CTS_OBSTRUCTION_AWARE` config keys used in the section above are
**not real LibreLane 2.4.13 variables** in this project's runtime tree
(`~/Downloads/Github/librelane`, git commit `3562a8d`, 2026-02-27, unmodified). Both
`/nobackup/asap7_soc_runs/soc_rvb_0ah.log` and a later `soc-ydw` run's log print `WARNING An
unknown key 'CTS_BALANCE_LEVELS' / 'CTS_OBSTRUCTION_AWARE' / 'CTS_CLK_NET_BUFFER' was provided`,
and a direct read of `librelane/scripts/openroad/cts.tcl` confirms it builds its
`clock_tree_synthesis` argument list from only `CTS_CLK_BUFFERS`, `CTS_ROOT_BUFFER`,
`CTS_SINK_CLUSTERING_SIZE`, `CTS_SINK_CLUSTERING_MAX_DIAMETER`, `CTS_DISTANCE_BETWEEN_BUFFERS`,
`CTS_DISABLE_POST_PROCESSING`, and `CTS_CLK_MAX_WIRE_LENGTH` — never the two "fix" keys (nor the
pre-existing, also-unused `CTS_CLK_NET_BUFFER`, which predates bead `0ah`). **The config change
in `78c5051`/`f80cb92` was silently ignored by the tool; it did not cause the clean-hold result.**

Re-investigated (read-only, no OpenROAD sessions or PD runs launched) by diffing the reference
run (`RUN_2026-09-16_19-19-45`) against a same-config, RTL-updated run
(`RUN_2026-09-17_06-25-54`, bead `ydw`'s +36 sys_clk registered-read flops). Macro placement is
byte-identical in both (`u_cpu`/`u_gpu` FIXED at the same DEF coordinates), ruling out macro
movement. `clk_i`'s sink count grew 45305→45340 (consistent with the +36 flops) and its
macro/register split disappeared; but `cpu_clk_i`'s sink count is **unchanged** (172 in both
runs) and its split *also* disappeared — ruling out "this net's own sinks changed" as the
per-net trigger and pointing to a session-wide, not per-net, internal mode selection. Direct
evidence of two different internal code paths: the reference run's CTS log prints "blockages
from hard placement blockages and placed macros will be used" (`CTS-0201`) six times and never
prints `CTS-0200`; the `ydw` run's log prints a *different* message pair, `CTS-0200` ("0
placement blockages have been identified") plus `CTS-0201` ("placed hard macros will be treated
like blockages"), four times — the same message ID with two different strings, on the identical
bundled OpenROAD 26Q2 binary.

**Best-supported hypothesis (medium confidence, log-evidence-based, not confirmed against
TritonCTS source, which is unavailable for this closed-source-packaged nix build; no bisection
run was performed)**: TritonCTS in this OpenROAD build auto-selects between two internal
macro/blockage handling paths based on an undocumented, likely sink-count/density-driven
threshold evaluated once per `clock_tree_synthesis` invocation (not per net) — `clk_i`'s
sink-count growth from bead `ydw`'s RTL crossed that threshold and changed behaviour for *all*
clocks in that invocation, including the unrelated `cpu_clk_i`. The tool itself has no seed or
randomization flag in its help text, so it is very likely deterministic given fixed inputs; the
observed run-to-run difference reflects a real netlist/placement difference, not tool
non-determinism.

**Real, deterministic fix (proposed, not applied — requires human approval to edit the shared
`librelane` tree)**: `openroad` help text confirms `clock_tree_synthesis` in this 26Q2 build
genuinely supports a level-balancing toggle, an obstruction-awareness toggle, and macro
clustering size/diameter settings. Patch `cts.tcl` to translate four new env vars
(`CTS_BALANCE_LEVELS`, `CTS_OBSTRUCTION_AWARE`, `CTS_MACRO_CLUSTERING_SIZE`,
`CTS_MACRO_CLUSTERING_MAX_DIAMETER`) into the corresponding `clock_tree_synthesis` arguments, and
register matching `Variable` declarations (mirroring the existing
`CTS_SINK_CLUSTERING_SIZE`/`CTS_SINK_CLUSTERING_MAX_DIAMETER` pattern) so the config validator
accepts them instead of silently dropping them. Explicitly forcing obstruction-awareness plus
macro clustering size/diameter matched to the existing sink-clustering values (8/10) would make
the reference run's good behaviour reproducible by design rather than incidental.

**Net effect**: the reference run's numbers (hold WNS 0 ps / 0 violators at `STAMidPNR-3`) are
real measurements and are **not retracted** — but they are **not reproducible from the config
alone**; they depended on TritonCTS's own undocumented, netlist-sensitive behaviour on that
specific run. Bead `0ah` has been **reopened**. Beads `rvb` and `ydw` and their findings in the
section above are unaffected by this correction.

### FURTHER CORRECTION (2026-09-17, second pass): the "identical binary" premise above was also wrong

The correction section above assumed the reference run and `soc-ydw` used the same OpenROAD
26Q2 binary and differed only in RTL/netlist. That premise is wrong. Confirmed from artifacts
(read-only: log/config reads plus two cheap, no-design `-version`/`help` queries on already-
resident binaries — no new PD runs launched):

- **Attempt 4** (`RUN_2026-09-16_01-13-02`, the original bead `0ah` baseline, -823.5 ps
  post-CTS) and **`w3a-sta-7`** (`RUN_2026-09-16_05-52-48`, the original -1687.9 ps "post-GRT"
  number): `memory/pd/run_state.md`'s own header for that campaign states "tool: LibreLane
  2.4.13 ... bundled OpenROAD edf00dff / OpenSTA 2.6.0 (`OR_PATH_PREFIX=`)" — the **bundled**
  `edf00dff` build, not the pinned 26Q2 shim.
- The **reference run** (`RUN_2026-09-16_19-19-45`, this bead's closure basis): launched by a
  hand-rolled script that explicitly set `PATH` to the 26Q2 shim inside `nix-shell` — confirmed
  **26Q2** by its 1639-unannotated-driver count and a repair-progress table with Area/StTNS/EnTNS
  columns.
- **`soc-ydw`** (`RUN_2026-09-17_06-25-54`): launched via `make librelane-asap7-soc-multiclock-hier`,
  which never sets `OR_PATH_PREFIX` (new bead `djm`) — confirmed **`edf00dff`** by its
  4663-unannotated-driver count, a repair-progress table lacking the Area/StTNS/EnTNS columns
  (single TNS column instead), and the live process binary itself reporting version
  `edf00dff99f6c40d67a30c0e22a8191c5d2ed9d6`.

So the real comparison this whole investigation made was **bundled `edf00dff` (attempt 4,
`w3a-sta-7`, `soc-ydw`) vs the pinned 26Q2 (the one reference run)** — a tool-version difference,
not a config or session-state difference. `clock_tree_synthesis` help text differs between the
two binaries: 26Q2 adds `macro_clustering_size`/`macro_clustering_max_diameter` and a
`no_obstruction_aware` complement that `edf00dff` lacks entirely. Since the shared `cts.tcl`
never passes any macro-specific flag explicitly, the two binaries' own different built-in
defaults for a clock net mixing macro and register sinks is the simplest, best-supported
explanation for the macro/register split and latency-balancing difference — superseding the
"session-wide TritonCTS mode" hypothesis in the correction above (whose underlying log
observations remain accurate, just better explained this way).

**Revised conclusion**: bead `0ah`'s apparent "fix" was most likely the pinned 26Q2 build's
TritonCTS macro-aware clustering, reached by accident because the validating script bypassed a
buggy Makefile target — not any config key (already confirmed a no-op) and not a documented,
controllable CTS setting.

**New Makefile gap found (bead `claude_verilog_test-djm`, P1, filed, not fixed)**:
`librelane-asap7-soc-multiclock-hier` — the target this entire campaign (`w3a`/`rvb`/`0ah`/`ydw`)
has used — is missing from `pnr/Makefile`'s target-specific `OR_PATH_PREFIX` assignment
(~line 918), even though `librelane-asap7-soc-multiclock` (without `-hier`) is present. Its
prerequisite `check-asap7-openroad` correctly verifies `ASAP7_OPENROAD_BIN` points at a valid
26Q2 build and explicitly rejects `edf00dff` — but only checks the *variable's value*, not that
the flow's actual bare `openroad` invocation resolves to it. The preflight passes while the flow
silently uses the rejected build anyway: precisely the "silent fallback to LibreLane's own
OpenROAD" failure mode (bead `xy6`) this check exists to prevent, via an untested code path.
One-line fix (add the target to the existing list) described in bead `djm`; not applied yet.

**Revised fix recommendation**: the `cts.tcl` passthrough proposed in the correction above is
most likely **unnecessary**. If bead `djm`'s Makefile fix is applied and the flow consistently
runs on the pinned 26Q2 build, 26Q2's own default TritonCTS macro-clustering behaviour may
already reproduce the clean-hold result with no new config knobs — the passthrough should be
treated as a fallback only if a properly-pinned 26Q2 re-run does *not* reproduce it on its own.

Bead `0ah` remains open. The full `0ah`/`rvb`/`ydw` comparison chain needs re-running on a
consistently-pinned 26Q2 build (after `djm`'s fix) before this bead can be honestly closed.

### 2026-09-17: bead `djm` fixed, clean 26Q2 re-run (`soc-ydw2`, `RUN_2026-09-17_09-01-42`) — `ydw` closed, `0ah` closed, `rvb` remains open

**`djm` fix** (commit `eb7f4be`): `pnr/Makefile`'s target-specific `OR_PATH_PREFIX` list
(~line 911-918) now includes `librelane-asap7-soc-multiclock-hier`. `check-asap7-openroad`
(the shared preflight) was also hardened: it now resolves a bare `openroad` inside `nix-shell`
under the *caller's* `OR_PATH_PREFIX` (propagated to prerequisites by GNU Make) and fails the
build if it does not land on the pinned shim — so a future target that forgets to join the list
fails loudly at preflight instead of silently mis-running on the bundled build. An audit of
every other ASAP7 target depending on `check-asap7-openroad` found no further gaps.

**Re-run**: `make librelane-asap7-soc-multiclock-hier SOC_CONFIG=config_multiclock_hier_rsz7_0ah.json
LIBRELANE_EXTRA_ARGS="--to OpenROAD.STAMidPNR-3"`, unit `soc-ydw2`, run dir
`pnr/asap7/soc/runs/RUN_2026-09-17_09-01-42`, `EXIT_CODE=0`. Binary confirmed live via
`/proc/PID/exe` at the Floorplan/PDN stage: `/nix/store/hgqrwa4687mf7n0y2x6lcgx1kj42sfga-openroad-26Q2/bin/.openroad-wrapped`
— the pinned 26Q2 build, launched through the **standard** Makefile target for the first time
in this campaign (not a hand-rolled `PATH`-override script).

**STAMidPNR-3 final (nom_tt_025C_0p7V) vs. reference `RUN_2026-09-16_19-19-45` (26Q2, rvb RTL, same config):**

| Metric | Reference (rvb RTL) | `soc-ydw2` (ydw RTL) | Δ |
| --- | --- | --- | --- |
| Setup WNS | -1144.5 ps | -1050.16 ps | +94.4 ps (+8.2%) |
| Setup TNS | -17,625,151 ps | -14,423,700 ps | +18.2% |
| Setup violators | 40,192 | 33,196 | -17.4% |
| Hold WNS / TNS / violators | 0 / 0 / 0 | 0 / 0 / 0 (WS +38.01 ps) | clean, both |
| cpu_clk hold skew | +249.2 ps | +236.29 ps | within ~13 ps |
| sys_clk hold skew | +656.5 ps | +640.42 ps | within ~16 ps |
| Power total / fabric-only | 303.4 / 111.2 mW | 293.2 / 100.7 mW | ~-3% |
| Unannotated / partial drivers | 1639 / — | 1426 / 0 | fewer (RTL-size delta) |

**Bead `ydw` — CLOSED.** Violator-class analysis of `violator_list.rpt` (33,206 lines):

- The SRAM flat-array read-mux class (startpoint `u_sram` mem[] `QN` → endpoint `u_dma` or
  `u_bus.u_xbar`; reference's #1 class, 9,259 violators, worst -1144.5 ps) is **completely gone**
  — 0 matches for `u_sram.*→u_dma` or `u_sram.*→u_bus.u_xbar` in the final violator list.
- It is replaced by a much smaller, module-internal class, `u_sram → u_sram` (the mem[]→
  `r_data_q` head-register segment ydw's design intentionally confines the mux's fan-out to):
  **32 violators** (matches the 32-bit read-data width), **worst slack -947.29 ps**. This is
  worse than the pre-measurement estimate of ~-300 ps (about 3x), a real and substantial
  residual, but it no longer propagates outside `sram_controller.sv` and is no longer the
  design's critical path. Post-synthesis instance names are fully anonymized (the flat 4096×32
  array is fully deduped/optimized by yosys), so the exact bit/word cannot be cited by RTL name.
- The new #1 class overall (by count and by worst slack) is **not** a read-side effect at all:
  `u_gpu/m_axi_wvalid → u_sram` (rvb's Path A write-decode residual), 16,400 violators, worst
  -1050.16 ps = the run's new overall setup WNS. `u_dma → u_sram` (DMA's own analog of the same
  pattern) is a close second: 14,392 violators, worst -975.65 ps. Together these two classes are
  92.7% of all setup violators.
- A 2-stage mux split (e.g. 32:1×32:1 instead of flat 1024:1) for the residual mem[]→`r_data_q`
  path was assessed as a plausible future improvement given the -947 ps residual, but judged
  **not urgent**: the write-path classes are ~100 ps worse and >500x more numerous, making them
  the higher-leverage target for the next PD iteration. Not implemented.

**Bead `rvb` — remains OPEN.** Path A (`u_gpu/m_axi_wvalid` → flat write decode) is not gone;
it is now the design's #1 class (16,400 violators / -1050.16 ps vs. the reference measurement's
6,093 / -954.8 ps). A DMA-side analog of the same pattern (`u_dma → u_sram`, 14,392 / -975.65 ps)
also appears. Whether Path A's own severity truly regressed, or the count/attention simply
redistributed onto it once the read-mux class (ydw) was removed, is not isolated by this
measurement — recorded on the bead as an open question. Recommended as the next PD target given
it is now >90% of all setup violators combined with its DMA analog.

**Bead `0ah` — CLOSED**, resolved by pinning 26Q2 (`djm`). Hold is clean end-to-end and clean
*before* dedicated hold repair even runs (0 violators already at the post-CTS checkpoint,
`32-openroad-stamidpnr-1`, WS +36.64 ps). Both clocks' skew is healthy positive and within
~13-16 ps of the original (accidental) reference-run measurement, now reproduced through the
**standard** Makefile path. This confirms the bead's own final root-cause conclusion — 26Q2's
TritonCTS macro-aware clustering default, not the confirmed-no-op `CTS_BALANCE_LEVELS`/
`CTS_OBSTRUCTION_AWARE` config keys — and satisfies the bead's own stated reopen condition (a
clean re-run of the full `0ah`/`rvb`/`ydw` chain on a consistently-pinned 26Q2 build via the
fixed Makefile target). No `cts.tcl` passthrough patch is needed.

Note: this run stopped at `--to OpenROAD.STAMidPNR-3` (no detailed routing / DRC / antenna / LVS
steps ran), so it is a timing-only measurement, not a routing sign-off; the power figures above
include the `Macro` power group (192.5 mW), unlike some earlier ASAP7 sign-offs in this document
that reported fabric-only figures as the headline number.
