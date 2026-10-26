# Step B4b: Conformal LEC (Cadence lec 24.10-p100), RTL == Genus netlist (Sky130 rv32i_cpu_top).
#   make -C pnr/commercial/signoff/lec/conformal lec-genus          Genus' two-leg flow (RTL -> fv_map, fv_map -> final netlist)
#   make -C pnr/commercial/signoff/lec/conformal lec-genus-negctl   mutated final netlist (each must be NON-EQUIVALENT)
# Needs the Genus run (pnr/commercial/syn/genus, GTAG=b3b_genus_tt_r2).  Runs under safe_run.sh (6G cap, <=2 threads).
# The tool runs INSIDE runs/<tag>/ (never the repo root): the do-file reads fv/ by relative path and drops
# fv_map_*_db/, hier_tmp2.lec.do, noneq.* into the cwd.  fv/ is COPIED there so Genus' run dir stays unmodified.
SHELL := /bin/bash
.NOTPARALLEL:
HERE   := $(CURDIR)
REPO   := $(abspath $(HERE)/../../../../..)
PDKDIR := $(REPO)/pnr/commercial/pdk/sky130
GTAG   ?= b3b_genus_tt_r2
GRUN   := $(REPO)/pnr/commercial/syn/genus/runs/$(GTAG)
IMPL   ?= $(GRUN)/out/rv32i_cpu_top.nl.v
TAG    ?= b4b_genus_vs_rtl
RUN    := $(HERE)/runs/$(TAG)
DOFILE ?= $(HERE)/scripts/lec_genus.do
PE     := source $(REPO)/tools/eda/pd_env.sh >/dev/null 2>&1
SAFE   = export SAFE_MEM_MAX=6G SAFE_THREADS=2 SAFE_TIMEOUT=$(or $(TIMEOUT),7200)
# [B4b] -xl: analyze_extended_mapping (in the Genus do-file) needs a Conformal_Ultra (XL) licence; plain lec aborts at that line.
# [B4b] the Genus do-file requires $LEC_VERSION (>= 19.10-p100 for the RTL-names flow); it is the installed lec version.
LECVER ?= 24.10-p100
# composed RTL->final name mapping written by leg 1 of the main run (only used by the direct compare)
MAPFILE ?= $(HERE)/runs/b4b_genus_vs_rtl/fv_map_rv32i_cpu_topnlv_1.map.do

define RUNLEC
	@$(PE); $(SAFE); rm -rf $(RUN); mkdir -p $(RUN); cp -r $(GRUN)/fv $(RUN)/fv; cd $(RUN); \
	  export LEC_VERSION=$(LECVER) LEC_RUN=$(RUN) IMPL=$(1) MAPFILE=$(MAPFILE); \
	  /usr/bin/time -v -o $(RUN)/time.txt $(PDKDIR)/scripts/safe_run.sh $(RUN)/lec.stdout lec -nogui -xl -dofile $(2) ; \
	  rc=$$?; echo "lec rc=$$rc"; grep -E "B4B_LEG1_VERDICT|Compare Results|No of (compare|diff|abort|unknown)" $(RUN)/lec.log | tail -12; exit $$rc
endef

.PHONY: gen lec-genus lec-genus-negctl lec-genus-flat lec-genus-direct lec-innovus-rtl lec-innovus-genus lec-innovus-rtl-nodiode lec-innovus-genus-nodiode lec-innovus-negctl
gen:
	python3 $(HERE)/scripts/mk_do.py $(GRUN)/out/lec_rv32i_cpu_top.do $(HERE)/scripts/lec_genus.do

lec-genus:
	$(call RUNLEC,$(IMPL),$(DOFILE))

