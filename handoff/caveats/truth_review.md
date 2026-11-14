# Truth review: TM part "Tool defects and standing caveats", the information notes, the dictionary terms

Reviewer: independent, read-only. Review date: 2026-11-14. Branch `docs/tm-standing-caveats`, uncommitted tree.
Scope: `docs/manual/tm/parts/06-tool-defects-and-standing-caveats.tex` (the "part"), the `information` notes in six files, four dictionary terms.
Each finding names its source. "INFERRED" marks a fact that I derived from configuration files and not from a record.

Cross-checks that passed and need no change:
- All 66 labels that the part cites exist (checked against `\label{}` in `docs/manual` and `labels.tsv`).
- The diff of the six note files and of `dictionary.yaml` / `glossary.tex` holds additions only (`git diff --numstat`: 0 deleted lines). Each note sits after the chapter heading and before `\begin{relocated}`. So no verbatim text changed.
- Deviation (a) is right: `git ls-files` shows the committed ASAP7 views in `pnr/asap7/cpu/macro/` (lef, nl.v.gz, nom_tt lib) and `pnr/asap7/gpu/macro/`. `pnr/asap7/soc/macro/` holds only `.gitignore` (it ignores `*.lef *.lib *.nl.v *.nl.v.gz`). `pnr/Makefile` copies the views into it.
- Deviation (b) is right: `cr:defect:synlig-struct-select-ainf` (D3 and Step 4) found the GPU fault on a cut cone of `gpu_compute_unit` and says "Not verified: ... the GPU netlist behaviour in simulation; the committed GPU macro views". `cr:defect:asap7-cpu-synlig-ma7:not-done` lists "the GPU macro".
- Deviation (c) is right in substance: `cr:run:phase5:routing-physical-closure-caveat-...-xy6` says "RESOLVED for new runs ... runs 14, 23 and every other pre-September run REMAIN TRUE and are not rehabilitated". Finding 3 narrows "new runs".
- Deviation (d) is right in substance: `cr:run:phase5:pdn-fixed-...` and `...routing-with-a-real-pdn-is-host-blocked-...-4l8`. Finding 2 narrows it.
- Deviation (e) is right: `USE_SYNLIG` is false in `pnr/asap7/{cpu,gpu}/config.json`, `config_3014.json`, all seven `pnr/asap7/soc/config*.json`, `pnr/sky130/cpu/config.json`, `pnr/sky130/soc/config.json`, `config_rccal.json`, `pnr/asap7/valu_hls*/config.json`. It is true in `pnr/asap7/{coalescer_hls,coalescer_rtl,hazard_hls,hazard_rtl,valu_rtl,template}/config.json`, `pnr/freepdk45/config.json`, `pnr/librelane/config.json`. The part omits `template` (finding 23).
- The quoted figures are the two figures of AGENTS.md section 2 only (-727.37 ps at 1750 ps, hold clean; 32 GB). The version numbers 0.42.0 / 0.48.0 come from CLAUDE.md.
- No "must" in the part.

---

## Numbered findings

### 1. OVERCLAIM-PERMITTED: Sky130 caveat says the CPU macro is corner-accurate
Where: `tm:status:sky130-single-sram-corner`, "What you may still say", bullet 1.
Current: "The CPU macro has its own Liberty view for each corner, and the standard cells vary with the corner. The record calls the CPU macro and the standard-cell logic corner-accurate."
Sources: `cr:pd:sky130-soc-sdc` says the CPU macro now maps "9 EXACT corner keys to 9 genuinely distinct per-corner Liberty views" and "Paths entirely within flat standard-cell logic ARE corner-accurate". The record does not call the CPU macro corner-accurate. INFERRED: the CPU macro holds SRAM macros of its own (`tm:pd:commercial-flow-comparison:1-executive-summary`: "rv32i_cpu_top with 10 sky130_sram_1kbyte_1rw1r_32x256_8"). `pnr/sky130/cpu/config.json` `EXTRA_LIBS` lists only `sky130_sram_1kbyte_1rw1r_32x256_8_TT_1p8V_25C.lib`. So the nine per-corner CPU views were written with a typical-corner model for the SRAMs inside the macro.
Replacement:
> \item The CPU macro has a separate Liberty view for each corner. The record calls the paths that are wholly in standard-cell logic corner-accurate.
> \item The CPU macro holds SRAM macros of its own. The flow of the CPU block reads one typical-corner Liberty view for them. So the paths through these SRAMs inside the CPU macro have the same limit as the paths through the SRAM of the SoC. This statement comes from the configuration of the CPU block and not from a run record.

### 2. OVERCLAIM-PERMITTED: "The flow now builds the grid"
Where: `tm:status:asap7-empty-power-grid`, "What you may still say", bullet 1.
Current: "The flow now builds the grid. The grid passes the power grid check on the CPU, the GPU and the SoC, and the IR drop step runs."
Sources: `cr:run:phase5:routing-with-a-real-pdn-is-host-blocked-...-4l8`: "The PDN fix itself is verified independently of routing: the grid builds and passes check_power_grid on CPU, GPU and SoC". `cr:run:phase5:pdn-fixed-...`: the IR figure came "from a standalone harness on a floorplan-stage ODB" and is "Indicative only ... not a sign-off IR figure". Repository: `pnr/asap7/soc/pdn_orfs.tcl` header: "NOT yet referenced by any SoC config. config.json and config_multiclock.json still point at pdn.tcl, which carries the same M1->M5 defect". All seven `pnr/asap7/soc/config*.json` set `"FP_PDN_CFG": "dir::pdn.tcl"`. Only `pnr/asap7/cpu/config_3014.json` and `pnr/asap7/gpu/config_3014.json` set `"PDN_CFG": "dir::pdn_orfs.tcl"`. `pnr/asap7/cpu/config.json` and `gpu/config.json` (the sv2v configurations) do not.
Replacement:
> \item A fixed grid script exists. The record says that the fixed grid builds and passes the power grid check on the CPU, the GPU and the SoC. The record made this check without a route. Its IR drop figure is indicative only.
> \item Only the LibreLane 3.0.14 configurations of the CPU and of the GPU select the fixed grid. The configurations of the SoC still select the old grid script, which has the same fault.

Also change "What ends the caveat" to:
> A configuration selects the fixed grid, a detailed route on that grid finishes, and the DRC count is reviewed. The record says that the route needs a machine with 32~GB or more (\cref{tm:status:asap7-reharden-host}). The record expects that the design needs work to close DRC with the grid in place.

