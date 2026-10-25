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

.PHONY: help all db db-verify tech redhawk nxtgrd-% techgen-% extraction-queue clean-build check-scripts
help:
	@echo "targets: db db-verify tech redhawk nxtgrd-{nom,min,max} techgen-{nom,min,max} extraction-queue clean-build"
	@echo "  db       Liberty -> .db (lc_shell) for hd tt/ss/ff + patched SRAM TT   [vendor, gated]"
	@echo "  db-verify  read the .db back (read_db) + check_library                  [vendor, gated]"
	@echo "  tech     author ITF/ICT (nom/min/max) + layer maps (python, no licence)"
	@echo "  redhawk  RedHawk .tech from the ITF via Ansys adsTechConverter.pl (perl, no licence)"
	@echo "  nxtgrd-C grdgenxo ITF -> nxtgrd + TLU+                                  [vendor, gated]"
	@echo "  techgen-C Techgen ICT -> qrcTechFile (2-D, cell-level; can take hours)   [vendor, gated]"
	@echo "  extraction-queue  all nxtgrd/techgen steps sequentially, in background-friendly order"

all: tech redhawk db db-verify extraction-queue

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