# Negative controls (REQUIRED for the EQUIVALENT verdict to count).  Mutants of the FINAL netlist (scripts/mk_mutant.py), each run through
#  (1) Genus' two-leg flow (leg 1, fv_map vs mutant, must report NOT_EQUIVALENT) and
#  (2) the direct RTL-vs-netlist compare (must report NOT_EQUIVALENT).  The recipe fails if any mutant is judged equivalent.
lec-genus-negctl:
	@mkdir -p $(HERE)/runs
	python3 $(HERE)/scripts/mk_mutant.py $(GRUN)/out/rv32i_cpu_top.nl.v $(HERE)/runs/mutant_fwdb_inv.nl.v fwdb_inv
	python3 $(HERE)/scripts/mk_mutant.py $(GRUN)/out/rv32i_cpu_top.nl.v $(HERE)/runs/mutant_swap.nl.v swap
	-$(MAKE) lec-genus IMPL=$(HERE)/runs/mutant_fwdb_inv.nl.v TAG=b4b_negctl_fwdb_inv
	-$(MAKE) lec-genus IMPL=$(HERE)/runs/mutant_swap.nl.v TAG=b4b_negctl_swap
	-$(MAKE) lec-genus DOFILE=$(HERE)/scripts/lec_genus_direct.do IMPL=$(HERE)/runs/mutant_fwdb_inv.nl.v TAG=b4b_negctl_direct_fwdb_inv
	-$(MAKE) lec-genus DOFILE=$(HERE)/scripts/lec_genus_direct.do IMPL=$(HERE)/runs/mutant_swap.nl.v TAG=b4b_negctl_direct_swap
	@rc=0; for t in b4b_negctl_fwdb_inv b4b_negctl_swap; do \
	  if grep -q "B4B_LEG1_VERDICT: NOT_EQUIVALENT" $(HERE)/runs/$$t/lec.log; then echo "negctl $$t (two-leg, leg 1): NON-EQUIVALENT (good)"; \
	  else echo "negctl $$t: NOT DETECTED -- LEC verdict is untrustworthy"; rc=1; fi; done; \
	for t in b4b_negctl_direct_fwdb_inv b4b_negctl_direct_swap; do \
	  if grep -q "B4B_DIRECT_VERDICT: NOT_EQUIVALENT" $(HERE)/runs/$$t/lec.log; then echo "negctl $$t (direct): NON-EQUIVALENT (good)"; \
	  else echo "negctl $$t: NOT DETECTED -- LEC verdict is untrustworthy"; rc=1; fi; done; exit $$rc

# Flat RTL -> fv_map compare (Genus' leg 2 without the hierarchical module-boundary constraints); also dumps the unmapped/unreachable lists.
lec-genus-flat:
	$(MAKE) lec-genus DOFILE=$(HERE)/scripts/lec_genus_flat.do TAG=b4b_flat_rtl_vs_fvmap

# Direct flat RTL -> FINAL netlist compare, no Genus implementation information (constants/merges found by Conformal itself).
lec-genus-direct:
	$(MAKE) lec-genus DOFILE=$(HERE)/scripts/lec_genus_direct.do TAG=b4b_direct_rtl_vs_final

# ---------------------------------------------------------------------------------------------------------------------------------
# Step B4d/B4e: post-route Innovus netlist.  Flat compares, no fv_map / Genus implementation info.  Parameterised so b5b and b5c both stay reproducible:
#   make lec-innovus-all                                         b5b -> tags b4d_*   (defaults)
#   make lec-innovus-all INNTAG=b5c_innovus_s2 STEP=b4e          b5c -> tags b4e_*
#   lec-innovus-rtl      (a) RTL vs Innovus netlist          lec-innovus-genus   (b) Genus final netlist vs Innovus netlist
#   *-nodiode            same with the diode_2 cells stripped (scripts/strip_diodes.py, count derived)
#   lec-innovus-negctl   2 mutants x 2 golden designs, each must be NON-EQUIVALENT
INNTAG   ?= b5b_innovus
STEP     ?= b4d
INNNL    ?= $(REPO)/pnr/commercial/impl/innovus/runs/$(INNTAG)/out/rv32i_cpu_top.nl.v
GENUS_NL ?= $(GRUN)/out/rv32i_cpu_top.nl.v
INNMAP   ?= $(HERE)/runs/b4b_genus_vs_rtl/fv_map_rv32i_cpu_topnlv_1.map.do
ND       := $(HERE)/runs/$(STEP)_innovus_nodiode.nl.v
define RUNLEC2
	@$(PE); $(SAFE); rm -rf $(RUN); mkdir -p $(RUN); cd $(RUN); \
	  export LEC_VERSION=$(LECVER) LEC_RUN=$(RUN) IMPL=$(1) MAPFILE=$(3) GOLDEN_NL=$(GENUS_NL); \
	  /usr/bin/time -v -o $(RUN)/time.txt $(PDKDIR)/scripts/safe_run.sh $(RUN)/lec.stdout lec -nogui -xl -dofile $(2) ; \
	  rc=$$?; echo "lec rc=$$rc"; grep -E "B4D_[A-Z]*_VERDICT|No of (compare|diff|abort|unknown)" $(RUN)/lec.log | tail -6; exit $$rc
