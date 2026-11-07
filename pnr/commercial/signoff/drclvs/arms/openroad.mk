# OpenROAD / LibreLane reference arm (step B2). Its Magic-written GDS is the one LibreLane's KLayout.DRC consumed.
IN_DIR  ?= $(REPO)/pnr/commercial/runs/openroad
GDS_IN  ?= $(IN_DIR)/rv32i_cpu_top.gds
DEF_IN  ?= $(IN_DIR)/rv32i_cpu_top.def
PNL_IN  ?= $(IN_DIR)/rv32i_cpu_top.pnl.v
ANT_MAP  = 0
