# AGENTS.md

This file is the guide for every agent and person that changes this repository.
Read it before you start work. The long documentation is in the books in `docs/manual/`.

## 1. What this repository is

The repository holds a multi-phase RV32I RISC-V microprocessor and a GPU-lite SoC.
It has the RTL (SystemVerilog), the tests (cocotb and Python), the physical design flows and the documents.

- CPU: 5-stage in-order pipeline with L1 caches (4 KB each, direct-mapped, write-back).
- GPU: single compute unit with 8-lane warps, up to 8 warps, 16 KB shared memory.
- SoC: AXI4 crossbar, DMA, UART, SPI, timer, interrupt controller, PMU, behavioral SRAM.
- Phase 6 blocks: GPIO, PWM, WDT, TRNG, I2C, AES-128 and SHA-256 accelerator, INT8 NPU.
- Phase 7: a mixed-signal PLL (analog flow in `analog/`).
- Technology nodes: Sky130 (real DRC and LVS), ASAP7 (predictive) and FreePDK45 (predictive).

The books in `docs/manual/` are the source of truth. Refer to them. Do not rely on RTL that does not exist.

## 2. Status

| Item | State | Note |
| :--- | :---- | :--- |
| Phase 0 to 2 | Done (2026-03-08) | Pipelined CPU reaches 75 MHz on Sky130 with real post-route SPEF. |
| Phase 3 caches | Done (2026-05-21) | The ASAP7 1418 MHz figure is unvalidated (see caveats). |
| Phase 4 GPU | Done (2026-05-27) | All GPU tests pass. The ASAP7 GPU figures are unvalidated. |
| Phase 5 SoC | Done (2026-06-24) | The latest ASAP7 timing point does not close at 1750 ps (see caveats). |
| Phase 6 IP | Done (2026-10-05) | Sky130 batched harden passed. |
| Phase 7 PLL | Done | Stages M-a to M-c. |
| DFT (scan, JTAG, MBIST) | In progress | JTAG TAP and MBIST merged. Scan insertion is open. |
| FPGA prototype | In progress | No board and no vendor toolchain on the host. |

These caveats always apply. Read them before you quote any result.

- Synlig built the ASAP7 CPU and GPU macro views. They are functionally wrong.
  Simulation of the netlist proved the CPU fault. The GPU fault is shown on one block only.
  The committed views are in `pnr/asap7/cpu/macro/` and `pnr/asap7/gpu/macro/`.
  The SoC flow copies them into `pnr/asap7/soc/macro/`.
- Every ASAP7 CPU and GPU figure rests on the Synlig-built netlists. Every ASAP7 SoC figure reads those views.
- The old ASAP7 timing figures came from an STA run with zero-wire parasitics. Treat them as unvalidated.
- The project withdrew the ASAP7 "0 DRC, 0 antenna" claims. Detailed routing committed no wires.
  This caveat still applies to the latest SoC point.
- The ASAP7 power grid was empty in every run. Routing numbers are lower bounds.
  The SoC configurations still select the old grid script.
- The latest ASAP7 SoC point is setup WNS -727.37 ps at 1750 ps. Hold is clean.
  The point predates the Phase 6 and DFT RTL. It is not a measurement of the present RTL.
- The old ASAP7 SoC power figures count zero power for the two hard macros.
- Sky130 timing uses one SRAM corner model (nom_tt only). "Clean at 9 corners" means 9 labels on one model.
- The Sky130 Magic DRC counts carry a waiver for the SRAM footprints. One Sky130 SoC harden did not run KLayout DRC.
- Commercial flows in `pnr/commercial/` are indicative. No arm meets sign-off.
- The Sky130 CPU macro was re-hardened with sv2v. The older Synlig-built views were wrong.
- ASAP7 CPU and GPU re-hardening waits for a host with 32 GB RAM or more. This is the owner's decision.
  A re-harden on sv2v ended in a routing regression, and the cause is not proven.

Detail for each caveat: the Technical Manual, part "Tool defects and standing caveats" (labels `tm:caveat:*`),
and the run histories in `docs/manual/cr/`.

## 3. Directory map

