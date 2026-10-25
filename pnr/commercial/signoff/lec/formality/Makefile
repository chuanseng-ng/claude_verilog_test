# Step B4a: Formality LEC, RTL == DC-NXT netlist (Sky130 rv32i_cpu_top).
#   make -C pnr/commercial/signoff/lec/formality lec-dc            real design
#   make -C pnr/commercial/signoff/lec/formality lec-dc-negctl     mutated-netlist negative control (must be NON-EQUIVALENT)
# Needs: DC run (pnr/commercial/syn/dc, TAG=b3a_dc_tt) and the PDK .db build products. Runs under safe_run.sh (6G cap, <=2 cores).
SHELL := /bin/bash
.NOTPARALLEL:
HERE   := $(CURDIR)
REPO   := $(abspath $(HERE)/../../../../..)
PDKDIR := $(REPO)/pnr/commercial/pdk/sky130
DCTAG  ?= b3a_dc_tt
DCOUT  := $(REPO)/pnr/commercial/syn/dc/runs/$(DCTAG)/out
IMPL   ?= $(DCOUT)/rv32i_cpu_top.nl.v
SVF    ?= $(DCOUT)/rv32i_cpu_top.svf
TAG    ?= b4a_dc_vs_rtl
RUN    := $(HERE)/runs/$(TAG)
PE     := source $(REPO)/tools/eda/pd_env.sh >/dev/null 2>&1
SAFE   = export SAFE_MEM_MAX=6G SAFE_THREADS=2 SAFE_TIMEOUT=$(or $(TIMEOUT),7200)

define RUNFM
	@$(PE); $(SAFE); mkdir -p $(RUN); cd $(RUN); \
	  export REPO=$(REPO) PDKDIR=$(PDKDIR) RUN=$(RUN) IMPL=$(1) SVF=$(2) RTL_LIST=$(RUN)/rtl.f; \
	  $(REPO)/pnr/commercial/syn/dc/scripts/rtl_list.sh $(REPO) $(RUN)/rtl.f; \
	  if [ -n "$(RTL_SUBST)" ]; then sed -i "s#^$(word 1,$(subst =, ,$(RTL_SUBST)))\$$#$(word 2,$(subst =, ,$(RTL_SUBST)))#" $(RUN)/rtl.f; echo "RTL_SUBST applied: $(RTL_SUBST)"; fi; \
	  /usr/bin/time -v -o $(RUN)/time.txt $(PDKDIR)/scripts/safe_run.sh $(RUN)/fm.log fm_shell -f $(HERE)/scripts/fm_lec.tcl; \
	  rc=$$?; echo "fm_shell rc=$$rc"; grep -E "VERIFY_RESULT|FM_DONE|Verification (SUCCEEDED|FAILED|INCONCLUSIVE)" $(RUN)/fm.log; exit $$rc
endef

.PHONY: lec-dc lec-dc-nosvf lec-dc-negctl lec-dc-svfprobe
lec-dc:
	$(call RUNFM,$(IMPL),$(SVF))

# RTL_SUBST=<orig.sv>=<mutated.sv> swaps one reference file (RTL-side probes of the SVF guidance, see report).
# lec-dc-nosvf: ablation run without the SVF (expected FAIL: DC's constant/merged registers are unmatched).
lec-dc-nosvf:
	$(MAKE) lec-dc SVF=none TAG=b4a_dc_vs_rtl_nosvf

# Negative controls (REQUIRED for the EQUIVALENT verdict to count): netlist mutants from scripts/mk_mutant.py;
# each must end 'Verification FAILED'.  The recipe fails if a mutant is judged equivalent.
lec-dc-negctl:
	@mkdir -p $(HERE)/runs
	python3 $(HERE)/scripts/mk_mutant.py $(IMPL) $(HERE)/runs/mutant_fwdb_inv.nl.v fwdb_inv
	python3 $(HERE)/scripts/mk_mutant.py $(IMPL) $(HERE)/runs/mutant_swap.nl.v swap
	-$(MAKE) lec-dc IMPL=$(HERE)/runs/mutant_fwdb_inv.nl.v TAG=b4a_negctl_fwdb_inv
	-$(MAKE) lec-dc IMPL=$(HERE)/runs/mutant_swap.nl.v TAG=b4a_negctl_swap
	@for t in b4a_negctl_fwdb_inv b4a_negctl_swap; do \
	  if grep -q "Verification FAILED" $(HERE)/runs/$$t/fm.log; then echo "negctl $$t: NON-EQUIVALENT (good)"; \
	  else echo "negctl $$t: NOT DETECTED -- LEC verdict is untrustworthy"; exit 1; fi; done

# SVF-guidance probes: RTL mutants that falsify DC's merge claim (fwd_store_sel_r == fwd_b_sel_r) / constant claim
# (flush_ex_mem register == 0).  Each must FAIL, proving Formality verifies (not blindly trusts) the SVF guidance.
RTLMUT := $(HERE)/runs/rtlmut
lec-dc-svfprobe:
	@mkdir -p $(RTLMUT)
	sed '535s/<= fwd_b_sel_pre_w;/<= ~fwd_b_sel_pre_w;/' $(REPO)/rtl/cpu/core/rv32i_core.sv > $(RTLMUT)/rv32i_core_m2.sv
	sed "335s/flush_ex_mem  = 1'b0;/flush_ex_mem  = 1'b1;/" $(REPO)/rtl/cpu/core/rv32i_pipeline_pkg.sv > $(RTLMUT)/rv32i_pipeline_pkg_m3.sv
	-$(MAKE) lec-dc TAG=b4a_rtlmut_m2_merge RTL_SUBST=$(REPO)/rtl/cpu/core/rv32i_core.sv=$(RTLMUT)/rv32i_core_m2.sv
	-$(MAKE) lec-dc TAG=b4a_rtlmut_m3_const RTL_SUBST=$(REPO)/rtl/cpu/core/rv32i_pipeline_pkg.sv=$(RTLMUT)/rv32i_pipeline_pkg_m3.sv
	@for t in b4a_rtlmut_m2_merge b4a_rtlmut_m3_const; do grep -q "Verification FAILED" $(HERE)/runs/$$t/fm.log && echo "svfprobe $$t: FAILED (good)" || { echo "svfprobe $$t: PASSED -- SVF guidance is not verified"; exit 1; }; done