### 3. OVERCLAIM-PERMITTED: "The flow now commits wires"
Where: `tm:status:asap7-drc-antenna-withdrawn`, "What you may still say", bullet 1.
Current: "The flow now commits wires. The record marks this as resolved for new runs. It does not rehabilitate the old runs."
Sources: `cr:run:phase5:routing-physical-closure-caveat-...-xy6`: the fix is the OpenROAD pin of LibreLane 3.0.14 plus "a +10 DBU shift on gen_data_sram[1]"; the first passing run is a CPU block run; "GPU and SoC still have RUN_SPEF_EXTRACTION false". `cr:run:phase5` (2026-09-18 update, "Unaffected by this update"): "the zero-routed-wire caveat (xy6) and the macro-power-excluded caveat both still stand" for the present SoC point.
Replacement:
> \item The record shows a CPU block run that committed wires, with a newer OpenROAD and a point fix for one column of macros. The record marks the fault as resolved for new runs. It does not make the old runs valid.
> \item The record says that the caveat of routing with no wires still applies to the present SoC point (\cref{tm:status:asap7-soc-setup-wns}).

### 4. MISSING: present SoC point omits the routing caveat and misplaces the grid statement
Where: `tm:status:asap7-soc-setup-wns`, "What you may still say", bullet 4.
Current: "The point still rests on the macro views and on the empty power grid (\cref{tm:status:synlig-macro-views,tm:status:asap7-empty-power-grid})."
Sources: `cr:run:phase5` 2026-09-18 update: xy6 "still stands" for this point; the point uses "annotated GRT parasitics, not SPEF". The empty-grid statement has no record for this run; it follows from `pnr/asap7/soc/pdn_orfs.tcl` and the SoC configurations (INFERRED, see finding 2).
Replacement:
> \item The point still rests on the macro views (\cref{tm:status:synlig-macro-views}). The record says that the caveat of routing with no wires still applies to it (\cref{tm:status:asap7-drc-antenna-withdrawn}). The configurations of the SoC select the old grid script, so the caveat of the empty grid also applies (\cref{tm:status:asap7-empty-power-grid}).

### 5. WRONG: "the current RTL" for a measurement of a past date
Where: `tm:status:asap7-soc-setup-wns` bullet 1 ("The point is a measurement of the current RTL on the fixed flow."); `tm:status:asap7-zero-wire-timing` bullets 2 and 3 ("on the current RTL with the fix").
Sources: the point is `RUN_2026-09-17_20-41-11` (`cr:run:phase5`). `cr:status:phase-status:current-phase` records Phase 6 complete on 2026-10-05 (GPIO, PWM, WDT, TRNG, I2C, crypto, NPU) and DFT work after it. The record's "current RTL" means the RTL of its date. In a book that states the present, "current" is wrong.
Replacements:
- SoC bullet 1: "The point is a measurement on the fixed flow, of the RTL of the date of the run. The RTL changed after the run. The record checked that no real signal driver lacked parasitics."
- Zero-wire bullet 2: "The record measured the CPU again, with the fix, on the RTL of a later date and at the period of the old figure of 1282~MHz. The CPU does not meet that period on that RTL (\cref{tm:pd:node-strategy:asap7-phase-23-sign-off-achieved-at-run-43-2026-05-20}). This is not a re-run of the old run."
- Zero-wire bullet 3: "A measurement of the SoC with the fix exists (\cref{tm:status:asap7-soc-setup-wns})."

### 6. OVERCLAIM-PERMITTED: the in-session global route is shown as a fixed guard
Where: `tm:defect:sta-without-in-session-route`, "Guard"; and the summary table row "Zero-wire timing ... Flow setting and annotation gate".
Current: "A flow setting makes the step run a global route in the same session. The record gives its name as \code{STA_POSTGRT_INSESSION_GRT=1}. The setting is in the shared LibreLane tree, which is outside this repository. The record also uses an annotation gate. ..."
Sources: `pnr/librelane_patches/librelane2413_postgrt_annotation_fix.diff`: "STA_POSTGRT_INSESSION_GRT (bool, default false)", "Unset is BYTE-IDENTICAL to upstream"; the annotation check "Prints a loud [WARNING] ... or exits 1 if STA_POSTGRT_UNANNOTATED_IS_ERROR=1". `git grep` finds the setting only in `pnr/asap7/soc/config_multiclock_hier_rsz7.json` and `config_multiclock_hier_rsz7_0ah.json`. No CPU or GPU configuration sets it. The setting is a configuration variable in the repository; the patch that adds it is to the shared LibreLane tree, and the repository keeps a copy of that patch.
Replacement (Guard):
> A patch of the shared LibreLane tree adds the setting \code{STA_POSTGRT_INSESSION_GRT}. When it is true, the step runs a global route in the same session before it reads the parasitics. The default is false, and then the step behaves as before. The repository keeps a copy of the patch in \src{pnr/librelane_patches/}. Two configurations of the ASAP7 SoC set the setting. The configurations of the CPU and of the GPU do not set it. The same patch counts the drivers without parasitics. By default it gives only a warning. It stops the step only when \code{STA_POSTGRT_UNANNOTATED_IS_ERROR} is 1.

Replacement (Work-around):
> Set \code{STA_POSTGRT_INSESSION_GRT} in the configuration, and read a timing figure only when no real signal driver lacks parasitics. The figures from the old flow stay unvalidated (\cref{tm:status:asap7-zero-wire-timing}).

Table cell "Guard": "Opt-in flow setting; annotation warning".

### 7. OVERCLAIM-PERMITTED: routing gate described as a closure check
Where: `tm:defect:flow-swallows-failure`, "Guard" and "Work-around".
Current: "The script ... fails when the route has no wires. It reads ... It exits 0 for a pass ..." and "It resolved the grid failure with a grid in the style of the OpenROAD flow scripts."
Sources: `tools/verif/check_asap7_routing.py` docstring: PASS needs routed nets, `route__wirelength__max` > 0 and zero `[ERROR DRT-` lines. `cr:run:phase5:...-xy6`: "the gate deliberately does not check DRC violations"; the first passing run had 2045 DRC errors. `pnr/Makefile` calls it from the ASAP7 CPU, GPU and SoC flow targets (`check-asap7-*-routing`); no workflow in `.github/` runs it. Grid: see finding 2.
Replacement (Guard, add after the exit-code sentence):
> It also fails on an error line of the route step. It does not count DRC violations. A run that passes the gate can have many DRC violations. The ASAP7 flow targets of \src{pnr/Makefile} run the gate after each flow. The CI does not run it.

