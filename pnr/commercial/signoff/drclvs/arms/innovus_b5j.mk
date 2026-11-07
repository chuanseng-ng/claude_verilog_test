# Innovus b5j arm (b5h routed + in-place n-well tie ECO; b5g arm kept as arms/innovus.mk)
IN_DIR  ?= $(REPO)/pnr/commercial/impl/innovus/runs/b5j_innovus/out
GDS_IN  ?= $(IN_DIR)/rv32i_cpu_top.gds
DEF_IN  ?= $(IN_DIR)/rv32i_cpu_top.def
PNL_IN  ?= $(IN_DIR)/rv32i_cpu_top.pg.pnl.v
# B5g streamOut: pin metal (pin purpose) AND pin text are in the GDS (503 each), via metal pads mapped -> no pin-adding step needed
PIN_MODE = none
ANT_MAP = 1
