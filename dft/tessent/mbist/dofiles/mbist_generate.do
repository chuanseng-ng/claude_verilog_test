// Stage 1: read, DRC, report memories, create (but do not process) the DFT specification.
source [file join [file dirname [info script]] common_setup.tcl]
check_design_rules
report_memory_instances
set spec [create_dft_specification]
report_config_data $spec
exit
