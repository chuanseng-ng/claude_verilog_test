# Physical verification (DRC + LVS + antenna) of a Sky130 rv32i_cpu_top layout with the OPEN decks only
# (Calibre/PVS have no public Sky130 decks). Tools run inside ghcr.io/librelane/librelane:2.4.13 (Magic 8.3.489,
# Netgen 1.5.278, KLayout 0.29.4, OpenROAD edf00dff) and use LibreLane's own Magic/Netgen scripts + env files copied from the
# OpenROAD-arm reference run, so the checks are the ones the OpenROAD arm passed.
#
#   make ARM=icc2    all         # or any single target below
#   make ARM=innovus all
#   make ARM=openroad lvs        # positive control of the harness on the reference arm
#
# Targets (one heavy tool at a time; every tool runs under scripts/guard_run.sh = safe_run.sh + MemAvailable watchdog):
#   inspect    GDS integrity: structure census, empty/referenced-only cells, layer:datatype map spot check   (klayout, ~1 GB)
#   fixgds     measurement copy of the GDS with truncated-name instance references repaired (no-op if none)    (klayout)
#   lvs        lvs-extract + lvs-netgen: Magic extraction of the DEF+LEF (LibreLane mode) vs powered netlist   (3 GB + 3 GB)
#   lvs-gds    Magic extraction from the GDS (std cells/SRAM as LEF abstracts) vs powered netlist              (see script)
#   kdrc       KLayout DRC, sky130A_mr.drc, same options as LibreLane                                          (~5 GB)
#   mdrc       Magic DRC drc(full), same script as LibreLane Magic.DRC; starts only when MemAvailable >= 11 GB (~9 GB peak)
#   mdrc-class stream-classify the Magic report: per rule, inside vs outside the SRAM footprints (45a logic)   (awk, tiny)
#   antenna    OpenROAD check_antennas -verbose on LEF+DEF (the checker the OpenROAD arm's 116 nets/119 pins came from)
#   summary    condensed reports/<arm>_summary.txt
# NEVER load the Magic report into memory: it is ~1.2 GB / 27 M lines; mdrc-class streams it.
SHELL := /bin/bash
HERE  := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
REPO  := $(abspath $(HERE)/../../../..)
ARM   ?= icc2
TOP   ?= rv32i_cpu_top
include $(HERE)/arms/$(ARM).mk

PDK_ROOT ?= $(HOME)/pdk
PDK      ?= sky130A
LLS      ?= $(HOME)/tools/librelane-3562a8d/librelane/scripts
RUN      := $(HERE)/runs/$(ARM)
REP      := $(HERE)/reports
LOGS     := $(RUN)/logs
S        := $(HERE)/scripts
CTR      := $(S)/ctr.sh
GUARD    := $(S)/guard_run.sh
KLAYOUT_THREADS ?= 2
# guard knobs (override on the command line)
export SAFE_MAX_LOAD  ?= 8
export GUARD_MIN_GB   ?= 1.5
export PDK_ROOT PDK

# $(call guarded,<name>,<min avail GB to start>,<timeout s>,<cmd...>)
guarded = SAFE_MIN_AVAIL_GB=$(2) SAFE_TIMEOUT=$(3) $(GUARD) $(LOGS)/$(1).log $(ARM)_$(1) $(CTR) $(ARM)_$(1) $(4)

GDS_FIXED := $(RUN)/gds/$(TOP).fixed.gds
PIN_MODE  ?= rect
GDS_PINS  := $(if $(filter none,$(PIN_MODE)),$(GDS_FIXED),$(RUN)/gds/$(TOP).fixed_pins.gds)
.PHONY: addpins lvs-gds-variants lvs-gds lvs-gds-extract lvs-gds-netgen all dirs inspect fixgds lvs lvs-extract lvs-netgen lvs-gds kdrc mdrc mdrc-class antenna summary
all: inspect fixgds lvs kdrc antenna mdrc mdrc-class summary
dirs:
	@mkdir -p $(RUN)/{logs,gds,lvs,lvsgds,kdrc,mdrc,antenna} $(REP)

inspect: dirs
	$(call guarded,inspect,5,900,klayout -b -r $(S)/gds_inspect.py -rd gds=$(GDS_IN) -rd top=$(TOP) -rd out=$(REP)/$(ARM)_gds_inspect.txt)

