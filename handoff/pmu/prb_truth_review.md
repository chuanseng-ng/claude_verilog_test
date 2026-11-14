# Truth review: power intent chapters (DS `ds:ch:power-intent`, TM `tm:pd:phase5-soc-upf`, UM `um:ch:power-integration:upf`, dictionary)

Scope: working tree of `docs/power-intent-chapter` (uncommitted). I read in full: `pnr/constraints/phase5_soc.upf`,
`tools/verif/check_upf.py`, `tb/tests/test_check_upf.py`, the facts file `pnr/constraints/phase5_soc_rtl_facts.json`
(summarised by script), the `check_upf` part of `tools/docs/check_pinned_text.py` and its test
`tb/tests/test_docs_check_pinned_text.py::test_upf_directive_lines_must_parse`, `.github/workflows/qa-checks.yml`,
`tests.yml`, the `docs.yml` run steps, `rtl/soc/dft/dft_ctrl.sv`, `rtl/soc/dft/dft_ctrl_ports.sv`, the PMU, clamp,
synchroniser and clock-gate parts of `rtl/soc/soc_top.sv`, the mode/target/output parts of `rtl/soc/pmu.sv`, the
`check_comment_budget.py` rules for `.upf`, `check_doc_labels.py::check_path_map`, the four chapter texts, the DS PMU
chapter, the dictionary diff, the path_map diff and the archive sections `cr:arc:ds-upf-power-spec` (intro, Checking,
Tool compatibility) and `cr:arc:tm-phase5-soc-upf` (intro). Grep over the repository for `UPF_FILE`, `.upf`,
`read_upf`, `phase5_soc.upf` and `ds:ch:upf-power-spec`.

Runs (all read-only on the repository):
- `PYTHONUTF8=1 python tools/verif/check_upf.py -v` -> PASS, exit 0; log: 4 ports, 4 nets, 3 sets; 4 domains, gated
  PD_CPU, PD_GPU; roster 34; per arm 14 isolated == 14 clamped, 40 classified; states NORMAL, CPU_OFF, GPU_OFF, IDLE, SCAN.
- 35 mutation experiments on scratch copies, script and results in
  `<scratchpad>\pmu\prb\review\exp.py`
  and `...\review\exp_results.txt`, each run as `python tools/verif/check_upf.py --upf <copy>`. Experiment ids (E01 ...)
  are cited below. E04b is the corrected location trial (`E04` hit the comment on UPF line 150, which also contains
  `-location parent`; see observation O10).

Recounts from the files (all agree with the chapters):
- `# upf-check aon` lines: 34 (UPF lines 21-27: 7, 29-30: 2, 32-35: 4, 37-40: 4, 42-47: 6, 49-59: 11). Facts: 37 top-level
  instances in each arm, minus `u_cpu`, `u_gpu`, `u_sram` = 34, same names. TM roster table: 34 names, same groups.
- Clamps: 14 in each arm of the facts (6 on `pmu_cpu_iso_en_sync`, 8 on `pmu_gpu_iso_en`, all clamp 0, sense high);
  `soc_top.sv` lines 822-827 and 1042-1050 are `assign <net> = <iso> ? 1'b0 : <raw>;`. TM clamp table: 14 rows, correct
  element-to-net mapping.
- Outputs: `u_cpu` 33, `u_gpu` 21 = 54; 54 - 14 = 40 classified (payload 16, slave_response 11, observability 13). TM
  class table lists the same 40.
- Arms: `ARMS` = asap7 {SRAM_ASAP7, USE_ICG_CELL, __pnr__}, sky130 {SRAM_SKY130, __pnr__}; `pnr/Makefile`
  `SKY130_SOC_SV2V_DEFINES` adds `USE_SKY130_CLKCELLS` (used only in `rv32i_clock_gate.sv` and `dft_clk_mux.sv`).
- DS requirement count: 30 (001-007, 020-028, 040-045, 060-062, 080-084). All `\cref`/`\reqref` targets I checked exist
  in `labels.tsv`.
- What the UPF lacks: no `create_power_switch`, no retention, no level shifter, no `map_isolation_cell` (true).
  No Makefile, script, flow config or workflow uses `UPF_FILE` or names `phase5_soc.upf` except the checker, the
  pinned-text check and the workflow comments (true).

Counts by category: WRONG 7, WEAK-VERIFY 4, MISSING 11, UNCLEAR 8, INCONSISTENT 3, STYLE 3, FIGURE 0, LABEL 1 (37 findings). Both TikZ figures were checked against the UPF and `soc_top.sv` and are correct.

---

## Findings (most harmful first)

### 1. WRONG: DS-PWR-044 and the TM SCAN table say `dft_ctrl_ports` drives the test enable of the clock gates
- **Where:** DS `power-intent.tex`, DS-PWR-044 body and its Information; TM `power.tex`, table `tab:tm:pd:phase5-soc-upf:scan`, row "Clock gates".
- **Current (DS):** "In the state `SCAN`, each top-level clock gate of `soc_top` must have the test-enable net of `dft_ctrl` as its test enable, and `dft_ctrl_ports` must drive that net from `scan_mode_i`."
- **Current (TM row):** "`dft_ctrl_ports` drives `test_en_o` from `scan_mode_i`. Each top-level clock gate takes this net as its test enable, so the gate is open."
- **What the files show:** `soc_top.sv` line 210 connects `u_dft_ctrl.test_en_o` to `dft_test_en`; gates `u_cpu_cg`/`u_gpu_cg` (lines 1878-1879) take `.test_en(dft_test_en)`. `dft_ctrl.sv` line 55-63 instantiates `dft_ctrl_ports u_pins` with `.test_en_o (pin_test_en)`, and line 142 is `assign test_en_o = pin_test_en | tap_scan;` (`tap_scan` = `u_tap.scan_mode_o`). `dft_ctrl_ports.sv` line 28 `assign test_en_o = scan_mode_i;` drives only `pin_test_en`. So `dft_ctrl_ports` does not drive the net of the gates, and the net is also high when the JTAG TAP selects scan with `scan_mode_i` low. The checker (`_check_scan_claim`) reads only the text of `dft_ctrl_ports.sv` (regex `assign\s+test_en_o\s*=\s*scan_mode_i\b`) and the facts `clock_gates`/`test_en_net` (`dft_test_en`). It does not read `dft_ctrl.sv`. The test `test_scan_state_claim_is_checked_against_rtl` breaks only the gate connection in the facts, not the text regex.
- **Proposed DS-PWR-044 body:** "In the state `SCAN`, the test enable of each top-level clock gate of `soc_top` must be the net `dft_test_en`, which is the output `test_en_o` of `u_dft_ctrl`."
- **Proposed DS-PWR-044 Information (replace the first two sentences, keep the rest):** "The checker reads the test enable of each gate from the facts file. It also requires the assignment `assign test_en_o = scan_mode_i` in the text of `rtl/soc/dft/dft_ctrl_ports.sv`. It does not read `rtl/soc/dft/dft_ctrl.sv`. In `dft_ctrl`, `test_en_o` is the OR of the test enable of `dft_ctrl_ports` and the scan mode of the JTAG TAP. So `scan_mode_i` high opens the gates. The TAP can also open them while `scan_mode_i` is low, and the state `SCAN` does not describe that case. The test of the checker changes the gate connection in the facts. No test changes the assignment in `dft_ctrl_ports.sv`."
- **Proposed TM row "Clock gates", middle cell:** "`dft_ctrl` drives `dft_test_en` from the OR of `scan_mode_i` (through `dft_ctrl_ports`) and the scan mode of the JTAG TAP. Each top-level clock gate takes `dft_test_en` as its test enable, so the gate is open." Last cell unchanged ("Yes, checked").
- **Proposed TM, add after the table (before "A clamp can be active during a scan."):** "The JTAG TAP can set the scan mode of the SoC while `scan_mode_i` is low. Then `dft_test_en` is high and the clock gates are open, but the file describes this condition as a functional state, because each functional state requires only `scan_mode_i == 1'b0`. The checker does not read the TAP path."
- See also finding 17 (duplicate of DS-PMU-108) and observation O1.

