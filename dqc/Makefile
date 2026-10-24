# dqc/Makefile - design-quality-check flow: SpyGlass lint / CDC / RDC and Cadence HAL on soc_top.
#
# LOCAL targets for an EDA host with SpyGlass + HAL licences.  CI does not run them (GitHub runners
# have no SpyGlass); CI keeps the open-source cdc_snitch gate (sim/Makefile `cdc`).
# Full description: docs/verification/DQC_FLOW.md
#
#   make -C dqc lint       SpyGlass lint/lint_rtl
#   make -C dqc cdc        SpyGlass cdc/cdc_setup_check + cdc/cdc_verify_struct
#   make -C dqc rdc        SpyGlass rdc/rdc_verify_struct
#   make -C dqc hal        Cadence HAL
#   make -C dqc selftest   negative controls (known-bad designs MUST be flagged)
#   make -C dqc all        lint cdc rdc hal (keeps going, then fails if any failed)
#   make -C dqc clean
#
# Variables:  ARM=default|sky130   (default: cocotb arm; sky130 = +define SRAM_SKY130)
#             TOP=soc_top
# Run ONE SpyGlass goal at a time on this host (shared with other heavy EDA jobs): the targets
# below are serial and `all` never uses make -j for the tool runs.
#
# Exit status: non-zero on any unwaived Fatal/Error, OR on a run whose rules did not complete
# (parse/elaboration fatal, a first-party module black-boxed, missing report).  The verdict is read
# from the SpyGlass reports by scripts/dqc_report.py, never from the tool's exit code.

SHELL := /bin/bash
.DEFAULT_GOAL := help

DQC   := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
REPO  := $(abspath $(DQC)/..)
ARM   ?= default
TOP   ?= soc_top
RUN   := $(DQC)/run/$(ARM)
PY    ?= python3
SG    ?= sg_shell
HAL   ?= hal

SGDC_SOC  := $(DQC)/sgdc/soc_top.sgdc
SGDC_ALL  := $(SGDC_SOC)
AWL_DIR   := $(DQC)/waivers
REPORT    := $(PY) $(DQC)/scripts/dqc_report.py

# Pre-flight: tools and licences are named in the failure so a missing licence is not a "clean" run.
.PHONY: help check-tools
help:
	@sed -n '2,22p' $(lastword $(MAKEFILE_LIST)) | sed 's/^# \{0,1\}//'

check-tools:
	@command -v $(SG) >/dev/null || { echo "dqc: $(SG) not on PATH (SpyGlass X-2025.06-SP1 expected)"; exit 3; }

# --- source lists (shared by SpyGlass and HAL; derived from rtl/filelist/$(TOP).f, never forked) ---
.PHONY: sources
sources:
	@mkdir -p $(RUN)
	@$(PY) $(DQC)/scripts/gen_sourcelist.py --top $(TOP) --arm $(ARM) --out $(RUN)

# $(call sg_goal,<goal>,<tag>,<sgdc files>,<awl files>,<extra dqc_report args>)  -> runs one SpyGlass goal, then judges it
define sg_goal
	@mkdir -p $(RUN)/$(2)
	@echo "dqc: SpyGlass $(1) on $(TOP) (arm=$(ARM)) ..."
	@cd $(RUN)/$(2) && \
	 DQC_RUN=$(RUN) DQC_GOAL=$(1) DQC_TOP=$(TOP) DQC_SGDC="$(3)" DQC_AWL="$(4)" \
	 /usr/bin/time -f "%e s wall, %M KB peak RSS" -o $(RUN)/$(2)/time.txt \
	 $(SG) -tcl $(DQC)/scripts/sg_run.tcl > $(RUN)/$(2)/sg_shell.out 2>&1 ; true
	@$(REPORT) --goal $(1) --run $(RUN) --tag $(2) --top $(TOP) --arm $(ARM) --awl "$(4)" $(5)
endef

LINT_AWL := $(wildcard $(AWL_DIR)/lint_*.awl)
CDC_AWL  := $(wildcard $(AWL_DIR)/cdc_*.awl)
RDC_AWL  := $(wildcard $(AWL_DIR)/rdc_*.awl)

