# pt_export.tcl -- PrimePower per-instance power (nom_tt, vectorless variant B) + RedHawk STA file, for ONE arm.
# Same settings as signoff/pt/scripts/judge.tcl (shared base SDC, md5-asserted; propagated clk_i; SI off; StarRC nom SPEF; tt lib + TT SRAM db;
# power: toggle 0.1 / static prob 0.5 on PIs AND on every register output pin = judge variant B, the headline in pt_judge_summary.md).
# env: J_ROOT J_NETLIST J_SPEF J_SDC J_SDC_MD5 J_OUT
set ROOT $::env(J_ROOT)
set DB   $ROOT/pnr/commercial/pdk/sky130/build/db
set fh [open metrics.tsv w]
proc m {k v} { global fh; puts $fh "$k\t$v"; flush $fh }
m pt_version [get_app_var sh_product_version]
set_host_options -max_cores 2
set_app_var report_default_significant_digits 6
set_app_var si_enable_analysis false
set_app_var power_enable_analysis true
set_app_var power_analysis_mode averaged
set_app_var search_path [list $DB]
set_app_var link_path [list * sky130_fd_sc_hd__tt_025C_1v80.db sky130_sram_1kbyte_1rw1r_32x256_8_TT_1p8V_25C.db]
read_verilog $::env(J_NETLIST)
current_design rv32i_cpu_top
link_design
set md5 [lindex [exec md5sum $::env(J_SDC)] 0]
m sdc_md5 $md5
if {$md5 ne $::env(J_SDC_MD5)} { puts "FATAL: SDC md5"; exit 3 }
read_sdc $::env(J_SDC)
set_propagated_clock [get_clocks clk_i]
read_parasitics -format spef $::env(J_SPEF)
update_timing
set_app_var power_default_toggle_rate 0.1
set_app_var power_default_static_probability 0.5
set rq [all_registers -output_pins]
m power_B_register_output_pins [sizeof_collection $rq]
set_switching_activity -toggle_rate 0.1 -static_probability 0.5 -base_clock clk_i $rq
update_power
redirect -file power_B.txt { report_power -nosplit }
redirect -file power_B_cellclass.txt { report_power -nosplit -groups {clock_network register combinational sequential memory io_pad black_box} }
# ---- per-leaf-cell power (W): total = internal + switching + leakage, as attributed by PrimePower
set cells [get_cells -hier -quiet -filter "is_hierarchical==false"]
m leaf_cells [sizeof_collection $cells]
set o [open instance_power.txt w]
set tot 0.0; set tint 0.0; set tsw 0.0; set tlk 0.0; set n 0; set nz 0
foreach_in_collection c $cells {
  set nm [get_object_name $c]
  set i [get_attribute $c internal_power]; set s [get_attribute $c switching_power]; set l [get_attribute $c leakage_power]
  if {$i eq ""} {set i 0}; if {$s eq ""} {set s 0}; if {$l eq ""} {set l 0}
  set p [expr {$i + $s + $l}]
  puts $o "$nm $p [get_attribute $c ref_name] $i $s $l"
  set tot [expr {$tot + $p}]; set tint [expr {$tint + $i}]; set tsw [expr {$tsw + $s}]; set tlk [expr {$tlk + $l}]
  incr n; if {$p == 0} { incr nz }
}
close $o
m ipf_cells $n; m ipf_zero_cells $nz
m ipf_total_W $tot; m ipf_internal_W $tint; m ipf_switching_W $tsw; m ipf_leakage_W $tlk
# ---- STA windows for RedHawk vectorless dynamic (native PrimeTime writer)
set timing_save_pin_arrival_and_slack true
update_timing
catch { write_rh_file -filetype irdrop -output rv32i_cpu_top.timing } err
m write_rh_file_msg $err
close $fh
exit
