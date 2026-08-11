###############################################################################
# STAGED COPY — GH #96 preflight (2026-08-05).
# Canonical source: pnr/constraints/phase5_soc_multiclock.sdc
# This copy exists only so PNR_SDC_FILE/SIGNOFF_SDC_FILE/FALLBACK_SDC_FILE's
# "dir::constraints/..." resolution (relative to pnr/asap7/soc/) finds it,
# matching how phase5_soc.sdc is consumed by the single-clock run-14 config.
# Edit the canonical file above and re-copy; do not hand-edit this copy.
###############################################################################

###############################################################################
# phase5_soc_multiclock.sdc — 2-domain IMPLEMENTATION constraints for soc_top
# (synthesis / P&R). Post-route CDC budget verification lives in the
# COMPANION file phase5_soc_multiclock_check.sdc — see the section 11-13
# note below for why the split exists (bead claude_verilog_test-k07).
#
# GH #94 / bead claude_verilog_test-oa7 (epic #90 -> #91..#96).
# GH #96 / bead claude_verilog_test-k07 (2026-08-02): split this file per
# OpenTitan precedent after tool-verified evidence that set_max_delay
# exceptions on CDC paths are NOT honoured once those paths sit between two
# set_clock_groups -asynchronous groups. See section 11-13 header below.
#
# STATUS: authored constraint-only deliverable. NOT yet wired into any
# config.json PNR_SDC_FILE/SIGNOFF_SDC_FILE/FALLBACK_SDC_FILE pointer — GH #96
# owns the actual re-closure P&R run that will consume this file (or a
# reconciled copy of it) as pnr/asap7/soc/constraints/*.sdc's replacement.
# Everything below is derived from static RTL/SDC/doc inspection; nothing
# here has been exercised by OpenSTA/OpenROAD. See the accompanying report
# for the full "what remains unvalidated" list.
#
# IMPORTANT: all time values are in PICOSECONDS (ASAP7 stdcell Liberty
# declares time_unit: "1ps" — see pnr/asap7/soc/constraints/phase5_soc.sdc
# and pnr/asap7/cpu/constraints/asap7.sdc headers for the historical Run
# 7-32 units bug this project already paid for once; do not repeat it here).
#
# Base file: this is a considered EVOLUTION of the signed-off single-clock
# pnr/asap7/soc/constraints/phase5_soc.sdc (run 14, 571 MHz / 62.9 mW / 0 DRC
# sign-off — see docs/PHASE5_RUN_HISTORY.md). All 10 of that file's sections
# are preserved below (renumbered), with two substantive changes:
#   (a) a second clock (cpu_clk) plus an asynchronous clock-group declaration
#       between it and the existing clock (renamed sys_clk for symmetry with
#       the async_axi_fifo.sv / apb_cdc_bridge.sv / docs/3PLL_CDC_EVALUATION.md
#       naming convention — "cpu_clk" and "sys_clk" are the names already used
#       in prose throughout this CDC epic);
#   (b) three new sections (11-13, plus 12a added by the GH #95 fix below)
#       constraining the CPU<->fabric CDC boundary that GH #91/#92/#93 built
#       and this bead's whole reason for existing: async_axi_fifo
#       (u_cpu_axi_cdc), apb_cdc_bridge (u_apb_pll2_cdc, and — GH #95 fix,
#       bead claude_verilog_test-eg2 — u_apb_dbg_cdc), and the PMU/IRQ
#       single-bit crossings into cpu_core_clk.
#
# Clock topology (2-domain SoC, sv2v synthesis, GH #92/#93):
#   clk_i      = fabric-domain top-level reference input. CTS root for sys_clk.
#   core_clk   = PLL stub output net (BUFx2 passthrough, divide-1) — feeds
#                GPU, crossbar, DMA, SRAM, all peripherals, and the PMU.
#   cpu_clk_i  = SECOND, INDEPENDENT top-level reference input (GH #92) — its
#                own PLL stub (u_cpu_pll_sub) is NOT derived from clk_i.
#   cpu_core_clk = u_cpu_pll_sub's PLL-stub output net (BUFx2 passthrough,
#                divide-1) — feeds u_cpu_cg (rv32i_clock_gate), whose output
#                cpu_gated_clk feeds u_cpu (the CPU hard macro) and
#                u_cpu_axi_cdc's s_* (CPU-domain) face.
#
# Run-13 lesson (preserved from the base file, and extended to cpu_core_clk):
#   create_generated_clock on a PLL-stub BUFx2 output pin caused CTS to build
#   TWO independent, unbalanced clock trees (macro-clk sinks vs std-cell FF
#   sinks), producing ~214 ps setup skew. Fix: do NOT create_generated_clock
#   for core_clk OR cpu_core_clk. Constrain the PORT (clk_i / cpu_clk_i)
#   directly; CTS (with the appropriate CLOCK_NET config) traces through each
#   PLL-stub BUFx2 automatically so macro and std-cell sinks land on one
#   balanced tree per domain.
#
# SoC fmax targets (per-domain, GH #93):
#   sys_clk (clk_i / core_clk):     1750 ps period (571 MHz, GPU-governed).
#   cpu_clk (cpu_clk_i / cpu_core_clk / cpu_gated_clk): 780 ps period
#     (1282 MHz), matching pnr/asap7/cpu/config.json's standalone CPU
#     sign-off target — the CPU hard macro is characterized at this period,
#     and no longer needs to be de-rated to sys_clk's 1750 ps the way the old
#     single-clock SoC forced it to be (see the revised section 10 note).
###############################################################################