### 2. WRONG / MISSING: a change of a top-level instance needs a regenerated facts file before the checker sees it
- **Where:** DS DS-PWR-003 Information; DS `ds:ch:power-intent:dec-follow` "Consequence for the user"; DS `dec-facts` "Consequence for the user"; UM `um:ch:power-integration:upf` paragraphs "A top-level instance changes" and "Regenerate the facts".
- **Current (DS-PWR-003 info):** "A new top-level instance in `soc_top` fails the check until its name is in the roster. The same holds when an instance leaves `soc_top`. The change forces a review of the power intent."
- **Current (dec-follow consequence):** "A change of a clamp, of an output of `u_cpu` or `u_gpu`, or of a top-level instance fails the check until the file follows."
- **Current (dec-facts consequence):** "After an RTL change that moves ports or clamps, regenerate the facts file and review the difference (...)."
- **Current (UM, Regenerate the facts):** "Do this after an RTL change that moves ports of `u_cpu`, `u_gpu` or `u_sram`, or that changes a clamp."
- **What the files show:** `check_upf.py::_check_domains` takes the instance list from `facts["arms"][arm]["instances"]`, not from the RTL. `build_facts_arm` writes `instances`, `ports` (of `u_cpu`, `u_gpu`, `u_sram`), `clamps`, `paths`, `nets`, `clock_gates` and `test_en_net`. With a new instance in the RTL and the old facts, `check_upf.py -v` passes; the CI step "UPF facts drift gate" (`gen-facts --check`) fails. Only after `gen-facts` does `check_upf.py` report U03 for the roster. In addition the keys of `paths` and `nets` come from the UPF (`rtl_path_refs(up)`, `rtl_net_refs(up)`), so a UPF edit that names a new net or path gives U08 "absent from the facts file; run gen-facts" until the facts are regenerated. The UM procedure "A top-level instance changes" has no regenerate step.
- **Proposed DS-PWR-003 Information:** "The checker reads the top-level instances from the facts file. After an instance is added to `soc_top` or removed from it, the drift check of the facts file fails until the facts file is regenerated. After that, the checker fails until the roster names the instance. The change forces a review of the power intent."
- **Proposed dec-follow consequence:** "A change of a clamp, of an output of `u_cpu` or `u_gpu`, or of a top-level instance fails the drift check of the facts file until the facts file is regenerated, and then fails the checker until the file follows. \Cref{um:ch:power-integration:upf} tells what to do."
- **Proposed dec-facts consequence:** "Regenerate the facts file after each change of a top-level instance, of a port of `u_cpu`, `u_gpu` or `u_sram`, of a clamp, of the test enable of a top-level clock gate, or of a net or instance path that the power intent names. Review the difference (\cref{um:ch:power-integration:upf}). Never edit the facts file by hand."
- **Proposed UM, "A top-level instance changes", new step 3 (before "Run the checker"):** "Regenerate the facts (see below). The checker reads the instances from the facts file, so it does not see the change before this step."
- **Proposed UM, "Regenerate the facts", first sentence:** "Do this after each change of a top-level instance of `soc_top`, of a port of `u_cpu`, `u_gpu` or `u_sram`, of a clamp, or of the test enable of a top-level clock gate. Do it also after an edit of the power intent that names a new net or a new instance path. Run the commands from the root of the repository."

### 3. WRONG: TM "Verification" says the ad hoc trial found no U06 finding; the list of untested checks is incomplete
- **Where:** TM `power.tex`, subsection Verification, the itemize and the sentence after it; TM findings table row U06.
- **Current:** "An ad hoc run of the checker on changed copies of the file gave a finding for each aspect except the last. This run is not a test in the repository."
- **What the files show:** E34 adds `create_power_switch PSW -domain PD_NONE -input_supply_port {vin VDD} -output_supply_port {vout VDD_CPU} -control_port {c pmu_cpu_iso_en_sync}` -> exit 1, `U06 [line 214] switch PSW: domain 'PD_NONE' does not exist`. So U06 can be raised. Further checks that have code and no test, each confirmed by a trial: element outside its domain (E16, U05 "is not inside domain PD_CPU" and "isolated twice"), classification line naming a non-gated output (E18, U05) or an isolated output (E19, U05), `-elements` missing (E25, U05), unconnected supply port (E23, U04), supply set without power state (E17, U04 and U07), rail that can be off without OFF state (E14, U04), malformed roster line (E30, U03), unknown class (E31, U05), wrong isolation signal (E26, U05), encoding missing from a state (E20, U07). The assignment check in `dft_ctrl_ports.sv` has no test and I did not break it (it reads a repository file).
- **Proposed replacement (itemize + sentence):**
  "These aspects have a check in the code and no test:
  - The location `parent` of a strategy.
  - An isolation strategy for each gated domain, and the option `-elements` of a strategy.
  - An element that is not inside the domain of its strategy, and an element in two strategies.
  - A classification line that names an output of no gated domain, or an output that a strategy names, or an unknown class.
  - A roster line with more than one name.
  - A supply port that no supply net uses, a supply set without a power state, and a rail with an OFF port state but no OFF power state.
  - The rails and the independence from the mode in the state `SCAN`, and the assignment in `dft_ctrl_ports.sv`.
  - The refusal of the commands that map isolation cells and declare level shifters.
  - The design top `soc_top`.
  - The U06 findings of a switch.
  A review run of the checker on changed copies of the file gave the expected finding for each aspect except the assignment in `dft_ctrl_ports.sv`, which the run did not change. This run is not a test in the repository."
