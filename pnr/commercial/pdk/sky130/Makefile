# Sky130 commercial-PDK enablement (part 1).  Run from this directory:  make help
#   Needs:  source tools/eda/pd_env.sh   (PDK_ROOT, SKY130_* view variables, licences, tools on PATH)
# Vendor tools (lc_shell, grdgenxo, Techgen) run through scripts/safe_run.sh:
#   one at a time, memory-capped (3G), nice'd, single-threaded, started only when loadavg1 < 6 and MemAvailable >= 4G,
#   whole process group killed on timeout.  Do NOT run these targets in parallel (make -j1 only).
SHELL := /bin/bash
.NOTPARALLEL:
HERE  := $(CURDIR)
B     := $(HERE)/build
REPO  := $(abspath $(HERE)/../../../..)
SRAM_PATCHED := $(REPO)/pnr/sky130/cpu/pdk_lib_patched/sky130_sram_1kbyte_1rw1r_32x256_8_TT_1p8V_25C.lib
CORNERS_HD := tt_025C_1v80 ss_100C_1v60 ff_n40C_1v95
PE := source $(REPO)/tools/eda/pd_env.sh >/dev/null 2>&1

.PHONY: ndm techfile link-check-dc link-check-pt load-genus load-innovus load-redhawk load-icc2 part2a help all db db-verify tech redhawk nxtgrd-% techgen-% extraction-queue clean-build check-scripts
help:
	@echo "targets: db db-verify tech redhawk nxtgrd-{nom,min,max} techgen-{nom,min,max} extraction-queue clean-build"
	@echo "  db       Liberty -> .db (lc_shell) for hd tt/ss/ff + patched SRAM TT   [vendor, gated]"
	@echo "  db-verify  read the .db back (read_db) + check_library                  [vendor, gated]"
	@echo "  tech     author ITF/ICT (nom/min/max) + layer maps (python, no licence)"
	@echo "  redhawk  RedHawk .tech from the ITF via Ansys adsTechConverter.pl (perl, no licence)"
	@echo "  nxtgrd-C grdgenxo ITF -> nxtgrd + TLU+                                  [vendor, gated]"
	@echo "  techgen-C Techgen ICT -> qrcTechFile (2-D, cell-level; can take hours)   [vendor, gated]"
	@echo "  techfile  derive the ICC2 .tf (+ layer dirs, tracks, antenna Tcl) from the tech LEF (python, no licence)"
	@echo "  ndm       icc2_lm_shell: reference NDMs  sky130_hd_{tt,ss,ff}, sky130_hd_phys, sky130_sram_*   [vendor, gated]"
	@echo "  link-check-dc / link-check-pt   dcnxt_shell (NDM, topo) / pt_shell link of tests/link_trivial.v   [vendor, gated]"
	@echo "  load-genus / load-innovus / load-redhawk   MMMC+LEF+netlist load tests (Genus, Innovus), RedHawk tech+DEF import"
	@echo "  part2a    ndm + all link/load checks, one tool at a time"
	@echo "  extraction-queue  all nxtgrd/techgen steps sequentially, in background-friendly order"

all: tech redhawk db db-verify extraction-queue

# ---- part 2a: NDM build + link / load checks (every vendor run through safe_run.sh; one tool at a time) ----
# Common env: HERE (this dir), SDC (trivial SDC for the load tests), REPO.   Peak RSS measured: lm_shell 0.45 GB,
# dcnxt 0.68 GB, pt 1.1 GB, genus 0.65 GB, innovus 2.5 GB, redhawk 0.4 GB (3 GB cap in safe_run is NOT enough for innovus: SAFE_MEM_MAX=6G).
RUN2A = export HERE=$(HERE) SDC=$(HERE)/tests/link_trivial.sdc REPO=$(REPO) SAFE_MEM_MAX=6G SAFE_THREADS=1 SAFE_TIMEOUT=900

techfile: | $(B)/logs
	@$(PE); python3 -I scripts/gen_techfile.py

ndm: techfile
	@$(PE); $(RUN2A); mkdir -p $(B)/work/ndm; cd $(B)/work/ndm; for c in tt ss ff phys sram; do \
	  CORNER=$$c $(HERE)/scripts/safe_run.sh $(B)/logs/ndm_$$c.log icc2_lm_shell -f $(HERE)/scripts/build_ndm.tcl; \
	  grep -q "Workspace check succeeded" $(B)/logs/ndm_$$c.log && grep -q "wrote .*ndm" $(B)/logs/ndm_$$c.log || { echo "NDM $$c FAILED"; exit 1; }; done; echo "NDM OK"