###############################################################################
# 1. Primary clocks
###############################################################################
create_clock -name sys_clk -period 1750 -waveform {0 875} [get_ports clk_i]

set_clock_uncertainty -setup 15 [get_clocks sys_clk]
set_clock_uncertainty -hold  10 [get_clocks sys_clk]
set_clock_transition   10       [get_clocks sys_clk]
set_clock_latency -source 50    [get_clocks sys_clk]

create_clock -name cpu_clk -period 780 -waveform {0 390} [get_ports cpu_clk_i]

set_clock_uncertainty -setup 15 [get_clocks cpu_clk]
set_clock_uncertainty -hold  10 [get_clocks cpu_clk]
set_clock_transition   10       [get_clocks cpu_clk]
set_clock_latency -source 50    [get_clocks cpu_clk]

###############################################################################
# 2. core_clk / cpu_core_clk — generated from clk_i / cpu_clk_i through their
#    respective PLL-stub BUFx2 cells. Run-13 lesson (see header): do NOT
#    create_generated_clock for either. CTS traces through both BUFx2 cells
#    automatically (CLOCK_NET config per domain) so macro and std-cell sinks
#    on each side land on one balanced tree.
###############################################################################
# (no create_generated_clock for core_clk)
# (no create_generated_clock for cpu_core_clk)
puts "INFO: No generated clock for core_clk — CTS traces through the fabric PLL BUFx2 as part of sys_clk's tree."
puts "INFO: No generated clock for cpu_core_clk — CTS traces through the CPU-domain PLL BUFx2 as part of cpu_clk's tree."