| Path | Content |
| :--- | :------ |
| `rtl/` | RTL: `cpu/`, `gpu/`, `mem/`, `periph/`, `npu/`, `soc/` (with `cdc/`, `dft/`, `pll/`), `fpga/`, `filelist/` |
| `tb/` | Tests: `cocotb/`, `models/` (Python reference models), `tests/` (pytest), `cpu_uvm/`, `generators/`, `common/` |
| `sim/` | Simulation Makefile and sim support |
| `pnr/` | Physical design: `sky130/`, `asap7/`, `freepdk45/`, `constraints/`, `commercial/`, `config/` |
| `tools/` | Scripts: `verif/`, `docs/`, `eda/`, `setup/`, `cdc/`, `dft/`, `formal/`, `fpga/`, `fw/`, `hls/` |
| `docs/` | Documents: the four books in `docs/manual/`, and `docs/README.md` |
| `dft/` | Tessent flows for scan and MBIST evaluation |
| `fpga/` | FPGA board files (`nexys_video/`) |
| `hls/` | High-level synthesis flows |
| `analog/` | Analog PLL flow |
| `sw/` | Firmware: `bootloader/`, `drivers/`, `bench/` |
| `dqc/`, `lint/` | SpyGlass lint and CDC flows |
| `fixes/` | RTL bug-fix records |
| `memory/` | Agent memory files (curated, force-tracked) |
| `.beads/` | Issue tracker export |
| `micro_p/` | Archived Phase 1 work |
| `install-missing-tools/` | Install scripts for EDA tools |
| `.github/` | CI workflows |

Legacy: `pnr/librelane/` and `pnr/openlane1/` are old flows. Do not start new work there.

## 4. Environment and entry points

The project uses nix devShells from `flake.nix`: `default`, `bench`, `fpga`, `dft`, `docs`, `hls`.
Run simulation and lint flows through `nix develop --command make ...`.

Run these commands in each new clone:

```bash
make setup            # trust filters, set paths, install the git hooks
make verify-tooling   # prove that setup took effect
```

Main entry points:

```bash
cd tb/tests && pytest -v                         # reference-model unit tests
make -C tb/cocotb/soc soc_all_ci                 # SoC regression
cd sim && make phase3_all                        # cache simulations
make -C pnr sky130-soc-sv2v                      # sv2v netlist for the Sky130 SoC
make -C pnr librelane-sky130-soc                 # Sky130 SoC flow
make -C pnr librelane-asap7-soc                  # ASAP7 SoC flow
make -C pnr dft-scan-check                       # DFT scan structural check
python tools/docs/build_books.py                 # build the four PDF books
```

Build commands for each phase are in the User Manual (`um:guide:frequently-used-commands`).

## 5. Hard rules

Each rule names its check. A check that fails blocks the pull request.

1. **No select on a struct member.** Do not take a bit, part or element select on a struct member in `rtl/`.
   Copy the member to a named wire first. Synlig elaborates this idiom wrongly.
   Check: `tools/verif/check_struct_member_select.py`. The waiver file `tools/verif/struct_member_select_baseline.txt` stays empty.
2. **Strict elaboration.** Declare each name before you use it. VCS and Xcelium reject use-before-declare.
   Add each new define arm to the `ARMS` table.
   Check: `tools/verif/check_elab_strict.py`.
3. **Avoid a runtime-indexed mux in new datapath RTL.** The crypto and NPU blocks use two-input ternary trees,
   one-hot AND-OR and shift registers instead. To prove it, count `$shiftx` and `$pmux` on the coarse-grain netlist
   (`synth -run :fine`). A full `synth` hides them.
   Check: none. Review by hand.
4. **PMU outputs that feed a clock crossing come straight from flops.** The flops load from the next-state decode.
   Check: `tools/verif/check_registered_outputs.py` and `tb/tests/test_pmu_registered_outputs.py`.
5. **Use the CDC primitives.** Cross clock domains only with `rtl/soc/cdc/cdc_sync.sv`, `cdc_reset_sync.sv` and `cdc_gray_fifo.sv`.
   Do not put a multi-bit binary bus through `cdc_sync`.
   Check: SpyGlass CDC flow in `dqc/`. No gate in CI.
6. **A reset value must not advertise availability.** A ready signal must be low while its domain is in reset.
   Test at a clock ratio that differs from 1:1, because 1:1 suites hide this fault class.
   Check: none. Review by hand.
