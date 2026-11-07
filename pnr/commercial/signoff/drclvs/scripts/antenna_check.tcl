# OpenROAD antenna check on LEF+DEF, same command LibreLane's OpenROAD.CheckAntennas runs (check_antennas -verbose).
set pdk "$::env(PDK_ROOT)/$::env(PDK)/libs.ref"
read_lef $pdk/sky130_fd_sc_hd/techlef/sky130_fd_sc_hd__nom.tlef
read_lef $pdk/sky130_fd_sc_hd/lef/sky130_fd_sc_hd.lef
read_lef $pdk/sky130_fd_sc_hd/lef/sky130_ef_sc_hd.lef
read_lef $pdk/sky130_sram_macros/lef/sky130_sram_1kbyte_1rw1r_32x256_8.lef
read_def $::env(DEF)
puts "%OL_CREATE_REPORT $::env(OUT)"
check_antennas -verbose
puts "%OL_END_REPORT"
puts "ANT_VIOLATING_NETS [ant::antenna_violation_count]"
