###############################################################################
# phase5_soc_multiclock.sdc — 2-domain timing constraints for soc_top
#
# GH #94 / bead claude_verilog_test-oa7 (epic #90 -> #91..#96).
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
#   (b) three new sections (11-13) constraining the CPU<->fabric CDC boundary
#       that GH #91/#92/#93 built and this bead's whole reason for existing:
#       async_axi_fifo (u_cpu_axi_cdc), apb_cdc_bridge (u_apb_pll2_cdc), and
#       the PMU/IRQ single-bit crossings into cpu_core_clk.
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
#    to sit in different domains). This does NOT, by itself, constrain the
#    deliberate CDC synchroniser paths that legitimately cross the boundary —
#    those get explicit set_max_delay -datapath_only overrides in sections
#    11-13 below, which OpenSTA honours even though the clock groups are
#    otherwise asynchronous.
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
#    Unaffected by the CPU/fabric split: the APB3 debug slave sits on
#    apb_interconnect, entirely in the fabric (sys_clk) domain. APB_PLL2 (the
#    one APB slot that now reaches into the cpu_clk domain) is bridged
#    transparently by apb_cdc_bridge — see section 12 — and does not change
#    this top-level port's domain.
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
# CDC exception coverage guard (GH #94 hardening — CodeRabbit review, PR #132,
# this file line 389: "add a diagnostic when a CDC exception's hierarchical
# pattern fails to match"). Shared by every exception in sections 11-13.
#
# Every exception below is built from get_pins/get_nets -hierarchical
# -filter against a specific instance path (e.g.
# u_cpu_axi_cdc/u_aw_fifo/mem_q). If that path is ever renamed — RTL
# refactor, or synthesis hierarchy flattening — the pattern silently matches
# an EMPTY collection, and a bare [llength $x > 0] guard just skips the
# exception with no trace. Timing then reports clean because OpenSTA was
# never told the path exists, not because the path is safe. That is exactly
# the failure class this CDC epic has already hit three times independently
# (stale soc_top_ports.v stub, stale generated soc_top_sv2v.v, an incomplete
# sv2v source list) — each would have quietly discarded real design content
# rather than erroring. A clean STA report is not proof this file did its
# job; an empty ::cdc_exception_misses list, checked in section 15, is.
#
# cdc_require_match reports EVERY miss immediately via a grep-able
# "CDC-EXCEPTION-MISS:" puts — so a human scanning a long P&R log catches it
# without knowing in advance to look — and records the miss in
# ::cdc_exception_misses. Section 15 (end of file) promotes any recorded
# miss to a hard Tcl `error`, aborting read_sdc, rather than leaving it as a
# warning-and-continue:
#   - this file is not yet wired into any config.json SDC pointer (see the
#     file header STATUS note), so failing loudly here breaks nothing that
#     currently passes;
#   - a puts-only warning is exactly what a multi-hour P&R log swallows —
#     this project's three prior incidents above were each discovered late,
#     not at the point of failure;
#   - an unconstrained CDC boundary that STA reports as "clean" is a strictly
#     worse outcome than an aborted read_sdc that names the missing
#     instance/pin/net.
###############################################################################
set ::cdc_exception_misses {}

proc cdc_require_match {collection description} {
    if {[llength $collection] > 0} {
        return 1
    }
    puts "ERROR: CDC-EXCEPTION-MISS: ${description} -- pattern matched an EMPTY collection. This CDC timing exception was NOT applied; the boundary is UNCONSTRAINED."
    lappend ::cdc_exception_misses $description
    return 0
}