###############################################################################
# 3. Clock-group relationship — sys_clk and cpu_clk are genuinely asynchronous
#    (two independent top-level reference ports, GH #92 — deliberately NOT a
#    divided/generated pair; pll_clkgen_stub is a pure passthrough, so two
#    PLLs off one reference would be bit-identical, hence a second PORT).
#    -asynchronous tells STA there is no fixed phase relationship: ordinary
#    setup/hold analysis between the two domains is skipped (would otherwise
#    report fabricated violations on every unrelated pair of FFs that happen
#    to sit in different domains). This IS needed for real synthesis/P&R —
#    do not remove it from this (implementation) file.
#
#    bead claude_verilog_test-k07 (2026-08-02) — TOOL-VERIFIED CORRECTION:
#    a prior version of this comment claimed set_max_delay -datapath_only
#    overrides in sections 11-13 "OpenSTA honours even though the clock
#    groups are otherwise asynchronous." That claim was UNVERIFIED and is
#    WRONG on both counts, confirmed with OpenSTA 2.6.0 (both the standalone
#    `sta` binary and OpenROAD's embedded STA engine, same STA-0563 error
#    code) against a synthetic sky130hd netlist reproducing this exact
#    two-clock / set_clock_groups -asynchronous / set_max_delay -through
#    topology:
#      (a) `-datapath_only` is not an implemented flag of OpenSTA's
#          set_max_delay/set_min_delay (see sdc/Sdc.tcl: only -rise -fall
#          -ignore_clock_latency -reset_path -comment are recognised).
#          read_sdc aborts immediately with "set_max_delay -datapath_only
#          is not a known keyword or flag" (STA-0563) the instant it hits
#          the first occurrence — every set_max_delay line at and after
#          that point (all of sections 11-13, and the section 15 coverage
#          gate) NEVER EXECUTES. This is not "masked"; it is a hard parse
#          failure that would have aborted read_sdc for this entire file.
#      (b) even after removing the illegal flag so the SDC parses, a
#          side-by-side comparison (identical set_max_delay -through
#          exception, with vs without set_clock_groups -asynchronous
#          between the two clocks) shows the exception is NOT applied when
#          -asynchronous is present: report_checks -to <the excepted pin>
#          returns "No paths found" under normal path_delay queries, and
#          only appears under -unconstrained, reported as
#          "Path Group: unconstrained" / "(Path is unconstrained)" — i.e.
#          OpenSTA drops the max_delay check entirely rather than applying
#          it. A further control (set_false_path -from/-to clocks, instead
#          of set_clock_groups) reproduces the same result even though the
#          set_max_delay exception is -through-qualified and therefore
#          "more specific" — confirming the textbook precedence rule
#          set_false_path > set_max_delay applies REGARDLESS of exception
#          specificity in this tool, not just when tied (matching this
#          bead's original hypothesis and the OpenTitan precedent cited
#          below).
#    CONSEQUENCE: sections 11-13's CDC budgets cannot live in the same file
#    as this set_clock_groups -asynchronous declaration and be honoured by
#    OpenSTA. Per OpenTitan precedent (hw/top_earlgrey/syn/
#    chip_earlgrey_asic_check_only.sdc), those budgets have been MOVED to
#    phase5_soc_multiclock_check.sdc, a separate post-route CDC-verification
#    SDC that intentionally does NOT declare sys_clk/cpu_clk asynchronous
#    (or false-path them) so the set_max_delay budgets are genuinely timed.
#    That file is not a substitute for this one at synthesis/P&R time.
###############################################################################
set_clock_groups -name cdc_boundary -asynchronous \
    -group [get_clocks sys_clk] \
    -group [get_clocks cpu_clk]

###############################################################################
# 4. Asynchronous resets — not timed
###############################################################################
set_false_path -from [get_ports rst_n_i]
set_false_path -from [get_ports cpu_rst_n_i]

###############################################################################
# 5. SoC I/O delays — timed ports only, per domain.
#    Run-13 lesson (preserved): 175 ps (10% of 1750 ps), not 350 ps (20%) —
#    the larger figure fed STA a pessimism large enough to make register ->
#    macro paths appear to violate even under the 2-cycle multicycle.
#    Exclude both clocks and both resets from the timed set.
#
#    Per-domain I/O delay note (GH #94 item 3): cpu_clk_i's ONLY companion
#    top-level ports are cpu_rst_n_i (false-pathed above, section 4) and
#    cpu_pll_locked_o (false-pathed below, section 7) — soc_top exposes no
#    other CPU-domain payload port at the chip boundary; every other timed
#    port (APB debug, UART, SPI, observability) is sourced/sunk in the
#    fabric domain via apb_interconnect / axil_to_apb, which stays on
#    core_clk. There is therefore no separate "cpu_clk I/O delay" block to
#    write here beyond the clock/reset/false-path treatment already given to
#    cpu_clk_i/cpu_rst_n_i/cpu_pll_locked_o — this is a considered absence,
#    not an oversight.
###############################################################################
set _in_timed {}
foreach _p [all_inputs] {
    set _n [get_full_name $_p]
    if {$_n ne "clk_i" && $_n ne "rst_n_i" && $_n ne "cpu_clk_i" && $_n ne "cpu_rst_n_i"} {
        lappend _in_timed $_p
    }
}

if {[llength $_in_timed] > 0} {
    set_input_delay  -max 175 -clock sys_clk $_in_timed
    set_input_delay  -min  10 -clock sys_clk $_in_timed
}

set_output_delay -max 175 -clock sys_clk [all_outputs]
set_output_delay -min  10 -clock sys_clk [all_outputs]