Replacement (Work-around, second sentence):
> It resolved the grid failure with a grid in the style of the OpenROAD flow scripts. The configurations of the SoC do not select that grid yet (\cref{tm:status:asap7-empty-power-grid}).

### 8. WRONG: OpenSTA flag shown as silent; standard SDC precedence shown as a defect
Where: `tm:defect:opensta-datapath-only`, "Tool and defect" and "How it shows".
Current: "OpenSTA does not implement \code{set_max_delay -datapath_only}. It stops reading the constraint file at this flag. It also drops a maximum-delay constraint that crosses an asynchronous clock group." / "A single constraint file that has both the flag and the clock group never applies its crossing budgets."
Sources: `tm:pd:phase5-soc-multiclock-check-sdc` (relocated header): "-datapath_only aborts read_sdc immediately with STA-0563 'is not a known keyword or flag'"; and "report_checks reports 'No paths found' / 'Path Group: unconstrained' ... Standard SDC precedence (set_false_path > set_max_delay > set_multicycle_path) applies unconditionally in this tool". `ds:ch:verification-strategy` says the same. The CDC chapter (`tm:ch:mod-cdc-primitives`) agrees on both facts and does not call them silent.
Replacement (Tool and defect):
> OpenSTA does not implement \code{set_max_delay -datapath_only}. The command \code{read_sdc} stops with the error STA-0563 at this flag. OpenSTA also applies the standard precedence of SDC exceptions without exception: a false path or an asynchronous clock group between two clocks removes a maximum-delay constraint on the same path.

Replacement (How it shows):
> The flag gives an error, so this part is not silent. The second part is silent: the report gives the path as unconstrained, and no check fails. A single constraint file that declares the clock group and a crossing budget never applies the budget.

### 9. WRONG: macro power of zero is not a fault of OpenROAD
Where: `tm:defect:macro-power-omitted`, "Tool and defect"; summary table cell "Tool: OpenROAD".
Current: "The power report of the SoC flow gave zero watts for both hard macros."
Sources: `cr:run:phase5:power-figure-caveat-...-ew3`, Finding 1 and 2: the macro Liberty files had "no power tables at all, by construction"; `write_timing_model` "has zero power-related code"; "this is a characterization-flow gap, not an OpenROAD registration or corner-mapping bug"; "report_power is not misreading these files".
Replacement (Tool and defect):
> The flow wrote the Liberty views of the hard macros with the command \code{write_timing_model}. This command writes timing arcs only and no power tables. So the power report of the SoC flow gave zero watts for both hard macros, and it gave no warning. Every SoC power figure of the old runs is the power of the fabric only.

Table cell "Tool": "Macro view flow".

### 10. UNCLEAR: SRAM instance name rule stated for every flow
Where: `tm:defect:sram-macro-instance-name`, "Tool and defect".
Current: "The flow connects the supply pins of the SRAM macro through an instance-name pattern, \code{.*u_sram_macro.*}."
Sources: the pattern is in `pnr/sky130/soc/config.json` `PDN_MACRO_CONNECTIONS` only. Other configurations use other patterns: `pnr/asap7/cpu/config.json` `.*(u_tag_sram|u_data_sram)`, `pnr/sky130/cpu/config.json` the same, `pnr/asap7/gpu/config.json` `.*u_bank`, `pnr/asap7/soc/config*.json` `.*u_cpu.*` / `.*u_gpu.*`. `ds:ch:phase6-ip-expansion-plan:weight-sram-instantiation-3-way-all-macro`: "any other name silently leaves vccd1/vssd1 unconnected". `rtl/npu/npu_weight_mem.sv` and `rtl/soc/sram_controller.sv` name the instance `u_sram_macro`.
Replacement:
> The flow of the Sky130 SoC connects the supply pins of its SRAM macros through an instance-name pattern in \code{PDN_MACRO_CONNECTIONS}, \code{.*u_sram_macro.*}. An instance with another name does not match. The flows of the other blocks use other patterns. LibreLane gives no error for an SRAM macro that no pattern matches.

### 11. OVERSTATED: "ten hypotheses" and "unknown cause"
Where: `tm:status:asap7-reharden-host`, "What you may not conclude", bullets 1 and 2.
Current: "The record tested ten hypotheses in five single-variable experiments, and none of them did." / "The record shows a re-harden on sv2v that ended in a routing regression with an unknown cause."
Sources: `cr:run:asap7:pause-button-decision-...`: "After five single-variable experiments refuted every config-level hypothesis". Several exclusions were read-only analyses, not experiments (`cr:run:asap7:candidates-12-executed-read-only-...`). `cr:run:asap7:candidate-3-executed-...`: "The only unexcluded explanation is the SRAM hard-macro's own pin-access geometry", and a fix "most plausibly requires a hard-macro LEF/pin-layout change ... needs explicit human approval".
Replacements:
> \item A change of a configuration setting repairs the routing regression. The record says that five single-variable experiments refuted every hypothesis at the level of the configuration.
> \item The sv2v front end alone gives routed ASAP7 views. A re-harden on sv2v ended in a routing regression. The record did not prove the cause. The one explanation that it did not exclude is the pin-access geometry of the SRAM macro, and a change of that geometry needs the approval of the owner.

### 12. UNCLEAR: "pnr/asap7/soc/macro/ holds copies"
Where: `tm:status:synlig-macro-views`, "Statement", last two sentences.
Current: "The directory \src{pnr/asap7/soc/macro/} holds copies of these views. Git ignores the copies."
Sources: `pnr/asap7/soc/macro/.gitignore` ("Macro views are copies of cpu/macro/ and gpu/macro/ — excluded"; "generated by: cp ..."); `pnr/Makefile` copies them. A fresh clone has no copies there.
Replacement:
> The flow of the SoC copies these views into \src{pnr/asap7/soc/macro/}, and git ignores the copies. Some records name the copies as the views.

### 13. UNCLEAR: "figures rest on the views" for the block figures and for the GPU
Where: `tm:status:asap7-figures-rest-on-macro-views`, "Statement".
Current: "Every ASAP7 timing, power and area figure of the CPU, the GPU and the SoC rests on the views of \cref{...}. The record says that these figures rest on a netlist with a proven functional miscompile."
Sources: `cr:run:asap7:pause-button-decision-...`: "the ASAP7 CPU and GPU macro views remain the Synlig-built netlists that u99/ma7 proved mis-execute a branch, so every ASAP7 CPU/GPU/SoC PPA figure rests on a netlist with a proven functional miscompile". The CPU and GPU block figures come from the Synlig block netlists from which the views were made. The proof by simulation is for the CPU only (`cr:defect:asap7-cpu-synlig-ma7:verdict`); the GPU fault is shown on a cone (finding list header, deviation b).
Replacement:
> Every ASAP7 timing, power and area figure of the CPU, the GPU and the SoC rests on the Synlig netlists of \cref{tm:status:synlig-macro-views}. The figures of the SoC read the macro views. The figures of the CPU and GPU blocks come from the netlists from which the views were made. The record says that these figures rest on a netlist with a proven functional miscompile. For the GPU, the record shows the fault on a part of one module and not by simulation of the netlist.

