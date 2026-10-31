# Innovus arm (step B5g; was b5d_innovus, results of b5d kept in runs/innovus_superseded_b5d)
IN_DIR  ?= $(REPO)/pnr/commercial/impl/innovus/runs/b5g_innovus/out
GDS_IN  ?= $(IN_DIR)/rv32i_cpu_top.gds
DEF_IN  ?= $(IN_DIR)/rv32i_cpu_top.def
PNL_IN  ?= $(IN_DIR)/rv32i_cpu_top.pg.pnl.v
# Innovus streamOut writes pin metal (pin purpose) but no pin text
PIN_MODE = text
ANT_MAP = 1
