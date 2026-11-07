# Innovus b6 PRE-FILL routed DEF (db 05m_eco) -- used only for the signoff-deck antenna check before the finish stage (antenna ECO input).
IN_DIR  ?= $(REPO)/pnr/commercial/impl/innovus/runs/b6_innovus/out_pre
GDS_IN  ?= $(IN_DIR)/rv32i_cpu_top.gds
DEF_IN  ?= $(IN_DIR)/rv32i_cpu_top.def
PNL_IN  ?= $(IN_DIR)/rv32i_cpu_top.pg.pnl.v
PIN_MODE = none
ANT_MAP = 1
