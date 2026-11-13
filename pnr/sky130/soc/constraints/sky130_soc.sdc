# sky130_soc.sdc - Functional-mode timing constraints for the Sky130 SoC (soc_top with the CPU hard macro)
#
# Scope: LibreLane flow in pnr/sky130/soc. config.json and config_rccal.json set PNR_SDC_FILE, SIGNOFF_SDC_FILE and
#   FALLBACK_SDC_FILE to this file. sta_load_sky130_soc.tcl, tools/dft/make_scan_analysis_sdc.py and
#   tb/tests/test_cvt_scan_step.py also read it.
# Contents: clocks core_clk (clk_i), cpu_clk (cpu_clk_i) and tck (tck_i, when it exists); I/O delays; false paths; DFT case analysis;
#   clock group async_domains; CDC hold exemption; 2-cycle path on the APB debug ports.
# Inputs: environment variable CVT_SDC_SCAN_VIEW (optional). The file sets clock_period and _jtag_period itself.
#   It guards optional ports with -quiet, so an older netlist still reads it.
# User rules:
#   Do not add set_max_delay across core_clk, cpu_clk and tck here. OpenSTA drops it inside an asynchronous group.
#   The CDC budgets are in sky130_soc_cdc_check.sdc, read by check_cdc_timing_sky130.tcl (make target check-cdc-timing-sky130-soc).
#   Set CVT_SDC_SCAN_VIEW to 1 to skip the CDC hold exemption in a scan-mode STA view.
#   In scan mode the flow does not repair hold on the exempted stage-0 synchroniser flops. That hold is not verified.
#   Mask those flops in the scan capture response.
#   This file is not a scan-mode SDC. A TAP flop also drives scan_mode, so STA can propagate tck and scan_clk_i
#   through the dft_clk_mux selects. This file cannot pin that flop, because its name does not survive flattening.
#   The tck period is a placeholder until a pad ring and an ATE exist.
#   Timing sign-off is typical-corner (nom_tt) only. Do not report it as a multi-corner sign-off.
#   The SRAM arcs are the same at all nine corners, because the 4 KB SRAM macro Liberty has one corner only.
#   Slow-corner (ss) setup is not signed off with this constraint set.
# Doc: tm:pd:sky130-soc-sdc, cr:pd:sky130-soc-sdc

set clock_period 25.0

###############################################################################
# Primary clock
###############################################################################
create_clock \
    -name core_clk \
    -period $clock_period \
    [get_ports clk_i]

set_clock_uncertainty -setup 0.300 [get_clocks core_clk]
set_clock_uncertainty -hold  0.150 [get_clocks core_clk]

create_clock \
    -name cpu_clk \
    -period $clock_period \
    [get_ports cpu_clk_i]

set_clock_uncertainty -setup 0.300 [get_clocks cpu_clk]
set_clock_uncertainty -hold  0.150 [get_clocks cpu_clk]

set _in_timed {}
# DFT Stage 1b (j41m.3): the JTAG inputs are timed against tck (section "JTAG TAP" below),
# not core_clk, and tck_i is a clock port (STA-0441), so they are not in this list.
set _jtag_in_names {tck_i tms_i tdi_i trst_ni}
foreach _p [all_inputs] {
    set _n [get_full_name $_p]
    if {$_n ne "clk_i" && $_n ne "cpu_clk_i" && [lsearch -exact $_jtag_in_names $_n] < 0} {
        lappend _in_timed $_p
    }
}

set_driving_cell \
    -lib_cell sky130_fd_sc_hd__buf_4 \
    -pin X \
    $_in_timed

set_driving_cell \
    -lib_cell sky130_fd_sc_hd__clkbuf_16 \
    -pin X \
    [get_ports {clk_i cpu_clk_i}]

set_load 0.1 [all_outputs]

###############################################################################
# Input / output delays (20% of period for setup, 5% for hold)
# Exclude clk_i from set_input_delay — STA-0441: input delay on clock port
# not allowed. Reuses $_in_timed computed above.
###############################################################################
if {[llength $_in_timed] > 0} {
    set_input_delay  [expr $clock_period * 0.20] -clock core_clk -max $_in_timed
    set_input_delay  [expr $clock_period * 0.05] -clock core_clk -min $_in_timed
}
set _out_timed {}
foreach _p [all_outputs] {
    if {[lsearch -exact {tdo_o tdo_oe_o} [get_full_name $_p]] < 0} {
        lappend _out_timed $_p
    }
}
set_output_delay [expr $clock_period * 0.20] -clock core_clk -max $_out_timed
set_output_delay [expr $clock_period * 0.05] -clock core_clk -min $_out_timed