- **Proposed U06 row, middle cell:** "A switch names a domain that exists, supply nets that exist and a control port. A control or acknowledge net of a switch that the facts file has as unresolved gives U06."

### 4. WRONG: "The checker is the only program that reads it"
- **Where:** DS Scope, Information box, sentence 2; UM `um:ch:power-integration:upf` intro, sentence 4; TM Introduction paragraph 2, sentence 1.
- **Current (DS):** "No physical flow of the project reads the file. The checker is the only program that reads it."
- **Current (UM):** "The checker is the only program that reads the file."
- **Current (TM):** "One program reads the file: `tools/verif/check_upf.py`." (the same paragraph then names the pinned-text check as a second reader).
- **What the files show:** `check_pinned_text.py::check_upf` reads every line of the UPF (`UPF = "pnr/constraints/phase5_soc.upf"`); `check_doc_labels.py::check_citations` reads its `# Doc:` line; `check_comment_budget.py` applies the `hdr_pnr` budget and the banned-content rules to `pnr/*.upf` (`HASH_EXT`, `PNR_HDR_EXT`). All three run in `qa-checks.yml`.
- **Proposed DS:** "No physical flow, simulator or linter of the project reads the file. The checker is the only program that reads its commands. The pinned-text check reads its directive lines, and the documentation checks read its comments."
- **Proposed UM:** "The checker is the only program that reads the commands of the file."
- **Proposed TM:** "One program reads the commands of the file: \src{tools/verif/check_upf.py}." Add at the end of the paragraph's second sentence group: "The documentation checks \src{tools/docs/check_doc_labels.py} and \src{tools/docs/check_comment_budget.py} read its comments."

### 5. WEAK-VERIFY: DS-PWR-001 — the checker does not enforce `PD_SRAM` or the names; the cited test proves DS-PWR-083
- **Where:** DS-PWR-001 `verify=` and Information.
- **Current info:** "The checker enforces the membership, not the names. It reports a finding when a named instance does not exist ... (finding U02). It reports a finding when no domain holds the top scope, or when the excluded instances of this domain differ from the instances of the other domains (finding U03). The state check uses the names `PD_CPU` and `PD_GPU`."
- **What the files show:** E01 deletes `create_power_domain PD_SRAM`, removes `u_sram` from `-exclude_elements` and adds `# upf-check aon u_sram` -> PASS. E27 renames `PD_PERIPH` to `PD_TOP` -> PASS. E29 renames `PD_CPU` -> U07 (`_domain_set(up, "PD_CPU")`). `u_cpu` in `PD_CPU` and `u_gpu` in `PD_GPU` are enforced only through the isolation check ("is not inside domain", E16). `test_missing_instance_fails` changes `-elements {u_cpu}` to `u_cpux` and expects U02: existence of a path, which is DS-PWR-083.
- **Proposed verify:** `[verify={check:tools/verif/check_upf.py; review}]` (drop `test:...::test_missing_instance_fails`, it stays on DS-PWR-083).
- **Proposed Information:** "The checker enforces part of the rule. The isolation check requires that `u_cpu` is in the domain of `ISO_CPU` and `u_gpu` in the domain of `ISO_GPU`, and the state check needs the names `PD_CPU` and `PD_GPU` (\reqref{DS-PWR-041}). The checker does not require the domain `PD_SRAM` and does not check the names `PD_SRAM` and `PD_PERIPH`. A trial that moved `u_sram` into the roster of `PD_PERIPH` and removed `PD_SRAM` passed. A reviewer checks these parts."

### 6. WEAK-VERIFY: DS-PWR-005 — the available supplies are not checked
- **Where:** DS-PWR-005 Information.
- **Current:** "The checker requires that each named supply set exists. It finds the gated domains from the power nets of the primary supplies. A wrong supply set fails the check of the power states (DS-PWR-041) or the check of the isolation (DS-PWR-026)."
- **What the files show:** `_check_supply` checks only that each `-available_supplies` set exists. E02 removes `-available_supplies {SS_AON}` from `PD_CPU` -> PASS. A wrong primary set does fail (E28: `PD_SRAM` on `SS_CPU` -> U05 "gated domain PD_SRAM has no set_isolation").
- **Proposed Information (append):** "The checker does not require the available supply `SS_AON` of `PD_CPU` and `PD_GPU`. A trial that removed it from `PD_CPU` passed. A reviewer checks this part."

### 7. WEAK-VERIFY: DS-PWR-006 — net names and ground nets of the supply sets are not checked
- **Where:** DS-PWR-006 (no Information).
- **What the files show:** `_check_supply` requires only that each function net exists. E03 gives `SS_CPU` the ground net `VDD` -> PASS. A changed power net is caught only when it changes which domains are gated.
- **Proposed Information (new, after the rule):** "The checker requires that each net of a supply set exists, and it compares the power nets with the power net of the always-on domain. It does not check the ground nets. A trial that gave `SS_CPU` the ground net `VDD` passed. A reviewer checks the names of the nets."

### 8. WRONG: TM says every synchroniser of the first roster group runs on `cpu_core_clk`
- **Where:** TM `power.tex`, paragraph after the roster table.
- **Current:** "The reason of the first group is that the synchronisers run on `cpu_core_clk`. This clock is an ungated PLL output, so the synchronisers keep running while the clock of `u_cpu` is stopped."
- **What the files show:** `soc_top.sv` lines 430-435: `u_cpu_iso_ack_sync` has `.clk_i (core_clk)`, `.rst_n_i (core_rst_n)`. The other six (`u_cpu_clk_dis_sync`, `u_cpu_iso_en_sync`, `u_cpu_pmu_rst_sync`, `u_cpu_wdt_rst_sync`, `u_ext_irq_sync`, `u_timer_irq_sync`) use `cpu_core_clk`. The TM figure caption of `fig:tm:ch:mod-power-management:soc` already says "`u_cpu_iso_ack_sync` runs on `core_clk`." The UPF group comment (line 19-20) has the same error (observation O3).
- **Proposed:** "The comment of the first group says that the synchronisers run on `cpu_core_clk`, an ungated PLL output, so that they keep running while the clock of `u_cpu` is stopped. This holds for six of the seven. `u_cpu_iso_ack_sync` runs on `core_clk` and carries the acknowledge back to the PMU. It stays powered because the PMU waits for it."

