# ICC2 arm, step B5m (b5i + PDN strap-end trim, antenna diodes, DRV sizing, hold buffer, export hygiene).  Use: make ARM=icc2_b5m <target>  (run dir runs/icc2_b5m, reports/icc2_b5m_*)
IN_DIR  ?= $(REPO)/pnr/commercial/impl/icc2/runs/b5m_icc2/out
GDS_IN  ?= $(IN_DIR)/rv32i_cpu_top.gds
DEF_IN  ?= $(IN_DIR)/rv32i_cpu_top.def
PNL_IN  ?= $(IN_DIR)/rv32i_cpu_top.full.pnl.v
# ICC2 write_gds -output_pin text writes pin NAMES only; same as the b5e arm (PIN_MODE=none per the task: the pin-adding step is skipped)
PIN_MODE = none
