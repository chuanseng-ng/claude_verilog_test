# Innovus arm (step B5g; was b5d_innovus, results of b5d kept in runs/innovus_superseded_b5d)
IN_DIR  ?= $(REPO)/pnr/commercial/impl/innovus/runs/b5g_innovus/out
GDS_IN  ?= $(IN_DIR)/rv32i_cpu_top.gds
DEF_IN  ?= $(IN_DIR)/rv32i_cpu_top.def
PNL_IN  ?= $(IN_DIR)/rv32i_cpu_top.pg.pnl.v
# B5g streamOut: pin metal (pin purpose) AND pin text are in the GDS (503 each), via metal pads mapped -> no pin-adding step needed
PIN_MODE = none
ANT_MAP = 1
