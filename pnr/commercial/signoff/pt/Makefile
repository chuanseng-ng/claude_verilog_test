# Neutral PrimeTime/PrimePower judge, Sky130 rv32i_cpu_top (task B6).  Run from this directory.
#   make judge        openroad + icc2 (StarRC SPEFs) x 9 corners, then innovus if its inputs exist, then tables
#   make rejudge      same, but re-reads every SPEF fresh and reruns anything whose SPEF/netlist/SDC/script md5 changed
#                     (this is the target to use after the StarRC SPEFs are regenerated, e.g. the tuned-ITF pass)
#   make openroad | icc2 | innovus     one arm (innovus = PENDING until b5c out/ and starrc innovus_<corner> exist: one command)
#   make rcx          OpenROAD netlist with the OpenRCX SPEFs x 9 corners (extractor-vs-engine sanity check)
#   make tables       parse runs/ -> reports/*.txt (and reports/judge_tables.md)
#   make force-<arm>  rerun that arm even when up to date (FORCE=1)
# Corners: RC {nom,min,max} x lib {tt,ss,ff}; label <rc>_<lib> = LibreLane's nom_tt_025C_1v80 ... max_ff_n40C_1v95.
# PrimePower (vectorless) runs inside the nom_tt run of each arm.  Everything runs strictly one pt_shell at a time
# (.NOTPARALLEL) under scripts/run_one.sh -> safe_run.sh (<=2 threads, 6 GB cap, process-group kill).  Never use bare `timeout`.
.DEFAULT_GOAL := judge
RCS  := nom min max
LIBS := tt ss ff
.NOTPARALLEL:
# SPEF sets.  Default = the StarRC SPEFs currently in ../starrc/runs (runs/, reports/current/).
#   make untuned   = the FROZEN untuned-ITF SPEFs in ../starrc/runs/_superseded_untuned (runs_untuned/, reports/untuned/)
# Both read their SPEFs fresh and snapshot them (md5 recorded in runs*/<tag>/inputs.txt) before each run.
untuned:
	PT_SET=untuned PT_STARRC_DIR=pnr/commercial/signoff/starrc/runs/_superseded_untuned $(MAKE) judge-set

judge-set: openroad icc2 innovus rcx tables
.PHONY: untuned judge-set judge rejudge openroad icc2 innovus rcx tables clean-runs force-openroad force-icc2 force-innovus force-rcx

judge: openroad icc2 innovus tables
rejudge: judge
openroad: ; @$(call RUNARM,openroad)
icc2:     ; @$(call RUNARM,icc2)
innovus:  ; @$(call RUNARM,innovus)
rcx:      ; @$(call RUNARM,openroad_rcx)
force-openroad: ; @export FORCE=1; $(call RUNARM,openroad)
force-icc2:     ; @export FORCE=1; $(call RUNARM,icc2)
force-innovus:  ; @export FORCE=1; $(call RUNARM,innovus)
force-rcx:      ; @export FORCE=1; $(call RUNARM,openroad_rcx)

# exit 3 from run_one.sh == PENDING inputs (reported, not an error); anything else non-zero stops the make
define RUNARM
for rc in $(RCS); do for lib in $(LIBS); do \
  pw=0; [ $$rc = nom ] && [ $$lib = tt ] && pw=1; \
  scripts/run_one.sh $(1) $$rc $$lib $$pw; r=$$?; \
  if [ $$r -eq 3 ]; then echo "$(1): PENDING (inputs absent); skipping the rest of this arm"; break 2; \
  elif [ $$r -ne 0 ]; then exit $$r; fi; \
done; done
endef

tables:
	python3 -I scripts/collect.py

clean-runs:
	rm -rf runs
