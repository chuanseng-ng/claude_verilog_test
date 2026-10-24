# DQC flow: SpyGlass lint / CDC / RDC and Cadence HAL on `soc_top`

Status (2026-10-24): **lint and HAL measured; CDC and RDC crossing checks are NOT RUN by the tool with the licences served today.** Read "Results" before trusting any green.

Local flow for the EDA host (SpyGlass X-2025.06-SP1, Cadence HAL 24.03). It is **not** in CI: GitHub runners have no SpyGlass. CI keeps the open-source `cdc_snitch` gate (`make -C sim cdc`, `tools/cdc/`). Everything lives in `dqc/`.

## How to run

```bash
make -C dqc lint        # SpyGlass lint/lint_rtl                          (~7-15 min, 1.7 GB)
make -C dqc cdc         # cdc/cdc_setup_check + cdc/cdc_verify_struct     (~1.5 min each)
make -C dqc rdc         # rdc/rdc_verify_struct                           (~1.5 min)
make -C dqc hal         # Cadence HAL (secondary lint)
make -C dqc selftest    # negative control on dqc/selftest/bad_cdc.sv     (~20 s)
make -C dqc all         # lint cdc rdc hal, keeps going, fails if any failed
make -C dqc clean
make -C dqc lint ARM=sky130     # +define SRAM_SKY130 (untested, see "Open work")
```

Run one SpyGlass goal at a time (shared host, other EDA jobs). Each target prints fatal/error/warning counts (all UNWAIVED), the SpyGlass-waived count, the run's wall clock and peak RSS, the report path and a verdict:

| Verdict | Exit | Meaning |
| :-- | :-- | :-- |
| PASS | 0 | rules completed, 0 unwaived Fatal/Error |
| FAIL | 1 | rules completed, at least one unwaived Fatal/Error (count printed; nothing hidden) |
| INCOMPLETE | 2 | the goal did not complete its rules (script aborted, no results summary, a first-party module black-boxed by the tool, an undefined module, a rule NOT RUN for licence reasons, a bad waiver, a stale waiver). Never clean. |

The verdict is read from `moresimple.rpt` by `dqc/scripts/dqc_report.py` (HAL: `hal_report.py`), never from the tool's exit code. `dqc/run/<arm>/<tag>.unwaived.tsv` lists every row; `<tag>.summary.json` is machine-readable.

## What is analysed

* Top `soc_top`; source list = `rtl/filelist/soc_top.f` (generated from the authoritative Make variables, not forked) resolved to absolute paths by `dqc/scripts/gen_sourcelist.py`. No testbench file.
* **SRAM hard macros are black boxes** (`dqc/stubs/*.sv`, port-only modules): the sim models in `sim/` and `rtl/mem/` are behavioural arrays that a lint tool would report as thousands of reset-less flops with a negedge-launched output, which is not a property of the macro. Macro-output findings that are only "undriven inside the stub" are stub artifacts. Modules: `sram_1rw_256x32_freepdk45` (default arm), `sky130_sram_*` (sky130 arm), `sram_1rw_128x32_asap7` (GPU shared memory, both arms).
* **String/real parameter overlay.** SpyGlass rules SYNTH_5260 (SystemVerilog `string`) and SYNTH_5247 (`real` parameter) are SynthesisErrors whose documented consequence is that the module "is considered as a black box for which no SpyGlass analysis is done". Here that would black-box `soc_top` itself, `pll_subsystem`, `pll_clkgen` and `boot_rom` (measured: 4 `UnsynthesizedDU`). `gen_sourcelist.py` therefore feeds SpyGlass a **line-count-preserving overlay** of those four files (`parameter string X` -> `parameter X`; `parameter real X = 1.3e9` -> `parameter X = 0`, RNM-only constants in a pruned generate branch). `rtl/` is untouched and report line numbers still match `rtl/`. `dqc_report.py` turns any remaining `UnsynthesizedDU`/undefined module into INCOMPLETE.
* `mthresh 65536` (the boot ROM and SRAM controller arrays are 32768 bits; the default 4096 aborts synthesis of them).
* GuideWare: `latest` = 2025.06 `block/rtl_handoff` (the host has 2020.12 through 2025.06, newer than the 2023.12 first assumed).

## Constraints (`dqc/sgdc/soc_top.sgdc`) and why

Derived from `soc_top.sv` ports, `pnr/constraints/phase5_soc_multiclock.sdc` and `tools/cdc/cdc_config.yml`, not guessed.