###############################################################################
# Asynchronous / quasi-static ports — false path
###############################################################################
set_false_path -from [get_ports rst_n_i]

foreach {_dft_p _dft_v} {scan_mode_i 0 scan_en_i 0 scan_rst_ni 1} {
    if {[llength [get_ports -quiet $_dft_p]] > 0} {
        set_case_analysis $_dft_v [get_ports $_dft_p]
    }
}
set _dft_in {}
foreach _dft_p {scan_mode_i scan_en_i scan_rst_ni scan_clk_i scan_in_i} {
    foreach _dft_x [get_ports -quiet $_dft_p] { lappend _dft_in $_dft_x }
}
if {[llength $_dft_in] > 0} { set_false_path -from $_dft_in }
if {[llength [get_ports -quiet scan_out_o]] > 0} { set_false_path -to [get_ports scan_out_o] }

if {[llength [get_ports -quiet tck_i]] > 0} {
    set _jtag_period 100.0
    create_clock -name tck -period $_jtag_period [get_ports tck_i]
    set_clock_uncertainty -setup 0.300 [get_clocks tck]
    set_clock_uncertainty -hold  0.150 [get_clocks tck]

    set _jtag_data_in {}
    foreach _jtag_p {tms_i tdi_i} {
        foreach _jtag_x [get_ports -quiet $_jtag_p] { lappend _jtag_data_in $_jtag_x }
    }
    if {[llength $_jtag_data_in] > 0} {
        set_driving_cell -lib_cell sky130_fd_sc_hd__buf_4 -pin X $_jtag_data_in
        set_input_delay [expr $_jtag_period * 0.20] -clock tck -max $_jtag_data_in
        set_input_delay [expr $_jtag_period * 0.05] -clock tck -min $_jtag_data_in
    }
    # TDO / TDO_OE are launched on the falling edge of tck inside the TAP; the external
    # capture is the next rising edge, so half a period minus the board allowance remains.
    set _jtag_out {}
    foreach _jtag_p {tdo_o tdo_oe_o} {
        foreach _jtag_x [get_ports -quiet $_jtag_p] { lappend _jtag_out $_jtag_x }
    }
    if {[llength $_jtag_out] > 0} {
        set_output_delay [expr $_jtag_period * 0.20] -clock tck -max $_jtag_out
        set_output_delay [expr $_jtag_period * 0.05] -clock tck -min $_jtag_out
    }
    # trst_ni: asynchronous assert into a cdc_reset_sync, same class as rst_n_i.
    foreach _jtag_x [get_ports -quiet trst_ni] { set_false_path -from $_jtag_x }
}

set _async_groups {}
foreach _c {core_clk cpu_clk tck} {
    if {[llength [get_clocks -quiet $_c]] > 0} {
        lappend _async_groups -group [get_clocks $_c]
    }
}
if {[llength $_async_groups] > 2} {
    set_clock_groups -name async_domains -asynchronous {*}$_async_groups
}

set ::cvt_cdc_hold_exempt_pins {}
set ::cvt_cdc_hold_exempt_misses {}
set ::cvt_cdc_regs_cache [dict create]

proc cvt_cdc_plain_name {obj} {
    return [string map {"\\" ""} [get_full_name $obj]]
}

proc cvt_cdc_regs_on_clock {clk_name} {
    if {![dict exists $::cvt_cdc_regs_cache $clk_name]} {
        set _ns [dict create]
        foreach c [all_registers -clock [get_clocks $clk_name]] { dict set _ns [get_full_name $c] 1 }
        dict set ::cvt_cdc_regs_cache $clk_name $_ns
    }
    return [dict get $::cvt_cdc_regs_cache $clk_name]
}

proc cvt_cdc_filter_by_clock {cells clk_name} {
    set _ns [cvt_cdc_regs_on_clock $clk_name]
    set _r {}
    foreach c $cells { if {[dict exists $_ns [get_full_name $c]]} { lappend _r $c } }
    return $_r
}