###############################################################################
# 6. Debug/APB interface — infrequent config path; false-path for timing.
#
#    GH #95 fix (bead claude_verilog_test-eg2): the APB3 debug slave does NOT
#    sit entirely in the fabric (sys_clk) domain any more. It never truly did
#    post-GH #93 — u_cpu (the debug slave) moved onto cpu_gated_clk while
#    these top-level ports fed it directly and unsynchronised, which is
#    exactly the cdc_snitch BAD=233 finding this fix closes. The apb_* ports
#    themselves ARE still sys_clk-domain (that is what "false-path for
#    timing" below is about — these are chip-boundary, infrequent-access
#    ports with no meaningful setup/hold relationship to any internal clock),
#    but they now terminate at a second apb_cdc_bridge instance,
#    u_apb_dbg_cdc, whose s-face is sys_clk (core_clk/core_rst_n, matching
#    apb_interconnect/axil_to_apb) and whose m-face is cpu_clk
#    (cpu_gated_clk/cpu_domain_rst_n, matching u_cpu itself) — see section 12a
#    for its internal CDC timing exceptions, mirroring u_apb_pll2_cdc's
#    treatment in section 12. APB_PLL2 (the other APB slot reaching into the
#    cpu_clk domain) continues to be bridged by u_apb_pll2_cdc as before.
###############################################################################
set _apb_in {}
set _apb_out {}
foreach _p [all_inputs] {
    if {[string match "apb_*" [get_full_name $_p]]} {
        lappend _apb_in $_p
    }
}
foreach _p [all_outputs] {
    if {[string match "apb_*" [get_full_name $_p]]} {
        lappend _apb_out $_p
    }
}
if {[llength $_apb_in] > 0}  { set_false_path -from $_apb_in }
if {[llength $_apb_out] > 0} { set_false_path -to   $_apb_out }

###############################################################################
# 7. Observability outputs — registered; relax output delay.
#    commit_valid_o/commit_pc_o/commit_insn_o are now genuinely sourced from
#    u_cpu on cpu_gated_clk (cpu_clk domain) rather than core_clk, per GH #93
#    — false_path suppresses the check regardless of source domain, so no
#    exception-type change is needed, only this note. cpu_pll_locked_o added
#    (mirrors pll_locked_o's treatment for the fabric-domain PLL).
###############################################################################
foreach _sig {commit_valid_o commit_pc_o commit_insn_o pll_locked_o cpu_pll_locked_o gpu_irq_o} {
    set _port [get_ports -quiet $_sig]
    if {[llength $_port] > 0} {
        set_false_path -to $_port
    }
}

###############################################################################
# 8. UART/SPI asynchronous board-level pins — unaffected (peripherals stay in
#    the fabric domain).
###############################################################################
foreach _sig {uart_rx_i spi_miso_i} {
    set _p [get_ports -quiet $_sig]
    if {[llength $_p] > 0} { set_false_path -from $_p }
}

###############################################################################
# 9. SRAM input hold false-paths (Liberty artifact: no hold arc on SRAM
#    inputs) — unaffected (sram_controller stays in the fabric domain).
###############################################################################
set _sram_din  [get_pins -hierarchical -filter "name =~ *din0*"  -quiet]
set _sram_addr [get_pins -hierarchical -filter "name =~ *addr0*" -quiet]
set _sram_csb  [get_pins -hierarchical -filter "name =~ *csb0*"  -quiet]
if {[llength $_sram_din]  > 0} { set_false_path -hold -to $_sram_din  }
if {[llength $_sram_addr] > 0} { set_false_path -hold -to $_sram_addr }
if {[llength $_sram_csb]  > 0} { set_false_path -hold -to $_sram_csb  }

