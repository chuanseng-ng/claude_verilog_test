# Innovus b11 PRE-FILL routed DEF (db 10_eco (b10 final pre-fill; the b11 ECO output is 11_eco_pre)) -- used only for the signoff-deck antenna check before the finish stage (antenna ECO input).
IN_DIR  ?= $(REPO)/pnr/commercial/impl/innovus/runs/b11_innovus/out_pre
GDS_IN  ?= $(IN_DIR)/rv32i_cpu_top.gds
DEF_IN  ?= $(IN_DIR)/rv32i_cpu_top.def
PNL_IN  ?= $(IN_DIR)/rv32i_cpu_top.pg.pnl.v
PIN_MODE = none
ANT_MAP = 1
