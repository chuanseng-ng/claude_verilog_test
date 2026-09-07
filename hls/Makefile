# hls/Makefile — Bambu HLS runs for the GH #119 PPA pilot.
#
# Run inside the HLS devshell, which is where `bambu` lives:
#     nix develop .#hls --command make -C hls <target>
#
# Every target goes through tools/eda/wrap-bambu.sh, so the exit status is a
# real verdict rather than Bambu's own (which is 0 for a generation run that
# produced nothing). See bead `dwp`.
include $(dir $(lastword $(MAKEFILE_LIST)))bambu.mk

HLS_DIR := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))

.PHONY: help
help:
	@echo "HLS (Bambu) targets — run via: nix develop .#hls --command make -C hls <target>"
	@echo "  memory_coalescer   — GH #119 datapath pole: C -> Verilog + cosim"
	@echo "  rv32i_hazard_unit  — GH #119 control pole: C -> Verilog (combinational ref)"
	@echo "  gate_b   — port-shape probe from GH #119 Gate B (regression for the flow itself)"
	@echo "  clean    — remove generated output under \$$(HLS_OUT)"
	@echo ""
	@echo "HLS_OUT = $(HLS_OUT)   (generated .v is not committed)"

# Gate B's port-shape probe, kept as a runnable regression: it is the cheapest
# end-to-end check that the toolchain, the ASAP7 device model, the cosim harness
# and the wrapper all still work together.
GATE_B_SRC := /nobackup/hls/scratch/gateB/gate_b.c
GATE_B_TB  := /nobackup/hls/scratch/gateB/gate_b_tb.xml

.PHONY: gate_b
gate_b:
	$(WRAP_BAMBU) $(HLS_OUT)/gate_b coal_shape $(GATE_B_SRC) \
	  $(BAMBU_FLAGS) --generate-tb=$(GATE_B_TB) $(BAMBU_SIM_FLAGS)

# The GH #119 datapath-pole arm: memory_coalescer, authored in C from the block's
# natural-language spec with the reference RTL body withheld (see NOTES.md). The
# generated .v is consumed by `make -C sim gpu_coalescer_hls`, which runs the
# SAME cocotb suite as the hand-RTL arm.
COALESCER_DIR := $(HLS_DIR)/gpu/memory_coalescer

.PHONY: memory_coalescer
memory_coalescer:
	$(WRAP_BAMBU) $(HLS_OUT)/memory_coalescer memory_coalescer \
	  $(COALESCER_DIR)/memory_coalescer.c \
	  $(BAMBU_FLAGS) --generate-tb=$(COALESCER_DIR)/memory_coalescer_tb.xml \
	  $(BAMBU_SIM_FLAGS)

# The GH #119 CONTROL pole: rv32i_hazard_unit, authored in C from the block's
# natural-language spec with the reference RTL body withheld (see NOTES.md).
#
# The reference is PURELY COMBINATIONAL (no clock, no reset, no always_ff), so
# the headline result for this block is that Bambu must wrap a zero-cycle
# function in a start/done FSM at all -- see NOTES.md.
#
# Leg 1 (Bambu's own C/RTL co-simulation) still applies and is still run: the C
# is the golden reference whether or not the reference RTL is combinational, so
# this leg validates the C->RTL step independently of whether the C itself is
# right. Leg 2 (the shared cocotb suite plus the cross-arm trace diff in
# tools/verif/compare_hazard_traces.py) is what validates the C against the spec.
HAZARD_DIR := $(HLS_DIR)/cpu/rv32i_hazard_unit

.PHONY: rv32i_hazard_unit
rv32i_hazard_unit:
	$(WRAP_BAMBU) $(HLS_OUT)/rv32i_hazard_unit rv32i_hazard_unit \
	  $(HAZARD_DIR)/rv32i_hazard_unit.c \
	  $(BAMBU_FLAGS) --generate-tb=$(HAZARD_DIR)/rv32i_hazard_unit_tb.xml \
	  $(BAMBU_SIM_FLAGS)

.PHONY: clean
clean:
	rm -rf $(HLS_OUT)