fixgds: dirs
	$(call guarded,fixgds,5,900,klayout -b -r $(S)/gds_fix_refs.py -rd gds=$(GDS_IN) -rd out=$(GDS_FIXED) -rd top=$(TOP) -rd report=$(REP)/$(ARM)_gds_fixrefs.txt)

# ---- LVS, LibreLane mode: Magic.SpiceExtraction (DEF + LEF abstracts, MAGIC_EXT_USE_GDS=0) then Netgen.LVS -------------
$(RUN)/lvs/extract/env.tcl: dirs
	@mkdir -p $(RUN)/lvs/extract
	@{ cat $(S)/env/magic_extract.base.tcl; \
	   echo 'set ::env(STEP_ID) Magic.SpiceExtraction'; \
	   echo 'set ::env(CURRENT_DEF) $(DEF_IN)'; echo 'set ::env(CURRENT_GDS) $(GDS_IN)'; \
	   echo 'set ::env(SAVE_SPICE) $(RUN)/lvs/extract/$(TOP).spice'; } > $@
lvs-extract: $(RUN)/lvs/extract/env.tcl
	$(call guarded,lvs_extract,5,3600,bash $(S)/in_container/magic_step.sh $< $(RUN)/lvs/extract extract_spice.tcl)
lvs-netgen: dirs
	@mkdir -p $(RUN)/lvs/netgen/reports
	@sed -e 's#@SPICE@#$(RUN)/lvs/extract/$(TOP).spice#' -e 's#@PNL@#$(PNL_IN)#' -e 's#@TOP@#$(TOP)#g' \
	    -e 's#@RPT@#$(RUN)/lvs/netgen/reports/lvs.netgen.rpt#' -e 's#@PDK@#$(PDK_ROOT)/$(PDK)#' -e 's#@LLS@#$(LLS)#' \
	    $(S)/lvs_script.lvs.in > $(RUN)/lvs/netgen/lvs_script.lvs
	@{ cat $(S)/env/netgen.env.tcl | grep -v -E '^set ::env\((CURRENT_SPICE|CURRENT_POWERED_NETLIST)\)'; \
	   echo 'set ::env(CURRENT_SPICE) $(RUN)/lvs/extract/$(TOP).spice'; \
	   echo 'set ::env(CURRENT_POWERED_NETLIST) $(PNL_IN)'; } > $(RUN)/lvs/netgen/env.tcl
	$(call guarded,lvs_netgen,5,3600,env _TCL_ENV_IN=$(RUN)/lvs/netgen/env.tcl netgen -batch source $(RUN)/lvs/netgen/lvs_script.lvs)
	@cp $(RUN)/lvs/netgen/reports/lvs.netgen.rpt $(REP)/$(ARM)_lvs_netgen.rpt 2>/dev/null || true
lvs: lvs-extract lvs-netgen

# ---- LVS, GDS mode: Magic extraction from the (repaired) GDS, std cells + SRAM as LEF abstracts ------------------------
# (the ICC2 DEF cannot be read by Magic as-is: it names vias via_cc/mcon_cc/... that are not in the tech LEF and uses via arrays)
$(RUN)/lvsgds/extract/env.tcl: dirs
	@mkdir -p $(RUN)/lvsgds/extract
	@python3 $(S)/pg_labels.py $(DEF_IN) $(RUN)/lvsgds/pg_labels.tcl >/dev/null
	@{ cat $(S)/env/magic_extract.base.tcl; \
	   echo 'set ::env(STEP_ID) Magic.SpiceExtraction.GDS'; \
	   echo 'set ::env(CURRENT_DEF) $(DEF_IN)'; echo 'set ::env(CURRENT_GDS) $(GDS_PINS)'; \
	   echo 'set ::env(PG_LABELS) $(RUN)/lvsgds/pg_labels.tcl'; echo 'set ::env(PIN_PORTS) $(RUN)/lvsgds/pin_ports.tcl'; \
	   echo 'set ::env(SAVE_SPICE) $(RUN)/lvsgds/extract/$(TOP).spice'; } > $@