###############################################################################
# 11. CPU<->fabric CDC boundary — async_axi_fifo (instance u_cpu_axi_cdc)
#
# GH #94 / bead oa7, item 1 of 2 (async_axi_fifo). Per cdc_gray_fifo.sv's
# header, three classes of path genuinely cross the clock boundary inside
# EACH of the 5 channel FIFOs (AW/W/B/AR/R):
#   (1) the mem_q write-clk -> read-domain COMBINATIONAL read (storage array,
#       no capture register of its own within the FIFO — see the header's
#       "mem_q is a genuine ASYNCHRONOUS DATA PATH" warning);
#   (2) the u_wr_ptr_to_rd registered gray-pointer crossing (cdc_2ff_sync);
#   (3) the u_rd_ptr_to_wr registered gray-pointer crossing (cdc_2ff_sync).
# Because section 3 declares sys_clk/cpu_clk asynchronous, OpenSTA does not
# analyze setup/hold across them by default; these set_max_delay
# -datapath_only overrides are additive exceptions that still apply (OpenSTA
# honours explicit exceptions even between clock groups otherwise marked
# asynchronous) and give the router an actual budget instead of leaving the
# path completely unconstrained. -datapath_only means only the maximum delay
# is checked (no clock uncertainty/skew term, which is meaningless between
# two free-running clocks). Each is bounded to ONE PERIOD OF THE PATH'S
# DESTINATION DOMAIN: generous relative to the real settling requirement
# (empty_q/full_q already gate visibility one cycle behind the raw compare —
# see cdc_gray_fifo.sv), but tight enough that P&R still optimises it.
#
#   AW/W/AR fifos: wr_clk_i = s_clk_i = cpu_clk (780 ps)
#                  rd_clk_i = m_clk_i = sys_clk (1750 ps)
#   B/R    fifos: wr_clk_i = m_clk_i = sys_clk (1750 ps)
#                  rd_clk_i = s_clk_i = cpu_clk (780 ps)
# (see async_axi_fifo.sv's per-channel instantiations for the wr/rd wiring;
# s_clk_i is the CPU domain and m_clk_i is the fabric domain throughout that
# module, despite the confusable "s"/"m" naming — see its header.)
###############################################################################
set _cdc_fifo_dirs {
    u_aw_fifo 780  1750
    u_w_fifo  780  1750
    u_ar_fifo 780  1750
    u_b_fifo  1750 780
    u_r_fifo  1750 780
}

foreach {_fifo_inst _fifo_wr_period _fifo_rd_period} $_cdc_fifo_dirs {
    # (1) mem_q combinational read — bounded to the READ (destination) domain
    set _memq [get_nets -hierarchical -filter "name =~ *u_cpu_axi_cdc/${_fifo_inst}/mem_q*" -quiet]
    if {[cdc_require_match $_memq "sec.11 u_cpu_axi_cdc/${_fifo_inst}/mem_q combinational read"]} {
        set_max_delay $_fifo_rd_period -datapath_only -through $_memq
    }

    # (2) u_wr_ptr_to_rd: wr_gray_q -> rd domain — bounded to rd (destination)
    set _wr2rd [get_pins -hierarchical -filter "full_name =~ *u_cpu_axi_cdc/${_fifo_inst}/u_wr_ptr_to_rd/q_o*" -quiet]
    if {[cdc_require_match $_wr2rd "sec.11 u_cpu_axi_cdc/${_fifo_inst}/u_wr_ptr_to_rd/q_o gray-pointer crossing"]} {
        set_max_delay $_fifo_rd_period -datapath_only -through $_wr2rd
    }

    # (3) u_rd_ptr_to_wr: rd_gray_q -> wr domain — bounded to wr (destination)
    set _rd2wr [get_pins -hierarchical -filter "full_name =~ *u_cpu_axi_cdc/${_fifo_inst}/u_rd_ptr_to_wr/q_o*" -quiet]
    if {[cdc_require_match $_rd2wr "sec.11 u_cpu_axi_cdc/${_fifo_inst}/u_rd_ptr_to_wr/q_o gray-pointer crossing"]} {
        set_max_delay $_fifo_wr_period -datapath_only -through $_rd2wr
    }
}

