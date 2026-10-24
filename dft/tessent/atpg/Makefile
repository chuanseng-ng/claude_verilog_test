# Siemens Tessent scan insertion + ATPG evaluation flow for the Sky130 SoC fabric (DFT Stage 2 evaluation).
# See docs/design/TESSENT_ATPG_FLOW.md.  Evaluation only: nothing here is back-annotated into PD.
#
#   make synth    sv2v netlist -> sky130_fd_sc_hd gate netlist (yosys)
#   make scan     Tessent scan insertion + scan DRC
#   make atpg     stuck-at (and transition) ATPG, patterns, coverage reports
#   make all      synth scan atpg
#   make clean
#
# Required tools: yosys (>= 0.62), sv2v, tessent (Tessent Shell 2025.4 on PATH, MGLS_LICENSE_FILE set).
# On hosts where the pinned sv2v needs a newer glibc, pass SV2V=<wrapper>.
HERE      := $(abspath .)
ROOT      := $(abspath $(HERE)/../../..)
BUILD     ?= $(HERE)/build
YOSYS     ?= yosys
SV2V      ?= sv2v
LIBDIR    ?= $(HERE)/lib
LIB       ?= $(LIBDIR)/sky130_fd_sc_hd__tt_025C_1v80.lib
# Tessent thread count (another heavy job may share the host).
THREADS   ?= 4
# Number of scan chains per the DFT_ARCHITECTURE decision (5 clk_i + 1 cpu_clk_i fabric; the 2 CPU-macro chains are not
# stitched here: the CPU macro is a black box).
export BUILD LIB ROOT THREADS

SV2V_NET  := $(BUILD)/soc_top_sv2v.v
GATE_NET  := $(BUILD)/soc_top_gate.v
SCAN_NET  := $(BUILD)/soc_top_scan.v

.PHONY: all synth scan atpg clean lib sv2v
all: synth scan atpg

lib: $(LIB)
$(LIB):
	sh $(HERE)/scripts/fetch_lib.sh $(LIBDIR)

# The sv2v netlist is the one the PD flow synthesises (pnr/Makefile sky130-soc-sv2v); regenerate it into BUILD so the
# checked-in tree is not touched.
sv2v: $(SV2V_NET)
$(SV2V_NET): FORCE
	mkdir -p $(BUILD)
	$(MAKE) -C $(ROOT)/pnr sky130-soc-sv2v SV2V=$(SV2V) SKY130_SOC_SV2V_OUT=$(SV2V_NET) > $(BUILD)/sv2v.log 2>&1
	@tail -4 $(BUILD)/sv2v.log

synth: $(GATE_NET)
$(GATE_NET): $(SV2V_NET) $(LIB) scripts/synth.ys.in scripts/latch_map.v
	sed -e 's|@LIB@|$(LIB)|g' -e 's|@NETLIST_IN@|$(SV2V_NET)|g' -e 's|@NETLIST_OUT@|$(GATE_NET)|g' \
	    -e 's|@STAT@|$(BUILD)/synth_stat.rpt|g' -e 's|@LATCHMAP@|$(HERE)/scripts/latch_map.v|g' \
	    scripts/synth.ys.in > $(BUILD)/synth.ys
	/usr/bin/time -v -o $(BUILD)/synth.time $(YOSYS) -q -l $(BUILD)/synth.log $(BUILD)/synth.ys
	@grep -E "Elapsed|Maximum resident" $(BUILD)/synth.time

scan: $(SCAN_NET)
$(SCAN_NET): $(GATE_NET) $(wildcard scripts/*.tcl)
	cd $(BUILD) && /usr/bin/time -v -o scan.time tessent -shell -dofile $(HERE)/scripts/scan.tcl -logfile scan.log < /dev/null > scan.out 2>&1
	@grep -E "Elapsed|Maximum resident" $(BUILD)/scan.time
	@test -s $(SCAN_NET)

atpg: $(SCAN_NET)
	cd $(BUILD) && /usr/bin/time -v -o atpg.time tessent -shell -dofile $(HERE)/scripts/atpg.tcl -logfile atpg.log < /dev/null > atpg.out 2>&1
	@grep -E "Elapsed|Maximum resident" $(BUILD)/atpg.time

clean:
	rm -rf $(BUILD)

FORCE:
