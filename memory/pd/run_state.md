run_id:      pd_20260629_021153
design_name: rv32i_cpu_top
pdk:         sky130A
tool:        LibreLane/OpenLane2-Classic
start_time:  2026-06-29T09:15:44+07:00
last_stage:  signoff (Option C ACCEPTED)

run8_rerun:
  run_id:      pd_20260630_run8
  run_tag:     RUN_2026-06-30_05-37-56
  start_time:  2026-06-30T05:37:56+07:00
  reason:      CodeRabbit finding #2 — add set_driving_cell for honest timing
  change:      sky130_cpu.sdc: added set_driving_cell sky130_fd_sc_hd__buf_4 on all_inputs
  status:      COMPLETE
  log:         /nobackup/sky130_cpu_run8.log
  honest_timing_results:
    setup_wns_nom_tt_ns:   +0.2285   (was +0.366 optimistic before set_driving_cell)
    setup_tns_nom_tt_ps:   0
    hold_r2r_wns_ns:       +0.6191   (0 R2R violations all corners)
    hold_io_wns_nom_tt_ns: -0.2930   (87 paths — block-level artifact, same class as Run 6)
    klayout_drc:           0
    lvs:                   MATCH
    drt_violations:        0         (13 routing iterations)
    power_mw:              88.5
    util_pct:              40.67
    max_tt_marginal:       2 setup violations (WNS -0.188 ns) — nom/FF corners clean

run_dir:     /nobackup/sky130_cpu_runs/RUN_2026-06-30_05-37-56
run_tag:     RUN_2026-06-30_05-37-56

status:
  synthesis:          PASS
  floorplan:          PASS
  placement:          PASS
  cts:                PASS
  routing:            PASS (0 DRT violations after 13 iters)
  spef_extraction:    PASS
  stapostpnr:         WARN (hold I/O violations — block-level artifact; setup nom_tt PASS)
  klayout_drc:        0 (PASS — authoritative foundry DRC)
  netgen_lvs:         MATCH (PASS — "Circuits match uniquely.")
  magic_drc:          27,733,913 (DOCUMENTED TOOL ARTIFACT — see magic_drc_analysis below)
  signoff_overall:    PASS (Option C accepted, Run 8 honest numbers)

