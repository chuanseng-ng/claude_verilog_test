# Innovus arm (step B5c; the dir is rewritten by the running reroute -- re-check file names when it finishes)
IN_DIR  ?= $(REPO)/pnr/commercial/impl/innovus/runs/b5d_innovus/out
GDS_IN  ?= $(IN_DIR)/rv32i_cpu_top.gds
DEF_IN  ?= $(IN_DIR)/rv32i_cpu_top.def
PNL_IN  ?= $(IN_DIR)/rv32i_cpu_top.pg.pnl.v
# Innovus streamOut writes pin metal (pin purpose) but no pin text
PIN_MODE = text
ANT_MAP = 1
