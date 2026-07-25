# OpenRAM config -- Sky130 4 KB (32,768 bit) SRAM hard macro, 1RW + 1R ports.
# GH #104 Sky130 SoC Stage-2: replaces the behavioral MEM_WORDS=1024 x 32b
# main-memory array in rtl/soc/sram_controller.sv with a real OpenRAM macro.
#
# Naming matches the installed sky130_sram_macros convention (singular
# "kbyte"): sky130_sram_<size>_<ports>_<word_size>x<num_words>_<write_size>.

word_size = 32   # bits
num_words = 1024
write_size = 8   # byte-wise write mask -> NUM_WMASKS = word_size/write_size = 4

# Dual port: 1 read/write + 1 read-only (matches existing 32x256 / 32x512 macros)
num_rw_ports = 1
num_r_ports = 1
num_w_ports = 0

tech_name = "sky130"
# TT / 1.8V / 25C only -- matches the SoC's nom_tt_025C_1v80 sign-off corner
# used by the other hardened macros (rv32i_cpu_top, sram_controller).
nominal_corner_only = True

route_supplies = "ring"
check_lvsdrc = True   # run OpenRAM's own magic DRC + netgen LVS after generation
uniquify = True

output_name = "sky130_sram_4kbyte_1rw1r_32x1024_8"
output_path = "macro/{}/".format(output_name)
