# nexys_video_cdc_waivers.tcl -- documented Vivado CDC waivers for the Nexys Video prototype (bead hlrm.3).
#
# Sourced by build.tcl on the ROUTED design, immediately before report_cdc (waivers are matched against the final netlist
# names, which is why they are a Tcl proc and not part of the post-synthesis XDC). Every waiver carries its reason; the
# full per-ID disposition (including the RTL-owned findings that are NOT waived here) is fpga/nexys_video/CDC_TRIAGE.md.
#
#   W1 mem_q    CDC-1 / CDC-13  cdc_gray_fifo storage read, protected by the gray-pointer protocol
#   W2 ila      CDC-1 / CDC-4 / CDC-13  ILA probe capture of system-domain nets (debug observation only)
#   W3 rstand   CDC-10          AND of two registered resets in front of a cdc_reset_sync async clear
#   W4 irqlvl   CDC-10          level-held IRQ / lock status (AND/OR of flops) in front of a 2-FF synchroniser, accepted risk
#   (W5 pmu)    CDC-10          PMU state decode in front of the CPU-domain synchronisers: a REAL RTL finding, NOT waived by
#                               default. nv_cdc_waive_rtl_open applies it only when NV_CDC_WAIVE_RTL_OPEN=1 (demonstration of
#                               the "all other findings closed" state); the default build keeps the 3 endpoints Critical.

proc nv_cdc_pins {cells filter} {
    set p {}
    if {[llength $cells] > 0} { set p [get_pins -quiet -of_objects $cells -filter $filter] }
    return $p
}

