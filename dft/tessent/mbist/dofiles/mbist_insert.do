// Stage 2: generate and insert the Tessent MemoryBIST hardware, extract ICL, create + run the testbench.
source $::env(MBIST_HERE)/dofiles/common_setup.tcl
check_design_rules
report_memory_instances

set spec [create_dft_specification]
// One controller, one step: both 4 KB macros are tested in parallel (the in-house controller also tests
// memory 0 and 1 in the same sweep).  Algorithms selectable at run time through IJTAG:
//   default (from the TCD): SMarchCHKBcil;  extras: March C- (LVMARCHCMINUS), SMARCH, SMARCHCHKB, checkerboard.
set_config_value $spec/MemoryBist/Controller(c1)/AdvancedOptions/extra_algorithms \
    {LVMARCHCMINUS SMARCH SMARCHCHKB SMARCHCHKBCI LVCHECKERBOARD1X1}
// Per-memory go/no-go and failing-address diagnosis through IJTAG
set_config_value $spec/MemoryBist/Controller(c1)/DiagnosisOptions/go_status per_memory
// Direct-access ports are NOT requested (access is IJTAG only)
report_config_data $spec

process_dft_specification
extract_icl
create_patterns_specification
process_patterns_specification
exit