### 14. TABLE: summary row for re-hardening states what the section does not
Where: caveat summary table, row "ASAP7 re-hardening", column "What it limits".
Current: "The repair of the first four ASAP7 caveats".
Sources: the part's own sections: `tm:status:asap7-zero-wire-timing` "does not end for the old runs"; `tm:status:asap7-drc-antenna-withdrawn` names no end run. Re-hardening cannot repair these two.
Replacement: "The replacement of the ASAP7 CPU and GPU macro views, and a route on the real power grid".

### 15. TABLE: other cells of the defect table
Where: defect summary table.
- Row "Zero-wire timing", Guard: replace by "Opt-in flow setting; annotation warning" (finding 6).
- Row "Macro power of zero", Tool: replace "OpenROAD" by "Macro view flow" (finding 9).
- Row "No \code{-datapath_only}", Guard: "Second check file" is right.
- Row "Flow that continues after a failure", Guard: add "(no DRC count)": "Gate \code{check_asap7_routing.py} (no DRC count)" (finding 7).
- Row "Open power connections", Tool "Flow": replace by "LibreLane (Sky130 SoC)" (finding 10).
- Column "Guide": see finding 16.
All other rows agree with their sections.

### 16. STYLE: section numbers and rule numbers of the project guide
Where: defect table column "Guide" ("Rule 1", "Section 7", "Section 6", "Rules 7, 9", ...); section texts "Hard rule 1 of the project guide", "Hard rule 2 ...", "Hard rule 3 ...", "Hard rule 8 ...", "Hard rules 7 and 9 ...".
Source: AGENTS.md section 10: "Never cite a file and line number, a page or a section number." A renumbering of AGENTS.md section 5 or of the sections would silently break these citations.
Replacements: name the rule by its title in AGENTS.md section 5.
- Column header "Guide" stays; cells: "No select on a struct member"; "Use the sv2v front end for macros" (for "Section 7" in the miscompile row); "Strict elaboration"; "Runtime-indexed mux"; "SRAM macro instance name"; "sv2v file lists; filelists from a generator"; "ASAP7 skips Magic, KLayout and Netgen" (no-physical-verification row); "Do not gate a decision on diff" (rtk row).
- Section texts: "The rule of the project guide on selects of a struct member." / "The rule of the project guide on strict elaboration." / "The rule of the project guide on runtime-indexed muxes." / "The rule of the project guide on the name of the SRAM macro instance." / "The rules of the project guide on sv2v file lists and on generated file lists."

### 17. MISSING: the file-list checks do not cover most modules
Where: `tm:defect:sv2v-blackbox`, "Guard".
Current: "The script \src{tools/verif/check_periph_filelists.py} checks that each peripheral and NPU module is in all five lists."
Sources: `check_periph_filelists.py` docstring: "Every .sv file under rtl/periph/ and rtl/npu/ that declares a module must be referenced by all five lists". It does not look at `rtl/cpu`, `rtl/gpu`, `rtl/soc`. The recorded case of missing modules was the five CDC modules and `rv32i_clock_gate.sv` missing from `SOC_SV_FILES` (`cr:status:phase5-workflow`: "sv2v has no Verilator-style -I auto-discovery, so a missing module there is silently blackboxed"). CI: `.github/workflows/cocotb.yml` runs `check_periph_filelists.py`; `qa-checks.yml` runs `gen_filelist.py --check`; no workflow runs `check_source_closure.py` as a step (it appears there in a comment only).
Replacement (add after the `check_periph_filelists.py` sentence):
> It checks only the modules in \src{rtl/periph/} and \src{rtl/npu/}. No script checks that a module of the CPU, the GPU or the SoC is in the sv2v file lists. The recorded case of missing modules was a set of CDC modules of the SoC.

Also change "One recorded case instantiated the module of the wrong technology and made a blackbox of it." to "One recorded case left out a define, so the netlist instantiated the SRAM module of the wrong technology and made a blackbox of it. A second recorded case left the CDC modules out of the file list of the SoC."

### 18. UNCLEAR: "the equivalence check of each module does not find the defect"
Where: `tm:defect:synlig-struct-member-select`, "How it shows".
Current: "Lint, LVS and the equivalence check of each module do not find the defect."
Sources: `cr:defect:sky130-cpu-synlig-dud4:why-nothing-caught-it`: per-module Synlig-vs-sv2v SAT equivalence "cannot see it because the broken wires are the instance's port connection". `cr:defect:synlig-struct-select-ainf:step-4-...` found D3 with a Synlig-vs-sv2v miter on a cone and recommends "a per-module Synlig-vs-sv2v miter (modeq.sh) in the PD flow" as "a stronger check". So a per-module equivalence check finds the defect when the select is inside the module.
Replacement:
> Lint and LVS do not find the defect. An equivalence check of each module against sv2v finds a select inside the module. It does not find a select in a port connection, because the broken wires are outside each module. sv2v is not affected.

### 19. UNCLEAR: hidden runtime mux is a fault of the proof, not of Yosys
Where: `tm:defect:yosys-hides-runtime-mux`, "Tool and defect" and "How it shows".
Current: "A full \code{synth} in Yosys runs \code{techmap}. ... A constant-label \code{case} is also not enough, because Yosys turns each \code{case} into a \texttt{\$pmux}."
Sources: `cr:status:phase5-workflow`: the earlier proof "was vacuous"; "yosys proc lowers every case, including constant-label ones" into `$pmux`; "None of this is new runtime indexing". AGENTS.md rule 3: "A full synth hides them."
Replacement (Tool and defect, add as first sentence): "This is the intended behaviour of Yosys. The defect was in a proof that counted on the wrong netlist."
Replacement (How it shows, second sentence):
> On the coarse-grain netlist the count of \texttt{\$pmux} is not zero even for a design with no runtime index, because Yosys turns each \code{case} into a \texttt{\$pmux}, also a \code{case} with constant labels. The reviewer decides which cells come from a runtime index.