###############################################################################
# 12. APB_PLL2 CDC bridge — apb_cdc_bridge (instance u_apb_pll2_cdc)
#
# GH #94 / bead oa7, item 2 of 2 (apb_cdc_bridge) — bead oa7 exists
# specifically because this second module, sitting on a single low-traffic
# APB slot rather than the main AXI datapath, is easy to forget. Per
# apb_cdc_bridge.sv's header, six paths cross the boundary:
#   - req_toggle_q  (s -> m, single bit, through u_req_sync)
#   - ack_toggle_q  (m -> s, single bit, through u_ack_sync)
#   - cmd_pwrite_q / cmd_paddr_q / cmd_pwdata_q / cmd_pstrb_q
#     (s -> m, 4 combinational payload reads, captured by the m-domain FSM)
#   - resp_prdata_dq / resp_pslverr_dq
#     (m -> s, 2 combinational payload reads, captured by the s-domain FSM)
# s_clk_i = core_clk (sys_clk, 1750 ps); m_clk_i = cpu_clk_i (cpu_clk,
# 780 ps) — see soc_top.sv's u_apb_pll2_cdc instantiation (m_clk_i is tied to
# the CPU-domain PLL's raw reference cpu_clk_i, not cpu_core_clk — matches
# u_cpu_pll_sub's own bootstrap rule that its APB regs run on the raw
# reference). Same -datapath_only / one-destination-period rationale as
# section 11: each bus/bit is bounded to the period of the domain that
# CAPTURES it, not the domain it originates in.
###############################################################################
set _req_sync [get_pins -hierarchical -filter "full_name =~ *u_apb_pll2_cdc/u_req_sync/q_o*" -quiet]
if {[cdc_require_match $_req_sync "sec.12 u_apb_pll2_cdc/u_req_sync/q_o toggle-bit crossing (s->m)"]} {
    set_max_delay 780 -datapath_only -through $_req_sync
}

set _ack_sync [get_pins -hierarchical -filter "full_name =~ *u_apb_pll2_cdc/u_ack_sync/q_o*" -quiet]
if {[cdc_require_match $_ack_sync "sec.12 u_apb_pll2_cdc/u_ack_sync/q_o toggle-bit crossing (m->s)"]} {
    set_max_delay 1750 -datapath_only -through $_ack_sync
}

# cmd_* payload (s=sys_clk -> m=cpu_clk domain capture): bound to cpu_clk
# NOTE: each of the 4 signals is checked individually via cdc_require_match
# (not just the aggregate _cmd_nets list) so that if, say, cmd_pstrb_q's
# path is renamed but the other 3 still match, that ONE miss still gets
# reported and gates section 15 — an aggregate-only check would have let a
# partial match through silently as if it were complete.
set _cmd_nets {}
foreach _sig {cmd_pwrite_q cmd_paddr_q cmd_pwdata_q cmd_pstrb_q} {
    set _n [get_nets -hierarchical -filter "name =~ *u_apb_pll2_cdc/${_sig}*" -quiet]
    if {[cdc_require_match $_n "sec.12 u_apb_pll2_cdc/${_sig} payload read (s->m capture)"]} {
        lappend _cmd_nets {*}$_n
    }
}
if {[llength $_cmd_nets] > 0} {
    set_max_delay 780 -datapath_only -through $_cmd_nets
}

# resp_* payload (m=cpu_clk -> s=sys_clk domain capture): bound to sys_clk
# Same per-signal rationale as cmd_* above.
set _resp_nets {}
foreach _sig {resp_prdata_dq resp_pslverr_dq} {
    set _n [get_nets -hierarchical -filter "name =~ *u_apb_pll2_cdc/${_sig}*" -quiet]
    if {[cdc_require_match $_n "sec.12 u_apb_pll2_cdc/${_sig} payload read (m->s capture)"]} {
        lappend _resp_nets {*}$_n
    }
}
if {[llength $_resp_nets] > 0} {
    set_max_delay 1750 -datapath_only -through $_resp_nets
}

