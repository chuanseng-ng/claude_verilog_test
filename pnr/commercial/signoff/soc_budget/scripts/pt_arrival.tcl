# pt_arrival.tcl -- step 4b: launch-edge -> CPU-macro-input-pin arrival of the SoC-side drivers, per library corner.
#   pt_shell -f pt_arrival.tcl   env: REPO RUN LIB (tt|ss|ff)
# Netlists: DC-mapped async_axi_fifo (SoC instance u_cpu_axi_cdc) and apb_cdc_bridge (u_apb_dbg_cdc), from pnr/sky130/soc/soc_top_sv2v.v.
# Time zero = the launching flop's own clock edge (ideal clock, zero latency, zero wire): ARRIVAL = clk->Q + driver logic, i.e. what the
# judge SDC's set_input_delay models.  Output load = the macro's own Liberty pin capacitance (pnr/sky130/cpu/macro, nom RC, same lib corner).
# Parasitics: NONE (no SoC SPEF exists on this host), so the figure is a lower bound of the SoC arrival; the margin rule is in the doc.
set REPO $::env(REPO); set RUN $::env(RUN); set L $::env(LIB)
set B $REPO/pnr/commercial/pdk/sky130/build/db
array set LN {tt sky130_fd_sc_hd__tt_025C_1v80 ss sky130_fd_sc_hd__ss_100C_1v60 ff sky130_fd_sc_hd__ff_n40C_1v95}
array set MC {tt nom_tt_025C_1v80 ss nom_ss_100C_1v60 ff nom_ff_n40C_1v95}
set search_path [list $B]
set link_path [list * $LN($L).db]
# register->output-port paths have no set_output_delay, so they are unconstrained; without this get_timing_paths returns nothing (all NA, 2026-11-14)
set timing_report_unconstrained_paths true
# macro pin caps (pF) from the SoC's macro Liberty, this corner
# macro pin caps (pF), extracted from that Liberty by mk_pincap.py (runs/pincap_<lib>.tsv: pin <TAB> capacitance)
set capof [dict create]
set fh [open $RUN/../pincap_$L.tsv r]
foreach line [split [read $fh] "\n"] { if {$line ne ""} { lassign [split $line "\t"] n c; dict set capof $n $c } }
close $fh
# fifo/bridge output port -> macro input pin
set map_fifo {s_awready_o axi_awready_i s_wready_o axi_wready_i s_arready_o axi_arready_i s_bresp_o axi_bresp_i s_bvalid_o axi_bvalid_i
              s_rdata_o axi_rdata_i s_rresp_o axi_rresp_i s_rlast_o axi_rlast_i s_rvalid_o axi_rvalid_i}
set map_apb  {m_paddr_o apb_paddr_i m_psel_o apb_psel_i m_penable_o apb_penable_i m_pwrite_o apb_pwrite_i m_pwdata_o apb_pwdata_i}
set out [open $RUN/arrival_$L.tsv w]
puts $out "# lib\tgroup\tport\tbit_cap_pf\tmax_arrival_ns\tmin_arrival_ns\tstartpoint"
foreach {mod map} [list async_axi_fifo $map_fifo apb_cdc_bridge $map_apb] {
  catch {remove_design -all}
  read_verilog $RUN/out/${mod}.mapped.v
  current_design $mod; link
  create_clock -name s_clk -period 25 [get_ports s_clk_i]
  create_clock -name m_clk -period 25 [get_ports m_clk_i]
  set_clock_groups -asynchronous -group s_clk -group m_clk
  foreach {po mi} $map {
    foreach_in_collection p [get_ports -quiet "${po}*"] {
      set pn [get_object_name $p]
      regsub {^[a-z0-9_]+_o} $pn $mi mn
      if {![dict exists $capof $mn]} { puts "NO CAP for $mn"; continue }
      set_load [dict get $capof $mn] $p
    }
  }
  foreach {po mi} $map {
    foreach_in_collection p [get_ports -quiet "${po}*"] {
      set pn [get_object_name $p]; regsub {^[a-z0-9_]+_o} $pn $mi mn
      set ps [get_timing_paths -from [all_registers -clock_pins] -to $p -delay_type max]
      set pm [get_timing_paths -from [all_registers -clock_pins] -to $p -delay_type min]
      if {[sizeof_collection $ps] == 0} { puts $out "$L\t$mi\t$pn\t[dict get $capof $mn]\tNA\tNA\tnone"; continue }
      set a [get_attribute $ps arrival]; set sp [get_object_name [get_attribute $ps startpoint]]
      set am [expr {[sizeof_collection $pm] ? [get_attribute $pm arrival] : "NA"}]
      puts $out "$L\t$mi\t$pn\t[dict get $capof $mn]\t$a\t$am\t$sp"
    }
  }
}
close $out
puts "PT_ARRIVAL_DONE $L"
exit
