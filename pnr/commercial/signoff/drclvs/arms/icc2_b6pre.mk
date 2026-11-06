# ICC2 b6 PRE-ECO routed DEF (stage b6_05_route out/pre_ant.def) -- used only for the signoff-deck antenna check before the antenna diode ECO (ECO input).
IN_DIR  ?= $(REPO)/pnr/commercial/impl/icc2/runs/b6_icc2/out
GDS_IN  ?= $(IN_DIR)/rv32i_cpu_top.gds
DEF_IN  ?= $(IN_DIR)/pre_ant.def
PNL_IN  ?= $(IN_DIR)/rv32i_cpu_top.full.pnl.v
PIN_MODE = none
ANT_MAP = 1