lvs-gds-extract: $(RUN)/lvsgds/extract/env.tcl
	$(CTR) pins_$(ARM) klayout -b -r $(S)/gds_pin_ports.py -rd gds=$(GDS_PINS) -rd top=$(TOP) -rd out=$(RUN)/lvsgds/pin_ports.tcl
	$(call guarded,lvsgds_extract,5,5400,bash $(S)/in_container/magic_step.sh $< $(RUN)/lvsgds/extract $(S)/magic/gds_abs_extract.tcl)
# netgen on the GDS-mode extraction. Variants (measurement copies, the layout/netlist inputs are never edited):
#   NG_TAG=            as extracted vs PNL_IN as delivered
#   NG_TAG=_clean      PNL_IN without its `supply1/0` declarations (Netgen makes phantom devices of them) and with case-colliding net
#                      names made unique (Netgen folds case: \u_core/N1435 and \u_core/n1435 become ONE net)
#   NG_TAG=_merged     _clean + extracted SPICE with the isolated well-tie (VPB) islands renamed VPWR -> shows what else differs
NG_TAG   ?=
NG_SPICE ?= $(RUN)/lvsgds/extract/$(TOP).spice
NG_PNL   ?= $(PNL_IN)
NGD      := $(RUN)/lvsgds$(NG_TAG)/netgen
$(RUN)/lvs_in/pnl.clean.v: $(PNL_IN)
	@mkdir -p $(RUN)/lvs_in
	python3 -I $(S)/fix_netlist_for_netgen.py $< $@ | tee $(RUN)/lvs_in/pnl.clean.v.log
$(RUN)/lvs_in/merged.spice: $(RUN)/lvsgds/extract/$(TOP).spice
	@mkdir -p $(RUN)/lvs_in
	python3 -I $(S)/spice_merge_islands.py $< $@ > $(RUN)/lvs_in/merged.spice.log
lvs-gds-netgen: dirs
	@mkdir -p $(NGD)/reports
	@sed -e 's#@SPICE@#$(NG_SPICE)#' -e 's#@PNL@#$(NG_PNL)#' -e 's#@TOP@#$(TOP)#g' \
	    -e 's#@RPT@#$(NGD)/reports/lvs.netgen.rpt#' -e 's#@PDK@#$(PDK_ROOT)/$(PDK)#' -e 's#@LLS@#$(LLS)#' \
	    $(S)/lvs_script.lvs.in > $(NGD)/lvs_script.lvs
	@{ cat $(S)/env/netgen.env.tcl | grep -v -E '^set ::env\((CURRENT_SPICE|CURRENT_POWERED_NETLIST)\)'; \
	   echo 'set ::env(CURRENT_SPICE) $(NG_SPICE)'; echo 'set ::env(CURRENT_POWERED_NETLIST) $(NG_PNL)'; } > $(NGD)/env.tcl
	$(call guarded,lvsgds$(NG_TAG)_netgen,5,5400,env _TCL_ENV_IN=$(NGD)/env.tcl netgen -batch source $(NGD)/lvs_script.lvs)
	@cp $(NGD)/reports/lvs.netgen.rpt $(REP)/$(ARM)_lvsgds$(NG_TAG)_netgen.rpt.full 2>/dev/null || true
lvs-gds-variants: $(RUN)/lvs_in/pnl.clean.v $(RUN)/lvs_in/merged.spice
	$(MAKE) ARM=$(ARM) lvs-gds-netgen NG_TAG=_clean NG_PNL=$(RUN)/lvs_in/pnl.clean.v
	$(MAKE) ARM=$(ARM) lvs-gds-netgen NG_TAG=_merged NG_PNL=$(RUN)/lvs_in/pnl.clean.v NG_SPICE=$(RUN)/lvs_in/merged.spice
lvs-gds: lvs-gds-extract lvs-gds-netgen

# measurement copy with the DEF pin rectangles added (ICC2 write_gds -output_pin text writes pin NAMES only, no pin metal)
addpins: dirs
	$(call guarded,addpins,5,900,klayout -b -r $(S)/gds_add_pins.py -rd gds=$(GDS_FIXED) -rd def=$(DEF_IN) -rd mode=$(PIN_MODE) -rd out=$(GDS_PINS) -rd top=$(TOP) -rd report=$(REP)/$(ARM)_gds_addpins.txt)

