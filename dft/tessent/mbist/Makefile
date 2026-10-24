# Tessent MemoryBIST evaluation flow (parallel to the in-house MBIST; commits nothing into rtl/).
# See docs/design/TESSENT_MBIST_EVALUATION.md.
#
#   make mbist-generate   sv2v the evaluation top + read memory library + create_dft_specification (DRC, no insertion)
#   make mbist-insert     process_dft_specification: generate and insert the MBIST hardware, extract ICL, write testbench
#   make mbist-sim        run the Tessent-generated testbench on VCS: fault-free pass, then fault injection
#   make all              generate, insert, sim
#   make clean
#
# Host notes: the pinned sv2v needs a glibc wrapper on RHEL8 (pass SV2V=<wrapper>); Tessent licence comes from
# MGLS_LICENSE_FILE / SALT_LICENSE_SERVER; VCS from tools/eda/sim_env.sh.  Tessent is held to 2 threads.
ROOT      := $(abspath ../../..)
HERE      := $(abspath .)
BUILD     := $(HERE)/build
RUN       := $(BUILD)/run
SV2V      ?= sv2v
TESSENT   ?= tessent
THREADS   ?= 2
# Same defines as pnr/Makefile SKY130_SOC_SV2V_DEFINES minus USE_SKY130_CLKCELLS (hand-instantiated clock cells
# are a physical-implementation choice and a black box to Tessent).
SV2V_DEFS := --define=__pnr__ --define=SRAM_SKY130
EVAL_SV   := $(ROOT)/rtl/soc/axi_pkg.sv $(ROOT)/rtl/soc/soc_addr_map_pkg.sv $(ROOT)/rtl/soc/soc_periph_map_pkg.sv \
             $(ROOT)/pnr/sky130/soc/sky130_sram_4kbyte_1rw1r_32x1024_8_stub.sv \
             $(ROOT)/rtl/soc/dft/mem_collar.sv $(ROOT)/rtl/soc/sram_controller.sv $(ROOT)/rtl/npu/npu_weight_mem.sv \
             $(HERE)/rtl/mbist_eval_top.sv
EVAL_V    := $(BUILD)/mbist_eval_top_sv2v.v

.PHONY: all mbist-generate mbist-insert mbist-sim clean
all: mbist-generate mbist-insert mbist-sim

$(EVAL_V): $(EVAL_SV)
	@mkdir -p $(BUILD)
	$(SV2V) $(SV2V_DEFS) $(EVAL_SV) -w $@

mbist-generate: $(EVAL_V)
	@mkdir -p $(RUN)
	cd $(RUN) && MBIST_HERE=$(HERE) MBIST_BUILD=$(BUILD) $(TESSENT) -shell -log mbist_generate.log -replace -dofile $(HERE)/dofiles/mbist_generate.do

mbist-insert: $(EVAL_V)
	@mkdir -p $(RUN)
	cd $(RUN) && MBIST_HERE=$(HERE) MBIST_BUILD=$(BUILD) $(TESSENT) -shell -log mbist_insert.log -replace -dofile $(HERE)/dofiles/mbist_insert.do

mbist-sim:
	$(MAKE) -C $(HERE) -f sim.mk sim

clean:
	rm -rf $(BUILD)