### 9. INCONSISTENT: DS-PWR-004 says the file gives a reason for each group; the TM says only the first two groups have one
- **Where:** DS-PWR-004 Information, sentence 1.
- **Current:** "The file gives the reason for a group of roster instances in the comment above the group."
- **What the files show:** UPF lines 19-20 and 28 give reasons; lines 31, 36, 41, 48 ("CDC bridges (...)", "Power management and DFT:", "Clocking and fabric:", "Bus masters and peripherals:") give roles. The TM paragraph before the roster table says the same.
- **Proposed:** "The comment above the first two groups of the roster gives the reason that the group stays powered. The comment above each other group names only the role of the group."

### 10. WRONG: dictionary "always-on roster" includes `u_sram`
- **Where:** `docs/manual/common/dictionary.yaml`, term `always-on roster`.
- **Current:** "The list in the power intent of the top-level instances that stay powered while the gated domains are off."
- **What the files show:** `u_sram` stays powered (`PD_SRAM`, primary `SS_AON`) and is not in the roster; `_check_domains` sets `expected_aon = set(insts) - set(seen)`, the instances of the domain with element `.`.
- **Proposed definition:** "The list in the power intent of the top-level instances of the always-on domain that holds the top scope. A checker compares it with the RTL."
- Then run `python tools/docs/gen_glossary.py`.

### 11. UNCLEAR: "Always-on domain" means `PD_PERIPH` only, but the text says two domains are always on
- **Where:** DS Definitions, item "Always-on domain"; DS section "Domains and supplies", sentence 2.
- **Current:** "Always-on domain: The power domain that holds the top scope of `soc_top`. ... In the file this is `PD_PERIPH`." and "The file has four power domains. Two are gated and two are always on."
- **What the files show:** `PD_PERIPH` and `PD_SRAM` both have primary `SS_AON`. The dictionary (`always-on domain`: "A power domain that stays powered while the other domains are off") and DS-PMU Definitions ("The power domain that stays powered while the CPU domain and the GPU domain are off.") include `PD_SRAM`.
- **Proposed definition:** "Always-on domain: The power domain that holds the top scope of `soc_top`. The checker finds it by its element `.`. In the file this is `PD_PERIPH`. `PD_SRAM` has the same primary supply, but this chapter does not call it the always-on domain."
- **Proposed section sentence:** "The file has four power domains. `PD_CPU` and `PD_GPU` are gated. `PD_PERIPH` and `PD_SRAM` have the always-on supply."

### 12. WRONG: "The option `-v` prints one line for each group of checks that passed"
- **Where:** TM `tm:pd:phase5-soc-upf:checker`, paragraph "What each finding proves", sentence 3.
- **What the files show:** `run_check`: `if verbose or not findings:` prints every `log` line with the prefix `ok`. `log` lines are appended whether or not the group had findings. Run on E26 with `-v`: prints "ok isolation[asap7]: 14 UPF-isolated == 14 RTL-clamped ..." and then 16 U05 findings. Run on the clean file without `-v`: prints the five `ok` lines.
- **Proposed:** "The checker prints one summary line for each group of checks, with the prefix `ok`, when the file is clean or when the option `-v` is given. The prefix does not show that the group passed. Only the finding lines and the last line `check_upf: PASS` or `check_upf: FAIL` give the result."

### 13. MISSING: `gen-facts` and the drift test depend on the working directory
- **Where:** DS-PWR-080 Information; TM paragraph "The facts file"; TM "Where it runs"; UM "Regenerate the facts" (see finding 2).
- **What the files show:** `FILELIST = "rtl/filelist/soc_top.f"` (relative); `_elaborate` passes `-f rtl/filelist/soc_top.f`, and the file list holds relative paths (`+incdir+rtl/soc`, ...). From another directory slang cannot load the list and `_elaborate` raises `RuntimeError` (a traceback, not exit 3). `test_facts_file_matches_fresh_elaboration` calls `build_facts` the same way, so from `tb/tests` it errors when `pyslang` is installed. `AGENTS.md` section 4 lists `cd tb/tests && pytest -v` as an entry point. (Inferred from the code; I did not run the elaboration. `pyslang` is installed on this host.)
- **Proposed DS-PWR-080 Information (append):** "The command and the test find the file list by a path relative to the working directory. Run them from the root of the repository. From another directory they stop with an error."
- **Proposed TM "The facts file", append:** "The generator names \src{rtl/filelist/soc_top.f} by a relative path, so \code{gen-facts} and the drift test run only from the root of the repository. From another directory, for example \src{tb/tests}, the drift test fails with an error."

### 14. MISSING: the checks of the state SCAN run only when the state exists
- **Where:** DS-PWR-043 (no Information); DS-PWR-040.
- **What the files show:** `_check_pst`: SCAN is in `EXTRA_STATES` (allowed, not required); `_check_scan_claim` runs only inside `if name == "SCAN"`. E11 removes the SCAN state -> PASS.
- **Proposed Information after DS-PWR-043:** "The checker checks the state `SCAN` and the clock gates (\reqref{DS-PWR-044}) only when the state exists. A file without the state `SCAN` passes. A reviewer checks that the state is present."

### 15. WEAK-VERIFY: DS-PWR-084 — the pinned-text check does not report a misspelled `upf-check`
- **Where:** DS-PWR-084 Information; TM paragraph "Directive lines", last two sentences.
- **Current (DS):** "The checker reads a misspelled line as a comment. It then reports a missing roster entry or a missing classification, and not the misspelling. The pinned-text check reports the misspelling."
- **What the files show:** `check_pinned_text.py::check_upf` collects lines matching `^\s*#\s*upf-check\b` and fails each that the directive regex `^\s*#\s*upf-check\s+(aon|unclamped)\b(.*)$` does not match. A line `# upf-chek aon u_pmu` (E12) matches neither: the pinned-text check ignores it and the checker reports only U03 "u_pmu ... not in the '# upf-check aon' roster". The test `test_upf_directive_lines_must_parse` covers `# upf-check bogus u_x` only.
- **Proposed DS Information:** "The checker reads a line whose kind word is wrong as a comment. It then reports a missing roster entry or a missing classification, and not the wrong word. The pinned-text check reports a line that starts with the word `upf-check` and does not have the kind `aon` or `unclamped`. Neither check reports a line in which the word `upf-check` itself is misspelled. A change of the kind, the names or the class of a directive line is a change of the power intent."
- **Proposed TM (replace the last two sentences of "Directive lines"):** "The checker reads every other line that starts with the word `upf-check` as an ordinary comment. The pinned-text check reports such a line (\reqref{DS-PWR-084}). A line in which the word `upf-check` itself is misspelled is an ordinary comment to both checks. The checker then reports the instance or the output that the line was to name."