| Item | Constraint | Source |
| :-- | :-- | :-- |
| clocks | `clk_i` (sys_clk), `cpu_clk_i` (cpu_clk), `tck_i` (TAP), `scan_clk_i` | SDC sec.1; DFT_ARCHITECTURE.md 15.5; internal `core_clk`, `cpu_core_clk`, `*_gated_clk` are derived by SpyGlass through the PLL-stub passthrough and `rv32i_clock_gate` (same aliasing as `cdc_config.yml` `domain_aliases`) |
| resets | `rst_n_i`, `cpu_rst_n_i`, `trst_ni` (active low); the registered PMU and WDT resets `u_cpu_pmu_rst_sync.rst_n_i`, `u_cpu_wdt_rst_sync.rst_n_i` | `Reset_info09a` demanded them (flop-generated async resets are not propagated automatically) |
| functional mode | `scan_mode_i=0`, `scan_en_i=0`, `scan_rst_ni=1`, and the TAP-held `u_dft_ctrl.tap_scan/tap_rst_assert/tap_serial/tap_scan_en=0` | SDC sec.4a `set_case_analysis`; `dft_ctrl.sv` ORs the TAP onto the pins |
| synchronisers | none declared: `cdc_sync`, `cdc_reset_sync`, `cdc_gray_fifo`, `async_axi_fifo`, `apb_cdc_bridge` are recognised **structurally** by SpyGlass (flop chains, gray pointers). Declaring them as qualified would be done with `abstract_port` / `cdc_attribute` only after the crossing rules can run (see Results) | `cdc_config.yml` `required_synchronisers` |

TCK-domain crossings (the MBIST control word and status) are real crossings and stay visible.

## Tool and licence matrix (measured 2026-10-24)

| Tool | Use | State |
| :-- | :-- | :-- |
| Synopsys SpyGlass `lint/lint_rtl` | RTL lint (primary) | works, `checker` licence |
| SpyGlass `cdc/cdc_setup_check` | clock/reset setup sanity | works; 2 rules NOT RUN (`Ar_syncrst_setupcheck01`, `Ar_converge01`) |
| SpyGlass `cdc/cdc_verify_struct`, `rdc/rdc_verify_struct` | the crossing checks | **core rules NOT RUN**: `Ac_license01` "not run due to unavailability of cdc_adv_checker license feature". Not run: `Ac_unsync01/02`, `Ac_sync01/02`, `Ac_conv01-04`, `Ac_glitch03`, `Ac_coherency06`, `Ac_crossing01`, `Setup_quasi_static01`, `Ar_resetcross01`, `Ar_resetcross_matrix01`, `Ar_converge01`, `Ar_syncrst_setupcheck01`. The server does list `checker`, `adv_checker`, `Advanced_CDC`, `Advanced_RDC` (99 each, 0 in use, `lmutil lmstat -a -c 27080@eda.ic`), yet SpyGlass asks for `cdc_adv_checker`. **Owner action: ask the licence admin which key maps to `cdc_adv_checker`.** |
| Cadence HAL (`hal -sv`) | lint + structural (secondary) | works with `-NOHALSYNTH`; the synthesizability engine stalled > 5 min on a 40-line design (suspected licence wait), so it is off |
| Cadence Conformal Constraint Designer (`ccd`) | optional second CDC opinion | licensed, **not set up** (follow-up) |
| Cadence Jasper CDC / RDC | | not licensed |
| Ansys | | no RTL CDC/RDC product installed (RedHawk/Totem/AnsysEM only) |

## Results (arm `default`)

| Goal | Fatal | Error | Warning | Waived | Unwaived Fatal+Error | Wall / peak RSS | Verdict |
| :-- | --: | --: | --: | --: | --: | :-- | :-- |
| lint/lint_rtl, before waivers | 0 | 1024 | 604 | 0 | 1024 | 900 s / 1.66 GB (Tessent job concurrent) | FAIL |
| lint/lint_rtl, after `lint_soc_top.awl` | 0 | 0 | 608 | 1024 | 0 | re-report on the saved project: seconds | 0 errors (see note) |
| cdc/cdc_setup_check | 0 | 0 | 32 | 0 | 0 | 96 s / 1.65 GB | PASS (2 rules not run, accepted) |
| cdc/cdc_verify_struct | 0 | 0 | 45 | 0 | 0 | 90 s / 1.68 GB | **INCOMPLETE** (crossing rules not run) |
| rdc/rdc_verify_struct | not run on soc_top | | | | | selftest: 9 s / 0.77 GB | **INCOMPLETE** |
| HAL (`make hal`), raw | - | 3802 | 6337 warn / 1598 notes | 0 | 3802 | 36 s / 0.68 GB | FAIL |
| HAL, after config + `hal.waivers` | - | 1 | 6337 | 4 | 1 | 32 s / 0.68 GB | FAIL (open F-7) |

Note on the lint "after" row: the waiver was applied by loading the `.awl` into the saved project and re-writing `moresimple` (1632 generated, 1024 waived, 608 reported). The full `make lint` was not re-run end to end with the waiver in place. **First action on resume: `make -C dqc lint` and confirm PASS.**

### Negative control (`make -C dqc selftest`)

`dqc/selftest/bad_cdc.sv` contains an unsynchronised clk_a->clk_b crossing, the same crossing through a 2-flop synchroniser, and a clk_a flop driving the async reset of a clk_b flop. Result: **SELFTEST FAIL, as it must be today** - SpyGlass reported no `Ac_unsync*` and no `Ar_resetcross*` row because those rules did not run (licence). This is the proof that a "0 errors" CDC/RDC result on `soc_top` would have been vacuous, and why `cdc_verify_struct` and `rdc_verify_struct` end INCOMPLETE rather than PASS. Once the licence is fixed the selftest must go green (bad crossing flagged, synchronised one spared); that is the acceptance test for the CDC/RDC targets.

