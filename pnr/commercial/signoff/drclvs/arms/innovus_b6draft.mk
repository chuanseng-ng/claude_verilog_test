# Innovus b6 DRAFT finish (stub/antenna lists are derived from this arm; not a result)
IN_DIR  ?= $(REPO)/pnr/commercial/impl/innovus/runs/b6_innovus/out_draft
GDS_IN  ?= $(IN_DIR)/rv32i_cpu_top.gds
DEF_IN  ?= $(IN_DIR)/rv32i_cpu_top.def
PNL_IN  ?= $(IN_DIR)/rv32i_cpu_top.pg.pnl.v
# B5g streamOut: pin metal (pin purpose) AND pin text are in the GDS (503 each), via metal pads mapped -> no pin-adding step needed
PIN_MODE = none
ANT_MAP = 1