### 16. UNCLEAR: "Do not reword a line that starts with the words `upf-check`" — the text after two hyphens is free
- **Where:** UM `um:ch:power-integration:upf`, first bullet of "Keep these points in mind".
- **Current:** "Do not reword a line that starts with the words `upf-check`. The checker and the pinned-text check read the exact form."
- **What the files show:** `parse_directives` does `rest.split("--", 1)[0]`; the text after `--` is not read by either check. The UPF header line 17 says "Do not reword the upf-check lines."
- **Proposed:** "Keep the form of each line that starts with the word `upf-check`: the kind, the names and the class. The checker and the pinned-text check read them. The checker does not read the text after the two hyphens. The file asks that you do not reword these lines."

### 17. INCONSISTENT: DS-PWR-044 restates DS-PMU-108
- **Where:** DS-PWR-044 vs DS `power.tex` DS-PMU-108 ("The test enable of `u_cpu_cg` and `u_gpu_cg` must be `dft_test_en`.").
- **What the files show:** Both rules require the same connection; DS Scope of the power-intent chapter says "This chapter does not repeat those rules."
- **Proposed:** Use the DS-PWR-044 body of finding 1 and add to its Information: "\reqref{DS-PMU-108} states the connection for the clock gates. This rule states that the state `SCAN` of the file depends on it."

### 18. STYLE: "This must hold in both arms" stated three times
- **Where:** DS-PWR-003 (last sentence), DS-PWR-020 (last sentence), DS-PWR-082.
- **Proposed:** Delete "This must hold in both arms." from DS-PWR-003 and DS-PWR-020. Keep DS-PWR-082. Add the tests of the roster to DS-PWR-082 only if a test exists for the sky130 arm (none does: `test_new_top_level_instance_forces_roster_update` changes asap7 only), so leave its verify as is.

### 19. MISSING: TM findings table row U05 omits checks that have tests cited in the same row
- **Where:** TM table `tab:tm:pd:phase5-soc-upf:findings`, row U05, middle cell.
- **What the files show:** `_check_isolation` also checks the isolation supply (tests cited in the row), `-location parent`, clamp value `0|1`, sense `high|low`, `-elements` present, one strategy for each gated domain, no element in two strategies, and the classification lines. `_check_switch_and_net_refs` gives U05 for an isolation net that is unresolved in the facts (`test_unresolved_net_in_facts_fails`, cited).
- **Proposed middle cell:** "The isolation rules of \cref{ds:ch:power-intent:isolation}: each gated domain has a strategy with `-elements`; the clamp set equals the RTL set, with the same control net, clamp value and sense; the isolation supply is a supply set on the always-on rail; the location is `parent`; each element is an output of an instance in the domain and is in one strategy only; the control net resolves in the facts; each other output of a gated domain is classified, a classification names only such outputs, and the class is known."

### 20. MISSING: TM "Tool compatibility" omits that OpenROAD failed on this file's first command
- **Where:** TM subsection Tool compatibility, sentence 3.
- **Current:** "A measurement in the archived text of the power-intent document found that the command `read_upf` of OpenROAD reads only a small subset of UPF 3.0 (\cref{cr:arc:ds-upf-power-spec})."
- **What the files show:** archive `ds:ch:upf-power-spec:tool-compatibility`: "It fails on the first command of both the old file (`create_supply_port`) and the new one (`upf_version`)."
- **Proposed:** "A measurement in the archived text of the power-intent document found that the command `read_upf` of OpenROAD reads only a small subset of UPF 3.0, and that it stopped at the first command of this file, `upf_version` (\cref{cr:arc:ds-upf-power-spec})."

### 21. MISSING: the facts file depends on the power intent as well as on the RTL
- **Where:** DS Definitions "Facts file"; dictionary `facts file`; TM table `tab:tm:pd:phase5-soc-upf:facts` rows `paths` and `nets`.
- **Current (DS):** "A program generates it from the RTL. The checker reads it in place of the RTL."
- **What the files show:** `build_facts_arm(arm, up)`: `paths` keys = `rtl_path_refs(up)`, `nets` keys = `rtl_net_refs(up)`, `ports` for the instances that the UPF domains and strategies name. `run_gen` refuses to write when `parse_upf` has findings.
- **Proposed DS definition:** "The file \src{pnr/constraints/phase5_soc_rtl_facts.json}. A program generates it from the RTL, for the nets and instance paths that the power intent names. The checker reads it in place of the RTL."
- **Proposed dictionary definition:** "The JSON file that the checker of the power intent reads in place of the RTL. A program generates it from the RTL for the names that the power intent uses."
- **Proposed TM rows:** `paths`: "The module name of each instance path that the power intent names, or null. The power intent gives the list." `nets`: "The kind and the width of each net that the power intent names, or null. The power intent gives the list."

