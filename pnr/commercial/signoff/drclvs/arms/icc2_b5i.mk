# ICC2 arm, step B5i (b5e + in-place met1-short / met4-spacing ECO).  Use: make ARM=icc2_b5i <target>  (run dir runs/icc2_b5i, reports/icc2_b5i_*; the b5e arm 'icc2' is untouched)
IN_DIR  ?= $(REPO)/pnr/commercial/impl/icc2/runs/b5i_icc2/out
GDS_IN  ?= $(IN_DIR)/rv32i_cpu_top.gds
DEF_IN  ?= $(IN_DIR)/rv32i_cpu_top.def
PNL_IN  ?= $(IN_DIR)/rv32i_cpu_top.full.pnl.v
# ICC2 write_gds -output_pin text writes pin NAMES only; same as the b5e arm (PIN_MODE=none per the task: the pin-adding step is skipped)
PIN_MODE = none
