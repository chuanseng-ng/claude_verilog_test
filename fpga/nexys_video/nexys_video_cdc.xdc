## nexys_video_cdc.xdc -- XDC translation of the CDC intent of pnr/constraints/phase5_soc_multiclock.sdc and
## phase5_soc_multiclock_check.sdc (bead hlrm.2). Applied AFTER synth_design (it binds to synthesized cell names) and after
## nexys_video.xdc (it needs the derived clocks). Same translation as tools/fpga/vivado_fmax_constraints.tcl, adapted to the
## real board top: the clocks are MMCM outputs, not harness pins.
##
## TRANSLATED
##   * clk_sys (50 MHz) <-> clk_cpu (75 MHz): `set_clock_groups -asynchronous` in the SDC, but the check SDC then bounds every
##     crossing with set_max_delay 0.9 x destination period. A clock group would override those budgets and cut the paths,
##     so: set_max_delay -datapath_only 0.9 x destination period, both directions.
##   * Gray-pointer crossings of the five async_axi_fifo channel FIFOs: 0.5 x destination period, datapath only, on the
##     first synchroniser stage D pins.
##   * apb_cdc_bridge req/ack and the PMU cpu_clk_dis synchroniser: 1 x destination period, datapath only.
##   * Reset synchronisers (cdc_reset_sync, and the two in nexys_video_top): async set/clear pins are a reset path.
##   * ASYNC_REG on every synchroniser flop (`*sync_q_reg*`), set here so the ASIC RTL stays untouched.
## HONEST CAVEAT: the two clocks are outputs of ONE MMCM, so Vivado sees them as related (synchronous) clocks. The
## -datapath_only budgets therefore REPLACE the default related-clock setup check on these crossings, but the HOLD check
## between related clocks still runs; it is covered by the WHS figure in the build report. An independent-clock soak needs
## a second oscillator (docs/FPGA_BOARD_SELECTION.md section 4).
## NOT TRANSLATED: DFT/scan constraints (tied off at the board top), the ASIC hard-macro boundary multicycles, clock
## uncertainty/latency model (Vivado derives it from the routed clock nets).

set nv_sys [get_clocks -of_objects [get_pins u_mmcm/CLKOUT0]]
set nv_cpu [get_clocks -of_objects [get_pins u_mmcm/CLKOUT1]]
set nv_p_sys 20.000
set nv_p_cpu 13.333

## ASYNC_REG on all synchroniser flops (cdc_sync, cdc_reset_sync, peripheral input synchronisers, board reset chains)
set nv_sync [get_cells -hierarchical -quiet -filter {NAME =~ *sync_q_reg* && IS_SEQUENTIAL}]
if {[llength $nv_sync] > 0} { set_property ASYNC_REG TRUE $nv_sync }
set nv_rstq [get_cells -hierarchical -quiet -filter {(NAME =~ sys_rst_q_reg* || NAME =~ cpu_rst_q_reg*) && IS_SEQUENTIAL}]
if {[llength $nv_rstq] > 0} { set_property ASYNC_REG TRUE $nv_rstq }

## domain-wide crossing bounds (0.9 x destination period)
set_max_delay -datapath_only [expr {0.9 * $nv_p_sys}] -from $nv_cpu -to $nv_sys
set_max_delay -datapath_only [expr {0.9 * $nv_p_cpu}] -from $nv_sys -to $nv_cpu

## reset synchronisers: async clear/preset pins
set nv_rs [get_cells -hierarchical -quiet -filter {(NAME =~ *rst_sync* || NAME =~ sys_rst_q_reg* || NAME =~ cpu_rst_q_reg*) && IS_SEQUENTIAL}]
set nv_rpins {}
foreach p {CLR PRE} {
    foreach x [get_pins -quiet -of_objects $nv_rs -filter "REF_PIN_NAME == $p"] { lappend nv_rpins $x }
}
if {[llength $nv_rpins] > 0} { set_false_path -to $nv_rpins }

## gray-pointer budgets, 0.5 x destination period. aw/w/ar are written in the CPU domain and read in the system domain;
## b/r the other way round. The write pointer crosses INTO the read domain, the read pointer into the write domain.
foreach {nv_fifo nv_wrdom} {u_aw_fifo cpu u_w_fifo cpu u_ar_fifo cpu u_b_fifo sys u_r_fifo sys} {
    if {$nv_wrdom eq "cpu"} { set nv_wrclk $nv_cpu; set nv_rdclk $nv_sys; set nv_wp $nv_p_cpu; set nv_rp $nv_p_sys
    } else {                  set nv_wrclk $nv_sys; set nv_rdclk $nv_cpu; set nv_wp $nv_p_sys; set nv_rp $nv_p_cpu }
    foreach {nv_pat nv_from nv_dst_p} [list \
            "*u_cpu_axi_cdc*${nv_fifo}*u_wr_ptr_to_rd*" $nv_wrclk $nv_rp \
            "*u_cpu_axi_cdc*${nv_fifo}*u_rd_ptr_to_wr*" $nv_rdclk $nv_wp] {
        set nv_cells [get_cells -hierarchical -quiet -filter "NAME =~ $nv_pat && IS_SEQUENTIAL"]
        set nv_pins  [get_pins -quiet -of_objects $nv_cells -filter {REF_PIN_NAME == D}]
        if {[llength $nv_pins] > 0} { set_max_delay -datapath_only [expr {0.5 * $nv_dst_p}] -from $nv_from -to $nv_pins }
    }
}

## single-bit req/ack and enable synchronisers, 1 x destination period
foreach {nv_pat nv_from nv_dst_p} [list \
        "*u_apb_pll2_cdc*req_q*"   $nv_sys $nv_p_cpu \
        "*u_apb_pll2_cdc*ack_q*"   $nv_cpu $nv_p_sys \
        "*u_apb_dbg_cdc*req_q*"    $nv_sys $nv_p_cpu \
        "*u_apb_dbg_cdc*ack_q*"    $nv_cpu $nv_p_sys \
        "*u_cpu_clk_dis_sync*"     $nv_sys $nv_p_cpu] {
    set nv_cells [get_cells -hierarchical -quiet -filter "NAME =~ $nv_pat && IS_SEQUENTIAL"]
    set nv_pins  [get_pins -quiet -of_objects $nv_cells -filter {REF_PIN_NAME == D}]
    if {[llength $nv_pins] > 0} { set_max_delay -datapath_only $nv_dst_p -from $nv_from -to $nv_pins }
}
