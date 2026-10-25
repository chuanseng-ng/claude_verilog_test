# Step B5a: ICC2 place-and-route of the Sky130 CPU macro rv32i_cpu_top from the Formality-proven DC-NXT netlist (b3a_dc_tt).
#   make -C pnr/commercial/impl/icc2 all [TAG=b5a_icc2]       full flow, ~35 min wall on 2 cores, peak RSS 3.8 GB
#   make -C pnr/commercial/impl/icc2 stage S=03_place         one stage (each stage copies the previous block label, edits the copy, saves it)
# Every stage runs through pdk/sky130/scripts/safe_run.sh (load/memory gate, 6 GB cap, process-group kill), icc2_shell, set_host_options -max_cores 2.
# Stage chain / block labels in runs/$(TAG)/rv32i.dlib: 01_floorplan -> 02_pdn -> 03_place -> 04_cts -> 05_route -> 05b_repair -> 05c_repair -> 06_finish
# (07_write_verilog re-writes the three netlist variants from 06_finish).  05b/05c are detail-route repair loops (see reports/stage_markers.txt).
SHELL := /bin/bash
.NOTPARALLEL:
TAG ?= b5a_icc2
STAGES := 01_floorplan 02_pdn 03_place 04_cts 05_route 05b_repair 05c_repair 06_finish 07_write_verilog
.PHONY: all stage clean-svf help $(STAGES)
help:
	@echo "all | stage S=<NN_name> | outputs in runs/$(TAG)/out (nl.v pg.nl.v full.pnl.v def gds sdc spef)"
all: $(STAGES)
$(STAGES):
	@scripts/run_stage.sh $@ $(TAG)
stage:
	@scripts/run_stage.sh $(S) $(TAG)