.PHONY: lint cdc rdc cdc-setup cdc-verify
lint: check-tools sources
	$(call sg_goal,lint/lint_rtl,lint,,$(LINT_AWL))

# cdc_verify_struct and rdc_verify_struct accept NO not-run rule: the crossing rules themselves
# (Ac_unsync01/02, Ac_sync01/02, Ac_conv01-04, Ac_glitch03, Ar_resetcross01) are NOT RUN with the
# licences served today (Ac_license01: "cdc_adv_checker"), so those goals end INCOMPLETE (exit 2)
# instead of reporting a vacuous "0 unsynchronised crossings".  `make selftest` proves it.
# For cdc_setup_check only, Ar_syncrst_setupcheck01 and Ar_converge01 need the cdc_adv_checker licence feature, which the
# server does not serve (measured: Ac_license01).  They are listed, printed on every run, and the
# gap is recorded in docs/verification/DQC_FLOW.md; any OTHER not-run rule makes the goal INCOMPLETE.
NOT_RUN_OK := --accept-not-run Ar_syncrst_setupcheck01,Ar_converge01

cdc-setup: check-tools sources
	$(call sg_goal,cdc/cdc_setup_check,cdc_setup,$(SGDC_ALL),$(CDC_AWL),$(NOT_RUN_OK))

cdc-verify: check-tools sources
	$(call sg_goal,cdc/cdc_verify_struct,cdc_verify,$(SGDC_ALL),$(CDC_AWL),)

cdc: cdc-setup cdc-verify

rdc: check-tools sources
	$(call sg_goal,rdc/rdc_verify_struct,rdc,$(SGDC_ALL),$(RDC_AWL),)

# --- Cadence HAL (secondary lint) --------------------------------------------------------------
# -NOHALSYNTH: the synthesizability engine stalled indefinitely on this host (no output for 5+ min
# on a 40-line design, process alive, "Performing synthesizability checks" -- consistent with a
# licence wait); lint (halcheck) and structural (halstruct) engines run in seconds.  SpyGlass lint
# covers synthesizability.  Style-only categories are off: see docs/verification/DQC_FLOW.md.
HAL_NOCHECK ?= RTL_NAMING,RTL_FILEFORMAT,RTL_CODECOMMENT,RTL_CODINGSTYLE,CBPAHI
.PHONY: hal
hal: sources
	@command -v $(HAL) >/dev/null || { echo "dqc: $(HAL) (Cadence Xcelium HAL) not on PATH"; exit 3; }
	@rm -rf $(RUN)/hal && mkdir -p $(RUN)/hal
	@cd $(RUN)/hal && /usr/bin/time -f "%e s wall, %M KB peak RSS" -o $(RUN)/hal/time.txt \
	 $(HAL) -sv -top $(TOP) -NOHALSYNTH -NOCHECK $(HAL_NOCHECK) \
	  $$(sed -e 's/^-incdir /-incdir /' $(RUN)/sources.f | tr '\n' ' ') \
	  < /dev/null > $(RUN)/hal/hal.out 2>&1 ; true
	@$(PY) $(DQC)/scripts/hal_report.py --log $(RUN)/hal/hal.log --waivers $(AWL_DIR)/hal.waivers \
	  --arm $(ARM) --timing "$$(tail -1 $(RUN)/hal/time.txt)" --out $(RUN)/hal

# --- negative control --------------------------------------------------------------------------
.PHONY: selftest
selftest: check-tools
	@$(PY) $(DQC)/scripts/selftest.py

# --- everything: keep going so one red goal does not hide the others; fail if any failed --------
.PHONY: all
all:
	@rc=0; for t in lint cdc rdc hal; do $(MAKE) --no-print-directory $$t || rc=1; done; \
	 echo "dqc all: $$([ $$rc = 0 ] && echo PASS || echo FAIL) (see per-goal verdicts above)"; exit $$rc

clean:
	rm -rf $(DQC)/run
