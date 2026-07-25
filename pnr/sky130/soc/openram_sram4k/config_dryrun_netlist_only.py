# Quick sanity-check pass: netlist/timing only, no layout/DRC/LVS/GDS.
# Used to validate the config + tool setup before committing to the full,
# long-running GDS+DRC+LVS compile.

word_size = 32
num_words = 1024
write_size = 8

num_rw_ports = 1
num_r_ports = 1
num_w_ports = 0

tech_name = "sky130"
nominal_corner_only = True

check_lvsdrc = False
netlist_only = True
uniquify = True

output_name = "sky130_sram_4kbyte_1rw1r_32x1024_8_dryrun"
output_path = "macro/{}/".format(output_name)