link-check-dc:
	@$(PE); $(RUN2A); mkdir -p $(B)/work/dc; cd $(B)/work/dc; $(HERE)/scripts/safe_run.sh $(B)/logs/dc_link.log dcnxt_shell -topographical_mode -f $(HERE)/scripts/link_check_dc.tcl; \
	  grep -q "LINK_RESULT: 1" $(B)/logs/dc_link.log && echo "DC LINK OK" || { echo "DC LINK FAILED"; exit 1; }

link-check-pt:
	@$(PE); $(RUN2A); mkdir -p $(B)/work/pt; cd $(B)/work/pt; $(HERE)/scripts/safe_run.sh $(B)/logs/pt_link.log pt_shell -f $(HERE)/scripts/link_check_pt.tcl; \
	  test $$(grep -c "^LINK_OK" $(B)/logs/pt_link.log) -eq 3 && echo "PT LINK OK (3 corners)" || { echo "PT LINK FAILED"; exit 1; }

load-genus:
	@$(PE); $(RUN2A); mkdir -p $(B)/work/genus; cd $(B)/work/genus; $(HERE)/scripts/safe_run.sh $(B)/logs/genus_load.log genus -no_gui -overwrite -files $(HERE)/scripts/load_genus.tcl; \
	  grep -q "Path 1: MET" $(B)/logs/genus_load.log && echo "GENUS LOAD OK" || { echo "GENUS LOAD FAILED"; exit 1; }

load-innovus:
	@$(PE); $(RUN2A); mkdir -p $(B)/work/innovus; cd $(B)/work/innovus; $(HERE)/scripts/safe_run.sh $(B)/logs/innovus_load.log innovus -nowin -overwrite -files $(HERE)/scripts/load_innovus.tcl -log innovus_run; \
	  test -s $(B)/work/innovus/link_trivial_fp.def && ! grep -q "^\*\*ERROR" $(B)/logs/innovus_load.log && echo "INNOVUS LOAD OK" || { echo "INNOVUS LOAD FAILED"; exit 1; }

load-icc2:
	@$(PE); $(RUN2A); mkdir -p $(B)/work/icc2; cd $(B)/work/icc2; $(HERE)/scripts/safe_run.sh $(B)/logs/icc2_load.log icc2_shell -f $(HERE)/scripts/load_icc2.tcl; \
	  grep -q "was successfully linked" $(B)/logs/icc2_load.log && grep -q "Initializing floorplan completed" $(B)/logs/icc2_load.log && echo "ICC2 LOAD OK" || { echo "ICC2 LOAD FAILED"; exit 1; }

# RedHawk: GSR + run.tcl are generated into build/work/redhawk by scripts/load_redhawk.sh (needs load-innovus's DEF)
load-redhawk:
	@$(PE); $(RUN2A); scripts/load_redhawk.sh

part2a: ndm link-check-dc link-check-pt load-icc2 load-genus load-innovus load-redhawk

$(B)/logs $(B)/db:
	mkdir -p $@

db: | $(B)/logs $(B)/db
	@$(PE); for c in $(CORNERS_HD); do \
	  scripts/lib2db.sh $$SKY130_HD_LIB/sky130_fd_sc_hd__$$c.lib $(B)/db/sky130_fd_sc_hd__$$c.db $(B)/logs/lc_$$c.log || exit 1; done; \
	  scripts/lib2db.sh $(SRAM_PATCHED) $(B)/db/sky130_sram_1kbyte_1rw1r_32x256_8_TT_1p8V_25C.db $(B)/logs/lc_sram.log

db-verify: | $(B)/logs
	@$(PE); mkdir -p $(B)/lc_work/verify; cd $(B)/lc_work/verify && DB_DIR=$(B)/db $(HERE)/scripts/safe_run.sh $(B)/logs/lc_verify.log lc_shell -f $(HERE)/scripts/verify_db.tcl; \
	  rm -f $(B)/lc_work/verify/Synopsys_stack_trace_* $(B)/lc_work/verify/crte_*; \
	  grep -E "VERIFY: libs|Number of cells missing pg_pins" $(B)/logs/lc_verify.log

tech: | $(B)/logs
	python3 -I scripts/gen_stack.py --out $(B)/tech
	@$(PE); python3 -I scripts/corner_scale.py
	python3 -I scripts/stack_calibrate.py > $(B)/tech/stack_calibration.txt; tail -3 $(B)/tech/stack_calibration.txt

redhawk: tech
	scripts/gen_redhawk_tech.sh

nxtgrd-%: tech
	@$(PE); scripts/run_grdgenxo.sh $*

techgen-%: tech
	@$(PE); scripts/run_techgen.sh $*

extraction-queue: tech
	scripts/queue_extraction.sh

check-scripts:
	bash -n scripts/*.sh && python3 -I -m py_compile scripts/*.py && echo scripts OK

clean-build:
	rm -rf $(B)