## Waivers (`dqc/waivers/`)

Format: SpyGlass `.awl` (Tcl `waive` commands), one per line, loaded by `sg_run.tcl`. `dqc_report.py` audits them: each needs `-rules`, a scope, and `-comment "id=; by=; why="`, else the run is INCOMPLETE. HAL waivers (`dqc/waivers/hal.waivers`, `id|tag|file|msg|by|why`, stale waivers fail).

| id | Rule | Count | Class | Justification |
| :-- | :-- | --: | :-- | :-- |
| lint-bootrom-undriven | UndrivenInTerm-ML | 1024 | tool artifact + design note F-2 | `boot_rom.mem` is filled by an `initial` block (sim `$readmemh`, PnR zero fill); synthesis ignores `initial`, so every word looks undriven |

All 1024 error-level lint findings are this one cause (one message per ROM word). No CDC/RDC waiver exists: nothing was reported, and none was written to get green.

## Findings

Real or possibly real, ranked by risk. These are proposals for `fix_requests`; `rtl/` was not edited.

| # | Risk | Where | Finding | Evidence / confidence |
| :-- | :-- | :-- | :-- | :-- |
| F-1 | **High (coverage, not an RTL bug)** | whole SoC | SpyGlass CDC/RDC crossing rules cannot run; the only measured CDC gate remains `cdc_snitch` | tool message, selftest |
| F-2 | Medium (design note) | `rtl/soc/boot_rom.sv:96-122` | In the ASIC/PnR arm the boot ROM has no content path (zero-filled `initial`); SpyGlass sees an array that is never driven. The DQC waiver hides the tool noise, not this fact | `UndrivenInTerm-ML` x1024 |
| F-3 | Low-Medium, UNVERIFIED | `rtl/soc/cdc/cdc_sync.sv:205` (instances in `u_dft_ctrl.u_clk_sw`, `u_cpu_axi_cdc` FIFOs, `u_uart_rx_sync`, `u_apb_dbg_cdc`) | STARC05-1.3.1.3: a synchronised/async reset net also reaches a flop D pin (e.g. `u_dft_ctrl.u_sw_rst` output into `u_clk_sw.en_a_q.D`, `s_rst_sync_n`/`m_rst_sync_n` into FIFO `full_q`). Reset used as data is an RDC-relevant pattern; needs the RDC rules to judge | warning rows, `lint.unwaived.tsv` |
| F-4 | Low | `rtl/soc/apb_interconnect.sv:75,85`; `rtl/soc/axi4_crossbar.sv:269,294,567-588` | W216 inappropriate range select on `int` loop index (`i[SEL_W-1:0]`, `m[MIDX_W-1:0]`) | 9 rows |
| F-5 | Low | `rtl/soc/apb4_register_bank.sv:98`, `axi_lite_register_bank.sv:134`, `aes128_core.sv:522` | FlopEConst: enable tied high on 31 flops (dead enable) | 31 rows |
| F-7 | Low (naming) | `rtl/soc/dft/mbist_xing.sv:26` | HAL VERCAS: identifier `CTL_W` reused with a case difference (only HAL error left, deliberately unwaived) | `make hal` |
| F-6 | Info | cdc setup: 13x `Reset_sync04` | `rst_n_i`/`cpu_rst_n_i`/`trst_ni` synchronised more than once per domain (e.g. `u_apb_dbg_cdc.u_m_rst_sync` and `u_cpu_axi_cdc.u_s_rst_sync`); consistent with the documented cross-coupled bridge reset design (`cdc_config.yml` waiver `cdc-bridge-cross-coupled-reset`) | expected |

Remaining lint warnings (W415a x276, STARC05-2.2.3.3 x81, W240 x75, W528 x62, STARC05-2.11.3.1 x31, ...) are style/dead-code classes (default-then-override assignment idiom, unused ports, combined FSM always blocks) and are listed, not waived, in `dqc/run/default/lint.unwaived.tsv`; they do not gate.

## Open work / exact resume point

1. Run `make -C dqc lint` end to end and confirm PASS with the waiver (only the saved-project re-report was done).
2. Resolve the `cdc_adv_checker` licence key, then re-run `make -C dqc selftest` (must go green), `cdc`, `rdc`; triage the real crossings (CDC/RDC) and add SGDC qualifiers for the project synchronisers only for crossings proven safe.
3. HAL: 3802 raw errors = 3797 CBPAHI (turned off, structure metric) + 4 GLTASR (waived, intentional DFT reset mux) + 1 VERCAS (F-7, open). Style categories are off via `HAL_NOCHECK`; 6337 warnings remain listed, not triaged.
4. `ARM=sky130` run (`SRAM_SKY130`).
5. Optional: Conformal Constraint Designer as a second CDC opinion.