###############################################################################
# 13. PMU/IRQ single-bit crossings into the cpu_core_clk domain
#
# soc_top.sv sources pmu_cpu_clk_en / pmu_cpu_iso_en / pmu_cpu_rst_n and
# ext_irq / timer_irq in the core_clk (sys_clk) domain and synchronises each
# into cpu_core_clk (== cpu_clk_i in STUB PLL mode, so shares cpu_clk's
# create_clock) via a dedicated instance:
#   u_cpu_clk_dis_sync  (cdc_2ff_sync, d_i = ~pmu_cpu_clk_en)
#   u_cpu_iso_en_sync   (cdc_2ff_sync, d_i = pmu_cpu_iso_en)
#   u_cpu_pmu_rst_sync  (cdc_reset_sync, rst_n_i = pmu_cpu_rst_n)
#   u_ext_irq_sync      (cdc_2ff_sync, d_i = ext_irq)
#   u_timer_irq_sync    (cdc_2ff_sync, d_i = timer_irq)
#
# u_cpu_pmu_rst_sync is DELIBERATELY excluded from the max_delay treatment
# below and given a false_path instead: cdc_reset_sync's rst_n_i is consumed
# only as an ASYNCHRONOUS CLEAR (negedge-sensitive, see cdc_reset_sync.sv) —
# by construction it has no setup/hold relationship to any clock, so a
# max_delay exception (which implies a setup-style data-arrival check) would
# be the wrong exception type. This mirrors section 4's treatment of the
# primary chip resets, not sections 11-12's data-path treatment.
#
# The other four are genuine single-bit DATA crossings through cdc_2ff_sync
# and get the same one-destination-period set_max_delay -datapath_only
# treatment as sections 11-12 (destination = cpu_core_clk = cpu_clk, 780 ps).
###############################################################################
set _rst_sync_pins [get_pins -hierarchical -filter "full_name =~ *u_cpu_pmu_rst_sync*" -quiet]
if {[cdc_require_match $_rst_sync_pins "sec.13 u_cpu_pmu_rst_sync async-clear reset sync (false_path)"]} {
    set_false_path -through $_rst_sync_pins
}

foreach _sync_inst {u_cpu_clk_dis_sync u_cpu_iso_en_sync u_ext_irq_sync u_timer_irq_sync} {
    set _p [get_pins -hierarchical -filter "full_name =~ *${_sync_inst}/q_o*" -quiet]
    if {[cdc_require_match $_p "sec.13 ${_sync_inst}/q_o single-bit CDC crossing"]} {
        set_max_delay 780 -datapath_only -through $_p
    }
}

###############################################################################
# 14. I/O hold false-paths — suppress spurious port hold violations.
###############################################################################
set_false_path -hold -from [all_inputs]
set_false_path -hold -to [all_outputs]

###############################################################################
# 15. CDC exception coverage gate — hard-fail on any section 11-13 miss.
#
# See the cdc_require_match proc / ::cdc_exception_misses list defined just
# before section 11. If ANY exception's get_pins/get_nets pattern matched an
# empty collection above, a CDC-EXCEPTION-MISS line was already puts'd at
# the point of failure, naming exactly which instance/pin/net path went
# missing. This final check promotes that from "logged" to "fatal": abort
# read_sdc with a nonzero-equivalent Tcl `error` rather than let the file
# finish reading as if nothing were wrong.
#
# This is a deliberate promotion from warning to hard error, not a stylistic
# default:
#   - this file is presently unwired into any config.json SDC pointer (see
#     the file header STATUS note) — failing loudly here breaks nothing that
#     currently passes today;
#   - this exact failure class (a pattern that silently matches nothing) has
#     already cost this CDC epic three separate incidents that were each
#     found late, not at the point of failure, precisely because nothing
#     errored; a puts-only warning would reproduce that same failure mode
#     for the fourth time;
#   - "STA reports clean" and "the CDC boundary is actually constrained" are
#     two different claims. Once any exception here goes missing, this file
#     can no longer tell those two claims apart — the only honest response
#     left is to refuse to be trusted, not to continue quietly.
###############################################################################
if {[llength $::cdc_exception_misses] > 0} {
    puts "ERROR: CDC-EXCEPTION-MISS: [llength $::cdc_exception_misses] of sections 11-13's CDC timing exceptions failed to match any object:"
    foreach _miss $::cdc_exception_misses {
        puts "ERROR: CDC-EXCEPTION-MISS:   - ${_miss}"
    }
    error "phase5_soc_multiclock.sdc: [llength $::cdc_exception_misses] CDC timing exception(s) in sections 11-13 matched an EMPTY collection -- see CDC-EXCEPTION-MISS lines above. Fix the referenced instance/pin/net path (RTL rename or hierarchy flattening) before trusting this SDC's STA results."
}