proc nv_cdc_waivers {} {
    set user "hlrm.3"
    set n 0

    # W1: cdc_gray_fifo `assign rd_data_o = mem_q[rd_bin_q]`. The storage is written in the write domain and read
    # combinationally in the read domain. Safe by construction: an entry is written one write-clock BEFORE the registered gray
    # write pointer that publishes it crosses (2-FF cdc_sync, rd_valid = !empty_q), and the writer cannot reuse the entry until
    # the registered gray read pointer has crossed back (full_q). The read data is therefore stable for at least one read
    # period before it is consumed; the remaining requirement is its delay bound, which nexys_video_cdc.xdc applies as
    # set_max_delay -datapath_only 0.9 x destination period (mirrors section 10 of phase5_soc_multiclock_check.sdc).
    set mem [get_cells -hierarchical -quiet -filter {NAME =~ u_soc/u_cpu_axi_cdc/u_*_fifo/mem_q_reg*}]
    set mclk [nv_cdc_pins $mem {REF_PIN_NAME =~ *CLK}]
    if {[llength $mclk] > 0} {
        foreach id {CDC-1 CDC-13} {
            create_waiver -type CDC -id $id -user $user -from $mclk -to *PIN \
                -tags {hlrm.3 mem_q} \
                -description "cdc_gray_fifo mem_q read: entry stable before its gray write pointer crosses (2-FF sync) and not reused before the gray read pointer crosses back; delay bounded by set_max_delay -datapath_only 0.9 x dst period (CDC_TRIAGE.md W1)"
            incr n
        }
    } else { puts "NV-CDC WARN W1: no mem_q cells found (RTL renamed?)" }

    # W2: the single ILA runs on the CPU clock and probes system-domain nets (APB debug bus, UART, IRQ, lock flags). The probes
    # are observation-only (no functional sink), the sampled system nets change at <= 50 MHz and are held for many cycles by
    # the apb_cdc_bridge handshake, and a torn capture only affects a debug trace.
    set ila [get_cells -hierarchical -quiet -filter {NAME =~ u_dbg/u_ila/*}]
    set ilapins [get_pins -hierarchical -quiet -filter {NAME =~ u_dbg/u_ila/*}]
    if {[llength $ilapins] > 0} {
        foreach id {CDC-1 CDC-4 CDC-13} {
            create_waiver -type CDC -id $id -user $user -from *PIN -to $ilapins \
                -tags {hlrm.3 ila} \
                -description "ILA probe capture of system-domain nets: observation only, no functional sink (CDC_TRIAGE.md W2)"
            incr n
        }
        foreach id {CDC-1 CDC-13} {
            create_waiver -type CDC -id $id -user $user -from [get_ports uart_tx_in] -to $ilapins \
                -tags {hlrm.3 ila} \
                -description "raw asynchronous UART input probed by the ILA only; the UART RX path itself has its own 2-FF synchroniser (CDC_TRIAGE.md W2)"
            incr n
        }
    } else { puts "NV-CDC WARN W2: no ILA pins found" }

    # W3: cdc_reset_sync async-clear fed by rst_both_n = s_rst_n & m_rst_n (async_axi_fifo / apb_cdc_bridge cross-coupled reset,
    # RTL-intentional: a one-sided reset would inject fabricated AXI beats). Both operands are registered resets (sys_rst_q /
    # cpu_rst_q), asserted by the same board event; the only glitch the AND can make is a short spurious RELEASE of an
    # already-asserted clear, which the clear re-asserts. ASIC SDC treats these pins as reset paths (set_false_path).
    set rs {}
    foreach pat {u_soc/u_cpu_axi_cdc/u_s_rst_sync/* u_soc/u_cpu_axi_cdc/u_m_rst_sync/* u_soc/u_apb_dbg_cdc/u_m_rst_sync/*
                 u_soc/u_apb_pll2_cdc/u_m_rst_sync/*} {
        foreach c [get_cells -hierarchical -quiet -filter "NAME =~ $pat && IS_SEQUENTIAL"] { lappend rs $c }
    }
    set rpins [nv_cdc_pins $rs {REF_PIN_NAME == CLR || REF_PIN_NAME == PRE}]
    if {[llength $rpins] > 0} {
        create_waiver -type CDC -id CDC-10 -user $user -from *PIN -to $rpins -tags {hlrm.3 rstand} \
            -description "AND of two registered resets in front of a cdc_reset_sync async clear; reset path, only a spurious release glitch is possible and the clear re-asserts (CDC_TRIAGE.md W3)"
        incr n
    } else { puts "NV-CDC WARN W3: no reset-sync clear pins found" }

    # W4: level-held sources. ext_irq (interrupt_controller |masked), timer_irq (irq_en & irq_pending_q) and the PLL lock status
    # (reset AND lock) are AND/OR functions of flops that are stable for many cycles. A glitch needs two inputs to move in
    # opposite directions in the same cycle; the consequence is one spurious level interrupt / status bit that software
    # clears, never a corrupted state. ACCEPTED RISK; registering the OR/AND in the source domain is optional hardening.
    set lvl {}
    foreach pat {u_soc/u_ext_irq_sync/* u_soc/u_timer_irq_sync/* u_soc/u_apb_dbg_cdc/u_m_rst_status_sync/*} {
        foreach c [get_cells -hierarchical -quiet -filter "NAME =~ $pat && IS_SEQUENTIAL"] { lappend lvl $c }
    }
    set lpins [nv_cdc_pins $lvl {REF_PIN_NAME == D}]
    if {[llength $lpins] > 0} {
        create_waiver -type CDC -id CDC-10 -user $user -from *PIN -to $lpins -tags {hlrm.3 irqlvl} \
            -description "level-held IRQ / PLL-lock status: AND/OR of stable flops ahead of a 2-FF synchroniser; glitch needs opposite simultaneous transitions and costs one spurious level interrupt, accepted risk (CDC_TRIAGE.md W4)"
        incr n
    } else { puts "NV-CDC WARN W4: no level-synchroniser D pins found" }

    puts "NV-CDC waivers created: $n"
    if {[info exists ::env(NV_CDC_WAIVE_RTL_OPEN)] && $::env(NV_CDC_WAIVE_RTL_OPEN) eq "1"} { nv_cdc_waive_rtl_open }
}

# W5: REAL RTL finding (pmu.sv clk_en_w / iso_en_w / rst_n_w are combinational decodes of the 4-bit binary dom_state_q and go
# straight to cdc_sync / cdc_reset_sync in soc_top.sv). Not applied by default; see CDC_TRIAGE.md section "RTL findings".
proc nv_cdc_waive_rtl_open {} {
    set pm [get_cells -hierarchical -quiet -filter {NAME =~ u_soc/u_cpu_clk_dis_sync/* || NAME =~ u_soc/u_cpu_iso_en_sync/* || NAME =~ u_soc/u_cpu_pmu_rst_sync/*}]
    set pp [get_pins -quiet -of_objects [filter $pm IS_SEQUENTIAL] -filter {REF_PIN_NAME == D || REF_PIN_NAME == CLR || REF_PIN_NAME == PRE}]
    if {[llength $pp] > 0} {
        create_waiver -type CDC -id CDC-10 -user hlrm.3 -from *PIN -to $pp -tags {hlrm.3 pmu RTL_OPEN} \
            -description "TEMPORARY (RTL finding, NOT a closure): PMU state decode feeds CPU-domain synchronisers; owner = RTL (CDC_TRIAGE.md)"
        puts "NV-CDC RTL-OPEN waiver applied (NV_CDC_WAIVE_RTL_OPEN=1)"
    }
}