### 22. MISSING: UM has no procedure for a new domain or a new top-level clock gate, and does not say what a CI failure looks like
- **Where:** UM `um:ch:power-integration:upf`.
- **What the files show:** `_check_pst` takes the CPU and GPU rails from `_domain_set(up, "PD_CPU")` and `"PD_GPU"` only; a third gated domain needs its own supply set, OFF port state, strategy (U05 "gated domain ... has no set_isolation") and classification of every output (E28: 26 findings). `_check_scan_claim` checks every top-level `rv32i_clock_gate`. CI step names in `qa-checks.yml`: "UPF structural gate (phase5_soc.upf vs soc_top and pmu.sv)" and "UPF facts drift gate (facts file matches a fresh elaboration of the RTL)"; the drift failure prints "check_upf gen-facts --check: DRIFT - ..." and up to 60 diff lines on stderr; a check failure prints "check_upf: FAIL - N finding(s) in ...". `check_comment_budget.py` applies the header budget to `pnr/*.upf`; the `upf-check` lines are pragmas (`_PRAGMA_ANY`) and do not count.
- **Proposed UM paragraph (after "An output of the CPU or the GPU changes"):** "\paragraph{A power domain changes.} A new domain, a domain that is removed, or an instance that moves between domains is a change of the power architecture. Stop and ask the owner. The checker compares the rails of the power states only for \code{PD_CPU} and \code{PD_GPU}. A new gated domain also needs a supply set, a supply port with an OFF port state, an isolation strategy and a classification of each of its outputs."
- **Proposed UM, step in "A top-level instance changes" (after the roster step):** "If the instance is a clock gate \code{rv32i_clock_gate}, connect its test enable to \code{dft_test_en}. The checker requires this of each top-level clock gate."
- **Proposed UM, append to "Find what the change broke":** "In CI the two steps are \textit{UPF structural gate} and \textit{UPF facts drift gate} of the workflow \code{qa-checks}. The first prints \code{check_upf: FAIL} and one line for each finding. The second prints \code{DRIFT} and the first lines of the difference."
- **Proposed UM bullet in "Keep these points in mind":** "A new comment line in the header of the file counts against the comment budget of \src{tools/docs/check_comment_budget.py}. The lines that start with the word \code{upf-check} do not count."

### 23. STYLE: "must" outside a requirement body in the TM
- **Where:** TM paragraph after the facts table: "The select net must have the text `iso` in its name."
- **Proposed:** "The generator takes only a select net whose name contains the text `iso`."

### 24. UNCLEAR: DS-PWR-027 names the class "slave response"; the file token is `slave_response`
- **Where:** DS-PWR-027 body and Information.
- **What the files show:** `CLASSES = ("payload", "slave_response", "observability")`; E31 (`slave response`) -> U05 "unclamped class 'slave response' not in ...".
- **Proposed body:** "Each output of a gated domain that no strategy names must be in a classification line with the class `payload`, `slave_response` or `observability`. ..." (rest unchanged). In the Information, write `slave_response` in the first sentence.
- **Also add to the Information:** "The test removes an output from a classification line. A classification of an isolated output, of an output of no gated domain and an unknown class have a check and no test."

### 25. UNCLEAR: "The PMU has the same steps without the switch"
- **Where:** TM subsection Switches and retention, last sentence.
- **What the files show:** DS-PMU-021: ret_save, iso_en, clock stop, reset. DS-PMU-022: reset release, clock start, ret_restore, iso release. The PMU adds the clock stop and start and has no switch step.
- **Proposed:** "The PMU has these steps without the switch, and it stops the clock before the reset and starts it after the reset release (\reqref{DS-PMU-021} and \reqref{DS-PMU-022})."

### 26. MISSING: the parts of DS-PWR-025 and DS-PWR-045 that have no test
- **Where:** DS-PWR-025 (no Information), DS-PWR-045 Information.
- **What the files show:** `test_input_port_cannot_be_isolated` covers the direction only; "inside the domain" fails by code (E16). `test_off_state_without_off_port_state_fails` covers OFF state without OFF port state; the reverse (E14) and "no power state" (E17) have code and no test.
- **Proposed after DS-PWR-025:** "\begin{information} The test adds an input port to a strategy. An element outside the domain of its strategy has a check and no test. \end{information}"
- **Proposed DS-PWR-045 Information (append):** "The test removes the OFF port state of `VDD_GPU`. A rail with an OFF port state and no OFF power state, and a supply set without a power state, have a check and no test."

### 27. MISSING: DS-PWR-061 Information on what the checker does with a switch
- **Where:** DS-PWR-061 Information, sentence 2.
- **Current:** "The checker accepts a switch command when its options are known and its nets exist."
- **What the files show:** `_check_switch_and_net_refs` also requires an existing `-domain` and a `-control_port` (E34). E09 adds a switch on `VDD_CPU` while the supply port `VDD_CPU` still drives the net: PASS, so a supply net with two sources is not reported.
- **Proposed:** "The checker accepts a switch command when its options are known, its domain and supply nets exist, it has a control port and its control net is in the facts file. It does not report a supply net that has both a supply port and a switch as source."

### 28. MISSING: DS-PWR-007 — the direction of a supply port is not checked
- **Where:** DS-PWR-007 Information.
- **What the files show:** `_check_supply` counts a net as sourced when any port connects to it; E35 sets `create_supply_port VDD_CPU -direction out` -> PASS.
- **Proposed Information (append):** "The checker takes each connected supply port as a source. It does not check the direction of the port."

### 29. UNCLEAR: DS-PWR-020 Information describes the generator too narrowly
- **Where:** DS-PWR-020 Information, sentence 4.
- **Current:** "The assignment selects between a constant and the output of a top-level instance, and the select signal is a net whose name contains the text `iso`."
- **What the files show:** `build_facts_arm` records any named source; when no instance output drives it the element is `?/<net>` (TM says so correctly). Sense low is any unary operator on the select.
- **Proposed:** "The assignment selects between a constant and a named signal, and the select signal is a net whose name contains the text `iso`, or the inverse of such a net. The element is the top-level instance output that drives the signal."

### 30. UNCLEAR: TM "The checker reads the top scope of `soc_top`, the ports of three instances ..."
- **Where:** TM paragraph "The two arms use the defines ...", sentence 4.
- **What the files show:** the checker reads only the facts file; the generator `build_facts_arm` reads the elaboration.
- **Proposed:** "The generator reads the top scope of `soc_top`, the ports of the three instances that the domains name and the test-enable connection of each clock gate. It does not read the inside of a clock gate."

### 31. UNCLEAR: TM SCAN table column header "Matches all on"
- **Where:** `tab:tm:pd:phase5-soc-upf:scan`, header of column 3.
- **Proposed header:** "Matches the state SCAN".

### 32. MISSING: TM does not point to the archived comment text of the file
- **Where:** TM Introduction of `tm:pd:phase5-soc-upf`.
- **What the files show:** `cr:arc:tm-phase5-soc-upf` (archive line 2467) holds the comment text that this section replaced.
- **Proposed (append to the Introduction, paragraph 1):** "The comment text that the file held before is in \cref{cr:arc:tm-phase5-soc-upf}."

### 33. MISSING: dictionary has no term "gated domain"
- **Where:** `dictionary.yaml`; the new term `always-on roster` uses "gated domains"; DS defines "Gated domain".
- **Proposed new term:** `term: gated domain`, `kind: technical-name`, `definition: A power domain whose supply can be switched off. In the power intent of the SoC these are the CPU domain and the GPU domain.`, `glossary: true`.

