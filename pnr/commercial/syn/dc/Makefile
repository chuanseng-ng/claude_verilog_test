# Step B3a: Synopsys DC-NXT topographical synthesis of the Sky130 CPU macro (comparison run, no PPA target).
#   make -C pnr/commercial/syn/dc dc-synth [TAG=b3a_dc_tt]      full flow (elab -> floorplan -> compile_ultra -spg -> reports)
#   make -C pnr/commercial/syn/dc dc-elab                       elaboration + link + check_design only (seconds)
# Needs the PDK build products of pnr/commercial/pdk/sky130 (make part2a): build/db, build/ndm, build/nxtgrd/nom, build/tech/map.
# Runs through pdk/sky130/scripts/safe_run.sh (load/memory gate, process-group kill); <= 2 cores; one vendor tool at a time.
SHELL := /bin/bash
.NOTPARALLEL:
HERE   := $(CURDIR)
REPO   := $(abspath $(HERE)/../../../..)
PDKDIR := $(REPO)/pnr/commercial/pdk/sky130
TAG    ?= b3a_dc_tt
RUN    := $(HERE)/runs/$(TAG)
SDC    := $(REPO)/pnr/sky130/cpu/constraints/sky130_cpu.sdc
PE     := source $(REPO)/tools/eda/pd_env.sh >/dev/null 2>&1
SAFE   = export SAFE_MEM_MAX=6G SAFE_THREADS=2 SAFE_TIMEOUT=$(or $(TIMEOUT),10800)

.PHONY: dc-synth dc-elab help
help:
	@echo "dc-synth  full DC-NXT topo synthesis -> runs/$(TAG)/{out,reports}; dc-elab elaboration only"

define RUNDC
	@$(PE); $(SAFE); mkdir -p $(RUN); cd $(RUN); \
	  export REPO=$(REPO) PDKDIR=$(PDKDIR) RUN=$(RUN) STOP=$(1) SCRIPTDIR=$(HERE)/scripts RTL_LIST=$(RUN)/rtl.f; \
	  $(HERE)/scripts/rtl_list.sh $(REPO) $(RUN)/rtl.f; \
	  md5sum $(SDC) > $(RUN)/sdc.md5; cat $(RUN)/sdc.md5; \
	  /usr/bin/time -v -o $(RUN)/time.txt $(PDKDIR)/scripts/safe_run.sh $(RUN)/dc.log dcnxt_shell -topographical_mode -f $(HERE)/scripts/dc_synth.tcl; \
	  rc=$$?; echo "dcnxt rc=$$rc"; exit $$rc
endef

dc-elab:
	$(call RUNDC,elab)
	@grep -E "ANALYZE_RESULT|ELABORATE_RESULT|LINK_RESULT|SRAM cells" $(RUN)/dc.log

dc-synth:
	$(call RUNDC,all)
	@grep -q "^DC_DONE" $(RUN)/dc.log && echo "DC SYNTH OK" || { echo "DC SYNTH FAILED (no DC_DONE)"; exit 1; }