###############################################################################
# 10. Hard-macro timing budgets — CPU and GPU are black-box macros.
#
#     GPU (unchanged from the base file): GPU stays entirely in the fabric
#     domain (crossbar, sys_clk) both before and after GH #93, so its
#     same-domain 2-cycle relaxation is preserved as-is. Run-13 lesson: the
#     worst setup violators were FF -> u_gpu/m_axi_rdata[N] paths (WNS
#     -364 ps) — a std-cell-FF -> macro-OUTPUT-port path, not a real
#     FF -> FF path (the GPU macro's own internal FFs are already covered by
#     its LIB). Two-cycle multicycle on the real crossbar -> macro INPUT
#     interface paths remains appropriate.
#
#     CPU (CHANGED from the base file, GH #93/#94): u_cpu no longer connects
#     to the fabric-domain crossbar directly at all — GH #93 re-routed the
#     CPU's AXI4 master entirely through u_cpu_axi_cdc's s_* (cpu_clk) face
#     (soc_top.sv "M0: CPU -> u_cpu_axi_cdc -> crossbar M0"). Every signal
#     that now reaches a u_cpu pin is already same-domain (cpu_clk): either
#     u_cpu_axi_cdc's s_* face, or one of the cpu_core_clk-synchronised
#     PMU/IRQ signals in section 13. The OLD 2-cycle sys_clk-relative
#     relaxation on u_cpu pins (inherited from the single-clock SoC, where
#     the CPU macro's own 780 ps-characterized inputs had to be de-rated to
#     survive a 1750 ps fabric cycle) is THEREFORE REMOVED here: u_cpu's
#     interface is now a normal single-cycle cpu_clk (780 ps) timing
#     problem, identical in kind to the CPU's own standalone sign-off SDC
#     (pnr/asap7/cpu/constraints/asap7.sdc) rather than a cross-domain
#     derating exercise. If a future run finds real single-cycle violations
#     on this interface, that is real information the multicycle used to
#     hide — do not silently reintroduce the relaxation without checking
#     Liberty-vs-Liberty margin at 780 ps first.
###############################################################################
set _gpu_in  [get_pins -hierarchical -filter "full_name =~ *u_gpu/*" -quiet]

if {[llength $_gpu_in] > 0} {
    set_multicycle_path -setup 2 -to $_gpu_in
    set_multicycle_path -hold  1 -to $_gpu_in
}

###############################################################################
# 10a. CPU APB debug read data — false path, matching the CPU macro's OWN
#      sign-off contract. Added for GH #96 run 17 after run 16 measured it.
#
#      Section 10 above says: "If a future run finds real single-cycle
#      violations on this interface, that is real information the multicycle
#      used to hide — do not silently reintroduce the relaxation without
#      checking Liberty-vs-Liberty margin at 780 ps first." Run 16
#      (RUN_2026-08-06_00-10-40) found exactly such violations, and that
#      check was then done. Findings:
#
#      * cpu_clk WNS = -205.34 ps, TNS = -7261.72 ps over 194 violating
#        endpoints. 33 of those traverse the CPU macro; the other 161 do not
#        and are only at -44.93 ps (those are a genuine synthesis-target
#        problem, addressed separately by CLOCK_PERIOD 0.78, NOT here).
#      * Every one of the 33 is the same shape: fabric FF -> u_cpu APB
#        address input -> a single 800.71 ps combinational arc inside the
#        macro -> u_cpu/apb_prdata_o[*] -> fabric FF. One macro-internal arc
#        of 800.71 ps cannot fit a 780 ps period; no placement, sizing or
#        synthesis knob can change it, because it is fixed in the macro's
#        Liberty.
#      * Liberty-vs-Liberty check, which is the decisive evidence: the CPU's
#        own standalone ASAP7 sign-off at this very period does
#            set_false_path -to [get_ports apb_prdata_o[*]]
#        (pnr/asap7/cpu/constraints/asap7.sdc:121). The macro was therefore
#        NEVER characterized to meet 780 ps on this path. Timing it here
#        holds the macro to a constraint its own sign-off explicitly excluded
#        — the violation is an artifact of the SoC constraining it more
#        tightly than the block, not a real design failure.
#
#      So this is not the old cross-domain de-rating being smuggled back in.
#      It is the block-level contract being honoured at the top level, and it
#      is deliberately NARROWER than run 14's blanket
#      `set_multicycle_path -setup 2 -to *u_cpu/*`: only the APB debug READ
#      data path is excepted. Everything else on the u_cpu interface — the
#      whole AXI4 master through u_cpu_axi_cdc, the PMU/IRQ synchronised
#      signals — stays a normal single-cycle cpu_clk check, so a real
#      datapath violation there is still reported.
#
#      Scope note: the APB address/control INPUTS are deliberately NOT
#      excepted. The standalone SDC times them (set_input_delay -max 120,
#      asap7.sdc:99-112), so they carry a real single-cycle requirement and
#      must keep being checked here.
#
#      Safety: APB debug is an infrequent, non-performance config interface
#      (same rationale as the top-level apb_* port false paths in section 6),
#      and u_apb_dbg_cdc drives it from a REGISTERED, captured address
#      (m_paddr_o = cmd_paddr_cap_q, apb_cdc_bridge.sv:648 -- line number as
#      of bead claude_verilog_test-rfz's NRZ->RZ conversion) held stable
#      across D_SETUP -> D_ACCESS until m_pready_i, i.e. >= 2 cpu_clk cycles.
#      The read data is likewise captured only on m_pready_i.
###############################################################################
#      -through, NOT -from/-to. At block level apb_prdata_o is a PORT and
#      therefore a path ENDPOINT, so the standalone SDC writes
#      `set_false_path -to`. At SoC level the same physical path does not end
#      there: it starts at a fabric flop, enters the macro at an APB address
#      input, crosses the 800.71 ps combinational in->out arc, exits at
#      apb_prdata_o and continues to a fabric flop. The macro pin is a
#      THROUGH point. Measured on run 16's routed netlist, re-timed with its
#      own final/sdc so the constraint is the only variable:
#          -from  : cpu_clk WNS -205.34 ps, 194 violators  (NO EFFECT — the
#                   pin is not a startpoint, so nothing matched)
#          -through: cpu_clk WNS  -44.93 ps, 162 violators, TNS -7261.72 ->
#                   -1756.83, achieved 1014.88 -> 1212.23 MHz
#      sys_clk was byte-identical (+106.217033 ps, 0 violators) in both,
#      confirming the exception is confined to the CPU domain.
###############################################################################
# RETIRED 2026-08-07 (bead cyb fixed at the source). apb_prdata_o is now a
# REGISTERED output of the CPU macro: the regenerated Liberty
# (pnr/asap7/cpu/macro/rv32i_cpu_top__nom_tt_025C_0p7V.lib) reports
# apb_prdata_o[*] as related_pin clk_i with timing_type rising_edge, where it
# previously carried a combinational arc from apb_paddr_i[9..11]/apb_psel_i/
# apb_pwrite_i. The 800.71 ps arc this exception existed to excuse no longer
# exists, so the exception is removed rather than left to hide a future
# regression. If cpu_clk setup regresses on the macro APB pins, do NOT simply
# restore this -- re-check the Liberty first, because a reappearing
# combinational arc would mean the macro abstract went stale again.
#
# set_false_path -through [get_pins u_cpu/apb_prdata_o[*]]   <-- retired

