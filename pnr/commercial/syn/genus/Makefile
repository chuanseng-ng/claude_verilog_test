# Step B3b: Cadence Genus 23.14 synthesis of the Sky130 CPU macro (comparison run, no PPA target).
#   make -C pnr/commercial/syn/genus genus-synth [TAG=b3b_genus_tt] [PHYS=1|0]   full flow (elab -> floorplan -> syn_generic/map/opt -> reports)
#   make -C pnr/commercial/syn/genus genus-elab                                   elaboration + check_design only (seconds)
# Needs the PDK build products of pnr/commercial/pdk/sky130 (build/db not used by Genus; Genus reads the .lib directly via mmmc.tcl).
# Runs through pdk/sky130/scripts/safe_run.sh (load/memory gate, process-group kill); <= 2 cores; one vendor tool at a time.
SHELL := /bin/bash
.NOTPARALLEL:
HERE   := $(CURDIR)
REPO   := $(abspath $(HERE)/../../../..)
PDKDIR := $(REPO)/pnr/commercial/pdk/sky130
TAG    ?= b3b_genus_tt
PHYS   ?= 1
RUN    := $(HERE)/runs/$(TAG)
SDC    := $(REPO)/pnr/sky130/cpu/constraints/sky130_cpu.sdc
PE     := source $(REPO)/tools/eda/pd_env.sh >/dev/null 2>&1
SAFE   = export SAFE_MEM_MAX=6G SAFE_THREADS=2 SAFE_TIMEOUT=$(or $(TIMEOUT),10800)

.PHONY: genus-synth genus-elab help
help:
	@echo "genus-synth  full Genus synthesis -> runs/$(TAG)/{out,reports}; genus-elab elaboration only"

define RUNGENUS
	@$(PE); $(SAFE); mkdir -p $(RUN); cd $(RUN); \
	  export REPO=$(REPO) PDKDIR=$(PDKDIR) RUN=$(RUN) STOP=$(1) PHYS=$(PHYS) SCRIPTDIR=$(HERE)/scripts RTL_LIST=$(RUN)/rtl.f; \
	  $(HERE)/scripts/rtl_list.sh $(REPO) $(RUN)/rtl.f; \
	  md5sum $(SDC) > $(RUN)/sdc.md5; cat $(RUN)/sdc.md5; \
	  /usr/bin/time -v -o $(RUN)/time.txt $(PDKDIR)/scripts/safe_run.sh $(RUN)/genus.log genus -no_gui -overwrite -f $(HERE)/scripts/genus_synth.tcl; \
	  rc=$$?; echo "genus rc=$$rc"; exit $$rc
endef

genus-elab:
	$(call RUNGENUS,elab)
	@grep -E "ELABORATE_DONE|sram:" $(RUN)/genus.log

genus-synth:
	$(call RUNGENUS,all)
	@grep -q "^GENUS_DONE" $(RUN)/genus.log && echo "GENUS SYNTH OK" || { echo "GENUS SYNTH FAILED (no GENUS_DONE)"; exit 1; }