### 20. UNCLEAR: rtk version text attributed to the wrong file and stated as present
Where: `tm:defect:rtk-diff`, "Tool and defect" and "Guard".
Current: "The project guide says that the machine of the project runs version 0.48.0 and that both defects are verified gone there." / "These were correct in every version."
Sources: CLAUDE.md section "rtk diff must not decide pass/fail below rtk 0.48.0" (CLAUDE.md is the Claude Code guide, not the project guide AGENTS.md): "This machine was upgraded to rtk 0.48.0 on 2026-09-07 and both defects are verified gone here"; "cmp -s (exit 0/1) and sha256sum were correct throughout both the broken and fixed versions"; identical files still return exit 0.
Replacements:
> The section of \src{CLAUDE.md} on \code{rtk diff} says that the project machine was upgraded to version 0.48.0 and that both defects are verified gone there. Another clone or machine on an older version is affected. Check the version with \code{rtk --version}.

> ... Use \code{cmp -s} or \code{sha256sum}. These were correct in version 0.42.0 and in version 0.48.0.

Also in "How it shows", first sentence: "Below version 0.48.0, a test such as \code{if diff a b} always takes the branch for identical files, and the screen looks right."

### 21. MISSING: Sky130 is not full physical verification either
Where: `tm:defect:asap7-no-physical-verification`, "Work-around".
Current: "Do not state a DRC or an LVS result for ASAP7. For real physical verification, use a Sky130 run."
Sources: TM `tm:ch:sky130-flow` result table of the batched Sky130 SoC harden: "KLayout DRC ... not run --- deliberately skipped", "Magic DRC 9,081 --- unchanged, bead 45a waiver"; `pnr/Makefile` target `librelane-sky130-soc-noklayout`: "KLayout DRC is DEFERRED, not waived." `tm:pd:node-strategy:sky130-real-drclvs-...`: CPU Magic DRC 27.7 M "waived PDK artifact --- 100 % ... inside SRAM macro footprints".
Replacement:
> Do not state a DRC or an LVS result for ASAP7. For real physical verification, use a Sky130 run, and state its limits: the Magic DRC count of the Sky130 runs has a waiver for the violations inside the SRAM footprints, and the batched harden of the Sky130 SoC did not run KLayout DRC.

Also: the switches are four, not three. Replace "The configurations set the switches of the three checks to false." by "The configurations set \code{RUN_MAGIC_DRC}, \code{RUN_KLAYOUT_DRC}, \code{RUN_KLAYOUT_XOR} and \code{RUN_LVS} to false." (checked in `pnr/asap7/{cpu,gpu,soc}/config.json`, `soc/config_multiclock_hier.json`).

### 22. UNCLEAR: the definition of a tool defect does not fit the entries, and the precedence sentence
Where: `tm:ch:tool-defects-and-caveats:use`, paragraph 1 and last paragraph.
Current: "A tool defect is a fault of a tool. The fault gives a wrong result, or no result, and the tool shows no error." / "When this part and a run history differ in wording, this part states the present limit."
Sources: several entries are not faults of a tool, or are not silent: flow patches of the project (`tm:defect:flow-swallows-failure`), a project naming pattern (finding 10), intended Yosys behaviour (finding 19), a flow gap (finding 9), a deliberate flow limit (finding 21 / 30), a loud OpenSTA error (finding 8). AGENTS.md section 11: "When a document and the RTL disagree, report it. Do not decide alone which one is correct."
Replacements:
> A tool defect is a behaviour of a tool, or of the flow around it, that gives a wrong result or no result without a clear error. Some entries are not faults of the tool itself. Each section says which part is silent.

> The Changes record holds the dated history of each entry. The record says what happened. This part says what the reader may quote today. This part does not change a record. If this part and a record disagree, report it to the owner.

### 23. STYLE/OVERSTATED: small corrections in the miscompile section
Where: `tm:defect:synlig-cpu-miscompile`.
Current: "The smaller netlist even helps timing." and "The configurations of several leaf blocks, of FreePDK45 and of the legacy flow still set it to true."
Sources: `cr:defect:sky130-cpu-synlig-dud4:why-nothing-caught-it`: "STA and P&R are happy with a smaller, wrong design (Synlig netlist is 333-957 cells smaller)". `pnr/asap7/template/config.json` has `"USE_SYNLIG": true`.
Replacements: "Timing analysis and place and route accept the smaller, wrong netlist." / "The configurations of several ASAP7 leaf blocks, of the ASAP7 template, of FreePDK45 and of the legacy flow still set it to true."

### 24. UNCLEAR: "Most drivers had no parasitics"
Where: `tm:status:asap7-zero-wire-timing`, "Statement", sentence 4.
Current: "Most drivers had no parasitics."
Source: `cr:run:phase5` opening notes: "Proven on an isolated CPU-block run of this same design family: 94.44% of drivers unannotated".
Replacement: "In a test run on a CPU block of the same design family, most drivers had no parasitics and the report showed no violation."

### 25. UNCLEAR: "a gated result at the other corners"
Where: `tm:status:sky130-single-sram-corner`, "What you may still say", bullet 3.
Current: "A result is a typical-corner result for the paths through the SRAM, and a gated result at the other corners. State both facts and do not mix them."
Source: `cr:pd:sky130-soc-sdc`: "SCOPE OF THIS SIGN-OFF: still a TYPICAL-CORNER (nom_tt) TIMING SIGN-OFF ... It is NOT a validated multi-corner timing sign-off".
Replacement:
> \item A Sky130 timing result is a typical-corner result. The flow checked all nine corner labels, but the paths through the SRAM have the same timing at each label. Say both facts.

