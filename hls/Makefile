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
	@echo "  memory_coalescer — GH #119 datapath pole: C -> Verilog + cosim"
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

.PHONY: clean
clean:
	rm -rf $(HLS_OUT)