### 34. INCONSISTENT: two definitions of "power domain"
- **Where:** DS power-intent Definitions "Power domain: A set of instances that share one supply set as primary supply." vs dictionary and DS-PMU Definitions "A set of instances that share one supply and one power state."
- **Proposed DS power-intent definition:** "Power domain: A set of instances that share one supply and one power state. In the file each domain has one supply set as primary supply. \Cref{ds:ch:mod-power-management:definitions} gives the same term for the PMU." (drop the existing second sentence).

### 35. UNCLEAR: TM "Contents of the file" sentence on directive lines
- **Where:** TM `Contents of the file`, sentence 3: "The comment lines that start with the words `upf-check` are part of the file."
- **Proposed:** "The comment lines that start with the word `upf-check` carry data for the checker. \Cref{tm:pd:phase5-soc-upf:checker} describes them."

### 36. STYLE: DS-PWR-001 and DS-PWR-045 each hold several statements with different verification
- **Where:** DS-PWR-001, DS-PWR-045.
- **Proposed:** keep the IDs (no new IDs in this PR), and rely on the Information notes of findings 5 and 26 to say which statement each check and test covers. If the owner allows new IDs, split DS-PWR-001 into domain names (review) and membership (check).

### 37. LABEL: `ds:ch:upf-power-spec` resolves into the archive
- **Where:** `docs/manual/cr/parts/06-source-archive.tex` line 960 (`\section{UPF Power Intent Specification}\label{ds:ch:upf-power-spec}` inside the `relocated` block); intro line 956.
- **Citing places and what the reader needs:**
  | Place | Text | Reader needs |
  | :-- | :-- | :-- |
  | `pnr/constraints/phase5_soc.upf` line 205 | "So a clamp can be active under scan. This is documented, not changed. See ds:ch:upf-power-spec." | Current spec of the scan limit (DS-PWR-044 Information, TM SCAN table) |
  | `pnr/README.md` line 148 | "UPF Power Spec: `Doc: ds:ch:upf-power-spec`" | Current spec |
  | `docs/manual/um/parts/01-chapters.tex` line 6869 | key-documents table row "UPF_POWER_SPEC.md (\cref{ds:ch:upf-power-spec}) & Power intent and UPF specification" | Current spec |
  | `docs/manual/ds/parts/01-architecture.tex` line 15110 | Phase 5 power domains "per UPF_POWER_SPEC.md (\cref{ds:ch:upf-power-spec})" | Current spec (the four domains of `phase5_soc.upf`) |
  | `docs/manual/cr/parts/06-source-archive.tex` line 2635 | archived moved UPF comment "Doc: ds:ch:upf-power-spec "Phase 5"" | History; the archive section `ds:ch:upf-power-spec:phase-5-full-soc-integration` keeps its own label |
  | `docs/manual/common/path_map.tsv` line 69 | old path -> archive file -> `ds:ch:upf-power-spec` | Where the old document's text is now (archive); the label is only checked for existence (`check_doc_labels.py::check_path_map`) |