# Returns the number of bits exempted; every unresolved bit is recorded as a miss.
proc cvt_cdc_hold_exempt {inst_token from_clk to_clk description} {
    set _nets {}
    foreach _n [get_nets -hierarchical -filter "name =~ *${inst_token}*sync_q*" -quiet] {
        set _nm [cvt_cdc_plain_name $_n]
        if {[string first "sync_q\[0\]" $_nm] >= 0} { lappend _nets $_n }
    }
    if {[llength $_nets] == 0} {
        lappend ::cvt_cdc_hold_exempt_misses "${description}: no stage-0 net matched"
        return 0
    }
    set _done 0
    foreach _n $_nets {
        set _drv [get_pins -of_objects $_n -filter {direction == output} -quiet]
        set _caps [cvt_cdc_filter_by_clock [get_cells -of_objects $_drv -quiet] $to_clk]
        set _dpins {}
        if {[llength $_caps] > 0} {
            set _dpins [get_pins -of_objects $_caps -filter {direction == input && name == D} -quiet]
        }
        if {[llength $_dpins] == 0} {
            lappend ::cvt_cdc_hold_exempt_misses "${description}: [get_full_name $_n] no ${to_clk} capture flop D pin"
            continue
        }
        set _launch [cvt_cdc_filter_by_clock [get_fanin -to $_dpins -startpoints_only -flat -only_cells] $from_clk]
        if {[llength $_launch] == 0} {
            lappend ::cvt_cdc_hold_exempt_misses "${description}: [get_full_name $_n] no ${from_clk} launch flop"
            continue
        }
        set_false_path -hold -from $_launch -to $_dpins
        foreach _p $_dpins { lappend ::cvt_cdc_hold_exempt_pins [get_full_name $_p] }
        incr _done
    }
    return $_done
}

if {[info exists ::env(CVT_SDC_SCAN_VIEW)] && $::env(CVT_SDC_SCAN_VIEW) eq "1"} {
    puts "INFO: CDC-HOLD-EXEMPT: CVT_SDC_SCAN_VIEW=1 -- gray-pointer hold exemption NOT applied (scan-mode view)."
} elseif {[llength [get_clocks -quiet cpu_clk]] > 0 && [llength [get_clocks -quiet core_clk]] > 0} {
    # fifo  write-domain clock  read-domain clock   (AW/W/AR: CPU writes; B/R: fabric writes)
    foreach {_fifo _wr_clk _rd_clk} {
        u_aw_fifo cpu_clk  core_clk
        u_w_fifo  cpu_clk  core_clk
        u_ar_fifo cpu_clk  core_clk
        u_b_fifo  core_clk cpu_clk
        u_r_fifo  core_clk cpu_clk
    } {
        cvt_cdc_hold_exempt "u_cpu_axi_cdc*${_fifo}*u_wr_ptr_to_rd" $_wr_clk $_rd_clk \
            "u_cpu_axi_cdc.${_fifo}.u_wr_ptr_to_rd (${_wr_clk} -> ${_rd_clk})"
        cvt_cdc_hold_exempt "u_cpu_axi_cdc*${_fifo}*u_rd_ptr_to_wr" $_rd_clk $_wr_clk \
            "u_cpu_axi_cdc.${_fifo}.u_rd_ptr_to_wr (${_rd_clk} -> ${_wr_clk})"
    }
    proc cvt_mbist_data_hold_exempt {xing_token dst_clk description} {
        set _dst [cvt_cdc_regs_on_clock $dst_clk]
        set _q {}
        foreach _n [get_nets -hierarchical -filter "name =~ *${xing_token}*mem_q*" -quiet] {
            if {![string match "*${xing_token}*u_fifo*" [cvt_cdc_plain_name $_n]]} { continue }
            foreach _p [get_pins -of_objects $_n -filter {direction == output} -quiet] {
                foreach _c [get_cells -of_objects $_p] {
                    if {![dict exists $_dst [get_full_name $_c]]} { lappend _q $_p }
                }
            }
        }
        if {[llength $_q] == 0} {
            lappend ::cvt_cdc_hold_exempt_misses "${description}: no mem_q launch flop"
            return 0
        }
        set _launch {}
        foreach _p $_q { foreach _c [get_cells -of_objects $_p] { lappend _launch $_c } }
        set _dpins {}
        foreach _e [get_fanout -from $_q -endpoints_only -flat] {
            if {[catch {get_property $_e lib_pin_name} _lp]} { continue }   ;# a port, not a pin
            if {$_lp ne "D"} { continue }
            if {[dict exists $_dst [get_full_name [get_cells -of_objects $_e]]]} { lappend _dpins $_e }
        }
        if {[llength $_dpins] == 0} {
            lappend ::cvt_cdc_hold_exempt_misses "${description}: no ${dst_clk} D pin in the mem_q fan-out"
            return 0
        }
        set_false_path -hold -from [lsort -unique $_launch] -to [lsort -unique $_dpins]
        foreach _p $_dpins { lappend ::cvt_cdc_hold_exempt_pins [get_full_name $_p] }
        return [llength [lsort -unique $_dpins]]
    }
    if {[llength [get_clocks -quiet tck]] > 0} {
        foreach {_dom _xing _dclk} {
            core u_xing_core core_clk
            cpu  u_xing_cpu  cpu_clk
        } {
            # the cpu half only exists with soc_top MBIST_CPU = 1
            if {[llength [get_nets -hierarchical -filter "name =~ *${_xing}*" -quiet]] == 0} {
                puts "INFO: CDC-HOLD-EXEMPT: no ${_xing} in this netlist (MBIST_CPU = 0 or pre-MBIST netlist); MBIST ${_dom} row skipped."
                continue
            }
            cvt_cdc_hold_exempt "${_xing}*u_fifo*u_wr_ptr_to_rd" tck $_dclk \
                "u_mbist.${_xing}.u_fifo.u_wr_ptr_to_rd (tck -> ${_dclk})"
            cvt_mbist_data_hold_exempt $_xing $_dclk "u_mbist.${_xing} mem_q -> holding register (tck -> ${_dclk})"
        }
    }
    if {[llength $::cvt_cdc_hold_exempt_misses] > 0} {
        foreach _m $::cvt_cdc_hold_exempt_misses { puts "ERROR: CDC-HOLD-EXEMPT-MISS: $_m" }
        error "sky130_soc.sdc: [llength $::cvt_cdc_hold_exempt_misses] CDC gray-pointer hold exemption(s) failed to bind (see CDC-HOLD-EXEMPT-MISS lines); the hold padding they exist to stop would return."
    }
    puts "INFO: CDC-HOLD-EXEMPT: [llength $::cvt_cdc_hold_exempt_pins] capture D pins exempt from hold (10 async_axi_fifo gray-pointer synchronisers + the MBIST tck -> dst pointer/payload rows)."
}

