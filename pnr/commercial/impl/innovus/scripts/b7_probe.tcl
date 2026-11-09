# b7_probe.tcl -- view-only probe of the Innovus b6 05m_eco label (nothing saved): SRAM dout0 term geometry, ecoAddRepeater help, the two antenna nets' sinks.
source [file join [file dirname [file normalize [info script]]] common.tcl]
restore_stage 05m_eco
common_settings
set insts [dbGet -p top.insts.cell.name $SRAM]
foreach i $insts { puts "SRAMI [dbGet $i.name] [dbGet $i.box] [dbGet $i.orient]" }
set i0 [lindex [dbGet -p top.insts.name {u_core/u_icache_gen_data_sram\[0\].u_data_sram}] 0]
puts "I0 [dbGet $i0.name]"
foreach b {0 1 15 31} {
  set it [dbGet -p $i0.instTerms.name "*dout0\\\[$b\\\]"]
  puts "TERM $b: [dbGet $it.name] pt=[dbGet $it.pt] net=[dbGet $it.net.name] nsink=[llength [dbGet $it.net.instTerms]]"
}
puts "HELP_ECOADD: [catch {help ecoAddRepeater} e]"
foreach nn {u_core/FE_OFN20491_n u_core/FE_OFN21807_n} {
  set n [dbGet -p top.nets.name $nn]
  foreach it [dbGet $n.instTerms] { puts "ANTNET $nn: [dbGet $it.name] pt=[dbGet $it.pt] cell=[dbGet $it.inst.cell.name]" }
}
puts "DIE [dbGet top.fPlan.box]"
exit