### 26. MISSING: tool defects with evidence that the part does not list or drop
Where: `tm:ch:tool-defects:dropped` and chapter `tm:ch:tool-defects`.
Sources and candidates:
- Xezim 0.11.4 silent miscompile of `~f(x) || y` and `~f(x) && y` (`tm:dec:xezim:4-silent-miscompile-measured-reproduced-twice-independently`): "This RTL hits it: ... sram_controller.sv"; "a similar miscompile that hides a fault instead of raising one would pass silently". This is a real, silent tool defect with a measurement. Add it as a defect section, or name it in the dropped section with a reason.
- The CDC gate is informational by default (`tm:ch:mod-cdc-primitives`, verification text: "The variable CDC_STRICT has the default 0, and then the run is informational: the gate can fail and the target still returns 0"). A check that can fail silently; it is the guard of the CDC rule.
- OpenSTA 2.7.0 in the LibreLane 3.0.14 shell "corrupts report_power to inf/NaN on this design" (`cr:run:phase5:power-figure-caveat-...-ew3`). The part mentions it inside `tm:defect:macro-power-omitted`; acceptable.
- LibreLane 2.4.13 unbounded `repair_timing` oscillation (`cr:run:asap7:addendum-2026-09-19-...`); loud (no convergence), so a drop is justified. Name it in the dropped section.
- Surelog shared parse cache: the drop reason "The sources do not give a work-around" is weak. `cr:defect:sky130-cpu-synlig-dud4:consequences` says the shared cache comes from running LibreLane "with cwd = the librelane checkout", and that the clean-cwd run gave a byte-identical netlist. It also says the hazard "cannot be excluded for the committed netlist" (the old Sky130 CPU netlist, since replaced). Keep the drop, but give the true reason.
Replacement for the second paragraph of the dropped section:
> The Synlig front end keeps a shared parser cache when LibreLane runs from its own checkout. The cache can mix the source paths of two work trees. The record found no stale content in the one case that it checked, and it calls the cache a latent hazard. The sv2v front end does not use this cache, so the hazard is outside the present flow of the macros. It is not in this chapter.
>
> The unbounded timing repair of LibreLane 2.4.13 is not in this chapter, because the step does not end and the fault is not silent.

Proposed new defect section (if the author agrees to add it), label `tm:defect:xezim-negated-call`:
> \section{Xezim: a negated function call in a logical operation}
> Tool and defect: Xezim 0.11.4 gives a wrong value for \code{~f(x) || y} and \code{~f(x) && y}. Verilator gives the correct value.
> How it shows: no error. On this RTL a legal SRAM write returns SLVERR in Xezim.
> Guard: none. Xezim is not the only evidence for a result.
> Work-around: do not use a Xezim result as the only evidence.
> Evidence: \cref{tm:dec:xezim:4-silent-miscompile-measured-reproduced-twice-independently}.

### 27. LABEL: the kind `status`
Where: all ten `tm:status:*` labels.
Sources: `tools/docs/check_doc_labels.py` `KINDS = "part ch mod pd suite dec defect run fix status guide flow mm inv app req arc"`. Existing `cr:status:*` labels are dated project-status history (`cr:status:phase-status`, `cr:status:roadmap`, `cr:status:phase5-workflow`, `cr:status:claude-md-overview`, ...). No slug collides, but the kind would mean "project status" in CR and "limit on a result" in TM. A caveat that ends would keep a label that says "status".
Recommendation: add the kind `caveat` to `KINDS` (one word, a one-line change of the checker), then name the ten sections `tm:caveat:<same slug>`. Do it before the merge, because labels do not change after it. Also move `tm:defect:asap7-no-physical-verification` to `tm:caveat:asap7-no-physical-verification` and into the caveat chapter (see finding 30).

### 28. MISSED-CLAIM: chapters without a note that hold unqualified claims (DS, TM, UM)
See the list "Missed claims" below. The serious ones: `tm:pd:power-domain-evaluation:1-findings` ("M11 signed off single-domain (62.9 mW, all logic powered)"), the ticked boxes of `tm:pd:openroad-flow:gate-2-place-route` / `gate-3-timing-closure`, the DFT architecture chapter (`tm:ch:dft-architecture`) with Sky130 results "at all 9 corners", and the FPGA chapter (`tm:ch:fpga-prototyping`) that derives scale factors from ASAP7 frequencies that do not stand.

### 29. UNCLEAR: two existing notes
- `tm:pd:node-strategy` note, last sentence: "The reasons are in \cref{tm:status:asap7-zero-wire-timing,tm:status:asap7-drc-antenna-withdrawn}." The note itself gives three reasons and names the wrong views first. Replacement: "The reasons are in \cref{tm:status:asap7-figures-rest-on-macro-views,tm:status:asap7-zero-wire-timing,tm:status:asap7-drc-antenna-withdrawn}." Also replace "The ASAP7 macro views are functionally wrong" by "The ASAP7 netlists that Synlig built are functionally wrong", because the Run 43 figures are of the CPU block netlist and not of the macro views (finding 13).
- `ds:ch:gpu-lite-simt-engine` note: "It reports an ASAP7 sign-off, a timing-closed top and a gate of 0 DRC and 0 antenna." In this chapter "0 DRC, 0 antenna" appears only in planned gates (`ds:ch:phase3-closure-phase4-plan:74-sign-off-gates`, and the plan list "→ WNS ≥ 0, hold ≥ 0, 0 DRC, 0 antenna"). The claims are the sign-offs at 1418 MHz and 571 MHz. Replacement: "Some text of this chapter comes from plans of a past date. It reports ASAP7 sign-offs of the CPU at 1418~MHz and of the GPU at 571~MHz, and a timing-closed top. These claims do not stand. Read \cref{tm:ch:standing-caveats} before you quote an ASAP7 figure from this chapter."

### 30. LABEL/UNCLEAR: "No physical verification" is a caveat, not a tool defect
Where: `tm:defect:asap7-no-physical-verification`.
Source: the section itself: "Guard: There is none. The limit is in the flow." The configurations switch the checks off on purpose (finding 21). AGENTS.md section 7 states it as practice. It fits the part's definition of a standing caveat ("a limit on what a result shows").
Recommendation: move it to the caveat chapter with label `tm:caveat:asap7-no-physical-verification` (or `tm:status:...` if the kind stays), use the five caveat parts, and remove its row from the defect table.

### 31. UNNECESSARY-NOTE (low): coding guidelines note
Where: `um:ch:coding-guidelines` note.
Source: the text it sits beside (`um:guide:coding-guidelines`) uses "signed-off RTL" and "ASAP7 sign-off" only as process words about whether a rename invalidates a run. It quotes no ASAP7 figure. The note is harmless and correct. Keep it or drop it; no change of meaning.

### 32. UNCLEAR: dictionary term "front end"
Where: `dictionary.yaml`, term `front end`.
Current: "The part of a synthesis tool that reads the source and builds the first internal form of the design."
Source: the part calls sv2v "the sv2v front end"; sv2v is a separate converter, not part of a synthesis tool (`pnr/Makefile` runs it as its own target `*-sv2v`; `pnr/sky130/cpu/config.json` reads its output file).
Replacement: "The tool, or the part of a tool, that reads the SystemVerilog source for synthesis and gives the first form of the design. In this project the front end is Synlig or sv2v."
The terms "standing caveat", "blackbox" and "macro view" are correct. Optional for "blackbox": "A module that a tool keeps as an empty box with ports only, because it has no description of the module or because the flow tells it to." (the SRAM stubs are blackboxes on purpose, `cr:defect:sky130-cpu-synlig-dud4:re-harden-on-sv2v-...`: "only the SRAM stub is a blackbox").