###############################################################################
# 10b. CPU macro APB INPUT multicycle — mirrors the CPU block's OWN sign-off
#      constraint. Added 2026-08-07 after run 20 measured the consequence of
#      omitting it.
#
#      WHAT MOVED. Registering apb_prdata_o (bead cyb) did NOT delete the APB
#      read mux; it RELOCATED where STA charges it. Before, the mux appeared in
#      the macro abstract as an ~800 ps COMBINATIONAL in->out arc, excused by
#      section 10a (now retired). After, the same logic appears as an INPUT
#      SETUP REQUIREMENT: the regenerated Liberty reports 876.85 ps of library
#      setup on u_cpu/apb_psel_i. Run 20 (no exception) therefore measured
#      cpu_clk WNS -350.05 ps over 15 violating endpoints, and every one of
#      those 15 ends at a macro APB input pin (apb_psel_i, apb_paddr_i[*],
#      apb_pwrite_i) — not one is a datapath failure.
#
#      WHY THIS IS CONTRACT-MIRRORING, NOT VIOLATION-HIDING. The CPU block has
#      always signed off this interface with exactly this relaxation:
#          pnr/asap7/cpu/constraints/asap7.sdc:183-184
#          set_multicycle_path -setup 3 -from [get_ports {apb_paddr_i[*] ...}]
#          set_multicycle_path -hold  2 -from [get_ports {apb_paddr_i[*] ...}]
#      under the header "APB multicycle — PREADY stretches for 2-cycle APB
#      handshake". Block-level STA confirms it: the worst apb_psel_i path has a
#      data-required time of 2480 ps (~3x780), and closes with +1328 ps. The
#      SoC was simply never mirroring that contract on the input side, because
#      until now the same logic reached it in output-arc form instead.
#
#      WHY IT IS SOUNDER NOW THAN IT WAS BEFORE. The protocol genuinely takes
#      more than one cycle: rv32i_cpu_top now inserts an APB3 wait state on
#      reads (apb_pready_o = apb_pwrite_i ? 1'b1 : apb_read_wait_q), and the
#      driving master holds the command stable for the whole transfer —
#      u_apb_dbg_cdc drives m_paddr_o from the REGISTERED cmd_paddr_cap_q
#      (apb_cdc_bridge.sv:648) and stays in D_ACCESS until m_pready_i. So the
#      3-cycle setup / 2-cycle hold window is one the hardware actually
#      provides, rather than an assertion about an infrequent path.
#
#      Measured effect on run 20's routed netlist, constraint as the only
#      variable: cpu_clk WNS -350.05 -> -60.66 ps, TNS -2406.71 -> -60.66,
#      violating endpoints 15 -> 1, achieved 884.92 -> 1189.54 MHz. sys_clk
#      byte-identical at +83.789642 ps, confirming CPU-domain-only scope.
###############################################################################
#      TCL GOTCHA (cost one wasted 5 h run, 2026-08-08): the pattern list below
#      MUST stay on a single line. A "\" line-continuation inside {braces} is
#      NOT a continuation — Tcl takes the backslash and newline literally, the
#      pattern matches nothing, and a `if {[llength ...] > 0}` guard then skips
#      the constraint in SILENCE. Run 21 was byte-identical to run 20 because of
#      exactly that. Hence the hard error below rather than a soft guard: an
#      exception that cannot bind must stop the flow, not quietly vanish.
set _cpu_apb_in [get_pins -quiet {u_cpu/apb_paddr_i[*] u_cpu/apb_psel_i u_cpu/apb_penable_i u_cpu/apb_pwrite_i u_cpu/apb_pwdata_i[*]}]