- **Recommendation:** Move the single line-level `\label{ds:ch:upf-power-spec}` out of the archived `\section` at line 960 and onto the new chapter, as a second label of `\chapter{Power intent}` in `docs/manual/ds/parts/chapters/power-intent.tex` (line 3: `\chapter{Power intent}\label{ds:ch:power-intent}\label{ds:ch:upf-power-spec}`). Then five of the six citers reach the current specification without a source change. The archived line-2635 citation then lands on the current chapter, whose Scope already links `cr:arc:ds-upf-power-spec`; that is acceptable for a history note. Change the archive intro (line 956, authored text, not record text) last sentence to: "The label \code{ds:ch:upf-power-spec} of the old document now names the authored chapter \cref{ds:ch:power-intent}. The labels inside the text are the labels of the old document." Change `path_map.tsv` line 69 to `docs/design/UPF_POWER_SPEC.md	docs/manual/ds/parts/chapters/power-intent.tex	ds:ch:upf-power-spec` (the old path's current replacement; the archive stays reachable from the chapter Scope). Then regenerate `labels.tsv` and run `check_doc_labels.py`. This needs the owner's acceptance of a one-line change inside the `relocated` block (the archived text is otherwise byte-identical).
- **Fallback if the owner refuses:** keep the label in the archive, and file a follow-up to change the two source citations (`phase5_soc.upf` line 205, `pnr/README.md` line 148) to `ds:ch:power-intent` in a later PR; in this PR change the two book citations (UM line 6869, DS line 15110) to `\cref{ds:ch:power-intent}` only if those converted texts may be edited; otherwise leave them and list them in the PR description.

---

## Table of the 30 rules

| Rule | Verdict | Finding |
| :-- | :-- | :-- |
| DS-PWR-001 | WEAK-VERIFY: names and PD_SRAM not checked; cited test proves 083 | 5, 36 |
| DS-PWR-002 | OK (U03 overlap + exclude equality + roster; test kills) | - |
| DS-PWR-003 | OK; Information needs the facts-regeneration step; duplicate "both arms" | 2, 18 |
| DS-PWR-004 | OK (review); Information inconsistent | 9, 8 |
| DS-PWR-005 | WEAK-VERIFY: available supplies not checked (E02) | 6 |
| DS-PWR-006 | WEAK-VERIFY: ground nets and net names not checked (E03) | 7 |
| DS-PWR-007 | OK; port direction not checked (E35) | 28 |
| DS-PWR-020 | OK (4 tests kill); Information narrow; duplicate "both arms" | 29, 18 |
| DS-PWR-021 | OK (tests kill U05) | - |
| DS-PWR-022 | OK (U08 / U05 tests kill) | - |
| DS-PWR-023 | OK (check; no test; E04b gives U05) | - |
| DS-PWR-024 | OK (two tests kill) | - |
| DS-PWR-025 | OK; "inside the domain" has no test (E16) | 26 |
| DS-PWR-026 | OK (check; no test; E05 gives U05 "has no set_isolation") | - |
| DS-PWR-027 | OK; class token; untested parts | 24 |
| DS-PWR-028 | OK (review only, stated) | - |
| DS-PWR-040 | OK (tests kill) | 14 |
| DS-PWR-041 | OK (test kills) | - |
| DS-PWR-042 | OK (test kills) | - |
| DS-PWR-043 | OK when SCAN exists (E08a/b/c give U07, no test); vacuous without SCAN (E11) | 14 |
| DS-PWR-044 | WRONG body (dft_ctrl OR); duplicate of DS-PMU-108; text-regex part untested | 1, 17 |
| DS-PWR-045 | OK; untested directions | 26, 36 |
| DS-PWR-060 | OK (U01; test kills) | - |
| DS-PWR-061 | OK as review-only (author is right: E09 passes); Information incomplete | 27 |
| DS-PWR-062 | OK (U01, E06a/E06b; no test, stated) | - |
| DS-PWR-080 | OK (CI `gen-facts --check`; test skips without pyslang); cwd not stated | 13 |
| DS-PWR-081 | OK (tests kill; design top untested, E07 gives U01) | - |
| DS-PWR-082 | OK (tests per arm on clamps) | 18 |
| DS-PWR-083 | OK (U02/U08/U05) | - |
| DS-PWR-084 | WEAK-VERIFY: misspelled `upf-check` escapes both checks | 15 |

Author's self-reported points, verified:
- Rule 061 review-only because no check forbids a switch: TRUE (E09 PASS).
- Docstring says retention is refused under U06, code reports U01: TRUE (`check_upf.py` docstring lines 28-29 vs `parse_upf` `REFUSED` -> `up.err("U01", ...)`; `test_retention_is_refused` expects U01). The chapters say U01 (TM) or give no id (DS): correct.
- Drift test depends on the working directory: TRUE by code (finding 13); chapters do not say it.
- Hard-coded clamp count 14: TRUE (`test_clamp_sets_are_the_rtl_sets`, `assert len(els) == 14`); TM Verification and UM say it.
- "Checker derives 'rail can be off' from port states only": TRUE (`_check_supply`, `can_off` from `up.port_states` of the ports connected to the power net); E10 reproduces the U04 finding the TM reports.

## The `create_power_switch` listing
- Uses only options in `_SWITCH_OPTS`; supply names `VDD`, `VDD_CPU` and domain `PD_CPU` match the UPF; the shape equals the archived comment text (`cr:arc:tm-phase5-soc-upf`). The TM presents it as a shape for a later change, not as implemented: correct. The two trials it reports are reproduced (E09 PASS, E10 one U04). No flow is claimed to implement the UPF. I did not compare the listing against the IEEE 1801 text (not in the repository).

## Owner decisions and caveats
- Q3 (only the existing power intent): met. Q2 (no CPU state guarantee, no retention): DS-PWR-060 and the TM retention text agree; the UPF header line 11 also says it. Q5 (scan clamp limit, no DS rule): the limit is in Information notes and the TM Known limits only: met. No power, area or timing figure appears; voltages are named only as "ASAP7 nominal". `AGENTS.md` section 2 caveats are not contradicted (the text tells the reader to read the standing caveats before quoting an ASAP7 power result).

## Observations for the owner (the files themselves, not chapter fixes)
- O1. TAP scan versus the state SCAN: `dft_ctrl.sv` line 141-142 ORs `tap_scan` into `scan_mode_o` and `test_en_o`. With `scan_mode_i` low and the TAP in scan, every functional state of `SOC_PST` still "holds" while the clock gates are forced open and the domain resets follow the scan reset. The SCAN state and the exclusivity rule are defined on the pin only, and the checker's SCAN claim reads `dft_ctrl_ports.sv`, not `dft_ctrl.sv`. Consider a state keyed on `dft_scan_mode` and a check of the `dft_ctrl` combiner.
- O2. `check_upf.py` gaps found by trial: PD_SRAM can be removed (E01); domain names other than PD_CPU/PD_GPU unchecked (E27); `-available_supplies` not required (E02); ground nets unchecked (E03); a SCAN-less file passes (E11); port direction ignored (E35); a net with a port and a switch source is not reported (E09).
- O3. UPF comment errors (pinned/comment text, cannot change in this PR): line 19-20 says the CPU-domain synchronisers run on `cpu_core_clk`, but `u_cpu_iso_ack_sync` runs on `core_clk`; line 13 "The checker fails if a top-level instance is added or removed without a roster update" is true only after `gen-facts` (the drift gate fails first); line 14 "The reason is in the group comment above its lines" holds for two of six groups; line 205 cites `ds:ch:upf-power-spec` (label question).
- O4. `check_upf.py` docstring: lines 28-29 put retention under U06 (code: U01); line 14 says "`-v` lists them" (the finding ids) but `-v` prints the summary log; line 53 cites the removed path `docs/design/UPF_POWER_SPEC.md`.
- O5. `run_check` prints `ok` before every log line even when that group produced findings (E26 with `-v`), which reads as a pass in a CI log.
- O6. `FILELIST` is relative, so `gen-facts` and `test_facts_file_matches_fresh_elaboration` work only from the repository root, while `AGENTS.md` section 4 lists `cd tb/tests && pytest -v` (the drift test would then error; inferred, not run).
- O7. The facts file is keyed by the UPF's references (`rtl_net_refs`, `rtl_path_refs`), so the drift gate couples UPF edits and RTL edits; a UPF-only edit that names a new net needs `gen-facts` and `pyslang`.
- O8. Known gap stands: the 11 `slave_response` outputs are unclamped (UPF line 16); the TM Known limits and DS-PWR-027 say it.
- O9. Directive line 23 carries a tracker id ("bead 3ogd"); `check_comment_budget.py` exempts `upf-check` lines as pragmas, and the pinned rule forbids rewording, so it stays.
- O10. Test-writing trap: `-location parent` also appears in the comment on UPF line 150, so `mutate("-location parent", ..., 1)` changes the comment, not the command (my E04). Existing tests avoid it (`test_unknown_option_and_command_fail` uses count -1), but a new negative control could become a silent no-op if its anchor also occurs in a comment.

## What I did not check
- I ran no `gen-facts`, no `gen-facts --check`, no pytest, no `check_pinned_text.py`, no `gen_glossary.py --check`, no `check_doc_labels.py`, no `check_requirements.py`, no LaTeX build. Findings 13 and O6 are inferred from the code.
- I did not verify that the archived text in `06-source-archive.tex` is byte-identical to the removed text (only the intros and two subsections were read).
- I did not read `generated/requirements-pwr.tex` against the rule bodies, nor the full `glossary.tex` diff.
- I did not check the IEEE 1801 syntax of the listing against the standard text.
- I did not trace whether the JTAG TAP can actually assert `scan_mode_o` in the current `jtag_tap.sv` (O1 rests on the `dft_ctrl` combiner only).
- I did not check the ASD-STE100 style of every sentence; only the meaning-changing style faults above.