---

## Verdict table

| # | Section | Verdict | Findings |
|---|---------|---------|----------|
| C1 | `tm:status:synlig-macro-views` | Right in substance; one wording fix | 12 |
| C2 | `tm:status:asap7-figures-rest-on-macro-views` | Right; make the GPU and block scope precise | 13 |
| C3 | `tm:status:asap7-zero-wire-timing` | Right; dated "current RTL", test-run scope | 5, 24 |
| C4 | `tm:status:asap7-drc-antenna-withdrawn` | Overclaim in "may still say" | 3 |
| C5 | `tm:status:asap7-empty-power-grid` | Overclaim in "may still say"; end condition incomplete | 2 |
| C6 | `tm:status:asap7-soc-setup-wns` | Figures right; "current RTL" wrong; routing caveat missing | 4, 5 |
| C7 | `tm:status:sky130-single-sram-corner` | Overclaim (CPU macro corner-accurate); one unclear bullet | 1, 25 |
| C8 | `tm:status:commercial-flows-indicative` | Correct | — |
| C9 | `tm:status:sky130-cpu-macro-sv2v` | Correct | — |
| C10 | `tm:status:asap7-reharden-host` | Overstated counts and cause | 11, 14 |
| D1 | `tm:defect:synlig-struct-member-select` | Correct except one sentence | 18, 16 |
| D2 | `tm:defect:synlig-cpu-miscompile` | Correct; small fixes | 23, 16 |
| D3 | `tm:defect:synlig-undef-warning` | Correct (gate in all 19 `python3 -m librelane` calls of `pnr/Makefile`; CI job `synth-undef-gate.yml`) | — |
| D4 | `tm:defect:sv2v-blackbox` | Guard overstated by omission | 17, 16 |
| D5 | `tm:defect:use-before-declare` | Correct (matches the docstring of `check_elab_strict.py`; CI `qa-checks.yml`) | 16 |
| D6 | `tm:defect:yosys-hides-runtime-mux` | Method right (AGENTS rule 3); framing unclear | 19, 16 |
| D7 | `tm:defect:sram-macro-instance-name` | Scope too wide | 10, 16 |
| D8 | `tm:defect:asap7-no-physical-verification` | Not a defect; work-around overclaims Sky130 | 21, 30 |
| D9 | `tm:defect:flow-swallows-failure` | Guard overstated (no DRC count, no CI) | 7 |
| D10 | `tm:defect:sta-without-in-session-route` | Guard overstated (opt-in, default off, warning only) | 6 |
| D11 | `tm:defect:macro-power-omitted` | Cause stated wrongly | 9 |
| D12 | `tm:defect:opensta-datapath-only` | Silence stated wrongly; consistent with CDC chapter otherwise | 8 |
| D13 | `tm:defect:rtk-diff` | Version conditions right; attribution and tense wrong | 20 |
| D14 | `tm:defect:empty-report-passes` | Correct (matches `tools/eda/README.md` exit codes and the `dwp` text) | — |
| Dropped | `tm:ch:tool-defects:dropped` | Design-rule drop justified; Surelog reason weak; Xezim and CDC_STRICT missing | 26 |
| Tables | both summary tables | Re-hardening row and four defect cells disagree with sections | 14, 15 |

## Missed claims (DS, TM, UM; not CR, not archive)

| Place (label / chapter) | Text | Note needed |
|---|---|---|
| `tm:ch:flow-overview`, section `tm:pd:power-domain-evaluation:1-findings` | "M11 signed off single-domain (62.9 mW, all logic powered)" | ASAP7 SoC sign-off of run 14 does not stand; 62.9 mW is fabric-only. Note at the chapter: "Some text of this chapter comes from plans and runs of a past date. It reports an ASAP7 SoC sign-off and quality gates marked as passed. These claims do not stand. Read \cref{tm:ch:standing-caveats} before you quote an ASAP7 figure from this chapter." |
| `tm:ch:flow-overview`, `tm:pd:openroad-flow:gate-2-place-route`, `gate-3-timing-closure` | Ticked boxes: "Routing converges (zero DRC violations)", "WNS = 0", "All corners passing (fast/slow/typical)" | Same note (covers both rows). |
| `tm:ch:pd-makefile-notes` | "config_multiclock.json (run 23's sign-off basis)"; "the accepted M11 SoC sign-off (run 14) and both GPU 571 MHz sign-off runs" | Note: "The comment text of this chapter comes from dated runs. It names ASAP7 runs as sign-offs. These sign-offs do not stand. Read \cref{tm:ch:standing-caveats}." |
| `tm:ch:mod-memory-and-caches` (module reference) | "on ASAP7 csb0 feeds the SRAM clock gate (extra enabled cycles = extra dynamic power on a flow signed off as-is)" | One-sentence note, or accept as low risk (no figure). |
| `tm:ch:dft-architecture` (DFT part) | Sky130 results "all 9 corners", "All nine corners PASS", "positive at all nine corners [M]" | Note pointing to \cref{tm:status:sky130-single-sram-corner}, same text as the Sky130 flow note. |
| `tm:ch:fpga-prototyping` | "ASIC target 1282 MHz", "Prototype scale factor (ASIC 571 MHz fabric / 1282 MHz CPU)" | Note: "The ASIC frequencies in this chapter are ASAP7 figures that do not stand. The scale factors use them. Read \cref{tm:ch:standing-caveats}." |
| `tm:ch:sky130-flow` | "All three ASAP7 sign-offs (CPU/GPU/SoC) skip physical verification." | Add one sentence to the existing note: "The chapter also calls the ASAP7 runs sign-offs. These sign-offs do not stand (\cref{tm:ch:standing-caveats})." |
| `ds:ch:mod-peripherals`, `tm:ch:mod-peripherals`, `tm:ch:test-benches-and-suites` | "571 MHz ASAP7, 1282 MHz CPU domain" used as clock rates and clock ratios | No note needed: design targets, not results. |
| `ds:ch:cpu-phases-0-to-3`, `ds:ch:timing-constraints`, `tm:ch:constraint-files`, `ds:ch:verification-strategy` lines with "all corners" | criteria and checklists, not results | No note needed. |
| `ds:ch:mixed-signal-pll` | Sky130 charge-pump "real DRC + LVS signed off"; ASAP7 "indicative" | No note needed: these stand and the text qualifies ASAP7. |
| `tm:ch:commercial-flow-comparison` | "signoff" labels in tables | No note needed: the chapter states "indicative, not sign-off". |

