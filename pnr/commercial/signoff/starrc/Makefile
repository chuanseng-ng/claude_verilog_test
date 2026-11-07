# numpy is needed by correlate.py/pinfit.py; the venvs here lack it, Calibre's bundled python3 has it.
PY ?= /home/EDA/mentor/calibre2026/aok_cal_2026.1_17.11/bin/python3
# StarRC neutral-judge extraction, Sky130 rv32i_cpu_top (B1 part 2b).  Run from this directory.
#   make smoke            OpenROAD DEF at nom (mapping / layer / open checks)
#   make corr-extract     OpenROAD DEF at nom, min, max (inputs of the correlation gate)
#   make judge            OpenROAD + ICC2 x nom/min/max, strictly one at a time
#   make innovus          Innovus (b5c DEF) x nom/min/max
#   make corr             StarRC vs OpenRCX ratio tables -> reports/correlation_<corner>.md
#   make stats            per-arm table input (reports/per_arm.tsv)
# Every extraction goes through run_starrc.sh -> pnr/commercial/pdk/sky130/scripts/safe_run.sh
# (load/memory gate, <= 2 threads, process-group kill).  Never run two at once.
ARMS    := openroad icc2 innovus
CORNERS := nom min max
RUNS    := runs
.NOTPARALLEL:
.SECONDARY:
.PHONY: smoke corr-extract judge innovus corr stats clean-star
smoke: $(RUNS)/openroad_nom/.done
corr-extract: $(foreach c,$(CORNERS),$(RUNS)/openroad_$(c)/.done)
judge: $(foreach a,openroad icc2,$(foreach c,$(CORNERS),$(RUNS)/$(a)_$(c)/.done))
# Innovus arm: only from the b5c reroute DEF (b5b is superseded).  One command once b5c/out/rv32i_cpu_top.def is complete:
#   make innovus
innovus: $(foreach c,$(CORNERS),$(RUNS)/innovus_$(c)/.done)

$(RUNS)/%/.done:
	@a=$(word 1,$(subst _, ,$*)); c=$(word 2,$(subst _, ,$*)); \
	scripts/run_starrc.sh $$a $$c && touch $@

# OpenRCX reference SPEFs (OpenROAD arm) -> tsv; StarRC SPEFs -> tsv
$(RUNS)/corr/rcx_openroad_%.tsv:
	@mkdir -p $(RUNS)/corr
	$(PY) -I scripts/spef_stats.py ../../runs/openroad/rv32i_cpu_top.$*.spef $@
$(RUNS)/corr/sr_%.tsv: $(RUNS)/%/.done
	@mkdir -p $(RUNS)/corr
	@n=$*; c=$${n##*_}; $(PY) -I scripts/spef_stats.py $(RUNS)/$*/rv32i_cpu_top.$$c.spef $@

corr: $(foreach c,$(CORNERS),reports/correlation_$(c).md)
reports/correlation_%.md: $(RUNS)/corr/rcx_openroad_%.tsv $(RUNS)/corr/sr_openroad_%.tsv
	$(PY) -I scripts/correlate.py $(RUNS)/corr/rcx_openroad_$*.tsv $(RUNS)/corr/sr_openroad_$*.tsv $* > $@

stats:
	$(PY) -I scripts/collect_stats.py > reports/per_arm.md
