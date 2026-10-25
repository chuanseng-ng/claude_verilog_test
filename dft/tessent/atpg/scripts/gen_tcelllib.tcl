# Build the Tessent cell library (.tcelllib) for sky130_fd_sc_hd: ATPG models from LibComp plus the scan-equivalent and
# clock-gating attributes that Tessent extracts from the Liberty.  The auto-created dft_cell_selection is replaced by a
# curated one in scripts/mk_tcelllib.py (the automatic choice picks lpflow_* low-power cells).
set_context dft -scan
set_cell_library_options -create_default_dft_cell_selection on -liberty_ignore_dont_use on \
    -report_clock_gaters off -report_scan_equivalent_undefined_references off \
    -report_nonscan_equivalent_undefined_references off
read_cell_library $env(BUILD)/sky130_hd.atpglib
read_liberty $env(LIB)
write_cell_library $env(BUILD)/sky130_hd_raw.tcelllib -replace -include_created_dft_cell_selections
exit