Notes that discredit a claim that stands: none found. Each note is scoped to ASAP7 or to the Sky130 corner wording, and the Sky130 DRC/LVS results are not discredited.

## Observations for the owner (AGENTS.md section 2 and source files)

1. "The committed `pnr/asap7/soc/macro/` views still use them." The committed views are `pnr/asap7/cpu/macro/` and `pnr/asap7/gpu/macro/`; `soc/macro/` holds a `.gitignore` and receives copies (`pnr/asap7/soc/macro/.gitignore`, `cr:run:phase5:power-figure-caveat-...-ew3` Finding 1: "pnr/asap7/soc/macro/* are gitignored copies"). Records `cr:defect:asap7-cpu-synlig-ma7:consequences` and `cr:run:asap7:addendum-...` name the copies.
2. "Every ASAP7 CPU, GPU and SoC ... figure rests on those views." Precisely: the block figures rest on the Synlig block netlists; the SoC figures read the views. The GPU miscompile is shown on a cone, not by netlist simulation (`cr:defect:synlig-struct-select-ainf:step-4-...`).
3. "Detailed routing committed no wires." Resolved for new runs on the CPU block (`...-xy6`, LibreLane 3.0.14 OpenROAD pin plus a per-instance shift); the record still applies the caveat to the -727.37 ps SoC point (`cr:run:phase5` 2026-09-18 update).
4. "The ASAP7 power grid was empty in every run." A fixed grid exists and is selected only by `pnr/asap7/{cpu,gpu}/config_3014.json`. The SoC configurations still select `pnr/asap7/soc/pdn.tcl`, "which carries the same M1->M5 defect" (`pnr/asap7/soc/pdn_orfs.tcl`).
5. "The current ASAP7 SoC point" and the table row "Timing is not closed at 1750 ps on the current RTL": the point is `RUN_2026-09-17_20-41-11`; Phase 6 RTL and DFT work landed after it (`cr:status:phase-status:current-phase`). It is the latest measurement, not a measurement of the current RTL.
6. "Sky130 timing uses one SRAM corner model (nom_tt only)." The SoC record says the SoC SRAM is "the SOLE source" (`cr:pd:sky130-soc-sdc`), but the Sky130 CPU block flow also reads a TT-only Liberty for the ten 1 KB SRAMs inside the CPU macro (`pnr/sky130/cpu/config.json` `EXTRA_LIBS`). INFERRED: the per-corner CPU macro views carry TT SRAM arcs.
7. "ASAP7 CPU and GPU re-hardening needs a host with 32 GB RAM or more." The CPU sv2v re-harden ran to the end of detailed routing on the 15.9 GB host and failed on a routing regression whose only unexcluded cause is SRAM pin-access geometry (`cr:run:asap7:candidate-3-...`). The 32 GB gate is the owner decision of `cr:run:asap7:pause-button-decision-...`, driven by the route with the real grid (`...-4l8`). For the GPU, `pnr/asap7/gpu/config.json` gives "~13.5h+ GRT and 14+ GiB peak RSS".
8. The zero-wire STA fix is opt-in with default false and is set only in two SoC configurations (`pnr/librelane_patches/librelane2413_postgrt_annotation_fix.diff`). A new CPU or GPU run repeats the defect unless the setting is added. The patch edits the shared LibreLane tree, which AGENTS.md section 7 says not to edit; the record says the fix was "applied to the shared LibreLane tree" (`cr:run:phase5`).
9. Not in AGENTS.md section 2 but standing in the records: macro power of zero in old SoC figures (`...-ew3`); the batched Sky130 SoC harden did not run KLayout DRC ("DEFERRED, not waived", `pnr/Makefile`); Sky130 Magic DRC counts carry an SRAM-footprint waiver.
10. AGENTS.md rule 7 names `tools/verif/check_source_closure.py` as a check; no workflow in `.github/` runs it as a step. `check_periph_filelists.py` covers only `rtl/periph` and `rtl/npu`.
11. Out-of-date text in source files:
    - `pnr/asap7/cpu/config.json` `// USE_SYNLIG_NOTE`: "OPT_MUXTREE mis-elaborates the runtime-indexed regfile read mux". Refuted by `cr:defect:asap7-cpu-synlig-ma7:verdict` ("the ma7 regfile read-mux / OPT_MUXTREE hypothesis is not supported"; cause = hazard-unit port part-selects).
    - `pnr/asap7/gpu/config.json` `// USE_SYNLIG_NOTE`: "The CPU macro has been re-hardened with USE_SYNLIG:false + sv2v" (false: `cr:run:asap7:addendum-...` "No macro views were regenerated"); names the GPU risk as the OPT_MUXTREE class (the measured GPU fault is D3); calls `pnr/asap7/soc/macro/gpu_top.*` "the tracked SoC macro views" (they are gitignored).
    - `cr:run:asap7:addendum-...` says u99/ma7 proved a miscompile of "this macro's regfile read ports"; the later verdict corrects it. CR text is a record and stays, but the TM should not repeat it (it does not).

## What I did not check

- I did not run `build_books.py`, `check_doc_labels.py`, `check_comment_budget.py`, `check_requirements.py`, `gen_glossary.py --check`, `prose_preserve.py`, `ste_check.py` or any simulator. I did not prove that `labels.tsv` and `glossary.tex` were produced by their generators (the diff of `glossary.tex` matches the four dictionary entries; `labels.tsv` changes 941/909 lines, consistent with a regeneration after inserted lines).
- I did not read the shared LibreLane install, so I did not confirm that the `catch {}` patch in `drt.tcl`, the `pdn.tcl` warn-and-continue patch or the `STA_POSTGRT_INSESSION_GRT` patch are still applied there.
- I did not read every CR record behind `cr:status:claude-md-overview` and `tm:pd:librelane-patching:the-cautionary-case-drttcl`; I checked that the labels exist and that the claims they support match other records.
- I did not check `tm:pd:sky130-real-drc-lvs:1-findings` text for the FreePDK45 Magic/Netgen statement beyond `tm:pd:node-strategy` ("FreePDK45 has them permanently blocked"); `pnr/freepdk45/config.json` sets `RUN_KLAYOUT_DRC: true`, `RUN_MAGIC_DRC: false`, `RUN_LVS: false`, which agrees.
- I did not check whether `tb/tests/test_gen_filelist.py` exercises `check_source_closure.py` on all lists in CI.
- I did not check that each `\cref` renders with the right name in the PDF.
- The missed-claim scan used a regular expression over DS/TM/UM `.tex` files per chapter; claims worded in another way can remain.