if {[llength $_cpu_apb_in] == 0} {
    puts "ERROR: SDC-EXCEPTION-MISS: section 10b matched no u_cpu APB input pins."
    error "phase5_soc_multiclock.sdc section 10b bound to nothing — refusing to run with the CPU macro APB inputs unconstrained."
}
puts "INFO: section 10b: APB input multicycle applied to [llength $_cpu_apb_in] macro pin(s)."
set_multicycle_path -setup 3 -to $_cpu_apb_in
set_multicycle_path -hold  2 -to $_cpu_apb_in

###############################################################################
# Sections 11-13 (async_axi_fifo gray-pointer/mem_q crossings, apb_cdc_bridge
# CDC (u_apb_pll2_cdc + u_apb_dbg_cdc), PMU/IRQ single-bit crossings into
# cpu_core_clk) MOVED to phase5_soc_multiclock_check.sdc.
#
# bead claude_verilog_test-k07 (2026-08-02): those set_max_delay exceptions
# cannot be honoured by OpenSTA in the same file as section 3's
# set_clock_groups -asynchronous (see section 3's header note above for the
# tool-verified evidence — a literal OpenSTA/OpenROAD read_sdc parse abort
# from the unsupported -datapath_only flag, and a proven "set_false_path
# beats set_max_delay regardless of -through specificity" precedence result
# even after that flag is removed). This file keeps set_clock_groups
# -asynchronous because it is still correct and necessary for real
# synthesis/P&R (suppresses fabricated setup/hold checks between the two
# genuinely-unrelated clock domains) — it simply can no longer also carry
# the CDC budget exceptions. phase5_soc_multiclock_check.sdc carries them,
# deliberately WITHOUT any clock-group/false-path declaration between
# sys_clk and cpu_clk, so the set_max_delay budgets are genuinely timed by
# OpenSTA when read against a post-route netlist for targeted
# report_checks -to/-through CDC-path queries (OpenTitan precedent:
# hw/top_earlgrey/syn/chip_earlgrey_asic_check_only.sdc). GH #96 owns
# wiring both files into the actual re-closure P&R + post-route check run;
# pnr/scripts/check_cdc_timing.tcl + `make check-cdc-timing-asap7-soc`
# (pnr/Makefile) is the invocation point once a routed netlist with the
# CDC modules exists.
###############################################################################

###############################################################################
# 14. I/O hold false-paths — suppress spurious port hold violations.
###############################################################################
set_false_path -hold -from [all_inputs]
set_false_path -hold -to [all_outputs]

# (Former section 15, the CDC exception coverage hard-fail gate, moved to
# phase5_soc_multiclock_check.sdc along with the cdc_require_match proc and
# the sections 11-13 exceptions it guards — this file no longer defines any
# CDC exceptions for it to guard.)
