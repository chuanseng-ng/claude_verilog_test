# ICC2 arm, step b8 (DC v2 MCMM netlist, ICC2 MCMM place/CTS/route, up-front met4 halo + strap-end trim, antenna diode ECO, export hygiene).  Use: make ARM=icc2_b8 <target>
IN_DIR  ?= $(REPO)/pnr/commercial/impl/icc2/runs/b8_icc2/out
GDS_IN  ?= $(IN_DIR)/rv32i_cpu_top.gds
DEF_IN  ?= $(IN_DIR)/rv32i_cpu_top.def
PNL_IN  ?= $(IN_DIR)/rv32i_cpu_top.full.pnl.v
# ICC2 write_gds -output_pin text writes pin NAMES only; same as the b5e arm (PIN_MODE=none per the task: the pin-adding step is skipped)
PIN_MODE = none