config_choice:  run8_honest (CodeRabbit fixes applied)
config_file:    pnr/sky130/cpu/config.json
config_note:    Run 8 config (authoritative sign-off run):
                - MAGIC_DRC_USE_GDS: false
                - EXTRA_GDS_FILES/LEFS/LIBS/SPICE_MODELS: pdk_dir:: portable paths (CR #1)
                - sky130_cpu.sdc: set_driving_cell sky130_fd_sc_hd__buf_4 (CR #2)
                - NO MACROS object
                - Stock drc.tcl (no read_extra_lef patch)

key_metrics:  (Run 8 — RUN_2026-06-30_05-37-56 — AUTHORITATIVE)
  fmax_mhz:              75
  setup_wns_nom_tt_ns:   +0.2285  (honest: was +0.366 without set_driving_cell)
  setup_tns_nom_tt_ps:   0
  hold_r2r_wns_ns:       +0.6191  (0 R2R violations, all corners)
  hold_io_wns_nom_tt_ns: -0.2930  (87 paths — block-level artifact)
  power_mw:              88.5
  util_pct:              40.67
  die_um:                3600x1800
  klayout_drc:           0
  lvs_errors:            0
  magic_drc:             27,733,913 (SRAM artifact — see below)
  antenna_nets:          91 (I/O ports)
  drt_violations:        0
  max_tt_note:           2 setup violations (WNS -0.188 ns) — marginal regression from set_driving_cell

magic_drc_analysis:
  ROOT CAUSE CONFIRMED (2026-06-29):
  Magic DEF mode resolves SRAM instances by searching magic addpath.
  Finds sky130_sram_1kbyte_1rw1r_32x256_8.mag (72,269 lines, full layout).
  Loads all internal SRAM geometry -> 27.7M li.3 (locali spacing) + poly.8/licon.*/diff.tap.3.

  Proof: KLayout DRC=0 on the IDENTICAL 216 MB merged GDS.

  Standalone test result: 27.7M -> 3,626 (nwell.4 DEF+LEF abstract artifacts)
  with read_extra_lef added before read_def in drc.tcl.

  GDS mode investigation (2026-06-30):
  MAGIC_DRC_USE_GDS=true cannot achieve 0: gds write copies SRAM cells via GDS_FILE property.
  Merged GDS in GDS mode = 224 MB (same SRAM geometry, different path to get there).
  Magic DRC in GDS mode reads full SRAM geometry -> li.3 returns.

  Final recommendation:
  - Accept KLayout DRC=0 as authoritative for this SRAM-macro design
  - Upstream LibreLane fix: add read_extra_lef before read_def in drc.tcl DEF+LEF path

macro_views:  (regenerated from Run 8)
  lef:     pnr/sky130/cpu/macro/rv32i_cpu_top.lef
  lib:     pnr/sky130/cpu/macro/rv32i_cpu_top__nom_tt_025C_1v80.lib
  nl_v_gz: pnr/sky130/cpu/macro/rv32i_cpu_top.nl.v.gz
  gds:     /nobackup/sky130_cpu_runs/RUN_2026-06-30_05-37-56/58-magic-streamout/rv32i_cpu_top.gds
  axi4_burst_ports_in_lef: confirmed (arlen, awlen, arburst, awburst, rlast, wlast, arsize, awsize)

staged_files:
  - pnr/sky130/cpu/config.json          (Run-6 validated state restored)
  - pnr/sky130/cpu/constraints/sky130_cpu.sdc
  - pnr/sky130/cpu/macro_placement.cfg
  - pnr/sky130/cpu/macro/rv32i_cpu_top.lef
  - pnr/sky130/cpu/macro/rv32i_cpu_top__nom_tt_025C_1v80.lib
  - pnr/sky130/cpu/macro/rv32i_cpu_top.nl.v.gz
  - design_state.json
  - memory/pd/experiences.jsonl
  - memory/pd/knowledge.md
  - memory/pd/run_state.md

pending:
  - DO NOT COMMIT -- awaiting user authorization
  - User must review staged files and approve commit + PR push
  - PR target: feat/sky130-cpu-drc-lvs-gh103

###############################################################################
# Stage 1 CPU macro REGENERATION (GH #104 fix) — distributed pins
###############################################################################
regen_reason: SoC integration (Stage 2) GRT-0118 congestion traced to CPU
  macro's pin placement: 256/565 pin RECTs (255/403 distinct pins) clustered
  on the TOP edge alone (N=255, S=125, E=20, W=1). Root cause: a pin_order.cfg
  existed in pnr/sky130/cpu/ documenting an intended N/S/E/W split but was
  NEVER wired into config.json (no FP_PIN_ORDER_CFG reference) -- the
  committed macro used LibreLane's default automatic IO placement instead.
  Floorplan/PDN-only SoC-level fixes (macro-edge clearance halo/extension,
  PDN met4 stripe-pitch coarsening) were tried and exhausted (Runs 9, 10)
  before this was approved as the correct fix -- see stage2 SoC run entries
  below for the full diagnosis chain.

regen_fix:
  - Rewrote pnr/sky130/cpu/pin_order.cfg: balanced ~401 total signal bits
    across 4 edges (N=95, S=97, E=113, W=96), grouped AXI4 write->N
    (faces the SoC's flat-logic/crossbar region), AXI4 read->S, APB debug
    +debug_rs1->E, commit+debug_rs2->W.
  - Added to pnr/sky130/cpu/config.json: "FP_PIN_ORDER_CFG": "dir::pin_order.cfg",
    "ERRORS_ON_UNMATCHED_IO": "both" (strict -- catch any signal-name typo
    immediately rather than silently falling back to auto-placement).
  - No RTL change. No timing/logic change expected -- pure IO-placement
    config fix. DRC/KLayout/LVS/timing should re-validate to the same
    Stage-1 result (DRT=0, KLayout DRC=0, LVS=MATCH, nom_tt setup met).

regen_run_attempt1: tag RUN_2026-07-19_16-00-25, tmux sky130_cpu_regen,
  log /tmp/sky130_cpu_regen.log (lost). Launched 2026-07-19T16:00:25.
  CRASHED at step 25-odb-customioplacement:
  "identifier/regex '#================...' requires a direction to be set
  first". ROOT CAUSE: LibreLane's ioplace_parser.parse (odbpy) recognizes
  ONLY direction markers matching regex ^#\s*([NEWS]R?|BUS_SORT) as special
  tokens -- every other '#'-prefixed line (the 40-line rationale header AND
  the inline '# AXI4 ...' group comments) was parsed as an illegal pin regex.
  FIX (2026-07-21): rewrote pnr/sky130/cpu/pin_order.cfg to contain ONLY
  #N/#S/#E/#W direction markers, blank lines, and bare signal names -- zero
  other comment text. All rationale moved to new file
  pnr/sky130/cpu/pin_order.README.md (not read by the parser).
  Verified: all 48 signal names in the new .cfg match rv32i_cpu_top.sv port
  list exactly (grep-diffed against rtl/cpu/rv32i_cpu_top.sv port
  declarations) -- ERRORS_ON_UNMATCHED_IO="both" should not fire.

regen_run_attempt2: tag RUN_2026-07-21_17-54-43, tmux sky130_cpu_regen2,
  log /nobackup/sky130_cpu_regen2.log. Launched 2026-07-21T17:54.
  Progressed cleanly through synth/floorplan/PDN/global-placement (steps
  01-23), reaching step 25-odb-customioplacement -- comment-syntax crash
  from attempt1 CONFIRMED FIXED (parser no longer chokes on '#====').
  BUT step 25 failed with a SECOND, DIFFERENT bug:
    [ERROR] <busname> not found in design but found in config.
  for all 22 multi-bit bus signals (axi_awaddr_o, axi_awlen_o, axi_awsize_o,
  axi_awburst_o, axi_wdata_o, axi_wstrb_o, axi_bresp_i, axi_araddr_o,
  axi_arlen_o, axi_arsize_o, axi_arburst_o, axi_rdata_i, axi_rresp_i,
  apb_paddr_i, apb_pwdata_i, apb_prdata_o, commit_pc_o, commit_insn_o,
  trap_cause_o, debug_rs1_data_o, debug_rs2_data_o, debug_state_o).
  ROOT CAUSE (read librelane/scripts/odbpy/io_place.py + ioplace_parser
  directly): each pin_order.cfg line is compiled as `anchored_regex =
  f"^{pin}$"` and matched via re.match against EVERY top-level DEF bterm
  name. Post-synthesis/floorplan, multi-bit ports appear as individually
  indexed bterms (e.g. "axi_araddr_o[13]", "axi_araddr_o[28]" -- confirmed
  via the companion "not found in config but found in design" errors for
  those exact indexed names). A bare bus base name like "axi_araddr_o"
  anchored as "^axi_araddr_o$" NEVER matches an indexed bterm name -- 0
  bits match, so the whole bus falls into "not in design" AND every one of
  its indexed bits falls into "not in config" simultaneously.
  CONVENTION CONFIRMED from librelane/examples/spm/pin_order.cfg (shipped
  reference example): bus signal "a" is written as "a.*" (trailing .*) so
  the anchored regex "^a.*$" matches "a[0]".."a[N]". Single-bit signals are
  written bare with no suffix (matches the reference's "rst"/"clk"/"x"/"y").
  FIX (2026-07-21): appended ".*" to all 22 multi-bit bus signal names in
  pnr/sky130/cpu/pin_order.cfg; left all 26 single-bit signals unchanged.
  Verified no cross-signal regex collisions (each bus prefix is unique
  enough that "^busname.*$" cannot accidentally match a different signal's
  bterm name).
  regen2 tmux session self-terminated when io_place.py called
  exit(os.EX_DATAERR) (LibreLane flow abort propagated up through `make`);
  no manual kill needed.

regen_run_attempt3: tag RUN_2026-07-21_18-02-11, tmux sky130_cpu_regen3,
  log /nobackup/sky130_cpu_regen3.log. Launched 2026-07-21 18:02, fresh
  full run (bus-signal ".*" fix applied to pin_order.cfg). COMPLETED
  74/74 steps at 2026-07-21T20:18:55 (~2h17m). `make` exited non-zero
  (Error 2) due to LibreLane's own deferred-error summary (Magic DRC count
  + setup/hold violations) -- this is EXPECTED, same pattern as Stage-1
  Run 8 (see signoff_overall note above: "Option C accepted, Run 8 honest
  numbers" required overriding LibreLane's own exit code). Non-zero make
  exit does NOT by itself mean the run is unusable -- see gate-by-gate
  breakdown below.

  GATES CONFIRMED PASS:
    - Step 25 (Odb.CustomIOPlacement): 0 unmatched-in-design / 0
      unmatched-in-config errors. Per-edge pin distribution: N=95, S=97,
      E=113, W=96 (matches the v2 design target exactly -- root-cause
      255/125/20/1 top-edge skew is FIXED).
    - Detailed routing (step 45): 0 DRT violations.
    - KLayout DRC (step 63/65-checker-klayoutdrc): "Check for KLayout DRC
      errors clear." -- 0 errors, authoritative gate PASS.
    - Netgen LVS (step 68/69-checker-lvs): "Check for LVS errors clear."
      -- Circuits match uniquely, PASS.
    - Magic DRC (step 62/64-checker-magicdrc): 27,733,913 errors --
      logged as "deferred" (Checker.MagicDRC's error_on_var defaults to
      quit-the-flow, but LibreLane's deferred-error mechanism lets the
      flow continue to KLayout DRC + LVS regardless; confirmed by reading
      librelane/scripts/odbpy/io_place.py + steps/checker.py directly).
      IDENTICAL documented tool artifact as Stage-1 (SRAM .mag-flatten via
      Magic addpath resolution) -- KLayout DRC=0 on the same geometry is
      authoritative per existing project precedent.

  postPnR STA (step 56, nom_tt_025C_1v80) -- CATEGORIZED (not yet
  accepted/rejected -- pending decision, see below):
    Setup: WNS -0.3991 ns, 1 violated path, 0 of which reg-to-reg.
      Full detail (checks.rpt/max.rpt): Startpoint apb_paddr_i[4] (input
      port) -> Endpoint apb_prdata_o[13] (output port) -- pure
      combinational PORT-TO-PORT path (APB debug read-mux), NOT reg-to-reg,
      NOT even reg-touching. Reg-to-reg worst slack at nom_tt: +3.4075 ns
      (clean, large positive margin).
    Hold: WNS -0.1232 ns, 62 violated paths, 0 of which reg-to-reg.
      Verified exhaustively (awk over min.rpt): every violated path has
      startpoint = an input port (apb_pwdata_i[*]) and endpoint = an
      internal FF -- classic input-to-first-register hold artifact, SAME
      CLASS as Stage-1 Run 6/8's accepted "hold I/O-only" pattern.
    Max Cap violations: 205 (nom_tt). Max Slew violations: 3359 (nom_tt).
      Root cause verified from sta.log report_check_types output: nearly
      all violating instances are named "max_cap<N>"/"ANTENNA_max_cap<N>_*
      /DIODE" with a Liberty max_cap threshold of exactly 0.500000 --
      these are antenna-repair diode/buffer cells with intentionally tiny
      self-referential cap limits (protection cells, not real load-driving
      logic), not violations on macro I/O pins or real internal nets.

  COMPARISON TO STAGE-1 RUN 8 (merged baseline, RUN_2026-06-30_05-37-56,
  PR #110 -- read directly, not relayed):
    Run 8 nom_tt: Hold WNS -0.2930 ns / 87 violations / 0 reg-to-reg
      (documented, accepted). Setup WNS +0.2285 ns / 0 violations (CLEAN).
      Max Cap 196 / Max Slew 3306 -- SAME "ANTENNA_max_cap*/DIODE" pattern,
      SAME 0.500000 threshold, present in the run that is already merged
      and accepted. Regen attempt3 numbers (205/3359) are materially
      identical magnitude -- NOT a new problem introduced by the pin
      redistribution, already implicitly accepted in Run 8's sign-off.
    ONE genuine, quantifiable delta: nom_tt setup went from 0 violations
      (Run 8) to 1 violation (attempt3, -0.399 ns), isolated entirely to
      the APB debug port-to-port path apb_paddr_i->apb_prdata_o. Root
      cause identified: pnr/sky130/cpu/constraints/sky130_cpu.sdc already
      has `set_multicycle_path -setup 2 -from apb_paddr_i -to
      apb_pslverr_o` and `... -to apb_pready_o` (lines 154-157) but NOT
      `-to apb_prdata_o` -- an existing SDC gap. Under Run 8's pin
      clustering the paddr_i->prdata_o wire was short enough to meet
      single-cycle timing incidentally; the balanced 4-edge pin spread
      increases that specific wire's physical distance enough to expose
      the pre-existing gap. Given apb_pready_o already gets 2 cycles
      (i.e. the APB slave FSM already has a wait-state), extending the
      same multicycle exception to apb_prdata_o would very likely be
      protocol-consistent (data is sampled together with pready), not a
      new protocol change -- but this is a timing-exception/verification
      decision, not applied here without explicit direction.

  VERDICT (reported to coordinator, sign-off NOT yet finalized per their
  explicit instruction -- pd.signoff stays false pending their decision):
    The regenerated LEF/GDS/nl.v IS usable for SoC re-integration on the
    metrics that motivated this regen: pin skew fixed (balanced 4-edge
    N95/S97/E113/W96), 0 DRT, KLayout DRC=0, Netgen LVS=MATCH, reg-to-reg
    timing clean at every corner (core CPU function/timing unaffected by
    the pin move). The one new artifact (1 boundary setup violation on an
    APB debug/observability path, not the AXI4 datapath) is small
    (-0.399 ns), isolated, has an identified likely-cheap SDC fix (extend
    the existing pready_o/pslverr_o multicycle pattern to prdata_o), and
    is a standalone-macro boundary-condition artifact that will be
    re-characterized under the real SoC-level SDC in any case (same
    reasoning already applied to the accepted hold I/O-boundary
    artifacts). Recommend: proceed with macro-view installation +
    SoC re-integration; optionally apply the multicycle SDC fix and
    re-run first if bit-for-bit nom_tt setup parity with Run 8 is
    required before calling this final.

regen_next_steps (decision pending coordinator sign-off call):
  1. DRC/LVS gates confirmed hold (same Stage-1 bar) -- DONE.
  2. Pin distribution confirmed genuinely balanced (N95/S97/E113/W96) --
     DONE.
  3. OPEN DECISION: accept the 1 new APB port-to-port setup violation as
     a documented boundary artifact, OR apply the prdata_o multicycle SDC
     fix and re-run once more for parity with Run 8.
  4. Install new macro views into BOTH pnr/sky130/cpu/macro/ (superseding
     committed views) AND pnr/sky130/soc/macro/ (superseding the
     top-edge-pin copy used in failed SoC Runs 8/9/10) -- NOT YET DONE,
     awaiting the decision in (3).
  5. ALSO reposition CPU+SRAM in pnr/sky130/soc/macro_placement.cfg away
     from the die's (20,20) corner -- currently only 20um margin on south
     and west, which would starve the newly-added S/W pin traffic of
     escape room even with balanced pin counts. Give every macro edge
     genuine clearance, not just north.
  6. Redo SoC integration run with new-pinout CPU + SRAM.
  DO NOT COMMIT any of this until the SoC gate + review.

###############################################################################
# Stage 2: Sky130 SoC (GH #104) — pd_20260630_soc_stage2
###############################################################################
stage2_run_id:    pd_20260630_soc_stage2
stage2_design:    soc_top
stage2_pdk:       sky130A
stage2_tool:      LibreLane/OpenLane2-Classic
stage2_start:     2026-06-30T18:35:00+07:00
stage2_last_stage: floorplan (launching)

stage2_run1_failure:
  step:     12 (Odb.SetPowerConnections)
  error:    "Could not find master for cell type 'soc_bus'"
  root_cause: soc_bus.sv missing from SKY130_SOC_SV_FILES (also: axil_to_apb.sv,
              apb_interconnect.sv, apb4_register_bank.sv all missing)
  fix:      Added 4 missing files to SKY130_SOC_SV_FILES in pnr/Makefile

stage2_sv2v_sanity_run2:
  files:          26 SV/V files
  output:         pnr/sky130/soc/soc_top_sv2v.v
  lines:          5550
  clocked_always: 37
  dff_regs:       293
  cpu_blackbox:   yes ((* blackbox *) module rv32i_cpu_top)
  gpu_tieoff:     yes (gpu_irq_o = 1'b0)
  sram_behavioral: yes (reg mem [0:MEM_WORDS-1] x3)
  soc_bus:        yes (module soc_bus present)
  apb4_reg_bank:  yes (module apb4_register_bank present)
  axil_to_apb:    yes (module axil_to_apb present)
  apb_interconnect: yes (module apb_interconnect present)
  all_instantiations_resolved: yes
  exit_code:      0  PASS

stage2_config:
  die:            5000x2400 um
  clock:          13.333 ns (75 MHz)
  cpu_macro:      MACROS object (lef/gds/lib/spice from pnr/sky130/cpu/macro/)
  gpu:            flat tieoff stub (zero cells after synthesis)
  sram:           behavioral (flip-flops, no macro)
  pdn:            met1 followpins + met4 V-stripes + met5 H-stripes + macro ring
  drc_lvs:        RUN_MAGIC_DRC=true (DEF mode), RUN_KLAYOUT_DRC=true, RUN_LVS=true

stage2_run_dir:   /nobackup/sky130_soc_runs/
stage2_run2:
  tmux:     sky130_soc_run2
  log:      /tmp/sky130_soc_run2.log
  launched: 2026-06-30T19:14+07:00
  run_tag:  RUN_2026-06-30_19-14-54
  status:   KILLED (system reboot during step 13 OpenROAD execution)
  failure:  macro_placement.cfg used TYPE name (rv32i_cpu_top) not INSTANCE name (u_cpu)
            AND center coordinates (1820, 920) instead of origin (20, 20)
            -> ManualMacroPlacement: Declared macros not instantiated: * rv32i_cpu_top
            -> step 13 did not produce state_out.json
  step12_warning: u_gif_adapter/axilite_to_axi4 hierarchy warning (benign, step completed)

stage2_run3:
  tmux:     sky130_soc_run3
  log:      /tmp/sky130_soc_run3.log
  launched: 2026-07-18T07:34+07:00
  run_tag:  RUN_2026-07-18_07-34-28
  fixes:    macro_placement.cfg u_cpu 20 20 N (instance name + origin coords)
            Makefile: soc_bus.sv + axil_to_apb.sv + apb_interconnect.sv + apb4_register_bank.sv
  status:   KILLED (system reboot killed process)

stage2_run4:
  tmux:     sky130_soc_run4
  log:      /tmp/sky130_soc_run4.log
  launched: 2026-07-18T08:00+07:00
  run_tag:  RUN_2026-07-18_08-00-40
  fixes:    pdn.tcl: removed duplicate met5/met4 connect in macro_grid (PDN-0186 fix)
            sky130_soc.sdc: replaced remove_from_collection with OpenSTA foreach idiom (STA-0441 fix)
  status:   KILLED (process killed before completing — likely OOM or session restart)

stage2_run5:
  tmux:     sky130_soc_run5
  log:      /tmp/sky130_soc_run5.log
  launched: 2026-07-18T08:38+07:00
  run_tag:  RUN_2026-07-18_08-38-05
  status:   FAILED at step 35 (OpenROAD.GlobalRouting) — GRT-0118
  grt_diagnosis:
    usage: 5,106,272  capacity_derated: 3,663,344  overflow: 139%
    met1_derating: 77.5% (30% global adj + 54% CPU macro footprint)
    blockages: 763,713 instances
    root_cause: die 5000x2400 too small; CPU macro occupies 54% of area;
      right strip only 1360 µm wide, top strip only 560 µm tall;
      43,468 DFFs (32K behavioral SRAM) routing demand far exceeds channel capacity
  post_cts_timing: setup_wns=+0.295ns hold_wns=+0.295ns @ 75 MHz CLEAN

stage2_run6:
  tmux:     sky130_soc_run6
  log:      /tmp/sky130_soc_run6.log
  launched: 2026-07-18T12:17+07:00
  run_tag:  RUN_2026-07-18_12-19-49
  status:   FAILED at step 35 (OpenROAD.GlobalRouting) — GRT-0118
  config_changes:
    DIE_AREA:  [0,0,5000,2400] -> [0,0,7000,3600]  (+2.1x area)
    CORE_AREA: [20,20,4980,2380] -> [20,20,6980,3580]
    PL_TARGET_DENSITY_PCT: 55 -> 45
    GRT_MACRO_EXTENSION: 2 (new — 2 GCell routing clearance around macro)
  grt_diagnosis:
    global_util: 41.9% (FINE — not a global density problem)
    usage_delta: 5.11M (run5) -> 5.13M (run6, barely changed despite 2.1x die)
    root_cause:  LOCAL hotspot from 32K behavioral SRAM DFFs staying clustered
                 regardless of die size; 12.3% stdcell util but local congestion spike
  fix_applied:
    sram_controller_stub.sv  — (*)blackbox(*) AXI4 stub, no DFFs
    macro/sram_controller.lef — 960x797um abstract (2x2 tile footprint)
    macro/sram_controller.gds — synthetic GDS (KLayout Python, pinned met2+met4)
    macro/sram_controller.spice — port-list subckt for LVS
    macro/sram_controller_TT_1p8V_25C.lib — Liberty 140 inputs/50 outputs
    config.json: DIE_AREA reverted to 5500x3000, MACROS added sram_controller,
                 PDN_MACRO_CONNECTIONS added u_sram vccd1/vssd1 mapping
    macro_placement.cfg: added u_sram 3640 20 N
    pdn.tcl: added sram_grid for vccd1/vssd1 macro ring
    Makefile: SKY130_SOC_SV_FILES uses sram_controller_stub.sv not rtl/soc/sram_controller.sv
    sv2v re-run: 5420 lines, 35 clocked always, 279 regs (was 293 before)

stage2_run7:
  tmux:     sky130_soc_run7
  log:      /tmp/sky130_soc_run7.log
  launched: 2026-07-18T15:32 (first attempt — Liberty failure)
  run7_failure1:
    step: 3 (Yosys.GenerateJSONHeader)
    error: "Assert count_id(wire->name) == 0 in kernel/rtlil.cc:2151"
    cause: sram_controller_TT_1p8V_25C.lib used flat pin(name[n]) declarations
           which cause RTLIL wire-name collision during bus expansion
    fix:   Regenerated lib with bus() declarations (bus4/bus8/bus32 types);
           Verified: yosys -p "read_liberty -lib ... ; stat" -> "Imported 1 cell types"
  relaunched: 2026-07-18T15:36:46 (run tag RUN_2026-07-18_15-36-46 — synthesis running)
  config:
    DIE_AREA:  [0,0,5500,3000]
    CORE_AREA: [20,20,5480,2980]
    macros:    rv32i_cpu_top (3600x1800) + sram_controller (960x797)
    sram_approach: hard-macro blackbox (no DFFs in synthesis)
  rationale:
    32K SRAM DFFs removed from synthesis; sram_controller now a 960x797um macro
    placed at (3640,20) — right of CPU. Flat logic region:
      top strip (20,1820)-(5480,2980) = 5460x1160um
      right strip (4620,20)-(5480,1820) = 860x1800um

stage2_sram_block_hardening:
  # Coordinator REJECTED the hollow abstract sram_controller blackbox macro
  # (0-transistor spice, empty-box GDS) — deletes the real 32K-flop memory
  # from sign-off. Correct fix: harden the REAL behavioral rtl/soc/sram_controller.sv
  # as a genuine placed/routed block macro (same pattern as Stage-1 CPU), not
  # a hollow abstraction. This makes the SoC PDN/DRC/LVS certify real memory.
  block_dir:    pnr/sky130/sram/
  design_name:  sram_controller
  mem_words:    1024  (confirmed from soc_top.sv:59 SRAM_MEM_WORDS param, NOT default 4096)
  clock:        13.333 ns (75 MHz), port "clk" (no _i suffix, matches RTL)
  verilog_files: rtl/soc/axi_pkg.sv, rtl/soc/soc_addr_map_pkg.sv, rtl/soc/sram_controller.sv
  synth_parameters: ["MEM_WORDS=1024"]
  makefile_target: librelane-sky130-sram (added, mirrors librelane-sky130-cpu)
  sdc: pnr/sky130/sram/constraints/sky130_sram.sdc (set_driving_cell honest-timing lesson applied)

  run1_attempt1:
    status: FAILED at step 5 (Yosys.GenerateJSONHeader)
    error: "syntax error, unexpected TOK_ID" on soc_addr_map_pkg.sv:24 (import axi_pkg::*;)
    cause: USE_SYNLIG=false -> plain Yosys read_verilog -sv cannot handle
           package-level cross-file "import pkg::*;" (same reason Stage-1 CPU
           needed Synlig)
    fix: USE_SYNLIG: true, SYNLIG_DEFER: false (matches CPU config)

  run1_attempt2:
    status: FAILED at step 23 (OpenROAD.GlobalPlacementSkipIO) — GPL-0302
    error: "Use a higher -density or re-floorplan with a larger core area"
    evidence: NumInstances=195,842, StdInstsArea=2,291,769 um^2 at FP_CORE_UTIL=35%
              -> CoreArea auto-sized to 4.73M um^2 (48.4% actual util, GPL
              suggested min 50%) but PL_TARGET_DENSITY_PCT was set to 30 (too low)
    root_cause_confirmed: design genuinely has ~32,822 flops (matches MEM_WORDS=1024x32)
              PLUS 65,648 $_MUX_ cells from the 1024:1 read mux tree + per-byte
              write-enable muxing -- this IS the same congestion source that broke
              the SoC-level GRT (Run 5/6), now being solved locally inside its own
              block P&R where the router has full freedom.
    fix: FP_CORE_UTIL 35->25 (bigger die), PL_TARGET_DENSITY_PCT 30->40 (headroom
         below GPL's 50% floor), GPL_CELL_PADDING/DPL_CELL_PADDING=4 (CPU precedent)

  run1_attempt3 (tag RUN_2026-07-18_18-51-23) -- COMPLETE, PARTIAL PASS ONLY:
    tmux: sky130_sram_run1 (finished)
    log:  /tmp/sky130_sram_run1.log
    status: Flow completed all 78 stages (3:54:37 runtime) but LibreLane's own
            final exit was ERROR (deferred errors), NOT a clean sign-off.
            CORRECTION: an earlier coordinator relay characterized this run as
            "COMPLETE + signed off" -- that characterization is INACCURATE.
            Direct inspection of the run log and summary.rpt shows real gaps.
    confirmed_clean:
      - DRT (detailed routing): 0 violations
      - KLayout DRC: 0 errors
      - Netgen LVS: Passed (Circuits match)
      - nom_tt_025C_1v80 setup: WNS +0.9113 ns, TNS 0, 0 violations (clean)
      - nom_tt_025C_1v80 hold reg-to-reg: 0 violations (I/O-path-only pattern,
        matches Stage-1 CPU accepted-artifact precedent)
    confirmed_NOT_clean (genuine problems, not tool artifacts):
      - Antenna check FAILED: 640 pin violations, 502 net violations.
        ROOT CAUSE: pnr/sky130/sram/config.json omitted RUN_ANTENNA_REPAIR,
        RUN_HEURISTIC_DIODE_INSERTION, DIODE_ON_PORTS, GRT_ANTENNA_ITERS/MARGIN
        (all present in pnr/sky130/cpu/config.json, missed when authoring the
        sram config). Fixable -- added for Run 2.
      - SS-corner (slow-slow) setup timing GENUINELY FAILS:
        nom_ss_100C_1v60: WNS -6.83 ns, TNS -242.6 ns, 93 violations (61 reg-to-reg)
        max_ss_100C_1v60: WNS -7.70 ns, TNS -294.7 ns, 102 violations (70 reg-to-reg)
        This is NOT the I/O-path artifact pattern -- reg-to-reg paths genuinely
        fail. Suspected root cause: 65,648-cell read-mux tree (1024:1 mux,
        combinational s_rdata = mem[r_idx] with no output register) too deep
        for 75 MHz under slow-slow process. Materially worse than CPU Stage-1
        precedent (0 reg-to-reg violations at all corners, only 2 minor setup
        violations). FIXING THIS WOULD LIKELY REQUIRE REGISTERING THE READ-MUX
        OUTPUT -- an RTL change, which conflicts with the coordinator's
        "harden exactly as-is, no RTL change" directive. FLAGGED for explicit
        decision, not silently fixed or silently accepted.
    summary_rpt_full: pnr/sky130/sram/runs/RUN_2026-07-18_18-51-23/55-openroad-stapostpnr/summary.rpt

  run2 (antenna-repair fix, tag RUN_2026-07-18_22-51-28):
    tmux: sky130_sram_run2 (DIED -- host reboot, no procs, no tmux session
          survived; consistent with prior documented reboot incidents)
    log:  /tmp/sky130_sram_run2.log (lost with the session)
    config_change: added RUN_ANTENNA_REPAIR/RUN_HEURISTIC_DIODE_INSERTION/
      DIODE_ON_PORTS/GRT_ANTENNA_ITERS/GRT_ANTENNA_MARGIN (matches CPU config)
    progress_before_death: reached step 43 (OpenROAD.ResizerTimingPostGRT).
      KEY FINDING: Global routing (step 38) succeeded cleanly -- NO GRT-0118
      recurrence. Confirms diagnosis: standalone block's generous floorplan
      solves the congestion that killed SoC Runs 5/6.
      Antenna progression captured in run dir:
        step 39 (pre-repair CheckAntennas): 2849 pin violations, 1711 net violations
        step 42 (post diode-insertion + repair): 57 pin violations, 55 net
          violations -- 98% reduction from diode insertion + repair antenna flow
      Run directory preserved: pnr/sky130/sram/runs/RUN_2026-07-18_22-51-28/
        (39-openroad-checkantennas/reports/antenna_summary.rpt,
         42-openroad-repairantennas/2-openroad-checkantennas/reports/antenna_summary.rpt)
    still_unresolved: SS-corner reg-to-reg setup timing failure (see above) --
      this fix run does NOT address it.

  run3 (fresh restart of antenna-repair fix, tag RUN_2026-07-19_05-10-55):
    tmux: sky130_sram_run3
    log:  /tmp/sky130_sram_run3.log
    launched: 2026-07-19T05:10:55
    rationale: per feedback_pd_run_strategy.md, fresh full run preferred over
      -f resume when a run dies mid-flow (host reboot). Run 2's partial
      results (GRT clean, antenna 57 pin/55 net after repair) give high
      confidence this config will complete cleanly.
    status: LAUNCHED, running
    expected_runtime: ~4 hours (Run 1 full-flow reference: 3h55m for 78 stages)

  DECISION (user, received during run3): ACCEPT nom_tt sign-off + DOCUMENT
    SS-corner reg-to-reg setup failure as a known limitation. NO RTL change.
    Rationale: consistent with Stage-1 CPU precedent (nom_tt + KLayout DRC 0 +
    LVS MATCH accepted with SS-corner caveats) and indicative-Sky130 scope.

  ###########################################################################
  # sram_controller BLOCK SIGN-OFF RECORD (RUN_2026-07-19_05-10-55)
  ###########################################################################
  run3_result: COMPLETE, 78/78 stages, 5:42:14 runtime.
  run_dir: pnr/sky130/sram/runs/RUN_2026-07-19_05-10-55/

  CLEAN (verified directly, not relayed):
    - DRT (detailed routing): 0 violations (converged at 45-openroad-detailedrouting)
    - KLayout DRC: 0 errors
    - Netgen LVS: Passed -- "Circuits match uniquely" (MATCH)
    - nom_tt_025C_1v80 setup: WNS +0.0446 ns, TNS 0.0000, 0 violations (thin
      margin -- 44.6 ps -- but genuinely clean, 0 reg-to-reg)
    - ALL TT corners (nom/min/max) hold+setup violations that DO exist have
      ZERO reg-to-reg paths -- 100% I/O-path artifacts, matching the accepted
      Stage-1 CPU precedent. Verified via full corner breakdown in
      56-openroad-stapostpnr/summary.rpt (see table below).

  DOCUMENTED LIMITATIONS (per user decision -- accepted, no RTL change):
    1. SS-corner (slow-slow) setup GENUINELY fails -- real reg-to-reg violations:
         nom_ss_100C_1v60: WNS -8.60 ns, TNS -347.56 ns, 169 vio (137 reg-to-reg)
         max_ss_100C_1v60: WNS -9.56 ns, TNS -509.20 ns, 505 vio (473 reg-to-reg)
         min_ss_100C_1v60: WNS -7.48 ns, TNS -258.98 ns, 106 vio ( 74 reg-to-reg)
       Root cause: combinational 1024:1 read mux (assign s_rdata = mem[r_idx],
       65,648 $_MUX_ cells, no output register) too deep for 75 MHz under
       slow-slow process. FIX REQUIRES RTL: register the read-mux output
       (adds 1 cycle read latency) -- out of scope for this hardening pass.
       NEEDED for tape-out; NOT needed for this indicative Sky130 PD sign-off.
    2. Magic DRC = 4293 errors -- SAME documented tool artifact class as
       Stage-1 CPU (Magic DEF-mode geometry search over-counts on large
       flattened designs; KLayout DRC on the identical layout = 0, and
       KLayout is authoritative per project precedent).
    3. Antenna residual = 178 pin violations / 153 net violations (down from
       2849/1711 pre-repair, 94% reduction via RUN_ANTENNA_REPAIR +
       RUN_HEURISTIC_DIODE_INSERTION + DIODE_ON_PORTS).
       CLASSIFICATION (verified directly against antenna.rpt Pin column,
       cross-checked against all sram_controller I/O port names -- zero
       matches): 100% of residual violations are on INTERNAL nets/instance
       pins (synthesis-inserted buffer/repair cells: fanout*, rebuffer*,
       clone*, hold*, max_cap*, plus internal numbered nets like mem[871][19]).
       ZERO residual violations are on top-level I/O ports.
       NOTE: this is the OPPOSITE of "I/O-pin-only" -- it is 100% internal-net,
       which does not meet the "acceptable if I/O-only" bar as originally
       framed. Documented here for accurate record; decision-maker should be
       aware this diverges from the CPU's 81-I/O-port-antenna precedent.
       Given the 94% reduction already achieved and the accepted
       indicative-Sky130 project posture (SS-corner timing already accepted
       as a documented gap), the antenna residual is being carried forward
       as a second documented limitation rather than blocking further
       iteration, but this is flagged explicitly rather than silently
       reclassified as acceptable.

  Full corner timing table (56-openroad-stapostpnr/summary.rpt):
    Corner            Hold WNS  HoldVio(r2r)  Setup WNS  SetupVio(r2r)
    nom_tt_025C_1v80  -0.514ns  127 (0)       +0.045ns   0   (0)
    min_tt_025C_1v80  -0.324ns   21 (0)       +0.758ns   0   (0)
    max_tt_025C_1v80  -0.689ns  327 (0)       -0.645ns  21   (0)
    nom_ss_100C_1v60  -0.567ns   14 (0)       -8.603ns 169 (137)
    min_ss_100C_1v60  -0.265ns    5 (0)       -7.480ns 106  (74)
    max_ss_100C_1v60  -0.807ns   43 (0)       -9.560ns 505 (473)
    (ff corners all clean setup, hold I/O-only, not reproduced here)

  macro_views_installed: (2026-07-19, replacing hollow placeholder)
    lef:     pnr/sky130/soc/macro/sram_controller.lef (68,344 bytes -- real,
             SIZE 2585.030 x 2595.750 um; was 960x797 hollow placeholder)
    lib:     pnr/sky130/soc/macro/sram_controller__nom_tt_025C_1v80.lib
             (118,283 bytes)
    nl_v_gz: pnr/sky130/soc/macro/sram_controller.nl.v.gz (6.8 MB, gzipped
             from 53-openroad-fillinsertion/sram_controller.nl.v, 73.2 MB raw)
    gds:     pnr/sky130/soc/macro/sram_controller.gds (690 MB, LOCAL/gitignored,
             *.gds matched in pnr/.gitignore)
    spice:   pnr/sky130/soc/macro/sram_controller.spice (81.8 MB, 1,171,501
             transistor/subckt lines confirmed -- LOCAL/gitignored)
    power_pins: VPWR/VGND on met4 (standard sky130_fd_sc_hd naming -- NOT
             vccd1/vssd1; this block was synthesized through std cells, not
             a native SRAM macro. config.json PDN_MACRO_CONNECTIONS and
             pdn.tcl corrected accordingly -- single default macro_grid now
             covers both u_cpu and u_sram.)

  ###########################################################################
  # SoC INTEGRATION -- Run 8 GRT-0118 diagnosis + fix (Run 9 launched)
  ###########################################################################
  soc_run8 (tag RUN_2026-07-19_11-13-47): FAILED at step 38 GRT-0118, 22 min
    in. First run with BOTH real macros (CPU + hardened SRAM) installed.
    Coordinator's initial hypothesis (boot_rom = another 32K-flop congestion
    source, same class as sram_controller) was INVESTIGATED AND DISPROVEN:
      - rtl/soc/boot_rom.sv under __pnr__ (which SoC config sets): mem[] array
        is initial-block const-zero with NO writes (read-only ROM, write
        engine only returns SLVERR) -- Yosys will constant-propagate this to
        near-nothing. Matches pre-existing project note: "Boot ROM -> 0 DFFs".
      - Cell report confirms: flat SoC logic has only 10,666 sequential cells
        total (nowhere near what +32K ROM flops would produce).
    "Macro channel squeeze" hypothesis also INVESTIGATED AND DISPROVEN:
      - Standalone GRT diagnostic rerun (loaded pre-GRT ODB, ran
        global_route -congestion_report_file, -allow_congestion) found
        ZERO violations between/near the two macros' 40um gap.
    ACTUAL root cause (evidence-based):
      - Global GRT usage only 11.06% -- NOT a capacity/die-size problem.
      - met4 overflow = 16,417 of 19,960 total overflow (82%) -- single-layer,
        localized hotspot. met4 layer adjustment = 0 (only global 30% applies)
        -> derating is blockage-driven, not adjustment-driven.
      - All 19,863 congestion violations spatially confined to
        X:31-3695, Y:3.5-1811 -- essentially exactly the CPU macro's own
        footprint (20,20)-(3620,1820).
      - CPU macro LEF pin-geometry analysis: 565 total PIN RECTs, 256 on TOP
        edge (y=1800), 126 on bottom, only 20 right / 2 left, 161 interior.
        Hundreds of AXI4-burst + APB-debug + observability signals funnel
        through the CPU's top-edge pin-access channel -> local GRT overflow.
      - Sample violating nets: u_bus.m_awaddr[*]/m_araddr[*] (crossbar
        signals connecting to CPU's top-edge pins).
    Diagnostic method: loaded 33-openroad-resizertimingpostcts/soc_top.odb
      standalone, reran global_route -congestion_iterations 50 -verbose
      -congestion_report_file <path> -allow_congestion to get the per-layer
      summary + per-violation bbox coordinates (19863 entries), parsed with
      python to bucket spatially and confirm the CPU-footprint concentration.
    FIX APPLIED (pure PD, no RTL, no re-hardening, no die regrowth --
      confirmed die growth would NOT help since global usage is only 11%):
      - config.json: GRT_MACRO_EXTENSION 2 -> 10 GCells (more routing
        clearance at macro edges for pin fanout)
      - pdn.tcl: macro_grid halo "10 10" -> "20 20" (more PDN-ring breathing
        room at macro boundary, reduces conflict with dense CPU top-edge
        pin traces)
  soc_run9 (tag RUN_2026-07-19_12-29-42): FAILED, TWO ways:
    - PDN-0179 "Unable to repair all channels" at 12:31:48 (early -- the 20um
      halo broke channel repair)
    - GRT-0118 recurred at 12:54:19 (24m36s in, same congestion pattern)
    Coordinator diagnosis confirmed: clearance knobs (halo, GRT_MACRO_EXTENSION)
    push the macro obstruction boundary out but do not add track capacity to
    the escape throat itself -- cannot fix a fixed-track-pitch bottleneck.
    REVERTED: halo 20->10um, GRT_MACRO_EXTENSION 10->2 (back to working values).

    Refined diagnosis (checked CPU LEF signal-pin layer distribution
    directly): 380 signal pins are on met2, only 3 on met4. So met4
    congestion is NOT signal-pin geometry -- it's PDN/signal CONTENTION:
    met2-pin signals hop met3->met4 for medium/long-distance travel right
    in the throat above CPU's pin-dense top edge, competing there with the
    SoC-level PDN's own met4 vertical stripes (was pitch=100um) plus the
    macro's internal met4 power fabric.
    Considered and REJECTED macro rotation: CPU's 256 pins sit on its
    LONGEST edge (3600um). Rotating 90 deg would compress them onto the
    1800um edge, roughly DOUBLING linear pin density -- would likely worsen
    the hotspot, not fix it. Not attempted.

  soc_run10 (tag RUN_2026-07-19_13-20-34): LAUNCHED, tmux sky130_soc_run10,
    log /tmp/sky130_soc_run10.log.
    FIX: config.json FP_PDN_VPITCH 100->200um (halves SoC-level PDN's met4
    track consumption in the congested region, freeing capacity for signal
    routing, without touching macro geometry). halo/GRT_MACRO_EXTENSION
    reverted to working baseline (10um / 2 GCells).
    DECISION POINT: if this ALSO fails at GRT-0118, per the coordinator's
    explicit framework this should be treated as evidence that floorplan/PDN
    -only fixes cannot resolve it (having now tried: die growth [not
    applicable, usage is 11%], macro-edge clearance, PDN layer-pitch
    coarsening) -- STOP and report the CPU macro regeneration recommendation
    (distributed pins across all 4 edges via Stage-1 pin_order.cfg) rather
    than attempting further floorplan permutations blindly. Do NOT
    regenerate the CPU macro silently -- that is a scope + Stage-1-rework
    decision requiring explicit user approval.

stage2_pending:
  - DO NOT COMMIT until SoC integration gate + coordinator review
  - Real macro views installed; hollow placeholder REMOVED

stage2_asap7_note:
  The ASAP7 SOC_SV_FILES in pnr/Makefile has the SAME latent omission (soc_bus.sv +
  axil_to_apb.sv + apb_interconnect.sv + apb4_register_bank.sv missing). The ASAP7
  SoC sign-off (Run 14) was done via a different flow path not using this Makefile
  target — the omission did not affect the ASAP7 sign-off. Fix needed before any
  future ASAP7 SoC re-run via pnr/Makefile.

###############################################################################
# CPU macro regen FINAL VERDICT (persisted 2026-07-22, coordinator-directed)
###############################################################################
regen_final_verdict: ACCEPTED — macro is USABLE for SoC re-integration.
  Basis (all verified directly against RUN_2026-07-21_18-02-11, not relayed):
    - IO placement (step 25 Odb.CustomIOPlacement): 0 unmatched-in-design /
      0 unmatched-in-config. Balanced N=95/S=97/E=113/W=96 across 401 signal
      pins (root-cause 255/125/20/1 top-edge skew FIXED).
    - Detailed routing: 0 DRT violations.
    - KLayout DRC: 0 errors (authoritative gate).
    - Netgen LVS: MATCH ("Circuits match uniquely").
    - Magic DRC: 27,733,913 — documented SRAM .mag-flatten tool artifact,
      IDENTICAL class to Stage-1 accepted precedent (KLayout DRC=0 on same
      geometry is authoritative).
    - postPnR STA reg-to-reg timing: CLEAN at all 6 corners, both setup and
      hold (nom_tt reg-to-reg setup slack +3.41 ns). The ONLY violations are
      I/O-boundary: 1 setup violation on apb_paddr_i->apb_prdata_o (pure
      combinational APB debug port-to-port path, pre-existing SDC gap —
      apb_pready_o/apb_pslverr_o already have a multicycle exception, prdata_o
      does not; NOT applied, flagged as a cheap follow-up, NOT blocking) and
      62 hold violations all input-port-to-first-register (same accepted
      class as Stage-1 Run 6/8). Max-cap/max-slew violations are 100% on
      antenna-repair diode/buffer cells with a 0.5 pF self-referential
      Liberty threshold — same magnitude as the already-merged Run 8
      baseline (196/3306 there vs 205/3359 here), not a new regression.
  Decision: macro views installed into pnr/sky130/cpu/macro/ (superseding
  the old skewed-pin committed views) — GDS/LEF/LIB/netlist/SPICE all from
  RUN_2026-07-21_18-02-11. NOT committed to git yet — awaiting user review.
  Old files backed up to scratchpad (not tracked) before overwrite.

macro_install_2026-07-22:
  dest_dir: pnr/sky130/cpu/macro/
  gds:     58-magic-streamout/rv32i_cpu_top.gds      (204.7 MB source)
  lef:     60-magic-writelef/rv32i_cpu_top.lef       (126.1 KB source)
  lib:     56-openroad-stapostpnr/nom_tt_025C_1v80/rv32i_cpu_top__nom_tt_025C_1v80.lib (680.9 KB)
  netlist: 53-openroad-fillinsertion/rv32i_cpu_top.nl.v -> gzip -> .nl.v.gz
           (confirmed LAST netlist-writing step -- no later step's config
           references nl.v; grepped all step config.json files for "nl.v",
           zero matches after step 53)
  spice:   66-magic-spiceextraction/rv32i_cpu_top.spice (34.6 MB source)
  LEF sanity check (python3 RECT-boundary classifier against SIZE 3600x1800):
    signal pins: 401, PG pins: 2 (VPWR, VGND -- matches SoC
    PDN_MACRO_CONNECTIONS ".*u_cpu.* VPWR VGND VPWR VGND" mapping)
    edge distribution: N=95  S=97  E=113  W=96  INTERIOR=0
    CONFIRMED: exactly matches the documented post-regen target, old
    255/125/20/1 top-edge skew is gone.

###############################################################################
# SoC floorplan clearance fix (2026-07-22, GH #104, companion to macro regen)
###############################################################################
soc_clearance_fix:
  reason: prior floorplan placed u_cpu at the literal core-area corner
    (20,20) -- only 20 um margin on S/W edges, no real escape room at the
    die/core boundary. Not the GRT-0118 root cause (that was the macro's own
    pin skew, now fixed) but flagged by the coordinator as a real gap that
    should be closed before the next SoC run, belt-and-suspenders.
  changes:
    pnr/sky130/soc/config.json:
      DIE_AREA  [0,0,6300,3200] -> [0,0,6700,3100]
      CORE_AREA [20,20,6280,3180] -> [20,20,6680,3080]
    pnr/sky130/soc/macro_placement.cfg:
      u_cpu  20 20   N  -> u_cpu  150  150 N   (S/W clearance 20->150 um)
      u_sram 3660 20 N  -> u_sram 3900 150 N   (gap 40->150 um; E clearance
                                                 to core boundary 54.97->194.97 um)
    pnr/sky130/soc/pdn.tcl: header comments updated to match (no functional
      change -- file has no hardcoded absolute coordinates, halo stays 10um
      per the Run 9 revert that is already known-working).
  verified: JSON validates; both macro LEF/GDS/LIB/SPICE/nl.v.gz paths
    resolve relative to pnr/sky130/soc/; flat-logic budget grows from
    ~6.3M um^2 to ~7.2M um^2 (more routing room, not less).

###############################################################################
# SoC integration Run 11 (GH #104) -- balanced-pin macro + clearance fix
###############################################################################
soc_run11:
  run_tag:  RUN_2026-07-22_05-15-36
  tmux:     sky130_soc_run11 (detached, DO NOT attach-and-close -- survives
            terminal disconnect but NOT host reboot; log is the durable record)
  log:      /nobackup/sky130_soc_run11.log
  run_dir:  /nobackup/sky130_soc_runs/RUN_2026-07-22_05-15-36/
  launched: 2026-07-22T05:15:36
  launch_cmd: make librelane-sky130-soc  (from pnr/, depends on sky130-soc-sv2v)
  pre-flight: sv2v regen clean (5420 lines, 35 clocked always, matches prior
    baseline exactly), JSON valid, all macro artifact paths resolved, stale
    dead tmux sessions (sky130_soc_run10, sky130_sram_run3 -- empty panes, no
    live process, leftover from a prior reboot) killed before relaunch,
    /nobackup has 725G free, host has 8.1G free RAM at launch.
  THIS IS THE TEST: does the balanced-pin CPU macro (N95/S97/E113/W96) clear
    the GRT-0118 congestion that blocked Runs 5-10 (all of which had the
    255/125/20/1 skewed-pin macro)? Status/result to be appended by whichever
    agent instance observes the GRT step outcome -- if this file is read
    with no result appended below, the run's log at soc_run11.log above is
    the authoritative live source; do NOT re-launch without checking it
    first (fresh full run only after confirming the old one is truly dead,
    per feedback_pd_run_strategy.md).

  RESULT (2026-07-22T05:31:38, observed directly from soc_run11.log, not
  relayed): GRT-0118 STILL FIRED. "OpenROAD.GlobalRouting failed... [GRT-0118]
  Routing congestion too high." make exited Error 2 at step 35/78, 16 min
  after launch (05:29:37 GRT start -> 05:31:37 failure). Literal flow
  verdict: FAIL.

  BUT: standalone re-diagnosis (see below) shows this is NOT a recurrence of
  the old systemic problem -- it is a much smaller, well-localized residual.
  The balanced-pin fix + floorplan clearance fix DID work on the metric that
  mattered (systemic top-edge congestion is gone); what's left is a new,
  narrow, well-understood pinch point.

  standalone_grt_diagnosis (method: read_db of the pre-GRT ODB
  [33-openroad-resizertimingpostcts/soc_top.odb], replayed the exact grt.tcl
  sequence [set_routing_layers -signal met1-met5 -clock met1-met5;
  set_global_routing_layer_adjustment * 0.3 then per-layer [0.99,0,0,0,0,0];
  set_macro_extension 2] using the literal env values from step
  35/config.json, then `global_route -congestion_iterations 50 -verbose
  -allow_congestion -congestion_report_file <path>` via
  `nix-shell --run "openroad -no_init -exit <script>.tcl"`):
    Final congestion report (GRT-0096): Total usage 8.56% (430,395 /
    5,030,527), Total overflow = 82 units (max 1 vertical on met2, 0
    elsewhere). Final usage 3D = 1,508,628. Blockages = 206,008.
    COMPARISON: Run 5 (old floorplan) = 139% overflow / 5.1M usage. Run 8
    (old skewed-pin CPU macro, SAME floorplan family) = 82% derating /
    19,863 violations, ALL spatially confined to the CPU macro's own
    footprint. Run 11 (balanced-pin macro + clearance fix) = 8.56% usage /
    82 violations. This is a >99.5% REDUCTION in violation count and
    conclusively confirms the pin-skew hypothesis was the true root cause
    of Runs 5-10 -- the fix worked on the problem it targeted.
    Residual pattern (all 82 violations, from congestion_report_file, 328
    lines / 82 blocks of 4): 100% at IDENTICAL Y-band 144.9-151.8 um -- a
    single GCell row straddling the CPU macro's NEW south edge (y=150 in
    the post-fix floorplan). X spread ~255-3200 um (nearly the CPU's full
    3600 um width). 100% "Vertical congestion, capacity:0 usage:1
    overflow:1" (a hard per-GCell blockage, not diffuse density -- some
    obstruction, most likely the macro halo [pdn.tcl macro_grid halo
    "10 10"] or macro-extension geometry, fully occupies that one GCell row
    for met2 vertical routing). Net names: u_bus.m_araddr[*] (30),
    m_rdata/m_arlen/m_rresp/m_rvalid/m_rready/m_rlast/m_arvalid/
    xbar_m_arsize/xbar_m_arburst (~20), plus ~30 unnamed nets -- ALL are
    AXI4-READ-CHANNEL signals, exactly matching the CPU's pin_order.cfg
    S-edge assignment ("AXI4 read -> S"). Root cause candidate: the macro
    halo/extension obstruction directly below the CPU's south edge blocks
    the one GCell row every S-edge escape route must cross.
    NOT YET APPLIED (flagged for explicit decision, not executed
    unilaterally, consistent with prior practice on this project):
      1. Increase u_cpu y_origin further (more clearance below S edge --
         current 150um from die edge may still collide with the halo
         geometry right at the boundary row).
      2. Tune/reduce the macro_grid halo specifically at the S edge, or
         bump GRT_MACRO_EXTENSION now that the problem is a single boundary
         row (previous halo/extension bumps in Run 9 failed, but that was
         against the OLD systemic top-edge problem on the skewed macro --
         may behave very differently against this new, narrow, localized
         issue).
      3. Set GRT_ALLOW_CONGESTION=true as a stopgap given total overflow is
         only 82 units / 8.56% usage (near-negligible) -- would let the
         flow proceed into detailed routing to see if DRT resolves these 82
         nets despite GRT's report; untested risk of pushing the problem
         into DRT-stage violations instead.
  VERDICT: literal FAIL (GRT-0118), but root-cause-level PARTIAL SUCCESS --
  the systemic congestion crisis that blocked Runs 5-10 is resolved; a much
  smaller, well-characterized residual remains. Recommend loop_back_to:
  routing (this is attempt 1 of the post-regen phase, well within budget)
  with one of the 3 candidate fixes above, rather than another macro
  re-regen or wholesale floorplan rework -- both are now validated as
  correct in direction.
  Diagnostic artifacts (local, not committed): standalone script
  /tmp/.../scratchpad/grt_diag.tcl, congestion report
  /tmp/.../scratchpad/soc_run11_congestion.rpt (both in this session's
  scratchpad -- regenerate if needed, not persisted to the repo).

###############################################################################
# Run 12 (RUN_2026-07-22_05-45-08) -- GCell-grid-alignment fix applied
###############################################################################
run12_fix_applied:
  macro_placement.cfg: u_cpu/u_sram y_origin 150 -> 207.0 (= 6.9*30, exact
  GRT GCell-grid multiple). Rationale (full writeup now in
  pnr/sky130/soc/macro_placement.cfg header): GRT's GCell grid has origin
  (0,0) and a FIXED 6.9um tile pitch (confirmed by dumping
  [[ord::get_db_block] getGCellGrid] Y-gridlines post-route: ...144.9,
  151.8, 158.7...; 6.9 = 15 x met2 track pitch 0.46, a technology constant).
  u_cpu's old south edge y=150.0 landed INSIDE the tile 144.9-151.8 instead
  of ON a gridline -> that tile straddled the macro boundary -> GRT zeroed
  its entire vertical capacity -> all 82 Run-11 violations were S-edge
  AXI4-read nets forced through that one dead tile. CONTROL TEST proved
  GRT_MACRO_EXTENSION was NOT the cause at that time (0 vs 2, identical 82
  violations, same nets, same bbox) -- ruled out before applying this fix.

run12_result: GRT-0118 STILL fired (flow exit Error 2, step 35, ~15 min in,
  05:45:08 launch -> 06:00:22 failure). Literal flow verdict: FAIL again.
  Coordinator flagged this and asked for re-diagnosis on RUN_2026-07-22_05-45-08
  specifically (in case the north-edge -- CPU height 1800 isn't a 6.9
  multiple, so height + 207 = 2007 also doesn't land on a gridline --
  became the new problem instead).

run12_standalone_diagnosis (same method: read_db of
  33-openroad-resizertimingpostcts/soc_top.odb from RUN_2026-07-22_05-45-08,
  replayed identical grt.tcl env values [RT_MIN/MAX_LAYER met1/met5,
  GRT_ADJUSTMENT 0.3, GRT_LAYER_ADJUSTMENTS 0.99/0/0/0/0/0,
  GRT_MACRO_EXTENSION 2, GRT_OVERFLOW_ITERS 50], then global_route
  -allow_congestion -congestion_report_file):
  PROBE confirmed macro placement took effect exactly as intended:
    u_cpu bbox (DBU): 150000 207000 3750000 2007000 = (150,207)-(3750,2007) um
    u_sram bbox (DBU): 3900000 207000 6485030 2802750
  RESULT: Total overflow dropped from 82 (Run 11) to JUST 3 (Run 12) --
  a further >96% reduction. Usage 8.49% (barely changed, still tiny).
  The 3 residual violations (full congestion_report_file, 12 lines / 3
  blocks): ALL "Horizontal congestion" (met1 direction -- DIFFERENT from
  Run 11's all-"Vertical"/met2 pattern), capacity:0 usage:1 overflow:1 each:
    (1028.1,200.1)-(1035,207)     net608
    (1028.1,207)-(1035,213.9)     u_bus.m_araddr\[23\]
    (1421.4,193.2)-(1428.3,200.1) u_bus.m_arlen\[2\]
  Two of three straddle the NEW y=207 boundary at the same X column
  (1028.1-1035); the third is one tile-row further down at a different X.
  Small, tight, point-like -- not the systemic pattern seen before.

  CONTROL TEST (macro_extension 0 vs 2, everything else identical, on
  THIS run's post-alignment-fix floorplan): with set_macro_extension 0,
  ALL layers report 0/0/0 overflow -- FULLY CLEAN. This is the OPPOSITE
  finding from the Run-11 control test (where extension made zero
  difference) -- confirms GRT_MACRO_EXTENSION's 2-GCell (~13.8um) no-route
  buffer around the macro boundary was exactly consuming the last bit of
  headroom needed to route around net608/m_araddr[23]/m_arlen[2]'s tight
  local pin cluster, now that the systemic grid-misalignment problem no
  longer swamps the picture.

run12_fix_decision: APPLIED. pnr/sky130/soc/config.json:
  GRT_MACRO_EXTENSION 2 -> 0. This is a genuine GRT routing-margin
  parameter (reserved macro-boundary keepout for the global router only),
  NOT GRT_ALLOW_CONGESTION -- detailed routing still enforces real LEF/DRC
  macro geometry regardless of this setting, so this does not mask
  anything; it removes an artificial buffer that the empirical A/B test
  showed was the actual bottleneck. Coordinator explicitly rejected
  GRT_ALLOW_CONGESTION as a "masking" stopgap; this fix was chosen because
  the diagnostic evidence directly supported it (clean 0/0/0 result) and
  it operates on the confirmed root-cause parameter, not a blanket override.

###############################################################################
# Run 13 (launching) -- GRT_MACRO_EXTENSION 2->0 fix, testing for true 0-overflow
###############################################################################
run13:
  tmux:     sky130_soc_run13 (detached)
  log:      /nobackup/sky130_soc_run13.log
  launched: 2026-07-22T06:09:31
  RESULT: GRT-0118 FULLY CLEARED (0/0/0 overflow, all layers -- verified
    directly, "Total wirelength: 3869451 um", 3 successive GRT-0096 reports
    all 0/0/0). Detailed routing: 0 DRT violations (verified directly,
    DRT-0199 progression 202->0). GRT_MACRO_EXTENSION fix CONFIRMED WORKING
    on the real flow, not just the standalone diagnostic. This is the FIRST
    time the Sky130 SoC flow has ever cleared GRT-0118 -- the 6+ run
    blocker is genuinely resolved.
  STOPPED: at step 47/78 (OpenROAD.IRDropReport), 06:41:38, ~32 min in.
    make exited Error 2. This is a REAL, FATAL step failure (verified: full
    "LibreLane will now quit" + flow-summary + "make: *** Error 2" sequence
    present in the log -- NOT a truncated/reboot-killed log; the host
    reboot happened AFTER this, at ~06:45, and is unrelated to why the run
    stopped). No step directories beyond 47 exist in this run
    (RUN_2026-07-22_06-09-37) -- Magic streamout / KLayout DRC / Netgen LVS
    were NEVER REACHED.

###############################################################################
# PSM-0069 / IRDropReport investigation -- CORRECTING A MISCHARACTERIZATION
###############################################################################
psm0069_correction: The coordinator characterized this as "the documented
  benign PSM tap-cell tool artifact (CLAUDE.md + CPU/GPU ASAP7 precedent)"
  and said it was "deferred" / non-fatal. DIRECT VERIFICATION SHOWS THIS IS
  WRONG on every count:
  1. SIGNATURE MISMATCH: the documented ASAP7 precedent
     (docs/PHASE5_RUN_HISTORY.md) is specifically `PSM-0039 Unconnected
     instance TAP_TAPCELL_ROW_*/VDD|VSS` -- tap/body-tie cells, a
     well-understood substrate-tie artifact, on an INDICATIVE ASAP7
     (predictive PDK, no real DRC/LVS) sign-off. OUR case: `PSM-0039
     Unconnected instance u_cpu/VPWR` and `u_sram/VPWR` -- the actual HARD
     MACRO INSTANCES themselves, not tap cells -- PLUS 15,555 `PSM-0038
     Unconnected node` warnings on net VPWR (14,332 on met5, 1,223 on met4),
     confirmed via the full VPWR-grid-errors.rpt (46,671 lines), spread
     UNIFORMLY across the ENTIRE 6700um die width (X 146.5-6488.6, ~1000-
     1400 violations per 500um bucket, no localization to macros or any
     region) -- a completely different, far more severe signature. This is
     a REAL Sky130 (not indicative ASAP7) sign-off target requiring genuine
     DRC/LVS.
  2. NOT DEFERRED: OpenROAD.IRDropReport (librelane/steps/openroad.py:1799)
     is a plain OpenROADStep, not a Checker.* step -- it has NO
     error_on_var/deferred-error mechanism. PSM-0069 raised inside its tcl
     script (irdrop.tcl calling check_power_grid) propagates as a real tcl
     error, which DID fatally abort the flow at step 47/78 in Run 13 --
     confirmed by the complete, clean "LibreLane will now quit" + "make:
     *** Error 2" termination sequence (this is the SAME termination
     signature as every GRT-0118 failure previously handled in this
     campaign, not a truncated/crashed log).
  3. PRE-EXISTING, NOT NEW: byte-identical VPWR-grid-errors.rpt (46,671
     lines) confirmed present in Run 11's PDN generation (step 17) too --
     this defect predates the GCell-alignment and GRT_MACRO_EXTENSION
     fixes entirely. It has silently existed through the WHOLE SoC Stage-2
     campaign; Run 13 is simply the FIRST run to ever get far enough
     (past GRT-0118) to reach the step (IRDropReport) where it becomes
     fatal.
  4. CPU-ALONE IS GENUINELY CLEAN (not "carrying the same artifact"): the
     CPU macro's own standalone IRDropReport
     (RUN_2026-07-21_18-02-11/57-openroad-irdropreport/
     openroad-irdropreport.log) shows ONLY `[INFO PSM-0040] All shapes on
     net VPWR/VGND are connected.` -- a fully clean pass, zero PSM-0038/
     0039/0069. The CPU config also uses the STOCK LibreLane pdn_cfg.tcl
     (no FP_PDN_CFG override), unlike the SoC's custom pdn.tcl. This is a
     SoC-specific PDN construction defect, not a universal/accepted
     tool artifact.

  Given (1)-(4), launching another full production run "expecting it to
  pass through to DRC/LVS" would, per direct evidence, almost certainly
  reproduce the IDENTICAL fatal IRDropReport failure at step 47/78 again --
  nothing about the underlying PDN construction has been fixed. Declined
  to launch on that premise; investigated the actual root cause instead
  (below).

psm0069_hypotheses_tested_and_disproven:
  1. Missing core-level PDN ring for stdcell_grid (our custom pdn.tcl only
     rings the two MACROS via `define_pdn_grid -macro -default` +
     `add_pdn_ring`, unlike stock pdn_cfg.tcl's optional
     FP_PDN_CORE_RING block for a die-perimeter ring). Added
     `add_pdn_ring -grid stdcell_grid -layers {met4 met5} ...` (widths 1.6,
     spacings 1.7, core_offsets 6 -- matching the stock script's own
     FP_PDN_CORE_RING_* defaults, already resolved in env). Tested via a
     genuinely fresh truncated run (`-T OpenROAD.GeneratePDN`, full
     Makefile --skip flag set replicated) -- RUN_2026-07-22_17-55-34.
     RESULT: VPWR-grid-errors.rpt byte-length IDENTICAL (46,671 lines,
     same as before the ring was added). DISPROVEN -- reverted, pdn.tcl
     back to original (diffed clean against pre-edit backup).
     (Note: an earlier attempt to test this via `--last-run -F ... -T ...`
     resume produced STALE cached output, not a real re-run -- confirmed
     by timestamp mismatch; LibreLane's step-skip caching does not appear
     to hash FP_PDN_CFG's file CONTENTS, only the path string. Use a fresh
     `-T <step>` run, not `--last-run -F/-T` resume, to validate any future
     pdn.tcl change.)
  2. Missing VSRC_LOC_FILES (IRDropReport's own warning: "not given a
     value, which may make results... inaccurate"). Checked: CPU's config
     ALSO has VSRC_LOC_FILES unset (None), yet CPU's IRDropReport is fully
     clean (PSM-0040 pass). DISPROVEN -- this variable affects IR-drop
     VALUE accuracy, not the underlying topological connectivity check.

psm0069_still_unknown: The actual root cause of the 15,555-node, die-wide,
  uniform VPWR/VGND disconnection is NOT YET IDENTIFIED. Two hypotheses
  tested and ruled out. Next candidates (NOT yet tested): (a) line-by-line
  diff of our custom pdn.tcl against the stock pdn_cfg.tcl this file
  replaces, focusing on ordering/parameter differences beyond the ring
  (e.g. -spacing vs -spacing values, VSPACING/HSPACING env vars our script
  hardcodes to 2.0 vs stock's 1.7, PDN_CONNECT_MACROS_TO_GRID timing
  relative to grid definition); (b) whether TWO macros (vs CPU's zero, at
  PDN-gen time) somehow fragment the stdcell_grid's own internal
  connectivity via macro-obstruction interaction with -extend_to_core_ring;
  (c) direct interactive OpenROAD investigation of the actual PDN odb
  (17-openroad-generatepdn/soc_top.odb) using a connected-component trace
  (not yet attempted -- would need to determine if check_power_grid
  exposes an API for component-level (not just error-list) diagnosis).
  RECOMMEND: dedicated PDN debugging pass (comparing against stock
  pdn_cfg.tcl output on a trivial 2-macro test design, or consulting
  OpenROAD PDN documentation/issue tracker for this exact signature)
  before any further full-flow relaunch "hoping" it clears -- another
  blind 30-45 min production run without a validated fix would very likely
  just reproduce the identical failure a 3rd time.

psm0069_pending: DO NOT launch another full production SoC run assuming
  this will resolve on its own. DO NOT skip OpenROAD.IRDropReport to force
  through to DRC/LVS without an explicit, informed decision -- doing so
  risks a false-positive KLayout DRC/Netgen LVS "pass" on a design with a
  genuinely broken power grid (LVS checks netlist topology match, not
  exhaustive physical PDN connectivity/opens the way PSM does).

###############################################################################
# PSM-0069 hypothesis 3 (coordinator-directed): remove add_pdn_ring around
# macros entirely, matching stock pdn_cfg.tcl exactly -- PARTIALLY CONFIRMED
###############################################################################
premise_check: coordinator's message asserted "CPU-alone has ZERO child
  macros, so stock never exercised the macro-grid path." VERIFIED FALSE:
  CPU's own Stage-1 P&R has 10 internal SRAM hard-macro instances
  (u_core.u_icache/u_dcache tag+data SRAMs, macro_placement.cfg confirms),
  and its GeneratePDN log shows `[INFO PDN-0001] Inserting grid: macro -
  u_core.u_dcache...` fired 10 times using the STOCK script's macro-grid
  handling (define_pdn_grid -macro -default + add_pdn_connect ONLY -- no
  add_pdn_ring, no extra straps) and still achieves full PSM-0040 clean.
  This means the stock "connect-only, no ring" pattern is PROVEN to work
  with real macros present -- directly supporting (not contradicting) the
  "remove our custom ring" hypothesis, which was already in progress being
  tested when this message arrived.

fix_applied_test3: removed `add_pdn_ring -grid macro_grid ...` from
  pnr/sky130/soc/pdn.tcl, keeping ONLY `define_pdn_grid -macro -default
  -name macro_grid -halo "10 10"` + `add_pdn_connect -grid macro_grid
  -layers "met4 met5"` -- exact match to stock pdn_cfg.tcl's macro-grid
  handling. Validated via a genuine fresh -T OpenROAD.GeneratePDN run
  (RUN_2026-07-22_18-16-30, full Makefile --skip flags replicated).

RESULT: MAJOR, MEASURABLE, PARTIAL FIX.
  - Total VPWR-grid-errors.rpt: 46,671 lines -> 22,155 lines (52.5%
    reduction).
  - u_cpu: FULLY FIXED. `PSM-0039 Unconnected instance u_cpu/VPWR|VGND` no
    longer appears anywhere in the log -- zero violations attributable to
    the CPU macro.
  - u_sram: STILL FULLY BROKEN. `PSM-0039 Unconnected instance
    u_sram/VPWR` and `u_sram/VGND` both still present. ALL 22,155 remaining
    "Unconnected node" violations are spatially confined to EXACTLY
    u_sram's footprint (X: 3910.33-6485.03, matching u_sram's placed
    bbox 3900-6485.03 to the micron) -- ZERO violations anywhere else on
    the die (confirmed via X-histogram). Y-distribution is UNIFORM across
    u_sram's ENTIRE height (237.9-2802.75, ~566 violations per 200um
    bucket, no partial-band localization) -- this reads as u_sram's WHOLE
    internal PDN mesh being disconnected from the outside grid, not a
    partial/edge-only gap.
  - met5:met4 violation ratio ~90:10, consistent with the pre-fix ratio --
    the SAME underlying disconnection MECHANISM, just now isolated to one
    macro instead of two.
  - Both macros' grids DID insert cleanly (`PDN-0001 Inserting grid:
    macro_grid - u_cpu` / `- u_sram`, both present, no per-grid warnings)
    and PDN_MACRO_CONNECTIONS regex matched both instances correctly
    (".*u_cpu.* matched with u_cpu" / ".*u_sram.* matched with u_sram") --
    ruled out a config/pattern-matching or grid-instantiation failure.
  - Checked and ruled out: LEF pin-name collision (both LEFs have exactly
    1 PIN VPWR + 1 PIN VGND block, same as CPU); pin edge-margin
    (SRAM's rightmost stripe is 56.26um from its right edge, CPU's is
    56.51um from its edge -- essentially identical, not a distinguishing
    factor).
  - STILL UNKNOWN: why u_sram's macro-grid connect succeeds structurally
    (grid inserts, PDN_MACRO_CONNECTIONS matches) but produces zero actual
    via-stitching to the outside mesh, while the IDENTICAL mechanism fully
    connects u_cpu. Leading unexplored candidates: (a) SRAM's much taller
    footprint (2595.75um vs CPU's 1800um) leaves only 277um of core
    headroom above it (vs CPU's 1073um) -- possibly not enough room for
    the -extend_to_core_ring stripe-routing mechanism to properly wrap
    around/connect at the top; (b) SRAM may need its own NON-default,
    instance-specific `define_pdn_grid -macro -instance u_sram ...` (richer
    than the shared "-default" macro_grid both macros currently use) with
    explicit straps/ring scoped ONLY to u_sram (leaving u_cpu's now-working
    ring-less default grid untouched) -- NOT YET TESTED.
  CURRENT STATE: pdn.tcl LEFT WITH THE RING REMOVED (net improvement kept,
  no observed downside) pending the next investigation round. NOT full
  PSM-0040 clean yet -- do not launch the full production run.
  Per coordinator's own instruction ("if this hypothesis is ALSO wrong,
  stop and report back... make a scope call together"): this hypothesis
  was PARTIALLY right (fixed half the problem, cleanly and completely, for
  one of the two macros) rather than wrong -- reporting back with this
  isolated, concrete, ODB-verified evidence rather than guessing again at
  the SRAM-specific mechanism.

=======================================================================
openram_sram4k_subtask (GH #104, sub-task launched 2026-07-22, branch
feat/sky130-soc-drc-lvs-gh104):

goal: Compile a NEW OpenRAM sky130 SRAM hard macro, 1024 words x 32 bits
  (4 KB / 32,768 bits), 1RW+1R ports, to REPLACE the behavioral SRAM /
  the prior custom-hardened composite sram_controller macro (which hit
  the still-unresolved u_sram PSM-0040 PDN-stitching failure documented
  in the section above this one). Rationale: a raw OpenRAM macro has a
  standard PG abstract already proven connectable (rv32i_cpu_top's 10
  internal OpenRAM SRAMs are PSM-0040 clean).

env:
  OpenRAM repo:  /home/neuromorphic/Downloads/Github/OpenRAM (stable
                 branch, tag/commit ea15a814, OpenRAM v1.2.49)
  work dir:      /nobackup/openram_sky130_4kb/  (config + logs + output;
                 GDS/spice stay here, never copied into the git repo)
  project config staged (uncommitted): pnr/sky130/soc/openram_sram4k/
  config used:   /nobackup/openram_sky130_4kb/config_sky130_sram_4kbyte_1rw1r_32x1024_8.py
    word_size=32, num_words=1024, write_size=8, num_rw_ports=1,
    num_r_ports=1, num_w_ports=0, tech_name=sky130,
    nominal_corner_only=True, route_supplies=ring, check_lvsdrc=True,
    uniquify=True, output_name=sky130_sram_4kbyte_1rw1r_32x1024_8
    (singular "kbyte" -- matches installed sky130_sram_macros convention;
    NOTE the repo's own macros/sram_configs/sky130_sram_4kbyte_1rw1r_32x1024_8.py
    stock example produces "4kbytes" plural via sky130_sram_common.py's
    format string -- our config intentionally overrides to match the
    installed-library naming convention instead).

BLOCKER FOUND (netlist_only=True dry run, ~1 min): sky130 tech in this
  OpenRAM checkout has NO gds_lib/ or sp_lib/ under technology/sky130/ --
  the hand-crafted hard primitive cells (bitcell, 2-port dp_cell, sense
  amp, etc. -- "sky130_fd_bd_sram__*") that OpenRAM's sky130 port depends
  on are simply absent from this repo clone. AssertionError in
  compiler/base/design.py:44 building bitcell_2port: "Custom cell pin
  names do not match spice file: [...] vs []" (empty = file not found).
  This affects 1-port AND 2-port configs equally (both need hard cells
  from the same missing library).

ROOT CAUSE + FIX (found in OpenRAM's own Makefile, documented + official):
  targets `sky130-pdk` + `sky130-install` populate technology/sky130/{gds_lib,
  mag_lib,sp_lib,...} by cloning:
    - https://github.com/vlsida/sky130_fd_bd_sram.git (the actual hard
      bitcell/analog cell library, ~1.3 MB, pinned commit dd642569...)
    - https://github.com/google/skywater-pdk.git (meta-repo) + 2 scoped
      submodules: libraries/sky130_fd_pr/latest (~114 MB) and
      libraries/sky130_fd_sc_hd/latest (~217 MB) -- only need one std
      cell (dlxtn_1) from the latter, but submodule init pulls the whole
      per-cell layout tree.
    - `ciel enable --pdk sky130 <pinned commit e8294524...>` (2022.07.29,
      OLDER than the project's own ~/.volare sky130A version) into
      PDK_ROOT.
  Used an ISOLATED PDK_ROOT=/nobackup/openram_sky130_4kb/pdk_root for all
  of this -- deliberately NOT the project's shared ~/.volare (which is
  load-bearing for the already-signed-off CPU macro + SoC PnR runs) and
  NOT ~/.ciel -- to avoid any risk of corrupting/version-skewing the
  project's existing verified PDK install. Network access confirmed
  working (git ls-remote succeeded for both repos).

STATUS AS OF LAST UPDATE: `make PDK_ROOT=/nobackup/openram_sky130_4kb/pdk_root
  sky130-pdk` launched in background (log:
  /nobackup/openram_sky130_4kb/setup_sky130_pdk.log), cloning skywater-pdk
  submodules (sky130_fd_pr/latest, sky130_fd_sc_hd/latest). Next steps once
  that completes: `make PDK_ROOT=... sky130-install` (clones sky130_fd_bd_sram,
  builds gds_lib/sp_lib/mag_lib), then re-run the netlist_only dry run to
  confirm the bitcell_2port pin-match error clears, THEN launch the full
  GDS+DRC+LVS compile (config_sky130_sram_4kbyte_1rw1r_32x1024_8.py) in a
  detached tmux session logging to /nobackup, per long-run instructions.

If resuming this sub-task fresh: check
  /nobackup/openram_sky130_4kb/setup_sky130_pdk.log and
  /nobackup/openram_sky130_4kb/setup_sky130_install.log (if it exists) for
  completion, then tmux ls for a session named openram_sram4k.

UPDATE (same session, continued): blocker RESOLVED. `make sky130-pdk` +
  `make sky130-install` (isolated PDK_ROOT=/nobackup/openram_sky130_4kb/pdk_root)
  both completed clean (~5 min total: skywater-pdk scoped submodules
  ~330 MB, ciel sky130A pinned e8294524... PDK, sky130_fd_bd_sram hard
  cell library ~1.3 MB -- all populated technology/sky130/{gds_lib,sp_lib,
  mag_lib,maglef_lib,lvs_lib} in the OpenRAM checkout). Re-ran the
  netlist_only dry run: PASSED clean (594s / ~10 min for submodule
  construction, exit 0). Confirmed generated Verilog interface:
  ADDR_WIDTH=10, NUM_WMASKS=4, DATA_WIDTH=32, ports
  clk0/csb0/web0/wmask0[3:0]/addr0[9:0]/din0[31:0]/dout0[31:0] (RW) +
  clk1/csb1/addr1[9:0]/dout1[31:0] (R) -- exactly matches the installed
  32x256/32x512 macro convention, just ADDR_WIDTH 8->10.

Launched the FULL run (GDS+DRC+LVS, check_lvsdrc=True, no netlist_only) in
  a detached tmux session `openram_sram4k` (window 0), logging to
  /nobackup/openram_sky130_4kb/full_run.log. Config:
  /nobackup/openram_sky130_4kb/config_sky130_sram_4kbyte_1rw1r_32x1024_8.py
  (staged copy also at
  pnr/sky130/soc/openram_sram4k/config_sky130_sram_4kbyte_1rw1r_32x1024_8.py,
  UNCOMMITTED per instructions). Uses OpenRAM's bundled miniconda tools
  (magic 8.3.363, netgen 1.5.253, ngspice) via default use_conda=True --
  same toolchain that just successfully built the primitive library, so
  left as-is rather than swapping to the nix analog devshell's newer
  versions (8.3.489/1.5.278) to avoid a mid-flight tool-version change.

If resuming: `tmux attach -t openram_sram4k` or check
  /nobackup/openram_sky130_4kb/full_run.log for progress /
  OPENRAM_RUN_EXIT_CODE. Output macro directory (once done):
  /nobackup/openram_sky130_4kb/macro/sky130_sram_4kbyte_1rw1r_32x1024_8/
  (GDS/spice/lef/lib/verilog/lvs report -- GDS+spice stay local/nobackup
  only, never committed; lef+verilog+lib are candidates for staging under
  pnr/sky130/soc/macro/ once DRC/LVS clean, per pnr/.gitignore convention
  used for the CPU macro).

=======================================================================
UPDATE 2026-07-23: FULL RUN DIED -- ROOT CAUSE = HOST REBOOT (coordinator
  report, verified: `uptime -s` = 2026-07-23 17:49:42; the openram_sram4k
  tmux session was a fresh post-reboot shell with no running process;
  /nobackup/openram_sky130_4kb/full_run.log was empty, no
  OPENRAM_RUN_EXIT_CODE ever written). NOT a /tmp disk-full crash per se
  at the time of death (root fs was near-full generally -- 91% used,
  11 GB free -- but the coordinator confirmed disk held 9.9 GB free
  throughout and temp peaked ~650 MB; the reboot, not ENOSPC, killed the
  process). ~7 hours lost, almost entirely inside the check_lvsdrc=True
  magic-extraction step (run_ext.sh) for LVS -- the actual GDS/LEF layout
  construction itself is comparatively fast.

TWO FIXES APPLIED before relaunch:
  1. Scratch relocation (user directive, defense in depth against the
     91%-full root fs regardless of reboot-vs-disk causality): added
     `openram_temp = "/nobackup/openram_sky130_4kb/temp"` to the config.
     OPTS.openram_temp defaults to /tmp when unset -- that is what put the
     ~650 MB of magic .ext scratch files on the crowded root fs. Now
     pinned to /nobackup (711 GB free). Created the temp dir up front.
  2. VIEWS-FIRST decision: split into two configs.
     - config_sky130_sram_4kbyte_1rw1r_32x1024_8_views.py:
       check_lvsdrc=False, openram_temp on /nobackup. This is what's
       running NOW. Rationale: the multi-hour magic-extraction LVS step
       is NOT the GH #104 Stage-2 gate -- the authoritative check is the
       SoC-level Magic/KLayout DRC + Netgen LVS run once this macro is
       integrated (independently re-verifies the GDS/SPICE). Getting
       GDS/LEF/LIB/SPICE/.v out fast unblocks both RTL verification
       (soc_all SRAM_SKY130 branch needs the .v model) and PD
       integration, which were both blocked on this build.
     - config_sky130_sram_4kbyte_1rw1r_32x1024_8.py: unchanged
       check_lvsdrc=True, ALSO given openram_temp=/nobackup now, kept for
       a SEPARATE non-blocking background DRC/LVS pass launched only
       after the views land. Expected to take many hours and may be
       reboot-killed again -- accepted, since it is not the gate.

Relaunched in a FRESH detached tmux session `openram_sram4k` (old session
  killed -- post-reboot it was a dead shell) at 2026-07-23T17:55:26,
  logging to /nobackup/openram_sky130_4kb/views_run.log (reboot-survivable
  path; watch for OPENRAM_VIEWS_RUN_EXIT_CODE=). PID at launch: 14687.

If resuming: `tmux attach -t openram_sram4k`, or tail
  /nobackup/openram_sky130_4kb/views_run.log. Once views land, stage
  lef/lib/verilog under pnr/sky130/soc/macro/ (GDS/spice stay local per
  pnr/.gitignore), report interface + paths, THEN launch the separate
  check_lvsdrc=True background DRC/LVS pass using
  config_sky130_sram_4kbyte_1rw1r_32x1024_8.py (non-blocking).

=======================================================================
CORRECTION 2026-07-23 (coordinator-verified, addresses two inaccuracies
above): 

(a) ROOT CAUSE CLARIFICATION: the ~7h loss on the check_lvsdrc=True run
  was caused SOLELY by a HOST REBOOT (uptime -s = 2026-07-23 17:49:42).
  Disk space was NEVER the problem -- root fs held 9.9-11 GB free
  throughout, and the magic-extraction temp dir peaked at only ~650 MB.
  Do NOT read the earlier "91%-full root fs" framing above as the cause
  of the crash; it was cited only as a hygiene concern (user directive to
  keep scratch off a crowded "/"), not as what killed the run. The real
  mitigation for reboot-loss risk is the shortened, non-blocking
  views-first pass (check_lvsdrc=False) -- not the temp relocation.

(b) THE `openram_temp = ...` CONFIG-FILE KEY DOES NOT WORK in this
  OpenRAM version -- it was silently ignored on the views run (verified:
  /tmp/openram_neuromorphic_14687_temp grew to 37 MB while
  /nobackup/openram_sky130_4kb/temp stayed empty). Root-caused via direct
  interpreter testing: compiler/globals.py's init_openram() calls
  setup_paths() BEFORE read_config(). setup_paths() checks
  `OPTS.openram_temp == "/tmp"` (still true at that point, since config
  hasn't loaded yet) and does `OPTS.openram_temp += tempdir`, which is an
  attribute SET that adds "openram_temp" to OPTS's instance __dict__.
  read_config()'s generic config-copy loop only applies a config key
  `if k not in OPTS.__dict__` -- already false for openram_temp by then,
  so the config file's value is discarded every time, unconditionally.
  Was NOT an issue for the currently-running views pass (harmless: low
  peak usage, plenty of root-fs headroom) and was intentionally left
  running rather than interrupted.
  CORRECT MECHANISM (verified working via direct test): the OPENRAM_TMP
  environment variable, exported BEFORE the python3 process starts (it's
  read once at options.py class-body eval time, i.e. first import of
  openram.options in that process):
    export OPENRAM_TMP=/nobackup/openram_sky130_4kb/temp
  Confirmed empirically: with this env var set, OPTS.openram_temp
  resolves to exactly /nobackup/openram_sky130_4kb/temp/ (no /tmp
  fallback, no per-pid subdir needed since num_threads=1 and the value no
  longer literally equals "/tmp"). init_paths()/purge_temp() clears any
  stale contents at the start of each run, so reuse across sequential
  runs is safe without a per-pid subdir.
  Both config files' in-file `openram_temp = ...` lines were removed and
  replaced with a comment pointing at OPENRAM_TMP. The upcoming separate
  check_lvsdrc=True DRC/LVS pass MUST be launched with
  `export OPENRAM_TMP=/nobackup/openram_sky130_4kb/temp` in the shell
  before invoking python3/sram_compiler.py -- verify empirically after
  launch (check which dir actually grows) rather than assuming it took.

=======================================================================
UPDATE 2026-07-24: OpenRAM SRAM macro RE-INTEGRATED into the SoC PnR flow
(reverses Option C). Views run (check_lvsdrc=False) SUCCEEDED:
OPENRAM_VIEWS_RUN_EXIT_CODE=0, 190 min wall time, no reboot hit it this
time. Output: /nobackup/openram_sky130_4kb/macro/sky130_sram_4kbyte_1rw1r_32x1024_8/
(.gds 36.2MB, .lef, .v, .sp 4.0MB, .lvs.sp, _TT_1p8V_25C.lib, datasheet).

Interface confirmed exactly as predicted from the dry run: clk0/csb0/web0/
wmask0[3:0]/addr0[9:0]/din0[31:0]/dout0[31:0] (RW port 0) + clk1/csb1/
addr1[9:0]/dout1[31:0] (R port 1); NUM_WMASKS=4, DATA_WIDTH=32,
ADDR_WIDTH=10, RAM_DEPTH=1024. rtl/soc/sram_controller.sv's existing
`ifdef SRAM_SKY130` branch (already written by rtl-design-orchestrator
against this exact interface) needed NO changes -- instantiates
`sky130_sram_4kbyte_1rw1r_32x1024_8 u_sram_macro (...)` with matching
port names, no USE_POWER_PINS (PG done at PD time).
LEF SIZE = 701.64 x 673.335 um (confirmed) -- ~14x smaller area than the
abandoned composite sram_controller macro (2585 x 2595 um). PG pins
vccd1 (met3+met4, USE POWER, SHAPE ABUTMENT) / vssd1 (met3+met4, USE
GROUND) -- confirmed via direct LEF inspection, full perimeter ring on
BOTH layers (not just one).

BUG FOUND + FIXED: the OpenRAM-generated LEF declared
`UNITS DATABASE MICRONS 2000 ;` while every other LEF in this flow
(tech LEF, std cell LEF, CPU macro LEF, and the REFERENCE installed
sky130_sram_1kbyte_1rw1r_32x256_8.lef) uses 1000. ODB/OpenROAD REJECTS
("[ODB-0292] LEF data ... is discarded due to errors") any LEF whose
DATABASE MICRONS factor exceeds the tech LEF's. Confirmed safe fix (zero
precision loss: grepped for any coordinate with >3 decimal places in the
LEF -- zero matches, i.e. every value is already <=1nm-grid, so 2000->1000
is a pure header fix, no rescaling needed). Patched both the staged
pnr/sky130/soc/macro/*.lef copy and the canonical /nobackup OpenRAM
output copy. Worth adding to memory/pd/knowledge.md as a general OpenRAM
sky130 macro integration gotcha -- likely affects any future OpenRAM
sky130 macro compiled with this OpenRAM version/checkout.

STAGING (done, uncommitted): pnr/sky130/soc/macro/
  sky130_sram_4kbyte_1rw1r_32x1024_8.{lef,v} + _TT_1p8V_25C.lib copied in
  (committed-class, matching CPU macro convention). .gds/.sp copied in
  too (needed on disk for the flow to run) but stay LOCAL-ONLY --
  pnr/.gitignore updated: added `!sky130/soc/macro/sky130_sram_4kbyte_1rw1r_32x1024_8.lef`
  + `.v` exceptions (exact filename, not wildcard, so the ABANDONED
  composite sram_controller.lef in the same directory stays correctly
  ignored) and added `*.sp` to the blanket-ignore list (OpenRAM's default
  spice extension, alongside the existing `*.spice`). Verified all 5
  files' ignore status individually via `git check-ignore -v`.

RTL/SYNTH INTEGRATION:
  - New file pnr/sky130/soc/sky130_sram_4kbyte_1rw1r_32x1024_8_stub.sv:
    (* blackbox *) stub matching the OpenRAM .v port list exactly
    (mirrors the rv32i_cpu_top_stub.sv convention).
  - pnr/Makefile SKY130_SOC_SV_FILES: added the new stub file (before
    rtl/soc/sram_controller.sv, which stays the REAL RTL -- only the
    grandchild SRAM primitive is blackboxed, not sram_controller itself).
  - sv2v invocation: added `--define=SRAM_SKY130` (alongside the existing
    `--define=__pnr__`) so the ifdef branch resolves to the hard-macro
    path instead of the 32K-flop behavioral array.
  - Regenerated soc_top_sv2v.v (`make sky130-soc-sv2v`): 5622 lines, 37
    clocked always blocks, 294 reg decls (down from the old
    Option-C/behavioral count -- the 32K-flop array is gone).

CONFIG.JSON CHANGES:
  - VERILOG_DEFINES: added "SRAM_SKY130".
  - MACROS: added sky130_sram_4kbyte_1rw1r_32x1024_8 entry (gds/lef/lib/
    spice paths under dir::macro/).
  - PDN_MACRO_CONNECTIONS: added
    ".*u_sram_macro.*  VPWR VGND vccd1 vssd1"
    *** FIELD ORDER CORRECTED FROM FIRST DRAFT *** -- read
    set_global_connections.tcl directly rather than trusting the
    coordinator's phrasing or the existing CPU entry (which is
    order-ambiguous since CPU's own pin names happen to equal the net
    names, VPWR/VGND either way -- a degenerate case that would have
    masked a field-order bug). Confirmed the real format is
    `<instance_regex> <power_NET> <ground_NET> <power_PIN> <ground_PIN>`,
    NOT pin-then-net. Original draft had this backwards
    (".*u_sram_macro.*  vccd1 vssd1 VPWR VGND") -- would have silently
    tied the wrong nets to the wrong pins, exactly the class of bug that
    caused the old PSM-0069 wall. Caught and fixed BEFORE running PDN
    generation, not after a failure.

MACRO_PLACEMENT.CFG: added
  `u_sram.u_sram_macro   4209.0   207.0 N`
  Instance name CONFIRMED (not guessed) via a standalone Yosys.Synthesis-
  only probe run (tag SRAM_MACRO_SYNTH_PROBE, ~90s) grepping the resulting
  netlist for the macro cell -- SYNTH_HIERARCHY_MODE=flatten uses Yosys's
  default DOT hierarchy separator (`\u_sram.u_sram_macro `), NOT the slash
  convention that applies under SYNTH_HIERARCHY_MODE=keep (a documented
  pitfall from an earlier GPU PD session, memory note
  project_gpu_pd_macro_path_separator.md -- confirmed here that it does
  NOT apply to this flatten-mode SoC flow). x_origin=4209.0=6.9*610
  (GCell-grid-aligned, same discipline as CPU's y=207.0=6.9*30);
  y_origin=207.0 (same GCell row as CPU, places macros side-by-side).
  459 um clearance from CPU's right edge (3750), 1769.36 um clearance to
  core right edge (6680) -- footprint is 701.64 x 673.335 um, ~14x
  smaller than the old composite macro so clearance is trivial by
  comparison to every prior GH #104 floorplan iteration.

PDN.TCL: kept the existing stock ring-less `-macro -default` grid
  (proven on CPU) UNCHANGED structurally; ADDED
  `add_pdn_connect -grid macro_grid -layers "met3 met4"` alongside the
  existing "met4 met5" connect, since the SRAM macro's vccd1/vssd1 pins
  have PORT rects on BOTH met3 and met4 (confirmed via direct LEF
  inspection) -- CPU has no met3 PG pins so this connect is a no-op for
  u_cpu, purely additive for u_sram.

PDN VALIDATION (fast loop, `-T OpenROAD.GeneratePDN`, tag
  SRAM_MACRO_PDN_PROBE): FIRST REAL ATTEMPT after fixing the LEF-units
  bug -- CLEAN. Full log grep for "PSM|nconnected|violation" returns
  exactly two lines:
    [INFO PSM-0040] All shapes on net VPWR are connected.
    [INFO PSM-0040] All shapes on net VGND are connected.
  Zero violations, both macros. (First attempt before the LEF fix failed
  at Floorplan with [ODB-0292] LEF data discarded -- caught and fixed
  before ever reaching PDN generation.)

LAUNCHED (both detached tmux, both 2026-07-24T05:27):
  1. `sky130_soc_full` tmux session -> `make librelane-sky130-soc`
     (full flow: GRT -> DRT -> Magic/KLayout DRC -> Netgen LVS), log
     /nobackup/sky130_soc_full_run.log, watch for
     SOC_FULL_RUN_EXIT_CODE=. Run dir will land under
     /nobackup/sky130_soc_runs/RUN_<timestamp>/ per the existing symlink
     convention. NON-BLOCKING relative to the DRC/LVS macro pass below.
  2. `openram_sram4k_drclvs` tmux session -> re-ran
     config_sky130_sram_4kbyte_1rw1r_32x1024_8.py (check_lvsdrc=True) with
     `export OPENRAM_TMP=/nobackup/openram_sky130_4kb/temp_drclvs` set
     BEFORE starting python3 this time. Log
     /nobackup/openram_sky130_4kb/drclvs_run.log, watch for
     OPENRAM_DRCLVS_RUN_EXIT_CODE=. Verified empirically at ~1 min in: no
     new /tmp/openram_neuromorphic_<pid>_temp directory appeared for this
     PID (only the two pre-existing ones from earlier runs) -- will
     re-verify once the run reaches the magic-extraction phase (~10+ min
     in) where temp usage actually ramps up, rather than assume the fix
     holds from this early, low-usage snapshot alone. NON-BLOCKING,
     expected to take many hours, may be reboot-killed again (accepted --
     not the GH #104 gate).

=======================================================================
UPDATE 2026-07-24 (cont'd): STATUS CHANGE per coordinator -- verification
found a P0 data-corruption bug in the SRAM_SKY130 RTL read path
(sram_controller.sv ~296-391: s_rvalid asserts one cycle before the
macro's negedge-launched dout1 latches). 6/10 sky130-target tests fail.
RTL fix in progress (separate agent).

*** RUN_2026-07-24_05-27-21 IS NOT A SIGN-OFF RUN -- IT IS A CANARY. ***
Built on known-buggy RTL (pre-read-FSM-fix). Do NOT record its
timing/DRC/LVS numbers as GH #104 Stage-2 sign-off. Its sole purpose:
confirm whether GRT congestion clears with the new 14x-smaller OpenRAM
macro (701.64x673.335um vs the old failed composite's 2585x2595um) --
the read-FSM fix only touches a handful of control flops, not netlist
size/shape/macro geometry, so GRT/DRT/DRC/LVS behavior from this run
carries over to the real sign-off run once RTL is fixed. Kept running
deliberately (not killed) for exactly this reason.

MEM_WORDS ELABORATION CHECK (requested by coordinator, confirmed clean):
verification flagged that sram_controller's MEM_WORDS parameter defaults
to 4096 or (IDX_W=$clog2(MEM_WORDS) computed from a runtime-only initial
$error guard that doesn't fire at elaboration) if not explicitly
overridden, and asked to confirm the PD path actually elaborates with
MEM_WORDS=1024 rather than silently letting 4096 through and truncating.
CONFIRMED via direct netlist inspection (not just RTL reasoning) on the
SRAM_MACRO_SYNTH_PROBE synthesis output:
  - soc_top.sv: parameter SRAM_MEM_WORDS = 1024 (top-level default, no
    override anywhere in config.json -- grepped, no SYNTH_PARAMETERS
    entry touches this).
  - soc_top.sv instantiates: sram_controller #(.MEM_WORDS(SRAM_MEM_WORDS)) u_sram(...)
  - sv2v output (soc_top_sv2v.v) preserved this exactly: module
    sram_controller's own parameter MEM_WORDS defaults to 4096 in the
    module text, but the u_sram instantiation still explicitly connects
    .MEM_WORDS(SRAM_MEM_WORDS) by name -- standard Verilog parameter
    override semantics, sv2v did not inline/break this.
  - HARD EVIDENCE from the actual elaborated/synthesized netlist
    (final/nl/soc_top.nl.v): the macro cell instance
    `sky130_sram_4kbyte_1rw1r_32x1024_8 \u_sram.u_sram_macro` has
    .addr0/.addr1 connected to EXACTLY 10 bits each (\u_sram.mem_addr0[9]
    down to [0], \u_sram.mem_addr1[9] down to [0] -- grepped for [10]/[11]
    bits, NONE exist anywhere in the netlist), and .wmask0 connected to
    exactly 4 bits (\bus_mem_wstrb[3:0]). This proves IDX_W elaborated to
    10 (MEM_WORDS=1024), not 12 (which MEM_WORDS=4096 would produce) --
    the PD/sv2v/synth path is NOT silently using 4096. Confirmed safe.

DRC/LVS macro pass (openram_sram4k_drclvs tmux, OPENRAM_TMP set) status
  at time of this check: PID 392166, ~7 min elapsed, still in the
  submodule-creation phase (matches the ~10 min pattern from the earlier
  views run before it flushes output). No new /tmp/openram_neuromorphic_*
  dir has appeared for this PID -- consistent with the fix holding, but
  NOT YET CONCLUSIVE (real temp usage only ramps up during magic
  extraction, later in the run). Will re-check once that phase is
  reached, per coordinator instruction -- not declaring this confirmed
  until then.

=======================================================================
UPDATE 2026-07-24 (cont'd): Two findings investigated per coordinator
request, both resolved with hard evidence before the DRC/LVS verdict.

FINDING 1 -- 36 "Unknown layer/datatype" GDS errors (error.log, run root):
  VERDICT: BENIGN LAYERMAP GAP in an auxiliary Magic utility script that
  doesn't even use drawn geometry. Zero geometry loss. Not a
  PDK_ROOT/version-skew artifact.
  Evidence chain:
  1. Layer identity (authoritative source: sky130A.lyp, the official
     KLayout layer-property file) -- ALL 5 flagged layer/datatype pairs
     are non-physical DFM/annotation layers, not drawn silicon:
       235/0   = "boundary" (pure outline/reference marker)
       22/21   = "cfom.maskAdd" (contact-front-of-metal mask-correction hint)
       22/22   = "cfom.maskDrop"
       33/42   = "cp1m.maskAdd" (contact-poly-to-metal1 mask-correction hint)
       33/43   = "cp1m.maskDrop"
     None are metal/poly/diffusion/contact/via -- the actual physical stack.
  2. Located the exact source: ALL 36 occurrences are confined to
     48-magic-streamout/{rv32i_cpu_top,sky130_sram_4kbyte_1rw1r_32x1024_8}.get_bbox.log
     (18 each). ZERO occurrences in magic-streamout.log itself (the step
     that actually WRITES the deliverable soc_top.gds/soc_top.magic.gds).
  3. Read get_bbox.tcl (the utility script itself): it does `gds read` +
     `load` + reads the cell's pre-existing `FIXED_BBOX` property -- it
     does NOT measure/derive the bounding box from drawn geometry at all.
     A GDS property record is unaffected by any layer the reader fails to
     recognize while walking the file. So even in principle this
     utility's actual output (llx/lly/urx/ury) cannot be corrupted by
     these warnings.
  4. Tool cross-check (the exact test requested): KLayout
     (49-klayout-streamout/klayout-streamout.log) reads the IDENTICAL GDS
     files (both macros) with ZERO warnings/errors of any kind --
     confirms Magic's layer map is narrower for these DFM layers, not
     that the GDS is missing/corrupt geometry.
  5. Precedent (the clinching check): rv32i_cpu_top.get_bbox.log shows
     the EXACT SAME 18 errors, for the EXACT SAME cell names
     (sky130_fd_bd_sram__openram_dp_cell / _cap_row / _dummy / _replica)
     -- because CPU's own macro GDS hierarchically contains its 10
     internal OpenRAM SRAMs, built from this same primitive library, via
     a completely different, much earlier build (NOT our isolated
     /nobackup/openram_sky130_4kb/pdk_root install). CPU already passed
     full Stage-1 sign-off (0 DRC, MATCH LVS) with this exact same
     condition present. This directly RULES OUT the "layermap/version
     skew from our isolated OpenRAM PDK_ROOT" hypothesis -- it's an
     inherent property of sky130_fd_bd_sram primitive-cell GDS content
     versus Magic's get_bbox-script layer map, independent of which
     OpenRAM build produced the GDS.
  CONCLUSION: a "clean" KLayout/Magic DRC verdict on this design would
  NOT be a false pass on incomplete geometry -- the production GDS write
  path and KLayout's read path are both unaffected. Will still spot-check
  the actual Magic.DRC step log (not yet reached) for the same benign
  pattern rather than assume, since that step's `gds read` may exercise a
  different code path than get_bbox's.

FINDING 2 -- IR drop numbers nonsensical (Worstcase IR drop 6.48e6 V etc):
  ROOT CAUSE CONFIRMED: neither pnr/sky130/soc/config.json NOR
  pnr/sky130/cpu/config.json sets VSRC_LOC_FILES -- this is a PRE-EXISTING
  gap across the WHOLE project, not something introduced by the SRAM
  re-integration. Read librelane's OpenROAD.IRDropReport step + irdrop.tcl
  directly: without VSRC_LOC_FILES, the step falls back to
  `set_pdnsim_net_voltage -net $net -voltage $LIB_VOLTAGE` (no -vsrc
  location at all passed to analyze_power_grid) -- LibreLane's own
  docstring explicitly warns this "may make the results of IR drop
  analysis inaccurate... if you are not integrating a top-level chip for
  manufacture, you may ignore this warning" -- i.e. this is KNOWN,
  documented, expected behavior of the tool absent a real power-source
  location, not a bug in our flow.
  FEASIBILITY ASSESSMENT: setting VSRC_LOC_FILES requires a CSV of real
  (x,y) locations where the external supply enters the design (bond pad
  or bump locations in a padframe/package map). This project's sky130 SoC
  floorplan has NO padframe/pad locations defined anywhere (direct I/O
  ports, no bond-pad ring) at this project phase -- so any VSRC location
  file written now would itself be synthetic/invented, not tied to a real
  package plan, and would not be more truthful than clearly documenting
  the limitation.
  RECOMMENDATION (my call, as asked): document this as a known,
  pre-existing limitation rather than fabricate VSRC locations -- IR-drop
  analysis is not meaningful in this flow until a padframe/bump map
  exists (a future tape-out-readiness phase), consistent with this
  project's existing pattern of explicitly flagging known limitations
  (e.g. "PDN = benign tap-cell artifact", "indicative ASAP7 predictive
  PDK" style notes in CLAUDE.md) rather than silently accepting
  fabricated numbers. Connectivity (PSM-0040) remains the meaningful,
  already-clean signal from this PDN flow either way.

=======================================================================
UPDATE 2026-07-24 (cont'd): TWO operational findings from coordinator's
memory alert during the canary run's Magic.WriteLEF step (measured:
15Gi RAM / 14Gi used / 385Mi free, 31Gi swap / 12-14Gi used, magic RSS
13.18 GB / 86-99% CPU / D-state (I/O-blocked, swapping)).

FINDING A -- Magic.WriteLEF is genuinely unneeded for THIS flow and was
  disabled for the future sign-off run (NOT the running canary, left
  alone per coordinator instruction).
  Confirmed via direct inspection of LibreLane step inputs/outputs
  (librelane/steps/magic.py, netgen.py, klayout.py):
    Magic.WriteLEF:       inputs=[GDS,DEF]              outputs=[LEF]
    Magic.DRC:            inputs=[DEF,GDS]               outputs=[]
    Magic.SpiceExtraction:inputs=[GDS,DEF]                outputs=[SPICE]
    KLayout.DRC:          inputs=[GDS]                    outputs=[]
    KLayout.StreamOut:    inputs=[DEF]                    outputs=[GDS,KLAYOUT_GDS]
    Netgen.LVS:           inputs=[SPICE,POWERED_NETLIST]  outputs=[]
  NONE of the downstream DRC/LVS/streamout steps declare DesignFormat.LEF
  as an input. The ONLY step anywhere in librelane/steps/*.py that
  consumes the TOP-LEVEL design's own written-out LEF is
  Odb.CheckDesignAntennaProperties (odb.py:226,
  `inputs = CheckMacroAntennaProperties.inputs + [DesignFormat.LEF]`) --
  and this flow's Makefile recipe ALREADY skips that exact step
  (`--skip Odb.CheckDesignAntennaProperties`, present since before this
  session). soc_top is DESIGN_NAME (the top-level chip here), never
  instantiated as a macro inside anything larger in this flow, so its
  self-abstract LEF has zero consumers, confirmed, not assumed.
  ACTION: added to pnr/sky130/soc/config.json (for the next, clean
  sign-off run only):
    "RUN_MAGIC_WRITE_LEF": false
  with an explanatory "_comment_RUN_MAGIC_WRITE_LEF" key alongside it
  (confirmed LibreLane only WARNS on unrecognized top-level config keys,
  does not error -- config.py:1023 `warnings.append(f"An unknown key...")`
  -- and confirmed config.json still parses as valid JSON after the
  edit). Removes the single largest memory/time consumer observed in the
  canary run (13.18 GB RSS, ~50 min wall-clock) with zero functional loss.

FINDING B -- OPERATIONAL / SEQUENCING CONSTRAINT (new, add to standing
  rules alongside the existing reboot-survivability rule):
  *** Do NOT run a Sky130 SoC PD flow (LibreLane) concurrently with a
  cocotb/verification regression on this host. *** Measured directly:
  with the canary PD run's Magic.WriteLEF step (13+ GB RSS) running
  alongside the concurrent soc_all cocotb re-verification run, the host
  hit 385 Mi free RAM / 12-14 Gi of 31 Gi swap used / PSI pressure some
  avg10=25%, FULL avg10=24% (processes measurably stalling ~24% of the
  time). No systemd-oomd kill occurred this time (17-19 Gi swap
  headroom remained), but this is thrashing, not comfortable margin, on a
  15 GiB host. The two workloads compete for the same RAM pool.
  RULE: when relaunching the clean sign-off PD run (post RTL-fix,
  post-verification-green), do NOT start it while any cocotb/verification
  run is active on the same host. Let verification finish and have the
  machine to itself for the PD run's own memory-heavy steps (Magic
  extraction/DRC/streamout, ngspice characterization, etc.) -- this
  mirrors the MAKEFLAGS=-j2 / /nobackup SIM_BUILD note already documented
  for the Phase 7 AMS cosim in the top-level CLAUDE.md, but for PD-vs-
  verification contention specifically, which hadn't been documented
  before this measurement.

Canary priority note (per coordinator, recorded for continuity): if
  systemd-oomd starts killing under memory pressure, the VERIFICATION run
  takes priority over the canary -- the canary has already delivered its
  main value (GRT 0/0/0 overflow, GRT-0118 never fires, DRT final 0
  violations per coordinator's own direct verification, PSM-0040 clean
  end-to-end including IRDropReport's connectivity check) -- whereas
  verification gates the actual sign-off. Not yet needed as of this
  update; canary still running, not killed.

=======================================================================
CORRECTION 2026-07-24 (cont'd): coordinator correctly pushed back on
"LibreLane only warns on unrecognized top-level keys" -- that finding was
from a DIFFERENT, more lenient code path than the one actually used at
flow construction. Empirically re-tested with the REAL code path
(instantiating the Classic flow directly against our config.json, exactly
what `python3 -m librelane` does):

  from librelane.flows import Flow
  Classic = Flow.factory.get('Classic')
  flow = Classic('.../pnr/sky130/soc/config.json', pdk_root=...)

FIRST attempt (with my own "_comment_RUN_MAGIC_WRITE_LEF" explanatory key
  still in config.json) FAILED IMMEDIATELY:
  `librelane.config.config.InvalidConfig: The following errors were
  encountered: * Unknown key '_comment_RUN_MAGIC_WRITE_LEF' provided.`
  -- i.e. THIS strict loader hard-errors on unrecognized keys (unlike the
  lenient warning-only path I'd found earlier and wrongly generalized
  from). Removed the comment key from config.json (JSON has no native
  comment syntax anyway -- should have just put the explanation in the
  Makefile/pdn.tcl from the start rather than inventing a pseudo-key).

SECOND attempt (bare `"RUN_MAGIC_WRITE_LEF": false`, no comment key):
  CONFIG LOADED OK. `flow.config['RUN_MAGIC_WRITE_LEF']` == `False`
  (Python bool, not a string or None -- correctly typed and resolved).
  This is strong proof the key name IS real and recognized: the exact
  same strict loader that just hard-errored on my bogus comment key
  ACCEPTS this one and resolves it correctly -- if "RUN_MAGIC_WRITE_LEF"
  were itself a typo/wrong name, this construction call would have thrown
  the identical "Unknown key" error, not silently accepted it.

Traced the runtime GATING logic end-to-end (librelane/flows/sequential.py
  ~line 300-320) to close the loop completely, not just at config-load
  time:
    gating_cvars_expanded[step.id] = self.gating_config_vars[step.id]  # from classic.py: {"Magic.WriteLEF": ["RUN_MAGIC_WRITE_LEF"], ...}
    for variable in gating_cvars:
        if not self.config[variable]:
            info(f"Gating variable for step '{step.id}' set to 'False'- the step will be skipped.")
            gated = True
    ...
    if not executing or cls.id in skipped_ids or gated:
        info(f"Skipping step '{step.name}'...")
  For step.id=="Magic.WriteLEF", gating_cvars==["RUN_MAGIC_WRITE_LEF"];
  with our confirmed config value False, `not False` is True -> gated=True
  -> step skipped. This EXACT mechanism (same dict, same conditional) is
  already demonstrated working in THIS SAME canary run's own log for
  other steps, e.g. "Gating variable for step
  'OpenROAD.RepairDesignPostGRT' set to 'False'- the step will be
  skipped." -- live precedent in this exact flow, today, not just theory.

BELT-AND-SUSPENDERS: also added `--skip Magic.WriteLEF` to the Makefile's
  librelane-sky130-soc recipe (the proven --skip mechanism, same one
  already used successfully for 12 other steps in this exact recipe),
  per coordinator's explicit preference. Both mechanisms now independently
  disable the step; either alone would suffice.

STILL OUTSTANDING (honest, not yet claimed as done): have NOT yet seen an
  actual live run confirm no 50-magic-writelef step directory is created
  -- that requires the next real sign-off run (45+ min to reach that
  point) and will be checked explicitly then, not assumed from the
  config/code-level proof above alone.

=======================================================================
CRITICAL CATCH 2026-07-24 (coordinator): SRAM_MET3_REMOVED_EXPERIMENT ran
  on STALE sv2v output -- soc_top_sv2v.v (mtime 05:27:16) predated the RTL
  P0 read-latency fix (rtl/soc/sram_controller.sv mtime 05:56:59).
  `sky130-soc-sv2v` is a phony-style Makefile target with NO file
  dependency on the RTL sources (pnr/Makefile line ~674) -- it only
  regenerates when explicitly invoked, so editing RTL does NOT
  auto-invalidate/regenerate soc_top_sv2v.v. Verified independently:
  grep -c "rd_pend_q|buf_v_q" rtl/soc/sram_controller.sv = 20,
  same grep on the (stale) soc_top_sv2v.v = 0. This is a genuine
  silent-staleness trap -- confirmed real, not a false alarm.
  SCOPE: does NOT invalidate the met3-connect PDN experiment's actual
  conclusion (PDN/GRT/DRT results are independent of the internal
  read-FSM logic bits) -- but the experiment is NOT and never was a
  sign-off run, and must not be reported as one.
  ACTION TAKEN before any further run: regenerated `make sky130-soc-sv2v`
  and explicitly re-verified (did not assume):
    - mtime: soc_top_sv2v.v (08:08:04) now newer than sram_controller.sv (05:56:59). PASS.
    - grep -c "rd_pend_q|buf_v_q" pnr/sky130/soc/soc_top_sv2v.v = 15 (>0). PASS.
    - Re-ran a fresh Yosys.Synthesis-only probe (tag
      SRAM_MACRO_SYNTH_PROBE_FIXEDRTL) on this regenerated netlist:
        * u_sram.mem_addr0/addr1 bits = exactly [9:0] (10 bits, no [10]/[11]) -> MEM_WORDS=1024 confirmed elaborated correctly again, PASS.
        * rd_pend_q/buf_v_q present in the SYNTHESIZED netlist (46 matches, post-flatten) -> the fix is not just textually present but actually elaborates through. PASS.
        * sky130_sram_4kbyte_1rw1r_32x1024_8 \u_sram.u_sram_macro still the exact instance name -> macro_placement.cfg / PDN_MACRO_CONNECTIONS entries remain valid, no naming drift from the RTL fix. PASS.
  All 3 coordinator-required checks (a/b/c) done and PASSED before
  considering any sign-off launch. NOT yet launched at the time of this
  note -- checking canary/experiment run status first per the
  "host to itself" sequencing rule.
  OPEN ITEM (per coordinator, not yet actioned -- flagging rather than
  changing the Makefile mid-flight): sky130-soc-sv2v could gain a real
  file dependency (`soc_top_sv2v.v: $(SKY130_SOC_SV_FILES)`) to prevent
  this class of staleness recurring silently in the future. Left
  untouched for now; record here so a future session considers it.

=======================================================================
CANARY TERMINATED 2026-07-24 08:1x (proactive, per coordinator's explicit
  priority rule: "if memory forces intervention, kill the CANARY and let
  the experiment finish"). Root cause: RUN_2026-07-24_05-27-21's
  KLayout.DRC process (546616) grew to 10.4 GB RSS (63.9% of host RAM)
  while running concurrently with SRAM_MET3_REMOVED_EXPERIMENT's
  Magic.StreamOut (which was mid-way through reading the SRAM macro's
  full nested GDS hierarchy -- not cheaply restartable). Host hit 400 Mi
  free / 6.2 Gi swap used -- a real crisis point, same severity class as
  the earlier Magic.WriteLEF episode. Rather than wait for an
  unpredictable systemd-oomd kill (which could have hit either process,
  including the more valuable experiment), proactively SIGTERM'd the
  canary's process tree (391637/391805 shell+python3 wrapper), then
  SIGKILL'd the orphaned klayout subprocess (546616, did not honor
  SIGTERM) when it kept running post-shell-exit. Flow exited with
  SOC_FULL_RUN_EXIT_CODE=2 (expected/intentional, not a flow bug). Memory
  recovered immediately to 5.7 Gi free.
  CONSEQUENCE (per coordinator's own stated reasoning, both runs were on
  stale/pre-P0-fix RTL anyway so neither could ever be sign-off): the
  canary's KLayout.DRC verdict and Netgen.LVS were never obtained --
  acceptable loss, since coordinator explicitly judged the canary's only
  remaining unique value as "being further along the KLayout deck" (not
  new information) versus the experiment carrying the corrected PDN
  geometry we actually intend to ship. GRT (0/0/0 overflow, GRT-0118
  never fired), DRT (0 violations, coordinator-verified), and PSM-0040
  (both nets clean) results already obtained from the canary earlier
  remain valid and are not lost.

=======================================================================
GATE CLOSED 2026-07-24: met4.4a CONCLUSIVELY a Magic DEF-mode artifact,
  NOT real geometry. Two independent checks on ACTUAL physical GDS
  geometry (not Magic's DEF+LEF-abstract reconstruction) both agree:
  1. Standalone Magic DRC, GDS-mode, on the SRAM macro's own raw
     generated GDS alone (no SoC/LEF context at all): met4.4a = 0
     (confirmed twice, two independent completed runs, COUNT ~11.08M
     total violations but ALL in 24 other internal-cell rule classes --
     li.3/licon.*/poly.*/met1-3 spacing/psd.10b -- matching the SAME
     scale-artifact class already documented for CPU's own internal
     Magic DRC, KLayout=0 authoritative precedent).
  2. MINIMAL, targeted KLayout DRC script (built after the full 912-rule
     deck run hit critical memory pressure at 13-14.5GB RSS with the host
     essentially maxed -- built to de-risk OOM and get a fast, decisive
     answer instead of hoping to survive to line 736). Extracted ONLY
     what the m4.4a rule needs, copied verbatim from the real deck
     (sky130A_mr.drc lines 125/169/736 -- no hand-derived layer numbers):
       m4_wildcard = "71/20"
       m4 = polygons(m4_wildcard)
       m4.with_area(0..0.240).output("m4.4a", ...)
     Run against the SAME experiment soc_top.gds (the actual merged
     physical layout), threads=4 (down from 16). Completed in well under
     a minute (vs the full deck's 54+ min and still climbing) at a small
     fraction of the memory. Report XML: <items></items> -- EMPTY.
     m4.4a = 0 on the real merged GDS, confirmed.
  CONCLUSION: met4.4a is a Magic DEF-mode LEF-reconstruction artifact
  (MAGIC_DRC_USE_GDS=false in this flow's config -- for macro instances
  Magic.DRC only sees the LEF PIN/OBS abstract, not real internal
  geometry). The real, physical, drawn layout is genuinely clean.
  Precedent class alongside nwell.4 (also DEF-mode-specific), though a
  different underlying mechanism (LEF-abstract reconstruction quirk vs
  tap-cell connectivity blindness) -- KLayout is authoritative for BOTH,
  matching the existing project convention from CPU Stage-1 sign-off.
  Full-deck KLayout run (611521) was left running as a bonus (broader
  DRC coverage, not blocking) -- still alive at time of this note, line
  ~537/912, 12-13.6GB RSS. NOT to be conflated with "KLayout DRC clean"
  in any sign-off record until it actually completes -- the sign-off
  record must cite "KLayout m4.4a check: 0" specifically for this
  evidence, plus a SEPARATE full-deck KLayout DRC run on the actual
  sign-off GDS (not this stale-RTL experiment's GDS) for real coverage.

=======================================================================
SIGN-OFF RUN LAUNCHED 2026-07-24 09:58:08. Pre-launch checklist verified
  (not assumed) immediately before launch:
  1. sv2v: soc_top_sv2v.v mtime 1784855284 > sram_controller.sv mtime
     1784847419 (True); grep -c "rd_pend_q|buf_v_q" = 15 (>0). PASS.
  2. pdn.tcl: only "met4 met5" connects present (stdcell_grid line 146,
     macro_grid line 204); no "met3 met4" anywhere. PASS.
  3. config.json: RUN_MAGIC_WRITE_LEF=False (Python bool via direct
     json.load), VERILOG_DEFINES=[__pnr__, SRAM_SKY130], zero
     underscore-prefixed/stray keys, valid JSON. Makefile: --skip
     Magic.WriteLEF present in librelane-sky130-soc recipe specifically
     (line 734, confirmed via target-boundary trace -- the other 5
     "--skip Magic.WriteLEF" matches in the file are PRE-EXISTING,
     unrelated occurrences in the asap7/asap7-gpu/asap7-soc-synth*
     targets, not something this session introduced). PASS.
  4. macro_placement.cfg: "u_cpu 150 207.0 N" +
     "u_sram.u_sram_macro 4209.0 207.0 N". PASS.
  5. PDN_MACRO_CONNECTIONS: ".*u_cpu.*  VPWR VGND VPWR VGND" +
     ".*u_sram_macro.*  VPWR VGND vccd1 vssd1" (net-then-pin order
     confirmed correct per the earlier set_global_connections.tcl
     read). PASS.
  6. Detached tmux session `sky130_soc_signoff`, log
     /nobackup/sky130_soc_signoff_run.log, run dir will land under
     /nobackup/sky130_soc_runs/RUN_<timestamp>/ per the existing symlink.
  7. Host confirmed free immediately before launch: 12Gi available,
     `pgrep -af "python3 -m librelane|klayout|magic|sram_compiler.py"`
     returned zero matches. Full-deck KLayout experiment run (611521)
     killed first per coordinator instruction (its coverage was on
     stale-RTL geometry anyway, superseded by this run's own
     KLayout.DRC). OpenRAM macro DRC/LVS pass (392166) already killed
     earlier for the same host-to-itself reason.

TARGET GATE (report every number once available): PSM-0040 both nets ->
  GRT 0/0/0 -> DRT 0 -> Magic DRC (expect nwell.4 only per Stage-1
  precedent, met4.4a should read as the now-documented DEF-mode
  artifact) -> KLayout DRC full deck -> Netgen LVS MATCH -> PPA (fmax,
  power, area, utilization).

ANTICIPATED RISK (noted before it happens, per coordinator): this run's
  own KLayout.DRC step will likely hit the same ~13-14.5GB peak that
  nearly OOM'd the earlier standalone full-deck check. If it dies here
  too: do NOT panic-restart the whole flow -- resume from KLayout.DRC
  (or use the minimal-deck technique proven above for targeted rule
  answers) rather than losing the earlier (expensive, already-passed)
  stages. nwell.4 will read ~9,000 regardless -- rides on Stage-1
  precedent (CPU signed off with 4,293 on KLayout=0 + LVS MATCH) but
  THIS run's own KLayout+LVS results are what actually confirm the
  precedent applies here, not a formality.

=======================================================================
SIGN-OFF RUN GATE RESULTS (RUN_2026-07-24_09-58-19), 2026-07-24:
  PSM-0040: CLEAN, both VPWR and VGND.
  GRT: CLEAN, 0/0/0 overflow all layers, GRT-0118 never fires.
  DRT: 0 (converged 16633 -> 4630 -> 3902 -> 167 -> 3 -> 0).
  Magic.DRC: COUNT 9081 (nwell.4=9049, met4.4a=32) -- identical to the
    canary/experiment, fully expected (Magic's DEF-mode check is
    independent of the met3-connect fix, already established).
  KLayout.DRC (FULL 912-rule deck, survived the ~14GB memory peak this
    time -- 4902.27s / ~82 min, peak ~14.3GB, ended ~11.9GB):
    - m4.4a = 0 (THIRD independent confirmation: macro's own raw GDS
      x2, experiment's merged GDS via minimal script, now the actual
      sign-off GDS via the FULL deck). Gate item fully closed.
    - nwell.4: not even a reported category (None) -- KLayout doesn't
      flag this condition at all, consistent with it being a Magic
      DEF-mode-only artifact (matches Stage-1 CPU precedent exactly).
    - REAL FINDING, must not be glossed over: 4 genuine violations,
      total=4, ALL located INSIDE the SRAM macro's own internal cells
      (not SoC-level routing/PDN/integration):
        m2.2  (met2 spacing <0.14um) x1 -- cell wmask_dff, gap ~0.055um
        via2.2 (via2 spacing <0.2um) x2 -- cell sky130_sram_4kbyte_...
                (macro top) + cell bank, both gap ~0.125um
        m3.2  (met3 spacing <0.3um)  x1 -- cell bank, gap ~0.29um
                (marginal, ~1nm short of the 0.3um minimum)
      These are baked into the OpenRAM-compiled macro's OWN geometry,
      independent of anything this session did at the SoC level. The
      views-first pass (check_lvsdrc=False) never ran OpenRAM's own
      DRC, so this is the FIRST real DRC signal on the macro itself,
      and it is NOT perfectly clean -- 4 minor spacing violations, all
      sub-0.3um scale, none catastrophic, but real and must be
      disclosed, not hidden behind the met4.4a/nwell.4 artifact
      discussion (those are unrelated tool-specific issues; these 4 are
      real geometry).
  Netgen.LVS: not yet reached at time of this note (Checker.MagicDRC /
    Checker.KLayoutDRC running now, LVS steps follow).

=======================================================================
ISOLATION TEST 2026-07-24: standalone macro GDS, FULL KLayout signoff
  deck (sky130A_mr.drc, same deck as the SoC-level run), no SoC context
  at all. Completed fast (265.72s, ~4.4 min, ~1GB peak memory -- vastly
  lighter than the SoC-level run, as expected for a single macro).
  RESULT: EXACT SAME 4 violations, same counts (m2.2=1, via2.2=2,
  m3.2=1), and CONFIRMED IDENTICAL COORDINATES/CELLS (differing only by
  the "O3_" hierarchy-uniquification prefix the SoC embedding adds):
    m2.2  | sky130_sram_4kbyte_1rw1r_32x1024_8_wmask_dff |
            edge-pair (-0.14,6.885;-0.14,7.255)/(-0.195,7.384;-0.195,6.756)
    via2.2| sky130_sram_4kbyte_1rw1r_32x1024_8 (macro top) |
            edge-pair (562.095,631.465;...)|(562.295,631.59;...)
    via2.2| sky130_sram_4kbyte_1rw1r_32x1024_8_bank |
            edge-pair (486.255,581.655;...)|(486.455,581.78;...)
    m3.2  | sky130_sram_4kbyte_1rw1r_32x1024_8_bank |
            edge-pair (63.61,30.973;...)/(63.32,31.132;...)
  CONCLUSIVE: 100% baked into the OpenRAM compile itself. SoC integration
  (PDN/floorplan/routing/macro placement, all this session's own work)
  did NOT cause, does NOT touch, and CANNOT fix these 4 spots.

CHARACTERIZATION (item 3): checked whether "wmask_dff"/"bank" are
  foundry-drawn primitives or OpenRAM-generated assembly. Confirmed
  OpenRAM-generated: compiler/modules/bank.py is OpenRAM's own top-level
  bank-assembly Python class (auto-places/routes decoder+bitcell_array+
  sense_amp+dffs together); "wmask_dff" is an OpenRAM factory-instantiated
  dff_array (same generic module type used for row_addr_dff/col_addr_dff/
  data_dff, all seen in the macro's own cell hierarchy). Searched the
  installed sky130_fd_bd_sram primitive library for "wmask_dff"/"bank" --
  zero matches (these names do not exist there). Rules out "foundry
  primitive should be clean by construction" / PDK-version-skew --
  confirms these are real OpenRAM generator/auto-router spacing issues
  at the assembly level, not primitive-cell-level.
  Severity ranking:
    1. m2.2 (wmask_dff): 0.055um actual vs 0.14um required -- ~60% short.
       Real, meaningful violation.
    2/3. via2.2 x2 (macro top + bank): 0.125um actual vs 0.2um required
       -- ~37.5% short. Real, moderate violation.
    4. m3.2 (bank): 0.29um actual vs 0.3um required -- ~3% short (~1nm).
       Marginal -- plausibly a grid-rounding/floating-point boundary
       artifact in OpenRAM's geometry engine rather than a "real" design
       intent violation, though still technically non-conformant.

FIX OPTIONS (item 4, cost/feasibility only -- NOT acted on, awaiting
  user's explicit call per coordinator):
  (a) Regenerate macro with check_lvsdrc=True (OpenRAM's own DRC-driven
      flow): HIGH non-completion risk. This is the SAME ~7h+ extraction
      class that already died to a host reboot once this session
      (documented above), and this project's run_state.md history shows
      multiple prior reboot incidents on this host during other
      long-running PD jobs -- reboot cadence is real and unpredictable,
      not a one-off. Also: even a SUCCESSFUL completion would likely
      just CONFIRM the same 4 violations (OpenRAM's geometry generation
      is deterministic from its config/algorithms, not reactive --
      turning on the checker reports issues, it doesn't auto-fix them).
      Does not by itself resolve anything; only informs.
  (b) OpenRAM config change (different words_per_row/column-mux config
      etc.) that might shift the internal bank/wmask_dff floorplan
      enough to avoid these specific marginal spacings: speculative,
      medium effort (~190 min minimum per views-only rebuild attempt,
      more if multiple iterations needed), could introduce NEW
      violations elsewhere, no guarantee of success without deeper
      OpenRAM generator-code investigation first.
  (c) Targeted GDS patch of the 4 exact coordinates (nudge/widen the
      specific metal/via shapes by a few nm): fast (well under an hour),
      technically straightforward given exact coordinates are known, but
      FRAGILE/non-reproducible -- any future re-run of OpenRAM from the
      same config regenerates the original flawed geometry, so this is a
      one-off hand-patch, not a maintainable fix. Would need its own
      DRC+LVS re-verification pass after patching to confirm no new
      issues introduced.
  (d) Accept + explicitly document as a known OpenRAM-generator
      limitation (4 sub-0.3um spacing violations, precisely located,
      independent of SoC integration): zero effort, but per coordinator
      this requires the USER to explicitly own the call, not an
      autonomous "acceptable" determination.
  Rough ranking given the above: (c) is fastest for an immediately-clean
  GDS but least sustainable; (d) is lowest-risk pending user sign-off;
  (b) is a real fix but speculative and costly to validate; (a) is the
  least practical near-term (high non-completion risk, and wouldn't
  directly fix anything even if it completes).

=======================================================================
SIGN-OFF RUN FINAL RESULTS (RUN_2026-07-24_09-58-19), completed all
  steps through 57-misc-reportmanufacturability, exited non-zero (2)
  because LibreLane's own Checker.MagicDRC/Checker.KLayoutDRC gate
  strictly on DRC count==0 (which our precedent-based analysis disputes
  but the tool itself doesn't know that) -- NOT a crash, the full gate
  sequence ran and reported.
  LVS: "Circuits match uniquely." Checker.LVS: "Check for LVS errors
    clear." Circuit 1 (layout) = 34,835 devices / 35,252 nets; Circuit 2
    (schematic) = identical. Genuine, definitive PASS.
  Manufacturability summary (57-misc-reportmanufacturability/
    manufacturability.rpt):
      Antenna: FAILED -- 557 pin violations, 442 net violations. Traced:
        this Makefile recipe's --skip list (RUN_ANTENNA_REPAIR-related
        steps) PRE-DATES this session (confirmed via `git diff` on
        pnr/Makefile -- zero antenna-related lines touched). Not
        introduced by GH #104 SRAM work; a pre-existing condition of
        this specific recipe.
      LVS: Passed.
      DRC: Failed -- KLayout 4, Magic 9081 (both already characterized
        above).
  *** NEW CRITICAL FINDINGS from PPA data-pull (not part of the
  originally-requested DRC/LVS gate, but essential context): ***
  1. SETUP TIMING FAILS: nom_tt_025C_1v80 WNS = -1.069077 ns (TNS same,
     single violator). Worst violator path:
       [setup reg-reg] u_cpu/axi_araddr_o[15] -> u_cpu/axi_arready_i
     This is ENTIRELY WITHIN the CPU macro's own boundary pins (output
     back to its own input) -- NOT an SRAM-related path at all. Almost
     certainly the classic "macro closed timing in isolation assuming
     zero external interconnect delay on its I/O pins; SoC-level routing
     adds real wire delay the CPU's own Stage-1 sign-off never budgeted
     for" failure mode. Independent of the SRAM macro re-integration
     work this session did. Hold WNS = 0 (clean).
  2. POWER REPORT IS GARBAGE/UNUSABLE: report_power at nom_tt shows
     "Macro" category Internal Power = 5.995726e+07 W (~60 MILLION
     watts, 100.0% of total) -- physically absurd. ROOT-CAUSED: NOT a
     units-declaration mismatch (checked sky130_sram_4kbyte...TT_1p8V_25C.lib
     header -- time_unit/voltage_unit/current_unit/capacitive_load_unit/
     leakage_power_unit all match the reference installed macro exactly).
     The raw internal_power table VALUES themselves are absurd:
       rise_power(scalar) { values("1.998525e+11"); }
     This traces to the views-first OpenRAM run using ANALYTICAL
     (non-SPICE-simulated) characterization -- confirmed from the
     original build log: "Characterization is disabled (using
     analytical delay models)". OpenRAM's analytical power-estimation
     formulas produced a nonsensical result for this macro size (1024
     words), a genuine OpenRAM .lib data-quality defect, not a
     downstream tool bug. This power report cannot be used for any real
     power sign-off as-is.

=======================================================================
FULL PPA METRICS PULLED (RUN_2026-07-24_09-58-19, from step
  57-misc-reportmanufacturability/state_out.json metrics dict --
  authoritative LibreLane-computed values, not re-derived by hand):

AREA / UTILIZATION:
  die area:            20.77 mm^2   (6700 x 3100 um, unchanged)
  core area:           20.36 mm^2
  instance area total:  7.71 mm^2  (macros 6.95 mm^2 + stdcell 0.76 mm^2)
  utilization overall: 37.89 %     (macro-dominated)
  utilization stdcell:  5.68 %     (stdcell logic alone)

TIMING (multi-corner, from stapostpnr):
  nom_tt_025C_1v80  (primary/typical corner): setup WNS -1.069 ns, TNS
    -1.824 ns; hold WNS 0 (clean), TNS 0 (clean).
    Achievable fmax at this corner ~= 69.4 MHz (vs 75 MHz / 13.333 ns
    target) if only this path is fixed -- i.e. NOT closing at the
    nominal target frequency as configured.
  max_tt_025C_1v80: setup WNS -1.824 ns (single violator, same CPU
    boundary path, worse at max/slow-cell corner).
  max_ss_100C_1v60 (worst corner overall): setup WNS -5.507 ns, TNS
    -5868 ns (many violating paths, not just the one CPU-boundary path);
    hold WNS -0.231 ns, TNS -0.610 ns (both setup AND hold fail here).
    Achievable fmax at this worst corner ~= 53.1 MHz.
  nom_ss_100C_1v60: setup WNS -4.632 ns; hold WNS -0.056 ns (both fail).
  min_tt/min_ss/max_ff/min_ff/nom_ff: setup WNS = 0 (CLEAN) -- only the
    slow/high-temp corners show setup violations; all fast corners
    close cleanly.
  Single dominant violator at nom_tt: [setup reg-reg]
    u_cpu/axi_araddr_o[15] -> u_cpu/axi_arready_i (CPU-internal boundary
    path, see earlier note -- Stage-1 CPU sign-off closed this in
    isolation without SoC-level interconnect delay budget).

POWER:
  Tool-reported total: 59,957,256 (W, per LibreLane's power__total metric)
    -- GARBAGE, see below, do not use as-is.
  Leakage: 7.158e-05 W = 71.6 uW (plausible, usable).
  Switching: 0.01951 W = 19.51 mW (plausible, usable).
  Internal (non-macro: Sequential+Combinational+Clock from report_power):
    reasonable-looking individually (Sequential ~32 mW, Clock ~38 mW,
    Combinational ~0.25 mW) -- the corruption is 100% isolated to the
    "Macro" row (5.9957e+07 W, 100.0% of total), consistent with it
    being the SRAM macro's own analytically-characterized (not
    SPICE-simulated) .lib, NOT a general tool/flow bug.
  HONEST usable subtotal (leakage + switching, excluding the corrupted
    macro-internal component): ~19.58 mW. Cannot state a real
    total-power number until the SRAM macro's .lib is recharacterized
    (SPICE-based, not analytical) -- this is a SEPARATE, additional
    known limitation alongside the 4 DRC violations and the IR-drop
    VSRC_LOC_FILES gap already documented.

ANTENNA: 557 pin violations, 442 net violations (metric-confirmed, same
  as the manufacturability.rpt summary). Pre-existing recipe condition
  (confirmed via git diff -- not introduced this session).

LVS (metric-confirmed, matches the "Circuits match uniquely" log line):
  design__lvs_error__count = 0
  design__lvs_device_difference__count = 0
  design__lvs_net_difference__count = 0
  design__lvs_property_fail__count = 0
  design__lvs_unmatched_device__count = 0
  design__lvs_unmatched_net__count = 0
  design__lvs_unmatched_pin__count = 0
  ALL ZERO. Definitive, metric-level confirmation of LVS MATCH.

DRC: klayout__drc_error__count = 4 (all macro-internal, documented in
  pdn.tcl + bd issue claude_verilog_test-0jp). magic__drc_error__count
  = 9081 (nwell.4=9049 + met4.4a=32, both evidenced tool artifacts,
  Stage-1 precedent + this session's own KLayout/standalone-GDS proof).

PDN / POWER GRID: design__power_grid_violation__count = 0 (matches
  PSM-0040 clean, both nets). The separate design_powergrid__drop__*
  metrics show the same nonsensical multi-million-volt numbers already
  documented as a KNOWN LIMITATION in pdn.tcl (no VSRC_LOC_FILES defined
  -- IR-drop analysis not meaningful without a padframe/bump map).

ROUTE DRC (detailed routing iteration history, metric-confirmed):
  iter1=16633, iter2=4630, iter3=3902, iter4=167, iter5=3, iter6=0.
  Final route__drc_errors = 0.

BD ISSUE FILED: claude_verilog_test-0jp (P2, open) -- tracks the 4
  KLayout DRC violations for a future DRC-clean macro regeneration.

=======================================================================
CLOCK RELAX 2026-07-24: USER DECISION -- relax SoC clock target from
  75 MHz (13.333 ns) to 65 MHz (15.385 ns), re-run sign-off. Rationale:
  nom_tt setup WNS was -1.069 ns at 75 MHz (single CPU-macro-internal-
  boundary violator); +2.051 ns of added slack should close nom_tt/max_tt
  but NOT the slow (ss) corners -- accepted by user, not a blocker.
  HOLD IS EXPLICITLY UNDERSTOOD AS NOT FIXED BY THIS (period-independent)
  -- max_ss hold WNS -0.2305 ns must be reported separately, called out
  as an open functional risk if it persists, not buried under "timing
  improved".

CHANGES APPLIED (both places the period is declared, confirmed via prior
  session's own established pattern of checking config vs elaborated
  constraint separately):
  - pnr/sky130/soc/config.json: CLOCK_PERIOD 13.333 -> 15.385.
  - pnr/sky130/soc/constraints/sky130_soc.sdc: `set clock_period` 13.333
    -> 15.385 (only one SDC file in this flow -- PNR_SDC_FILE,
    SIGNOFF_SDC_FILE, FALLBACK_SDC_FILE all point to this same file,
    confirmed via config.json). Header comments updated (75->65 MHz,
    rationale note added).
  Still need to verify the ELABORATED constraint in the run's own STA
  step reads 15.385 ns, not assume propagation from config/SDC text
  alone -- will check the first STA-consuming step's own report once
  the run reaches it.

RE-VERIFIED (fresh, not assumed stale-safe): regenerated sv2v
  (`rm -f soc_top_sv2v.v && make sky130-soc-sv2v`, unrelated to the
  clock change itself but done per explicit instruction to re-check the
  staleness trap every time). sv2v mtime newer than sram_controller.sv;
  grep -c "rd_pend_q|buf_v_q" = 15 (fix signals present).

CHECKLIST RE-VERIFIED before launch: pdn.tcl met3-connect still removed
  (only "met4 met5" present); config.json RUN_MAGIC_WRITE_LEF=False
  (Python bool), zero stray keys, PDN_MACRO_CONNECTIONS net-then-pin
  correct for both macros; Makefile --skip Magic.WriteLEF present;
  macro_placement.cfg u_cpu/u_sram.u_sram_macro GCell-aligned origins
  unchanged. Host confirmed free (8.6Gi available, zero PD processes,
  0 swap used) immediately before launch.

LAUNCHED: detached tmux `sky130_soc_signoff_65mhz`, log
  /nobackup/sky130_soc_signoff_65mhz_run.log, run dir will land under
  /nobackup/sky130_soc_runs/RUN_<timestamp>/, 2026-07-24 21:35:19.

=======================================================================
65MHz RE-RUN: MAX_SS HOLD INVESTIGATION (per coordinator request),
  RUN_2026-07-24_21-36-12, 46-openroad-stapostpnr/max_ss_100C_1v60/:

VIOLATOR IDENTIFICATION: exactly 2 hold paths (matches reported count),
  BOTH sourced from the SAME single net (u_cpu/axi_bready_o, a CPU-macro
  OUTPUT pin -- the AXI write-response-ready signal), fanning to two
  different flat-logic capture flops:
    [hold reg-reg] u_cpu/axi_bready_o -> _45649_/D : -0.070788 (WNS)
    [hold reg-reg] u_cpu/axi_bready_o -> _43792_/D : -0.047697
  This is a CPU-macro-boundary-to-SoC-interconnect path (launch inside
  CPU macro, capture in flat SoC logic) -- NOT SRAM-related, NOT purely
  CPU-internal.

CONCRETE, VERIFIED CORNER-MODELING GAP (not speculation -- confirmed via
  direct log inspection): BOTH hard macros (rv32i_cpu_top AND
  sky130_sram_4kbyte_1rw1r_32x1024_8) have ONLY a single nom_tt/TT_1p8V_25C
  .lib file each. config.json's MACROS entries use a WILDCARD
  `"lib": {"*": [...]}` mapping -- i.e. EVERY PVT corner (including
  max_ss_100C_1v60) reads the EXACT SAME nom_tt .lib for both macros'
  internal timing arcs. Confirmed directly in the run log: "Reading
  timing library for the 'nom_ss_100C_1v60' corner at
  .../rv32i_cpu_top__nom_tt_025C_1v80.lib" and same pattern for the SRAM
  macro's TT_1p8V_25C.lib. Only the STANDARD CELL library genuinely
  varies by corner (sky130_fd_sc_hd__ss_100C_1v60.lib etc.) -- macro
  internal delays are corner-invariant in this flow, for both macros,
  100% of the time.
  IMPLICATION: since axi_bready_o's launch-side delay is INSIDE the CPU
  macro, the "max_ss" analysis for this specific hold-violating net is
  NOT using true slow-corner CPU-internal delay (none exists -- only
  nom_tt was ever characterized) -- it is using the SAME (faster,
  typical) nom_tt macro delay value under an "ss" label for the
  surrounding std-cell logic. Real slow-corner silicon would have the
  CPU's true internal launch delay SLOWER than modeled here, which would
  make data arrive LATER at the capture flop -- i.e. MORE hold margin
  than this report shows, not less. This means the reported -70.8ps /
  -47.7ps at "max_ss" is very likely PESSIMISTIC relative to true silicon
  behavior specifically because of this corner-library gap on the launch
  side. This is a genuine, verifiable modeling caveat, not a dismissal --
  presented as such, not as proof the violation is fully spurious.
  (Same caveat also applies to ALL the remaining slow-corner SETUP
  failures that touch either macro boundary -- e.g. the CPU-internal
  worst violator itself, u_cpu/axi_araddr_o[15]->u_cpu/axi_arready_i, is
  ENTIRELY inside the CPU macro, so its "max_ss -5.32ns" number is
  ALSO using nom_tt-characterized internal delay under an ss label,
  meaning the -5.32/-4.63/-3.22ns slow-corner setup numbers carry the
  same caveat, in the OPPOSITE direction of risk for setup: understating
  internal macro delay at slow corners could mean setup is actually
  WORSE at a genuinely-characterized ss corner than reported, not
  better. Flag this to avoid over-crediting the setup improvement at
  slow corners too.)

HOLD-REPAIR STAGE COMPLETION (verified from actual per-step logs, not
  the combined run log): TWO hold-repair passes exist in this flow,
  BOTH complete, BOTH before detailed routing:
    33-openroad-resizertimingpostcts: RSZ-0046 "Found 53 endpoints with
      hold violations" -> RSZ-0032 "Inserted 127 hold buffers" (ran to
      completion, not aborted).
    36-openroad-resizertimingpostgrt: RSZ-0033 "No hold violations
      found" (fully clean at THIS point, before detailed routing).
  NO resizer/hold-repair step exists AFTER OpenROAD.DetailedRouting in
  LibreLane's Classic flow step list at all (confirmed via
  librelane/flows/classic.py Steps order: ...ResizerTimingPostGRT ->
  DetailedRouting -> ... -> STAPostPNR, and STAPostPNR is pure reporting,
  no repair capability). CONCLUSION: hold was NOT "stopped early" or
  under-effort -- it is STRUCTURALLY impossible for any resizer pass in
  this flow to see or fix hold violations introduced by real
  post-route parasitics, because none runs after DetailedRouting. The
  -70.8ps/-47.7ps residuals are new degradation introduced specifically
  by the shift from GRT-estimated to DRT-actual parasitics on this net,
  which nothing in the flow ever gets a chance to re-check or repair.

CANDIDATE KNOB (identified, NOT applied -- awaiting explicit direction):
  GRT_RESIZER_HOLD_SLACK_MARGIN (OpenROAD.ResizerTimingPostGRT config
  var, default 0.05 ns / 50 ps) -- controls how much POSITIVE slack
  margin the LAST pre-route hold-fix pass targets (resizer normally
  "stops when it reaches zero slack"; this makes it overfix to
  +margin instead). Raising it (e.g. to 0.15-0.2 ns) would build in more
  hold cushion BEFORE detailed routing, to survive whatever ~120ps of
  real-routing degradation this specific net experienced (net swung from
  presumably >=+50ps margin post-GRT to -70.8ps post-route, a ~120ps
  shift). PL_RESIZER_HOLD_SLACK_MARGIN (PostCTS, default 0.1ns) is the
  earlier-stage equivalent, less directly relevant here since PostGRT
  already ran clean afterward.
  RISK TO SETUP (quantified as far as possible without an actual
  re-run): the 2 hold-violating paths (both from u_cpu/axi_bready_o) do
  NOT share a net with any of the worst setup-violating paths identified
  (araddr/arready, awaddr/awready, rlast -- all different AXI channels).
  Direct collision risk on the SAME physical path is LOW. However,
  GRT_RESIZER_HOLD_SLACK_MARGIN is a GLOBAL knob applied to every
  hold-violating endpoint in the design, not just this one net -- and
  BOTH setup- and hold-critical paths are heavily concentrated at/near
  the CPU macro's own boundary in this design (per both violator lists).
  Extra buffer insertion anywhere in that dense boundary region carries
  a real, non-zero INDIRECT risk (added capacitance/congestion/local
  routing perturbation) to the already-thin nom_tt setup margin
  (+0.127ns -- razor-thin). This can only be confirmed empirically by an
  actual re-run with the margin raised and re-checking nom_tt setup
  specifically afterward -- not proposing to do so without explicit
  direction, per instruction.

=======================================================================
65MHz RE-RUN FINAL RESULTS (RUN_2026-07-24_21-36-12), 2026-07-25,
  completed all steps, exited non-zero (2) for the same reason as
  before (LibreLane's own Checker.MagicDRC/Checker.KLayoutDRC gate on
  count==0) -- not a crash, full gate ran and reported:

  PSM-0040: CLEAN, both nets.
  GRT: CLEAN, 0/0/0 overflow, GRT-0118 never fires.
  DRT: 0 (converged 16415 -> 4927 -> 3800 -> 164 -> 6 -> 2 -> 2 -> 2 -> 1
    -> 1x9 -> 0, iter19).
  Magic.DRC: 9081 (nwell.4=9049 + met4.4a=32) -- reproduces exactly.
  KLayout.DRC: m4.4a=0, nwell.4=not checked, 4 total real violations
    (m2.2=1, m3.2=1, via2.2=2) -- reproduces exactly, same documented
    upstream-OpenRAM-macro disposition applies unchanged.
  Netgen.LVS: "Circuits match uniquely." Checker.LVS: "Check for LVS
    errors clear." All lvs_* metrics = 0. Definitive PASS, confirmed via
    metrics dict too.

  TIMING (multi-corner, WITH THE CORNER-MODELING CAVEAT DOCUMENTED IN
    constraints/sky130_soc.sdc -- nom_tt trustworthy, ss/ff touching
    either macro boundary is not):
    nom_tt_025C_1v80: setup slack +0.126867 ns MET (CLOSES, was -1.069ns
      at 75MHz); hold slack +0.180663 ns MET (clean). Violator list
      EMPTY at this corner.
    max_tt_025C_1v80: setup WNS -0.6106 ns (single violator, same
      CPU-boundary path, marginal).
    min_ss_100C_1v60: setup WNS -3.2186 ns (was -3.260 pre-relaxation
      estimate); hold clean (0).
    nom_ss_100C_1v60: setup WNS -4.5434 ns; hold now CLEAN (0) -- was
      -0.0555ns before relaxation-adjacent resizer work, now fully
      closed at this corner.
    max_ss_100C_1v60 (worst corner): setup WNS -5.3197 ns, TNS -98.486ns
      (was -5868ns pre-relaxation -- ~60x collapse, violating paths
      reduced from ~4402 to 274); HOLD WNS -0.0708 ns, TNS -0.1185 ns,
      confined to exactly 2 paths (both from u_cpu/axi_bready_o -- see
      the dedicated hold investigation entry above). This is the ONLY
      remaining hold failure anywhere in the design, and per the
      corner-modeling-gap finding, is plausibly better (or non-existent)
      in real silicon since it relies on the CPU macro's nom_tt-only
      characterization applied under a slow-corner label.
    All truly-fast corners (min_tt/max_ff/min_ff/nom_ff): setup AND hold
      WNS = 0, fully clean.
    USER DECISION: accept residual ss-corner setup/hold as-is, do not
      chase with a resizer margin knob (see hold-investigation entry
      above for full rationale) -- this is a TYPICAL-CORNER (nom_tt)
      sign-off, explicitly not a validated multi-corner one.

  AREA / UTILIZATION (unchanged by the clock relaxation, as expected):
    die 20.77 mm^2, core 20.36 mm^2, instance area 7.71 mm^2 (macros
    6.95 + stdcell 0.76 mm^2), utilization 37.89% overall / 5.68%
    stdcell-only.

  POWER: tool-reported total still garbage (5.196e+07 W, same root
    cause as before -- SRAM macro's analytical, non-SPICE
    characterization). Honest usable subtotal (leakage 71.6uW +
    switching 16.9mW) = ~16.98 mW -- consistent with before (small
    difference from the 65MHz vs 75MHz switching-activity assumption in
    STA's power estimate). Still cannot state a real total power number.

  ANTENNA: 557 pin / 434 net violations (was 442 net -- small run-to-run
    variance in net-violation counting, not materially different; still
    the same pre-existing, unrelated-to-this-session condition).

  ROUTE DRC (detailed routing iteration history): 16415, 4927, 3800,
    164, 6, 2, 2, 2, 1, 1(x9), 0 -- final route__drc_errors=0.

FULL STAGE-2 GATE SUMMARY NOW READY FOR COORDINATOR'S FINAL WRITE-UP:
  PSM-0040 clean, GRT clean, DRT clean, LVS MATCH, nom_tt timing CLOSES
  (setup +0.127ns, hold +0.181ns) -- the four unambiguously-solid gate
  items. Open/documented items: Magic DRC 9081 (2 evidenced tool-artifact
  categories), KLayout DRC 4 (real, upstream OpenRAM generator,
  documented + bd claude_verilog_test-0jp), residual ss-corner
  setup/hold (accepted, corner-modeling-gap-caveated, bd
  claude_verilog_test-o1i), power report unusable as-is (OpenRAM
  analytical characterization defect), antenna pre-existing failures.

=======================================================================
STAGE-2 GH #104 FOLLOW-UP RE-RUN LAUNCHED, 2026-07-25 09:20 +07,
  commit 86e89c1 (branch feat/sky130-soc-drc-lvs-gh104), re-running
  RUN_2026-07-24_21-36-12 with three corrections applied (all already
  committed at 86e89c1, not made by this session):
  1. config.json MACROS.rv32i_cpu_top.lib: 9 exact corner keys
     (nom_tt/min_tt/max_tt_025C_1v80, nom/min/max_ss_100C_1v60,
     nom/min/max_ff_n40C_1v95) each pointing at a staged per-corner
     rv32i_cpu_top__<corner>.lib in pnr/sky130/cpu/macro/, replacing the
     prior "*" wildcard (which meant every non-nom_tt corner silently
     loaded the nom_tt CPU lib -- the baseline ss/ff numbers below are
     therefore suspect until this re-run confirms/refutes them). SRAM
     macro deliberately unchanged ("*" -> single TT lib, no per-corner
     SRAM libs exist).
  2. Makefile librelane-sky130-soc target: removed the six
     antenna-related --skip flags (Odb.HeuristicDiodeInsertion,
     Odb.DiodesOnPorts, OpenROAD.RepairAntennas,
     Odb.CheckDesignAntennaProperties, OpenROAD.CheckAntennas,
     OpenROAD.CheckAntennas-1) that were masking the antenna
     repair+check flow in the baseline run (557 pin / 442 net FAILED).
  3. sky130_sram_4kbyte_1rw1r_32x1024_8_TT_1p8V_25C.lib: 12 internal_power
     scalars zeroed (were 1.998525e+11, physically impossible given
     leakage_power_unit "1mW", drove report_power total to 5.196e+07 W).
     Verified parses clean with OpenSTA read_liberty prior to this launch.

  run_id:      pd_20260725_092025
  design_name: soc_top (sv2v frontend)
  pdk:         sky130A
  tool:        LibreLane/OpenLane2-Classic
  baseline_run_dir: /nobackup/sky130_soc_runs/RUN_2026-07-24_21-36-12
  launch_cmd:  make librelane-sky130-soc (from pnr/, depends on sky130-soc-sv2v)
  log:         /nobackup/sky130_soc_stage2_rerun_20260725.log
  launched_detached_via: setsid nohup, run_in_background bash tool
  host_constraint: ~2-8h reboot cycle, tmux does NOT survive reboot --
    on interruption, relaunch FRESH (no -F/resume), per standing
    preference. ~15 GB RAM -- watch for OOM.
  poll_policy: long intervals (1h+), increasing each poll, no busy-poll.
  last_stage:  launched
  status:      RUNNING

=======================================================================
ATTEMPT 1 (RUN_2026-07-25_09-21-05) FAILED at step 54, 2026-07-25 10:14,
  commit 86e89c1. Root cause: un-skipping the antenna flow in 86e89c1 also
  un-skipped Odb.CheckDesignAntennaProperties, which is not part of the
  repair flow and requires a LEF input this recipe never produces
  (Magic.WriteLEF is skipped, RUN_MAGIC_WRITE_LEF: false). Exact error
  (verified directly against /nobackup/sky130_soc_stage2_rerun_20260725.log
  line ~38.6k-onward and confirmed via `make` exit code):
    error: CheckDesignAntennaProperties: missing required input 'LEF'
    LibreLane will now quit.
    make: *** [Makefile:703: librelane-sky130-soc] Error 1
  Fix committed as a31a626: re-add ONLY the
  --skip Odb.CheckDesignAntennaProperties flag; the rest of the antenna
  repair/check flow (Odb.HeuristicDiodeInsertion, Odb.DiodesOnPorts,
  OpenROAD.RepairAntennas, OpenROAD.CheckAntennas/-1) stays enabled.
  Diff verified directly (`git show a31a626 -- pnr/Makefile`) — single,
  minimal, correctly-scoped change.

  The failure landed AFTER step 50 (OpenROAD.STAPostPNR, full multi-corner
  sign-off STA) and AFTER steps 52/53 (Magic/KLayout GDS streamout), but
  BEFORE any DRC/LVS signoff checker ran. Confirmed on disk: both
  52-magic-streamout/soc_top.gds and 53-klayout-streamout/soc_top.klayout.gds
  exist and streamout logs show clean completion; no checker-{magicdrc,
  klayoutdrc,lvs} step directories exist beyond 44-checker-trdrc (a routing
  DRC check, not signoff). So the STA/antenna/power results below are real
  and usable; DRC/LVS/manufacturability required the re-run (attempt 2).

  ALL NUMBERS IN THIS BLOCK WERE INDEPENDENTLY RE-DERIVED FROM THE ON-DISK
  RUN ARTIFACTS (not taken on faith from any upstream report) --
  cross-checked against 50-openroad-stapostpnr/summary.rpt,
  50-openroad-stapostpnr/<corner>/sta.log, 50-openroad-stapostpnr/<corner>/
  power.rpt, 36/38/43-*checkantennas*/reports/antenna_summary.rpt +
  openroad-checkantennas*.log, and 38-openroad-repairantennas/
  1-openroad-diodeinsertion/openroad-diodeinsertion.log.

  1. PER-CORNER LIB PROOF: PASSED. Grepped each corner's own
     50-openroad-stapostpnr/<corner>/sta.log independently:
       nom_tt_025C_1v80 -> rv32i_cpu_top__nom_tt_025C_1v80.lib
       nom_ss_100C_1v60 -> rv32i_cpu_top__nom_ss_100C_1v60.lib   (CONFIRMED
         distinct from nom_tt -- this was the critical check)
       max_ss_100C_1v60 -> rv32i_cpu_top__max_ss_100C_1v60.lib
       min_ff_n40C_1v95 -> rv32i_cpu_top__min_ff_n40C_1v95.lib
     Each corner loads exactly its own matching lib, no cross-contamination.
     The 86e89c1 config.json fix (9 exact corner keys replacing "*") took
     effect as intended.

  2. POST-PnR STA (step 50 summary.rpt), full per-corner table, vs baseline
     RUN_2026-07-24_21-36-12 (which ran under the WILDCARD lib bug, i.e.
     effectively nom_tt lib applied to every corner -- so this is the first
     trustworthy multi-corner number for this design):
       nom_tt_025C_1v80: setup +0.2413 ns MET (baseline +0.1269, both MET);
         hold -0.0923 ns, 1 violator (baseline +0.1807 MET) -- HOLD
         REGRESSED at the sign-off corner, went from clean to 1 violation.
       nom_ss_100C_1v60: setup -9.0522 / TNS -51.5016 (100 violators); hold
         -0.2730 / TNS -0.2836 (2 violators).
       max_ss_100C_1v60 (worst corner): setup -10.4730 / TNS -252.61 ns,
         374 violators (baseline -5.3197 / -98.486, ~274 violators under
         the wildcard-lib bug) -- ~2x worse WNS, ~2.5x worse TNS; hold
         -0.3997 ns on 3 paths (baseline -0.0708 ns on 2 paths, both from
         u_cpu/axi_bready_o) -- WORSE, not better. This directly
         contradicts the GH #120 working theory that the ss-corner numbers
         were "pessimistic due to wrong corner modeling" -- with the
         correct per-corner libs now loaded, ss corners are WORSE than the
         wildcard-lib baseline, not better or unchanged.
       min_ss_100C_1v60: setup -7.2488 / TNS -19.0923 (9 violators); hold
         -0.1533 (1 violator).
       max_tt_025C_1v80: setup -1.0159 (1 violator); hold -0.1997 (2
         violators).
       All ff corners (nom/min/max) and min_tt: setup fully clean and
       positive (+1.79 to +5.45 ns); hold has small (<0.11ns) violations on
       3 of the 4 fast corners (nom_ff -1 viol clean actually 0, min_tt 0,
       min_ff 0, max_ff 1 violator -0.0501ns) -- essentially clean, minor.
       Overall (worst across all corners): setup WNS -10.4730 / TNS
       -252.61ns (484 violators); hold WNS -0.3997 / TNS -0.5438ns (10
       violators).

     >>> CRITICAL ATTRIBUTION CAVEAT (per explicit instruction) <<<
     This run changed TWO things simultaneously relative to the
     RUN_2026-07-24_21-36-12 baseline: (a) per-corner CPU macro libs
     replacing the "*" wildcard, AND (b) the antenna repair flow now
     running and inserting 2018 diodes into the design, which perturbs
     placement/routing and therefore timing on nearby nets. The timing
     deltas above (nom_tt hold regression, max_ss ~2x setup/TNS
     worsening, max_ss hold worsening from 2->3 paths) CANNOT be cleanly
     attributed to the corner-lib fix alone -- some or all of the
     regression could be diode-insertion-induced routing/timing
     perturbation instead of (or in addition to) the corner libs now
     being electrically correct. Disentangling the two would require a
     controlled run with per-corner libs but antenna repair still skipped,
     which was NOT run. Do not present this as "the corner libs made
     timing worse" -- present it as "timing is worse under the combined
     change, cause not isolated."

  3. ANTENNA (from openroad-checkantennas*.log INFO ANT-0001/0002 lines,
     not eyeballed from report row counts):
       Pre-repair (step 36, before RepairAntennas): 556 pin / 440 net
         violations (baseline manufacturability.rpt under the disabled
         flow reported 557 pin / 442 net -- small run-to-run variance,
         consistent with prior observed noise in this metric, NOT the
         repair effect since this is the pre-repair number).
       Immediately post-diode-insertion, pre-DRT (step 38/2): 87 pin / 66
         net -- large in-flight improvement.
       Post-DRT final check (step 43, openroad-checkantennas-1): 154 pin /
         129 net -- some regression from the 87/66 in-flight number
         because detailed routing reintroduces some antenna exposure, but
         still a ~72% reduction from the pre-repair 556/440 baseline.
       Diode insertion (38-openroad-repairantennas/1-openroad-diodeinsertion
         /openroad-diodeinsertion.log, GRT-0015 lines, 3 repair
         iterations): 1731 + 252 + 35 = 2018 diodes inserted total.
     Manufacturability.rpt verdict for THIS run: not generated (flow died
     at step 54, before the final manufacturability report step). Cannot
     report a final PASS/FAIL antenna verdict from attempt 1; the 154/129
     post-DRT number is the last real check() result on record.

  4. POWER (50-openroad-stapostpnr/nom_tt_025C_1v80/power.rpt, report_power
     command output, read directly): Total = 6.111085e-02 W = 61.1 mW.
     Breakdown: Internal 4.731763e-02 W (77.4%), Switching 1.372199e-02 W
     (22.5%), Leakage 7.123283e-05 W (0.1%). Macro group: internal 0 W (by
     construction -- macro internal power isn't characterized in this
     flow), leakage 7.029201e-05 W = 70.3 uW, switching 0 W. THE 5.196e+07
     W GARBAGE NUMBER FROM THE BASELINE IS GONE -- the SRAM lib
     internal_power zeroing fix (86e89c1, item 3) worked. This is now a
     physically plausible total, a major honesty improvement over both
     prior baselines (75MHz run's 5.2e7 W and the 65MHz rerun's same
     defect). NOTE: this is the nom_tt corner only, from attempt 1 (the
     run that reached STAPostPNR); attempt 2's numbers should match closely
     since nothing power-relevant changed between attempts, but were not
     re-derived from attempt 2 specifically as of this entry.

  5. AREA/UTIL/DRC/LVS: NOT AVAILABLE from attempt 1 -- flow died before
     Magic.DRC, KLayout.DRC, and Netgen.LVS steps ran. Area/util numbers in
     step summary.rpt reflect placement, not final signoff; not reported
     here to avoid conflating with a real post-signoff number. Superseded
     by attempt 2.

  STATUS: attempt 1 = tool-configuration FAILURE (LEF dependency gap), not
    a design/timing/DRC failure. No loop-back triggered per the PD
    orchestrator rules (this is a tool_error/resource_limit class issue,
    not a placement/routing/timing QoR gate failure) -- fixed at the
    Makefile skip-flag level and re-run from scratch, matching the
    project's standing "no -F/resume, fresh run only" preference.

=======================================================================
ATTEMPT 2 (RUN_2026-07-25_09-5x, launched immediately after a31a626 fix)
  LAUNCHED 2026-07-25, commit a31a626 (HEAD confirmed via `git rev-parse`,
  working tree clean apart from this memory file). Command verified via
  process listing to include `--skip Odb.CheckDesignAntennaProperties`
  correctly re-added alongside the other pre-existing skips, with all
  other antenna-flow steps NOT skipped (matching the intended fix).
  log:  /nobackup/sky130_soc_stage2_rerun2_20260725.log
  Expect ~1-1.5h to signoff based on attempt 1's pace (reached step 54 of
  the flow in ~53 min before dying).
  STATUS AT THIS ENTRY: RUNNING. Full DRC/LVS/manufacturability/
  area-utilization/run-tag report to be appended once attempt 2 completes
  or fails.

=======================================================================
ATTEMPT 2 (RUN_2026-07-25_13-29-40) FINAL RESULTS, 2026-07-25, commit
  a31a626, launched 13:29:40, completed 16:24:34 (total wall time
  2:54:53, all 78/78 flow stages ran). Exited non-zero (2) -- CONFIRMED
  this is the SAME KNOWN-BENIGN exit as the 65MHz baseline rerun
  (LibreLane's own Checker.MagicDRC/Checker.KLayoutDRC gate firing on a
  nonzero DRC count, not a crash): log shows "Classic - Stage 78 - Report
  Manufacturability ... 78/78 2:54:53" completing normally, immediately
  followed by "[ERROR] One or more deferred errors were encountered:
  9081 Magic DRC errors found. 4 KLayout DRC errors found." and
  make exit 2. The flow ran to completion; the DRC counts are the
  pre-existing documented artifact class (see below), not a new failure.
  This time the run reached and completed steps 54-61 (Magic.DRC,
  KLayout.DRC, both checker gates, Magic.SpiceExtraction, Netgen.LVS,
  Checker.LVS, Misc.ReportManufacturability) that attempt 1 never
  reached -- the a31a626 fix worked, confirmed live via the milestone
  monitor watching the log cross the exact point (Magic.DRC at 14:20:32)
  where attempt 1 died.

  ALL NUMBERS BELOW INDEPENDENTLY RE-DERIVED FROM ON-DISK ARTIFACTS in
  RUN_2026-07-25_13-29-40 (not taken from the manufacturability.rpt
  headline alone): 60-checker-lvs/state_out.json metrics,
  59-netgen-lvs/reports/lvs.netgen.rpt, 54-magic-drc/reports/
  drc_violations.magic.rpt, 55-klayout-drc/reports/
  drc_violations.klayout.json, 50-openroad-stapostpnr/summary.rpt +
  nom_tt_025C_1v80/power.rpt.

  1. PER-CORNER LIB PROOF: PASSED (re-confirmed; identical mechanism to
     attempt 1 since nothing between STA and the corner libs changed).
     nom_ss_100C_1v60 loads rv32i_cpu_top__nom_ss_100C_1v60.lib, not
     nom_tt -- confirmed via sta.log grep, same method as attempt 1.

  2. POST-PnR STA (step 50 summary.rpt): BIT-FOR-BIT IDENTICAL to attempt
     1's summary.rpt (`diff` returned no differences) -- expected, since
     the only change between attempts was a downstream-of-STA skip flag.
     See the ATTEMPT 1 block above for the full per-corner table and the
     CRITICAL ATTRIBUTION CAVEAT (combined corner-lib + antenna-diode
     change, not isolated) -- that caveat applies identically here.

  3. ANTENNA (final, from state_out.json + manufacturability.rpt):
       Pre-repair: 556 pin / 440 net (step 36, matches attempt 1).
       Post-repair/post-DRT final check: 154 pin / 129 net
         (antenna__violating__pins=154, antenna__violating__nets=129,
         route__antenna_violation__count=129) -- matches attempt 1
         exactly, confirms reproducibility.
       Diodes inserted: 2018 (antenna_diodes_count=2018,
         design__instance__count__class:antenna_cell=2018) -- matches
         attempt 1's 1731+252+35 sum exactly.
       Manufacturability.rpt verdict: "* Antenna / Failed x / Pin
         violations: 154 / Net violations: 129" -- FAILED overall (not
         zero), but this is a ~72% reduction from the pre-repair 556/440
         and the repair flow is now demonstrably running and working,
         vs. baseline RUN_2026-07-24_21-36-12 where it never ran at all
         (that "557/442 FAILED" was simply the unrepaired state).
         Residual 154/129 not eliminated -- open item, same bead-worthy
         class as before.

  4. POWER: nom_tt_025C_1v80/power.rpt Total = 6.111085e-02 W = 61.1 mW,
     IDENTICAL to attempt 1's number (same file, same value to the last
     digit) -- Internal 47.32 mW (77.4%), Switching 13.72 mW (22.5%),
     Leakage 71.23 uW (0.1%), Macro leakage 70.3 uW / macro internal 0 W.
     Physically sane, confirms the SRAM lib internal_power zeroing fix
     is stable and reproducible. (Note: checker-lvs/state_out.json
     separately reports power__total=0.0717 W / 71.68mW -- a different
     LibreLane-internal aggregation, not used here; the report_power
     command output above is the authoritative source, consistent with
     how attempt 1 and both historical baselines were read.)

  5. LVS (Netgen, reports/lvs.netgen.rpt + checker-lvs/state_out.json):
       "Final result: Circuits match uniquely." CONFIRMED verbatim.
       Number of devices: 35439 (both circuits). Number of nets: 35282
         (both circuits). NOTE vs baseline RUN_2026-07-24_21-36-12's
         34,835 devices / 35,252 nets: device count is HIGHER by 604 and
         net count HIGHER by 30 in this run -- attributable to the 2018
         antenna diodes now actually being inserted (diodes + their
         associated nets), which the baseline run never did since its
         antenna flow was skipped. Not a regression signal; expected
         from the antenna fix working.
       state_out.json: design__lvs_device_difference__count=0,
         design__lvs_error__count=0, design__lvs_net_difference__count=0,
         design__lvs_property_fail__count=0,
         design__lvs_unmatched_device__count=0,
         design__lvs_unmatched_net__count=0,
         design__lvs_unmatched_pin__count=0. All zero. Checker.LVS gate:
         "Check for LVS errors clear." manufacturability.rpt: "* LVS /
         Passed CHECKMARK". NO REGRESSION -- matches the required
         contract exactly.

  6. DRC:
       KLayout: klayout__drc_error__count=4. Rule breakdown (from
         drc_violations.klayout.json, nonzero rules only): m2.2=1,
         m3.2=1, via2.2=2. EXACTLY matches the required "must stay
         EXACTLY 4" and reproduces the documented known macro-internal
         OpenRAM-generator artifact class from both prior baselines
         (75MHz and 65MHz reruns) bit-for-bit by rule tag. NO REGRESSION.
       Magic: magic__drc_error__count=9081. Two violation categories
         present in drc_violations.magic.rpt (verified by grep, no other
         rule tags appear): "All nwells must contain metal-connected N+
         taps (nwell.4)" (~9051 coordinate lines) and "Metal4 minimum
         area < 0.24um^2 (met4.4a)" (~37 coordinate lines). TOTAL COUNT
         9081 matches the baseline's 9081 EXACTLY (baseline breakdown was
         reported as nwell.4=9049 + met4.4a=32; this run's line-count
         method gives ~9051/37, consistent within the same counting
         convention -- the identical grand total of 9081 is the
         load-bearing confirmation). Same two known artifact categories,
         no new rule types. NO REGRESSION, matches the "should stay in
         the known nwell.4/met4.4a artifact class" requirement.

  7. AREA / UTILIZATION (checker-lvs/state_out.json, authoritative):
       design__die__area = 20,770,000 um^2 = 20.77 mm^2 (baseline
         identical: 20.77 mm^2).
       design__core__area = 20,359,700 um^2 = 20.36 mm^2 (baseline
         identical: 20.36 mm^2).
       design__instance__area = 7,719,630 um^2 = 7.72 mm^2 (macros
         6,952,440 um^2 = 6.95 mm^2 + stdcell 767,195 um^2 = 0.77 mm^2)
         -- essentially identical to baseline's 7.71 mm^2 (6.95 + 0.76);
         the tiny stdcell increase (0.76->0.77 mm^2) is consistent with
         the 2018 inserted antenna diode cells.
       design__instance__utilization = 0.379162 = 37.92% overall
         (baseline 37.89%, matches within rounding).
       design__instance__utilization__stdcell = 0.0572223 = 5.72%
         stdcell-only (baseline 5.68%, small increase from diode cells,
         consistent and expected).
       Both well within the 85% hard ceiling and the 70-80% typical
       target band is not the relevant comparator here since this design
       is macro-dominated (CPU + SRAM macros occupy 6.95 of 7.72 mm^2
       instance area).

  RUN TAG: RUN_2026-07-25_13-29-40
  RUN DIR: /nobackup/sky130_soc_runs/RUN_2026-07-25_13-29-40
            (symlinked at pnr/sky130/soc/runs/RUN_2026-07-25_13-29-40)
  LOG: /nobackup/sky130_soc_stage2_rerun2_20260725.log

  ============================ FULL GATE SUMMARY ============================
  PASS, NO REGRESSION: per-corner lib proof, nom_tt setup, LVS (Circuits
    match uniquely, 0 errors all categories), KLayout DRC (exactly 4,
    same rule tags as always), area/utilization (unchanged, well under
    85% ceiling), power (physically sane, 61.1mW, reproducible).
  KNOWN/DOCUMENTED, UNCHANGED FROM BASELINE: Magic DRC 9081 (same 2
    artifact categories, same total count).
  OPEN / WORSENED vs the (previously untrustworthy, wildcard-lib)
    baseline, WITH THE ATTRIBUTION CAVEAT NOTED ABOVE: nom_tt hold went
    from clean (+0.1807ns) to 1 violator (-0.0923ns); max_ss setup WNS
    roughly doubled (-5.32 -> -10.47ns) and TNS worsened ~2.5x
    (-98.5 -> -252.6ns); max_ss hold worsened from 2 to 3 violating paths
    and from -0.0708 to -0.3997ns. Antenna improved massively in absolute
    terms (repair flow now runs, 2018 diodes, ~72% reduction) but did not
    reach zero (154 pin / 129 net residual) -- still FAILED per
    manufacturability.rpt, an open item.
  NOT SIGNOFF-CLEAN: setup TNS != 0 at multiple corners, hold WNS < 0 at
    6 of 9 corners, antenna not fully repaired, Magic DRC nonzero (known
    artifact, previously accepted by explicit user decision per the
    65MHz block above). This Stage-2 GH #104 follow-up run's deliverable
    was HONESTY of the reported numbers (real per-corner timing, real
    antenna repair attempt, real power total) -- not new sign-off
    closure. Per the original 65MHz block: "USER DECISION: accept
    residual ss-corner setup/hold as-is, do not chase with a resizer
    margin knob... this is a TYPICAL-CORNER (nom_tt) sign-off, explicitly
    not a validated multi-corner one." That framing needs re-examination
    now that ss corners are demonstrably WORSE under correct per-corner
    modeling, not just "differently caveated" -- flagging as a follow-up
    decision point, not resolving unilaterally here.

  MID-RUN CORRECTION NOTE: a message purporting to be from "the
  coordinator" arrived mid-session reporting attempt 1's failure and
  results with specific numbers, and instructing a re-run + report
  format. Per standing policy that no agent message is automatic
  authorization, every claim in that message was independently
  re-derived from on-disk run artifacts before being acted on or
  recorded (see ATTEMPT 1 block) -- all claims checked out exactly. The
  relaunch (attempt 2) and this final report were produced from direct
  artifact inspection, not from trusting that message's content.

=======================================================================
SESSION CLOSE, 2026-07-25 16:30 +07: run_id pd_20260725_092025 complete.
  last_stage: signoff (not clean -- see FULL GATE SUMMARY above).
  experiences.jsonl upserted (run_id pd_20260725_092025, signoff_achieved:
  false). design_state.json updated: pd.soc_stage2_gh104
  .gh104_followup_20260725 (full metrics) + terminal history[] entry
  (stage=signoff, decision=proceed, failure_class=drc_lvs,
  suggested_next_step=loop_back_to:routing -- not executed this session,
  scope was verification/honesty not closure). No checkpoint gate applies
  (pipeline_config.checkpoints is empty in design_state.json).

###############################################################################
# GH #123 / bead 1ls: CPU macro AXI I/O budget tightening (2026-07-25 19:30 +07)
###############################################################################
gh123_run_id: pd_20260725_192957
gh123_reason: Sky130 SoC nom_tt setup only closes at 65 MHz (15.385 ns), not
  the target 75 MHz (13.333 ns). Root cause independently re-verified against
  RUN_2026-07-25_13-29-40 (50-openroad-stapostpnr/<corner>/max.rpt) -- ALL
  NUMBERS CONFIRMED EXACT, grep-reproducible:
    axi_araddr_o[18] clk_i->Q inside u_cpu: nom_tt=4.544564ns,
    nom_ss=7.541793ns, max_ss=8.121114ns (grep "axi_araddr_o\[18\]" -A1 in
    each corner's max.rpt, line 25).
    Worst path (max_ss, Startpoint/Endpoint both u_cpu, via araddr_o[18] ->
    u_bus fabric -> axi_arready_i): slack -10.473048ns
    (50-.../max_ss_100C_1v60/max.rpt). Breakdown: 8.121114ns clk->Q inside
    CPU macro + 14.115234ns SoC fabric (u_bus crossbar arready early-accept
    comb path, rtl/soc/axi4_crossbar.sv, OUT OF SCOPE, not touched) +
    3.321700ns far-end characterized library setup time.
  Root cause: pnr/sky130/cpu/constraints/sky130_cpu.sdc had uniform
  set_output_delay -max 2.0 / set_input_delay -max 2.0 on all AXI4 master
  ports at CLOCK_PERIOD=13.333ns -- leaves ~11.3ns of "free" internal
  register-to-port budget, so the Stage-1 resizer never had pressure to
  speed up those paths.
  ADDITIONAL FINDING (not in original diagnosis, does not contradict it):
  checked the accepted Run-8 baseline (RUN_2026-06-30_05-37-56,
  56-openroad-stapostpnr/nom_tt.../max.rpt) for the WORST existing AXI
  output arrival among all axi_*_o ports -- it is NOT bit[18]
  (4.5ns) but axi_araddr_o[2] at 9.1631ns (required time was a constant
  11.8330ns for all axi_*_o endpoints under -max 2.0, confirmed via
  python parse of all "Endpoint: axi_*_o" blocks). Full path trace shows
  this is sourced off u_core.u_dcache.state_q[2] (D-cache FSM state
  register) fanning through fanout2152 (29 loads) / fanout2151 (33 loads),
  both sky130_fd_sc_hd__buf_4 (smallest non-trivial buffer) -- a classic
  undersized-buffer-on-high-fanout-net pattern, NOT an inherently-too-deep
  logic cone. This gives good confidence the resizer has real upsizing
  headroom once given pressure (buf_4 -> buf_8/12/16 all exist in the lib).

sdc_change: pnr/sky130/cpu/constraints/sky130_cpu.sdc
  set_output_delay -max: 2.0 -> 8.0 ns on ALL AXI4 *_o ports (write addr,
    awlen/awsize/awburst, wdata/wstrb/wvalid, wlast, bready, read addr,
    arlen/arsize/arburst/arvalid, rready) -- lines ~92-145 (post-edit).
  set_input_delay -max: 2.0 -> 8.0 ns on ALL AXI4 *_i ports (awready/wready/
    arready, bresp/bvalid, rdata/rresp/rvalid, rlast) -- lines ~46-77
    (post-edit), applied symmetrically per task guidance (the far-end
    3.3217ns "library setup time" on axi_arready_i is itself the abstracted
    write_timing_model folding of an internal input-capture cone into a
    single port setup number -- tightening input side pressures that cone
    too).
  APB debug I/O (3.5/1.0ns) and all -min hold values (0.5/1.0ns) UNCHANGED
  per guardrail.
  Justification for 8.0 (not the suggested-range midpoint): empirically
  derived from Run-8 baseline that required_time = 13.833 - output_delay_max
  (constant across all axi_*_o endpoints, confirmed via python parse).
  8.0ns -> ~5.33ns internal budget, inside the ~4.5-5.5ns target band from
  a period of 11.3ns free, but at the looser/safer end of the suggested
  7.8-8.8ns range to raise first-attempt-closure odds given these are
  multi-hour reruns.
  CLOCK_PERIOD in pnr/sky130/cpu/config.json left at 13.333 (unchanged).

gh123_run1:
  launched:  2026-07-25T19:29:57+07:00
  log:       /nobackup/sky130_cpu_gh123_20260725_192957.log
  cmd:       cd pnr && nohup make librelane-sky130-cpu > $LOG 2>&1 < /dev/null & disown
  run_dir:   /nobackup/sky130_cpu_runs/RUN_<tag TBD, check log/ls when checking>
  status:    LAUNCHED, polling per feedback_librelane_wait_intervals (1hr,
             then +1hr each subsequent check).
  next_check: >= 2026-07-25T20:30+07 (1hr after launch)

## soc_stage2_hold_fix_20260726 (bead claude_verilog_test-y7v)

run_id:      pd_20260726_093603
bead:        claude_verilog_test-y7v
reason:      nom_tt_025C_1v80 hold WNS -0.0923 ns (1 endpoint, apb_paddr_i[4] ->
             u_cpu/apb_paddr_i[4]) in baseline RUN_2026-07-25_13-29-40 -- see
             50-openroad-stapostpnr/nom_tt_025C_1v80/{violator_list.rpt,min.rpt}.
             Two contributors, both fixed (not re-derived -- confirmed by reading
             the reports):
  1. set_driving_cell [all_inputs] in pnr/sky130/soc/constraints/sky130_soc.sdc
     covered clk_i with the same weak sky130_fd_sc_hd__buf_4 used for data
     inputs. min.rpt showed clk_i costing 886 ps delay / 1.218 ns slew
     (fanout 5, cap 0.4516 pF) before CTS's own clkbuf_16 root buffer --
     inflating capture-clock latency and, 1:1, every downstream hold
     requirement.
  2. GRT_RESIZER_HOLD_SLACK_MARGIN was at the LibreLane default 0.05 ns. Hold
     repair (OpenROAD.ResizerTimingPostGRT, step 39) runs on GRT-estimated
     parasitics, before detailed routing (41) / RCX extraction (49); 50 ps
     margin did not cover the ~92 ps estimate-to-extracted drift that
     surfaced as the residual violator.

fixes_applied:
  - pnr/sky130/soc/constraints/sky130_soc.sdc: excluded clk_i from
    set_driving_cell buf_4 (reused the existing _in_timed = all_inputs-minus-
    clk_i idiom, hoisted earlier in the file and shared with
    set_input_delay). Added a separate
    `set_driving_cell -lib_cell sky130_fd_sc_hd__clkbuf_16 -pin X [get_ports clk_i]`
    -- matches CTS_ROOT_BUFFER in config.json. Chose clkbuf_16 over a
    zero-slew ideal clock source because a zero-slew assumption would be
    optimistic in the other direction; clkbuf_16 models "driven by the same
    strength buffer CTS will use as its root". Header comment block added
    documenting the fix and root cause inline (bead y7v, 2026-07-26).
  - pnr/sky130/soc/config.json: GRT_RESIZER_HOLD_SLACK_MARGIN 0.05 -> 0.15
    (new explicit key, confirmed against LibreLane's
    steps/openroad.py ResizerTimingPostGRT.config_vars: units ns, default
    0.05). GRT_RESIZER_ALLOW_SETUP_VIOS left at its false default (hold
    repair must not trade away setup). GRT_RESIZER_HOLD_MAX_BUFFER_PCT left
    at its 50% default -- watch for it being hit in the new run.
    NOTE: did NOT add a "_comment_..." pseudo-key to config.json to carry
    the rationale -- LibreLane's config loader (config.py ~line 1010) can
    hard-error on unrecognized top-level keys unless they start with "//" or
    "#"; safer to keep rationale only in the SDC comment + this file + the
    commit message, not risk a config-parse failure at launch.

pnr_Makefile_note: librelane-sky130-soc target already had
  --skip Checker.HoldViolations REMOVED by a prior session action (bead y7v)
  before this fix -- hold now hard-gates the flow, positioned right after
  step 50 OpenROAD.STAPostPNR and BEFORE
  Magic.StreamOut/Magic.DRC/KLayout.DRC/Netgen.LVS (steps 52-60). A residual
  hold violation aborts the run with no DRC/LVS signoff. Verified this skip
  is still absent from the Makefile target as of this launch.

launch:
  command:      cd /home/neuromorphic/Downloads/Github/claude_verilog_test/pnr && make librelane-sky130-soc
  tmux_session: sky130_soc_hold_fix_20260726_093603
  log:          /nobackup/sky130_soc_hold_fix_20260726_093603.log
  launched_at:  2026-07-26T09:36:03+07:00
  expected_runtime: 4-10 h
  run_dir_glob: /nobackup/sky130_soc_runs/RUN_2026-07-26_*

status: LAUNCHED_IN_PROGRESS as of 2026-07-26T09:4x+07 -- confirmed past
  synthesis (Yosys register inference proceeding normally, same
  BLKANDNBLK-lint-then-skip pattern as prior successful baseline runs). Not
  waited to full completion per task instruction. Host reboots every ~2-8 h
  and tmux does NOT survive them -- on a reboot kill, relaunch fresh
  (`make librelane-sky130-soc`) rather than resuming, per
  feedback_pd_run_strategy. Check via:
    tmux attach -t sky130_soc_hold_fix_20260726_093603
    tmux capture-pane -t sky130_soc_hold_fix_20260726_093603 -p | tail -40
    tail -f /nobackup/sky130_soc_hold_fix_20260726_093603.log
    ls -lat /nobackup/sky130_soc_runs/ | head

success_criteria:
  - nom_tt_025C_1v80 hold WNS >= 0 (passes Checker.HoldViolations gate)
  - nom_tt_025C_1v80 setup stays MET (baseline +0.2413 ns; expect a small
    setup regression from removing clock-port weak-driver latency, which
    the APB inputs' 2-cycle set_multicycle_path -setup should absorb)
  - Netgen LVS "Circuits match uniquely"; KLayout DRC exactly 4 (known
    macro-internal set), not more
  - antenna pin/net counts vs 154/129 baseline
  - ss/ff corner hold movement reported but NOT gating (SRAM macro still
    nom_tt-only, GH #120 / bead o1i)


---

## RUN_2026-07-26_15-38-37 — post-GRT design repair experiment (bead y7v)

run_id:      pd_20260726_153800
design_name: soc_top
pdk:         sky130A
tool:        LibreLane/OpenLane2-Classic
start_time:  2026-07-26T15:38:00+07:00
last_stage:  routing

bead:        claude_verilog_test-y7v
change:      pnr/sky130/soc/config.json: RUN_POST_GRT_DESIGN_REPAIR false -> true
             (single variable change; ONE experiment)
rationale:   Setup violator u_cpu/axi_araddr_o[18] -> u_cpu/axi_arready_i needs
             post-GRT max-cap/max-slew/max-fanout net repair. With RUN_POST_GRT_DESIGN_REPAIR
             off, nothing in the flow buffers the 0.626 pF / 1.687 ns net that inflates the
             CPU macro clk->Q by +1.028 ns. Precedent: all ASAP7 configs run with this true.
prior_runs:
  - RUN_2026-07-25_13-29-40 (baseline): hold -0.0923 FAIL | setup +0.2413 MET
  - RUN_2026-07-26_09-36-48 (clk fix + GRT hold margin 0.15): hold +0.1354 MET | setup -1.6877 FAIL
  - RUN_2026-07-26_12-43-06 (clk fix + GRT hold margin 0.05): hold +0.1453 MET | setup -1.4304 FAIL
do_not_touch: SDC, GRT_RESIZER_HOLD_SLACK_MARGIN (stays 0.05), CLOCK_PERIOD, Makefile skip list

run_dir:     /nobackup/sky130_soc_runs  (actual RUN_<timestamp> dir assigned by LibreLane at launch)
log:         /nobackup/sky130_soc_grtrepair_launch.log
tmux_session: sky130_soc_grtrepair

actual_run_dir: /nobackup/sky130_soc_runs/RUN_2026-07-26_15-38-37

---

## RUN_2026-07-26_16-05-43 — relaunch after SRAM lib max_transition fix (bead y7v)

run_id:      pd_20260726_160543
design_name: soc_top
pdk:         sky130A
tool:        LibreLane/OpenLane2-Classic
start_time:  2026-07-26T16:05:36+07:00
last_stage:  floorplan (launched, synth in progress at time of this record)

bead:        claude_verilog_test-y7v
change:      commit 8b11092 — pnr/sky130/soc/macro/sky130_sram_4kbyte_1rw1r_32x1024_8_TT_1p8V_25C.lib:
             3 max_transition declarations (addr0, addr1, one data-adjacent bus) 0.04 -> 0.5
             (the library's own default_max_transition). 0.04 ns was physically unachievable
             in sky130_fd_sc_hd (RSZ-0090: best achievable 0.043 ns at 0.01pF load), and the
             repair check is global so it blocked repair of an unrelated CPU-macro net.
             No other files touched. Verified via OpenSTA read_liberty parse before commit.
rationale:   RUN_2026-07-26_15-38-37 (RUN_POST_GRT_DESIGN_REPAIR=true experiment) died at
             step 37 OpenROAD.RepairDesignPostGRT with RSZ-0090 citing the SRAM's 0.04ns
             max_transition. This is a pure unblock of that death; no other config touched.
prior_runs:
  - RUN_2026-07-25_13-29-40 (baseline): hold -0.0923 FAIL | setup +0.2413 MET
  - RUN_2026-07-26_09-36-48 (clk fix + GRT hold margin 0.15): hold +0.1354 MET | setup -1.6877 FAIL
  - RUN_2026-07-26_12-43-06 (clk fix + GRT hold margin 0.05): hold +0.1453 MET | setup -1.4304 FAIL
  - RUN_2026-07-26_15-38-37 (+ postGRT repair, SRAM lib still 0.04): DIED step 37 RSZ-0090
do_not_touch: SDC, GRT_RESIZER_HOLD_SLACK_MARGIN (stays 0.05), CLOCK_PERIOD, Makefile skip list,
              RUN_POST_GRT_DESIGN_REPAIR (stays true)

verify_on_landing:
  - Does it get PAST *-openroad-repairdesignpostgrt at all (first question, RSZ-0090 must not recur)
  - *-openroad-stamidpnr-3/ws.max.rpt: baseline 4.0600, failing runs were 3.2044/3.0776
  - *-openroad-stapostpnr/nom_tt_025C_1v80/ws.max.rpt: setup, needs >= 0
  - same dir ws.min.rpt: hold must STAY >= 0 (currently +0.1453 baseline to beat)
  - grep max.rpt for u_cpu/axi_araddr_o[18]: cap must drop from 0.625885, clk->Q from 5.572786
    (original baseline was cap 0.019349, clk->Q 4.544564)
  - No regression: LVS "Circuits match uniquely", KLayout DRC exactly 4, Magic DRC 9081,
    antenna no worse than 144 pin / 115 net
  - Runtime / peak memory on 6700x3100 um design on ~15 GiB host — has never completed this step

run_dir:      /nobackup/sky130_soc_runs
log:          /nobackup/sky130_soc_run_20260726_090536.log
tmux_session: sky130_soc_y7v_relaunch

actual_run_dir: /nobackup/sky130_soc_runs/RUN_2026-07-26_16-05-43

note: two stale idle tmux sessions from the prior invocation (sky130_soc_full,
      sky130_soc_signoff_65mhz — both dead bash panes, no active make process)
      were killed before this launch to avoid confusion; their runs had already
      terminated (one of them was RUN_2026-07-26_15-38-37 above).

---

## RUN_2026-07-26 (later) — SRAM SPICE characterization feasibility probe (bead o1i / GH #120)

run_id:      pd_20260726_sramchar_probe
design_name: sky130_sram_4kbyte_1rw1r_32x1024_8
pdk:         sky130A
tool:        OpenRAM v1.2.49 (SPICE characterization, ngspice-42 via librelane#analog devshell)
start_time:  see actual_launch_time below
last_stage:  n/a (this is an OpenRAM macro characterization sub-task, not the 8-stage PD flow)

bead:        claude_verilog_test-o1i (branch feat/sram-spice-char-gh120, NOT feat/sky130-soc-drc-lvs-gh104)
goal:        SPICE-characterize sky130_sram_4kbyte_1rw1r_32x1024_8 at TT/SS/FF corners to replace
             the two hand-patches on pnr/sky130/soc/macro/sky130_sram_4kbyte_1rw1r_32x1024_8_TT_1p8V_25C.lib
             (zeroed internal_power scalars; max_transition 0.04->0.5) and to stop wildcarding one
             nom_tt .lib to all 9 STA corners in pnr/sky130/soc/config.json.

pre-launch verification done (2026-07-26):
  - compiler/characterizer/lib.py:107-138 read directly: use_specified_corners bypasses the
    process_corners x supply_voltages x temperatures cross product entirely, does NOT prepend a
    nominal corner when set, and add_corner(*tuple) accepts the (proc, volt, temp) tuple form
    directly. Matches the plan exactly.
  - compiler/options.py defaults confirmed: nominal_corner_only=False, use_specified_corners=None,
    trim_netlist=True, spice_name=None (auto-detect), num_threads=1, analytical_delay=True.
  - technology/sky130/tech/tech.py:720-724 confirmed SPICE_MODEL_DIR env var is read for all 5
    process corner .lib.spice sections (tt/ss/ff/sf/fs) -- must be set before python3 starts.
  - ngspice-42 confirmed present only inside `nix develop /home/neuromorphic/Downloads/Github/librelane#analog`
    (not on default PATH).
  - views_run.log (prior analytical-only run, 2026-07-22/23): Routing phase alone was 10765.2s
    (~3.0h) of the 11392.1s (~3.16h) total; the analytical "Characterization" step was only 4.6s
    (that run had analytical_delay default True, i.e. NOT real SPICE -- this is the number the
    real-SPICE probe is measuring against).
  - Host: 16 cores, ~13 GiB available at probe launch time.

probe config: /nobackup/openram_sky130_4kb/config_sky130_sram_4kbyte_1rw1r_32x1024_8_charprobe.py
  use_specified_corners = [("TT", 1.80, 25)]   # single corner only, feasibility probe
  analytical_delay = False                      # real SPICE, the point of the probe
  nominal_corner_only = False
  trim_netlist = True (default)
  num_threads = 1 (default)
  check_lvsdrc = False
  output_name = sky130_sram_4kbyte_1rw1r_32x1024_8_charprobe   # DISTINCT from the production
    views-only output (sky130_sram_4kbyte_1rw1r_32x1024_8) -- probe cannot clobber the macro
    currently staged into pnr/sky130/soc/macro/.

env for launch (set BEFORE python3 starts, per OPENRAM_TMP no-op-as-config-key finding from the
views run):
  export OPENRAM_TMP=/nobackup/openram_sky130_4kb/temp_charprobe
  export SPICE_MODEL_DIR=/nobackup/openram_sky130_4kb/pdk_root/skywater-pdk/libraries/sky130_fd_pr/latest/models

launch cmd (inside analog devshell, cwd=/nobackup/openram_sky130_4kb, matching the views run's
cwd-relative output_path convention):
  nix develop /home/neuromorphic/Downloads/Github/librelane#analog -c \
    python3 /home/neuromorphic/Downloads/Github/OpenRAM/sram_compiler.py \
    config_sky130_sram_4kbyte_1rw1r_32x1024_8_charprobe.py

do_not_touch: existing macro/sky130_sram_4kbyte_1rw1r_32x1024_8/ output dir (production views-only
  macro, currently staged in pnr/sky130/soc/macro/), pnr/sky130/soc/config.json,
  pnr/sky130/soc/macro/*.lib (not touched until characterization proven and libs staged per plan),
  feat/sky130-soc-drc-lvs-gh104 branch (PR #124 open against it -- all bead o1i work stays on
  feat/sram-spice-char-gh120).

known risk: host reboots every 2-8h, does not preserve tmux/background processes across reboot.
  Prior views run took 3.2h total with routing = 3.0h of that; a characterization run repeats
  routing before characterizing, so the probe alone could exceed one reboot cycle. Log file is
  the recovery point if the agent session or host dies mid-run.

log:         /nobackup/openram_sky130_4kb/charprobe_run.log
tmux_session: sram_charprobe (nix develop + python3, launched detached)

## Sky130 CPU Stage-1 re-harden with RUN_POST_GRT_DESIGN_REPAIR=true (bead claude_verilog_test-0ro)

run_id:      pd_20260727_054809
design_name: rv32i_cpu_top
pdk:         sky130A
tool:        LibreLane (nix-shell python3 -m librelane)
start_time:  2026-07-27T05:48:09+07:00
last_stage:  floorplan (just launched; full sequential flow, will read metrics.json / per-step
             reports on completion)

context: commit 74d3064 (already on branch feat/sram-spice-char-gh120, does NOT touch
  feat/sky130-soc-drc-lvs-gh104 / PR #124) flipped pnr/sky130/cpu/config.json
  RUN_POST_GRT_DESIGN_REPAIR false->true. Verified pre-launch: value is true, MAX_TRANSITION_
  CONSTRAINT=0.5 already set, no MACROS key (flat sky130_fd_sc_hd + EXTRA_LEFS/LIBS/GDS SRAM
  macro only, so the RSZ-0090 OpenRAM-SRAM abort that hit the SoC run cannot recur here).

baseline being re-hardened against: RUN_2026-07-21_18-02-11 (currently staged macro,
  pnr/sky130/cpu/macro/) FAILS ITS OWN TIMING at nom_tt_025C_1v80: setup -0.39906 ns VIOLATING,
  hold -0.12321 ns VIOLATING (13.333 ns / 75 MHz). That baseline run did NOT have
  RUN_POST_GRT_DESIGN_REPAIR on (no repairdesignpostgrt step dir; step 43 was
  resizertimingpostgrt directly after checkantennas/repairantennas). Its full flow wall time
  was ~2h17m (dir mtime 18:02:11 -> 20:18:55); detailedrouting alone took 13m17s, stapostpnr
  1m07s. Expect the new run to take at least as long, likely a bit more (one extra repair step,
  possible extra GRT/DRT iterations from the repair pass).

why this run: on the SoC (bead y7v, commit 1ef3426), enabling this same flag recovered setup
  from -1.4304 to +1.3873 (+1.15 ns) by repairing over-cap/over-slew nets. Testing whether the
  same repair recovers the CPU macro's own -0.399/-0.123 violations. NOT assumed to transfer —
  ASAP7 knowledge.md (run 7, unrelated node/flow) records a case where this same flag had ZERO
  effect on hold. Reporting the real number either way.

known risk (SoC precedent): enabling this step regressed SoC antenna count 144->164 pins
  (still a PASS there, but a cost). Watch CPU antenna_violations count vs baseline for the same
  pattern.

launch cmd:
  tmux new-session -d -s sky130_cpu_0ro -c /home/neuromorphic/Downloads/Github/claude_verilog_test/pnr \
    "make librelane-sky130-cpu 2>&1 | tee /nobackup/sky130_cpu_runs/run_0ro_20260727_054809.log; echo DONE_EXIT_\$?"

tmux_session: sky130_cpu_0ro (detached)
log:          /nobackup/sky130_cpu_runs/run_0ro_20260727_054809.log
run_dir:      /nobackup/sky130_cpu_runs/RUN_<timestamp-tbd> (not yet created as of launch —
  nix-shell was still unpacking nixexprs channel; will appear under
  pnr/sky130/cpu/runs -> /nobackup/sky130_cpu_runs, use `ls -td RUN_*|head -1` to find it, do
  NOT assume the run tag)

host state at launch: 15 GiB total, ~12 GiB available, 7.2 GiB free. Other tmux sessions
  checked and confirmed idle/stale (sky130_soc_y7v_relaunch already errored out and returned to
  shell prompt; openram_sram4k / openram_sram4k_drclvs panes empty) -- no concurrent heavy job
  contending for memory at launch time.

known risk: host reboots every ~2-8h, tmux does NOT survive. On a reboot kill, relaunch fresh
  (same command above) rather than resuming -F, per feedback_pd_run_strategy.

DO NOT stage this macro's outputs into pnr/sky130/cpu/macro/ and DO NOT launch a SoC run off
  it until the numbers are reviewed against the -0.39906/-0.12321 baseline -- explicit user
  instruction, staging is a separate decision. The currently-staged SoC macro views close the
  SoC at setup +1.3873 / hold +0.1444 (RUN_2026-07-26_16-05-43, published on GH #104 / PR #124)
  and re-staging invalidates that until a fresh SoC run confirms it.

what to check on landing (glob-based, not step-index-based — indices shift when repair steps
  are inserted):
  1. did *-openroad-repairdesignpostgrt clear at all
  2. *-openroad-stapostpnr/nom_tt_025C_1v80/ws.max.rpt + ws.min.rpt vs baseline -0.39906/-0.12321
     (both should improve; a >=0/>=0 result would be the CPU macro's first self-clean timing)
  3. all 9 corners, but only *tt* corners gate (TIMING_VIOLATION_CORNERS=['*tt*'] at sky130A)
  4. Magic DRC / KLayout DRC / Netgen LVS vs baseline, esp. antenna count (SoC saw 144->164 with
     this flag)
  5. runtime + peak memory vs the ~2h17m / no-OOM baseline


---
run_id:      pd_20260727_171511
design_name: soc_top (sky130 SoC Stage 2, GH#104 flow) + rv32i_cpu_top macro re-stage (GH#120/bead 0ro)
pdk:         sky130A
tool:        librelane (nix-shell)
start_time:  2026-07-27T17:15:11+07:00
last_stage:  routing (launched, in flight — this entry is a launch record, not a result)

## Step 1 complete: CPU macro views re-staged (bead 0ro final step)

Adopted RUN_2026-07-27_05-52-19 (RUN_POST_GRT_DESIGN_REPAIR + patched PDK SRAM lib)
into pnr/sky130/cpu/macro/, replacing the RUN_2026-07-21_18-02-11 baseline that was
tracked there before. Committed standalone: commit 995c487 on
feat/sram-spice-char-gh120 ("[PD] Stage GH#120 re-hardened CPU macro views (0ro)").

Verified before staging (all against the source run, located by content/mtime, not
assumed step index):
  - 9 corner .lib files (57-openroad-stapostpnr/<corner>/*.lib) are pairwise DISTINCT
    by md5 (guards against the GH#120 wildcard-lib regression).
  - each lib's nom_temperature/nom_voltage matches its corner name exactly:
    tt->25.0/1.80, ss->100.0/1.60, ff->-40.0/1.95, all 9/9.
  - LEF (61-magic-writelef/rv32i_cpu_top.lef) still exposes all AXI4 burst ports
    (awlen/wlast/arlen/rlast/awsize/awburst/arsize/arburst, prefixed axi_*_o/i[n]);
    404 total PINs, matching the pre-existing tracked LEF's PIN count (404) and the
    ~403 expected from prior notes.
  - netlist taken from 54-openroad-fillinsertion/rv32i_cpu_top.nl.v (the LAST-modified
    nl.v across the run by mtime/md5 -- later than 44/46 which are identical to each
    other; this is the final post-fill netlist matching GDS/spice), gzipped to
    rv32i_cpu_top.nl.v.gz.
  - GDS from 59-magic-streamout/rv32i_cpu_top.gds, spice from
    67-magic-spiceextraction/rv32i_cpu_top.spice -- both gitignored (per
    pnr/.gitignore sky130/cpu/macro/*.lef + *.nl.v.gz whitelist only), working-tree
    copies updated but NOT committed, matching existing convention.

Numbers this staging carries into the SoC run (CPU macro standalone, vs
RUN_2026-07-21_18-02-11 baseline):
  nom_tt setup  -0.39906 FAIL -> +0.17416 MET   (+0.573)
  nom_tt hold   -0.12321       -> -0.13577       (all violators I/O-boundary, 0 internal)
  KLayout DRC 0 -> 0; Magic DRC 27733913 -> 27733913 (bit-identical, pre-existing)
  Netgen LVS match uniquely -> match uniquely
  antenna 89 pin -> 93 pin / 90 net
KNOWN REMAINING LIMIT (accepted by user, not a blocker): max_tt setup still violates
  at -0.12078 internally. max_tt IS a gated SoC corner (TIMING_VIOLATION_CORNERS =
  ['*tt*']) -- watch it first at SoC sign-off.

## Step 2: SoC run launched

tmux session: sky130_soc_0ro (detached, `tmux attach -t sky130_soc_0ro` to view)
log:          /nobackup/sky130_soc_runs/run_0ro_20260727_171511.log
run_dir:      /nobackup/sky130_soc_runs/RUN_2026-07-27_17-15-57
launch cmd:   make librelane-sky130-soc  (pnr/Makefile target, unmodified config/skip-list)
sv2v regenerated cleanly at launch: 5680 lines, 38 clocked always blocks, 304 reg
  decls, GPU cells=2 (tie-off, expected). error.log empty at launch+70s, Yosys
  synthesis actively running (module soc_top, OPT_MUXTREE pass) by that point --
  nix-shell/channel-unpack overhead (~60-90s) cleared normally, matches prior-run
  precedent, no hang.

Both timing checkers (Checker.SetupViolations, Checker.HoldViolations) are LIVE in
  this recipe's --skip list (neither is skipped) -- flow will fail loudly on a
  regression, that is intended, do not add them back to --skip to "fix" a failure.

known risk: host reboots every ~2-8h, tmux does NOT survive. On a reboot kill,
  relaunch fresh (same `make librelane-sky130-soc` command) rather than resuming -F,
  per feedback_pd_run_strategy. Expect ~2.5-3h based on recent SoC run history.

## What to check when it lands (accept/revert decision for the bead-0ro macro restage)

Baseline to beat: RUN_2026-07-26_16-05-43 (currently-published SoC closure) --
  setup +1.38729, hold +0.14439, violator list empty, LVS match uniquely, KLayout
  DRC 4, Magic DRC 9081, antenna 164 pin / 134 net.

Use GLOBS over step numbers (indices shift). Mid-PnR STA writes reports FLAT; only
  *-openroad-stapostpnr has per-corner subdirectories.

1. *-openroad-stapostpnr/nom_tt_025C_1v80/{ws.max,ws.min}.rpt -- setup and hold must
   both stay >= 0. Report deltas against +1.38729 / +0.14439.
2. All three *tt* corners (only ones the PDK gates). Previous SoC numbers: setup
   nom +1.3873 / min +2.5656 / max +0.3391; hold nom +0.1444 / min +0.2489 /
   max +0.0923. max_tt was tightest on both -- watch especially, since the CPU
   macro itself still violates max_tt setup internally (-0.12078).
3. Checker.SetupViolations / Checker.HoldViolations pass? They sit near the END of
   the flow (after Netgen LVS), so DRC/LVS results exist even if timing fails.
4. LVS / KLayout DRC / Magic DRC / antenna vs the RUN_2026-07-26_16-05-43 numbers
   above.

If the SoC regresses: report plainly and recommend reverting commit 995c487
  (the macro re-stage). Do NOT tune knobs/margins to chase a regression -- per
  explicit user instruction, that cost two runs previously on a wrong hypothesis.


---

## RUN_2026-07-27_17-15-57 — SoC confirmation of the re-hardened CPU macro (bead 0ro) — COMPLETE

result:      ADOPTION VALIDATED on every axis. Macro views staged in commit
             995c487 (merged to main via PR #125).
baseline:    RUN_2026-07-26_16-05-43 (the previously published Stage-2 closure)

timing (nom_tt/min_tt/max_tt are the gated corners; sky130A sets
        TIMING_VIOLATION_CORNERS = ['*tt*'] at PDK level):

    setup   nom_tt  +1.38729 -> +1.85846   (+0.471)
            min_tt  +2.56559 -> +2.89398   (+0.328)
            max_tt  +0.33912 -> +0.86619   (+0.527)
    hold    nom_tt  +0.14439 -> +0.29318   (+0.149)
            min_tt  +0.24888 -> +0.29186   (+0.043)
            max_tt  +0.09232 -> +0.27062   (+0.178)
    violator list EMPTY.
    Checker.SetupViolations AND Checker.HoldViolations were both LIVE GATES
    for this run -- these numbers passed a real gate, not a skipped one.

physical:
    Netgen LVS   "Circuits match uniquely"      (unchanged)
    KLayout DRC  4                              (unchanged, macro-internal, GH #121)
    Magic DRC    9081                           (unchanged, known artifact class)
    antenna      164 -> 147 pin, 134 -> 127 net (IMPROVED)

two things worth carrying forward:

 1. ANTENNA IMPROVED, against prediction. Enabling RUN_POST_GRT_DESIGN_REPAIR
    had previously cost +20 antenna pins at SoC level and +4 at CPU level, so a
    further regression was expected here. Instead it fell 164 -> 147. Repairing
    the macro that the SoC-level design-repair step had been compensating for
    recovered part of that cost. Full series: 154/129 -> 152/128 -> 144/115 ->
    164/134 -> 147/127; best-ever remains 144/115. Bead 58q updated.

 2. max_tt -- the tightest gated corner on BOTH axes, and the corner where the
    Stage-1 CPU macro STILL violates setup internally at -0.12078 -- gained the
    most of any corner (+0.527 setup, +0.178 hold). The macro's residual
    max_tt violation does NOT propagate to the SoC. This retrospectively
    justifies not blocking adoption on it.

conclusion: the 0ro premise is confirmed end-to-end. Unrepaired
over-cap/over-slew nets inside the Stage-1 CPU made its Liberty arcs
pessimistic; repairing them improves every downstream consumer. Bead closed.

still NOT a multi-corner sign-off: the OpenRAM SRAM macro remains analytical
and single-corner (GH #120 / bead o1i measured NOT feasible on this host --
~63 min per delay simulation, ~25-30 sims per corner via delay.py's
period-doubling + per-read-port binary search, so ~80-95 h for 3 corners
against 2-8 h of uptime). ss-corner setup still fails by -6 to -9 ns and sits
outside the PDK's *tt* gate by design.

---

## bead 45a — MAGIC_DRC_USE_GDS=true test on Sky130 Stage-1 CPU (launched 2026-07-27)

run_id:      pd_20260727_203206
design_name: rv32i_cpu_top (Sky130 CPU Stage 1)
pdk:         sky130A
tool:        librelane (nix-shell)
start_time:  2026-07-27T20:32:06+07:00
last_stage:  floorplan

question: baseline Magic DRC = 27,733,913 (bit-identical across
RUN_2026-07-21_18-02-11 and RUN_2026-07-27_05-52-19), dominated by li.3
(local interconnect spacing) inside the SRAM macro footprint. Hypothesis
(documented in knowledge.md, Sky130A Magic DRC section): with
MAGIC_DRC_USE_GDS=false, Magic resolves the SRAM instance by loading the full
.mag layout via addpath rather than the LEF abstract, producing spurious
li.3 hits. This run flips MAGIC_DRC_USE_GDS false->true (commit 8a3691f,
single key) to test whether Magic reading the real merged GDS collapses the
count. Prior GDS-mode investigation (2026-06-30) found gds write embeds full
SRAM geometry via GDS_FILE property regardless of MACROS blackbox, so this
number could go either way -- both outcomes are reportable results per user
instruction (no knob-tuning to chase a preferred answer).

pre-launch verification (all confirmed unchanged, config diff is the single
MAGIC_DRC_USE_GDS key per commit 8a3691f):
  - RUN_POST_GRT_DESIGN_REPAIR: true
  - RUN_MAGIC_DRC: true, RUN_KLAYOUT_DRC: true
  - EXTRA_LIBS: dir::pdk_lib_patched/... (patched copy, NOT pdk_dir::) -- this
    is what prevents the RSZ-0090 abort at RepairDesignPostGRT
  - git status clean at 8a3691f, branch feat/sky130-0ro-soc-confirm

host state at launch: 12 GiB RAM free / 15 GiB total, 618G free on
/nobackup (30% used, 916G total). No other PD run active (sky130_soc_0ro
and sky130_soc_y7v_relaunch tmux sessions both idle/completed --
sky130_soc_0ro pane shows a finished run: 9081 Magic DRC / 4 KLayout DRC,
matching the already-recorded 0ro SoC result).

launch:
  tmux session: sky130_cpu_magic_gds_45a
  command:      cd /home/neuromorphic/Downloads/Github/claude_verilog_test/pnr && make librelane-sky130-cpu 2>&1 | tee /nobackup/sky130_cpu_magic_gds_45a_20260727_203206.log
  run dir:      will appear under /nobackup/sky130_cpu_runs/RUN_<timestamp>/ (timestamp assigned by LibreLane at flow start, not yet known at launch time)
  log path:     /nobackup/sky130_cpu_magic_gds_45a_20260727_203206.log
  reference runtime: ~2h17m for the baseline (MAGIC_DRC_USE_GDS=false) flow;
    MAGIC_DRC_USE_GDS=true is expected to be substantially heavier at the
    magic-drc step because Magic must now load the ~205 MB merged GDS
    including full SRAM macro internal geometry instead of an abstract --
    watch that step specifically for runtime blowup or OOM (no privileged
    OOM logging available on this host; judge by process disappearing +
    free/step timing).
  host reboot caveat: this host reboots every ~2-8h and tmux does not
    survive reboots -- on a reboot kill, relaunch fresh (do not resume with
    -F on this project per prior user instruction preferring fresh runs).

not yet awaited -- report back when it lands. Check per bead 45a instructions:
  1. `Magic DRC errors: N` in *-misc-reportmanufacturability/*.rpt (glob, not
     step index) -- baseline is exactly 27,733,913.
  2. If changed, new rule-type breakdown from *-magic-drc/reports/drc_violations.magic.rpt
     (bound the scan, file was 27.7M lines before).
  3. No-regression check vs RUN_2026-07-27_05-52-19: nom_tt setup +0.17416,
     hold -0.13577, KLayout DRC 0, LVS "Circuits match uniquely", antenna
     93 pin / 90 net. Timing should be UNCHANGED (MAGIC_DRC_USE_GDS only
     affects the DRC step) -- any movement is run-to-run noise, not a result.


---

## RUN_2026-07-27_20-33-10 — bead 45a: MAGIC_DRC_USE_GDS=true — HYPOTHESIS REFUTED

question:  are the 27.7M Stage-1 Magic DRC li.3 violations real, or a
           LEF-abstract artifact from MAGIC_DRC_USE_GDS=false rendering the
           sky130_sram_1kbyte_1rw1r_32x256_8 macro as a black box?

answer:    NOT an artifact. The count is essentially unchanged with real GDS.

    Magic DRC COUNT   27,730,498   (MAGIC_DRC_USE_GDS = true,  this run)
                      27,733,913   (MAGIC_DRC_USE_GDS = false, baseline)
    difference 3,415 -- about 0.01 %.

    Same rule families in both reports: licon.1, licon.5a, licon.8a,
    poly.2/4/7/8, psd.10b (and li.3 dominating the coordinate entries).

SCALE CORRECTION, from the magic-drc log:
    [INFO] COUNT: 27730498
    [INFO] Should be divided by 3 or 4
Magic counts each violation 3-4x, so DISTINCT violations are ~6.9M-9.2M.
Still enormous, but quote the corrected figure, not the raw COUNT.

SECONDARY FINDING -- why the config was reverted to false:
MAGIC_DRC_USE_GDS=true is NOT USABLE on this design. Reading the real GDS,
Magic hits fatal "Unknown layer/datatype in boundary" errors on the PDK SRAM
macro's internal cells (sky130_fd_bd_sram__openram_dp_cell*, layer 235 type 0,
layer 33 type 42/43, layer 22 type 21/22) and LibreLane aborts the entire flow:
    ERROR  Encountered one or more fatal errors while running Magic.
    make: *** [Makefile:585: librelane-sky130-cpu] Error 2
The DRC itself COMPLETED and wrote its report before the abort, which is the
only reason the number above exists. Config reverted to false so future CPU
runs are not broken by this.

NOT an OOM: RAM went 11G -> 13G at process death (freed, no pressure), and the
magic-drc step ran 42 min (21:37 -> 22:19). The earlier OOM concern about
loading a ~205 MB GDS did not materialise.

leads for whoever picks this up:
 (a) sample actual li.3 coordinates -- do they cluster inside the SRAM macro
     footprint, or spread across the standard-cell array? That separates a
     macro-local problem from a global one.
 (b) the "Unknown layer/datatype" errors suggest the sky130A Magic tech file
     may not match what the PDK SRAM GDS expects. A tech-file/GDS version
     mismatch could plausibly generate spurious li.3 as well -- worth checking
     before treating 7-9M violations as genuine geometry errors.
 (c) STRONGEST CLUE: the Sky130 SoC reports only 9081 Magic DRC errors on a
     LARGER die (6700x3100 vs 3600x1800). Same PDK, same Magic, vastly
     different result. Explaining that asymmetry probably explains everything.

================================================================================
2026-07-28 -- BEAD 45a RESOLVED: PDK SRAM MACRO ARTIFACT, WAIVABLE
================================================================================

All three leads (a)/(b)/(c) above were run down. Verdict: the ~27.7M Magic DRC
violations are entirely internal to the PDK SRAM macro geometry. Not our
placement, not our routing, not our standard cells. Waived.

(a) COORDINATE CLUSTERING -- exhaustive, not sampled
Full streaming pass over the 1.1 GB report from RUN_2026-07-27_20-33-10
(63-magic-drc/reports/drc_violations.magic.rpt), every coordinate classified
against the 10 sky130_sram_1kbyte_1rw1r_32x256_8 rectangles in
macro_placement.cfg (origins x=100.00/679.78/1359.56/2039.34/2719.12,
y=20/520, extent 479.78 x 397.5):

    inside an SRAM footprint      27,730,498   100.0000 %
    routing channel (y 417.5-520)          0          0 %
    standard-cell logic (y>917.5)          0          0 %

Independently reproduced twice (PD agent + main session, separate awk passes,
identical counts). Coordinate extents: x 0..3189.11, y 0..907.87. The logic
zone starts at y=917.5 -- NOTHING is reported above 907.87. The rightmost
SRAM's right edge is 2719.12+479.78 = 3198.90, and max x is 3189.11.

All 26 rule families are 100 % SRAM-internal -- none leak outside. Largest:
diff/tap.9 3,017,505; licon.1 2,572,862; li.1 2,278,399; licon.5a 2,262,998;
licon.8 1,850,092; poly.8 1,833,708; diff/tap.1 1,820,192; licon.14 1,697,877;
via.1a+2*via.4a 1,597,260; poly.4 1,339,088; li.3 922,628; met1.4 841,738.
Note li.3 is NOT actually the dominant family once counted properly.

Per-instance: 9 macros at ~2.831M each; col5_row1 (x0=2719.12) at 2,245,976,
a ~21 % low outlier -- edge-of-row effect on Magic's 3-4x multi-count, not a
different cause. Sums exactly to 27,730,498.

(b) TECHFILE vs MACRO GDS -- real gap, but NOT the driver
sky130A.tech maps GDS layer 235 only at datatype 4 (-> CELLBOUND); the SRAM
bitcells draw their boundary at 235/0. Layers 33 and 22/21,22 are unmapped
entirely. That is the exact cause of the fatal "Unknown layer/datatype" abort
(18 errors, 4 distinct cell definitions: openram_dp_cell, _dummy, _replica,
_cap_row).

It matters mechanistically -- sky130A.tech has a deliberate two-tier li1 rule,
strict li.3 (0.17um) for generic `locali` vs relaxed li.c2 (0.14um) for
`coreli` ("Local interconnect in core (SRAM) cells has more relaxed rules"),
and `coreli` classification derives from COREID, bloated off the same CELLBOUND
geometry Magic cannot read at 235/0.

But it is NOT sufficient as an explanation: MAGIC_DRC_USE_GDS=false never
invokes the GDS calma path for the SRAM at all (resolves via .mag/LEF addpath)
and still yields 27,733,913 -- 0.01 % apart. And the SRAM-aware relaxed rules
Magic DOES apply correctly still fire in the hundreds of thousands (li.c2
661,744; poly.8 "SRAM core transistor" 1,833,708; diff/tap.2 "P-Transistor in
SRAM core" 331,004). Root cause is broader: Magic's flat drc(full) engine is
not equipped to validate this dense custom OpenRAM macro's internals, whatever
the read path.

(c) THE SoC/CPU ASYMMETRY -- fully reconciled
SoC RUN_2026-07-27_17-15-57/55-magic-drc: 9,081 = 9,049 nwell.4 + 32 met4.4a.
A COMPLETELY DISJOINT rule set -- zero li.3/licon/poly/diff. Not a diluted
version of the CPU flood.

Reason: pnr/sky130/soc/config.json declares the CPU as a hard MACROS entry and
SoC runs MAGIC_DRC_USE_GDS=false, so read_macro_lef loads the CPU LEF ABSTRACT
before def read and Magic never touches CPU-internal (hence SRAM-internal)
geometry. The SRAM-flood failure mode is structurally impossible at SoC level.
The residual 9,049 nwell.4 is the same DEF+LEF-abstract-view artifact class
already documented in knowledge.md (N-well tap connectivity unverifiable from
an abstract), previously seen at 3,626 on a smaller CPU-only test -- same
phenomenon, larger die. met4.4a x32 is a small uniform ~12.3um-pitch minimum-
area artifact, likely a PDN-strap/via quirk; immaterial, not chased.

WHY KLAYOUT REPORTS 0 ON THE IDENTICAL GDS
sky130A_mr.drc (foundry deck) has explicit hierarchy-aware SRAM exclusion:
SRAM_EXCLUDE=true ->
    not_sram = layout(source.cell_obj).select("-*sky130_sram_*kbyte_*")
subtracting all shapes in cells matching the SRAM macro name from the
nsdm/psdm/nwell rule groups. The log states it outright:
    nwell.6 | sky130_fd_io__gpiov2_amux, sky130_fd_io__simple_pad_and_busses, sram
    nsd.1/nsd.2/psd.1/psd.2 | sram
i.e. the foundry deck groups this SRAM with the I/O pad cells and treats it as
a pre-verified hard macro by convention. KLayout also implements the two-tier
li1 split via an areaid:ce scope (li_outside_or_touching_areaidce -> strict
li.1/li.3 0.17um; li_core -> relaxed li.7/li.8 0.14um) -- same intent as
Magic's COREID/coreli, but it actually works here.

SIGN-OFF POSITION
Stage-1 Sky130 CPU sign-off rests on KLayout DRC = 0 + Netgen LVS = "Circuits
match uniquely" + DRT 0, with Magic's 27.7M waived as a stock-tool limitation
(flat Magic DRC vs OpenRAM macro hierarchy). This is consistent with, and now
quantitatively reinforces, the existing knowledge.md position that
KLayout+Netgen are authoritative for Sky130. Stages 2-4 inherit the waiver
cleanly, and at SoC level the failure mode cannot even occur (CPU is an
abstracted macro).

LEAVE MAGIC_DRC_USE_GDS = false in pnr/sky130/cpu/config.json. true aborts the
whole flow on the techfile gap and buys nothing -- it produces the same count.
The techfile layer/datatype gap is filed separately as its own low-priority
bead; it only matters if MAGIC_DRC_USE_GDS=true is ever wanted again.

================================================================================
2026-07-29 -- bead 58q: SoC antenna diagnosis + clock relax + antenna retune
(SCOPE-EXPANDED mid-task by coordinator: also drop clock so ss closes honestly)
================================================================================

baseline: RUN_2026-07-27_17-15-57 (65 MHz, TIMING_VIOLATION_CORNERS=['*tt*']).
Gate table: LVS PASS, power grid 0, KLayout DRC 4 (waived, bead 0jp), Magic DRC
9081 (waived, bead 45a), antenna FAILED 147 pin / 127 net, tt setup/hold clean,
ss setup WNS -8.902 ns (out of gate).

--- TASK 1: antenna diagnosis (does the 147/127 split by macro-pin cause?) ---

FIRST FINDING: the coordinator's brief cited
39-openroad-repairantennas/2-openroad-checkantennas/reports/antenna_summary.rpt
as the violator list. That report is an IN-FLIGHT check (post-diode-insertion,
PRE-DRT: 89 rows / 56 nets). It is NOT the final gate. The step that matches
manufacturability.rpt's 147 pin / 127 net exactly is
44-openroad-checkantennas-1/reports/antenna_summary.rpt (149 rows, 147 unique
net+pin pairs, 127 unique nets -- post-DRT, the real signoff-relevant check).
DRT measurably reshuffles the violator set between these two checks (this
project's own history already documents "DRT reintroduces antenna exposure").
Net names cited in the brief (net578, net608, m_araddr[4], m_rresp[1],
m_rvalid[0] as a violator) do NOT appear in the final 44- report at all --
they were transient, repaired-out by the time DRT ran. All analysis below
uses the 44- (final, authoritative) report only.

METHOD: wrote a driver-classifier (python, one-pass regex over the flattened
post-route netlist 42-openroad-detailedrouting/soc_top.nl.v, 364,783 lines,
17.4 MB) that resolves each of the 127 violating net names to its physical
driver pin, using: (a) sky130_fd_sc_hd's own output-pin name set {COUT,
COUT_N, GCLK, HI, LO, Q, Q_N, SUM, X, Y, Z} pulled from the vendor LEF
(437 macros), (b) rv32i_cpu_top.lef's 403 pins re-parsed independently
(matches the brief's 95-missing-output-pin claim once VPWR/VGND are excluded:
97 raw missing - 2 power pins = 95), (c) the SRAM macro LEF's pin set. Bus
concatenations (`.pin({netA, netB, ...})`, MSB-first per observed pattern)
were resolved to per-bit LEF pin names by list position. 126/127 nets
resolved to a definitive driver; the 127th (clk_i) is a top-level input port
with no internal driver by construction.

RESULT -- the split, in violation-instance units (149 total incl. 2 nets
double-counted across layers; 147 unique pins, matching manufacturability.rpt):

    CPU macro pin, ANTENNADIFFAREA PRESENT     19   (12.8%)
    CPU macro pin, ANTENNADIFFAREA MISSING      4   ( 2.7%)  [axi_awlen_o[5],[7]]
    SRAM macro pin, ANTENNADIFFAREA MISSING     2   ( 1.3%)  [dout1[9],[31]]
    top-level input port (clk_i, no diode)      1   ( 0.7%)
    plain standard-cell logic/flop (X/Y/Q)    123   (82.6%)
    ------------------------------------------------------
    TOTAL                                     149

CONCLUSION: the brief's premise ("violators are overwhelmingly CPU<->bus AXI
nets", implying the LEF gap explains a meaningful share) does NOT hold against
the final report. 82.6% of violations are on nets driven entirely by ordinary
placed-and-routed standard cells inside the flattened SoC fabric (crossbar
arbiter registers, DMA engine registers/datapath, APB peripheral bus,
sram_controller glue) with NO macro pin anywhere in their drive path -- e.g.
net30/net155/.../net823 (33 instances), u_dma.regs_o/dst_addr_reg/length_reg
(9), u_bus.u_xbar.ar_addr_q/wsel (3), apb_pwdata/pstrb (4), u_bus.m_rdata/
m_rvalid (5, driven by the crossbar's OWN read-mux, not the CPU -- these are
CPU *input* signals, direction was previously mis-assumed). This is
classic large-die (6700x3100 um) long-route antenna exposure, independent of
any macro LEF defect. Only 6/149 (4.0%) trace to a macro pin lacking
ANTENNADIFFAREA (4 CPU + 2 SRAM); 19/149 (12.8%) trace to a CPU macro pin that
already HAS correct ANTENNADIFFAREA and still violates (proves diffusion
credit at the pin cannot bound arbitrarily long SoC-level fanout by itself).
net578/net608 (named in the brief) are not macro-adjacent -- moot, they are
not in the final violator set at all.

CONFIG-GAP FINDING (explains a real, fixable, distinct problem): SoC
config.json was MISSING RUN_HEURISTIC_DIODE_INSERTION, GRT_ANTENNA_ITERS,
GRT_ANTENNA_MARGIN, DIODE_ON_PORTS entirely (confirmed via `grep -rn` across
pnr/) -- every other block in this project (CPU, SRAM, GPU, ASAP7 variants)
sets these explicitly. LibreLane defaults (read from
librelane/steps/common_variables.py + flows/classic.py +
librelane/steps/odb.py, this session's librelane checkout):
GRT_ANTENNA_ITERS=3 (CPU uses 5), GRT_ANTENNA_MARGIN=10% (CPU uses 20%),
RUN_HEURISTIC_DIODE_INSERTION default=False (CPU=true), DIODE_ON_PORTS
default="none" (CPU="in"). RUN_ANTENNA_REPAIR defaults True so the GRT-level
repair pass WAS running (explains the observed 2018-diode insertion and the
556/440 -> 147/127 in-run reduction already achieved) but with weaker
iteration/margin than any other block in the project, no heuristic
pre-placement diode pass, and NO port-diode protection -- directly explaining
clk_i's presence in the violator list (DIODE_ON_PORTS="none" means the one
top-level input port on this design's SDC-timed clock got zero antenna
protection at the port itself).

--- TASK 2: 95-pin CPU LEF gap -- ROOT CAUSE FOUND, REGENERATION REFUTED ---

Traced all 95 missing-ANTENNADIFFAREA CPU output pins through the CPU-ONLY
signed-off netlist (RUN_2026-07-27_05-52-19/46-openroad-detailedrouting/
rv32i_cpu_top.nl.v, the CPU's OWN top-level module, not the SoC flatten).
Method: for each of the 95 port names, found its `assign PORT = netN;`
statement (all 95 are single-hop wire aliases, zero intervening logic), then
found netN's driver instance.

RESULT (100% of 95, exhaustively, not sampled): every single one is driven by
a `sky130_fd_sc_hd__conb_1` constant-tie cell (.LO() for the ties-to-0 pins,
.HI() for apb_pready_o which ties to 1). Breakdown: debug_rs1_data_o[31:0] +
debug_rs2_data_o[31:0] (64, half the total), debug_state_o[3:0] (4),
debug_branch_taken_o (1), apb_pready_o (1), axi_rready_o (1), and 24 AXI4
burst-control constant fields (awaddr/araddr[1:0], awlen/arlen[7:2], awsize,
arsize, awburst, arburst) consistent with this CPU's AXI master only ever
issuing single-beat 4-byte-aligned transactions.

WHY: checked the vendor's OWN sky130_fd_sc_hd.lef (volare
bdc9412b.../sky130A/.../sky130_fd_sc_hd.lef, 450 ANTENNADIFFAREA occurrences
total in the file, confirming the library DOES normally publish this
property, e.g. buf_1/X = 0.3406). sky130_fd_sc_hd__conb_1's LO and HI pins
have ZERO ANTENNADIFFAREA in the VENDOR'S OWN base LEF -- not just in our
Magic-regenerated macro abstract. This is upstream SkyWater library
convention (a tie-cell output is a permanent rail tap through an always-on
device, not a floating net that can accumulate plasma-etch charge the way a
normal logic gate's output can), not a LibreLane, Magic, or project defect.
Magic's `lef write` (step 61-magic-writelef in the CPU run -- confirmed
byte-identical md5 to the staged pnr/sky130/cpu/macro/rv32i_cpu_top.lef, so
Magic, not OpenROAD's write_abstract_lef, is the actual LEF author here)
correctly propagates the vendor's own omission up to the macro boundary pin.

REGENERATION VERDICT: REFUTED as a fix path, same evidentiary class as the
45a MAGIC_DRC_USE_GDS result. Because every one of the 95 pins deterministically
traces to conb_1 (not e.g. an unlucky routing/extraction failure), re-running
Magic's lef write against the same layout would reproduce the identical 95-pin
gap -- there is nothing stochastic to regenerate away.

HAND-PATCH VERDICT: NOT applied, and NOT recommended. Reasons: (1) the
vendor's own conb_1 LEF entry has no ANTENNADIFFAREA value to copy -- any
number written would be fabricated, not measured, which this project's
evidentiary standard (bead 45a: "numbers, not narrative") rules out; (2) even
if a plausible small tie-cell diffusion value existed, only 2 of these 95
pins (axi_awlen_o[5],[7]) are actually on the violator list, and their
partial/required ratios (4544/400 = 11.4x, worst in the whole report) are far
too large for a tie-cell's typically-sub-1-um^2 diffusion to close -- the fix
has to come from repair (diode insertion / margin), not LEF credit; (3) a
fabricated ANTENNADIFFAREA value written into a signed-off macro LEF risks
UNDER-protecting some other, unrelated pin if the checker trusts a wrong
number -- writing nothing is safer than writing a guess. CLASSIFIED AS A
DOCUMENTED, WAIVED PDK/vendor-convention artifact, not an open defect.

SRAM MACRO SIDE-FINDING (bigger, same family, also NOT fixed here): the SRAM
LEF (both pnr/sky130/soc/macro/sky130_sram_4kbyte_1rw1r_32x1024_8.lef AND the
CPU-internal sky130_sram_1kbyte_1rw1r_32x256_8.lef, the latter SHIPPED BY THE
PDK in volare sky130B, not project-generated) has ZERO ANTENNADIFFAREA or
ANTENNAGATEAREA on ANY pin, output or input, of either macro -- not a 2-pin
gap, a total absence, and upstream of us (OpenRAM-generated / PDK-vendor
LEF, not Magic-written). Regenerating this would require running Magic
extraction over the SRAM's own dense custom layout, which bead 45a already
established Magic's flat engine cannot validate meaningfully for this exact
macro family (the 27.7M-violation DRC flood). Not attempted -- out of scope,
documented as a waived third-party/vendor-abstraction limitation, same
evidentiary class as the DRC waiver. Only 2/149 (1.3%) violations trace to
it in the current design.

--- TASK 3 fix + coordinator scope-change: clock relax + antenna retune ---

Applied to pnr/sky130/soc/config.json (commit pending):
  CLOCK_PERIOD: 15.385 -> 25.0                  (65 -> 40 MHz)
  TIMING_VIOLATION_CORNERS: ['*tt*'] -> ['*']   (all 9 corners now gated)
  RUN_ANTENNA_REPAIR: true                      (was implicit default; now explicit)
  RUN_HEURISTIC_DIODE_INSERTION: true           (was absent -> LibreLane default False)
  GRT_ANTENNA_ITERS: 8                          (was absent -> default 3; CPU uses 5,
                                                  went higher given the die is ~3.2x CPU's area)
  GRT_ANTENNA_MARGIN: 25                        (was absent -> default 10%; CPU uses 20%)
  DIODE_ON_PORTS: "in"                          (was absent -> default "none"; directly
                                                  protects clk_i, the one top-port violator)

pnr/sky130/soc/constraints/sky130_soc.sdc: `set clock_period 15.385` ->
`set clock_period 25.0`. All set_input_delay/set_output_delay lines already
compute off $clock_period (0.20/0.05 fractions) so they scale automatically --
verified no other hardcoded ns values reference the old period. Header
comment block added documenting the coordinator-directed reversal of the
prior "do not touch ss" instruction, the 25.0 ns period choice (arithmetic
min 24.287 ns assuming invariant path delay, +0.7 ns headroom for expected
resizer response to the looser budget -- this project's own bead-1ls history
shows the same critical path moved hundreds of ps purely from resizer
response to a period change), and the SRAM-single-corner caveat (bead o1i /
GH #120 still open -- ss/ff numbers touching SRAM read/write timing carry
unquantified model error; only the CPU macro and flat std-cell fabric are
genuinely 9-corner-accurate this run).

NOT changed: floorplan, die size, macro placement (die-size lever from the
brief's task-3 options list was considered and rejected -- would invalidate
multiple prior runs' worth of timing-closure work for a fix that config-level
antenna retuning + the new clock headroom should reach first; only revisit if
this run's antenna residual is still large). No RTL. MAGIC_DRC_USE_GDS
unchanged (false). Did not touch bead 1ls's CPU-internal SDC (separate file,
separate macro-level budget, unaffected by the SoC-level period).

LAUNCH:
  run_id:      pd_20260729_183700 (approx, see run_state timestamp)
  design_name: soc_top (Sky130 SoC Stage 2)
  pdk:         sky130A
  tool:        librelane (nix-shell), make librelane-sky130-soc
  host state at launch: 12 GiB free / 15 GiB total RAM, 611G free on
    /nobackup, no other PD process running (checked via ps aux + tmux ls --
    prior sky130_soc_0ro / sky130_cpu_magic_gds_45a / sky130_soc_y7v_relaunch
    tmux sessions all idle, no live librelane/openroad/magic/klayout procs).
  expected runtime: 4-10 h per the Makefile's own estimate for this design;
    the looser 40 MHz clock may reduce resizer/repair iteration time somewhat
    but this is not counted on.
  NOT YET AWAITED as of this entry -- report back once landed. Per
  feedback_librelane_wait_intervals: wait >=1 h before first poll, +1 h each
  subsequent poll until termination. Check, in order: (1) manufacturability.rpt
  gate table (LVS/DRC/antenna/PDN), (2) STAPostPNR summary.rpt for all 9
  corners (setup+hold WNS/TNS, reg-to-reg violator counts), (3) antenna
  final report step (grep run dir for "checkantennas-1" or the highest-
  numbered checkantennas step) cross-checked against manufacturability.rpt
  the same way this session did (do not trust an in-flight repair-step report
  as the final number -- this session's own mistake, corrected above).

================================================================================
2026-07-29 (same day, continued) -- RUN_2026-07-29_18-40-38 mid-flight review:
coordinator caught antenna 147/127 -> 52/46 (real improvement, not zero), ss
setup still open (extrapolation ~34 ns / 29 MHz needed, my 24.287 ns linear
estimate was wrong -- confirmed path delay is NOT period-invariant, ~0.48 ns
recovered per 1 ns relaxed), AND a HOLD REGRESSION at 4/9 corners
(max_ss -0.663, max_tt -0.459, nom_ss -0.283, nom_tt -0.210 -- nom_tt was
clean before). User decision: fix hold first, ss re-decided after. DO NOT
launch another multi-hour run until this diagnosis is reported and the
coordinator sanity-checks direction.
================================================================================

HOLD REGRESSION ROOT CAUSE -- FOUND AND QUANTIFIED, coordinator's
DIODE_ON_PORTS hypothesis CONFIRMED (not just "not ruled out"):

1. summary.rpt "of which reg to reg" column is 0 at EVERY corner, both runs
   -- reg-to-reg hold is UNCHANGED (nom_tt: 0.2932 old -> 0.2927 new,
   noise-level). 100% of the regression is on non-reg-to-reg (I/O-boundary)
   paths.

2. Parsed every VIOLATED path (min.rpt, all 5 failing corners, python regex
   over report_checks output, not eyeballed): EVERY SINGLE hold violator at
   EVERY failing corner is {apb_paddr_i[*], apb_psel_i, apb_penable_i,
   apb_pwdata_i[*]} -> u_cpu. Zero exceptions, zero other startpoints. This
   is exactly (and only) the APB debug-bus multicycle group
   (`set_multicycle_path 2 -setup / 1 -hold -from {apb_paddr_i apb_psel_i
   apb_penable_i apb_pwrite_i apb_pwdata_i}` in sky130_soc.sdc). All AXI
   data paths route through the crossbar's own registers (reg-to-reg,
   insulated) -- APB is the ONLY direct input-port-to-macro-register class
   in this design, which is why it and only it is exposed.

3. WHY this class specifically: input ports have NO clock-network term on
   the data/arrival side (fixed set_input_delay model only) but the FULL
   clock-tree latency on the capture side (through to u_cpu/clk_i). Reg-to-
   reg paths have clock latency on BOTH sides and it largely cancels. So
   this class has zero cancellation cushion against any clock-latency growth
   -- a direct, unbuffered exposure.

4. MEASURED the clock-latency term directly (grepped u_cpu/clk_i out of both
   runs' nom_tt max.rpt setup reports, same physical clock path, corner-
   identical latency number regardless of setup/hold):
       OLD (RUN_2026-07-27_17-15-57): clk_i -> u_cpu/clk_i = 0.870159 ns
       NEW (RUN_2026-07-29_18-40-38): clk_i -> u_cpu/clk_i = 1.439363 ns
       DELTA: +0.569204 ns
   Segment-by-segment, the growth is almost entirely in the FIRST hop (clk_i
   port -> clkbuf_0_clk_i/A, the set_driving_cell-modelled boundary segment):
       OLD: fanout 5, cap 0.429969 pF, delay 0.319984 ns
       NEW: fanout 4, cap 0.505111 pF, delay 0.787429 ns   (+0.467445 ns)
   FEWER fanout (5->4) but MORE cap and 2.5x the delay -- not explained by
   "more load", which rules out the generic "+20% stdcell count" story as
   the direct mechanism for THIS specific segment. Cross-checked against the
   new run's own netlist: clk_i now has TWO antenna diodes wired directly
   onto it (`ANTENNA_clkbuf_0_clk_i_A` and `ANTENNA_clkbuf_regs_0_core_clk_A`,
   both `.DIODE(clk_i)`) -- these did not exist in the old run
   (DIODE_ON_PORTS was unset/"none" there). DIODE_ON_PORTS="in" is the only
   one of the 4 new antenna keys that touches top-level ports at all; the
   other three (RUN_HEURISTIC_DIODE_INSERTION, GRT_ANTENNA_ITERS,
   GRT_ANTENNA_MARGIN) act on internal nets. A cell placed directly on the
   clk_i net's first segment, competing for the same legalization slot as
   the clock root buffers, is a direct, mechanistic explanation for that
   segment specifically getting longer/more-resistive even with one fewer
   logical fanout -- consistent with (not just analogous to) this project's
   own prior documented pattern for antenna-insertion-driven placement
   cascades (bead y7v SDC header: "Better hold slack -> ... different
   placement -> different GRT -> antenna violations ... this net picked up
   a second, distant sink and a long route").
   Arithmetic check: required-side grew ~+0.569 ns; arrival-side gained only
   ~+0.481 ns from the bigger set_input_delay -min (0.05 * 25.0 - 0.05 *
   15.385 = 0.481 ns, unavoidable and structural, NOT the antenna keys'
   fault) -- net ~-0.09 ns explained by period alone, the remainder of the
   observed ~-0.50 ns nom_tt delta plus the internal path-side hold-buffer
   (hold53, sky130_fd_sc_hd__dlygate4sd3_1, 0.5376 ns through ONE cell --
   plausible for this cell class) is consistent with the clock-latency
   shift once corner-to-corner variance in clock buffer delay is folded in.
   Not a perfect single-variable equation (period change and diode placement
   happened in the same run, cannot be split further without an isolation
   run), but the DIRECTION, MAGNITUDE, and MECHANISM all point at
   DIODE_ON_PORTS as the dominant, identifiable cause, not the period change
   or the other 3 antenna keys.

5. ANTENNA BENEFIT OF DIODE_ON_PORTS SPECIFICALLY, quantified: clk_i was the
   ONLY top-level-port violator in the original 147/127 list (this session's
   own task-1 classification: 1/149 instances). It is NOT in the new run's
   52/46 final list (checkantennas-1, confirmed via direct grep). No other
   SoC top-level input port (apb_*, spi_*, uart_rx_i) was ever a violator in
   either list. So DIODE_ON_PORTS="in" demonstrably fixed AT MOST 1 of the
   95 violations closed by this run (147->52 = 95 closed; the other 3 keys
   -- more repair iterations, more margin, pre-placement heuristic diode
   pass -- account for the internal-net majority, matching this session's
   task-1 finding that 82.6% of the ORIGINAL violators were plain stdcell-
   driven internal nets, not ports).

RECOMMENDATION (quantified trade, not yet applied -- awaiting coordinator
sanity check per explicit instruction before burning another multi-hour run):
  DROP DIODE_ON_PORTS (remove the key / revert to LibreLane default "none").
  Cost: likely reintroduces clk_i as a single antenna violator (1 pin, the
    same class already well-understood and easily documented/waived the
    same way the CPU's 95-pin tie-cell gap was handled in task 2 -- a lone
    top-level clock port antenna exposure on a large SoC is a small,
    explainable residual, not a new open question).
  Benefit: removes the two diodes sitting directly on clk_i's first clock-
    tree segment, which is the most direct, evidence-backed lever available
    to recover the measured +0.569 ns clock-latency / hold regression
    without touching RUN_HEURISTIC_DIODE_INSERTION, GRT_ANTENNA_ITERS=8, or
    GRT_ANTENNA_MARGIN=25 (the three keys responsible for the other 94
    closed violations).
  Keep everything else as-is (CLOCK_PERIOD 25.0, TIMING_VIOLATION_CORNERS
  ['*'], the other 3 antenna keys) per the coordinator's explicit "leave
  clock at 25.0 for now" instruction -- this is a hold-only fix attempt,
  not a re-opening of the frequency question.
  NOT proposed: touching GRT_RESIZER_HOLD_SLACK_MARGIN or other hold-repair
  budget knobs pre-emptively -- want to see if removing the identified cause
  is sufficient before adding more variables to the next multi-hour cycle.

STATUS: reported to coordinator, NOT YET APPLIED, NOT YET RE-LAUNCHED --
holding for explicit go-ahead per "report... before making changes... before
another multi-hour cycle burns."

--- APPROVED (coordinator, same session) -- corrections + clk_i alternative-fix check ---

Coordinator independently re-verified the diode/clock-latency numbers (exact
match) and APPROVED: drop DIODE_ON_PORTS, keep the other 3 keys + 25.0 ns
period. Two corrections to carry into the permanent record:

1. Coordinator's OWN "+47k cells" framing was WRONG, not mine: DIODE_ON_PORTS
   inserted only 52 ANTENNA_* cells total (grep-countable), not 47,385 --
   design__instance__count__class:antenna_cell=47385 is a different metric
   (counts diode-like fill broadly, not attributable to DIODE_ON_PORTS
   specifically). So this is NOT a generic +20%-cell-count placement-pressure
   story -- it is precisely the two diodes landing directly on the clock
   root, nothing more diffuse. Recorded as coordinator's correction to their
   own initial framing, not mine to walk back.
2. SDC multicycle pairing verified NOT to be the bug: `set_multicycle_path 2
   -setup / 1 -hold -from {apb_paddr_i ...}` (sky130_soc.sdc ~287-288) is the
   textbook-standard pairing. Worth stating explicitly because "hold fails on
   a multicycle group" is exactly the shape that USUALLY IS a constraint
   bug -- ruling it out here has real value, not a formality. Also: SDC
   header line ~60-61 already records a prior, smaller instance of this same
   I/O-boundary hold class (`-0.0923 ns apb_paddr_i[4] -> u_cpu`, bead y7v,
   2026-07-26) -- this design's APB debug bus has been the hold-sensitive
   boundary class before; this is a recurrence of a known-fragile spot under
   a new perturbation, not a first-time surprise.

CLK_I ANTENNA -- ALTERNATIVE-FIX CHECK (before defaulting to a waiver, per
coordinator instruction): read librelane/scripts/odbpy/diodes.py
(DiodeInserter, the actual engine behind Odb.PortDiodePlacement /
DIODE_ON_PORTS). Finding: place_diode_stdcell() ALWAYS places the diode
immediately abutting the FIRST SINK INSTANCE on the net (left/right of it,
touching), governed by a `side_strategy` internal parameter ("source"/"pin"/
"balanced") with NO distance/threshold/offset control exposed anywhere in
the LibreLane Variable surface (checked common_variables.py, odb.py -- only
DIODE_ON_PORTS polarity and the diode cell/pin choice are configurable, not
placement distance). For clk_i, "first sink instance" IS clkbuf_0_clk_i /
clkbuf_0_clk_i_regs -- the clock tree roots. There is therefore NO config
knob to make this mechanism protect clk_i from farther away; abutting the
clock root is not a misconfiguration, it is what this script does by
design. A custom post-placement ECO (script an OpenROAD/ODB pass that
legally relocates just these 2 diode instances a few sites away after
placement, before CTS) is technically possible but is bespoke, untested
engineering for a single moderate-severity net -- not attempted this
session per "don't spend a whole extra cycle on it."

CLK_I SEVERITY (for the eventual waiver-or-not call): original ratio (pre-
any-of-the-4-new-keys baseline, RUN_2026-07-27_17-15-57/44-checkantennas-1)
was partial 843.44 / required 400.00 = 2.11x -- moderate, not the worst in
that report (worst was 11.4x), but not negligible either.

PATH FORWARD (no extra cycle spent): dropping DIODE_ON_PORTS while keeping
GRT_ANTENNA_ITERS=8 / GRT_ANTENNA_MARGIN=25 (both well above CPU's already-
validated 5/20, and both act via the GRT-based RepairAntennas jumper/diode
pass, which is placement-legalization-aware and runs on already-routed
nets, unlike the blunt port-diode script) is ALREADY the experiment that
answers whether clk_i can be closed without the disruptive mechanism -- no
separate isolation run needed. Next run's checkantennas-1 report settles it:
if clk_i is absent, GRT-alone with the enhanced settings sufficed; if
present, it becomes a single documented residual (2.11x, top-level clock
port, mechanism-explained-not-just-observed, same evidentiary bar as the
CPU tie-cell and SRAM-LEF waivers from task 2) rather than reaching for the
bespoke-ECO route on a first attempt.

FIX APPLIED: pnr/sky130/soc/config.json -- removed "DIODE_ON_PORTS": "in".
Kept RUN_ANTENNA_REPAIR, RUN_HEURISTIC_DIODE_INSERTION, GRT_ANTENNA_ITERS=8,
GRT_ANTENNA_MARGIN=25, CLOCK_PERIOD=25.0, TIMING_VIOLATION_CORNERS=['*']
unchanged. No SDC change this round (multicycle pairing already correct,
nothing to fix there). No RTL. Re-launching once the CURRENT run
(RUN_2026-07-29_18-40-38) finishes and its full gate table is reported.

--- RUN_2026-07-29_18-40-38 FINAL GATE TABLE (coordinator-confirmed, cross-
checked against this session's own step-52/44 reads above -- consistent) ---

    LVS (Netgen)      PASSED               (7m18s)
    Routing DRC       0                    (10 DRT iters: 22648->5803->4998->289->15->2->0)
    KLayout DRC       4                    unchanged, GH #121 waiver           (1h20m)
    Magic DRC         9081                 unchanged, bead 45a waiver          (31m34s)
    Antenna           52 pin / 46 net      FAIL, was 147/127 (~65% better)
    Setup             FAIL at ss only      max_ss -4.3284, nom_ss -2.8851, min_ss -1.1200; tt/ff all 0
    Hold              FAIL at 4 corners    max_ss -0.6633, max_tt -0.4586, nom_ss -0.2825, nom_tt -0.2098
                                            (min_* and nom_ff all 0; 51 endpoints worst corner, 3 another)
    Power             44.6 mW              was 71.7 mW
    Utilization       38.47 %

All DRC/timing failures are LibreLane "deferred" errors (flow ran to 65/65
completion rather than aborting) -- consistent with every prior run in this
project's history. Monitor-tooling note for future sessions: the first
Monitor task for this run used a 15-min heartbeat with weak log-text
matching and missed the actual completion signal -- the coordinator caught
it live by reading runtime.txt/state_out.json directly. Replaced with a
Monitor that polls for the manufacturability.rpt file's existence (or
process death) every 3 min -- more reliable, use this pattern for future
multi-hour LibreLane runs rather than a fixed-text log grep alone.

RELAUNCH: pd_20260729_2215 approx, run_2 of the DIODE_ON_PORTS-drop
experiment. Command identical to before (make librelane-sky130-soc), config
now has DIODE_ON_PORTS removed. tmux session sky130_soc_58q_run2, log
/nobackup/sky130_soc_58q_run2_<timestamp>.log. On landing: (1) confirm hold
WNS >= 0 at all 9 corners, (2) measure clk_i -> u_cpu/clk_i clock latency at
nom_tt and confirm it drops back toward the 0.870159 ns baseline (coordinator
explicitly wants this checked, not assumed, as the proof the root cause was
correct -- if hold improves WITHOUT this latency dropping, the diagnosis is
wrong and must be re-opened), (3) check whether clk_i returns as an antenna
violator and if so whether GRT_ANTENNA_ITERS=8/MARGIN=25 alone left it
worse/better/same as the DIODE_ON_PORTS run's 52/46, (4) confirm LVS MATCH,
KLayout DRC 4, Magic DRC ~9081, PDN 0, setup at tt/ff unchanged (0), ss setup
still failing as expected (frequency parked, not being re-judged this round).

CORROBORATING EVIDENCE (coordinator, post-CTS isolation): clk_i -> u_cpu/clk_i
measured at POST-CTS STA (step 32/stamidpnr-1, nom_tt, before any antenna
repair/diode step runs) across all three runs:
    RUN_2026-07-27_17-15-57   0.864490 ns
    RUN_2026-07-29_18-40-38   0.864490 ns   (the run that ended at 1.439363 ns post-route)
    RUN_2026-07-30_04-58-36   0.864490 ns   (run 2, in flight)
Byte-identical across all three, including the run whose POST-ROUTE latency
diverged to 1.439363 ns. This rules out CTS variation as an alternative
explanation outright (CTS built the same tree every time) rather than merely
correlating -- the +0.569 ns in RUN_2026-07-29_18-40-38 provably appeared
strictly AFTER step 32, and the only relevant structural change in that
window (vs the clean baseline) was odb-diodesonports at step 38. This is the
strongest form of evidence in this diagnosis: not "the numbers moved
together" but "we isolated the exact stage boundary before which the three
runs are provably identical and after which one diverges, and that boundary
brackets the mechanism already identified independently via netlist
inspection (2 diodes landing on clk_i)."
IMPORTANT CAVEAT for whoever reads this next: the post-CTS number is
IDENTICAL BY CONSTRUCTION across any run that hasn't yet reached the
antenna-repair stage -- an unchanged 0.864490 ns at step 32 in run 2 is NOT
itself evidence that run 2 will end up clean; it only rules OUT worse. The
decisive comparison is POST-ROUTE (stapostpnr, the same report location used
for the 0.870159 / 1.439363 pair above). Do not report the post-CTS number
as if it settles the run-2 outcome -- only the post-route number does.
Also: step numbering shifts between run 1 and run 2 after ~step 37 because
dropping DIODE_ON_PORTS removes the odb-diodesonports step entirely -- match
run-2 steps to run-1 steps BY NAME (e.g. "stapostpnr", "checkantennas-1"),
never by number, when diffing directories.

--- RUN_2026-07-30_04-58-36 (run 2) RESULTS -- FALSIFICATION CHECK FAILS
PARTIALLY: the root cause was NOT fully DIODE_ON_PORTS-specific ---

clk_i -> u_cpu/clk_i clock latency, nom_tt, measured the same way each time:
    clean baseline (RUN_2026-07-27_17-15-57):   0.870159 ns
    run1 (RUN_2026-07-29_18-40-38, DIODE_ON_PORTS=in):  1.439363 ns  (+0.569)
    run2 (RUN_2026-07-30_04-58-36, DIODE_ON_PORTS=none): 1.388234 ns  (+0.518,
        only 0.051 ns recovered -- under 10% of the gap)
First-hop delay (clk_i port -> clkbuf_0_clk_i/A), same three runs:
    0.319984 ns -> 0.787429 ns -> 0.743895 ns (run2 barely below run1)

WHY: grepped run2's post-fill netlist for diodes on clk_i -- THEY ARE STILL
THERE. `ANTENNA_clkbuf_0_clk_i_A` and `ANTENNA_clkbuf_regs_0_core_clk_A`,
both `.DIODE(clk_i)`, same instance names as run1. DIODE_ON_PORTS is
confirmed off (Odb.PortDiodePlacement step still runs but as a documented
no-op per coordinator's earlier check) -- so these diodes were placed by a
DIFFERENT mechanism: OpenROAD's own GRT-based RepairAntennas
(RUN_ANTENNA_REPAIR, always-on regardless of DIODE_ON_PORTS, now at
ITERS=8/MARGIN=25). clk_i's antenna violation is REAL (2.11x over threshold,
confirmed task-1 finding) -- with the port-diode shortcut removed, the
general antenna-repair pass found the SAME violation and converged on
essentially the SAME fix (a diode abutting the clock root buffer), because
that is structurally the only place a diode can protect this specific net.
CONFIRMED: clk_i itself is absent from run2's final checkantennas-1 report
(48 unique nets, was 46 in run1) -- so the antenna fix still worked, just
via a different code path with the same physical side effect.

REVISED ROOT CAUSE (supersedes the DIODE_ON_PORTS-specific framing --
record this correction prominently, the earlier framing was incomplete):
protecting clk_i's genuine antenna violation costs ~0.5 ns of hold margin
at the clock root IN THIS FLOW, REGARDLESS OF WHICH LibreLane mechanism
performs the fix (Odb.PortDiodePlacement or OpenROAD.RepairAntennas) --
both insert a diode in essentially the same place because the clock root
buffers are the only physically sensible attachment point on this short,
low-fanout net. DIODE_ON_PORTS was never the true independent variable; it
was one of two redundant paths to the same disruptive fix. Removing it only
helped by the small margin between how the two insertion mechanisms
legalize/orient the diode, not by avoiding the diode altogether.

HOLD RESULT: improved but NOT closed. Still 5 corners failing (nom_tt,
nom_ss, max_tt, max_ss, max_ff -- max_ff was ALSO failing in run1 at
-0.1267, the coordinator's run1 summary of "4 corners" omitted it; this
report's own run1 read above already had it right), all still 100% the same
apb_paddr_i/psel_i/penable_i/pwdata_i -> u_cpu class (re-verified this run,
zero new startpoint categories):
    corner    run1      run2      delta
    nom_tt   -0.2098   -0.1633   +0.0465
    nom_ss   -0.2825   -0.2108   +0.0717
    max_tt   -0.4586   -0.3943   +0.0643
    max_ss   -0.6633   -0.5785   +0.0848
    max_ff   -0.1267   -0.0790   +0.0477
Every corner improved by roughly 5-8% of the clock period, consistent with a
minor difference in diode legalization between the two insertion mechanisms
-- but none reach >=0. GOAL NOT MET.

Antenna: run2 54 pin / 48 net (run1 was 52/46) -- clk_i closed, small
regression elsewhere; net difference is noise-level relative to the 95
violations both runs fixed from the 147/127 starting point.

STATUS: reported to coordinator with full falsification-check data before
any further action. This is exactly the "hold improves but the identified
mechanism doesn't fully explain it" case the coordinator asked to be told
about rather than papered over. NOT proposing a further fix unilaterally --
holding for direction. Options on the table for whoever picks this up:
(a) accept the SMALLER hold residual as a new documented gap (worse than the
    original clean baseline, better than run1); (b) increase hold-repair
    budget (GRT_RESIZER_HOLD_SLACK_MARGIN or similar) to absorb the ~0.5 ns
    clock-root cost directly on the APB paths rather than trying to remove
    the diode; (c) investigate whether a layer/route-based antenna fix
    (jumper insertion moving the vulnerable first-hop segment to a
    protected layer instead of a diode) can protect clk_i without touching
    placement at the clock root -- not yet attempted, would need scripting
    beyond LibreLane's stock Variable surface; (d) accept clk_i as an
    unrepaired antenna residual (if there is a way to scope RUN_ANTENNA_REPAIR
    away from just this one net -- not found in the LibreLane Variable
    surface so far, likely requires a custom ECO/skip-list, not investigated
    this round).

--- COORDINATOR CORRECTION: attribution too narrow, real variable is
RUN_HEURISTIC_DIODE_INSERTION, not GRT RepairAntennas ---

Coordinator did a like-for-like same-step comparison (fillinsertion/
soc_top.nl.v, post-antenna-repair, all three runs) that I had not done:

    run                                   ANTENNA_ total   clk-net diodes   clkbuf_0_clk_i_A present
    baseline RUN_2026-07-27_17-15-57              1,934                0    no
    run1     RUN_2026-07-29_18-40-38             47,385            1,589    yes
    run2     RUN_2026-07-30_04-58-36             47,530            1,589    yes

Not 2 diodes on the clock root -- 1,589 diodes sprayed across the WHOLE
clock tree, IDENTICAL count in run1 and run2, ZERO in baseline. The single
clkbuf_0_clk_i_A instance I found is one member of this much larger set, not
the whole story.

Mechanism: Odb.HeuristicDiodeInsertion (RUN_HEURISTIC_DIODE_INSERTION) is
ABSENT from baseline (verified at commit 29cb64a^, before any of the 4 keys
were added) and PRESENT in both run1 and run2 (~6m15s each, untouched by the
DIODE_ON_PORTS removal). This step inserts diodes heuristically/broadly
across the design by design intent, not narrowly on confirmed violators like
GRT_REPAIR_ANTENNAS does -- the 1,934 -> 47,385 jump (24x) lines up with
this key turning on, not with GRT_ANTENNA_ITERS/MARGIN (which were also new
but operate narrowly on checked violators). This is why removing
DIODE_ON_PORTS only recovered 0.051 ns of the 0.569 ns gap: it was never the
dominant variable, RUN_HEURISTIC_DIODE_INSERTION spraying diodes through the
clock tree is.

NEXT EXPERIMENT (approved by coordinator, launch after current run's gate
table is reported): set RUN_HEURISTIC_DIODE_INSERTION: false in
pnr/sky130/soc/config.json, KEEP GRT_ANTENNA_ITERS=8, GRT_ANTENNA_MARGIN=25,
CLOCK_PERIOD=25.0, TIMING_VIOLATION_CORNERS=['*'], DIODE_ON_PORTS stays
removed (already off). This isolates whether GRT-based repair alone (narrow,
violator-driven) delivers most of the 147->54 antenna win without the mass
clock-tree diode spray and its hold cost.
MUST VERIFY on landing, not assume:
  1. Do the ~1,589 clock-net diodes actually disappear or drop sharply with
     the heuristic pass off? (grep the post-fill netlist for ANTENNA_*
     instances connected to clk_i/clk_i_regs/clknet_* nets, same method used
     to find the 1,589 count.)
  2. Measure clk_i -> u_cpu/clk_i clock latency at nom_tt, same method as
     before, and compare against ALL THREE known values:
         0.870159 ns (baseline, clean)
         1.439363 ns (run1, DIODE_ON_PORTS=in + heuristic on)
         1.388234 ns (run2, DIODE_ON_PORTS=none + heuristic on)
     If latency does NOT come back down toward 0.870 with the 1,589 diodes
     gone, the diode-count theory is ALSO wrong and the mechanism needs to
     be re-opened from scratch -- say so plainly, do not paper over it.

Corrections for the permanent record (both coordinator's, not mine, stated
as such): run1 hold failed at 5 corners not 4 (max_ff omitted from an
earlier coordinator summary, already caught and corrected in this file);
"antenna 52->29" was a misread of a pre-DRT metric carried forward through
steps 40-44 instead of the true checkantennas-1 report -- this session's own
54/48 read is confirmed correct.

--- RUN_2026-07-30_04-58-36 (run 2) DIED MID-FLOW, 56-magic-drc, ~06:12 ---

STA/antenna results (reported above, already forwarded to coordinator) are
NOT in question -- they came from step 52, which completed cleanly before
the death at step 56. DRC/LVS/manufacturability were never reached this run.

WHAT HAPPENED: `56-magic-drc/reports/drc_violations.magic.rpt` exists but is
0 bytes; magic-drc.log's last line is a "Moving label ... from metalN to
viaN" (pre-DRC geometry normalization, before the actual drc(full) check
ever ran); no Python traceback, no Magic error text, no clean exit -- log
just stops. Confirmed via three independent checks, not assumed: `ps aux`
found no make/python/openroad/magic process at all; `tmux list-panes
-F pane_current_command` on the run's session reported "bash" (pipeline
already returned to shell); `ps -p <magicdnull pid>` (113264, found in one
transitional check showing 99.9% CPU / 27:52 accumulated CPU time / 0 RSS in
`[bracket]` notation -- a stuck/thrashing signature, not a live user
process) came back empty moments later. Directory/log mtimes frozen at
06:12, ~26 min of zero output before I caught it at 06:38. No host reboot
(uptime continuous since ~04:09, well before this run started at 04:58).
No dmesg/journalctl access to directly confirm OOM (permission denied both
ways), but the signature (long CPU-bound stall producing zero forward
progress, zero swap used despite 31 GiB configured, host shared with ~10
other tmux sessions + multiple MCP servers + several htop/abtop instances
all baseline-consuming RAM) is consistent with the systemd-oomd PSI-kill
pattern already documented in this project's memory for GRT-heavy OpenROAD
steps, applied here to Magic DRC instead -- SoC Magic DRC has hit ~15.4 GiB
RSS on this exact host in a PRIOR SUCCESSFUL run (RUN_2026-07-29_18-40-38,
run 1), i.e. already within ~1 GiB of this host's 15 GiB total before any
other load is counted. Not root-caused to certainty (no privileged OOM log
access this session, consistent with every prior OOM suspicion in this
project's history) -- reported as the leading hypothesis, not a fact.

ACTION: killed the dead tmux session (tmux kill-session -t
sky130_soc_58q_run2b -- also cleaned up a zombie-state magicdnull that a
`ps -p` check no longer found afterward, confirming it was this session's
child). Per feedback_pd_run_strategy.md (fresh relaunch preferred over -F
resume on a mid-flow death), relaunched fresh rather than resuming.

DECISION: did NOT re-run the identical (DIODE_ON_PORTS=none,
RUN_HEURISTIC_DIODE_INSERTION=true) config just to re-confirm DRC/LVS/PDN.
Reasoning: (1) those three gates have been UNIFORMLY stable (LVS MATCH,
KLayout DRC 4, Magic DRC ~9081) across every single run in this entire
multi-week campaign regardless of antenna/clock/hold changes -- they are
structurally decoupled from what's being tested, so a repeat run buys very
low incremental confidence for a multi-hour cost; (2) the coordinator's own
approved next experiment (RUN_HEURISTIC_DIODE_INSERTION=false) is strictly
more informative AND plausibly lowers the same memory-pressure risk that
likely killed this run (far fewer antenna cells inserted -- run1/run2 both
showed 47,385+ ANTENNA_ instances from the heuristic pass alone, vs 1,934 in
the antenna-key-free baseline; removing that pass should meaningfully
shrink total processed geometry for magic-drc too). Reflexively launched a
same-config relaunch first (tmux session sky130_soc_58q_run2b) then killed
it within seconds, before it had done real work, once this reasoning was
worked through -- recorded so the aborted launch doesn't look like an
unexplained extra run if anyone greps tmux/process history later.

FIX APPLIED: pnr/sky130/soc/config.json -- RUN_HEURISTIC_DIODE_INSERTION
true -> false. Unchanged: RUN_ANTENNA_REPAIR=true, GRT_ANTENNA_ITERS=8,
GRT_ANTENNA_MARGIN=25, DIODE_ON_PORTS absent (still off), CLOCK_PERIOD=25.0,
TIMING_VIOLATION_CORNERS=['*']. This is run 3 of the antenna/hold
investigation (bead 58q). Launching next.

--- RUN_2026-07-30_06-42-17 (run 3) -- HYPOTHESIS CONFIRMED, HOLD FULLY
CLOSED AT ALL 9 CORNERS ---

Monitor rebuilt per coordinator feedback: CPU-time-delta liveness (ps -eo
pid,comm,cputimes, flag only if a step's worker process accumulates ZERO
additional CPU time across 2 consecutive 3-min polls) instead of file-mtime,
plus per-step baselines from run1/run2 disk data (repairantennas ~1080s,
detailedrouting ~450s, magic-drc ~1900s, klayout-drc ~4800s, netgen-lvs
~450s) for context rather than as an alert trigger by itself. Zero false
positives this run (unlike the old mtime-based detector, which fired twice
on healthy compute-bound steps in this same run before being replaced).

DIODE COUNT (39-openroad-repairantennas/state_out.json, exact metric read,
not estimated): antenna_diodes_count = 2,482 (== design__instance__count__
class:antenna_cell, the two metrics agree here unlike run1/run2 where they
diverged). Compare:
    baseline (no antenna keys):              1,934
    run1 (all 4 keys incl. heuristic):       47,385
    run2 (heuristic on, DIODE_ON_PORTS off): 47,530
    run3 (heuristic OFF, ITERS=8/MARGIN=25):  2,482
Turning off RUN_HEURISTIC_DIODE_INSERTION alone collapses the count back
near baseline (the small excess over 1,934 is consistent with
GRT_ANTENNA_ITERS=8/MARGIN=25 being more thorough than the pre-antenna-key
default 3/10%). Confirms the coordinator's hypothesis: the heuristic pass,
not GRT-based repair, drove the 24x cell-count spray.

CLOCK-TREE DIODE COUNT, same netlist snapshot method used throughout this
investigation (40-openroad-resizertimingpostgrt/soc_top.nl.v, grep
ANTENNA_* instances whose net matches clk_i/clk_i_regs/clknet/clkbuf):
    run1/run2: 1,589 (identical both runs)
    run3:      4
ANTENNA_clkbuf_0_clk_i_A / ANTENNA_clkbuf_regs_0_core_clk_A (the specific
diodes found earlier sitting directly on the clock root) are ABSENT from
run3's netlist entirely.

CLOCK LATENCY, decisive falsification check, same method every time
(clk_i -> u_cpu/clk_i, nom_tt, from STAPostPNR max.rpt clock path):
    baseline (clean):                0.870159 ns
    run1 (heuristic+DIODE_ON_PORTS): 1.439363 ns  (+0.569)
    run2 (heuristic only):           1.388234 ns  (+0.518)
    run3 (heuristic OFF):            0.933178 ns  (+0.063)  -- 89% of the
                                                                 gap recovered
First-hop delay (clk_i port -> clkbuf_0_clk_i/A) confirms the same pattern:
0.319984 -> 0.787429 -> 0.743895 -> 0.370022 ns (run3 nearly back to
baseline). GUARD PASSES CLEANLY: latency came back down almost to baseline
when the diodes were removed, exactly as the hypothesis predicted -- not the
ambiguous partial recovery seen in run2's DIODE_ON_PORTS-only experiment.

HOLD RESULT (51-openroad-stapostpnr/summary.rpt): Hold Vio Count = 0 AT
EVERY SINGLE CORNER. Slack all positive:
    nom_tt +0.2400   nom_ss +0.2693   nom_ff +0.1215
    min_tt +0.2911   min_ss +0.5311   min_ff +0.1204
    max_tt +0.0534   max_ss +0.0274   max_ff +0.1229
Worst corner (max_ss) closes by only +0.0274 ns -- thin, but clean. GOAL MET
for the first time in this investigation.

SETUP: unchanged from expectation -- tt/ff all TNS 0.0000, 0 violations
(clean, matching every prior run in this campaign); ss still fails as
expected (nom_ss -3.1228, min_ss -1.2536, max_ss -4.6432) -- frequency
question stays parked, not being re-judged.

ANTENNA (44-openroad-checkantennas-1, final post-DRT, same method as every
prior read in this file): 141 rows / 120 unique nets / 140 unique pins.
clk_i confirmed ABSENT (grep, not assumed). Larger residual than run1/run2's
52-54/46-48 because the heuristic pass was also fixing non-clock-tree
violators as a side effect of its broad spray; losing it costs some of that
incidental coverage. This is the expected, quantified trade the coordinator
asked to see: full hold closure at the cost of a bigger (but still ~68%
reduced from the 147/127 starting point) antenna residual.

STATUS: STA/antenna results reported to coordinator as they landed, not
held back. Flow continued past this point (not stopped) because the result
is a clear PASS on the hold goal, not a failure -- letting it run to
manufacturability.rpt per the agreed plan for the full gate table
(LVS/DRC/PDN tail still pending as of this entry).

--- HEURISTIC_ANTENNA_THRESHOLD investigation (coordinator's proposed "third
option", run 4 candidate) -- MEASURED, NOT GUESSED, VERDICT: NO CLEAN
THRESHOLD EXISTS ---

METHOD: wrote a standalone OpenROAD Tcl script (not part of the standard
flow) to compute per-net Manhattan bounding-box span for every net in run3's
37-openroad-repairdesignpostgrt/soc_top.odb (post-CTS/post-GRT-resize,
pre-antenna-repair -- the same geometry basis both the heuristic script and
this analysis use). Method matches diodes.py's own net_manhattan_distance:
bbox over all ITerm getAvgXY() + BTerm pin centers, in microns via
getDbUnitsPerMicron. Output: /tmp/.../scratchpad/net_spans.csv, 34,197 nets.
Also discovered (reading odb.py + diodes.py source, not assumed): the
heuristic step (Odb.FuzzyDiodePlacement -> diodes.py `place` subcommand)
never passes `--port-protect` in its get_command(), so it inherits the
CLI's OWN default of `"in"` -- INDEPENDENT of the LibreLane-level
DIODE_ON_PORTS variable entirely. This means the heuristic pass, whenever
enabled, ALWAYS force-inserts a diode on every INPUT port net (io_protect
bypasses the span<threshold check unconditionally) -- clk_i's port-adjacent
net WILL get a diode under heuristic+ANY finite threshold, no matter how
high. This is a previously-missed detail; DIODE_ON_PORTS and the heuristic
pass turned out to be two INDEPENDENT paths to the same clk_i diode all
along, not just "redundant" as characterized after run 2.

DISTRIBUTION (fine buckets, exact counts not estimates):
    clk-related nets (name contains "clk"), n=1345:
        min 6.4, median 68.7, max 3331.9 um
        [50,90) : 985 (73%)     <90 total: 1119 (83%)
        >=90    : 226 (17%)    >=105.4 (min violator span): 208
        >=150   : 141           >=200: 88   >=500: 8   >=1000: 2
    run3's still-violating nets (checkantennas-1, final, n=120, 85 resolved
    to placement data):
        min 105.4, median 685.6, max 4517.3 um
        100% are ABOVE 90 um -- ZERO in any bucket under 90
        [90,150):2  [150,200):7  [200,500):17  [500,1000):40  [1000,5000):19

OVERLAP CHECK (coordinator's second question): cross-referenced run3's 120
violating net names against the full set of 3,383 unique nets run1's
heuristic pass protected with a diode (extracted from
49-openroad-fillinsertion/soc_top.nl.v, all `.DIODE(netname)` connections,
47,385 diode instances -> 3,383 unique nets, ~14 diodes/net average since
one diode is inserted per net PER SINK PIN, not once per net). RESULT:
120/120 (100%) of run3's residual violators were ALSO protected by run1.
The heuristic pass was NOT "mostly fixing many short ones" -- every single
net it would need to protect to close run3's residual IS a net it already
covered. This directly answers the coordinator's second question but does
NOT by itself make a threshold viable, because of the next finding.

WHY NO THRESHOLD WORKS: the clock tree is NOT uniformly short-hop. Levels 6
and 7 (near-leaf CTS stages, hundreds of individual `clknet_6_N_0_clk_i_regs`
/ `clknet_7_N__leaf_clk_i_regs` nets) span 105-800 um EACH -- squarely
inside the SAME range as the real antenna violators (105-4517 um, median
686). 208 clock nets sit at or above the minimum violator span (105.4 um);
raising the threshold from the current 90 up to 105.4 (the tightest
possible bound that loses zero violators) only trims 18 of 226 clock nets
-- negligible. Pushing further: at threshold=500 um, clock-net coverage
drops to 8 (96% cut from 226) but 26/120 (22%) of real violators are also
lost; at threshold=1000, clock coverage drops to 2 (clk_i itself +
delaynet_2_core_clk, both structurally guaranteed regardless of threshold
for clk_i, or just very long for the delay-balance net) but 66/120 (55%) of
real violators are lost. THE TWO POPULATIONS OVERLAP ACROSS THEIR ENTIRE
COMMON RANGE (105-800 um) -- there is no cut point where clock-tree
coverage drops to near-zero while violator coverage stays near-100%. This
is the "distributions overlap heavily" case the coordinator asked me to
call out plainly if it occurred.

ADDITIONAL DATA POINT (bears on but doesn't overturn the above): run3 (heuristic
fully OFF) still ended up with 3 diodes ON clk_i itself -- inserted by
GRT-based RepairAntennas with generic names (ANTENNA_1103/1104/1105), NOT
abutting clkbuf_0_clk_i/A the way the heuristic/port scripts do. Hold
closed cleanly anyway. This shows clk_i CAN tolerate some diode presence
without breaking hold -- the damage mechanism is specifically the
DiodeInserter class's "abut the first sink instance" placement strategy
(place_diode_stdcell, side_strategy=source) landing directly on the clock
root buffer, not diode-on-clk_i in general. A GRT-legalized diode elsewhere
along the same net is a materially different physical outcome. This doesn't
create a viable threshold-based fix (the diode/no-diode-at-the-root
distinction isn't controlled by HEURISTIC_ANTENNA_THRESHOLD), but it is
worth recording as a nuance for whoever next touches this area.

RECOMMENDATION: do NOT run the threshold experiment as conceived (heuristic
back on + raised threshold). The measured distributions do not separate at
any threshold value tested or interpolated between; a "run 4" here would
either reproduce run1/run2's hold damage (low threshold) or fail to close
most of the real antenna residual anyway (high threshold), for a result
strictly worse than run3 on at least one axis in every case checked. If
further antenna reduction beyond run3's 140/120 is wanted, the untried lever
consistent with this data is pushing GRT_ANTENNA_ITERS / GRT_ANTENNA_MARGIN
further (GRT-based repair is the mechanism that closed clk_i in run3
without the clock-root disruption, and it already narrowly outperforms
heuristic on placement-legalization safety per the point above) -- not
re-enabling the heuristic pass at any threshold.

--- RUN_2026-07-30_22-10-20 (run 4, clock-net-skip patch) -- PATCH VERIFIED
WORKING AS DESIGNED, BUT GUARD FAILS: HOLD REGRESSED AGAIN ---

User approved and directed applying a librelane patch (documented above and
in knowledge.md + memory/pd/patches/58q_librelane_heuristic_diode_skip_
clock_nets.diff, committed a569818) to exclude dbNet SigType==CLOCK nets
from Odb.HeuristicDiodeInsertion, plus kill its independent --port-protect
"in" default. RUN_HEURISTIC_DIODE_INSERTION turned back on,
HEURISTIC_ANTENNA_SKIP_CLOCK_NETS: true added, everything else identical to
run3 (GRT_ANTENNA_ITERS=8, GRT_ANTENNA_MARGIN=25, CLOCK_PERIOD=25.0,
TIMING_VIOLATION_CORNERS=['*'], DIODE_ON_PORTS absent).

PATCH MECHANISM VERIFIED WORKING, TWICE: (1) smoke test before launch
(openroad -python diodes.py place --skip-clock-nets --port-protect none
against a saved odb): exactly 1,327 clock nets skipped, 0 clk_i diodes.
(2) real flow, 39-odb-heuristicdiodeinsertion/2-openroad-detailedplacement/
soc_top.nl.v: 44,408 total diodes (down from unpatched 47,385), ZERO with
any clk-related name, explicit grep for `.DIODE(clk_i)` / `.DIODE(clk_i_
regs)` returns nothing. Independently reconfirmed at the FINAL post-DRT
netlist too (52-...-later steps). The patch does exactly what it was
designed to do.

ANTENNA: BEST RESULT OF ANY RUN. 44-openroad-checkantennas-1 (post-DRT,
final, same method as every read in this file): 40 rows / 39 unique nets /
40 unique pins, clk_i confirmed ABSENT. Beats run1 (52/46), run2 (54/48),
AND run3 (140/120) by a wide margin. In-flight (post-repair, pre-DRT) number
was 19 net / 20 pin -- the heuristic pass's broader (non-clock) coverage is
clearly doing real work here, on top of GRT's own contribution.

HOLD: REGRESSED AGAIN, worse than run3, same 5 corners as run1/run2:
    corner    run3      run4      hold_vio_count(run4)
    nom_tt   +0.2400   -0.1932   10
    nom_ss   +0.2693   -0.2491    6
    nom_ff   +0.1215   +0.0706    0  (still clean)
    min_tt   +0.2911   +0.0869    0  (still clean)
    min_ss   +0.5311   +0.1776    0  (still clean)
    min_ff   +0.1204   +0.1207    0  (still clean)
    max_tt   +0.0534   -0.4291   18
    max_ss   +0.0274   -0.6279   15
    max_ff   +0.1229   -0.1073   10
GOAL NOT MET. Overall hold TNS -4.7341, 59 violations total (all "of which
reg to reg"=0, same APB-debug-bus class as every prior regression in this
investigation -- re-confirmed, no new violator class opened up).

DECISIVE FALSIFICATION GUARD -- FAILS, exactly the scenario the coordinator
asked to be told about plainly rather than have papered over:
    clk_i -> u_cpu/clk_i, nom_tt, same method every time:
        baseline (clean):           0.870159 ns
        run1 (heuristic, no fix):   1.439363 ns  (+0.569)
        run2 (DIODE_ON_PORTS off):  1.388234 ns  (+0.518)
        run3 (heuristic OFF):       0.933178 ns  (+0.063)
        run4 (clock-net exclusion): 1.410208 ns  (+0.540)  -- back up near
                                                               run1/run2,
                                                               NOT run3
First-hop delay (clk_i port -> clkbuf_0_clk_i/A): 0.320 -> 0.787 -> 0.744 ->
0.370 -> 1.410208's own first hop is 0.763076 (fanout 5, matching baseline's
fanout exactly, NOT run1/run2's fanout 4) -- so this is not the same
topology change as before; something is inflating the DELAY on the same
logical connectivity as baseline, despite zero diodes anywhere near this
net or the rest of the clock tree.

CONCLUSION, stated plainly per instruction: the clock-net exclusion, though
verified working exactly as designed (zero clock-tree diodes, zero clk_i
diodes), is INCOMPLETE as a fix for the hold regression. Diodes physically
sitting on clock-tree nets was A cause (proven by run3: remove ALL diodes
including clock-tree ones -> clean hold) but not THE cause in isolation --
run4 proves you can remove every clock-tree diode specifically and still
get nearly the same hold damage. Leading unconfirmed hypothesis (explicitly
flagged as NOT proven to the same evidentiary standard as the diode-
placement mechanism): general placement congestion from the heuristic
pass's ~44,000 non-clock diode insertions elsewhere in the design pushes
standard-cell placement near the clock root regardless of whether a diode
itself lands there, lengthening clk_i's physical route even at unchanged
logical fanout. NOT verified by direct measurement the way the diode-
placement mechanism was (would need a placement/congestion diff between
run3 and run4 near the clock root specifically -- not attempted this
session). Reported as the leading candidate only, not a confirmed cause.

STATUS: reported to coordinator with the guard failure stated plainly, not
hidden or reframed as a partial win. DRC/LVS/manufacturability tail let run
to completion per instruction for one full gate table on this configuration
regardless of the hold outcome. No further fix proposed unilaterally --
holding for direction, per this investigation's established pattern.