endef
.PHONY: lec-innovus-all
$(ND): $(INNNL) $(HERE)/scripts/strip_diodes.py
	@mkdir -p $(HERE)/runs
	python3 $(HERE)/scripts/strip_diodes.py $(INNNL) $@

lec-innovus-rtl:
	$(call RUNLEC2,$(INNNL),$(HERE)/scripts/lec_innovus_rtl.do,$(INNMAP))
lec-innovus-genus:
	$(call RUNLEC2,$(INNNL),$(HERE)/scripts/lec_innovus_genus.do,)
lec-innovus-rtl-nodiode: $(ND)
	$(MAKE) lec-innovus-rtl INNNL=$(ND) TAG=$(STEP)_innovus_nodiode_vs_rtl
lec-innovus-genus-nodiode: $(ND)
	$(MAKE) lec-innovus-genus INNNL=$(ND) TAG=$(STEP)_innovus_nodiode_vs_genus

lec-innovus-negctl:
	@mkdir -p $(HERE)/runs
	python3 $(HERE)/scripts/mk_mutant_innovus.py $(INNNL) $(HERE)/runs/$(STEP)_mutant_fwdb_inv.nl.v fwdb_inv
	python3 $(HERE)/scripts/mk_mutant_innovus.py $(INNNL) $(HERE)/runs/$(STEP)_mutant_swap.nl.v swap
	-$(MAKE) lec-innovus-rtl INNNL=$(HERE)/runs/$(STEP)_mutant_fwdb_inv.nl.v TAG=$(STEP)_negctl_rtl_fwdb_inv
	-$(MAKE) lec-innovus-rtl INNNL=$(HERE)/runs/$(STEP)_mutant_swap.nl.v TAG=$(STEP)_negctl_rtl_swap
	-$(MAKE) lec-innovus-genus INNNL=$(HERE)/runs/$(STEP)_mutant_fwdb_inv.nl.v TAG=$(STEP)_negctl_genus_fwdb_inv
	-$(MAKE) lec-innovus-genus INNNL=$(HERE)/runs/$(STEP)_mutant_swap.nl.v TAG=$(STEP)_negctl_genus_swap
	@rc=0; for t in rtl_fwdb_inv rtl_swap; do \
	  if grep -q "B4D_RTL_VERDICT: NOT_EQUIVALENT" $(HERE)/runs/$(STEP)_negctl_$$t/lec.log; then echo "negctl $$t (vs RTL): NON-EQUIVALENT (good)"; \
	  else echo "negctl $$t: NOT DETECTED -- LEC verdict is untrustworthy"; rc=1; fi; done; \
	for t in genus_fwdb_inv genus_swap; do \
	  if grep -q "B4D_GENUS_VERDICT: NOT_EQUIVALENT" $(HERE)/runs/$(STEP)_negctl_$$t/lec.log; then echo "negctl $$t (vs Genus netlist): NON-EQUIVALENT (good)"; \
	  else echo "negctl $$t: NOT DETECTED -- LEC verdict is untrustworthy"; rc=1; fi; done; exit $$rc

# everything for one netlist: 4 compares + negative controls (verdicts are read from the logs afterwards)
lec-innovus-all:
	$(MAKE) lec-innovus-rtl TAG=$(STEP)_innovus_vs_rtl
	$(MAKE) lec-innovus-genus TAG=$(STEP)_innovus_vs_genus
	$(MAKE) lec-innovus-rtl-nodiode
	$(MAKE) lec-innovus-genus-nodiode
	$(MAKE) lec-innovus-negctl