set_false_path -from [get_ports cpu_rst_n_i]

set_false_path -from [get_ports gpio_in_i]

set_false_path -from [get_ports i2c_scl_i]
set_false_path -from [get_ports i2c_sda_i]
set_false_path -to   [get_ports pwm_o]
set_false_path -to   [get_ports i2c_scl_o]
set_false_path -to   [get_ports i2c_scl_oe_o]
set_false_path -to   [get_ports i2c_sda_o]
set_false_path -to   [get_ports i2c_sda_oe_o]
set_false_path -to   [get_ports wdt_rst_req_o]

# UART I/O (asynchronous serial)
set_false_path -from [get_ports uart_rx_i]
set_false_path -to   [get_ports uart_tx_o]

# SPI I/O (asynchronous from SoC timing perspective at this abstraction)
set_false_path -from [get_ports spi_miso_i]
set_false_path -to   [get_ports spi_sclk_o]
set_false_path -to   [get_ports spi_mosi_o]
set_false_path -to   [get_ports spi_cs_n_o]

###############################################################################
# APB debug interface — 2-cycle multicycle (low-speed debug bus)
###############################################################################
set_multicycle_path 2 -setup -from [get_ports {apb_paddr_i apb_psel_i apb_penable_i apb_pwrite_i apb_pwdata_i}]
set_multicycle_path 1 -hold  -from [get_ports {apb_paddr_i apb_psel_i apb_penable_i apb_pwrite_i apb_pwdata_i}]
set_multicycle_path 2 -setup -to   [get_ports {apb_prdata_o apb_pready_o apb_pslverr_o}]
set_multicycle_path 1 -hold  -to   [get_ports {apb_prdata_o apb_pready_o apb_pslverr_o}]

###############################################################################
# Observability outputs — relaxed (sampled externally, not on-chip timing)
###############################################################################
set_false_path -to [get_ports {commit_valid_o commit_pc_o commit_insn_o gpu_irq_o pll_locked_o}]
# cpu_pll_locked_o is launched by a cpu_clk-domain flop (u_cpu_pll_sub). Once cpu_clk exists
# it would otherwise be a cpu_clk -> core_clk-referenced output path; same class as
# pll_locked_o (a level status flag, no timed receiver). Guarded: older port sets lack it.
foreach _p [get_ports -quiet cpu_pll_locked_o] { set_false_path -to $_p }

###############################################################################
# CPU macro hold false-path on I/O boundary
# The CPU macro timing model covers setup; hold on I/O ports is an external
# board-level concern and is excluded to avoid false hold violations on the
# macro's output boundary in this flat SoC flow.
###############################################################################
set_false_path -hold -from [get_ports clk_i] -to [all_outputs]