7. **sv2v file lists and defines.** Add each new module to the sv2v file lists in `pnr/Makefile`.
   sv2v makes a blackbox for an absent module and gives no error. It resolves `ifdef` before Yosys.
   Check: `tools/verif/check_source_closure.py` (lists close over imports)
   and `tools/verif/check_periph_filelists.py` (each peripheral and NPU module is in all five file lists).
8. **Name the SRAM macro instance `u_sram_macro`.** With any other name, the power connections stay open.
   Check: none. Review by hand.
9. **Filelists come from a generator.** Edit the Makefile sources, never `rtl/filelist/*.f`.
   Check: `tools/verif/gen_filelist.py --check`.
10. **UPF facts match the RTL.** Regenerate the facts file after an RTL change that touches the power structure.
    Check: `tools/verif/check_upf.py -v` and `tools/verif/check_upf.py gen-facts --check`.
11. **Never edit generated files.** Generated files include `rtl/filelist/*.f`, `phase5_soc_rtl_facts.json`,
    `docs/manual/common/glossary.tex` and `docs/manual/common/labels.tsv`. Change the source. Then run the generator.
12. **Pinned text.** Some tools match comments and line text in source. Do not reword pinned lines.
    Check: `tools/docs/check_pinned_text.py`.
13. **Coverage waivers.** Line waivers anchor on comment-stripped text. Run the check after each RTL edit.
    Check: `tools/verif/coverage_report.py --check-waivers --waivers tools/verif/coverage_waivers.txt`.
14. **Sky130 CPU macro pins.** The pin template must reproduce the committed LEF.
    Check: `tools/verif/pin_lock.py check`.
15. **No bead reopen by accident.** A pull request must not move a closed bead to open.
    Check: `tools/setup/check_beads_reopen.py`.

The workflow `.github/workflows/qa-checks.yml` runs most of these checks. `docs.yml` runs the document checks.

## 6. Verification practice

- Test every RTL block against the Python reference models in `tb/models/` (`rv32i_model.py`, `gpu_kernel_model.py`).
- Write the test before the fix. Show that the test fails on the old RTL.
- Add a negative control to each proof. A check that cannot fail proves nothing.
- Use mutation campaigns where they exist. The scripts are `tools/verif/mutate_cdc_gray_fifo.py`,
  `mutate_crypto_scan_wipe.py` and `mutate_pmu_iso_ack.py`. They match exact source lines.
- Compare a gate netlist with the RTL by simulation before you trust the netlist (`tools/verif/gls/sky130/run_netlist_proof.sh`).
- Compare sv2v output with the RTL by formal equivalence (`tools/verif/equiv_sv2v_module.sh`).
- Mark each result as measured or inferred. State the coverage limit of each result.
- Do not gate a decision on `diff`. Use `cmp -s` or `sha256sum`. Some filters change `diff` output and exit code.
- Some checks need tools that are not on every host. Say which checks you ran and which you did not.

## 7. Physical design practice

- Change one variable at a time. Record the run name and the result.
- Report slack, violators and DRC counts from the flow reports. Do not report a count from a flow that did not route.
- Run `python3 tools/verif/check_source_closure.py <config>` before you trust an old config.
- ASAP7 skips Magic, KLayout and Netgen. Only Sky130 has real DRC and LVS.
- Use the sv2v frontend (`USE_SYNLIG:false`) for macros. Synlig miscompiled this repository's CPU. Sv2v did not.
- Do not edit a hard-macro view (LEF, Liberty, GDS) without owner approval.
- The shared LibreLane install is external. Do not edit it. Use the project plugins under `pnr/`.
- Pin the macro boundary pins (`pin_order.cfg`) so that a re-run gives the same LEF.

## 8. Issue tracking

The project uses **bd (beads)** for all tasks. Do not use markdown task lists.

```bash
bd ready                 # find available work
bd show <id>             # view an issue
bd update <id> --claim   # claim work
bd close <id>            # complete work
bd prime                 # full command reference
```

