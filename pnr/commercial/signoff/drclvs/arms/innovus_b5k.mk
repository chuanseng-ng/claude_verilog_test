# Innovus b5j arm (round-2 ECOs on b5j)
IN_DIR  ?= $(REPO)/pnr/commercial/impl/innovus/runs/b5k_innovus/out
GDS_IN  ?= $(IN_DIR)/rv32i_cpu_top.gds
DEF_IN  ?= $(IN_DIR)/rv32i_cpu_top.def
PNL_IN  ?= $(IN_DIR)/rv32i_cpu_top.pg.pnl.v
# B5g streamOut: pin metal (pin purpose) AND pin text are in the GDS (503 each), via metal pads mapped -> no pin-adding step needed
PIN_MODE = none
ANT_MAP = 1