# ---- KLayout DRC (same options as LibreLane KLayout.DRC) ----------------------------------------------------------------
kdrc: dirs
	$(call guarded,kdrc,7,10800,klayout -b -zz -r $(PDK_ROOT)/$(PDK)/libs.tech/klayout/drc/sky130A_mr.drc \
	  -rd input=$(GDS_FIXED) -rd topcell=$(TOP) -rd report=$(RUN)/kdrc/drc_violations.klayout.xml \
	  -rd feol=true -rd beol=true -rd floating_metal=false -rd offgrid=true -rd seal=true -rd threads=$(KLAYOUT_THREADS))
	python3 -I $(S)/klayout_report_summary.py $(RUN)/kdrc/drc_violations.klayout.xml > $(REP)/$(ARM)_klayout_drc_by_rule.txt

# ---- Magic DRC. GDS mode (default): routing/vias/PG from the GDS, std cells as PDK LEF abstracts (what LibreLane's DEF-mode DRC uses),
# SRAM_MODE=real => OpenRAM internals DRC'd flat (27 M artifact violations, ~9-10 GB peak: starts only at MemAvailable >= 11 GB);
# SRAM_MODE=abstract => SRAM = LEF abstract (~3 GB). Set MDRC_MODE=def for the original LibreLane DEF mode (needs a DEF whose via
# names exist in the tech LEF: not the ICC2 DEF).
SRAM_MODE ?= real
MDRC_MODE ?= gds
MDIR := $(RUN)/mdrc_$(SRAM_MODE)
$(MDIR)/env.tcl: dirs
	@mkdir -p $(MDIR)
	@{ cat $(S)/env/magic_drc.base.tcl; \
	   echo 'set ::env(STEP_ID) Magic.DRC'; \
	   echo 'set ::env(CURRENT_DEF) $(DEF_IN)'; echo 'set ::env(CURRENT_GDS) $(GDS_FIXED)'; \
	   echo 'set ::env(SRAM_MODE) $(SRAM_MODE)'; } > $@
mdrc: $(MDIR)/env.tcl
	$(call guarded,mdrc_$(SRAM_MODE),$(if $(filter real,$(SRAM_MODE)),11,5),5400,bash $(S)/in_container/magic_step.sh $< $(MDIR) $(if $(filter gds,$(MDRC_MODE)),$(S)/magic/gds_abs_drc.tcl,drc.tcl))
mdrc-class: dirs
	python3 $(S)/sram_boxes.py $(DEF_IN) > $(RUN)/sram_boxes.txt
	$(S)/magic_drc_classify.sh $(MDIR)/reports/drc_violations.magic.rpt $(RUN)/sram_boxes.txt $(REP)/$(ARM)_magic_drc_$(SRAM_MODE)_by_rule.tsv $(MDIR)/outside_sample.txt

# ---- antenna: OpenROAD check_antennas on LEF+DEF -------------------------------------------------------------------------
ANT_MAP ?= 1
ANT_DEF := $(if $(filter 1,$(ANT_MAP)),$(RUN)/antenna/mapped.def,$(DEF_IN))
$(RUN)/antenna/mapped.def: $(DEF_IN)
	@mkdir -p $(RUN)/antenna
	$(S)/map_def_vias.sh $< $@   # ICC2: via names; Innovus: drops the 48 zero-geometry VIRTUAL stubs OpenROAD cannot parse
antenna: dirs $(if $(filter 1,$(ANT_MAP)),$(RUN)/antenna/mapped.def)
	$(call guarded,antenna,5,3600,env DEF=$(ANT_DEF) TOP=$(TOP) OUT=$(RUN)/antenna/antenna.rpt openroad -exit -no_splash $(S)/antenna_check.tcl)
	awk '/%OL_CREATE_REPORT/{f=1;next} /%OL_END_REPORT/{f=0} f' $(LOGS)/antenna.log > $(REP)/$(ARM)_antenna.rpt; grep -E 'ANT-000[12]' $(LOGS)/antenna.log

summary:
	python3 $(S)/summarize.py $(ARM) $(HERE) > $(REP)/$(ARM)_summary.txt; cat $(REP)/$(ARM)_summary.txt