- One Dolt database holds the beads. `.beads/issues.jsonl` is an export of it.
- In a secondary git worktree, do not run `git add .beads/`. The file there is a stale snapshot.
- Commit bead changes before you switch branches. A branch switch can import an older file.
- Never check out a stale local `main`. Run `git fetch`, then `git checkout -B main origin/main`.
- To reopen a closed bead on purpose, add a new line that starts with `beads-reopen-ok:` to its notes.

## 9. Commits and pull requests

- An agent can write RTL, tests, flows and documents.
- A human approves each specification, each architecture decision, each hard-macro change and each merge.
- When a task needs one of these approvals, stop and ask the owner.
- Never commit to `main`. Create a branch. Open a pull request.
- Write the commit subject as `[Category] Brief description`.
- Categories: `[Fix]`, `[Feature]`, `[Code]` (refactor), `[Env]` (build), `[Doc]`, `[Test]`, `[Spec]`, `[RTL]`, `[PD]`, `[Analog]`, `[Chore]`.
- Make one commit for one purpose. Do not mix a conversion pass with a rewrite pass in one pull request.
- Run the checks of section 5 that apply to your change before you push.
- Push your branch at the end of a work session. Do not leave work only on your machine.
- Follow `Doc: um:guide:coding-guidelines` for all new and changed code.

## 10. Documentation rules

Project documentation is in four LaTeX books in `docs/manual/`. Each book builds to a PDF.
No Markdown file remains in `docs/` except `docs/README.md`. Local `README.md` files next to the code stay Markdown.

| Book | Directory | Content |
| :--- | :-------- | :------ |
| Design Specification (`ds`) | `docs/manual/ds/` | What the design must do |
| Technical Manual (`tm`) | `docs/manual/tm/` | How the design and the flows work |
| User Manual (`um`) | `docs/manual/um/` | How to use the project |
| Changes record (`cr`) | `docs/manual/cr/` | History of the project |

- A label has the form `book:kind:slug`, for example `ds:mod:apb-cdc-bridge`. Labels do not change when text moves.
- A source file cites a label with one line: `// Doc: ds:mod:apb-cdc-bridge`. Use `#` in Python, Tcl, SDC, shell and Make files.
- Cite a label or a symbol name. Never cite a file and line number, a page or a section number.
- Do not put these in a source comment: bead IDs, `GH #` or `PR #` numbers, run names, ISO dates, measured values with units.
- Put history, measurements and rejected alternatives in the books. Keep the contract and the reason in the file.
- Keep source comments inside the budgets in `Doc: um:guide:coding-guidelines` (section "Source comments").
- Do not edit the words inside a `record` environment of the Changes record.
- Write new text in ASD-STE100 style. Use `python tools/docs/ste_check.py <file>` for hints. It cannot prove compliance.
- Check your edit: `python tools/docs/check_doc_labels.py`, `python tools/docs/check_comment_budget.py`
  and `python tools/docs/build_books.py`.
- Authored chapters use `\begin{requirement}{DS-AREA-NNN}` for rules and generated fact tables for ports and parameters.
  Run `python tools/docs/check_requirements.py` and `python tools/docs/gen_fact_tables.py --check`.
  Never edit files under `docs/manual/*/generated/` or `common/generated/`.
- After you edit `docs/manual/common/dictionary.yaml`, run `python tools/docs/gen_glossary.py`.
- To move text from a comment into a book, copy it verbatim first. Then run `python tools/docs/prose_preserve.py` to find lost text.
  Run `python tools/docs/code_equiv.py` to show that no code changed.

## 11. How to look things up

| You want | Do this |
| :------- | :------ |
| A section for a label | `grep -rn '\label{ds:mod:x}' docs/manual`, or search `docs/manual/common/labels.tsv` |
| The contract of a module | Read the header of the module file. Follow its `Doc:` label. |
| The history of a decision | Search the Changes record (`docs/manual/cr/`) |
| A tool defect or caveat | Search the Technical Manual, part "Tool defects and standing caveats" |
| An old `.md` document path | Look it up in `docs/manual/common/path_map.tsv` |
| Who instantiates a module | Search `rtl/` with grep, or use the code graph tool if your agent has one |
| What a command does | `docs/README.md` and the User Manual |

The Changes record describes the past, not the present. For the current state, read the Design Specification
and the Technical Manual. When a document and the RTL disagree, report it. Do not decide alone which one is correct.
