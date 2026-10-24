# Tessent MemoryBIST evaluation flow (parallel to the in-house MBIST; commits nothing into rtl/).
# See docs/design/TESSENT_MBIST_EVALUATION.md.
#
#   make mbist-generate   sv2v the evaluation top, read the memory library, run DRC, create the DftSpecification
#   make mbist-insert     process_dft_specification: generate + insert the MBIST hardware, extract ICL, patterns spec
#   make mbist-sim        VCS: Tessent-generated patterns, full address count, fault-free (project SRAM model), then the
#                         fault-injection simv (MBIST_MODEL=fi) and the fault campaign (scripts/fi_campaign.py)
#   make mbist-area       sky130_fd_sc_hd area (yosys) of in-house blocks, baseline and Tessent-inserted design
#   make all              generate, insert, sim, area
#   make clean
#
# Variants (MBIST_VARIANT): full (default; 6 algorithms selectable at run time, per-memory go/no-go),
#   min (March C- only), tap (Tessent-inserted IEEE 1149.1 TAP instead of raw IJTAG ports).
#
# Host notes: the pinned sv2v needs a glibc wrapper on RHEL8 (SV2V=<wrapper>); Tessent licence comes from
# MGLS_LICENSE_FILE / SALT_LICENSE_SERVER; VCS from tools/eda/sim_env.sh.  Tessent is held to 2 processors
# (set_multiprocessing_options in dofiles/common_setup.tcl).  Optional host overrides: build/host_env.sh.
HERE      := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
ROOT      := $(abspath $(HERE)/../../..)
BUILD     := $(HERE)/build
SV2V      ?= sv2v
export SV2V
RUN       := $(HERE)/scripts/run_tessent.sh
# Same defines as pnr/Makefile SKY130_SOC_SV2V_DEFINES minus USE_SKY130_CLKCELLS (hand-instantiated clock cells are a
# physical-implementation choice and a black box to Tessent).  The memory macro is left undefined for sv2v on purpose:
# Tessent reads lib/*.v_interface, simulation reads the model (sim/ or tb/).
SV2V_DEFS := --define=__pnr__ --define=SRAM_SKY130
EVAL_SV   := $(ROOT)/rtl/soc/axi_pkg.sv $(ROOT)/rtl/soc/soc_addr_map_pkg.sv $(ROOT)/rtl/soc/soc_periph_map_pkg.sv \
             $(ROOT)/rtl/soc/dft/mem_collar.sv $(ROOT)/rtl/soc/sram_controller.sv $(ROOT)/rtl/npu/npu_weight_mem.sv \
             $(HERE)/rtl/mbist_eval_top.sv
EVAL_V    := $(BUILD)/mbist_eval_top_sv2v.v

.PHONY: all mbist-generate mbist-insert mbist-sim mbist-area clean
all: mbist-generate mbist-insert mbist-sim mbist-area

$(EVAL_V): $(EVAL_SV)
	@mkdir -p $(BUILD)
	$(SV2V) $(SV2V_DEFS) $(EVAL_SV) -w $@

mbist-generate: $(EVAL_V)
	$(RUN) $(HERE)/dofiles/mbist_generate.do mbist_generate.log

mbist-insert: $(EVAL_V)
	$(RUN) $(HERE)/dofiles/mbist_insert.do mbist_insert.log

mbist-sim:
	rm -rf $(BUILD)/run/simulation_outdir
	MBIST_MODEL=real $(RUN) $(HERE)/dofiles/mbist_sim.do mbist_sim_real.log
	MBIST_MODEL=fi   $(RUN) $(HERE)/dofiles/mbist_sim.do mbist_sim_fi.log
	python3 $(HERE)/scripts/fi_campaign.py --mem both --jobs 2

mbist-area:
	$(HERE)/scripts/area.sh inhouse
	$(HERE)/scripts/area.sh base
	$(HERE)/scripts/area.sh tessent

clean:
	rm -rf $(BUILD)
